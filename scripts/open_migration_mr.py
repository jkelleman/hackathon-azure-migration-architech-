#!/usr/bin/env python3
"""
open_migration_mr.py
────────────────────
Automates the GitLab side of the PushToBicep Architect agent:

  1. create-branch  → Creates a `migrate-to-azure` branch from HEAD.
  2. commit         → Commits generated .bicep files to that branch.
  3. open-mr        → Opens a Merge Request with the migration summary.

Requires the environment variables set in agent-config.yml / CI Variables:
  GITLAB_API_TOKEN, CI_PROJECT_ID, CI_COMMIT_SHA, CI_DEFAULT_BRANCH

Usage (called automatically by the agent, or manually for testing):
    python scripts/open_migration_mr.py --action create-branch
    python scripts/open_migration_mr.py --action commit --file infra/main.bicep --content-file generated/main.bicep
    python scripts/open_migration_mr.py --action open-mr --title "Azure Migration" --description "## Summary ..."
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


# ── Configuration ──────────────────────────────────────────────────────────
GITLAB_URL = os.getenv("CI_SERVER_URL", "https://gitlab.com")
PROJECT_ID = os.getenv("CI_PROJECT_ID", "")
API_TOKEN  = os.getenv("GITLAB_API_TOKEN", "")
SOURCE_SHA = os.getenv("CI_COMMIT_SHA", "")
DEFAULT_BR = os.getenv("CI_DEFAULT_BRANCH", "main")

MIGRATION_BRANCH = "migrate-to-azure"
API_BASE = f"{GITLAB_URL}/api/v4/projects/{PROJECT_ID}"

HEADERS = {
    "PRIVATE-TOKEN": API_TOKEN,
    "Content-Type": "application/json",
}


# ── Helpers ────────────────────────────────────────────────────────────────
def _api(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    max_retries: int = 3,
    timeout: int = 30,
) -> dict:
    """Thin wrapper around the GitLab REST API (stdlib only, no requests).
    Retries transient errors (429, 5xx) with exponential backoff."""
    url = f"{API_BASE}/{path}"
    data = json.dumps(body).encode() if body else None

    for attempt in range(1, max_retries + 1):
        req = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode() if exc.fp else ""
            retryable = exc.code in (429, 500, 502, 503, 504)
            if retryable and attempt < max_retries:
                wait = 2 ** attempt
                print(f"GitLab API {exc.code} (attempt {attempt}/{max_retries}), retrying in {wait}s…", file=sys.stderr)
                time.sleep(wait)
                continue
            # Return error detail so callers can inspect the code
            if exc.code == 409:
                return {"_conflict": True, "_status": 409, "_detail": detail}
            print(f"GitLab API {exc.code}: {detail}", file=sys.stderr)
            sys.exit(1)
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt < max_retries:
                wait = 2 ** attempt
                print(f"Network error (attempt {attempt}/{max_retries}): {exc}, retrying in {wait}s…", file=sys.stderr)
                time.sleep(wait)
                continue
            print(f"Network error after {max_retries} attempts: {exc}", file=sys.stderr)
            sys.exit(1)
    sys.exit(1)


def create_branch() -> None:
    """Create the migration branch from the triggering commit.
    Gracefully handles the case where the branch already exists (409)."""
    print(f"Creating branch '{MIGRATION_BRANCH}' from {SOURCE_SHA[:8]}…")
    result = _api("POST", "repository/branches", {
        "branch": MIGRATION_BRANCH,
        "ref": SOURCE_SHA or DEFAULT_BR,
    })
    if result.get("_conflict"):
        print(f"  ℹ Branch '{MIGRATION_BRANCH}' already exists — continuing.")
        return
    print(f"  ✓ Branch created: {result.get('web_url', result.get('name'))}")


def commit_file(file_path: str, content: str, message: str | None = None) -> None:
    """Commit a single generated file to the migration branch.
    Uses 'create' first; falls back to 'update' if the file already exists."""
    msg = message or f"feat: add Azure Bicep template — {file_path}"
    print(f"Committing '{file_path}' to '{MIGRATION_BRANCH}'…")
    result = _api("POST", "repository/commits", {
        "branch": MIGRATION_BRANCH,
        "commit_message": msg,
        "actions": [
            {
                "action": "create",
                "file_path": file_path,
                "content": content,
            }
        ],
    })
    # If the file already exists, retry with 'update' action
    if result.get("_conflict"):
        print(f"  ℹ File already exists, updating instead…")
        result = _api("POST", "repository/commits", {
            "branch": MIGRATION_BRANCH,
            "commit_message": msg.replace("add", "update"),
            "actions": [
                {
                    "action": "update",
                    "file_path": file_path,
                    "content": content,
                }
            ],
        })
    print(f"  ✓ Commit {result.get('id', '?')[:8]}: {msg}")


def open_merge_request(title: str, description: str) -> None:
    """Open a Merge Request from the migration branch → default branch."""
    print(f"Opening Merge Request → '{DEFAULT_BR}'…")
    result = _api("POST", "merge_requests", {
        "source_branch": MIGRATION_BRANCH,
        "target_branch": DEFAULT_BR,
        "title": title,
        "description": description,
        "remove_source_branch": True,
        "labels": "azure-migration,automated,duo-agent",
    })
    print(f"  ✓ MR !{result.get('iid')}: {result.get('web_url')}")


# ── CLI ────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        description="GitLab API automation for PushToBicep Architect agent"
    )
    parser.add_argument(
        "--action",
        required=True,
        choices=["create-branch", "commit", "open-mr"],
        help="Which step of the pipeline to execute",
    )
    parser.add_argument("--file", help="File path for commit action")
    parser.add_argument("--content", help="File content for commit action (inline)")
    parser.add_argument("--content-file", help="Path to a local file whose content to commit (preferred over --content)")
    parser.add_argument("--title", help="MR title for open-mr action")
    parser.add_argument("--description", help="MR description (Markdown) for open-mr action")

    args = parser.parse_args()

    # Validate required env vars
    if not PROJECT_ID or not API_TOKEN:
        print(
            "ERROR: CI_PROJECT_ID and GITLAB_API_TOKEN must be set.\n"
            "Add them as CI/CD Variables in your GitLab project settings.",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.action == "create-branch":
        create_branch()

    elif args.action == "commit":
        if not args.file:
            parser.error("--file is required for the 'commit' action")
        # Prefer --content-file over --content to avoid shell expansion issues
        content = None
        if args.content_file:
            content = Path(args.content_file).read_text()
        elif args.content:
            content = args.content
        else:
            parser.error("--content or --content-file is required for the 'commit' action")
        commit_file(args.file, content)

    elif args.action == "open-mr":
        title = args.title or "🏗️ Azure Migration: auto-generated Bicep templates"
        desc = args.description or (
            "## PushToBicep Architect — Automated MR\n\n"
            "This Merge Request was created automatically by the "
            "GitLab Duo **PushToBicep Architect** agent.\n\n"
            "Please review the generated `.bicep` files and the "
            "cost estimate before merging."
        )
        open_merge_request(title, desc)


if __name__ == "__main__":
    main()
