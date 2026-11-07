"""Bind one opaque Switch participant to an existing local reviewer identity."""
import argparse
import json
from pathlib import Path
from dotenv import dotenv_values,set_key


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sender',help='Complete opaque participant ID reported by the agent')
    parser.add_argument('role',choices=['finance','engineering'])
    parser.add_argument('--room',help='Set the single Switch room ID on first binding')
    args=parser.parse_args()
    path=Path(__file__).resolve().parents[2]/'.env'
    if not path.is_file():raise ValueError('Run incident_room.configure first')
    values=dotenv_values(path)
    actors=json.loads(values.get('ROOM_TOKENS') or '{}')
    matching=[(token,actor) for token,actor in actors.items() if actor['role']==args.role]
    if len(matching)!=1:raise ValueError('Exactly one configured reviewer must match this role')
    token,actor=matching[0]
    members=json.loads(values.get('SWITCH_MEMBERS') or '{}')
    if args.sender in members and members[args.sender]['role']!=args.role:raise ValueError('This Switch identity is already assigned to the other role')
    members[args.sender]={**actor,'token':token}
    set_key(path,'SWITCH_MEMBERS',json.dumps(members))
    if args.room:set_key(path,'SWITCH_ROOM_ID',args.room)
    print('Bound participant to '+args.role+'. Restart the adapter to load the updated mapping.')


if __name__=='__main__':main()
