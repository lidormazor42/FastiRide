from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class TicketRequest(BaseModel):
    ticket_code: str


class EventCreate(BaseModel):
    name: str
    ticket_prefix: Optional[str] = ""
    location: Optional[str] = None
    date: Optional[str] = None
    logo_url: Optional[str] = None


class EventOut(EventCreate):
    id: int

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
    seats_available: int = 2


class RideOut(RideCreate):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class RideUpdate(BaseModel):
    city: Optional[str] = None
    pickup_point: Optional[str] = None
    departure_time: Optional[str] = None
    seats_available: Optional[int] = None
    vehicle_type: Optional[str] = None


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    picture: Optional[str] = None

    class Config:
        from_attributes = True


class UserEventOut(BaseModel):
    event_id: int
    event: EventOut
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
