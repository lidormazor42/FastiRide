import base64
import json
import os
import re
import uuid
from datetime import datetime
from io import BytesIO
from urllib.parse import urlencode
from fastapi import (
    FastAPI, Depends, HTTPException, UploadFile, File, Form, Cookie, Response,
    WebSocket, WebSocketDisconnect,
)
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text
from jose import jwt, JWTError
import httpx
from prometheus_fastapi_instrumentator import Instrumentator
from PIL import Image
from pyzbar.pyzbar import decode as qr_decode
import pytesseract
from database import engine, get_db, Base
import models
import schemas
from email_service import send_join_notification, send_cancel_notification

SESSION_SECRET = os.getenv("SESSION_SECRET", "fastiride-dev-secret-change-in-prod")

AWS_REGION        = os.getenv("AWS_REGION", "us-east-1")
S3_UPLOADS_BUCKET = os.getenv("S3_UPLOADS_BUCKET", "")
USE_REKOGNITION   = os.getenv("USE_REKOGNITION", "").lower() in ("1", "true", "yes")

Base.metadata.create_all(bind=engine)

# Add new columns to existing tables without Alembic — Postgres-only syntax
# (ALTER COLUMN ... IF NOT EXISTS, DO $$ blocks); skipped under the sqlite
# in-memory engine used by the test suite.
if engine.dialect.name == "postgresql":
    with engine.connect() as _conn:
        _conn.execute(text("ALTER TABLE rides ADD COLUMN IF NOT EXISTS driver_age INTEGER"))
        _conn.execute(text("ALTER TABLE rides ADD COLUMN IF NOT EXISTS driver_photo TEXT"))
        _conn.execute(text("ALTER TABLE rides ADD COLUMN IF NOT EXISTS driver_email TEXT"))
        _conn.execute(text("ALTER TABLE rides ADD COLUMN IF NOT EXISTS vehicle_type TEXT"))
        _conn.execute(text("ALTER TABLE events ADD COLUMN IF NOT EXISTS logo_url TEXT"))
        # ticket_prefix never had a real source of truth (producers don't control
        # barcode formats issued by external ticketing platforms) — dropped.
        _conn.execute(text("ALTER TABLE events DROP COLUMN IF EXISTS ticket_prefix"))
        _conn.execute(text("ALTER TABLE ride_requests ADD COLUMN IF NOT EXISTS passenger_email TEXT"))
        _conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS age INTEGER"))
        _conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS city TEXT"))
        _conn.execute(text("ALTER TABLE events ADD COLUMN IF NOT EXISTS owner_email TEXT"))
        _conn.execute(text("ALTER TABLE events ADD COLUMN IF NOT EXISTS owner_phone TEXT"))
        _conn.execute(text("ALTER TABLE rides ADD COLUMN IF NOT EXISTS return_city TEXT"))
        _conn.execute(text("ALTER TABLE rides ADD COLUMN IF NOT EXISTS return_time TEXT"))
        _conn.execute(text("ALTER TABLE rides ADD COLUMN IF NOT EXISTS fuel_cost DOUBLE PRECISION"))
        # Precise-location picker was tried three times (address autocomplete, then a
        # pin-drop map, then a Voyager/Israel-bounds restyle) and rejected each time —
        # dropped for good, back to plain free-text geocoding for the map view.
        _conn.execute(text("ALTER TABLE rides DROP COLUMN IF EXISTS pickup_lat"))
        _conn.execute(text("ALTER TABLE rides DROP COLUMN IF EXISTS pickup_lng"))
        _conn.execute(text("ALTER TABLE events ADD COLUMN IF NOT EXISTS reference_tickets TEXT"))
        _conn.execute(text("""
            DO $$ BEGIN
                ALTER TABLE events ADD CONSTRAINT events_name_date_key UNIQUE (name, date);
            EXCEPTION WHEN duplicate_object OR duplicate_table THEN NULL;
            END $$;
        """))
        _conn.commit()

app = FastAPI()
Instrumentator().instrument(app).expose(app)

GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI  = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost/api/auth/google/callback")


# ── Session helpers ───────────────────────────────────────────────
def _make_token(user_id: int) -> str:
    return jwt.encode({"sub": str(user_id)}, SESSION_SECRET, algorithm="HS256")


def _get_user_from_cookie(session: str, db: Session) -> models.User | None:
    if not session:
        return None
    try:
        payload = jwt.decode(session, SESSION_SECRET, algorithms=["HS256"])
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        return None
    return db.query(models.User).filter(models.User.id == user_id).first()


