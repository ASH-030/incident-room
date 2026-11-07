"""Provision the project's real private Switch room and operator-owned reviewer accounts."""
import json
import os
from pathlib import Path
import secrets
from dotenv import dotenv_values
import httpx
from incident_room.auth import AuthStore
from incident_room.storage import Store

operator=dotenv_values('/run/switch.env')
state_file=Path('/app/runtime/cloud-switch.json')
state=json.loads(state_file.read_text()) if state_file.exists() else {}
def save():
    descriptor=os.open(state_file,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(descriptor,'w') as handle:json.dump(state,handle,indent=2)
def checked(response):
    if response.status_code>=400:raise RuntimeError(f'{response.request.method} {response.request.url.path}: HTTP {response.status_code}')
    return response.json()
def login(client,email,password):
    response=client.post('/gateway/auth/login',json={'email':email,'password':password})
    account=checked(response)
    client.headers['Cookie']='switch_auth='+response.cookies['switch_auth']
    return account

base=os.environ['SWITCH_BASE_URL']
state.setdefault('engineering_password',secrets.token_urlsafe(32)+'Aa1!')
state.setdefault('engineering_chat_password',secrets.token_urlsafe(32)+'Aa1!')
save()
with httpx.Client(base_url=base,timeout=45) as client:
    finance=login(client,operator['GATEWAY_ADMIN_EMAIL'],operator['GATEWAY_ADMIN_PASSWORD'])
    users=checked(client.get('/gateway/users'))
    engineering=next((user for user in users if user.get('email')=='engineering@example.com'),None)
    if not engineering:engineering=checked(client.post('/gateway/users',json={'name':'Engineering reviewer','email':'engineering@example.com','password':state['engineering_password'],'role':'user'}))
    with httpx.Client(base_url='http://10.44.0.2:8065',timeout=30) as chat:
        response=chat.post('/api/v4/users/login',json={'login_id':operator['MATTERMOST_ADMIN_USER'],'password':operator['MATTERMOST_ADMIN_PASSWORD']})
        checked(response);chat.headers['Authorization']='Bearer '+response.headers['token']
        response=chat.get('/api/v4/users/username/engineering')
        person=checked(response) if response.status_code==200 else checked(chat.post('/api/v4/users',json={'username':'engineering','email':'engineering@example.com','password':state['engineering_chat_password']}))
        team=checked(chat.get('/api/v4/teams/name/'+operator['MATTERMOST_TEAM_NAME']))
        response=chat.post('/api/v4/teams/'+team['id']+'/members',json={'team_id':team['id'],'user_id':person['id']})
        if response.status_code not in {200,201,400}:checked(response)
    if not state.get('agent_id'):
        registration=checked(client.post('/gateway/api-keys',json={'label':'Incident Room one-time production provisioning'}))
        try:
            agent=checked(client.post('/agents',headers={'Authorization':'Bearer '+registration['key']},json={'name':'incident-room','display_name':'Incident Room','description':'Collaborative BigQuery investigations with exact-patch review','connector_type':'incident-room-python','integration_profile':{'connection_model':'session_addressable','message_exchange':True,'pre_invocation_mediation':[],'post_invocation_mediation':[],'event_reporting':[]}}))
            state.update(agent_id=agent['id'],agent_api_key=agent['api_key']);save()
        finally:
            response=client.delete('/gateway/api-keys/'+registration['id'])
            if response.status_code>=400:raise RuntimeError('One-time registration key could not be revoked')
    if not state.get('room_id'):
        room=checked(client.post('/gateway/rooms',json={'name':'Incident Room','description':'Finance and engineering investigate evidence and review verified SQL repairs.','agent_ids':[state['agent_id']],'user_names':['finance','engineering'],'read_visibility':'private','write_visibility':'private'}))
        state.update(room_id=room['id'],channel_id=room.get('external_channel_id'));save()
    room_id=state['room_id']
    checked(client.put('/gateway/agents/'+state['agent_id']+'/addressing-policy',json={'policy':{'rules':[{'rooms':[room_id],'users':'*','agents':[]}]}}))
    auth=AuthStore(Store(os.environ['DATABASE_URL']))
    for account,email in [(finance,operator['GATEWAY_ADMIN_EMAIL']),(engineering,'engineering@example.com')]:
        checked(client.post('/gateway/chats/'+room_id+'/members',json={'userId':account['id']}))
        # Switch's member_actor creates this exact transport ID for a Console member.
        auth.bind_switch('@switch-member-'+account['id']+':incident-room',email)
    state.update(finance_user_id=finance['id'],engineering_user_id=engineering['id'],configured=True)
    save()
print('Production agent, private room and reviewer accounts configured. Credentials remain private.')
