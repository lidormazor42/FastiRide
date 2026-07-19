"""The Redis pub/sub layer itself is exercised live on staging (two pods,
cross-pod delivery). These tests pin the mode-selection contract:
- without REDIS_URL (this suite): broadcast() delivers locally, exactly like
  the original single-replica implementation — nothing regresses.
- with a redis client injected: broadcast() publishes and does NOT deliver
  locally (delivery is the subscriber's job, on every pod including this one).
"""
import asyncio
import json

import main


def test_broadcast_without_redis_delivers_locally():
    rooms = main.ChatRooms()

    delivered = []

    class FakeWS:
        async def send_json(self, payload):
            delivered.append(payload)

    rooms.rooms[42] = [FakeWS()]
    assert main.redis_client is None
    asyncio.run(rooms.broadcast(42, {"type": "message", "text": "שלום"}))
    assert delivered == [{"type": "message", "text": "שלום"}]


def test_broadcast_with_redis_publishes_instead_of_delivering(monkeypatch):
    rooms = main.ChatRooms()

    published = []
    delivered = []

    class FakeRedis:
        async def publish(self, channel, data):
            published.append((channel, json.loads(data)))

    class FakeWS:
        async def send_json(self, payload):
            delivered.append(payload)

    rooms.rooms[7] = [FakeWS()]
    monkeypatch.setattr(main, "redis_client", FakeRedis())
    asyncio.run(rooms.broadcast(7, {"type": "message", "text": "hi"}))

    assert published == [("chat:7", {"type": "message", "text": "hi"})]
    # Local delivery is the subscriber's responsibility in redis mode —
    # broadcast() itself must not double-deliver.
    assert delivered == []
