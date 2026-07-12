import pytest
from starlette.websockets import WebSocketDisconnect

import main
from tests.conftest import make_user, login, make_event, make_ride


def _ws_headers(user):
    return {"cookie": f"session={main._make_token(user.id)}"}


def test_ws_chat_ping_send_broadcast_and_persist(client, db):
    driver = make_user(db, email="driver@example.com")
    event = make_event(db)
    ride = make_ride(db, event.id, driver_email=driver.email)

    with client.websocket_connect(
        f"/api/ws/rides/{ride.id}/chat", headers=_ws_headers(driver)
    ) as ws:
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}

        ws.send_json({"text": "יוצאים ב-14:00"})
        msg = ws.receive_json()
        assert msg["type"] == "message"
        assert msg["text"] == "יוצאים ב-14:00"
        assert msg["sender_email"] == driver.email

    # The message survives the socket: it was committed, not just broadcast
    login(client, driver)
    history = client.get(f"/api/rides/{ride.id}/chat").json()
    assert [m["text"] for m in history] == ["יוצאים ב-14:00"]


def test_ws_chat_rejects_stranger(client, db):
    driver = make_user(db, email="driver@example.com")
    stranger = make_user(db, email="stranger@example.com")
    event = make_event(db)
    ride = make_ride(db, event.id, driver_email=driver.email)

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            f"/api/ws/rides/{ride.id}/chat", headers=_ws_headers(stranger)
        ):
            pass
