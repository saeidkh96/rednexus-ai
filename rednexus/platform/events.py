from datetime import datetime, timezone
import json
import time
from sqlalchemy import select
from .storage import Event, BusReceipt, uid


def emit(s, workspace, kind, data, run_id=None):
    event_id = uid()
    body = {
        "specversion": "1.0",
        "id": event_id,
        "source": "/rednexus/platform",
        "type": f"ai.rednexus.{kind}.v1",
        "time": datetime.now(timezone.utc).isoformat(),
        "subject": run_id or workspace,
        "datacontenttype": "application/json",
        "workspaceid": workspace,
        "correlationid": run_id or event_id,
        "data": data,
    }
    s.add(Event(id=event_id, workspace=workspace, run_id=run_id, kind=kind, body=body))
    return event_id


class EventBus:
    """Transactional outbox -> Redis Streams. At-least-once by design."""

    def __init__(self, db, redis_url, client=None):
        import redis

        self.db = db
        self.client = client or redis.Redis.from_url(redis_url, decode_responses=True)
        self.stream = "rednexus:events:v1"
        self.group = "nexus-audit-v1"

    def publish(self, limit=100):
        with self.db.session() as s:
            ids = list(
                s.scalars(select(Event.id).where(Event.published.is_(False)).order_by(Event.created).limit(limit))
            )
        count = 0
        for event_id in ids:
            with self.db.session.begin() as s:
                row = s.get(Event, event_id)
                if row.published:
                    continue
                self.client.xadd(self.stream, {"event": json.dumps(row.body)})
                row.published = True
                count += 1
        return count

    def consume(self, consumer="worker", limit=100):
        import redis

        try:
            self.client.xgroup_create(self.stream, self.group, id="0", mkstream=True)
        except redis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise
        claimed = self.client.xautoclaim(self.stream, self.group, consumer, 30000, "0-0", count=limit)
        messages = list(claimed[1])
        fresh = self.client.xreadgroup(self.group, consumer, {self.stream: ">"}, count=limit)
        for _, entries in fresh:
            messages.extend(entries)
        count = 0
        for message_id, fields in messages:
            try:
                body = json.loads(fields["event"])
                if body.get("specversion") != "1.0" or not body.get("workspaceid") or not body.get("id"):
                    raise ValueError("invalid event")
            except (KeyError, ValueError, TypeError):
                self.client.xadd(
                    "rednexus:deadletters:v1",
                    {"message_id": message_id, "reason": "invalid_envelope", "time": str(time.time())},
                )
                self.client.xack(self.stream, self.group, message_id)
                continue
            with self.db.session.begin() as s:
                if not s.get(BusReceipt, body["id"]):
                    s.add(BusReceipt(id=body["id"], workspace=body["workspaceid"]))
                    s.flush()
            self.client.xack(self.stream, self.group, message_id)
            count += 1
        return count