# ── Health ────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    return {"status": "ok"}


# ── Google OAuth ──────────────────────────────────────────────────
@app.get("/api/auth/google")
async def google_login():
    # Random per-login state, echoed back by Google and compared against a
    # short-lived cookie in the callback — a mismatch means the callback
    # wasn't initiated by this browser (login CSRF), so it's rejected.
    state = uuid.uuid4().hex
    params = urlencode({
        "client_id":     GOOGLE_CLIENT_ID,
        "redirect_uri":  GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope":         "openid email profile",
        "access_type":   "offline",
        "prompt":        "select_account",
        "state":         state,
    })
    redirect = RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{params}")
    redirect.set_cookie(
        "oauth_state", state,
        httponly=True, samesite="lax", max_age=600, path="/",
    )
    return redirect


@app.get("/api/auth/google/callback")
async def google_callback(
    code: str,
    state: str = "",
    oauth_state: str = Cookie(default=None),
    db: Session = Depends(get_db),
):
    if not state or not oauth_state or state != oauth_state:
        raise HTTPException(status_code=400, detail="בקשת התחברות לא תקינה — נסה שוב")
    async with httpx.AsyncClient() as client:
        token_res = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id":     GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "code":          code,
                "grant_type":    "authorization_code",
                "redirect_uri":  GOOGLE_REDIRECT_URI,
            },
        )
        access_token = token_res.json().get("access_token")

        user_res = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        guser = user_res.json()

    google_id = guser.get("id", "")
    name      = guser.get("name", "משתמש")
    email     = guser.get("email", "")
    picture   = guser.get("picture", "")

    user = db.query(models.User).filter(models.User.google_id == google_id).first()
    if not user:
        user = models.User(google_id=google_id, name=name, email=email, picture=picture)
        db.add(user)
    else:
        user.name    = name
        user.picture = picture
    db.commit()
    db.refresh(user)

    redirect = RedirectResponse("/app")
    redirect.set_cookie(
        "session", _make_token(user.id),
        httponly=True, samesite="lax", max_age=30 * 24 * 3600, path="/",
    )
    redirect.delete_cookie("oauth_state", path="/")
    return redirect


@app.get("/api/me", response_model=schemas.UserOut)
def get_me(session: str = Cookie(default=None), db: Session = Depends(get_db)):
    user = _get_user_from_cookie(session, db)
    if not user:
        raise HTTPException(status_code=401, detail="לא מחובר")
    return user


@app.patch("/api/me", response_model=schemas.UserOut)
def update_profile(
    update: schemas.ProfileUpdate,
    session: str = Cookie(default=None),
    db: Session = Depends(get_db),
):
    user = _get_user_from_cookie(session, db)
    if not user:
        raise HTTPException(status_code=401, detail="לא מחובר")
    if update.age is not None:
        user.age = update.age
    if update.picture is not None:
        user.picture = update.picture
    if update.city is not None:
        user.city = update.city
    db.commit()
    db.refresh(user)
    return user


@app.get("/api/me/events", response_model=list[schemas.UserEventOut])
def get_my_events(session: str = Cookie(default=None), db: Session = Depends(get_db)):
    user = _get_user_from_cookie(session, db)
    if not user:
        raise HTTPException(status_code=401, detail="לא מחובר")
    return user.validated_events


@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie("session")
    return {"ok": True}


# ── Ticket check ──────────────────────────────────────────────────
# This is NOT ticket authentication — FastiRide doesn't sell tickets and has
# no access to the issuing platform's (Zygo/Go-Out/etc.) real database, so
# there's no way to check a barcode is genuine or unused. This only checks
# that the uploaded photo *plausibly* mentions the event, as a light spam
# filter before someone can see/post rides. Framed honestly in the UI too.
def _perceptual_hash(image: Image.Image, hash_size: int = 8) -> int:
    """Coarse visual fingerprint (average hash) — compares overall layout/color,
    not text. A small localized text edit (e.g. a ticket-round label) only
    flips a couple of the hash_size**2 bits, so real tickets from different
    rounds of the same design still match; a genuinely different event's
    ticket (different template/colors/logo) does not, no matter what text is
    pasted onto it."""
    small = image.convert("L").resize((hash_size, hash_size), Image.LANCZOS)
    pixels = list(small.getdata())
    avg = sum(pixels) / len(pixels)
    bits = 0
    for i, p in enumerate(pixels):
        if p > avg:
            bits |= (1 << i)
    return bits


