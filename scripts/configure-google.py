"""Save the public Google client ID. The client secret is neither needed nor accepted."""
import argparse
import re
from pathlib import Path
from dotenv import set_key

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--client-id')
args=parser.parse_args()
client_id=(args.client_id or input('Public Google Web application Client ID: ')).strip()
if not re.fullmatch(r'[0-9]+-[A-Za-z0-9_-]+\.apps\.googleusercontent\.com',client_id):raise SystemExit('Use the public Client ID ending in .apps.googleusercontent.com, not its secret')
root=Path(__file__).resolve().parents[1]
if not (root/'.env').is_file():raise SystemExit('Configure Incident Room first')
set_key(root/'.env','GOOGLE_CLIENT_ID',client_id)
print('Public Google client ID saved. Restart Incident Room to enable the sign-in button.')
