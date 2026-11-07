import json
from types import SimpleNamespace as NS
import pytest
from incident_room.live_service import LiveService
from incident_room import live_service as module
from incident_room.errors import Rejected
from incident_room.storage import Store,Conflict
from incident_room.project import Assertion

ENGINEER={'name':'Engineering reviewer','role':'engineering'}
FINANCE={'name':'Finance reviewer','role':'finance'}


class WarehouseDouble:
    """Test double only. Production always constructs the BigQuery adapter."""
    config=NS(name='test project',transforms=['model.sql'],assertions=[Assertion(name='contract',sql='SELECT 1 WHERE FALSE')])
    stamp='initial'
    passing=True
    baseline_passed=True
    source_map={}
    def fingerprint(self):return self.stamp
    def schema(self):return {'tables':['project.dataset.orders']}
    def metadata(self):return {'contract':'confirmed by owner'}
    def metrics(self):return [{'name':'amount','value':'10.10','passed':True}]
    def verify(self,mapping):return {'passed':self.baseline_passed,'checks':[{'name':'contract','passed':self.baseline_passed}],'metrics':self.metrics()}
    def query(self,sql):return {'sql':sql,'columns':['amount'],'rows':[['10.10']]}
    def read_transform(self,file):
        if file!='model.sql':raise ValueError('not allowed')
        return {'file':file,'content':'SELECT amount FROM `project.dataset.orders`'}
    def verify_patch(self,file,content,workdir):
        return {'passed':self.passing,'checks':[{'name':'contract','passed':self.passing}],'production_modified':False}
    def publish(self,iid,proposal,workdir):return {'branch':'incident-room/'+iid,'commit':'exact-test-sha','deployed':False}


@pytest.fixture
def svc(tmp_path,monkeypatch):
    service=LiveService(Store('sqlite:///'+(tmp_path/'state.db').as_posix()),tmp_path/'jobs')
    project=WarehouseDouble()
    monkeypatch.setattr(service,'project',lambda:project)
    monkeypatch.setenv('OPENAI_API_KEY','test-key-not-a-secret')
    monkeypatch.setenv('OPENAI_MODEL','configured-test-model')
    yield service
    service.pool.shutdown(wait=True)


def move(svc,doc,action,actor=ENGINEER,**payload):return svc.mutate(doc['id'],actor,doc['version'],action,payload)
def call(name,args):return NS(type='function_call',name=name,arguments=json.dumps(args),call_id=name)


def proposed(svc,monkeypatch,terminal='propose_patch'):
    doc=svc.create(ENGINEER,'Investigate the unexpected revenue change')
    doc=move(svc,doc,'definition',FINANCE,definition='Revenue is recognized on settlement, net of refunds.')
    calls=[]
    def respond(**kwargs):
        calls.append(kwargs)
        if len(calls)==1:return NS(output=[call('query',{'sql':'SELECT amount FROM `project.dataset.orders`'}),call('read_transform',{'file':'model.sql'})])
        current=svc.store.get(doc['id'])
        args={'reason':'The executed SQL and source explain the discrepancy.','evidence_ids':[e['id'] for e in current['evidence'] if e['kind'] in {'SQL','SOURCE'}]}
        if terminal=='propose_patch':args.update(file='model.sql',content='SELECT amount / 100 AS amount FROM `project.dataset.orders`')
        if terminal=='request_input':args={'question':'Which settlement date defines revenue?'}
        return NS(output=[call(terminal,args)])
    monkeypatch.setattr(module,'OpenAI',lambda **kw:NS(responses=NS(create=respond)))
    doc=move(svc,doc,'investigate')
    svc.jobs[doc['id']].result(timeout=10)
    return svc.store.get(doc['id']),calls


def approved(svc,doc):
    doc=move(svc,doc,'approve',FINANCE,digest=doc['proposal']['digest'])
    return move(svc,doc,'approve',ENGINEER,digest=doc['proposal']['digest'])


