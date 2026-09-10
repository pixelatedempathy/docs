#!/usr/bin/env python3
"""
refresh_dashboard.py — Live dashboard generator for Enterprise Readiness Program.

Fetches all issues from the Linear project, computes completion stats per
workstream, and regenerates docs/linear-audit/dashboard.md with live data.

Markdown rendering lives in ``dashboard_render.py``; this module keeps the API
fetch and CLI wiring (and re-exports the render helpers for backward
compatibility).

Usage:
    export LINEAR_API_KEY=lin_api_...
    python3 refresh_dashboard.py
"""

import argparse
import os
import sys
from pathlib import Path

import requests
from dashboard_render import (
    DEFAULT_CUSTOM_VIEW_URL,
    DEFAULT_WORKSTREAMS,
    generate_dashboard_content,
    progress_bar,
)

__all__ = [
    "API_URL",
    "CUSTOM_VIEW_URL",
    "DASHBOARD_PATH",
    "PROJECT_ID",
    "WORKSTREAMS",
    "fetch_project_issues",
    "generate_dashboard_content",
    "gql",
    "main",
    "progress_bar",
]

# ── Defaults & Constants ──────────────────────────────────────────────────────

DEFAULT_API_URL = "https://api.linear.app/graphql"
DEFAULT_PROJECT_ID = "29c133a2-9195-42d3-b53e-31154d47ea7d"
DEFAULT_DASHBOARD_PATH = Path(__file__).resolve().parent / "dashboard.md"

# Module-level aliases for backwards compatibility
API_URL = DEFAULT_API_URL
PROJECT_ID = DEFAULT_PROJECT_ID
CUSTOM_VIEW_URL = DEFAULT_CUSTOM_VIEW_URL
DASHBOARD_PATH = str(DEFAULT_DASHBOARD_PATH)
WORKSTREAMS = DEFAULT_WORKSTREAMS


# ── API helpers ───────────────────────────────────────────────────────────────


def gql(query: str, api_key: str | None = None, api_url: str = DEFAULT_API_URL) -> dict | None:
    """Execute a GraphQL query against the Linear API with retry."""
    if not api_url.startswith(("https://", "http://")):
        raise ValueError("Invalid URL scheme: only https/http supported")
    key = api_key or os.environ.get("LINEAR_API_KEY", "")
    for attempt in range(3):
        try:
            resp = requests.post(
                api_url,
                json={"query": query},
                headers={"Content-Type": "application/json", "Authorization": key},
                timeout=30,
            )
            result = resp.json()
            if "errors" in result:
                print(f"  API error: {result['errors']}", file=sys.stderr)
                return None
            return result
        except Exception as e:
            if attempt < 2:
                print(f"  Retry {attempt + 1} after: {e}", file=sys.stderr)
            else:
                print(f"  Failed after 3 retries: {e}", file=sys.stderr)
                return None
    return None


def fetch_project_issues(
    project_id: str = DEFAULT_PROJECT_ID,
    api_key: str | None = None,
    api_url: str = DEFAULT_API_URL,
    max_pages: int | None = 100,
) -> list[dict]:
    """Fetch all issues in the Linear project."""
    all_issues = []
    cursor = None
    page = 0

    while True:
        page += 1
        if max_pages is not None and page > max_pages:
            print(f"Reached maximum page limit ({max_pages}), stopping.", file=sys.stderr)
            break

        after = f', after: "{cursor}"' if cursor else ""
        query = f"""{{
            issues(first: 50{after}, filter: {{
                project: {{ id: {{ eq: "{project_id}" }} }}
            }}) {{
                nodes {{
                    id identifier title priority estimate
                    state {{ id name type }}
                    parent {{ id identifier title }}
                    completedAt
                }}
                pageInfo {{ hasNextPage endCursor }}
            }}
        }}"""
        result = gql(query, api_key=api_key, api_url=api_url)
        if not result or "data" not in result:
            print(f"  Error on page {page}", file=sys.stderr)
            break

        nodes = result["data"]["issues"]["nodes"]
        page_info = result["data"]["issues"]["pageInfo"]
        all_issues.extend(nodes)

        if not page_info["hasNextPage"]:
            break
        cursor = page_info["endCursor"]

    return all_issues


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Generate live dashboard for Linear project")
    parser.add_argument(
        "--api-key",
        default=os.environ.get("LINEAR_API_KEY", ""),
        help="Linear API key (or set LINEAR_API_KEY)",
    )
    parser.add_argument(
        "--project-id",
        default=os.environ.get("LINEAR_PROJECT_ID", DEFAULT_PROJECT_ID),
        help="Linear project ID (or set LINEAR_PROJECT_ID)",
    )
    parser.add_argument(
        "--api-url",
        default=os.environ.get("LINEAR_API_URL", DEFAULT_API_URL),
        help="Linear GraphQL API URL",
    )
    parser.add_argument(
        "--custom-view-url",
        default=os.environ.get("LINEAR_CUSTOM_VIEW_URL", DEFAULT_CUSTOM_VIEW_URL),
        help="Linear Custom View URL",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_DASHBOARD_PATH),
        help="Output dashboard markdown path",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=100,
        help="Max pages to fetch from Linear (default: 100)",
    )
    args = parser.parse_args()

    if not args.api_key:
        print("ERROR: LINEAR_API_KEY environment variable or --api-key must be set.", file=sys.stderr)
        sys.exit(1)

    print("=" * 60, file=sys.stderr)
    print("REFRESH DASHBOARD: Enterprise Readiness Program", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    # 1. Fetch data
    print(f"Fetching issues for project {args.project_id}...", file=sys.stderr)
    all_issues = fetch_project_issues(
        project_id=args.project_id,
        api_key=args.api_key,
        api_url=args.api_url,
        max_pages=args.max_pages,
    )
    print(f"  {len(all_issues)} issues found", file=sys.stderr)

    if not all_issues:
        print("ERROR: No issues found in project!", file=sys.stderr)
        sys.exit(1)

    # 2. Generate dashboard markdown
    dashboard, ws_entries, stats = generate_dashboard_content(
        all_issues=all_issues,
        workstreams=DEFAULT_WORKSTREAMS,
        custom_view_url=args.custom_view_url,
    )

    # 3. Write to file
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(dashboard)

    print(f"\n\U0001f4be Dashboard written to {output_path}", file=sys.stderr)
    completed_line = (
        f"   {stats['total_done']}/{stats['total_sub_issues']} sub-issues completed "
        f"({stats['total_done_effort']}/{stats['total_effort']} pts)"
    )
    print(completed_line, file=sys.stderr)

    # Summary
    print("\n=== WORKSTREAM SUMMARY ===", file=sys.stderr)
    for ws in ws_entries:
        bar = ws["progress_bar"]
        summary_line = (
            f"  {ws['icon']} {ws['name']:25s} {bar:15s}  "
            f"{ws['done_count']:2d}/{ws['total']:2d}  "
            f"({ws['done_effort']}/{ws['total_effort']} pts)"
        )
        print(summary_line, file=sys.stderr)


if __name__ == "__main__":
    main()