def _hamming_distance(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


VISUAL_MATCH_THRESHOLD = 12  # out of 64 bits — tolerant of minor edits, not of a different design

# Generous enough for a full-resolution phone photo of a ticket, small enough
# to keep a hostile upload from tying up memory/Rekognition for nothing.
MAX_TICKET_UPLOAD_BYTES = 15 * 1024 * 1024


def _ticket_matches(qr_text: str, ocr_text: str, event: models.Event, image: Image.Image) -> bool:
    # A scannable QR/barcode is mandatory — closes the "type the event name
    # over any random image, no real ticket at all" gap that pure-OCR
    # matching used to allow.
    if not qr_text.strip():
        return False

    reference_tickets = json.loads(event.reference_tickets) if event.reference_tickets else []
    if reference_tickets:
        # Real reference samples exist for this event — visual similarity is
        # the ONLY signal that decides. Text is deliberately excluded here:
        # it's exactly the part an attacker can edit, so once we have real
        # data to compare against, a text match alone must never be enough
        # (a genuine ticket from a DIFFERENT event with this event's name
        # pasted on top would otherwise still pass on text).
        uploaded_hash = _perceptual_hash(image)
        for ref_data_uri in reference_tickets:
            try:
                ref_bytes = base64.b64decode(ref_data_uri.split(",", 1)[1])
                ref_image = Image.open(BytesIO(ref_bytes)).convert("RGB")
                if _hamming_distance(uploaded_hash, _perceptual_hash(ref_image)) <= VISUAL_MATCH_THRESHOLD:
                    return True
            except Exception:
                continue
        return False

    # No reference tickets at all for this event (producer chose not to
    # upload any) — fall back to the original text-based baseline.
    combined = (qr_text + " " + ocr_text).lower()
    words = [w for w in event.name.split() if len(w) > 2]
    if not words:
        return False
    matches = sum(1 for w in words if w.lower() in combined)
    return matches >= max(1, len(words) // 2)


def _extract_text_rekognition(content: bytes) -> str:
    """Managed OCR via AWS Rekognition — no native deps in the container.
    Note: DetectText reads Latin script only; Hebrew-only tickets fall
    back to the QR path (and pytesseract when Rekognition is disabled)."""
    import boto3
    client = boto3.client("rekognition", region_name=AWS_REGION)
    resp = client.detect_text(Image={"Bytes": content})
    return " ".join(
        d["DetectedText"] for d in resp.get("TextDetections", [])
        if d.get("Type") == "LINE"
    )


def _archive_ticket_to_s3(content: bytes, event_id: int) -> None:
    if not S3_UPLOADS_BUCKET:
        return
    try:
        import boto3
        boto3.client("s3", region_name=AWS_REGION).put_object(
            Bucket=S3_UPLOADS_BUCKET,
            Key=f"tickets/{event_id}/{uuid.uuid4().hex}.jpg",
            Body=content,
            ContentType="image/jpeg",
        )
    except Exception as e:
        print(f"[S3 ARCHIVE ERROR] {e}")


@app.post("/api/validate")
async def validate(
    event_id: int        = Form(...),
    file:     UploadFile = File(...),
    db:       Session    = Depends(get_db),
    session:  str        = Cookie(default=None),
):
    # Auth first: every anonymous call here would otherwise burn a paid
    # Rekognition request and an S3 write — and the real user flow always
    # reaches this screen logged-in anyway.
    user = _get_user_from_cookie(session, db)
    if not user:
        raise HTTPException(status_code=401, detail="יש להתחבר כדי לאמת כרטיס")

    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        return {"valid": False, "error": "האירוע לא נמצא"}

    content = await file.read()
    if len(content) > MAX_TICKET_UPLOAD_BYTES:
        return {"valid": False, "error": "הקובץ גדול מדי — יש להעלות תמונה עד 15MB"}
    try:
        image = Image.open(BytesIO(content)).convert("RGB")
    except Exception:
        # Covers corrupt files, non-images and PIL's decompression-bomb guard
        return {"valid": False, "error": "הקובץ שהועלה אינו תמונה תקינה"}

    # שלב א' — סריקת QR / ברקוד (מקומי, מהיר, תמיד רץ)
    qr_text = ""
    try:
        decoded = qr_decode(image)
        if decoded:
            qr_text = " ".join(d.data.decode("utf-8", errors="ignore") for d in decoded)
    except Exception:
        pass

    # שלב ב' — OCR: Rekognition (מנוהל) עם fallback ל-pytesseract מקומי.
    # מדלגים לגמרי כשלאירוע יש כרטיסי דוגמה — במקרה הזה ההחלטה נשענת רק על
    # דמיון חזותי (ראו _ticket_matches), וה-OCR לא ייכנס לתמונה בכלל, אז אין
    # טעם לשלם/להמתין לקריאת Rekognition שהתוצאה שלה תיזרק.
    ocr_text = ""
    if not event.reference_tickets:
        if USE_REKOGNITION:
            try:
                ocr_text = _extract_text_rekognition(content)
            except Exception as e:
                print(f"[REKOGNITION ERROR] {e} — falling back to local OCR")
        if not ocr_text:
            try:
                ocr_text = pytesseract.image_to_string(image, lang="heb+eng")
            except Exception:
                pass

    # ארכיון: שמירת תמונת הכרטיס ב-S3 (אם מוגדר bucket)
    _archive_ticket_to_s3(content, event.id)

    if _ticket_matches(qr_text, ocr_text, event, image):
        try:
            db.add(models.UserEvent(user_id=user.id, event_id=event.id))
            db.commit()
        except IntegrityError:
            db.rollback()
        return {"valid": True, "event_name": event.name, "event_id": event.id}

    if not qr_text.strip():
        error = "לא זיהינו ברקוד/QR קריא בתמונה — יש להעלות צילום ברור של הכרטיס עצמו"
    else:
        error = f"התמונה שהעלית לא זוהתה ככרטיס תקף ל-'{event.name}'"
    return {"valid": False, "error": error}


# ── Events ────────────────────────────────────────────────────────
@app.get("/api/events", response_model=list[schemas.EventPublic])
def get_events(db: Session = Depends(get_db)):
    return db.query(models.Event).all()


@app.post("/api/events", response_model=schemas.EventOut)
def create_event(
    event: schemas.EventCreate,
    db: Session = Depends(get_db),
    session: str = Cookie(default=None),
):
    user = _get_user_from_cookie(session, db)
    if not user:
        raise HTTPException(status_code=401, detail="יש להתחבר כדי ליצור אירוע")
    phone = re.sub(r"\D", "", event.owner_phone or "")
    if not re.match(r"^0\d{8,9}$", phone):
        raise HTTPException(status_code=400, detail="מספר טלפון לא תקין")
    db_event = models.Event(
        **event.model_dump(exclude={"owner_phone", "reference_tickets"}),
        owner_email=user.email,
        owner_phone=phone,
        reference_tickets=json.dumps(event.reference_tickets) if event.reference_tickets else None,
    )
    db.add(db_event)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="אירוע עם אותו שם ותאריך כבר קיים")
    db.refresh(db_event)
    return db_event


@app.get("/api/me/produced-events", response_model=list[schemas.EventOut])
def get_my_produced_events(session: str = Cookie(default=None), db: Session = Depends(get_db)):
    user = _get_user_from_cookie(session, db)
    if not user:
        raise HTTPException(status_code=401, detail="לא מחובר")
    return (
        db.query(models.Event)
        .filter(models.Event.owner_email == user.email)
        .order_by(models.Event.id.desc())
        .all()
    )


def _authorize_event_owner(event: models.Event, session: str, db: Session) -> None:
    user = _get_user_from_cookie(session, db)
    # No recorded owner = nobody is authorized (deny-by-default) — the old
    # `if event.owner_email and ...` form silently let anyone manage
    # legacy owner-less events.
    if not user or not event.owner_email or event.owner_email != user.email:
        raise HTTPException(status_code=403, detail="אין הרשאה לנהל אירוע זה")


@app.patch("/api/events/{event_id}", response_model=schemas.EventOut)
def update_event(
    event_id: int,
    updates: schemas.EventUpdate,
    db: Session = Depends(get_db),
    session: str = Cookie(default=None),
):
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="האירוע לא נמצא")
    _authorize_event_owner(event, session, db)
    for field, value in updates.model_dump(exclude_unset=True).items():
        if field == "reference_tickets":
            value = json.dumps(value) if value else None
        setattr(event, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="אירוע עם אותו שם ותאריך כבר קיים")
    db.refresh(event)
    return event


