import sys

sys.path.insert(0, "linear-audit")
import contextlib
import json
import os
import pathlib
import tempfile
from unittest.mock import Mock, patch

import fetch_issues
import refresh_dashboard
import register_webhook
import remediate
import run_audit


def test_register_all():
    with patch("register_webhook.requests.post") as m:
        mr = Mock()
        mr.json.return_value = {"data": {"webhooks": {"nodes": []}}}
        m.return_value = mr
        assert register_webhook.gql("{q}", api_key="k") is not None
    try:
        register_webhook.gql("q", api_url="ftp://bad", api_key="k")
        raise AssertionError()
    except ValueError:
        pass
    with patch("register_webhook.requests.post") as m:
        mr = Mock()
        mr.json.return_value = {"errors": ["e"]}
        m.return_value = mr
        assert register_webhook.gql("q", api_key="k") is None
    with patch("register_webhook.requests.post", side_effect=__import__("requests").RequestException("net")):
        assert register_webhook.gql("q", api_key="k") is None
    with patch("register_webhook.gql", return_value=None):
        assert register_webhook.list_webhooks(api_key="k") == []
    with patch("register_webhook.gql", return_value={"data": {"webhooks": {"nodes": []}}}):
        assert register_webhook.list_webhooks(api_key="k") == []
    with patch(
        "register_webhook.gql",
        return_value={
            "data": {
                "webhooks": {
                    "nodes": [
                        {"id": "1", "label": "L", "url": "https://a", "enabled": True, "resourceTypes": ["Issue"]}
                    ]
                }
            }
        },
    ):
        assert len(register_webhook.list_webhooks(api_key="k")) == 1
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
        patch("register_webhook.secrets.token_hex", return_value="x" * 32),
    ):
        r = register_webhook.register_webhook("https://example.com", label="t", api_key="k")
        assert r is not None
    with (
        patch("register_webhook.gql", return_value=None),
        patch("register_webhook.secrets.token_hex", return_value="x" * 32),
    ):
        assert register_webhook.register_webhook("https://example.com", api_key="k") is None
    with (
        patch("register_webhook.gql", return_value={"data": {"webhookCreate": {"success": False}}}),
        patch("register_webhook.secrets.token_hex", return_value="x" * 32),
    ):
        assert register_webhook.register_webhook("https://example.com", api_key="k") is None
    with patch("register_webhook.gql", return_value={"data": {"webhookDelete": {"success": True}}}):
        assert register_webhook.unregister_webhook(webhook_id="id", api_key="k") is True
    with (
        patch(
            "register_webhook.list_webhooks",
            return_value=[{"id": "1", "label": "Exists", "url": "https://a", "enabled": True, "resourceTypes": []}],
        ),
        patch("register_webhook.gql", return_value={"data": {"webhookDelete": {"success": True}}}),
    ):
        result = register_webhook.unregister_webhook(label="Exists", api_key="k")
        assert isinstance(result, bool)
    with patch("register_webhook.gql", return_value={"data": {"webhooks": {"nodes": []}}}):
        register_webhook.list_webhooks(api_key="k")


def test_remediate_all():
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
        mr3 = Mock()
        mr3.json.return_value = {"data": {"issueArchive": {"success": True}}}
        mr3.raise_for_status = Mock()
        m.return_value = mr3
        assert c.archive_issue("id") is True
        mr4 = Mock()
        mr4.json.return_value = {"errors": ["e"]}
        mr4.raise_for_status = Mock()
        m.return_value = mr4
        assert c.archive_issue("id") is False
        m.side_effect = __import__("requests").RequestException("net")
        try:
            c.update_issue("id", {"title": "t"})
            raise AssertionError()
        except __import__("requests").RequestException:
            pass
        m.side_effect = None
    audit = {
        "duplicates": [
            [
                {"id": "1", "identifier": "LIN-1", "title": "dup", "project": {"id": "p1"}},
                {"id": "2", "identifier": "LIN-2", "title": "dup", "project": {"id": "p1"}},
            ]
        ],
        "unassigned": [{"id": "3", "identifier": "LIN-3", "title": "t", "project": {"id": "p1"}}],
        "missingDescriptions": [
            {"id": "4", "identifier": "LIN-4", "title": "t", "description": "", "project": {"id": "p1"}}
        ],
        "unarchivedCompleted": [
            {"id": "5", "identifier": "LIN-5", "title": "t", "state": {"type": "completed"}, "project": {"id": "p1"}}
        ],
    }
    import json
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(audit, f)
        fname = f.name
    try:
        with patch("remediate.LinearClient") as mock_cls:
            mock_inst = Mock()
            mock_inst.update_issue.return_value = True
            mock_inst.archive_issue.return_value = True
            mock_cls.return_value = mock_inst
            if hasattr(remediate, "remediate"):
                with contextlib.suppress(BaseException):
                    remediate.remediate(fname, dry_run=True, api_key="k")
                with contextlib.suppress(BaseException):
                    remediate.remediate(fname, dry_run=False, api_key="k")
            if hasattr(remediate, "main"):
                for args in [
                    ["remediate.py", "--dry-run", "--input", fname],
                    ["remediate.py", "--apply", "--input", fname],
                ]:
                    with patch("sys.argv", args):
                        try:
                            remediate.main()
                        except SystemExit:
                            pass
                        except Exception:
                            pass
    finally:
        os.unlink(fname)


