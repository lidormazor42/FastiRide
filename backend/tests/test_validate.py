import base64
import json
from io import BytesIO

from PIL import Image, ImageDraw

import main
from tests.conftest import make_user, login, make_event


def _png_bytes(size=(60, 60)):
    buf = BytesIO()
    Image.new("RGB", size, color=(200, 40, 40)).save(buf, format="PNG")
    return buf.getvalue()


def _generic_ticket_bytes(square_offset=0):
    """A white-bg / centered-block / text-bars layout — the rough shape
    every digital ticket shares (header bar, centered QR-ish block, footer
    bar), regardless of the actual event. Used to prove two DIFFERENT
    events' tickets can still hash within VISUAL_MATCH_THRESHOLD of each
    other purely from sharing this generic layout."""
    img = Image.new("RGB", (200, 200), color="white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 10, 200, 30], fill="black")
    draw.rectangle([60 + square_offset, 70, 140 + square_offset, 150], fill="black")
    draw.rectangle([0, 170, 200, 190], fill="black")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class _FakeDecoded:
    def __init__(self, text):
        self.data = text.encode()


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


def test_validate_rejects_different_event_ticket_despite_visual_hash_match(client, db, monkeypatch):
    """Real incident: a genuinely different event's real ticket (different
    vendor, different design) hashed within VISUAL_MATCH_THRESHOLD of this
    event's reference ticket — an 8x8 average-hash only sees coarse layout
    (white background, centered QR-ish block, text bars), and nearly every
    digital ticket from every vendor shares that same rough shape. Visual
    similarity alone must no longer be enough to grant access."""
    ref_bytes = _generic_ticket_bytes(square_offset=0)
    uploaded_bytes = _generic_ticket_bytes(square_offset=4)

    # Confirm this pair actually exercises the scenario: visually close
    # enough that hash-only matching would have accepted it.
    ref_image = Image.open(BytesIO(ref_bytes)).convert("RGB")
    uploaded_image = Image.open(BytesIO(uploaded_bytes)).convert("RGB")
    distance = main._hamming_distance(main._perceptual_hash(uploaded_image), main._perceptual_hash(ref_image))
    assert distance <= main.VISUAL_MATCH_THRESHOLD

    ref_data_uri = "data:image/png;base64," + base64.b64encode(ref_bytes).decode()
    event = make_event(db, name="Yom Sport")
    event.reference_tickets = json.dumps([ref_data_uri])
    db.commit()

    # Real QR/OCR content for a genuinely different event's ticket —
    # never mentions "Yom Sport" anywhere.
    monkeypatch.setattr(main, "qr_decode", lambda image: [_FakeDecoded("ZG10347647")])
    monkeypatch.setattr(main.pytesseract, "image_to_string", lambda image, **kwargs: "1YEAR CELEBRATION - AMERICANA")

    user = make_user(db)
    login(client, user)
    res = client.post(
        "/api/validate",
        data={"event_id": str(event.id)},
        files={"file": ("ticket.png", uploaded_bytes, "image/png")},
    )
    assert res.status_code == 200
    assert res.json()["valid"] is False


def test_validate_accepts_same_event_reference_ticket_with_text_match(client, db, monkeypatch):
    """Baseline regression: the original legitimate case (same event, minor
    text/round-label edit on the same real ticket template) must still pass
    now that a text check runs alongside the visual one."""
    ref_bytes = _generic_ticket_bytes(square_offset=0)
    uploaded_bytes = _generic_ticket_bytes(square_offset=4)
    ref_data_uri = "data:image/png;base64," + base64.b64encode(ref_bytes).decode()

    event = make_event(db, name="Yom Sport")
    event.reference_tickets = json.dumps([ref_data_uri])
    db.commit()

    monkeypatch.setattr(main, "qr_decode", lambda image: [_FakeDecoded("ZG10347647")])
    monkeypatch.setattr(main.pytesseract, "image_to_string", lambda image, **kwargs: "Yom Sport round 4")

    user = make_user(db)
    login(client, user)
    res = client.post(
        "/api/validate",
        data={"event_id": str(event.id)},
        files={"file": ("ticket.png", uploaded_bytes, "image/png")},
    )
    assert res.status_code == 200
    assert res.json()["valid"] is True
