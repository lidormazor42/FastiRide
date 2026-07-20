from io import BytesIO

from PIL import Image

import main
from tests.conftest import make_user, login, make_event


def _png_bytes(size=(60, 60)):
    buf = BytesIO()
    Image.new("RGB", size, color=(200, 40, 40)).save(buf, format="PNG")
    return buf.getvalue()


def test_validate_requires_login(client, db):
    event = make_event(db)
    res = client.post(
        "/api/validate",
        data={"event_id": str(event.id)},
        files={"file": ("ticket.png", _png_bytes(), "image/png")},
    )
    assert res.status_code == 401


def test_validate_rejects_oversized_upload(client, db, monkeypatch):
    monkeypatch.setattr(main, "MAX_TICKET_UPLOAD_BYTES", 1024)
    user = make_user(db)
    event = make_event(db)
    login(client, user)
    res = client.post(
        "/api/validate",
        data={"event_id": str(event.id)},
        files={"file": ("ticket.png", b"x" * 2048, "image/png")},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["valid"] is False
    assert "גדול מדי" in body["error"]


def test_validate_rejects_non_image_file(client, db):
    user = make_user(db)
    event = make_event(db)
    login(client, user)
    res = client.post(
        "/api/validate",
        data={"event_id": str(event.id)},
        files={"file": ("ticket.png", b"definitely not an image", "image/png")},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["valid"] is False
    assert "אינה" in body["error"] or "תקינה" in body["error"]


def test_validate_image_without_barcode_fails_clearly(client, db):
    """A plain photo with no QR/barcode must be rejected with the
    no-barcode message — the mandatory-QR rule from the security redesign."""
    user = make_user(db)
    event = make_event(db)
    login(client, user)
    res = client.post(
        "/api/validate",
        data={"event_id": str(event.id)},
        files={"file": ("ticket.png", _png_bytes(), "image/png")},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["valid"] is False
    assert "ברקוד" in body["error"] or "QR" in body["error"]


def test_validate_is_rate_limited_per_ip(client, db):
    """Protects a real cost (Rekognition) from being hammered — the limit
    trips before the route body even runs, so this fires regardless of auth."""
    event = make_event(db)
    responses = [
        client.post(
            "/api/validate",
            data={"event_id": str(event.id)},
            files={"file": ("ticket.png", _png_bytes(), "image/png")},
        )
        for _ in range(11)
    ]
    assert [r.status_code for r in responses[:10]] == [401] * 10
    assert responses[10].status_code == 429