@app.delete("/api/events/{event_id}")
def delete_event(
    event_id: int,
    db: Session = Depends(get_db),
    session: str = Cookie(default=None),
):
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="האירוע לא נמצא")
    _authorize_event_owner(event, session, db)
    active_rides = db.query(models.Ride).filter(models.Ride.event_id == event_id).count()
    if active_rides:
        raise HTTPException(
            status_code=400,
            detail="לא ניתן למחוק אירוע עם נסיעות פעילות — יש לבטל אותן קודם",
        )
    db.delete(event)
    db.commit()
    return {"ok": True}


@app.get("/api/events/{event_id}/attendees")
def get_event_attendees(
    event_id: int,
    db: Session = Depends(get_db),
    session: str = Cookie(default=None),
):
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="האירוע לא נמצא")
    _authorize_event_owner(event, session, db)
    rides = db.query(models.Ride).filter(models.Ride.event_id == event_id).all()
    return {
        "validated_count": db.query(models.UserEvent).filter(models.UserEvent.event_id == event_id).count(),
        "rides_count": len(rides),
        "rides": [
            {
                "id": r.id,
                "driver_name": r.driver_name,
                "city": r.city,
                "departure_time": r.departure_time,
                "seats_available": r.seats_available,
                "approved_count": db.query(models.RideRequest).filter(
                    models.RideRequest.ride_id == r.id,
                    models.RideRequest.status == "approved",
                ).count(),
            }
            for r in rides
        ],
    }