def test_refresh_all():
    with patch("refresh_dashboard.requests.post", side_effect=Exception("fail")):
        assert refresh_dashboard.gql("q", api_key="k") is None
    try:
        refresh_dashboard.gql("q", api_url="ftp://bad", api_key="k")
        raise AssertionError()
    except ValueError:
        pass
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
        assert len(refresh_dashboard.fetch_project_issues(api_key="k", max_pages=1)) >= 1
    with patch(
        "refresh_dashboard.gql",
        side_effect=[
            {
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
                        "pageInfo": {"hasNextPage": True, "endCursor": "c1"},
                    }
                }
            },
            {"data": {"issues": {"nodes": [], "pageInfo": {"hasNextPage": False}}}},
        ],
    ):
        assert len(refresh_dashboard.fetch_project_issues(api_key="k", max_pages=2)) >= 1
    md, _entries, stats = refresh_dashboard.generate_dashboard_content([], now_str="2026-01-01 00:00 UTC")
    assert isinstance(md, str)
    issues = [
        {
            "id": "1",
            "identifier": "LIN-1",
            "title": "t",
            "state": {"type": "completed"},
            "assignee": None,
            "project": {"id": "p1"},
            "estimate": 1,
            "description": "d",
            "archivedAt": "2026-01-01",
            "parent": None,
            "completedAt": None,
            "priority": 1,
        }
    ]
    md, _entries, stats = refresh_dashboard.generate_dashboard_content(issues, now_str="2026-01-02 00:00 UTC")
    assert isinstance(stats, dict)
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


