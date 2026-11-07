import asyncio
import json
import threading
from types import SimpleNamespace as NS
from unittest.mock import Mock
from urllib.parse import urlsplit,parse_qs
import pytest
from incident_room import switch_adapter as adapter
from incident_room.storage import Store


def test_unassigned_switch_sender_cannot_execute(monkeypatch):
    monkeypatch.setenv('SWITCH_MEMBERS','{}')
    assert 'not assigned' in adapter.dispatch('room','@unassigned:server','!repair')


def test_switch_commands_use_bearer_actor_not_claimed_role(monkeypatch):
    monkeypatch.setenv('SWITCH_MEMBERS',json.dumps({'@person:server':{'name':'Name','role':'finance','token':'assigned-token'}}))
    client=Mock()
    client.__enter__=Mock(return_value=client);client.__exit__=Mock(return_value=False)
    client.get.return_value.json.return_value=[{'id':'12345678','room_id':'room','created_at':'today','version':7}]
    client.get.return_value.status_code=200
    client.post.return_value.json.return_value={'id':'12345678','stage':'NEEDS_REVIEW','revision':2,'definition':'Net after refunds','approvals':{},'proposal':None}
    client.post.return_value.status_code=200
    constructor=Mock(return_value=client)
    monkeypatch.setattr(adapter.httpx,'Client',constructor)
    adapter.dispatch('room','@person:server','!definition Net after refunds')
    assert constructor.call_args.kwargs['headers']=={'Authorization':'Bearer assigned-token'}
    sent=client.post.call_args.kwargs['json']
    assert sent=={'expected_version':7,'payload':{'definition':'Net after refunds'}}


def test_service_identity_uses_server_binding_and_rejects_unknown_sender(monkeypatch):
    monkeypatch.setenv('SWITCH_ADAPTER_TOKEN','adapter-service-key')
    monkeypatch.setenv('SWITCH_MEMBERS','{}')
    client=Mock();client.__enter__=Mock(return_value=client);client.__exit__=Mock(return_value=False)
    client.get.return_value.status_code=403
    constructor=Mock(return_value=client)
    monkeypatch.setattr(adapter.httpx,'Client',constructor)
    result=adapter.dispatch('room','opaque-sender','!repair')
    assert 'not linked' in result
    assert constructor.call_args.kwargs['headers']=={'Authorization':'Bearer adapter-service-key','X-Switch-Sender':'opaque-sender'}
    client.post.assert_not_called()


def test_service_identity_never_uses_claimed_member_token(monkeypatch):
    monkeypatch.setenv('SWITCH_ADAPTER_TOKEN','adapter-service-key')
    monkeypatch.setenv('SWITCH_MEMBERS',json.dumps({'opaque-sender':{'role':'engineering','token':'untrusted-role-token'}}))
    client=Mock();client.__enter__=Mock(return_value=client);client.__exit__=Mock(return_value=False)
    client.get.return_value.status_code=200
    client.get.return_value.json.return_value=[{'id':'12345678','room_id':'room','created_at':'today','version':1,'stage':'OPEN','revision':1,'definition':None,'approvals':{}}]
    constructor=Mock(return_value=client);monkeypatch.setattr(adapter.httpx,'Client',constructor)
    assert 'OPEN' in adapter.dispatch('room','opaque-sender','!status')
    assert constructor.call_args.kwargs['headers']['Authorization']=='Bearer adapter-service-key'


def test_switch_pongs_while_command_runs_and_deduplicates(tmp_path,monkeypatch):
    for name,value in {'SWITCH_BASE_URL':'http://127.0.0.1:9999','SWITCH_AGENT_ID':'agent','SWITCH_API_KEY':'not-a-real-key','SWITCH_ROOM_ID':'room','DATABASE_URL':'sqlite:///'+(tmp_path/'switch.db').as_posix()}.items():monkeypatch.setenv(name,value)
    delivered=asyncio.Event()
    release=threading.Event()
    calls=[];pongs=[];urls=[]
    def command(*args):
        calls.append(args)
        assert release.wait(timeout=3),'Ping was blocked by command work'
        return 'Recorded'
    monkeypatch.setattr(adapter,'dispatch',command)
    class Client:
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,*args,**kwargs):
            delivered.set()
            return NS(raise_for_status=lambda:None)
    monkeypatch.setattr(adapter.httpx,'AsyncClient',lambda **kwargs:Client())
    class Socket:
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def send(self,raw):
            pongs.append(json.loads(raw))
            release.set()
        def __aiter__(self):return self.frames()
        async def frames(self):
            yield json.dumps({'type':'connection_state','rooms':['room'],'cursor':10,'generation':3})
            event={'event':'message','id':11,'data':{'type':'message','room_id':'room','sequence':11,'payload':{'addressed':True,'sender':'@person:server','body':'!context migration'}}}
            yield json.dumps(event)
            yield json.dumps({'type':'ping'})
            await asyncio.wait_for(delivered.wait(),timeout=3)
            yield json.dumps(event)
            yield json.dumps({'type':'ping'})
            await asyncio.sleep(.05)
            raise RuntimeError('Test complete')
    def connect(url,**kwargs):
        urls.append(url)
        assert kwargs['additional_headers']['Authorization']=='Bearer not-a-real-key'
        return Socket()
    monkeypatch.setattr(adapter,'connect',connect)
    async def execute():
        with pytest.raises(RuntimeError,match='Test complete'):await adapter.run()
    asyncio.run(execute())
    assert len(calls)==1 and pongs[0]=={'type':'pong','cursor':10}
    assert parse_qs(urlsplit(urls[0]).query)['filter']==['addressed']
    state=Store('sqlite:///'+(tmp_path/'switch.db').as_posix()).state('switch:agent:room')
    assert state['cursor']==11 and state['generation']==3