# ── Rides ─────────────────────────────────────────────────────────
@app.get("/api/rides")
def get_rides(
    event_id: int = None,
    db: Session = Depends(get_db),
    session: str = Cookie(default=None),
):
    query = db.query(models.Ride)
    if event_id:
        query = query.filter(models.Ride.event_id == event_id)
    rides = query.order_by(models.Ride.created_at.desc()).all()
    me = _get_user_from_cookie(session, db)

    ride_ids = [r.id for r in rides]
    approved = []
    if ride_ids:
        approved = (
            db.query(models.RideRequest, models.User)
            .outerjoin(models.User, models.User.email == models.RideRequest.passenger_email)
            .filter(
                models.RideRequest.ride_id.in_(ride_ids),
                models.RideRequest.status == "approved",
            )
            .all()
        )

    participants_by_ride = {}
    for req, user in approved:
        participants_by_ride.setdefault(req.ride_id, []).append({
            "name":    req.passenger_name,
            "age":     user.age if user else None,
            "picture": user.picture if user else None,
        })

    # The logged-in user's own request per ride — lets the UI restore
    # the "pending"/"approved" button state after a page reload.
    my_requests = {}
    if me and ride_ids:
        for req in (
            db.query(models.RideRequest)
            .filter(
                models.RideRequest.ride_id.in_(ride_ids),
                models.RideRequest.passenger_email == me.email,
            )
            .all()
        ):
            my_requests[req.ride_id] = {"id": req.id, "status": req.status}

    result = []
    for r in rides:
        d = {c.name: getattr(r, c.name) for c in r.__table__.columns}
        d["participants"] = participants_by_ride.get(r.id, [])
        d["my_request"]   = my_requests.get(r.id)
        result.append(d)
    return result


@app.post("/api/rides", response_model=schemas.RideOut)
def create_ride(
    ride: schemas.RideCreate,
    db: Session = Depends(get_db),
    session: str = Cookie(default=None),
):
    user = _get_user_from_cookie(session, db)
    if not user:
        raise HTTPException(status_code=401, detail="יש להתחבר כדי לפרסם נסיעה")
    event = db.query(models.Event).filter(models.Event.id == ride.event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="האירוע לא נמצא")
    ride_data = ride.model_dump()
    # Identity comes from the session, never from client input — same rule
    # join_ride already enforces for passengers. A client-supplied
    # driver_email would let anyone publish rides in someone else's name.
    ride_data["driver_email"] = user.email
    ride_data["driver_name"]  = user.name
    if not ride_data.get("driver_photo"):
        ride_data["driver_photo"] = user.picture
    if not ride_data.get("driver_age"):
        ride_data["driver_age"] = user.age
    db_ride = models.Ride(**ride_data)
    db.add(db_ride)
    db.commit()
    db.refresh(db_ride)
    return db_ride


@app.patch("/api/rides/{ride_id}", response_model=schemas.RideOut)
def update_ride(
    ride_id: int,
    updates: schemas.RideUpdate,
    db: Session = Depends(get_db),
    session: str = Cookie(default=None),
):
    ride = db.query(models.Ride).filter(models.Ride.id == ride_id).first()
    if not ride:
        raise HTTPException(status_code=404, detail="הנסיעה לא נמצאה")
    user = _get_user_from_cookie(session, db)
    # Owner-less rides are locked, not open — deny-by-default
    if not user or not ride.driver_email or ride.driver_email != user.email:
        raise HTTPException(status_code=403, detail="אין הרשאה לערוך נסיעה זו")
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(ride, field, value)
    db.commit()
    db.refresh(ride)
    return ride


