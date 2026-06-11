from datetime import datetime
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from database import Base


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    ticket_prefix = Column(String, nullable=True, default="")
    location = Column(String, nullable=True)
    date = Column(String, nullable=True)
    logo_url = Column(String, nullable=True)

    rides = relationship("Ride", back_populates="event")


class Ride(Base):
    __tablename__ = "rides"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False)
    driver_name = Column(String, nullable=False)
    city = Column(String, nullable=False)
    pickup_point = Column(String, nullable=False)
    departure_time = Column(String, nullable=False)
    seats_available = Column(Integer, default=2)
    driver_age = Column(Integer, nullable=True)
    driver_photo = Column(String, nullable=True)
    vehicle_type = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    event = relationship("Event", back_populates="rides")
    requests = relationship("RideRequest", back_populates="ride")


class RideRequest(Base):
    __tablename__ = "ride_requests"

    id = Column(Integer, primary_key=True, index=True)
    ride_id = Column(Integer, ForeignKey("rides.id"), nullable=False)
    passenger_name = Column(String, nullable=False)
    status = Column(String, default="pending")  # pending | approved | rejected
    created_at = Column(DateTime, default=datetime.utcnow)

    ride = relationship("Ride", back_populates="requests")
