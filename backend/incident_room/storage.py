"""Transactional incident documents, optimistic locking and immutable audit entries."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from sqlalchemy import create_engine, MetaData, Table, Column, String, Integer, Text, select, update, insert
import json


def now():
    return datetime.now(timezone.utc).isoformat()


class Conflict(Exception):
    pass


class Store:
    def __init__(self, url):
        self.engine = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
        meta = MetaData()
        self.docs = Table("incidents", meta, Column("id", String, primary_key=True), Column("version", Integer, nullable=False), Column("body", Text, nullable=False))
        self.audit = Table("audit", meta, Column("id", String, primary_key=True), Column("incident", String, nullable=False), Column("body", Text, nullable=False))
        self.kv = Table("adapter_state", meta, Column("id", String, primary_key=True), Column("body", Text, nullable=False))
        meta.create_all(self.engine)

    def get(self, iid):
        with self.engine.connect() as c:
            row = c.execute(select(self.docs.c.body).where(self.docs.c.id == iid)).first()
            if not row:
                raise KeyError(iid)
            return json.loads(row[0])

    def all(self):
        with self.engine.connect() as c:
            return [json.loads(r[0]) for r in c.execute(select(self.docs.c.body))]

    def save(self, doc, expected, event):
        doc = deepcopy(doc)
        doc["version"] = expected + 1
        doc["updated_at"] = now()
        event = {**event, "at": now(), "version": doc["version"]}
        with self.engine.begin() as c:
            if expected == 0:
                c.execute(insert(self.docs).values(id=doc["id"], version=1, body=json.dumps(doc)))
            else:
                result = c.execute(update(self.docs).where(self.docs.c.id == doc["id"], self.docs.c.version == expected).values(version=doc["version"], body=json.dumps(doc)))
                if result.rowcount != 1:
                    raise Conflict("Incident changed; reload before trying again.")
            c.execute(insert(self.audit).values(id=f'{doc["id"]}:{doc["version"]}', incident=doc["id"], body=json.dumps(event)))
        return doc

    def history(self, iid):
        with self.engine.connect() as c:
            return sorted([json.loads(r[0]) for r in c.execute(select(self.audit.c.body).where(self.audit.c.incident == iid))], key=lambda x: x["version"])

    def state(self, key, value=None):
        with self.engine.begin() as c:
            row = c.execute(select(self.kv.c.body).where(self.kv.c.id == key)).first()
            if value is None:
                return json.loads(row[0]) if row else None
            if row:
                c.execute(update(self.kv).where(self.kv.c.id == key).values(body=json.dumps(value)))
            else:
                c.execute(insert(self.kv).values(id=key, body=json.dumps(value)))
            return value