@app.delete("/api/rides/{ride_id}")
def delete_ride(
    ride_id: int,
    db: Session = Depends(get_db),
    session: str = Cookie(default=None),
):
    ride = db.query(models.Ride).filter(models.Ride.id == ride_id).first()
    if not ride:
        raise HTTPException(status_code=404, detail="הנסיעה לא נמצאה")
    user = _get_user_from_cookie(session, db)
    # Owner-less rides are locked, not open — deny-by-default
    if not user or not ride.driver_email or ride.driver_email != user.email:
        raise HTTPException(status_code=403, detail="אין הרשאה למחוק נסיעה זו")
    db.delete(ride)
    db.commit()
    return {"ok": True}


@app.post("/api/rides/{ride_id}/join", response_model=schemas.RideRequestOut)
def join_ride(
    ride_id: int,
    req: schemas.RideRequestCreate,
    db: Session = Depends(get_db),
    session: str = Cookie(default=None),
):
    ride = db.query(models.Ride).filter(models.Ride.id == ride_id).first()
    if not ride:
        raise HTTPException(status_code=404, detail="הנסיעה לא נמצאה")
    if ride.seats_available <= 0:
        raise HTTPException(status_code=400, detail="אין מקומות פנויים")
    user = _get_user_from_cookie(session, db)
    if not user:
        raise HTTPException(status_code=401, detail="יש להתחבר כדי להצטרף לנסיעה")
    if user.age is None:
        raise HTTPException(status_code=403, detail="יש להשלים גיל בפרופיל לפני הצטרפות לנסיעה")
    if ride.driver_email and ride.driver_email == user.email:
        raise HTTPException(status_code=400, detail="לא ניתן להצטרף לנסיעה של עצמך")
    existing = db.query(models.RideRequest).filter(
        models.RideRequest.ride_id == ride_id,
        models.RideRequest.passenger_email == user.email,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="כבר שלחת בקשה לנסיעה זו")
    payload = req.model_dump()
    # Identity comes from the session, not from whatever the client typed
    payload["passenger_name"]  = user.name
    payload["passenger_email"] = user.email
    db_req = models.RideRequest(ride_id=ride_id, **payload)
    db.add(db_req)
    db.commit()
    db.refresh(db_req)
    send_join_notification(
        driver_email=ride.driver_email or "",
        driver_name=ride.driver_name,
        passenger_name=user.name,
        ride_city=ride.city,
        departure_time=ride.departure_time,
    )
    return db_req


@app.delete("/api/rides/{ride_id}/join/{request_id}")
def cancel_join(
    ride_id: int,
    request_id: int,
    db: Session = Depends(get_db),
    session: str = Cookie(default=None),
):
    req = db.query(models.RideRequest).filter(
        models.RideRequest.id == request_id,
        models.RideRequest.ride_id == ride_id,
    ).first()
    if not req:
        raise HTTPException(status_code=404, detail="הבקשה לא נמצאה")
    ride = req.ride
    user = _get_user_from_cookie(session, db)
    is_passenger = user and req.passenger_email == user.email
    is_driver    = user and ride.driver_email == user.email
    if not (is_passenger or is_driver):
        raise HTTPException(status_code=403, detail="אין הרשאה לבטל בקשה זו")
    # An approved passenger leaving frees their seat back up
    if req.status == "approved":
        ride.seats_available += 1
    send_cancel_notification(
        driver_email=ride.driver_email or "",
        driver_name=ride.driver_name,
        passenger_name=req.passenger_name,
        ride_city=ride.city,
    )
    db.delete(req)
    db.commit()
    return {"ok": True}


