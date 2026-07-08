from tests.conftest import make_user, login, make_event, make_ride


def test_chat_open_to_driver(client, db):
    driver = make_user(db, email="driver@example.com")
    event = make_event(db)
    ride = make_ride(db, event.id, driver_email=driver.email)
    login(client, driver)
    assert client.get(f"/api/rides/{ride.id}/chat").status_code == 200


def test_chat_closed_to_unrelated_user(client, db):
    driver = make_user(db, email="driver@example.com")
    stranger = make_user(db, email="stranger@example.com")
    event = make_event(db)
    ride = make_ride(db, event.id, driver_email=driver.email)
    login(client, stranger)
    assert client.get(f"/api/rides/{ride.id}/chat").status_code == 403


def test_chat_closed_to_pending_passenger(client, db):
    driver = make_user(db, email="driver@example.com")
    passenger = make_user(db, email="passenger@example.com")
    event = make_event(db)
    ride = make_ride(db, event.id, driver_email=driver.email)

    login(client, passenger)
    client.post(f"/api/rides/{ride.id}/join", json={"passenger_name": passenger.name})
    res = client.get(f"/api/rides/{ride.id}/chat")
    assert res.status_code == 403


def test_chat_open_to_approved_passenger(client, db):
    driver = make_user(db, email="driver@example.com")
    passenger = make_user(db, email="passenger@example.com")
    event = make_event(db)
    ride = make_ride(db, event.id, driver_email=driver.email)

    login(client, passenger)
    request_id = client.post(f"/api/rides/{ride.id}/join", json={"passenger_name": passenger.name}).json()["id"]

    login(client, driver)
    client.post(f"/api/rides/{ride.id}/join/{request_id}/approve")

    login(client, passenger)
    assert client.get(f"/api/rides/{ride.id}/chat").status_code == 200
