"""Check the actual API container's configured presentation tables and SQL mount."""
import json
import os
from pathlib import Path
from incident_room.bigquery_project import BigQueryProject

project=BigQueryProject(os.environ['PROJECT_CONFIG'])
assert all('.incident_room_presentation.' in table for table in project.config.tables)
assert 'WHERE NOT is_cancellation' in project.read_transform('models/retail_daily.sql')['content']
result=project.verify(project.source_map)
assert [check['name'] for check in result['checks'] if not check['passed']]==['Every daily amount and count reconciles directly to raw inputs']
assert next(str(metric['value']) for metric in result['metrics'] if metric['name']=='Signed invoice value (GBP)')=='10644560.424'
report={'passed':True,'name':project.config.name,'tables':project.config.tables,'sql_head':project.git(['rev-parse','HEAD']).strip(),'checks_passed':5,'checks_total':6,'expected_fault_detected':True,'false_approval_created':False}
Path('/app/runtime/presentation-active-validation.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS: running API targets the isolated presentation project; its actual daily reconciliation fails as intended.')
