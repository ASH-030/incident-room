"""Authenticated API for configured BigQuery projects. No fixture or simulated identity path."""
from __future__ import annotations
import os
from pathlib import Path
from fastapi import FastAPI,Depends,Header,HTTPException,Request,Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel,Field
from dotenv import load_dotenv
from .storage import Store,Conflict
from .errors import Rejected
from .live_service import LiveService
from .auth import AuthStore,SESSION_COOKIE,CHALLENGE_COOKIE,check_origin,legacy_enabled,origins,production,validate_production

ROOT=Path(__file__).resolve().parents[2]
load_dotenv(ROOT/'.env')
validate_production()
DATA=Path(os.getenv('ROOM_DATA_DIR',str(ROOT/'runtime')))
DATA.mkdir(parents=True,exist_ok=True)
store=Store(os.getenv('DATABASE_URL','sqlite:///'+(DATA/'room-live.db').as_posix()))
service=LiveService(store,DATA/'jobs')
auth=AuthStore(store)
app=FastAPI(title='Incident Room',version='1.0.0')
app.add_middleware(CORSMiddleware,allow_origins=sorted(origins()),allow_credentials=True,allow_methods=['GET','POST'],allow_headers=['Authorization','Content-Type','X-CSRF-Token'])


def identity(request:Request,authorization:str=Header(default='')):return auth.identity(request,authorization)


def editor(actor=Depends(identity)):
    if actor['role'] not in {'finance','engineering'}:raise HTTPException(403,'A finance or engineering membership is required')
    return actor


@app.middleware('http')
async def security_headers(request,call_next):
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    response.headers['Cache-Control']='no-store'
    return response


@app.exception_handler(Rejected)
async def rejected(request,exc):return JSONResponse({'detail':str(exc)},status_code=409)


@app.exception_handler(Conflict)
async def conflicted(request,exc):return JSONResponse({'detail':str(exc)},status_code=409)


@app.exception_handler(KeyError)
async def missing(request,exc):return JSONResponse({'detail':'Unknown incident'},status_code=404)


@app.exception_handler(ValueError)
async def invalid(request,exc):return JSONResponse({'detail':str(exc)},status_code=422)


@app.get('/api/health')
def health():
    blockers=[]
    if not os.getenv('GOOGLE_CLIENT_ID') and (not legacy_enabled() or not os.getenv('ROOM_TOKENS') or os.getenv('ROOM_TOKENS')=='{}'):blockers.append('Reviewer sign-in not configured')
    if not os.getenv('OPENAI_API_KEY') or not os.getenv('OPENAI_MODEL'):blockers.append('OpenAI model access not configured')
    if not os.getenv('PROJECT_CONFIG') or not Path(os.getenv('PROJECT_CONFIG','')).is_file():blockers.append('BigQuery project configuration not supplied')
    return {'status':'configured' if not blockers else 'configuration_required','live_connection_verified':False,'blockers':blockers,'storage':store.engine.dialect.name,'switch_configured':all(os.getenv(k) for k in ['SWITCH_BASE_URL','SWITCH_AGENT_ID','SWITCH_API_KEY','SWITCH_ROOM_ID'])}


@app.get('/api/auth/config')
def auth_config():return {'google_client_id':os.getenv('GOOGLE_CLIENT_ID') or None,'legacy_tokens_enabled':legacy_enabled()}


@app.get('/api/auth/challenge')
def auth_challenge(response:Response):
    if not os.getenv('GOOGLE_CLIENT_ID'):raise HTTPException(503,'Google sign-in has not been configured')
    token,nonce=auth.challenge()
    response.set_cookie(CHALLENGE_COOKIE,token,max_age=300,httponly=True,secure=production(),samesite='lax',path='/api/auth')
    return {'nonce':nonce}


class GoogleLogin(BaseModel):
    credential:str=Field(min_length=20,max_length=16384)


@app.post('/api/auth/google')
def google_login(body:GoogleLogin,request:Request,response:Response):
    check_origin(request)
    token,actor=auth.login(body.credential,request.cookies.get(CHALLENGE_COOKIE))
    auth.logout(request.cookies.get(SESSION_COOKIE))
    response.set_cookie(SESSION_COOKIE,token,max_age=28_800,httponly=True,secure=production(),samesite='lax',path='/')
    response.delete_cookie(CHALLENGE_COOKIE,path='/api/auth',httponly=True,secure=production(),samesite='lax')
    return actor


@app.post('/api/auth/logout')
def logout(request:Request,response:Response,actor=Depends(identity)):
    auth.logout(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE,path='/',httponly=True,secure=production(),samesite='lax')
    return {'signed_out':True}


@app.get('/api/me')
def me(actor=Depends(identity)):return actor


@app.get('/api/project')
def project(actor=Depends(identity)):
    p=service.project()
    return {'name':p.config.name,'schema':p.schema(),'metadata':p.metadata(),'metrics':p.metrics(),'transforms':p.config.transforms}


@app.get('/api/incidents')
def incidents(actor=Depends(identity)):return sorted(store.all(),key=lambda d:d['created_at'],reverse=True)


class OpenIn(BaseModel):
    report:str=Field(min_length=5,max_length=6000)
    room_id:str|None=None


class ActionIn(BaseModel):
    expected_version:int=Field(ge=1)
    payload:dict=Field(default_factory=dict)


@app.post('/api/incidents')
def create(body:OpenIn,actor=Depends(editor)):return service.create(actor,body.report,body.room_id)


@app.get('/api/incidents/{iid}')
def get(iid:str,actor=Depends(identity)):
    with service.lock:return {**store.get(iid),'audit':store.history(iid)}


@app.post('/api/incidents/{iid}/{action}')
def act(iid:str,action:str,body:ActionIn,actor=Depends(editor)):
    out=service.mutate(iid,actor,body.expected_version,action,body.payload)
    return {**out,'audit':store.history(iid)}
