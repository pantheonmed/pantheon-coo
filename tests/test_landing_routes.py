"""Marketing landing at ``/`` and dashboard at ``/dashboard``."""

def test_root_returns_landing_page(client):
    r = client.get("/")
    assert r.status_code == 200
    body = r.text
    assert "Your AI Chief Operating Officer" in body
    assert "17 AI agents" in body
    assert "30+ tools" in body
    assert 'href="/dashboard"' in body


def test_dashboard_route_returns_dashboard_ui(client):
    r = client.get("/dashboard")
    assert r.status_code == 200
    assert "Pantheon COO OS" in r.text


def test_landing_alias_matches_home(client):
    a = client.get("/")
    b = client.get("/landing")
    assert a.status_code == 200 and b.status_code == 200
    assert a.text == b.text
