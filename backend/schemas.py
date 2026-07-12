import json
from pydantic import BaseModel, field_validator
from typing import Optional, List
from datetime import datetime


class TicketRequest(BaseModel):
    ticket_code: str


class EventCreate(BaseModel):
    name: str
    location: Optional[str] = None
    date: Optional[str] = None
    logo_url: Optional[str] = None
    reference_tickets: Optional[List[str]] = None
    owner_phone: str


class EventUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    date: Optional[str] = None
    logo_url: Optional[str] = None
    reference_tickets: Optional[List[str]] = None


class EventOut(BaseModel):
    id: int
    name: str
    location: Optional[str] = None
    date: Optional[str] = None
    logo_url: Optional[str] = None
    reference_tickets: Optional[List[str]] = None
    owner_email: Optional[str] = None
    owner_phone: Optional[str] = None

    @field_validator("reference_tickets", mode="before")
    @classmethod
    def _parse_reference_tickets(cls, v):
        """DB stores this as a JSON string (Text column); expose it as a list."""
        if isinstance(v, str):
            return json.loads(v) if v else None
        return v

    class Config:
        from_attributes = True


class EventPublic(BaseModel):
    """Public event listing — deliberately excludes owner contact details
    (privacy) and reference_tickets (both private security material and a
    huge base64 payload that made /api/events megabytes-heavy)."""
    id: int
    name: str
    location: Optional[str] = None
    date: Optional[str] = None
    logo_url: Optional[str] = None

    class Config:
        from_attributes = True


class RideCreate(BaseModel):
    event_id: int
    driver_name: str
    driver_age: Optional[int] = None
    driver_photo: Optional[str] = None
    driver_email: Optional[str] = None
    vehicle_type: Optional[str] = None
    city: str
    pickup_point: str
    departure_time: str
    return_city: Optional[str] = None
    return_time: Optional[str] = None
    seats_available: int = 2
    fuel_cost: Optional[float] = None


class RideOut(RideCreate):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class RideUpdate(BaseModel):
    city: Optional[str] = None
    pickup_point: Optional[str] = None
    departure_time: Optional[str] = None
    return_city: Optional[str] = None
    return_time: Optional[str] = None
    seats_available: Optional[int] = None
    vehicle_type: Optional[str] = None
    fuel_cost: Optional[float] = None


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    picture: Optional[str] = None
    age: Optional[int] = None
    city: Optional[str] = None

    class Config:
        from_attributes = True


class ProfileUpdate(BaseModel):
    age: Optional[int] = None
    picture: Optional[str] = None
    city: Optional[str] = None


class UserEventOut(BaseModel):
    event_id: int
    event: EventPublic
    validated_at: datetime

    class Config:
        from_attributes = True


class RideRequestCreate(BaseModel):
    passenger_name: str
    passenger_email: Optional[str] = None


class RideRequestOut(RideRequestCreate):
    id: int
    ride_id: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
