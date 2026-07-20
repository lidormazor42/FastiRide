from tests.conftest import make_user, login, make_event, make_ride


def test_event_attendees_approved_counts_per_ride(client, db):
    """Locks in behavior across the N+1 -> grouped-query rewrite: each ride's
    approved_count must reflect only ITS OWN approved requests, not bleed
    into another ride's count."""
    owner = make_user(db, email="owner@example.com")
    p1 = make_user(db, email="p1@example.com")
    p2 = make_user(db, email="p2@example.com")
    p3 = make_user(db, email="p3@example.com")
    event = make_event(db, owner_email=owner.email)
    ride_a = make_ride(db, event.id, driver_email=owner.email, seats_available=3)
    ride_b = make_ride(db, event.id, driver_email=owner.email, seats_available=3)

    def join_and_approve(passenger, ride):
        login(client, passenger)
        req_id = client.post(f"/api/rides/{ride.id}/join", json={"passenger_name": passenger.name}).json()["id"]
        login(client, owner)
        client.post(f"/api/rides/{ride.id}/join/{req_id}/approve")

    join_and_approve(p1, ride_a)
    join_and_approve(p2, ride_a)
    join_and_approve(p3, ride_b)

    login(client, owner)
    res = client.get(f"/api/events/{event.id}/attendees")
    assert res.status_code == 200
    body = res.json()
    counts = {r["id"]: r["approved_count"] for r in body["rides"]}
    assert counts[ride_a.id] == 2
    assert counts[ride_b.id] == 1
    assert body["rides_count"] == 2


def test_event_attendees_ride_with_no_requests_shows_zero(client, db):
    owner = make_user(db, email="owner@example.com")
    event = make_event(db, owner_email=owner.email)
    make_ride(db, event.id, driver_email=owner.email)
    login(client, owner)
    res = client.get(f"/api/events/{event.id}/attendees")
    assert res.json()["rides"][0]["approved_count"] == 0


def test_my_chats_last_message_and_unread_count_per_ride(client, db):
    """Locks in the grouped-in-Python rewrite: last message + unread count
    must stay correctly scoped per ride, not mixed across rides sharing the
    same message table."""
    driver = make_user(db, email="driver@example.com")
    passenger = make_user(db, email="passenger@example.com")
    event = make_event(db)
    ride1 = make_ride(db, event.id, driver_email=driver.email)
    ride2 = make_ride(db, event.id, driver_email=driver.email)

    for ride in (ride1, ride2):
        login(client, passenger)
        req_id = client.post(f"/api/rides/{ride.id}/join", json={"passenger_name": passenger.name}).json()["id"]
        login(client, driver)
        client.post(f"/api/rides/{ride.id}/join/{req_id}/approve")

    with client.websocket_connect(
        f"/api/ws/rides/{ride1.id}/chat",
        headers={"cookie": f"session={_session_cookie(client, passenger)}"},
    ) as ws:
        ws.send_json({"text": "hi from ride1"})
        ws.receive_json()
    with client.websocket_connect(
        f"/api/ws/rides/{ride2.id}/chat",
        headers={"cookie": f"session={_session_cookie(client, passenger)}"},
    ) as ws:
        ws.send_json({"text": "hi from ride2"})
        ws.receive_json()
        ws.send_json({"text": "second message ride2"})
        ws.receive_json()

    login(client, driver)
    res = client.get("/api/me/chats")
    assert res.status_code == 200
    by_ride = {c["ride_id"]: c for c in res.json()}
    assert by_ride[ride1.id]["last_message"] == "hi from ride1"
    assert by_ride[ride1.id]["unread_count"] == 1
    assert by_ride[ride2.id]["last_message"] == "second message ride2"
    assert by_ride[ride2.id]["unread_count"] == 2


def _session_cookie(client, user):
    import main
    return main._make_token(user.id)
