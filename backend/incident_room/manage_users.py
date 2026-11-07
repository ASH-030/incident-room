"""Operator-only local membership administration. No public role-selection endpoint."""
import argparse
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from .auth import AuthStore,ROLES
from .storage import Store


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    member=commands.add_parser('invite');member.add_argument('email');member.add_argument('role',choices=sorted(ROLES));member.add_argument('--name',default='')
    revoke=commands.add_parser('revoke');revoke.add_argument('email')
    bind=commands.add_parser('bind-switch');bind.add_argument('sender');bind.add_argument('email')
    commands.add_parser('list')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[2];load_dotenv(root/'.env')
    data=Path(os.getenv('ROOM_DATA_DIR',str(root/'runtime')));data.mkdir(parents=True,exist_ok=True)
    auth=AuthStore(Store(os.getenv('DATABASE_URL','sqlite:///'+(data/'room-live.db').as_posix())))
    if args.command=='invite':auth.set_member(args.email,args.role,args.name);print('Membership saved; existing sessions for this member were revoked.')
    elif args.command=='revoke':
        existing=auth.member(args.email)
        if not existing:raise ValueError('Member not found')
        auth.set_member(args.email,existing['role'],existing['name'],enabled=False);print('Membership and sessions revoked.')
    elif args.command=='bind-switch':auth.bind_switch(args.sender,args.email);print('Switch participant bound to the verified-account membership.')
    else:
        with auth.engine.connect() as conn:print(json.dumps([dict(r) for r in conn.execute(auth.members.select()).mappings()],indent=2))


if __name__=='__main__':main()