def test_real_tool_orchestration_and_exact_branch(svc,monkeypatch):
    doc,calls=proposed(svc,monkeypatch)
    assert doc['stage']=='PROPOSAL_READY'
    assert calls[0]['store'] is False and calls[0]['model']=='configured-test-model'
    assert all(request['tool_choice']=='required' for request in calls)
    assert any(item.get('type')=='function_call_output' for item in calls[1]['input'] if isinstance(item,dict))
    assert doc['proposal']['verification']['production_modified'] is False
    doc=move(svc,approved(svc,doc),'repair')
    svc.jobs[doc['id']].result(timeout=10)
    result=svc.store.get(doc['id'])
    assert result['stage']=='VERIFIED_BRANCH' and result['artifact']['deployed'] is False
    assert len(svc.store.history(doc['id']))==result['version']


def test_no_api_key_has_no_fallback(svc,monkeypatch):
    doc=svc.create(ENGINEER,'Investigate real revenue')
    with pytest.raises(Rejected,match='Finance'):move(svc,doc,'investigate')
    doc=move(svc,doc,'definition',FINANCE,definition='Net settlement')
    monkeypatch.delenv('OPENAI_API_KEY')
    with pytest.raises(Rejected,match='no simulated'):move(svc,doc,'investigate')


def test_roles_and_exact_digest(svc,monkeypatch):
    doc,_=proposed(svc,monkeypatch)
    with pytest.raises(Rejected):move(svc,doc,'definition',definition='Changed definition')
    with pytest.raises(Rejected):move(svc,doc,'approve',digest='wrong')
    doc=move(svc,doc,'approve',digest=doc['proposal']['digest'])
    with pytest.raises(Rejected):move(svc,doc,'repair')
    with pytest.raises(Rejected,match='different people'):move(svc,doc,'approve',{'name':ENGINEER['name'],'role':'finance'},digest=doc['proposal']['digest'])


def test_new_context_invalidates_every_approval(svc,monkeypatch):
    doc,_=proposed(svc,monkeypatch)
    doc=approved(svc,doc)
    old_version=doc['version']
    doc=move(svc,doc,'message',FINANCE,text='Refunds count on the refund settlement date.')
    assert doc['proposal'] is None and not doc['approvals'] and not doc['evidence'] and not doc['metrics']
    with pytest.raises(Rejected):move(svc,doc,'repair')
    with pytest.raises(Conflict):svc.mutate(doc['id'],ENGINEER,old_version,'approve',{})


def test_changed_source_blocks_approval_and_publication(svc,monkeypatch):
    doc,_=proposed(svc,monkeypatch)
    svc.project().stamp='changed'
    with pytest.raises(Rejected,match='changed'):move(svc,doc,'approve',FINANCE,digest=doc['proposal']['digest'])
    svc.project().stamp='initial'
    doc=approved(svc,doc)
    svc.project().stamp='changed-again'
    with pytest.raises(Rejected,match='stale'):move(svc,doc,'repair')


def test_failed_checks_never_reach_review(svc,monkeypatch):
    svc.project().passing=False
    doc,_=proposed(svc,monkeypatch)
    assert doc['stage']=='FAILED' and doc['proposal'] is None and not doc['approvals']
    assert any(e['kind']=='TEST' and not e['value']['passed'] for e in doc['evidence'])


@pytest.mark.parametrize('terminal,stage',[('request_input','NEEDS_INPUT'),('no_repair','NO_REPAIR_PROPOSED')])
def test_question_or_no_repair_does_not_create_patch(svc,monkeypatch,terminal,stage):
    doc,_=proposed(svc,monkeypatch,terminal)
    assert doc['stage']==stage and doc['proposal'] is None


