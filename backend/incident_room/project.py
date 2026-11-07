"""Configured real SQL project. No sample database is created or substituted."""
from __future__ import annotations
import hashlib
import json
import os
import subprocess
from decimal import Decimal,InvalidOperation
from pathlib import Path
import httpx
from pydantic import BaseModel, Field


class Assertion(BaseModel):
    name: str
    sql: str  # Returns failing rows. Zero rows means pass.


class Metric(BaseModel):
    name: str
    sql: str  # One numeric scalar.
    minimum: float | None = None
    maximum: float | None = None


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,default=str).encode()).hexdigest()


def file_hash(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


class Project:
    def transform_path(self,name):
        if name not in self.config.transforms:raise ValueError('Transform is not explicitly allowed in project configuration')
        path=(self.root/name).resolve()
        if not path.is_relative_to(self.root) or path.suffix.lower()!='.sql' or not path.is_file():
            raise ValueError('Transform must be an existing SQL file inside the configured project')
        return path

    def read_transform(self,name):
        return {'file':name,'content':self.transform_path(name).read_text(encoding='utf-8-sig')}

    def metadata(self):
        if not self.config.datahub_urns:return {'source':'project configuration','datahub_configured':False,'datasets':[]}
        endpoint=os.getenv('DATAHUB_GMS_URL','').rstrip('/')
        if not endpoint:raise ValueError('DATAHUB_GMS_URL is required for configured DataHub assets')
        token=os.getenv('DATAHUB_TOKEN','')
        headers={'Authorization':'Bearer '+token} if token else {}
        query='query ($urn:String!){dataset(urn:$urn){urn name properties{name description} editableProperties{description} schemaMetadata{fields{fieldPath nativeDataType description}} upstreamLineage{upstreams{dataset{urn name}}}}}'
        datasets=[]
        with httpx.Client(timeout=20) as client:
            for urn in self.config.datahub_urns:
                r=client.post(endpoint+'/api/graphql',headers=headers,json={'query':query,'variables':{'urn':urn}})
                r.raise_for_status()
                body=r.json()
                if body.get('errors') or not body.get('data',{}).get('dataset'):raise ValueError('Configured DataHub asset could not be read')
                datasets.append(body['data']['dataset'])
        return {'source':'DataHub','datasets':datasets}

    def metrics(self,database=None):
        results=[]
        for metric in self.config.metrics:
            out=self.query(metric.sql,database)
            if len(out['rows'])!=1 or len(out['rows'][0])!=1 or isinstance(out['rows'][0][0],bool):
                raise ValueError(f'Metric {metric.name} must return one numeric value')
            value=out['rows'][0][0]
            try:number=Decimal(str(value))
            except InvalidOperation:raise ValueError(f'Metric {metric.name} did not return a numeric scalar')
            if not number.is_finite():raise ValueError(f'Metric {metric.name} returned a non-finite value')
            passed=(metric.minimum is None or number>=Decimal(str(metric.minimum))) and (metric.maximum is None or number<=Decimal(str(metric.maximum)))
            results.append({'name':metric.name,'value':value,'minimum':metric.minimum,'maximum':metric.maximum,'passed':passed})
        return results

    def verify(self,database):
        checks=[]
        for assertion in self.config.assertions:
            try:
                result=self.query(assertion.sql,database)
                checks.append({'name':assertion.name,'passed':not result['rows'],'failing_rows':result['rows'],'truncated':result['truncated'],'sql':result.get('sql',assertion.sql),'job_id':result.get('job_id')})
            except Exception as exc:
                checks.append({'name':assertion.name,'passed':False,'error':str(exc),'sql':assertion.sql})
        metric_error=None
        try:metrics=self.metrics(database)
        except Exception as exc:metrics=[];metric_error=str(exc)
        return {'checks':checks,'metrics':metrics,'metric_error':metric_error,'passed':bool(checks) and all(c['passed'] for c in checks) and not metric_error and all(m['passed'] for m in metrics)}

    def git(self,args,cwd=None):
        r=subprocess.run(['git',*args],cwd=cwd or self.root,capture_output=True,text=True,timeout=90)
        if r.returncode:raise ValueError('Git operation failed: '+r.stderr.strip()[:400])
        return r.stdout.strip()

    def publish(self,iid,proposal,workdir):
        # Detached worktree means an interrupted operation never changes the main checkout.
        if self.git(['status','--porcelain']):raise ValueError('Commit or stash project changes before publishing a repair branch')
        branch='incident-room/'+iid
        if not iid.isalnum():raise ValueError('Invalid incident identifier')
        self.transform_path(proposal['file'])
        location=Path(workdir)/'checkout'
        self.git(['worktree','add','-b',branch,str(location),'HEAD'])
        try:
            dst=(location/proposal['file']).resolve()
            if not dst.is_relative_to(location.resolve()):raise ValueError('Invalid worktree path')
            dst.write_text(proposal['content'],encoding='utf-8',newline='')
            self.git(['add','--',proposal['file']],location)
            self.git(['commit','-m',f'fix: verified data repair ({iid})'],location)
            commit=self.git(['rev-parse','HEAD'],location)
            blob=subprocess.run(['git','cat-file','blob',commit+':'+proposal['file']],cwd=location,capture_output=True,check=True,timeout=30).stdout
            if blob!=proposal['content'].encode('utf-8'):raise ValueError('Git filters changed the tested SQL bytes. Review the retained branch; publication stopped.')
        finally:
            self.git(['worktree','remove','--force',str(location)])
        result={'branch':branch,'commit':commit,'deployed':False}
        if self.config.publish_pr:
            body_path=Path(workdir)/'pr-body.md'
            body_path.write_text('Verified in an isolated warehouse clone. Production data has not been changed.\n\n'+proposal['reason']+'\n\nProposal digest: '+proposal['digest'],encoding='utf-8')
            try:
                self.git(['push','origin',branch])
                r=subprocess.run(['gh','pr','create','--head',branch,'--title',f'Verified data repair {iid}','--body-file',str(body_path)],cwd=self.root,capture_output=True,text=True,timeout=60)
                result['pr_url']=r.stdout.strip() if r.returncode==0 else None
                if r.returncode:result['publication_error']=r.stderr[:400]
            except Exception as exc:result['publication_error']=str(exc)[:400]
        return result
