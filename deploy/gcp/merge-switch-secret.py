"""Retain the registered agent's identity and prepare a private reviewer handover."""
import json
from pathlib import Path
from dotenv import dotenv_values,set_key

root=Path(__file__).resolve().parents[2]
private=root.parents[1]/'private/gcp'
state=json.loads((private/'cloud-switch.json').read_text())
release=json.loads((private/'cloud-release.json').read_text())
app=private/'app.production.env';operator=dotenv_values(private/'switch.production.env')
for key,value in {'SWITCH_AGENT_ID':state['agent_id'],'SWITCH_API_KEY':state['agent_api_key'],'SWITCH_ROOM_ID':state['room_id']}.items():set_key(app,key,value)
access={'application':{'url':release['urls']['app'],'sign_in':'Google','reviewers':['finance@example.com','engineering@example.com']},'switch_server':release['urls']['switch'],'switch_admin':release['urls']['gateway'],'chat':release['urls']['chat'],'finance':{'gateway_email':operator['GATEWAY_ADMIN_EMAIL'],'gateway_password':operator['GATEWAY_ADMIN_PASSWORD'],'chat_username':'finance','chat_password':operator['MATTERMOST_USER_PASSWORD']},'engineering':{'gateway_email':'engineering@example.com','gateway_password':state['engineering_password'],'chat_username':'engineering','chat_password':state['engineering_chat_password']}}
(private/'reviewer-access.json').write_text(json.dumps(access,indent=2)+'\n',encoding='utf-8')
print('Agent identity saved for production. Reviewer access details saved privately; no passwords printed.')
