import json
from decimal import Decimal
from types import SimpleNamespace as NS
from unittest.mock import Mock
import pytest
from google.cloud import bigquery
from incident_room.bigquery_project import BigQueryProject


@pytest.fixture
def project(tmp_path):
    (tmp_path/'model.sql').write_text('SELECT amount FROM `project.dataset.source`')
    config={'name':'warehouse','billing_project':'project','location':'US','project_root':str(tmp_path),'tables':['project.dataset.source','project.dataset.output'],'transforms':['model.sql'],'outputs':{'model.sql':'project.dataset.output'},'assertions':[{'name':'positive','sql':'SELECT * FROM `project.dataset.output` WHERE amount < 0'}],'metrics':[{'name':'total','sql':'SELECT SUM(amount) FROM `project.dataset.output`','minimum':0}]}
    path=tmp_path/'project.json';path.write_text(json.dumps(config))
    return BigQueryProject(path,client=Mock())


@pytest.mark.parametrize('sql',[
    'DELETE FROM `project.dataset.source` WHERE TRUE',
    'SELECT 1; SELECT 2',
    'SELECT * FROM `project.secret.table`',
    "SELECT * FROM EXTERNAL_QUERY('connection', 'SELECT 1')",
    'SELECT `project.dataset.remote`(amount) FROM `project.dataset.source`',
    'EXPORT DATA OPTIONS(uri="gs://bucket/*",format="CSV") AS SELECT 1',
])
def test_scoped_sql_rejects_escape_paths(project,sql):
    with pytest.raises(Exception):project.rewrite(sql,project.source_map)
    project.client.query.assert_not_called()


def test_cte_join_aliases_and_literal_preserved(project):
    sql="WITH scoped AS (SELECT amount FROM `project.dataset.source`) SELECT s.amount, 'project.dataset.source' AS literal FROM scoped s JOIN `project.dataset.output` o ON s.amount=o.amount"
    rewritten=project.rewrite(sql,{'project.dataset.source':'project.incident_room_test.a','project.dataset.output':'project.incident_room_test.b'})
    assert 'incident_room_test.a' in rewritten and 'incident_room_test.b` AS o' in rewritten
    assert "'project.dataset.source'" in rewritten and 'scoped AS s' in rewritten


@pytest.mark.parametrize('dry',[
    NS(statement_type='DELETE',referenced_tables=[],total_bytes_processed=0),
    NS(statement_type='SELECT',referenced_tables=[bigquery.TableReference.from_string('project.secret.table')],total_bytes_processed=0),
    NS(statement_type='SELECT',referenced_tables=[],total_bytes_processed=2_000_000_000),
])
def test_dry_run_must_pass_before_execution(project,dry):
    project.client.query.return_value=dry
    with pytest.raises(ValueError):project.query('SELECT amount FROM `project.dataset.source`')
    assert project.client.query.call_count==1


def test_query_keeps_exact_decimal_evidence_and_bounds(project):
    dry=NS(statement_type='SELECT',referenced_tables=[],total_bytes_processed=10)
    class Rows(list):schema=[NS(name='amount')]
    job=Mock(job_id='real-job-id',total_bytes_processed=10)
    job.result.return_value=Rows([{'amount':Decimal('12345678901234567890.123456789')}])
    project.client.query.side_effect=[dry,job]
    result=project.query('SELECT amount FROM `project.dataset.source`')
    assert result['rows']==[['12345678901234567890.123456789']]
    config=project.client.query.call_args.kwargs['job_config']
    assert config.maximum_bytes_billed==1_000_000_000 and config.destination is None
    assert result['sql'] and result['job_id']=='real-job-id'


def test_timeout_cancels_query(project):
    job=Mock();job.result.side_effect=TimeoutError('deadline')
    project.client.query.side_effect=[NS(statement_type='SELECT',referenced_tables=[],total_bytes_processed=0),job]
    with pytest.raises(TimeoutError):project.query('SELECT 1')
    job.cancel.assert_called_once()


def test_validation_writes_only_generated_scratch_tables(project,monkeypatch,tmp_path):
    project.client.get_table.return_value=NS(table_type='TABLE')
    executed=[]
    monkeypatch.setattr(project,'execute',lambda sql,allowed,destination=None:executed.append((sql,allowed,destination)))
    monkeypatch.setattr(project,'verify',lambda mapping:{'passed':True,'checks':[{'name':'contract','passed':True}]})
    result=project.verify_patch('model.sql','SELECT amount / 100 FROM `project.dataset.source`',tmp_path)
    assert result['production_modified'] is False
    assert executed[0][2].startswith(result['validation_dataset']+'.')
    assert all(t.startswith(result['validation_dataset']+'.') for t in executed[0][1])
    assert 'dataset.source' not in executed[0][0]
    project.client.delete_dataset.assert_called_once_with(result['validation_dataset'],delete_contents=True,not_found_ok=True,timeout=60)
    assert all(' CLONE ' in c.args[0] for c in project.client.query.call_args_list)


def test_validation_cleanup_on_clone_failure(project,tmp_path):
    project.client.get_table.return_value=NS(table_type='TABLE')
    project.client.query.return_value.result.side_effect=TimeoutError('clone failed')
    with pytest.raises(TimeoutError):project.verify_patch('model.sql','SELECT 1',tmp_path)
    project.client.query.return_value.cancel.assert_called_once()
    project.client.delete_dataset.assert_called_once()


def test_streaming_and_external_sources_block_review(project):
    project.client.get_table.return_value=NS(table_type='EXTERNAL')
    with pytest.raises(ValueError,match='materialized'):project.fingerprint()
    project.client.get_table.return_value=NS(table_type='TABLE',streaming_buffer=True)
    with pytest.raises(ValueError,match='Streaming'):project.fingerprint()


def test_decimal_metric_is_not_rounded(project,monkeypatch):
    monkeypatch.setattr(project,'query',lambda sql,database:{'rows':[['10.123456789']]})
    result=project.metrics()
    assert result[0]['value']=='10.123456789' and result[0]['passed']
