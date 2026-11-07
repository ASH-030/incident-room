"""Run explicitly once after creating your Switch server and registration key."""
import getpass
import os
from pathlib import Path
import httpx
from dotenv import load_dotenv,set_key

ROOT=Path(__file__).resolve().parents[2]


def main():
    env=ROOT/'.env'
    if not env.exists():raise ValueError('Run incident_room.configure first')
    load_dotenv(env)
    if os.getenv('SWITCH_AGENT_ID') or os.getenv('SWITCH_API_KEY'):raise ValueError('An agent is already configured. Do not register it again or rotate its key accidentally.')
    base=input('Switch server/bridge base URL: ').strip().rstrip('/')
    if not base.startswith(('https://','http://127.0.0.1:','http://localhost:')):raise ValueError('Use HTTPS or a loopback HTTP server')
    name=input('Unique agent name [incident-room]: ').strip() or 'incident-room'
    registration=getpass.getpass('Switch registration API key (hidden, used once): ').strip()
    payload={'name':name,'display_name':'Incident Room','description':'Collaborative BigQuery incident investigation with finance and engineering review','connector_type':'incident-room-python','integration_profile':{'connection_model':'session_addressable','message_exchange':True,'pre_invocation_mediation':[],'post_invocation_mediation':[],'event_reporting':[]}}
    with httpx.Client(timeout=20) as client:
        client.get(base+'/health').raise_for_status()
        response=client.post(base+'/agents',headers={'Authorization':'Bearer '+registration},json=payload)
        response.raise_for_status()
        agent=response.json()
    # Save the one-time returned identity before any further operation.
    set_key(env,'SWITCH_BASE_URL',base)
    set_key(env,'SWITCH_AGENT_ID',agent['id'])
    set_key(env,'SWITCH_API_KEY',agent['api_key'])
    print('Agent registered and credentials saved locally. Invite it to your room, permit the intended reviewers in Switch agent settings, then set SWITCH_ROOM_ID and SWITCH_MEMBERS. Registration key was not saved.')


if __name__=='__main__':main()
