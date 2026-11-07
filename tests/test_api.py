import json
import pytest
from fastapi.testclient import TestClient
from incident_room import app as module
from incident_room.live_service import LiveService
from incident_room.storage import Store
from incident_room.auth import AuthStore


@pytest.fixture
def client(tmp_path,monkeypatch):
    store=Store('sqlite:///'+(tmp_path/'http.db').as_posix())
    service=LiveService(store,tmp_path/'jobs')
    monkeypatch.setattr(module,'store',store)
    monkeypatch.setattr(module,'service',service)
    monkeypatch.setattr(module,'auth',AuthStore(store))
    monkeypatch.setenv('ROOM_TOKENS',json.dumps({'finance-test':{'name':'Finance','role':'finance'},'engineer-test':{'name':'Engineering','role':'engineering'}}))
    with TestClient(module.app) as c:yield c
    service.pool.shutdown()


def test_no_simulated_authentication(client):
    assert client.get('/api/incidents').status_code==401
    assert client.get('/api/incidents',headers={'X-Demo-Role':'finance'}).status_code==401
    assert client.get('/api/me',headers={'Authorization':'Bearer wrong'}).status_code==401
    assert client.get('/api/me',headers={'Authorization':'Bearer finance-test'}).json()['role']=='finance'


def test_http_context_and_concurrency_guards(client):
    headers={'Authorization':'Bearer engineer-test'}
    assert client.post('/api/incidents',headers=headers,json={}).status_code==422
    doc=client.post('/api/incidents',headers=headers,json={'report':'Investigate net revenue'}).json()
    url=f"/api/incidents/{doc['id']}/definition"
    body={'expected_version':doc['version'],'payload':{'definition':'Net settled revenue excluding tax'}}
    assert client.post(url,headers=headers,json=body).status_code==409
    finance={'Authorization':'Bearer finance-test'}
    assert client.post(url,headers=finance,json=body).status_code==200
    assert client.post(url,headers=finance,json=body).status_code==409
    assert client.get('/api/incidents/unknown',headers=headers).status_code==404


def test_health_never_claims_live_connections_validated(client):
    assert client.get('/api/health').json()['live_connection_verified'] is False
