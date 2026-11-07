"""Google identity, persistent reviewer membership and revocable browser sessions."""
from __future__ import annotations
import hashlib
import hmac
import json
import os
import secrets
import time
from urllib.parse import urlsplit
from fastapi import HTTPException,Request
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from sqlalchemy import MetaData,Table,Column,String,Integer,Boolean,select,insert,update,delete

ROLES={'finance','engineering','viewer'}
SESSION_COOKIE='ir_session'
CHALLENGE_COOKIE='ir_login'


def hashed(value):return hashlib.sha256(value.encode('utf-8')).hexdigest()


def production():return os.getenv('APP_ENV','local')=='production'


def legacy_enabled():return not production() and os.getenv('ALLOW_REVIEWER_TOKENS','true').lower()=='true'


def origins():
    configured=os.getenv('APP_ORIGINS','http://localhost:3000,http://127.0.0.1:3000')
    return {value.strip().rstrip('/') for value in configured.split(',') if value.strip()}


def validate_production():
    if not production():return
    if not os.getenv('GOOGLE_CLIENT_ID'):raise ValueError('Production requires GOOGLE_CLIENT_ID')
    if not os.getenv('DATABASE_URL'):raise ValueError('Production requires a persistent DATABASE_URL')
    if not os.getenv('APP_ORIGINS') or any(urlsplit(value).scheme!='https' for value in origins()):raise ValueError('Production requires explicit HTTPS APP_ORIGINS')


def check_origin(request):
    if request.headers.get('origin','').rstrip('/') not in origins():raise HTTPException(403,'Request origin is not allowed')


