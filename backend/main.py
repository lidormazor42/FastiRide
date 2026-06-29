import os
from io import BytesIO
from urllib.parse import urlencode
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Cookie, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from jose import jwt, JWTError
import httpx
from PIL import Image
from pyzbar.pyzbar import decode as qr_decode
import pytesseract
from database import engine, get_db, Base
import models
import schemas
from email_service import send_join_notification, send_cancel_notification

SESSION_SECRET = os.getenv("SESSION_SECRET", "fastiride-dev-secret-change-in-prod")

Base.metadata.create_all(bind=engine)

# Add new columns to existing tables without Alembic
from sqlalchemy import text
with engine.connect() as _conn:
    _conn.execute(text("ALTER TABLE rides ADD COLUMN IF NOT EXISTS driver_age INTEGER"))
    _conn.execute(text("ALTER TABLE rides ADD COLUMN IF NOT EXISTS driver_photo TEXT"))
    _conn.execute(text("ALTER TABLE rides ADD COLUMN IF NOT EXISTS driver_email TEXT"))
    _conn.execute(text("ALTER TABLE rides ADD COLUMN IF NOT EXISTS vehicle_type TEXT"))
    _conn.execute(text("ALTER TABLE events ADD COLUMN IF NOT EXISTS logo_url TEXT"))
    _conn.execute(text("ALTER TABLE events ALTER COLUMN ticket_prefix DROP NOT NULL"))
    _conn.execute(text("ALTER TABLE ride_requests ADD COLUMN IF NOT EXISTS passenger_email TEXT"))
    _conn.commit()

app = FastAPI()

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
    params = urlencode({
        "client_id":     GOOGLE_CLIENT_ID,
        "redirect_uri":  GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope":         "openid email profile",
        "access_type":   "offline",
        "prompt":        "select_account",
    })
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{params}")


@app.get("/api/auth/google/callback")
async def google_callback(code: str, db: Session = Depends(get_db)):
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

    redirect = RedirectResponse("/")
    redirect.set_cookie(
        "session", _make_token(user.id),
        httponly=True, samesite="lax", max_age=30 * 24 * 3600, path="/",
    )
    return redirect


@app.get("/api/me", response_model=schemas.UserOut)
def get_me(session: str = Cookie(default=None), db: Session = Depends(get_db)):
    user = _get_user_from_cookie(session, db)
    if not user:
        raise HTTPException(status_code=401, detail="לא מחובר")
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


# ── Ticket validation ─────────────────────────────────────────────
def _ticket_matches(qr_text: str, ocr_text: str, event_name: str) -> bool:
    combined = (qr_text + " " + ocr_text).lower()
    words    = [w for w in event_name.split() if len(w) > 2]
    if not words:
        return False
    matches = sum(1 for w in words if w.lower() in combined)
    return matches >= max(1, len(words) // 2)


@app.post("/api/validate")
async def validate(
    event_id: int        = Form(...),
    file:     UploadFile = File(...),
    db:       Session    = Depends(get_db),
    session:  str        = Cookie(default=None),
):
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        return {"valid": False, "error": "האירוע לא נמצא"}

    content = await file.read()
    image   = Image.open(BytesIO(content)).convert("RGB")

    # שלב א' — סריקת QR / ברקוד
    qr_text = ""
    try:
        decoded = qr_decode(image)
        if decoded:
            qr_text = " ".join(d.data.decode("utf-8", errors="ignore") for d in decoded)
    except Exception:
        pass

    # שלב ב' — OCR (גיבוי אם QR לא מספיק)
    ocr_text = ""
    try:
        ocr_text = pytesseract.image_to_string(image, lang="heb+eng")
    except Exception:
        pass

    if _ticket_matches(qr_text, ocr_text, event.name):
        user = _get_user_from_cookie(session, db)
        if user:
            try:
                db.add(models.UserEvent(user_id=user.id, event_id=event.id))
                db.commit()
            except IntegrityError:
                db.rollback()
        return {"valid": True, "event_name": event.name, "event_id": event.id}

    return {"valid": False, "error": f"הכרטיס לא תואם לאירוע '{event.name}'"}


# ── Events ────────────────────────────────────────────────────────
@app.get("/api/events")
def get_events(db: Session = Depends(get_db)):
    return db.query(models.Event).all()


@app.post("/api/events", response_model=schemas.EventOut)
def create_event(event: schemas.EventCreate, db: Session = Depends(get_db)):
    db_event = models.Event(**event.model_dump())
    db.add(db_event)
    db.commit()
    db.refresh(db_event)
    return db_event


# ── Rides ─────────────────────────────────────────────────────────
@app.get("/api/rides")
def get_rides(event_id: int = None, db: Session = Depends(get_db)):
    query = db.query(models.Ride)
    if event_id:
        query = query.filter(models.Ride.event_id == event_id)
    return query.order_by(models.Ride.created_at.desc()).all()


@app.post("/api/rides", response_model=schemas.RideOut)
def create_ride(
    ride: schemas.RideCreate,
    db: Session = Depends(get_db),
    session: str = Cookie(default=None),
):
    event = db.query(models.Event).filter(models.Event.id == ride.event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="האירוע לא נמצא")
    ride_data = ride.model_dump()
    # Guarantee driver_email is always saved — fill from session if client didn't send it
    if not ride_data.get("driver_email"):
        user = _get_user_from_cookie(session, db)
        if user:
            ride_data["driver_email"] = user.email
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
    # If the ride has an owner email, enforce it matches the session user
    if ride.driver_email and (not user or ride.driver_email != user.email):
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
    # If the ride has an owner email, enforce it matches the session user
    if ride.driver_email and (not user or ride.driver_email != user.email):
        raise HTTPException(status_code=403, detail="אין הרשאה למחוק נסיעה זו")
    db.delete(ride)
    db.commit()
    return {"ok": True}


@app.post("/api/rides/{ride_id}/join", response_model=schemas.RideRequestOut)
def join_ride(ride_id: int, req: schemas.RideRequestCreate, db: Session = Depends(get_db)):
    ride = db.query(models.Ride).filter(models.Ride.id == ride_id).first()
    if not ride:
        raise HTTPException(status_code=404, detail="הנסיעה לא נמצאה")
    if ride.seats_available <= 0:
        raise HTTPException(status_code=400, detail="אין מקומות פנויים")
    db_req = models.RideRequest(ride_id=ride_id, **req.model_dump())
    db.add(db_req)
    db.commit()
    db.refresh(db_req)
    send_join_notification(
        driver_email=ride.driver_email or "",
        driver_name=ride.driver_name,
        passenger_name=req.passenger_name,
        ride_city=ride.city,
        departure_time=ride.departure_time,
    )
    return db_req


@app.delete("/api/rides/{ride_id}/join/{request_id}")
def cancel_join(ride_id: int, request_id: int, db: Session = Depends(get_db)):
    req = db.query(models.RideRequest).filter(
        models.RideRequest.id == request_id,
        models.RideRequest.ride_id == ride_id,
    ).first()
    if not req:
        raise HTTPException(status_code=404, detail="הבקשה לא נמצאה")
    ride = req.ride
    send_cancel_notification(
        driver_email=ride.driver_email or "",
        driver_name=ride.driver_name,
        passenger_name=req.passenger_name,
        ride_city=ride.city,
    )
    db.delete(req)
    db.commit()
    return {"ok": True}