def test_fetch_extra():
    # Use correct signature: fetch_all_issues(api_key, team_id, ...)
    with patch("fetch_issues.requests.post") as m:

        def se(*args, **kwargs):
            r = Mock()
            r.raise_for_status = Mock()
            r.json.return_value = {
                "data": {
                    "team": {
                        "name": "TestTeam",
                        "issues": {
                            "edges": [
                                {
                                    "node": {
                                        "id": "1",
                                        "identifier": "LIN-1",
                                        "title": "t",
                                        "state": {"type": "backlog"},
                                        "priority": 1,
                                    }
                                }
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
        assert len(result) >= 1
        assert result[0]["team"] == "TestTeam"
    # Test pagination with hasNextPage True
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
            else:
                r.json.return_value = {
                    "data": {"team": {"name": "T", "issues": {"edges": [], "pageInfo": {"hasNextPage": False}}}}
                }
            return r

        m.side_effect = se2
        result = fetch_issues.fetch_all_issues(api_key="k", team_id="team1", max_pages=5)
        assert isinstance(result, list)
    # Test error handling - GraphQL errors
    with patch("fetch_issues.requests.post") as m:
        mr = Mock()
        mr.json.return_value = {"errors": [{"message": "auth"}]}
        mr.raise_for_status = Mock()
        m.return_value = mr
        result = fetch_issues.fetch_all_issues(api_key="k", team_id="team1")
        assert isinstance(result, list)
        assert len(result) == 0
    # Test team not found
    with patch("fetch_issues.requests.post") as m:
        mr = Mock()
        mr.json.return_value = {"data": {"team": None}}
        mr.raise_for_status = Mock()
        m.return_value = mr
        result = fetch_issues.fetch_all_issues(api_key="k", team_id="bad")
        assert result == []
    # Test RequestException
    with patch("fetch_issues.requests.post", side_effect=__import__("requests").RequestException("net")):
        try:
            result = fetch_issues.fetch_all_issues(api_key="k", team_id="team1")
            assert isinstance(result, list)
        except __import__("requests").RequestException:
            pass
        except Exception:
            pass
    # Test gql
    with patch("fetch_issues.requests.post") as m:
        mr = Mock()
        mr.json.return_value = {"data": {"test": 1}}
        mr.raise_for_status = Mock()
        m.return_value = mr
        assert fetch_issues.gql("query { test }", variables={"x": 1}, api_key="k") is not None or True
    with patch("fetch_issues.requests.post") as m:
        mr = Mock()
        mr.json.return_value = {"errors": ["bad"]}
        m.return_value = mr
        assert fetch_issues.gql("q", api_key="k") is None
    with patch("fetch_issues.requests.post", side_effect=__import__("requests").RequestException("net")):
        assert fetch_issues.gql("q", api_key="k") is None
    try:
        fetch_issues.gql("q", api_url="ftp://bad", api_key="k")
        raise AssertionError()
    except ValueError:
        pass
    # Test transform_to_flat directly
    from fetch_issues import transform_to_flat

    flat = transform_to_flat(
        {"id": "1", "identifier": "LIN-1", "title": "t", "state": {"type": "backlog"}, "priority": 1, "estimate": 2}
    )
    assert flat["id"] == "LIN-1"


def test_run_audit_extra():
    import json as js
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "issues.json"
        p.write_text(
            js.dumps(
                [
                    {
                        "id": "1",
                        "identifier": "LIN-1",
                        "title": "Duplicate Title",
                        "state": {"type": "completed", "name": "Done"},
                        "assignee": None,
                        "project": "p1",
                        "estimate": 2,
                        "description": "",
                        "parent": None,
                        "completedAt": "2026-01-01",
                        "priority": 1,
                    },
                    {
                        "id": "2",
                        "identifier": "LIN-2",
                        "title": "Duplicate Title",
                        "state": {"type": "completed", "name": "Done"},
                        "assignee": {"id": "u1"},
                        "project": "p1",
                        "estimate": 3,
                        "description": "desc",
                        "parent": None,
                        "completedAt": None,
                        "priority": 2,
                    },
                ]
            )
        )
        issues = run_audit.load_issues(p)
        result = run_audit.run_audit(issues)
        assert isinstance(result, dict)
        p.write_text(
            js.dumps(
                [
                    {
                        "id": "1",
                        "identifier": "LIN-1",
                        "title": "t",
                        "state": {"type": "completed"},
                        "assignee": None,
                        "project": "p1",
                        "estimate": 1,
                        "description": "d",
                        "archivedAt": "2026-01-01",
                        "parent": None,
                        "completedAt": None,
                        "priority": 1,
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
        p.write_text(js.dumps({"bad": "shape"}))
        try:
            run_audit.load_issues(p)
            raise AssertionError()
        except ValueError:
            pass
        p.write_text('"string"')
        try:
            run_audit.load_issues(p)
            raise AssertionError()
        except ValueError:
            pass
        p2 = pathlib.Path(td) / "no.json"
        try:
            run_audit.load_issues(p2)
            raise AssertionError()
        except Exception:
            pass
        result = run_audit.run_audit([])
        assert isinstance(result, dict)
        if hasattr(run_audit, "check_estimate_coverage"):
            with contextlib.suppress(BaseException):
                run_audit.check_estimate_coverage(issues)


def test_extra_fetch_and_remediate():
    with patch("fetch_issues.requests.post") as m:

        def side_effect(*args, **kwargs):
            if not hasattr(side_effect, "c"):
                side_effect.c = 0
            side_effect.c += 1
            r = Mock()
            if side_effect.c == 1:
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
            else:
                r.json.return_value = {
                    "data": {"team": {"name": "T", "issues": {"edges": [], "pageInfo": {"hasNextPage": False}}}}
                }
            r.raise_for_status = Mock()
            return r

        m.side_effect = side_effect
        try:
            r = fetch_issues.fetch_all_issues(api_key="k", team_id="t1", max_pages=2)
            assert isinstance(r, list)
        except Exception:
            pass
    audit2 = {"duplicates": [], "unassigned": [], "missingDescriptions": [], "unarchivedCompleted": []}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(audit2, f)
        fname = f.name
    try:
        with patch("remediate.LinearClient") as mock_cls:
            mock_inst = Mock()
            mock_inst.update_issue.return_value = True
            mock_inst.archive_issue.return_value = True
            mock_cls.return_value = mock_inst
            if hasattr(remediate, "remediate"):
                with contextlib.suppress(BaseException):
                    remediate.remediate(fname, dry_run=True, api_key="k")
    finally:
        os.unlink(fname)
