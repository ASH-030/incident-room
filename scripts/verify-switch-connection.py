"""Exercise a real Switch message round trip and the unbound-sender guard."""
import json
import argparse
import re
from pathlib import Path
import time
from uuid import uuid4
import httpx
from dotenv import dotenv_values

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--expect-bound',action='store_true')
args=parser.parse_args()
values=dotenv_values(root/'.env')
operator=dotenv_values(root.parents[1]/'deploy'/'switch'/'.env')
room,agent=values['SWITCH_ROOM_ID'],values['SWITCH_AGENT_ID']
def checked(response):response.raise_for_status();return response.json()
with httpx.Client(base_url=values['SWITCH_BASE_URL']+'/gateway',timeout=20) as client:
    checked(client.post('/auth/login',json={'email':operator['GATEWAY_ADMIN_EMAIL'],'password':operator['GATEWAY_ADMIN_PASSWORD']}))
    existing=checked(client.get('/chats/'+room+'/messages'))
    head=existing['headSeq']
    sent=checked(client.post('/chats/'+room+'/messages',json={'requestId':str(uuid4()),'body':'!status','mentionAgentId':agent}))
    chat_client_id=sent['messages'][0]['sender']['clientId']
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        messages=checked(client.get('/chats/'+room+'/messages'))['messages']
        replies=[message for message in messages if message['seq']>head and message['sender'].get('agentId')==agent]
        if replies:
            reply=replies[-1]
            if args.expect_bound:
                assert reply['body'].startswith(('Open an incident with !open','Incident ')), 'Expected an authorized status response'
                sender=json.loads((root/'runtime'/'switch-connection-validation.json').read_text())['sender']
                identity=httpx.get(values.get('ROOM_API_URL','http://127.0.0.1:8400')+'/api/me',headers={'Authorization':'Bearer '+values['SWITCH_ADAPTER_TOKEN'],'X-Switch-Sender':sender})
                identity.raise_for_status()
                assert identity.json()['auth_method']=='switch' and identity.json()['id'].startswith('google:')
            else:
                assert 'not linked to an active workspace member' in reply['body'], 'Expected the unbound sender to be denied'
                # Chat's database UUID is distinct from the agent protocol's opaque sender.
                match=re.search(r'Your Switch identity \(([^)]+)\)',reply['body'])
                assert match, 'The adapter must report the actual transport sender for binding'
                sender=match.group(1)
            result={'passed':True,'server_version':'0.31.0','real_websocket_round_trip':True,'unbound_sender_denied':not args.expect_bound,'verified_google_membership_used':args.expect_bound,'sender':sender,'chat_client_id':chat_client_id,'room_id':room,'reply_sequence':reply['seq'],'domain_mutation_attempted':False}
            filename='switch-authenticated-validation.json' if args.expect_bound else 'switch-connection-validation.json'
            (root/'runtime'/filename).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
            print('PASS: real human message -> Switch websocket -> adapter -> API '+('verified Google membership' if args.expect_bound else 'membership denial')+' -> Switch room reply.')
            print('No incident or approval was created. Sender recorded privately for operator binding.')
            break
        time.sleep(.5)
    else:raise RuntimeError('No adapter reply within 30 seconds; inspect runtime/switch.stderr.log')
