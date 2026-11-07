from types import SimpleNamespace as NS
import pytest
from fastapi.testclient import TestClient
from incident_room import app as module
from incident_room import auth as auth_module
from incident_room.auth import AuthStore,validate_production
from incident_room.storage import Store
from incident_room.live_service import LiveService

CLIENT_ID='test-client.apps.googleusercontent.com'
ORIGIN='http://localhost:3000'


@pytest.fixture
def setup(tmp_path,monkeypatch):
    monkeypatch.setenv('GOOGLE_CLIENT_ID',CLIENT_ID)
    monkeypatch.setenv('APP_ENV','local')
    monkeypatch.setenv('APP_ORIGINS',ORIGIN)
    monkeypatch.setenv('AUTH_MEMBERS','{}')
    store=Store('sqlite:///'+(tmp_path/'auth.db').as_posix())
    auth=AuthStore(store)
    auth.set_member('finance@gmail.com','finance')
    auth.set_member('engineering@gmail.com','engineering')
    auth.set_member('viewer@gmail.com','viewer')
    service=LiveService(store,tmp_path/'jobs')
    monkeypatch.setattr(module,'store',store);monkeypatch.setattr(module,'auth',auth);monkeypatch.setattr(module,'service',service)
    with TestClient(module.app) as client:yield client,auth
    service.pool.shutdown()


def sign_in(client,monkeypatch,email='finance@gmail.com',**overrides):
    challenge=client.get('/api/auth/challenge')
    assert challenge.status_code==200
    claims={'sub':email.split('@')[0]+'-google-id','email':email,'email_verified':True,'iss':'https://accounts.google.com','name':'Reviewer','nonce':challenge.json()['nonce']}
    claims.update(overrides)
    def verify(token,request,audience):
        assert audience==CLIENT_ID
        return claims
    monkeypatch.setattr(auth_module.id_token,'verify_oauth2_token',verify)
    return client.post('/api/auth/google',headers={'Origin':ORIGIN},json={'credential':'signed-google-id-token-for-unit-test'})


def test_google_login_uses_invited_role_and_persistent_secure_session(setup,monkeypatch):
    client,auth=setup
    result=sign_in(client,monkeypatch)
    assert result.status_code==200 and result.json()['role']=='finance'
    assert result.json()['id']=='google:finance-google-id'
    cookie=next(c for c in result.headers.get_list('set-cookie') if c.startswith('ir_session='))
    assert 'HttpOnly' in cookie and 'SameSite=lax' in cookie
    assert 'token' not in result.json()
    assert client.get('/api/me').json()['role']=='finance'
    restarted=AuthStore(Store(str(auth.engine.url)))
    assert restarted.session(client.cookies.get('ir_session'))['id']=='google:finance-google-id'
    with auth.engine.connect() as conn:
        row=conn.execute(auth.sessions.select()).mappings().first()
        assert row['hash']!=client.cookies.get('ir_session')


@pytest.mark.parametrize('overrides,status',[
    ({'email':'uninvited@gmail.com'},403),
    ({'email_verified':False},401),
    ({'nonce':'wrong-nonce'},401),
    ({'iss':'https://untrusted.example'},401),
])
def test_invalid_or_uninvited_google_identity_rejected(setup,monkeypatch,overrides,status):
    client,auth=setup
    assert sign_in(client,monkeypatch,**overrides).status_code==status
    assert client.get('/api/me').status_code==401


def test_challenge_cannot_be_replayed(setup,monkeypatch):
    client,auth=setup
    assert sign_in(client,monkeypatch).status_code==200
    result=client.post('/api/auth/google',headers={'Origin':ORIGIN},json={'credential':'signed-google-id-token-for-unit-test'})
    assert result.status_code==401


def test_cookie_writes_require_correct_origin_and_csrf(setup,monkeypatch):
    client,auth=setup
    actor=sign_in(client,monkeypatch).json()
    body={'report':'A real investigation request'}
    assert client.post('/api/incidents',json=body).status_code==403
    assert client.post('/api/incidents',headers={'Origin':ORIGIN},json=body).status_code==403
    assert client.post('/api/incidents',headers={'Origin':'https://attacker.example','X-CSRF-Token':actor['csrf_token']},json=body).status_code==403
    assert client.post('/api/incidents',headers={'Origin':ORIGIN,'X-CSRF-Token':actor['csrf_token']},json=body).status_code==200


def test_membership_revocation_ends_existing_access(setup,monkeypatch):
    client,auth=setup
    assert sign_in(client,monkeypatch).status_code==200
    auth.set_member('finance@gmail.com','finance',enabled=False)
    assert client.get('/api/me').status_code==401


def test_viewer_can_read_but_cannot_open_or_approve_incidents(setup,monkeypatch):
    client,auth=setup
    actor=sign_in(client,monkeypatch,email='viewer@gmail.com').json()
    assert client.get('/api/incidents').status_code==200
    assert client.post('/api/incidents',headers={'Origin':ORIGIN,'X-CSRF-Token':actor['csrf_token']},json={'report':'Attempted change by viewer'}).status_code==403


def test_logout_revokes_server_session(setup,monkeypatch):
    client,auth=setup
    actor=sign_in(client,monkeypatch).json()
    assert client.post('/api/auth/logout',headers={'Origin':ORIGIN,'X-CSRF-Token':actor['csrf_token']}).status_code==200
    assert client.get('/api/me').status_code==401


def test_switch_service_cannot_choose_actor_by_name_or_role(setup,monkeypatch):
    client,auth=setup
    sign_in(client,monkeypatch)
    auth.bind_switch('@opaque:server','finance@gmail.com')
    monkeypatch.setenv('SWITCH_ADAPTER_TOKEN','service-test-token')
    client.cookies.clear()
    headers={'Authorization':'Bearer service-test-token','X-Switch-Sender':'@opaque:server','X-Demo-Role':'engineering'}
    result=client.get('/api/me',headers=headers)
    assert result.status_code==200 and result.json()['role']=='finance'
    assert result.json()['id']=='google:finance-google-id'
    headers['X-Switch-Sender']='@unbound:server'
    assert client.get('/api/me',headers=headers).status_code==403


def test_production_rejects_local_reviewer_tokens(setup,monkeypatch):
    client,auth=setup
    monkeypatch.setenv('APP_ENV','production')
    monkeypatch.setenv('ROOM_TOKENS','{"test-token":{"name":"Reviewer","role":"finance"}}')
    assert client.get('/api/me',headers={'Authorization':'Bearer test-token'}).status_code==401


def test_production_requires_explicit_authentication_and_https(monkeypatch):
    monkeypatch.setenv('APP_ENV','production')
    monkeypatch.delenv('GOOGLE_CLIENT_ID',raising=False)
    with pytest.raises(ValueError,match='GOOGLE_CLIENT_ID'):validate_production()
    monkeypatch.setenv('GOOGLE_CLIENT_ID',CLIENT_ID)
    monkeypatch.setenv('DATABASE_URL','postgresql+psycopg://user:password@db/incident')
    monkeypatch.setenv('APP_ORIGINS',ORIGIN)
    with pytest.raises(ValueError,match='HTTPS'):validate_production()
