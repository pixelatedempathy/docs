import sys

sys.path.insert(0, "linear-audit")
import pathlib
import tempfile
from unittest.mock import Mock, patch

import fetch_issues
import refresh_dashboard
import register_webhook
import remediate
import run_audit


def test_fetch_paths():
    with patch("fetch_issues.requests.post") as m:

        def se(*args, **kwargs):
            r = Mock()
            r.raise_for_status = Mock()
            r.json.return_value = {
                "data": {
                    "team": {
                        "name": "T",
                        "issues": {
                            "edges": [
                                {"node": {"id": "1", "identifier": "LIN-1", "title": "t", "state": {"type": "backlog"}}}
                            ],
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                        },
                    }
                }
            }
            return r

        m.side_effect = se
        result = fetch_issues.fetch_all_issues(api_key="k", team_id="team1", max_pages=1)
        assert isinstance(result, list)
        assert len(result) == 1
    with patch("fetch_issues.requests.post") as m:
        calls = [0]

        def se2(*args, **kwargs):
            calls[0] += 1
            r = Mock()
            r.raise_for_status = Mock()
            if calls[0] == 1:
                r.json.return_value = {
                    "data": {
                        "team": {
                            "name": "T",
                            "issues": {
                                "edges": [
                                    {
                                        "node": {
                                            "id": "1",
                                            "identifier": "LIN-1",
                                            "title": "t",
                                            "state": {"type": "backlog"},
                                        }
                                    }
                                ],
                                "pageInfo": {"hasNextPage": True, "endCursor": "c1"},
                            },
                        }
                    }
                }
            elif calls[0] == 2:
                r.json.return_value = {
                    "data": {
                        "team": {
                            "name": "T",
                            "issues": {
                                "edges": [
                                    {
                                        "node": {
                                            "id": "2",
                                            "identifier": "LIN-2",
                                            "title": "t2",
                                            "state": {"type": "backlog"},
                                        }
                                    }
                                ],
                                "pageInfo": {"hasNextPage": True, "endCursor": "c2"},
                            },
                        }
                    }
                }
            else:
                r.json.return_value = {
                    "data": {"team": {"name": "T", "issues": {"edges": [], "pageInfo": {"hasNextPage": False}}}}
                }
            return r

        m.side_effect = se2
        result = fetch_issues.fetch_all_issues(api_key="k", team_id="team1", max_pages=5)
        assert len(result) >= 2
    with patch("fetch_issues.requests.post") as m:
        mr = Mock()
        mr.json.return_value = {"errors": [{"message": "auth"}]}
        mr.raise_for_status = Mock()
        m.return_value = mr
        result = fetch_issues.fetch_all_issues(api_key="k", team_id="team1")
        assert result == []
    with patch("fetch_issues.requests.post") as m:
        mr = Mock()
        mr.json.return_value = {"data": {"team": None}}
        mr.raise_for_status = Mock()
        m.return_value = mr
        result = fetch_issues.fetch_all_issues(api_key="k", team_id="bad")
        assert result == []
    with patch("fetch_issues.requests.post", side_effect=__import__("requests").RequestException("net")):
        try:
            result = fetch_issues.fetch_all_issues(api_key="k", team_id="team1")
            assert isinstance(result, list)
        except __import__("requests").RequestException:
            pass
    from fetch_issues import transform_to_flat

    flat = transform_to_flat(
        {"id": "1", "identifier": "LIN-1", "title": "t", "state": {"type": "backlog"}, "priority": 1}
    )
    assert flat.get("identifier") == "LIN-1" or flat.get("id") == "LIN-1" or flat.get("id") == "1"
    assert flat.get("title") == "t"


