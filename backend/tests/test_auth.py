from urllib.parse import parse_qs, urlparse


def test_google_login_sets_state_cookie_matching_redirect(client):
    res = client.get("/api/auth/google", follow_redirects=False)
    assert res.status_code == 307
    query = parse_qs(urlparse(res.headers["location"]).query)
    state_in_url = query["state"][0]
    assert state_in_url
    assert res.cookies.get("oauth_state") == state_in_url


def test_google_callback_rejects_mismatched_state(client):
    client.cookies.set("oauth_state", "expected-state")
    res = client.get(
        "/api/auth/google/callback?code=whatever&state=attacker-state",
        follow_redirects=False,
    )
    assert res.status_code == 400


def test_google_callback_rejects_missing_state(client):
    res = client.get(
        "/api/auth/google/callback?code=whatever",
        follow_redirects=False,
    )
    assert res.status_code == 400
