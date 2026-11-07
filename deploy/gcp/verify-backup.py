"""Restore the latest app dump into a disposable database and compare history."""
import json
from pathlib import Path
import subprocess
from uuid import uuid4

dump=max(Path('/srv/incident-room/backups').glob('*-app.dump'),key=lambda path:path.name)
temporary='incident_restore_'+uuid4().hex[:12]
prefix=['docker','exec','incident-room-db-1']
def query(database):
    sql="SELECT count(*),md5(coalesce(string_agg(id || ':' || md5(body),',' ORDER BY id),'')) FROM incidents UNION ALL SELECT count(*),md5(coalesce(string_agg(id || ':' || md5(body),',' ORDER BY id),'')) FROM audit;"
    return subprocess.run(prefix+['psql','-U','incident','-d',database,'-At','-c',sql],check=True,capture_output=True,text=True).stdout
subprocess.run(prefix+['createdb','-U','incident',temporary],check=True)
try:
    with dump.open('rb') as handle:subprocess.run(['docker','exec','-i','incident-room-db-1','pg_restore','-U','incident','--exit-on-error','-d',temporary],stdin=handle,check=True)
    original=query('incident');restored=query(temporary)
    if restored!=original:raise RuntimeError('Restored incident or audit content differs from the current history')
    Path('/srv/incident-room/runtime/cloud-backup-validation.json').write_text(json.dumps({'passed':True,'backup':dump.name,'actual_restore_tested':True,'incident_and_audit_content_match':True,'production_database_modified':False},indent=2)+'\n')
    print('PASS: backup restored in a disposable database; all incident and audit content matched.')
finally:
    subprocess.run(prefix+['dropdb','-U','incident',temporary],check=True)
