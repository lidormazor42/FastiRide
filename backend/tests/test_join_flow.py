from tests.conftest import make_user, login, make_event, make_ride, grant_event_access


def test_join_requires_login(client, db):
    event = make_event(db)
    ride = make_ride(db, event.id)
    res = client.post(f"/api/rides/{ride.id}/join", json={"passenger_name": "X"})
    assert res.status_code == 401


def test_join_requires_age_set(client, db):
    passenger = make_user(db, age=None)
    event = make_event(db)
    ride = make_ride(db, event.id)
    login(client, passenger)
    res = client.post(f"/api/rides/{ride.id}/join", json={"passenger_name": passenger.name})
    assert res.status_code == 403


def test_driver_cannot_join_own_ride(client, db):
    driver = make_user(db, email="driver@example.com")
    event = make_event(db)
    ride = make_ride(db, event.id, driver_email=driver.email)
    login(client, driver)
    res = client.post(f"/api/rides/{ride.id}/join", json={"passenger_name": driver.name})
    assert res.status_code == 400


def test_duplicate_join_request_rejected(client, db):
    passenger = make_user(db)
    event = make_event(db)
    ride = make_ride(db, event.id)
    login(client, passenger)
    assert client.post(f"/api/rides/{ride.id}/join", json={"passenger_name": passenger.name}).status_code == 200
    res = client.post(f"/api/rides/{ride.id}/join", json={"passenger_name": passenger.name})
    assert res.status_code == 409


def test_approve_reduces_seats_and_requires_driver(client, db):
    driver = make_user(db, email="driver@example.com")
    passenger = make_user(db, email="passenger@example.com")
    other = make_user(db, email="other@example.com")
    event = make_event(db)
    ride = make_ride(db, event.id, driver_email=driver.email, seats_available=2)
    grant_event_access(db, driver, event.id)

    login(client, passenger)
    request_id = client.post(f"/api/rides/{ride.id}/join", json={"passenger_name": passenger.name}).json()["id"]

    login(client, other)
    assert client.post(f"/api/rides/{ride.id}/join/{request_id}/approve").status_code == 403

    login(client, driver)
    res = client.post(f"/api/rides/{ride.id}/join/{request_id}/approve")
    assert res.status_code == 200
    assert res.json()["status"] == "approved"

    rides = client.get(f"/api/rides?event_id={event.id}").json()
    assert next(r for r in rides if r["id"] == ride.id)["seats_available"] == 1


def test_reject_deletes_request_without_touching_seats(client, db):
    driver = make_user(db, email="driver@example.com")
    passenger = make_user(db, email="passenger@example.com")
    event = make_event(db)
    ride = make_ride(db, event.id, driver_email=driver.email, seats_available=2)
    grant_event_access(db, driver, event.id)

    login(client, passenger)
    request_id = client.post(f"/api/rides/{ride.id}/join", json={"passenger_name": passenger.name}).json()["id"]

    login(client, driver)
    res = client.post(f"/api/rides/{ride.id}/join/{request_id}/reject")
    assert res.status_code == 200

    rides = client.get(f"/api/rides?event_id={event.id}").json()
    assert next(r for r in rides if r["id"] == ride.id)["seats_available"] == 2


def test_cancel_join_frees_seat_only_if_was_approved(client, db):
    driver = make_user(db, email="driver@example.com")
    passenger = make_user(db, email="passenger@example.com")
    event = make_event(db)
    ride = make_ride(db, event.id, driver_email=driver.email, seats_available=2)
    grant_event_access(db, driver, event.id)
    grant_event_access(db, passenger, event.id)  # reads the board back below

    login(client, passenger)
    request_id = client.post(f"/api/rides/{ride.id}/join", json={"passenger_name": passenger.name}).json()["id"]

    login(client, driver)
    client.post(f"/api/rides/{ride.id}/join/{request_id}/approve")

    login(client, passenger)
    res = client.delete(f"/api/rides/{ride.id}/join/{request_id}")
    assert res.status_code == 200

    rides = client.get(f"/api/rides?event_id={event.id}").json()
    assert next(r for r in rides if r["id"] == ride.id)["seats_available"] == 2


def test_join_and_cancel_send_driver_notifications(client, db, _no_real_emails):
    """Emails now go through BackgroundTasks — this pins that they still
    actually fire (TestClient runs background tasks before returning)."""
    driver = make_user(db, email="driver@example.com")
    passenger = make_user(db, email="passenger@example.com")
    event = make_event(db)
    ride = make_ride(db, event.id, driver_email=driver.email)

    login(client, passenger)
    request_id = client.post(
        f"/api/rides/{ride.id}/join", json={"passenger_name": passenger.name}
    ).json()["id"]
    assert len(_no_real_emails) == 1
    assert _no_real_emails[0][0] == "driver@example.com"

    client.delete(f"/api/rides/{ride.id}/join/{request_id}")
    assert len(_no_real_emails) == 2
    assert _no_real_emails[1][0] == "driver@example.com"
