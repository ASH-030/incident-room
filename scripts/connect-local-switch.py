"""Connect the project to its private local Switch server, preserving agent identity."""
import json
from pathlib import Path
import httpx
from dotenv import dotenv_values,set_key

root=Path(__file__).resolve().parents[1]
stack=root.parents[1]/'deploy'/'switch'
values=dotenv_values(root/'.env')
operator=dotenv_values(stack/'.env')
base='http://127.0.0.1:8000'
state_file=root/'runtime'/'switch-setup.json'
state=json.loads(state_file.read_text(encoding='utf-8')) if state_file.exists() else {}
def save():state_file.write_text(json.dumps(state,indent=2)+'\n',encoding='utf-8')
def checked(response):
    if response.status_code>=400:raise RuntimeError(f'Switch rejected {response.request.method} {response.request.url.path}: HTTP {response.status_code}')
    return response.json()

with httpx.Client(base_url=base,timeout=45) as client:
    account=checked(client.post('/gateway/auth/login',json={'email':operator['GATEWAY_ADMIN_EMAIL'],'password':operator['GATEWAY_ADMIN_PASSWORD']}))
    agent_id=values.get('SWITCH_AGENT_ID') or state.get('agent_id')
    if not agent_id:
        registration=checked(client.post('/gateway/api-keys',json={'label':'Incident Room one-time provisioning'}))
        try:
            agent=checked(client.post('/agents',headers={'Authorization':'Bearer '+registration['key']},json={'name':'incident-room','display_name':'Incident Room','description':'Evidence-backed BigQuery investigations with finance and engineering approval','connector_type':'incident-room-python','integration_profile':{'connection_model':'session_addressable','message_exchange':True,'pre_invocation_mediation':[],'post_invocation_mediation':[],'event_reporting':[]}}))
            agent_id=agent['id']
            # Save the one-time key before any following network operation.
            for key,value in {'SWITCH_BASE_URL':base,'SWITCH_AGENT_ID':agent_id,'SWITCH_API_KEY':agent['api_key']}.items():set_key(root/'.env',key,value)
            state['agent_id']=agent_id;save()
        finally:
            response=client.delete('/gateway/api-keys/'+registration['id'])
            if response.status_code>=400:raise RuntimeError('Revoke the one-time provisioning key in the Switch Gateway before continuing')
    room_id=values.get('SWITCH_ROOM_ID') or state.get('room_id')
    if not room_id:
        rooms=checked(client.get('/gateway/rooms'))
        matches=[r for r in rooms if r.get('name')=='Incident Room']
        if len(matches)>1:raise RuntimeError('Multiple Incident Room rooms exist; select a room explicitly in .env')
        room=matches[0] if matches else checked(client.post('/gateway/rooms',json={'name':'Incident Room','description':'Investigate retail data contracts and review proven SQL fixes together.','agent_ids':[agent_id],'internal_only':False,'read_visibility':'private','write_visibility':'private'}))
        room_id=room['id'];state['room_id']=room_id;save()
        set_key(root/'.env','SWITCH_ROOM_ID',room_id)
    # Admit human room participants only. Application membership owns business roles.
    checked(client.put('/gateway/agents/'+agent_id+'/addressing-policy',json={'policy':{'rules':[{'rooms':[room_id],'users':'*','agents':[]}]}}))
    checked(client.post('/gateway/chats/'+room_id+'/members',json={'userId':account['id']}))
    checked(client.post('/gateway/rooms/'+room_id+'/users',json={'user_names':[operator.get('MATTERMOST_USER','user')]}))
    room=checked(client.get('/gateway/rooms/'+room_id))
    state.update(agent_id=agent_id,room_id=room_id,server_version='0.31.0',gateway='http://127.0.0.1:3001',messaging='http://127.0.0.1:8065',channel_id=room.get('external_channel_id'),connected_users=room.get('connected_user_names',[]))
    save()
print('Incident Room agent registered and added to a private real Switch room.')
print('One-time registration key revoked. Agent credentials saved locally.')
print('Gateway: http://127.0.0.1:3001 | Messaging: http://127.0.0.1:8065')
print('Next: bind each actual sender to its invited Google account after its first dashboard sign-in.')
