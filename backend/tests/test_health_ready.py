def test_health_is_shallow(client):
    """Liveness must never depend on the DB — see the docstring in main.py."""
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_ready_checks_the_db(client, db):
    res = client.get("/api/ready")
    assert res.status_code == 200
    assert res.json() == {"status": "ready"}


def test_ready_returns_503_when_db_unreachable(client):
    import main
    from database import get_db

    class BrokenSession:
        def execute(self, *a, **kw):
            raise Exception("connection refused")

    main.app.dependency_overrides[get_db] = lambda: BrokenSession()
    try:
        res = client.get("/api/ready")
        assert res.status_code == 503
    finally:
        main.app.dependency_overrides.pop(get_db, None)
