"""Real connection checks; no credentials or seeded data are substituted."""
import argparse
import json
import os
from pathlib import Path
import tempfile
import httpx
from dotenv import load_dotenv
from openai import OpenAI
from .bigquery_project import BigQueryProject
from .auth import AuthStore,legacy_enabled,validate_production
from .storage import Store

ROOT=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validate',action='store_true',help='Rebuild current SQL in a temporary BigQuery dataset, run contracts, and clean up. Bills BigQuery jobs.')
    args=parser.parse_args()
    load_dotenv(ROOT/'.env')
    failures=[]
    project=None
    def check(name,operation):
        try:
            value=operation()
            print(name+': OK')
            return value
        except Exception as exc:
            failures.append(name)
            # SDK status and exception type are enough to diagnose without echoing request secrets.
            print(name+': FAILED ('+type(exc).__name__+'). Check configuration and provider permissions.')
    def actors():
        validate_production()
        if os.getenv('GOOGLE_CLIENT_ID'):
            data=Path(os.getenv('ROOM_DATA_DIR',str(ROOT/'runtime')))
            auth=AuthStore(Store(os.getenv('DATABASE_URL','sqlite:///'+(data/'room-live.db').as_posix())))
            with auth.engine.connect() as conn:
                members=[dict(row) for row in conn.execute(auth.members.select()).mappings() if row['enabled']]
            if not {'finance','engineering'}<={member['role'] for member in members}:raise ValueError('Invite both reviewer roles')
            return
        if not legacy_enabled():raise ValueError('Configure Google sign-in')
        configured=json.loads(os.environ['ROOM_TOKENS'])
        roles={a['role'] for a in configured.values()}
        if not {'finance','engineering'}<=roles:raise ValueError('Both reviewers required')
        if len({a['name'] for a in configured.values()})<2:raise ValueError('Distinct reviewers required')
    check('Reviewer authentication and membership',actors)
    check('OpenAI model access',lambda:OpenAI(timeout=20,max_retries=0).models.retrieve(os.environ['OPENAI_MODEL']))
    project=check('BigQuery configuration and ADC',lambda:BigQueryProject(os.environ['PROJECT_CONFIG']))
    if project:
        check('BigQuery source schema and metadata',lambda:(project.schema(),project.fingerprint()))
        metrics=check('BigQuery metric queries',project.metrics)
        if metrics:print(json.dumps(metrics,indent=2))
        check('Git identity',lambda:(project.git(['rev-parse','--show-toplevel']),project.git(['var','GIT_AUTHOR_IDENT'])))
        if args.validate:
            def validate():
                with tempfile.TemporaryDirectory(prefix='incident-room-preflight-') as tmp:
                    file=project.config.transforms[0]
                    result=project.verify_patch(file,project.read_transform(file)['content'],tmp)
                print(json.dumps(result,indent=2,default=str))
                if not result['passed']:raise ValueError('Current SQL fails configured business assertions')
            check('Isolated BigQuery rebuild and assertions',validate)
    if os.getenv('SWITCH_BASE_URL'):
        def switch():
            base=os.environ['SWITCH_BASE_URL'].rstrip('/')
            with httpx.Client(timeout=15) as client:
                client.get(base+'/health').raise_for_status()
                client.get(base+'/agents/'+os.environ['SWITCH_AGENT_ID']+'/ops',headers={'Authorization':'Bearer '+os.environ['SWITCH_API_KEY']}).raise_for_status()
        check('Switch bridge and agent identity',switch)
    else:print('Switch: NOT CONFIGURED; follow docs/SETUP.md')
    if failures:raise SystemExit('Checks failed: '+', '.join(failures))
    print('Configured checks passed. WebSocket room delivery and model-generated investigations still require an actual run.')


if __name__=='__main__':main()
