"""Move incident history and memberships into an empty database. Never exports sessions."""
import argparse
import json
import os
from pathlib import Path
from sqlalchemy import MetaData,select
from dotenv import load_dotenv
from .auth import AuthStore
from .storage import Store

TABLES=('incidents','audit','adapter_state','auth_members','auth_users','auth_switch_bindings')

def initialize(url):
    store=Store(url)
    previous=os.environ.pop('AUTH_MEMBERS',None)
    try:AuthStore(store)
    finally:
        if previous is not None:os.environ['AUTH_MEMBERS']=previous
    meta=MetaData();meta.reflect(bind=store.engine)
    return store.engine,meta

def export_database(url,path):
    engine,meta=initialize(url)
    with engine.connect() as conn:
        data={name:[dict(row) for row in conn.execute(select(meta.tables[name])).mappings()] for name in TABLES}
    path=Path(path)
    with path.open('x',encoding='utf-8') as handle:json.dump({'format':1,'tables':data},handle,indent=2)
    engine.dispose()
    return {name:len(rows) for name,rows in data.items()}

def import_database(url,path):
    payload=json.loads(Path(path).read_text(encoding='utf-8'))
    if payload.get('format')!=1 or set(payload.get('tables',{}))!=set(TABLES):raise ValueError('Unsupported database transfer file')
    engine,meta=initialize(url)
    try:
        with engine.begin() as conn:
            # Refuse to merge identities, incident versions or adapter cursors.
            if any(conn.execute(select(table).limit(1)).first() for table in meta.tables.values()):raise ValueError('Target database must be empty; existing data was not changed')
            for name in TABLES:
                rows=payload['tables'][name]
                if rows:conn.execute(meta.tables[name].insert(),rows)
    finally:engine.dispose()
    return {name:len(rows) for name,rows in payload['tables'].items()}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=['export','import']);parser.add_argument('file',type=Path)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[2];load_dotenv(root/'.env')
    data=Path(os.getenv('ROOM_DATA_DIR',str(root/'runtime')))
    url=os.getenv('DATABASE_URL','sqlite:///'+(data/'room-live.db').as_posix())
    counts=(export_database if args.operation=='export' else import_database)(url,args.file)
    print(json.dumps({'operation':args.operation,'rows':counts,'browser_sessions_transferred':False},indent=2))

if __name__=='__main__':main()