@app.get("/api/me/requests")
def get_my_pending_requests(session: str = Cookie(default=None), db: Session = Depends(get_db)):
    user = _get_user_from_cookie(session, db)
    if not user:
        raise HTTPException(status_code=401, detail="לא מחובר")
    requests = (
        db.query(models.RideRequest)
        .join(models.Ride)
        .filter(models.Ride.driver_email == user.email, models.RideRequest.status == "pending")
        .order_by(models.RideRequest.created_at.desc())
        .all()
    )
    passenger_emails = {r.passenger_email for r in requests if r.passenger_email}
    passengers_by_email = {
        u.email: u
        for u in db.query(models.User).filter(models.User.email.in_(passenger_emails)).all()
    } if passenger_emails else {}
    return [
        {
            "id": r.id,
            "ride_id": r.ride_id,
            "passenger_name": r.passenger_name,
            "passenger_photo": passengers_by_email.get(r.passenger_email).picture if r.passenger_email in passengers_by_email else None,
            "passenger_age": passengers_by_email.get(r.passenger_email).age if r.passenger_email in passengers_by_email else None,
            "created_at": r.created_at,
            "ride_city": r.ride.city,
            "ride_departure_time": r.ride.departure_time,
        }
        for r in requests
    ]


def _authorize_driver(ride: models.Ride, session: str, db: Session) -> None:
    user = _get_user_from_cookie(session, db)
    if not user or not ride.driver_email or ride.driver_email != user.email:
        raise HTTPException(status_code=403, detail="אין הרשאה לנהל בקשה זו")


@app.post("/api/rides/{ride_id}/join/{request_id}/approve", response_model=schemas.RideRequestOut)
def approve_join(
    ride_id: int,
    request_id: int,
    db: Session = Depends(get_db),
    session: str = Cookie(default=None),
):
    req = db.query(models.RideRequest).filter(
        models.RideRequest.id == request_id,
        models.RideRequest.ride_id == ride_id,
    ).first()
    if not req:
        raise HTTPException(status_code=404, detail="הבקשה לא נמצאה")
    ride = req.ride
    _authorize_driver(ride, session, db)
    if ride.seats_available <= 0:
        raise HTTPException(status_code=400, detail="אין מקומות פנויים")
    req.status = "approved"
    ride.seats_available -= 1
    db.commit()
    db.refresh(req)
    return req


@app.post("/api/rides/{ride_id}/join/{request_id}/reject")
def reject_join(
    ride_id: int,
    request_id: int,
    db: Session = Depends(get_db),
    session: str = Cookie(default=None),
):
    req = db.query(models.RideRequest).filter(
        models.RideRequest.id == request_id,
        models.RideRequest.ride_id == ride_id,
    ).first()
    if not req:
        raise HTTPException(status_code=404, detail="הבקשה לא נמצאה")
    ride = req.ride
    _authorize_driver(ride, session, db)
    db.delete(req)
    db.commit()
    return {"ok": True}


# ── Ride chat (WebSocket) ─────────────────────────────────────────
# Room registry: ride_id -> list of live WebSocket connections.
# In-memory — fine for a single replica; scaling to multiple pods
# requires pub/sub (e.g. Redis) so messages cross pod boundaries.
class ChatRooms:
    def __init__(self):
        self.rooms: dict[int, list[WebSocket]] = {}

    async def connect(self, ride_id: int, ws: WebSocket):
        await ws.accept()
        self.rooms.setdefault(ride_id, []).append(ws)

    def disconnect(self, ride_id: int, ws: WebSocket):
        conns = self.rooms.get(ride_id, [])
        if ws in conns:
            conns.remove(ws)
        if not conns:
            self.rooms.pop(ride_id, None)

    async def broadcast(self, ride_id: int, payload: dict):
        for ws in list(self.rooms.get(ride_id, [])):
            try:
                await ws.send_json(payload)
            except Exception:
                self.disconnect(ride_id, ws)


chat_rooms = ChatRooms()


def _can_access_chat(ride: models.Ride, user: models.User | None, db: Session) -> bool:
    """Chat is private: driver + approved passengers only."""
    if not user:
        return False
    if ride.driver_email and ride.driver_email == user.email:
        return True
    return db.query(models.RideRequest).filter(
        models.RideRequest.ride_id == ride.id,
        models.RideRequest.passenger_email == user.email,
        models.RideRequest.status == "approved",
    ).first() is not None


@app.get("/api/rides/{ride_id}/chat")
def chat_history(
    ride_id: int,
    db: Session = Depends(get_db),
    session: str = Cookie(default=None),
):
    ride = db.query(models.Ride).filter(models.Ride.id == ride_id).first()
    if not ride:
        raise HTTPException(status_code=404, detail="הנסיעה לא נמצאה")
    user = _get_user_from_cookie(session, db)
    if not _can_access_chat(ride, user, db):
        raise HTTPException(status_code=403, detail="הצ'אט פתוח לנהג ולנוסעים שאושרו בלבד")
    messages = (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.ride_id == ride_id)
        .order_by(models.ChatMessage.created_at.asc())
        .limit(200)
        .all()
    )
    return [
        {
            "sender_name":  m.sender_name,
            "sender_email": m.sender_email,
            "text":         m.text,
            "created_at":   m.created_at.isoformat(),
        }
        for m in messages
    ]


