import os
from io import BytesIO
from urllib.parse import urlencode, quote
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
import httpx
from PIL import Image
from pyzbar.pyzbar import decode as qr_decode
import pytesseract
from database import engine, get_db, Base
import models
import schemas

Base.metadata.create_all(bind=engine)

# Add new columns to existing tables without Alembic
from sqlalchemy import text
with engine.connect() as _conn:
    _conn.execute(text("ALTER TABLE rides ADD COLUMN IF NOT EXISTS driver_age INTEGER"))
    _conn.execute(text("ALTER TABLE rides ADD COLUMN IF NOT EXISTS driver_photo TEXT"))
    _conn.execute(text("ALTER TABLE rides ADD COLUMN IF NOT EXISTS vehicle_type TEXT"))
    _conn.execute(text("ALTER TABLE events ADD COLUMN IF NOT EXISTS logo_url TEXT"))
    _conn.execute(text("ALTER TABLE events ALTER COLUMN ticket_prefix DROP NOT NULL"))
    _conn.commit()

app = FastAPI()

GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI  = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost/api/auth/google/callback")


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
async def google_callback(code: str):
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
        user = user_res.json()

    name    = quote(user.get("name", "משתמש"), safe="")
    picture = quote(user.get("picture", ""), safe="")
    email   = quote(user.get("email", ""), safe="")

    return RedirectResponse(f"/?name={name}&picture={picture}&email={email}")


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
def create_ride(ride: schemas.RideCreate, db: Session = Depends(get_db)):
    event = db.query(models.Event).filter(models.Event.id == ride.event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="האירוע לא נמצא")
    db_ride = models.Ride(**ride.model_dump())
    db.add(db_ride)
    db.commit()
    db.refresh(db_ride)
    return db_ride


@app.patch("/api/rides/{ride_id}", response_model=schemas.RideOut)
def update_ride(ride_id: int, updates: schemas.RideUpdate, db: Session = Depends(get_db)):
    ride = db.query(models.Ride).filter(models.Ride.id == ride_id).first()
    if not ride:
        raise HTTPException(status_code=404, detail="הנסיעה לא נמצאה")
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(ride, field, value)
    db.commit()
    db.refresh(ride)
    return ride


@app.delete("/api/rides/{ride_id}")
def delete_ride(ride_id: int, db: Session = Depends(get_db)):
    ride = db.query(models.Ride).filter(models.Ride.id == ride_id).first()
    if not ride:
        raise HTTPException(status_code=404, detail="הנסיעה לא נמצאה")
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
    return db_req
