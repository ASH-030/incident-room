"""BigQuery data adapter: scoped reads, bounded query jobs and isolated validation datasets."""
from __future__ import annotations
import re
from pathlib import Path
from uuid import uuid4
from google.cloud import bigquery
from pydantic import BaseModel,Field
from sqlglot import parse,exp
from .project import Project,Assertion,Metric,digest,file_hash

TABLE=re.compile(r'^[a-zA-Z0-9_-]+\.[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+$')


class BigQueryConfig(BaseModel):
    name:str
    billing_project:str=Field(pattern=r'^[a-zA-Z0-9_-]+$')
    location:str=Field(pattern=r'^[a-zA-Z0-9-]+$')
    scratch_prefix:str=Field(default='incident_room_',pattern=r'^incident_room_[a-z0-9_]*$')
    project_root:Path
    tables:list[str]=Field(min_length=1)
    transforms:list[str]=Field(min_length=1)
    outputs:dict[str,str]
    assertions:list[Assertion]=Field(min_length=1)
    metrics:list[Metric]=Field(default_factory=list)
    datahub_urns:list[str]=Field(default_factory=list)
    publish_pr:bool=False
    maximum_bytes_billed:int=Field(default=1_000_000_000,ge=10_485_760)
    query_timeout_seconds:int=Field(default=60,ge=1,le=600)


