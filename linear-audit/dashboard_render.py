#!/usr/bin/env python3
"""
Markdown rendering helpers for the Enterprise Readiness dashboard.

Pure functions that turn a flat list of Linear issue nodes into the
``dashboard.md`` markdown and workstream statistics. Kept separate from
``refresh_dashboard.py`` (API fetch + CLI) so the rendering logic is testable
without network access.
"""

from datetime import UTC, datetime

# Workstream definitions keyed by parent issue identifier.
# Each entry: (short_name, priority, icon, priority_emoji)
DEFAULT_WORKSTREAMS = {
    "PIX-4126": ("Penetration Testing", 1, "\U0001f512", "\U0001f534"),  # Urgent
    "PIX-4125": ("Disaster Recovery", 2, "\U0001f504", "\U0001f7e1"),  # High
    "PIX-4127": ("SLA/SLO Definitions", 2, "\U0001f4ca", "\U0001f7e1"),  # High
    "PIX-4129": ("Vendor Risk Assessment", 2, "\U0001f4cb", "\U0001f7e1"),  # High
    "PIX-4130": ("SOC2/HIPAA Readiness", 2, "\u2705", "\U0001f7e1"),  # High
    "PIX-4128": ("Chaos Engineering", 3, "\U0001f9ea", "\U0001f7e2"),  # Medium
}

DEFAULT_CUSTOM_VIEW_URL = "https://linear.app/pixelated/view/cb20ccc27a23"
DEFAULT_EPIC_ID = "PIX-4131"
DEFAULT_AUDIT_TRACKER_ID = "PIX-4158"

PRIORITY_LABELS = {1: "Urgent", 2: "High", 3: "Medium"}

# State types considered "complete/done"
DONE_STATE_TYPES = {"completed"}

# State types considered "in progress"
IN_PROGRESS_STATE_TYPES = {"started", "review"}


def progress_bar(completed: int, total: int, width: int = 10) -> str:
    """Generate a Unicode progress bar like ████░░░░░░."""
    if total == 0:
        return "\u2591" * width + " 0%"
    filled = round(completed / total * width)
    pct = round(completed / total * 100)
    bar = "\u2588" * filled + "\u2591" * (width - filled)
    return f"{bar} {pct}%"


def render_workstream_table(ws_entries: list) -> str:
    """Render the overview progress table."""
    rows = []
    for ws in ws_entries:
        rows.append(
            f"| {ws['priority_emoji']} {ws['priority_label']} "
            f"| {ws['icon']} {ws['name']} "
            f"| {ws['progress_bar']} "
            f"| {ws['done_count']}/{ws['total']} "
            f"| {ws['done_effort']}/{ws['total_effort']} pts |"
        )
    return "\n".join(rows)


def render_detail_section(ws: dict, sub_issues: list) -> str:
    """Render the detailed sub-issue table for one workstream."""
    # Summary line
    in_prog = ws["in_progress_count"]
    triage = ws["triage_count"]
    other = ws["total"] - ws["done_count"] - in_prog - triage
    parts = [f"**Sub-issues:** {ws['total']}"]
    if ws["done_count"]:
        parts.append(f"**Done:** {ws['done_count']}")
    if in_prog:
        parts.append(f"**In Progress:** {in_prog}")
    if triage:
        parts.append(f"**Triage:** {triage}")
    if other:
        parts.append(f"**Other:** {other}")
    summary = " | ".join(parts)

    lines = [
        f"### {ws['icon']} {ws['name']}",
        "",
        f"{summary}  ",
        f"**Est. Effort:** {ws['done_effort']}/{ws['total_effort']} pts completed",
        "",
        "| Issue | Title | Status | Priority | Estimate |",
        "|-------|-------|--------|----------|----------|",
    ]

    for si in sorted(sub_issues, key=lambda x: x.get("identifier") or x.get("id") or ""):
        ident = si.get("identifier") or si.get("id") or ""
        title = si.get("title") or ""
        state = si.get("state")
        if isinstance(state, dict):
            state_type = state.get("type", "triage")
            state_name = state.get("name", "?")
        else:
            state_type = si.get("statusType", "triage")
            state_name = si.get("status", "?")

        priority_raw = si.get("priority")
        priority = priority_raw.get("value", 0) if isinstance(priority_raw, dict) else (priority_raw or 0)
        estimate_raw = si.get("estimate")
        estimate = estimate_raw.get("value", 0) if isinstance(estimate_raw, dict) else (estimate_raw or 0)

        # Status emoji
        if state_type in DONE_STATE_TYPES:
            status_emoji = "\u2705"
        elif state_type in IN_PROGRESS_STATE_TYPES:
            status_emoji = "\U0001f3c3"
        elif state_type == "canceled":
            status_emoji = "\u274c"
        else:
            status_emoji = "\u23f3"

        # Priority emoji
        pri_emoji = {1: "\U0001f534", 2: "\U0001f7e1", 3: "\U0001f7e2", 0: "\u26ab"}.get(priority, "\u26ab")

        # Truncate title to fit table
        title_display = title[:65]

        lines.append(f"| {ident} | {title_display} | {status_emoji} {state_name} | {pri_emoji} | {estimate} |")

    return "\n".join(lines)


