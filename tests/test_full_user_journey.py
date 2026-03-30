"""End-to-end user journey smoke tests (Task 92)."""
from __future__ import annotations


class TestCompleteUserJourney:
    def test_free_user_onboarding_and_execute(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        st = client.get("/onboarding/status")
        assert st.status_code == 200
        assert st.json().get("current_step") == 0
        ex = client.post(
            "/execute",
            json={"command": "check disk space and save report to workspace"},
        )
        assert ex.status_code == 202
        task_id = ex.json()["task_id"]
        tr = client.get(f"/tasks/{task_id}")
        assert tr.status_code == 200
        tpl = client.get("/templates")
        assert tpl.status_code == 200
        assert len(tpl.json().get("templates", [])) > 0