def test_restart_marks_jobs_interrupted_without_replay(svc):
    doc=svc.create(ENGINEER,'A real incident report')
    doc['stage']='PUBLISHING'
    svc.store.save(doc,doc['version'],{'type':'test','actor':'test','detail':'interrupted job'})
    restarted=LiveService(svc.store,svc.root)
    try:assert svc.store.get(doc['id'])['stage']=='INTERRUPTED'
    finally:restarted.pool.shutdown()


def test_stale_source_failure_is_visible(svc,monkeypatch):
    project=svc.project()
    original=project.query
    def change(sql):
        project.stamp='changed-during-investigation'
        return original(sql)
    monkeypatch.setattr(project,'query',change)
    doc,_=proposed(svc,monkeypatch)
    assert doc['stage']=='STALE_SOURCE' and doc['proposal'] is None


def test_only_executed_evidence_can_be_cited(svc):
    doc=svc.create(ENGINEER,'A real incident report')
    with pytest.raises(Rejected):svc.citations(doc,['invented-evidence'])


def test_unstructured_text_is_not_accepted_as_a_conclusion(svc,monkeypatch):
    doc=svc.create(ENGINEER,'Explain the difference in invoice values')
    doc=move(svc,doc,'definition',FINANCE,definition='All original signed invoice lines in GBP')
    requests=[]
    def respond(**kwargs):
        requests.append(kwargs)
        return NS(status='completed',output=[NS(type='message',content='The data looks correct.')])
    monkeypatch.setattr(module,'OpenAI',lambda **kw:NS(responses=NS(create=respond)))
    doc=move(svc,doc,'investigate')
    svc.jobs[doc['id']].result(timeout=10)
    result=svc.store.get(doc['id'])
    assert requests[0]['tool_choice']=='required'
    assert result['stage']=='FAILED' and result['summary'] is None and result['proposal'] is None
    assert 'required tool protocol' in result['error']


def test_incomplete_tool_call_is_never_executed(svc,monkeypatch):
    doc=svc.create(ENGINEER,'Explain the difference in invoice values')
    doc=move(svc,doc,'definition',FINANCE,definition='All original signed invoice lines in GBP')
    executed=[]
    monkeypatch.setattr(svc.project(),'query',lambda sql:executed.append(sql))
    response=NS(status='incomplete',incomplete_details=NS(reason='max_output_tokens'),output=[call('query',{'sql':'SELECT amount FROM `project.dataset.orders`'})])
    monkeypatch.setattr(module,'OpenAI',lambda **kw:NS(responses=NS(create=lambda **kwargs:response)))
    doc=move(svc,doc,'investigate')
    svc.jobs[doc['id']].result(timeout=10)
    result=svc.store.get(doc['id'])
    assert not executed and result['stage']=='FAILED'
    assert 'max_output_tokens' in result['error'] and result['proposal'] is None


def test_google_subject_prevents_self_approval_after_name_or_role_change(svc,monkeypatch):
    doc,_=proposed(svc,monkeypatch)
    doc=move(svc,doc,'approve',{'id':'google:same-person','name':'First name','role':'finance'},digest=doc['proposal']['digest'])
    with pytest.raises(Rejected,match='different people'):
        move(svc,doc,'approve',{'id':'google:same-person','name':'Changed display name','role':'engineering'},digest=doc['proposal']['digest'])


def test_distinct_google_reviewers_can_share_a_display_name(svc,monkeypatch):
    doc,_=proposed(svc,monkeypatch)
    for role,uid in [('finance','google:person-a'),('engineering','google:person-b')]:
        doc=move(svc,doc,'approve',{'id':uid,'name':'Shared display name','role':role},digest=doc['proposal']['digest'])
    assert doc['stage']=='APPROVED'


def test_failed_source_contract_cannot_close_as_no_repair(svc,monkeypatch):
    svc.project().baseline_passed=False
    doc,_=proposed(svc,monkeypatch,'no_repair')
    assert doc['stage']=='FAILED' and doc['summary'] is None and doc['proposal'] is None
    assert any(e['kind']=='TEST' and not e['value']['passed'] for e in doc['evidence'])