@app.get("/api/me/chats")
def get_my_chats(session: str = Cookie(default=None), db: Session = Depends(get_db)):
    """Every ride chat the user can access, with last message + unread count — powers the 'my chats' screen and the navbar badge."""
    user = _get_user_from_cookie(session, db)
    if not user:
        raise HTTPException(status_code=401, detail="לא מחובר")

    driver_ride_ids = [
        r.id for r in db.query(models.Ride.id).filter(models.Ride.driver_email == user.email).all()
    ]
    passenger_ride_ids = [
        req.ride_id for req in db.query(models.RideRequest).filter(
            models.RideRequest.passenger_email == user.email,
            models.RideRequest.status == "approved",
        ).all()
    ]
    ride_ids = list({*driver_ride_ids, *passenger_ride_ids})
    if not ride_ids:
        return []

    rides = db.query(models.Ride).filter(models.Ride.id.in_(ride_ids)).all()
    reads = {
        r.ride_id: r.read_at
        for r in db.query(models.ChatRead).filter(
            models.ChatRead.ride_id.in_(ride_ids),
            models.ChatRead.user_email == user.email,
        ).all()
    }

    result = []
    for ride in rides:
        last_msg = (
            db.query(models.ChatMessage)
            .filter(models.ChatMessage.ride_id == ride.id)
            .order_by(models.ChatMessage.created_at.desc())
            .first()
        )
        if not last_msg:
            continue
        read_at = reads.get(ride.id)
        unread_query = db.query(models.ChatMessage).filter(
            models.ChatMessage.ride_id == ride.id,
            models.ChatMessage.sender_email != user.email,
        )
        if read_at:
            unread_query = unread_query.filter(models.ChatMessage.created_at > read_at)
        result.append({
            "ride_id":          ride.id,
            "ride_city":        ride.city,
            "ride_departure_time": ride.departure_time,
            "last_message":     last_msg.text,
            "last_message_at":  last_msg.created_at.isoformat(),
            "unread_count":     unread_query.count(),
        })
    result.sort(key=lambda c: c["last_message_at"], reverse=True)
    return result


@app.post("/api/rides/{ride_id}/chat/read")
def mark_chat_read(
    ride_id: int,
    db: Session = Depends(get_db),
    session: str = Cookie(default=None),
):
    ride = db.query(models.Ride).filter(models.Ride.id == ride_id).first()
    if not ride:
        raise HTTPException(status_code=404, detail="הנסיעה לא נמצאה")
    user = _get_user_from_cookie(session, db)
    if not _can_access_chat(ride, user, db):
        raise HTTPException(status_code=403, detail="הצ'אט פתוח לנהג ולנוסעים שאושרו בלבד")
    read = db.query(models.ChatRead).filter(
        models.ChatRead.ride_id == ride_id,
        models.ChatRead.user_email == user.email,
    ).first()
    if read:
        read.read_at = datetime.utcnow()
    else:
        db.add(models.ChatRead(ride_id=ride_id, user_email=user.email))
    db.commit()
    return {"ok": True}


@app.websocket("/api/ws/rides/{ride_id}/chat")
async def ride_chat(websocket: WebSocket, ride_id: int, db: Session = Depends(get_db)):
    ride = db.query(models.Ride).filter(models.Ride.id == ride_id).first()
    user = _get_user_from_cookie(websocket.cookies.get("session"), db)
    if not ride or not _can_access_chat(ride, user, db):
        # 4403: application-level "forbidden" close code (4000+ is the app range)
        await websocket.close(code=4403)
        return

    await chat_rooms.connect(ride_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            # Keepalive — resets the ALB idle timeout (default 60s)
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            msg_text = (data.get("text") or "").strip()[:500]
            if not msg_text:
                continue
            msg = models.ChatMessage(
                ride_id=ride_id,
                sender_name=user.name,
                sender_email=user.email,
                text=msg_text,
            )
            db.add(msg)
            db.commit()
            db.refresh(msg)
            await chat_rooms.broadcast(ride_id, {
                "type":         "message",
                "sender_name":  user.name,
                "sender_email": user.email,
                "text":         msg_text,
                "created_at":   msg.created_at.isoformat(),
            })
    except WebSocketDisconnect:
        chat_rooms.disconnect(ride_id, websocket)
