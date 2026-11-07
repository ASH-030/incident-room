"""Standalone Switch protocol adapter. No external message is sent until explicitly run.

Implements documented WebSocket events, immediate pongs and HTTP message posting.
An opaque sender allowlist establishes actor roles. No automatic role inference.
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
from urllib.parse import urlencode
from uuid import uuid4
from pathlib import Path
import httpx
from dotenv import load_dotenv
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed
from .storage import Store

ROOT=Path(__file__).resolve().parents[2]
load_dotenv(ROOT/'.env')

LOG = logging.getLogger("incident_room.switch")


def dispatch(room_id, sender, body):
    members = json.loads(os.getenv("SWITCH_MEMBERS", "{}"))
    actor = members.get(sender)
    service_key = os.getenv('SWITCH_ADAPTER_TOKEN','')
    if not service_key and (not actor or actor.get("role") not in {"finance", "engineering"}):
        return f"Your Switch identity ({sender}) is not assigned a project role. Ask the operator to bind it with incident_room.bind_switch."
    # Require explicit commands before changing shared incident context or approvals.
    start = body.find("!")
    if start < 0:
        return "Commands: !open <report>, !status, !evidence, !context <text>, !definition <metric meaning>, !approve <full digest>, !repair."
    parts=body[start:].split(maxsplit=1)
    command=parts[0]
    argument=parts[1] if len(parts)>1 else ''
    # The API owns all domain mutations so the dashboard and adapter share one lock.
    if not service_key and not actor.get("token"):
        return "No authenticated API identity is configured for this Switch participant."
    headers = {"Authorization": "Bearer " + service_key, 'X-Switch-Sender':sender} if service_key else {"Authorization": "Bearer " + actor["token"]}
    with httpx.Client(base_url=os.getenv("ROOM_API_URL", "http://127.0.0.1:8400"), headers=headers, timeout=30) as api:
        identity=api.get('/api/me')
        if identity.status_code in {401,403}:
            return f"Your Switch identity ({sender}) is not linked to an active workspace member. Ask the operator to run manage_users bind-switch, then sign in to the dashboard once."
        identity.raise_for_status()
        if command == "!open":
            if len(argument.strip())<5:return "Provide a concrete report: !open <what changed and where>."
            response = api.post("/api/incidents", json={"report": argument.strip(), "room_id": room_id})
            if response.status_code>=400:return 'Request rejected: '+str(response.json().get('detail',response.status_code))
            doc = response.json()
        else:
            response = api.get("/api/incidents")
            response.raise_for_status()
            docs = sorted([d for d in response.json() if d.get("room_id") == room_id], key=lambda d: d["created_at"], reverse=True)
            if not docs:
                return "Open an incident with !open <report> first."
            doc = docs[0]
            if command != "!status":
                actions = {"!evidence": ("investigate", {}), "!context": ("message", {"text": argument}), "!definition": ("definition", {"definition": argument.strip()}), "!approve": ("approve", {"digest": argument.strip()}), "!repair": ("repair", {})}
                if command not in actions:
                    return "Unknown command. Use !status or !evidence."
                action, payload = actions[command]
                response = api.post(f"/api/incidents/{doc['id']}/{action}", json={"expected_version":doc["version"], "payload":payload})
                if response.status_code >= 400:
                    return "Request rejected: " + str(response.json().get("detail", response.status_code))
                doc = response.json()
    proposal = doc.get("proposal") or {}
    artifact=doc.get('artifact') or {}
    return f"Incident {doc['id'][:8]} | {doc['stage']} | revision {doc['revision']}\nDefinition: {doc['definition'] or 'finance confirmation needed'}\nApprovals: {', '.join(doc['approvals']) or 'none'}\n{doc.get('error') or doc.get('question') or doc.get('summary') or ''}" + (f"\nDigest: {proposal['digest']}\n{proposal['diff'][:10000]}" if proposal else "") + (f"\nBranch: {artifact['branch']}\nCommit: {artifact['commit']}\nProduction deployment pending." if artifact else '') + ('\nInvestigation is running; use !status for the result.' if doc['stage'] in {'INVESTIGATING','VERIFYING','PUBLISHING'} else '')


async def run():
    data=Path(os.getenv('ROOM_DATA_DIR',str(ROOT/'runtime')))
    data.mkdir(parents=True,exist_ok=True)
    store=Store(os.getenv('DATABASE_URL','sqlite:///'+(data/'room-live.db').as_posix()))
    required = ["SWITCH_BASE_URL", "SWITCH_AGENT_ID", "SWITCH_API_KEY", "SWITCH_ROOM_ID"]
    if any(not os.getenv(k) for k in required):
        raise RuntimeError("Configure Switch connection values in .env before running the adapter")
    base = os.environ["SWITCH_BASE_URL"].rstrip("/")
    agent = os.environ["SWITCH_AGENT_ID"]
    room = os.environ["SWITCH_ROOM_ID"]
    headers = {"Authorization": "Bearer " + os.environ["SWITCH_API_KEY"]}
    state_key = f"switch:{agent}:{room}"
    state = store.state(state_key) or {"connection_id": str(uuid4()), "cursor": "head"}
    store.state(state_key, state)
    queue = asyncio.Queue()

    async def worker():
        async with httpx.AsyncClient(timeout=20) as client:
            while True:
                frame = await queue.get()
                try:
                    data = frame["data"]
                    payload = data.get("payload", {})
                    if frame.get('event',frame.get('type'))!='message' or data.get('room_id')!=room or not payload.get('addressed'):
                        state['cursor']=max(state['cursor'],frame['id'])
                        store.state(state_key,state)
                        continue
                    # Reserve before mutation; a crash leaves an explicit reconciliation state.
                    key = state_key + ":event:" + str(frame["id"])
                    result = store.state(key)
                    if result is None:
                        store.state(key, {"processing": True})
                        try:
                            reply = await asyncio.to_thread(dispatch, room, payload.get("sender", ""), payload.get("body", ""))
                        except Exception as exc:
                            reply = "Request rejected: " + str(exc)
                        result = {"reply": reply, "sent": False}
                        store.state(key, result)
                    if result.get("processing"):
                        raise RuntimeError("Unfinished event found; reconcile its audit history before replay")
                    if not result["sent"]:
                        response = await client.post(f"{base}/agents/{agent}/message", headers=headers, json={"room_id": room, "content": result["reply"]})
                        response.raise_for_status()
                        store.state(key, {**result, "sent": True})
                    state["cursor"] = max(state['cursor'],frame["id"])
                    store.state(state_key, state)
                except Exception:
                    LOG.exception("Switch delivery failed; stopping for reconciliation before replay")
                    raise
                finally:
                    queue.task_done()

    task = asyncio.create_task(worker())
    try:
        while True:
            drained=asyncio.create_task(queue.join())
            await asyncio.wait([drained,task],return_when=asyncio.FIRST_COMPLETED)
            if task.done():
                drained.cancel()
                task.result()
            await drained
            if task.done():task.result()
            query = {"connection_id": state["connection_id"], "rooms": room, "filter": "addressed", "start_from": state["cursor"]}
            if state.get("generation") is not None:
                query["expected_generation"] = state["generation"]
            url = base.replace("https://", "wss://", 1).replace("http://", "ws://", 1) + f"/agents/{agent}/connection/ws?" + urlencode(query)
            try:
                async with connect(url, additional_headers=headers) as ws:
                    async for raw in ws:
                        if task.done():
                            task.result()
                        frame = json.loads(raw)
                        kind = frame.get("type") or frame.get("event")
                        if kind == "ping":
                            await ws.send(json.dumps({"type": "pong", "cursor": state["cursor"] if isinstance(state["cursor"], int) else 0}))
                        elif kind == "connection_state":
                            state["generation"] = frame.get("generation", frame.get("data", {}).get("generation"))
                            answer=frame.get('data',frame)
                            if room not in answer.get('rooms',[]):raise RuntimeError('Switch did not grant the configured room')
                            state['cursor']=answer['cursor']
                            store.state(state_key, state)
                        elif kind=='evicted' and frame.get('code') in {'heartbeat_lapsed','no_stream','unfenced','connection_error'}:
                            break
                        elif kind=='subscription_changed' and room not in frame.get('rooms',[]):
                            raise RuntimeError('Configured room is no longer covered; stop and reconcile')
                        elif kind in {"gap", "refused", "room_released", "evicted"}:
                            raise RuntimeError(f"Switch control frame {kind}; stop and reconcile room history before restarting")
                        elif 'id' in frame and 'data' in frame:
                            await queue.put(frame)
            except OSError:
                await asyncio.sleep(2)
            except ConnectionClosed as exc:
                if exc.rcvd and exc.rcvd.code in {1011,1012}:await asyncio.sleep(2)
                else:raise
    finally:
        task.cancel()
        await asyncio.gather(task,return_exceptions=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