class BigQueryProject(Project):
    def __init__(self,config_path,client=None):
        if not config_path or not Path(config_path).is_file():raise ValueError('Set PROJECT_CONFIG to the configuration for your real BigQuery project')
        self.config_path=Path(config_path).resolve()
        self.config=BigQueryConfig.model_validate_json(self.config_path.read_text(encoding='utf-8-sig'))
        self.root=self.config.project_root.resolve()
        if not self.root.is_dir():raise ValueError('Configured SQL Git project does not exist')
        if any(not TABLE.fullmatch(t) for t in self.config.tables):raise ValueError('Tables must use explicit project.dataset.table names; wildcards are not allowed')
        if set(self.config.transforms)!=set(self.config.outputs):raise ValueError('Each ordered SQL transform requires exactly one configured output table')
        if any(t not in self.config.tables for t in self.config.outputs.values()):raise ValueError('Transform outputs must be part of the allowed table set')
        for name in self.config.transforms:self.transform_path(name)
        # ADC credentials are resolved by the SDK, never uploaded to the app.
        self.client=client or bigquery.Client(project=self.config.billing_project,location=self.config.location)
        self.source_map={t:t for t in self.config.tables}

    def rewrite(self,sql,mapping):
        statements=parse(sql,read='bigquery')
        if len(statements)!=1 or not isinstance(statements[0],exp.Query):raise ValueError('A transform or query must be one GoogleSQL SELECT/UNION, not a script or DDL')
        tree=statements[0]
        if any(isinstance(node,exp.Dot) and isinstance(node.expression,exp.Func) for node in tree.walk()):raise ValueError('Qualified UDF and remote function calls are not permitted')
        if any(isinstance(node,exp.Anonymous) and ('.' in node.name or isinstance(node.this,exp.Identifier) and node.this.args.get('quoted')) for node in tree.walk()):raise ValueError('Quoted or qualified UDF calls are not permitted')
        if re.search(r'\b(EXTERNAL_QUERY|EXTERNAL_OBJECT_TRANSFORM|EXPORT|EXECUTE|CONNECTION)\b',sql,re.I):raise ValueError('External operations are not permitted')
        ctes={cte.alias_or_name for cte in tree.find_all(exp.CTE)}
        for table in list(tree.find_all(exp.Table)):
            if not table.catalog and not table.db and table.name in ctes:continue
            full='.'.join(p.name for p in table.parts)
            if full not in mapping:raise ValueError('Query references a table outside the configured allowlist: '+full)
            if table.args.get('version'):raise ValueError('Time travel modifiers are not supported; use a stable table snapshot')
            if not isinstance(table.this,exp.Identifier):raise ValueError('Table-valued functions are not permitted')
            dest=table.copy()
            target=exp.to_table(mapping[full],dialect='bigquery')
            for key in ['this','db','catalog']:dest.set(key,target.args.get(key))
            table.replace(dest)
        return tree.sql(dialect='bigquery')

    def execute(self,sql,allowed,destination=None):
        dry=self.client.query(sql,job_config=bigquery.QueryJobConfig(dry_run=True,use_query_cache=False),location=self.config.location,timeout=self.config.query_timeout_seconds)
        if dry.statement_type!='SELECT':raise ValueError('BigQuery classified the query as a non-SELECT statement')
        if any(f'{t.project}.{t.dataset_id}.{t.table_id}' not in allowed for t in (dry.referenced_tables or [])):raise ValueError('BigQuery resolved a reference outside the allowed tables')
        if (dry.total_bytes_processed or 0)>self.config.maximum_bytes_billed:raise ValueError('Query exceeds configured maximum_bytes_billed')
        config=bigquery.QueryJobConfig(maximum_bytes_billed=self.config.maximum_bytes_billed,use_query_cache=False,labels={'app':'incident-room'})
        if destination:
            if destination not in allowed:raise ValueError('Validation destination is outside the scratch allowlist')
            config.destination=destination
            config.write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE
        job=self.client.query(sql,job_config=config,location=self.config.location,timeout=self.config.query_timeout_seconds)
        try:
            result=job.result(timeout=self.config.query_timeout_seconds,max_results=201)
            rows=list(result)
            return {'sql':sql,'columns':[f.name for f in result.schema],'rows':[[str(v) if not isinstance(v,(str,int,float,bool,type(None))) else v for v in row.values()] for row in rows[:200]],'truncated':len(rows)>200,'job_id':job.job_id,'bytes_processed':job.total_bytes_processed,'location':self.config.location}
        except BaseException:
            job.cancel()
            raise

    def query(self,sql,database=None):
        mapping=database or self.source_map
        return self.execute(self.rewrite(sql,mapping),set(mapping.values()))

    def schema(self):
        tables=[]
        for name in self.config.tables:
            table=self.client.get_table(name,timeout=self.config.query_timeout_seconds)
            tables.append({'table':name,'description':table.description,'type':table.table_type,'columns':[f.to_api_repr() for f in table.schema]})
        return {'tables':tables}

    def fingerprint(self):
        tables=[]
        for name in self.config.tables:
            t=self.client.get_table(name,timeout=self.config.query_timeout_seconds)
            if t.table_type!='TABLE':raise ValueError('Configure materialized BigQuery TABLE assets, not external tables or views')
            if t.streaming_buffer:raise ValueError('Streaming-buffer tables require a stable materialized snapshot before repair review')
            tables.append({'table':name,'etag':t.etag,'modified':str(t.modified),'rows':t.num_rows,'bytes':t.num_bytes,'schema':[f.to_api_repr() for f in t.schema]})
        # BigQuery metadata fingerprint: not a cryptographic digest of every underlying row.
        return digest({'config':file_hash(self.config_path),'tables':tables,'transforms':{n:file_hash(self.transform_path(n)) for n in self.config.transforms},'metadata':self.metadata(),'git_head':self.git(['rev-parse','HEAD'])})

    def verify_patch(self,file,content,workdir):
        self.transform_path(file)
        dataset_id=f'{self.config.billing_project}.{self.config.scratch_prefix}{uuid4().hex[:16]}'
        dataset=bigquery.Dataset(dataset_id)
        dataset.location=self.config.location
        dataset.default_table_expiration_ms=3_600_000
        self.client.create_dataset(dataset,timeout=self.config.query_timeout_seconds)
        mapping={name:f'{dataset_id}.table_{i}' for i,name in enumerate(self.config.tables)}
        try:
            for source,target in mapping.items():
                table=self.client.get_table(source,timeout=self.config.query_timeout_seconds)
                if table.table_type!='TABLE':raise ValueError('Validation currently requires materialized BigQuery TABLE assets; materialize views first')
                job=self.client.query(f'CREATE TABLE `{target}` CLONE `{source}` OPTIONS(expiration_timestamp=TIMESTAMP_ADD(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR))',location=self.config.location,timeout=self.config.query_timeout_seconds)
                try:job.result(timeout=self.config.query_timeout_seconds)
                except BaseException:
                    job.cancel()
                    raise
            for name in self.config.transforms:
                sql=content if name==file else self.transform_path(name).read_text(encoding='utf-8-sig')
                self.execute(self.rewrite(sql,mapping),set(mapping.values()),destination=mapping[self.config.outputs[name]])
            result=self.verify(mapping)
            result['validation_dataset']=dataset_id
            result['production_modified']=False
            return result
        finally:
            # Only the unique dataset this invocation created is eligible for cleanup.
            if not dataset_id.startswith(self.config.billing_project+'.'+self.config.scratch_prefix):raise ValueError('Invalid cleanup target')
            self.client.delete_dataset(dataset_id,delete_contents=True,not_found_ok=True,timeout=self.config.query_timeout_seconds)
