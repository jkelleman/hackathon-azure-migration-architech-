#!/usr/bin/env python3
"""
invoke_duo_agent.py
───────────────────
Calls the GitLab Duo Chat / Agent API with the PushToBicep Architect
prompt template, sending changed infrastructure files as input.

Returns the AI-generated Bicep code + migration summary to stdout,
and writes the .bicep file(s) to the `generated/` directory.

Environment variables (set in GitLab CI/CD Variables):
  GITLAB_API_TOKEN   — Project or personal access token with `api` scope
  CI_PROJECT_ID      — Auto-set by GitLab CI
  CI_SERVER_URL      — Auto-set by GitLab CI

Usage:
  python scripts/invoke_duo_agent.py --files "main.tf,Dockerfile" --outdir generated/
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import textwrap
import urllib.error
import urllib.request
from pathlib import Path


# ── Config ─────────────────────────────────────────────────────────────────
GITLAB_URL  = os.getenv("CI_SERVER_URL", "https://gitlab.com")
PROJECT_ID  = os.getenv("CI_PROJECT_ID", "")
API_TOKEN   = os.getenv("GITLAB_API_TOKEN", "")

HEADERS = {
    "PRIVATE-TOKEN": API_TOKEN,
    "Content-Type": "application/json",
}

# Load the prompt template at import time so it can be interpolated
PROMPT_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "prompts" / "azure_migration_architect.md"


# ── Helpers ────────────────────────────────────────────────────────────────
def _load_prompt_template() -> str:
    """Read the markdown prompt template from disk."""
    if PROMPT_TEMPLATE_PATH.exists():
        return PROMPT_TEMPLATE_PATH.read_text()
    # Fallback minimal prompt if file is missing
    return textwrap.dedent("""\
        You are the PushToBicep Architect agent.
        Convert the following infrastructure code to Azure Bicep.
        Include a cost estimate table.

        {{original_code}}
    """)


def _build_prompt(original_code: str) -> str:
    """Interpolate the prompt template with the actual code."""
    template = _load_prompt_template()
    prompt = template.replace("{{original_code}}", original_code)
    prompt = prompt.replace(
        "{{project_context}}",
        json.dumps({
            "project_id": PROJECT_ID,
            "server_url": GITLAB_URL,
        }),
    )
    return prompt


def _call_duo_chat(prompt: str) -> str:
    """
    Call the GitLab Duo Chat API (or Agent Platform API) and return the
    AI-generated text response.

    Endpoint: POST /api/v4/chat/completions   (GitLab 17.x+)
    Docs: https://docs.gitlab.com/ee/api/duo_chat.html
    """
    url = f"{GITLAB_URL}/api/v4/chat/completions"
    body = json.dumps({
        "content": prompt,
        "resource_type": "project",
        "resource_id": PROJECT_ID,
    }).encode()

    req = urllib.request.Request(url, data=body, headers=HEADERS, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
            # The response shape may vary; handle common formats
            if isinstance(data, dict):
                return data.get("choices", [{}])[0].get("message", {}).get("content", "") \
                    or data.get("response", "") \
                    or data.get("content", "") \
                    or json.dumps(data)
            return str(data)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode() if exc.fp else ""
        print(f"Duo Chat API {exc.code}: {detail}", file=sys.stderr)
        sys.exit(1)


def _extract_bicep(response_text: str) -> str:
    """
    Extract the Bicep code block from the AI response.
    Looks for ```bicep ... ``` fenced blocks.
    """
    pattern = r"```bicep\s*\n(.*?)```"
    match = re.search(pattern, response_text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Fallback: return everything after "## Generated Bicep Code"
    marker = "## Generated Bicep Code"
    idx = response_text.find(marker)
    if idx != -1:
        return response_text[idx + len(marker):].strip()
    return response_text


def _extract_summary(response_text: str) -> str:
    """
    Extract everything before the Bicep code block to use as the
    MR description (Migration Summary + Cost Estimate tables).
    """
    marker = "## Generated Bicep Code"
    idx = response_text.find(marker)
    if idx != -1:
        return response_text[:idx].strip()
    return ""


# ── Main ───────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Invoke GitLab Duo for Azure migration")
    parser.add_argument(
        "--files",
        required=True,
        help="Comma-separated list of changed infrastructure files",
    )
    parser.add_argument(
        "--outdir",
        default="generated",
        help="Directory to write generated .bicep files (default: generated/)",
    )
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    changed_files = [f.strip() for f in args.files.split(",") if f.strip()]
    if not changed_files:
        print("No infrastructure files to process.")
        return

    # ── Collect all changed file contents into one prompt ──────────────
    code_sections: list[str] = []
    for fpath in changed_files:
        p = Path(fpath)
        if p.exists():
            code_sections.append(f"### File: {fpath}\n```\n{p.read_text()}\n```")
        else:
            print(f"Warning: {fpath} not found, skipping.", file=sys.stderr)

    if not code_sections:
        print("No valid files found to process.")
        return

    original_code = "\n\n".join(code_sections)
    prompt = _build_prompt(original_code)

    print(f"Sending {len(changed_files)} file(s) to GitLab Duo ({len(prompt)} chars)…")
    response = _call_duo_chat(prompt)

    # ── Write outputs ─────────────────────────────────────────────────
    bicep_code = _extract_bicep(response)
    summary = _extract_summary(response)

    bicep_path = outdir / "main.bicep"
    bicep_path.write_text(bicep_code + "\n")
    print(f"  ✓ Wrote {bicep_path} ({len(bicep_code)} chars)")

    summary_path = outdir / "migration_summary.md"
    summary_path.write_text(summary + "\n")
    print(f"  ✓ Wrote {summary_path}")

    # Also write the full raw response for debugging
    (outdir / "duo_response_raw.md").write_text(response + "\n")
    print(f"  ✓ Wrote {outdir / 'duo_response_raw.md'}")


if __name__ == "__main__":
    main()