class AuthStore:
    def __init__(self,store):
        self.engine=store.engine
        meta=MetaData()
        self.members=Table('auth_members',meta,Column('email',String,primary_key=True),Column('role',String,nullable=False),Column('name',String,nullable=False),Column('enabled',Boolean,nullable=False))
        self.users=Table('auth_users',meta,Column('id',String,primary_key=True),Column('email',String,unique=True,nullable=False),Column('name',String,nullable=False))
        self.sessions=Table('auth_sessions',meta,Column('hash',String,primary_key=True),Column('user_id',String,nullable=False),Column('csrf',String,nullable=False),Column('expires',Integer,nullable=False))
        self.challenges=Table('auth_challenges',meta,Column('hash',String,primary_key=True),Column('nonce',String,nullable=False),Column('expires',Integer,nullable=False))
        self.bindings=Table('auth_switch_bindings',meta,Column('sender',String,primary_key=True),Column('email',String,nullable=False))
        meta.create_all(self.engine)
        for email,member in json.loads(os.getenv('AUTH_MEMBERS','{}')).items():
            member={'role':member} if isinstance(member,str) else member
            if not self.member(email):self.set_member(email,member['role'],member.get('name',''))

    def member(self,email):
        with self.engine.connect() as conn:
            row=conn.execute(select(self.members).where(self.members.c.email==email.strip().lower())).mappings().first()
            return dict(row) if row else None

    def set_member(self,email,role,name='',enabled=True):
        email=email.strip().lower()
        if '@' not in email or len(email)>320 or role not in ROLES:raise ValueError('Supply a valid member email and finance, engineering or viewer role')
        values={'email':email,'role':role,'name':name.strip(),'enabled':enabled}
        with self.engine.begin() as conn:
            current=conn.execute(select(self.members.c.email).where(self.members.c.email==email)).first()
            conn.execute(update(self.members).where(self.members.c.email==email).values(**values) if current else insert(self.members).values(**values))
            # Role changes and revocation end existing sessions, requiring fresh sign-in.
            user=conn.execute(select(self.users.c.id).where(self.users.c.email==email)).first()
            if user:conn.execute(delete(self.sessions).where(self.sessions.c.user_id==user[0]))

    def challenge(self):
        token,nonce=secrets.token_urlsafe(32),secrets.token_urlsafe(32)
        stamp=int(time.time())
        with self.engine.begin() as conn:
            conn.execute(delete(self.challenges).where(self.challenges.c.expires<stamp))
            conn.execute(delete(self.sessions).where(self.sessions.c.expires<stamp))
            conn.execute(insert(self.challenges).values(hash=hashed(token),nonce=nonce,expires=stamp+300))
        return token,nonce

    def login(self,credential,challenge_token):
        client_id=os.getenv('GOOGLE_CLIENT_ID','')
        if not client_id:raise HTTPException(503,'Google sign-in has not been configured')
        if not challenge_token:raise HTTPException(401,'Start a fresh Google sign-in')
        with self.engine.connect() as conn:
            challenge=conn.execute(select(self.challenges).where(self.challenges.c.hash==hashed(challenge_token))).mappings().first()
        if not challenge or challenge['expires']<=int(time.time()):raise HTTPException(401,'Sign-in expired. Start a fresh Google sign-in')
        try:claims=id_token.verify_oauth2_token(credential,GoogleRequest(),client_id)
        except Exception:raise HTTPException(401,'Google could not verify this sign-in') from None
        if claims.get('iss') not in {'accounts.google.com','https://accounts.google.com'} or claims.get('email_verified') is not True or not claims.get('sub'):raise HTTPException(401,'A verified Google identity is required')
        nonce=claims.get('nonce')
        if not isinstance(nonce,str) or not hmac.compare_digest(nonce,challenge['nonce']):raise HTTPException(401,'Google sign-in challenge does not match')
        email=str(claims.get('email','')).lower()
        # Gmail and Workspace claims are authoritative for these invited accounts.
        if not email.endswith('@gmail.com') and not claims.get('hd'):raise HTTPException(403,'Use an invited Gmail or Google Workspace account')
        member=self.member(email)
        if not member or not member['enabled']:raise HTTPException(403,'This Google account has not been invited to the workspace')
        uid='google:'+str(claims['sub'])
        name=str(claims.get('name') or email)
        token,csrf=secrets.token_urlsafe(32),secrets.token_urlsafe(32)
        with self.engine.begin() as conn:
            consumed=conn.execute(delete(self.challenges).where(self.challenges.c.hash==hashed(challenge_token),self.challenges.c.expires>int(time.time())))
            if consumed.rowcount!=1:raise HTTPException(401,'Google sign-in challenge was already used')
            user=conn.execute(select(self.users).where(self.users.c.id==uid)).mappings().first()
            if user and user['email']!=email:raise HTTPException(403,'Google account email changed; ask the workspace operator to review the membership')
            other=conn.execute(select(self.users.c.id).where(self.users.c.email==email)).first()
            if other and other[0]!=uid:raise HTTPException(403,'Membership is already linked to a different Google identity')
            conn.execute(update(self.users).where(self.users.c.id==uid).values(name=name) if user else insert(self.users).values(id=uid,email=email,name=name))
            conn.execute(insert(self.sessions).values(hash=hashed(token),user_id=uid,csrf=csrf,expires=int(time.time())+28_800))
        return token,{'id':uid,'email':email,'name':member['name'] or name,'role':member['role'],'auth_method':'google','csrf_token':csrf}

    def session(self,token):
        if not token:return None
        with self.engine.connect() as conn:
            row=conn.execute(select(self.sessions,self.users.c.email,self.users.c.name).join(self.users,self.sessions.c.user_id==self.users.c.id).where(self.sessions.c.hash==hashed(token),self.sessions.c.expires>int(time.time()))).mappings().first()
        if not row:return None
        member=self.member(row['email'])
        if not member or not member['enabled']:return None
        return {'id':row['user_id'],'email':row['email'],'name':member['name'] or row['name'],'role':member['role'],'auth_method':'google','csrf_token':row['csrf']}

    def logout(self,token):
        if not token:return
        with self.engine.begin() as conn:conn.execute(delete(self.sessions).where(self.sessions.c.hash==hashed(token)))

    def bind_switch(self,sender,email):
        member=self.member(email)
        if not member or not member['enabled']:raise ValueError('Invite this Google account before binding its Switch participant')
        with self.engine.begin() as conn:
            current=conn.execute(select(self.bindings.c.sender).where(self.bindings.c.sender==sender)).first()
            values={'sender':sender,'email':member['email']}
            conn.execute(update(self.bindings).where(self.bindings.c.sender==sender).values(**values) if current else insert(self.bindings).values(**values))

    def switch_actor(self,sender):
        with self.engine.connect() as conn:
            row=conn.execute(select(self.users).join(self.bindings,self.bindings.c.email==self.users.c.email).where(self.bindings.c.sender==sender)).mappings().first()
        if not row:raise HTTPException(403,'Bind this Switch participant to an invited account, then sign in with Google in the dashboard once')
        member=self.member(row['email'])
        if not member or not member['enabled']:raise HTTPException(403,'This workspace membership has been revoked')
        return {'id':row['id'],'email':row['email'],'name':member['name'] or row['name'],'role':member['role'],'auth_method':'switch'}

    def identity(self,request:Request,authorization=''):
        supplied=authorization[7:] if authorization.startswith('Bearer ') else ''
        service_key=os.getenv('SWITCH_ADAPTER_TOKEN','')
        if supplied and service_key and hmac.compare_digest(supplied,service_key):return self.switch_actor(request.headers.get('x-switch-sender',''))
        if supplied and legacy_enabled():
            for token,actor in json.loads(os.getenv('ROOM_TOKENS','{}')).items():
                if hmac.compare_digest(supplied,token) and actor.get('name') and actor.get('role') in ROLES:
                    return {**actor,'id':actor.get('id') or 'legacy:'+actor['name'].strip().casefold(),'auth_method':'token'}
        actor=self.session(request.cookies.get(SESSION_COOKIE))
        if not actor:raise HTTPException(401,'Sign in to your workspace')
        if request.method not in {'GET','HEAD','OPTIONS'}:
            check_origin(request)
            csrf=request.headers.get('x-csrf-token','')
            if not csrf or not hmac.compare_digest(csrf,actor['csrf_token']):raise HTTPException(403,'Session request could not be verified; reload the page')
        return actor
