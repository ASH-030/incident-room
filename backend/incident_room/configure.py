"""Interactive local configuration. Never print or transmit credentials."""
import getpass
import json
from pathlib import Path
import secrets
from dotenv import set_key,dotenv_values

ROOT=Path(__file__).resolve().parents[2]


def main():
    path=ROOT/'.env'
    if not path.exists():path.write_text((ROOT/'.env.example').read_text(),encoding='utf-8')
    current=dotenv_values(path)
    if not current.get('OPENAI_API_KEY'):
        key=getpass.getpass('OpenAI API key (hidden; stored only in local .env): ').strip()
        if not key:raise ValueError('An OpenAI key is required')
        set_key(path,'OPENAI_API_KEY',key)
    model=input('OpenAI model ID with Responses API function calling: ').strip()
    if not model:raise ValueError('Choose a model available to your OpenAI project')
    set_key(path,'OPENAI_MODEL',model)
    config=Path(input('Absolute path to your completed BigQuery project JSON: ').strip().strip('"')).resolve()
    if not config.is_file():raise ValueError('Project JSON file does not exist')
    set_key(path,'PROJECT_CONFIG',config.as_posix())
    if current.get('ROOM_TOKENS') not in {None,'','{}'}:
        print('Kept existing reviewer credentials. No rotation performed.')
        return
    finance=input('Finance reviewer name: ').strip()
    engineer=input('Engineering reviewer name (different person): ').strip()
    if not finance or not engineer or finance.casefold()==engineer.casefold():raise ValueError('Supply two distinct reviewer names')
    actors={secrets.token_urlsafe(32):{'name':finance,'role':'finance'},secrets.token_urlsafe(32):{'name':engineer,'role':'engineering'}}
    set_key(path,'ROOM_TOKENS',json.dumps(actors))
    runtime=ROOT/'runtime';runtime.mkdir(exist_ok=True)
    credentials=runtime/'reviewer-credentials.json'
    credentials.write_text(json.dumps([{'token':t,**a} for t,a in actors.items()],indent=2),encoding='utf-8')
    print('Configured. Reviewer sign-in tokens are in runtime/reviewer-credentials.json. Share each token privately with its assigned reviewer.')


if __name__=='__main__':main()
