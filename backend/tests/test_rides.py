from tests.conftest import make_user, login, make_event, make_ride, grant_event_access


def test_create_ride_with_new_fields(client, db):
    user = make_user(db, email="driver@example.com")
    event = make_event(db)
    login(client, user)

    res = client.post("/api/rides", json={
        "event_id": event.id,
        "driver_name": "נהג",
        "city": "תל אביב",
        "pickup_point": "תחנת רכבת",
        "departure_time": "14:00",
        "return_city": "חיפה",
        "return_time": "23:30",
        "seats_available": 3,
        "fuel_cost": 90,
    })
    assert res.status_code == 200
    body = res.json()
    assert body["return_city"] == "חיפה"
    assert body["fuel_cost"] == 90.0
    # driver_email auto-filled from the session, not required in the payload
    assert body["driver_email"] == user.email


def test_create_ride_requires_login(client, db):
    event = make_event(db)
    res = client.post("/api/rides", json={
        "event_id": event.id,
        "driver_name": "נהג",
        "city": "תל אביב",
        "pickup_point": "תחנה",
        "departure_time": "14:00",
    })
    assert res.status_code == 401


def test_create_ride_ignores_spoofed_driver_identity(client, db):
    """driver_email/driver_name always come from the session — a client
    sending someone else's email must not be able to publish rides in
    their name (they'd own the ride and get its join-request emails)."""
    user = make_user(db, name="Real Name", email="real@example.com")
    event = make_event(db)
    login(client, user)
    res = client.post("/api/rides", json={
        "event_id": event.id,
        "driver_name": "Fake Name",
        "driver_email": "victim@example.com",
        "city": "תל אביב",
        "pickup_point": "תחנה",
        "departure_time": "14:00",
    })
    assert res.status_code == 200
    body = res.json()
    assert body["driver_email"] == "real@example.com"
    assert body["driver_name"] == "Real Name"


def test_ownerless_ride_is_locked_not_open(client, db):
    user = make_user(db)
    event = make_event(db)
    ride = make_ride(db, event.id, driver_email=None)
    login(client, user)
    assert client.patch(f"/api/rides/{ride.id}", json={"city": "חיפה"}).status_code == 403
    assert client.delete(f"/api/rides/{ride.id}").status_code == 403


def test_create_ride_requires_existing_event(client, db):
    user = make_user(db)
    login(client, user)
    res = client.post("/api/rides", json={
        "event_id": 999,
        "driver_name": "נהג",
        "city": "תל אביב",
        "pickup_point": "תחנה",
        "departure_time": "14:00",
    })
    assert res.status_code == 404


def test_get_rides_includes_participants_and_my_request(client, db):
    driver = make_user(db, email="driver@example.com")
    passenger = make_user(db, email="passenger@example.com", age=30)
    event = make_event(db)
    ride = make_ride(db, event.id, driver_email=driver.email)
    grant_event_access(db, passenger, event.id)

    login(client, passenger)
    join_res = client.post(f"/api/rides/{ride.id}/join", json={"passenger_name": passenger.name})
    assert join_res.status_code == 200
    request_id = join_res.json()["id"]

    login(client, driver)
    approve_res = client.post(f"/api/rides/{ride.id}/join/{request_id}/approve")
    assert approve_res.status_code == 200

    login(client, passenger)
    rides = client.get("/api/rides").json()
    this_ride = next(r for r in rides if r["id"] == ride.id)
    assert this_ride["my_request"]["status"] == "approved"
    assert len(this_ride["participants"]) == 1
    assert this_ride["participants"][0]["name"] == passenger.name


def test_only_driver_can_update_or_delete_ride(client, db):
    driver = make_user(db, email="driver@example.com")
    other = make_user(db, email="other@example.com")
    event = make_event(db)
    ride = make_ride(db, event.id, driver_email=driver.email)

    login(client, other)
    assert client.patch(f"/api/rides/{ride.id}", json={"city": "חיפה"}).status_code == 403
    assert client.delete(f"/api/rides/{ride.id}").status_code == 403

    login(client, driver)
    res = client.patch(f"/api/rides/{ride.id}", json={"city": "חיפה"})
    assert res.status_code == 200
    assert res.json()["city"] == "חיפה"
    assert client.delete(f"/api/rides/{ride.id}").status_code == 200


def test_get_rides_requires_login(client, db):
    """A ride row carries a named person, a pickup point and a departure
    time — an anonymous caller must never be able to read that."""
    event = make_event(db)
    make_ride(db, event.id)
    res = client.get("/api/rides")
    assert res.status_code == 401


def test_get_rides_requires_validated_ticket_for_that_event(client, db):
    """Validating a ticket is the product's access gate; it has to be
    enforced by the API, not only by the UI hiding the board."""
    outsider = make_user(db, email="outsider@example.com")
    event = make_event(db)
    make_ride(db, event.id)

    login(client, outsider)
    assert client.get(f"/api/rides?event_id={event.id}").status_code == 403
    # Without an event_id it must not leak the same rides via the "all" path
    assert client.get("/api/rides").json() == []


def test_get_rides_visible_after_validating_and_to_the_producer(client, db):
    attendee = make_user(db, email="attendee@example.com")
    producer = make_user(db, email="producer@example.com")
    event = make_event(db, owner_email=producer.email)
    ride = make_ride(db, event.id)

    grant_event_access(db, attendee, event.id)
    login(client, attendee)
    res = client.get(f"/api/rides?event_id={event.id}")
    assert res.status_code == 200
    assert [r["id"] for r in res.json()] == [ride.id]

    # The producer never validates a ticket for their own event
    login(client, producer)
    assert [r["id"] for r in client.get(f"/api/rides?event_id={event.id}").json()] == [ride.id]


def test_get_rides_hides_driver_email_and_flags_own_rides(client, db):
    driver = make_user(db, email="driver@example.com")
    other  = make_user(db, email="other@example.com")
    event  = make_event(db)
    make_ride(db, event.id, driver_email=driver.email)
    grant_event_access(db, driver, event.id)
    grant_event_access(db, other, event.id)

    login(client, other)
    ride = client.get(f"/api/rides?event_id={event.id}").json()[0]
    assert "driver_email" not in ride
    assert ride["is_mine"] is False

    login(client, driver)
    assert client.get(f"/api/rides?event_id={event.id}").json()[0]["is_mine"] is True