def generate_dashboard_content(
    all_issues: list[dict],
    workstreams: dict | None = None,
    workstream_order: list[str] | None = None,
    project_name: str = "Enterprise Readiness Program",
    custom_view_url: str = DEFAULT_CUSTOM_VIEW_URL,
    epic_id: str = DEFAULT_EPIC_ID,
    audit_tracker_id: str = DEFAULT_AUDIT_TRACKER_ID,
    now_str: str | None = None,
) -> tuple[str, list[dict], dict]:
    """Pure helper to generate dashboard markdown and workstream stats from issue list."""
    ws_dict = workstreams or DEFAULT_WORKSTREAMS
    ws_order = workstream_order or list(ws_dict.keys())

    # Build parent → sub-issue map
    sub_issues_by_parent: dict[str, list[dict]] = {}
    parent_map: dict[str, dict] = {}

    for issue in all_issues:
        ident = issue.get("identifier") or issue.get("id")
        parent = issue.get("parent")
        pid = None
        if isinstance(parent, dict):
            pid = parent.get("identifier") or parent.get("id")
        elif isinstance(parent, str):
            pid = parent
        elif issue.get("parentId"):
            pid = issue.get("parentId")

        if pid:
            if pid not in sub_issues_by_parent:
                sub_issues_by_parent[pid] = []
            sub_issues_by_parent[pid].append(issue)
        elif ident:
            parent_map[ident] = issue
            if issue.get("id") and issue["id"] != ident:
                parent_map[issue["id"]] = issue

    ws_entries = []
    all_detail_sections = []

    total_done = 0
    total_sub_issues = 0
    total_done_effort = 0.0
    total_effort = 0.0

    def _get_state_type(k: dict) -> str:
        st = k.get("state")
        if isinstance(st, dict):
            return st.get("type", "triage")
        return k.get("statusType", "triage")

    def _get_estimate(k: dict) -> int | float:
        est = k.get("estimate")
        if isinstance(est, dict):
            return est.get("value", 0) or 0
        return est or 0

    for ws_ident in ws_order:
        if ws_ident not in ws_dict:
            continue

        name, priority, icon, pri_emoji = ws_dict[ws_ident]
        parent = parent_map.get(ws_ident)
        if not parent:
            continue

        p_key = parent.get("id") or ws_ident
        kids = sub_issues_by_parent.get(p_key, [])
        if not kids and ws_ident in sub_issues_by_parent:
            kids = sub_issues_by_parent[ws_ident]

        done_count = sum(1 for k in kids if _get_state_type(k) in DONE_STATE_TYPES)
        in_progress_count = sum(1 for k in kids if _get_state_type(k) in IN_PROGRESS_STATE_TYPES)
        triage_count = sum(1 for k in kids if _get_state_type(k) == "triage")
        total = len(kids)

        done_effort = sum(_get_estimate(k) for k in kids if _get_state_type(k) in DONE_STATE_TYPES)
        total_effort_ws = sum(_get_estimate(k) for k in kids)

        total_done += done_count
        total_sub_issues += total
        total_done_effort += done_effort
        total_effort += total_effort_ws

        ws_entry = {
            "ident": ws_ident,
            "name": name,
            "priority": priority,
            "priority_label": PRIORITY_LABELS.get(priority, "Unknown"),
            "priority_emoji": pri_emoji,
            "icon": icon,
            "total": total,
            "done_count": done_count,
            "in_progress_count": in_progress_count,
            "triage_count": triage_count,
            "done_effort": done_effort,
            "total_effort": total_effort_ws,
            "progress_bar": progress_bar(done_count, total),
        }
        ws_entries.append(ws_entry)

        detail = render_detail_section(ws_entry, kids)
        all_detail_sections.append(detail)

    epic = parent_map.get(epic_id)
    epic_status = (epic.get("state") or {}).get("name", "Triage") if epic else "?"

    audit_issue = [i for i in all_issues if i.get("identifier") == audit_tracker_id]
    audit_status = (audit_issue[0].get("state") or {}).get("name", "Triage") if audit_issue else "?"

    now = now_str or datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    if total_done == 0 and sum(int(ws.get("in_progress_count", 0)) for ws in ws_entries) == 0:
        banner = (
            "> **\U0001f504 All sub-issues are in Triage \u2014 execution has not yet begun.**\n"
            "> The 0% completion across all workstreams is accurate for this starting state. "
            "Work begins with PIX-4126 (Penetration Testing \u2014 Urgent priority) as the first priority sprint.\n"
        )
    else:
        banner = ""

    overview_table = render_workstream_table(ws_entries)
    detail_sections = "\n\n".join(all_detail_sections)

    dashboard = f"""# {project_name} \u2014 Dashboard

**Generated:** {now}
**Project:** {project_name}
**Linear View:** [\U0001f517 Workstream Dashboard]({custom_view_url})

{banner}---

## Overview

| Metric | Value |
|--------|-------|
| Total Issues | {len(all_issues)} |
| Workstreams | {len(ws_entries)} |
| Completed Sub-Issues | {total_done}/{total_sub_issues} |
| Total Estimated Effort | {total_effort} pts (completed: {total_done_effort} pts) |

---

## Workstream Progress

| Priority | Workstream | Progress | Completed | Est. Effort |
|----------|------------|----------|-----------|-------------|
{overview_table}

---

## Workstream Details

{detail_sections}

---

## EPIC: Enterprise Readiness

**EPIC: Enterprise Readiness \u2014 Close All Enterprise Gaps** \u2014 Status: {epic_status}

Tracks the overall closure of all 6 enterprise gaps.

---

## Quarterly Audit Tracker

**Quarterly Workspace Audit \u2014 Linear Hygiene Check** \u2014 Status: {audit_status}

Next scheduled audit: **2026-10-29**

---

## Navigation

- **Linear Project:** {project_name} (`PIX` team)
- **Linear Custom View:** [\U0001f517 Workstream Dashboard]({custom_view_url})
- **Initiative:** [Enterprise Readiness](https://linear.app/pixelated/initiative/enterprise-readiness)
- **Initial Audit Report:** [./linear_audit.md](./linear_audit.md)
- **Final Snapshot:** [./linear_audit_final.md](./linear_audit_final.md)
- **Scripts:** `./fetch_issues.py`, `./run_audit.py`, `./remediate.py`, `./refresh_dashboard.py`

---

*Dashboard auto-generated by `refresh_dashboard.py`. Refresh by re-running:*
*`python3 docs/linear-audit/refresh_dashboard.py`*
"""

    summary_stats = {
        "total_issues": len(all_issues),
        "total_done": total_done,
        "total_sub_issues": total_sub_issues,
        "total_done_effort": total_done_effort,
        "total_effort": total_effort,
    }

    return dashboard, ws_entries, summary_stats