def test_refresh_paths():
    issues = [
        {
            "id": "1",
            "identifier": "LIN-1",
            "title": "t",
            "state": {"type": "completed", "name": "Done"},
            "assignee": None,
            "project": {"id": "p1"},
            "estimate": 2,
            "description": "d",
            "parent": None,
            "completedAt": "2026-01-01",
            "priority": 1,
            "archivedAt": None,
        },
    ]
    md, _entries, stats = refresh_dashboard.generate_dashboard_content(issues, now_str="2026-01-01 00:00 UTC")
    assert isinstance(md, str)
    md2, _e2, _s2 = refresh_dashboard.generate_dashboard_content([], now_str="2026-01-01 00:00 UTC")
    assert isinstance(md2, str)
    big = [
        {
            "id": str(i),
            "identifier": f"LIN-{i}",
            "title": f"Issue {i}",
            "state": {"type": "completed" if i % 3 == 0 else "backlog", "name": "Done" if i % 3 == 0 else "Todo"},
            "assignee": None if i % 2 == 0 else {"id": "u1"},
            "project": {"id": f"p{i % 2}", "name": f"P{i % 2}"},
            "estimate": i % 5,
            "description": "d" if i % 2 == 0 else "",
            "parent": None,
            "priority": 1,
            "archivedAt": None,
            "completedAt": None,
        }
        for i in range(50)
    ]
    md, _entries, stats = refresh_dashboard.generate_dashboard_content(big, now_str="2026-01-01 00:00 UTC")
    assert stats["total_issues"] == 50
    with patch(
        "refresh_dashboard.gql", return_value={"data": {"issues": {"nodes": [], "pageInfo": {"hasNextPage": False}}}}
    ):
        assert refresh_dashboard.fetch_project_issues(api_key="k", max_pages=1) == []
    with patch(
        "refresh_dashboard.gql",
        return_value={
            "data": {
                "issues": {
                    "nodes": [
                        {
                            "id": "1",
                            "identifier": "LIN-1",
                            "title": "t",
                            "priority": 1,
                            "estimate": 2,
                            "state": {"id": "s", "name": "Todo", "type": "backlog"},
                            "parent": None,
                            "completedAt": None,
                        }
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        },
    ):
        assert isinstance(refresh_dashboard.fetch_project_issues(api_key="k", max_pages=None), list)


def test_register_paths():
    with patch(
        "register_webhook.gql",
        return_value={
            "data": {
                "webhooks": {
                    "nodes": [
                        {"id": "1", "label": "L1", "url": "https://a", "enabled": True, "resourceTypes": ["Issue"]}
                    ]
                }
            }
        },
    ):
        assert len(register_webhook.list_webhooks(api_key="k")) == 1
    with patch("register_webhook.gql", return_value=None):
        assert register_webhook.list_webhooks(api_key="k") == []
    with (
        patch(
            "register_webhook.gql",
            return_value={
                "data": {
                    "webhookCreate": {
                        "success": True,
                        "webhook": {
                            "id": "1",
                            "label": "t",
                            "url": "https://example.com",
                            "enabled": True,
                            "resourceTypes": ["Issue"],
                        },
                    }
                }
            },
        ),
        patch("register_webhook.secrets.token_hex", return_value="a" * 32),
    ):
        r = register_webhook.register_webhook("https://example.com/hook2", label="Label With Spaces", api_key="k")
        assert r is not None
    with (
        patch(
            "register_webhook.list_webhooks",
            return_value=[{"id": "1", "label": "Exists", "url": "https://a", "enabled": True, "resourceTypes": []}],
        ),
        patch("register_webhook.gql", return_value={"data": {"webhookDelete": {"success": True}}}),
    ):
        result = register_webhook.unregister_webhook(label="Exists", api_key="k")
        assert isinstance(result, bool)


def test_remediate_paths():
    c = remediate.LinearClient(api_key="k")
    assert "Authorization" in c.headers
    with patch("remediate.requests.post") as m:
        mr = Mock()
        mr.json.return_value = {"data": {"issueUpdate": {"success": True}}}
        mr.raise_for_status = Mock()
        m.return_value = mr
        assert c.update_issue("id", {"title": "t"}) is True
        mr2 = Mock()
        mr2.json.return_value = {"errors": ["e"]}
        mr2.raise_for_status = Mock()
        m.return_value = mr2
        assert c.update_issue("id", {}) is False


def test_run_audit_paths():
    import json as js

    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "issues.json"
        p.write_text(
            js.dumps(
                [
                    {
                        "id": "1",
                        "identifier": "LIN-1",
                        "title": "t",
                        "state": {"type": "backlog"},
                        "project": "p1",
                        "estimate": 1,
                    }
                ]
            )
        )
        issues = run_audit.load_issues(p)
        result = run_audit.run_audit(issues)
        assert isinstance(result, dict)
        p.write_text(js.dumps({"issues": "notalist"}))
        try:
            run_audit.load_issues(p)
            raise AssertionError()
        except ValueError:
            pass
        result = run_audit.run_audit([])
        assert isinstance(result, dict)
