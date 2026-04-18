#!/usr/bin/env python3
"""
sync_jp_m3u.py
Fetches jp.m3u from GitFlic and syncs it to a GitHub repository.

Usage:
    python sync_jp_m3u.py

Required environment variables:
    GITHUB_TOKEN   - Personal access token with repo write access
    GITHUB_REPO    - Target repo in "owner/repo" format  (e.g. "myuser/myrepo")
    GITHUB_PATH    - Path inside the repo to write the file (e.g. "jp.m3u" or "iptv/jp.m3u")
    GITHUB_BRANCH  - Branch to commit to (default: "main")
"""

import os
import sys
import base64
import hashlib
import urllib.request
import urllib.error
import json

# ── Configuration ────────────────────────────────────────────────────────────

SOURCE_URL    = "https://gitflic.ru/project/utako/utako/blob/raw?file=jp.m3u"
GITHUB_API    = "https://api.github.com"

GITHUB_TOKEN  = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO   = os.environ.get("GITHUB_REPO", "")          # e.g. "myuser/myrepo"
GITHUB_PATH   = os.environ.get("GITHUB_PATH", "jp.m3u")   # path inside repo
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")

COMMIT_MSG    = "chore: sync jp.m3u from GitFlic"

# ── Helpers ──────────────────────────────────────────────────────────────────

def _github_request(method: str, endpoint: str, payload: dict | None = None) -> dict:
    url = f"{GITHUB_API}{endpoint}"
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "sync-jp-m3u/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise RuntimeError(f"GitHub API {method} {url} → {exc.code}: {body}") from exc


def fetch_source() -> bytes:
    """Download the file from GitFlic."""
    print(f"[fetch] {SOURCE_URL}")
    req = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "sync-jp-m3u/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        content = resp.read()
    print(f"[fetch] {len(content):,} bytes received")
    return content


def get_github_file() -> tuple[str | None, str | None]:
    """
    Return (sha, content_b64) of the existing file in the repo, or (None, None)
    if it doesn't exist yet.
    """
    endpoint = f"/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}?ref={GITHUB_BRANCH}"
    try:
        data = _github_request("GET", endpoint)
        return data["sha"], data["content"]  # content is base64 + newlines
    except RuntimeError as exc:
        if "404" in str(exc):
            return None, None
        raise


def push_to_github(new_content: bytes, existing_sha: str | None) -> None:
    """Create or update the file in the GitHub repo."""
    encoded = base64.b64encode(new_content).decode()
    payload: dict = {
        "message": COMMIT_MSG,
        "content": encoded,
        "branch": GITHUB_BRANCH,
    }
    if existing_sha:
        payload["sha"] = existing_sha

    endpoint = f"/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}"
    result = _github_request("PUT", endpoint, payload)
    commit_url = result.get("commit", {}).get("html_url", "(unknown)")
    print(f"[github] committed → {commit_url}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    # Validate env
    missing = [v for v in ("GITHUB_TOKEN", "GITHUB_REPO") if not os.environ.get(v)]
    if missing:
        sys.exit(f"ERROR: missing environment variables: {', '.join(missing)}")

    # 1. Fetch from GitFlic
    new_content = fetch_source()

    # 2. Get current state from GitHub
    existing_sha, existing_b64 = get_github_file()

    if existing_b64:
        # Strip newlines that GitHub injects into base64
        existing_content = base64.b64decode(existing_b64.replace("\n", ""))
        if hashlib.sha256(existing_content).digest() == hashlib.sha256(new_content).digest():
            print("[sync] file is already up to date — nothing to do")
            return
        print("[sync] content changed, updating …")
    else:
        print("[sync] file does not exist in repo yet, creating …")

    # 3. Push update
    push_to_github(new_content, existing_sha)
    print("[sync] done ✓")


if __name__ == "__main__":
    main()
