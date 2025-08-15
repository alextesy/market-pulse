#!/usr/bin/env python3
"""
Create GitHub issues from a JSON spec.
Usage:
  python create_gh_issues.py --repo owner/name --file issues.json [--token $GITHUB_TOKEN]
Notes:
  - Idempotent by title: skips if an issue with same title already exists.
  - Creates milestones and labels on-the-fly if missing.
  - Requires token with 'repo' scope for private repos, 'public_repo' for public repos.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

API = "https://api.github.com"


def req(method, url, token, data=None):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "issue-bulk-uploader",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        data = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"[HTTP {e.code}] {url}\n{body}", file=sys.stderr)
        if e.code == 403:
            print(
                "\nPERMISSION ERROR: Your token may not have the required scopes.",
                file=sys.stderr,
            )
            print(
                "Required scopes: 'repo' (for private repos) or 'public_repo' (for public repos)",
                file=sys.stderr,
            )
            print(
                "Create a new token at: https://github.com/settings/tokens",
                file=sys.stderr,
            )
        raise


def get_all(url, token):
    out, page = [], 1
    while True:
        resp = req("GET", f"{url}?per_page=100&page={page}", token)
        if not resp:
            break
        out.extend(resp)
        page += 1
    return out


def get_or_create_milestone(repo, token, title):
    # Try to find existing (open or closed)
    for state in ("open", "closed"):
        try:
            ms = req(
                "GET",
                f"{API}/repos/{repo}/milestones?state={state}&per_page=100",
                token,
            )
            for m in ms:
                if m["title"] == title:
                    return m["number"]
        except urllib.error.HTTPError as e:
            if e.code == 403:
                print(
                    "WARNING: Cannot access milestones due to permission error. Skipping milestone creation.",
                    file=sys.stderr,
                )
                return None
            raise
    # Create
    try:
        m = req(
            "POST",
            f"{API}/repos/{repo}/milestones",
            token,
            {"title": title, "state": "open"},
        )
        return m["number"]
    except urllib.error.HTTPError as e:
        if e.code == 403:
            print(
                f"WARNING: Cannot create milestone '{title}' due to permission error. Skipping.",
                file=sys.stderr,
            )
            return None
        raise


def get_or_create_label(repo, token, name):
    # Try to get
    try:
        l = req("GET", f"{API}/repos/{repo}/labels/{name.replace(' ', '%20')}", token)
        return l["name"]
    except urllib.error.HTTPError as e:
        if e.code == 404:
            pass  # Label doesn't exist, will create
        elif e.code == 403:
            print(
                "WARNING: Cannot access labels due to permission error. Skipping label creation.",
                file=sys.stderr,
            )
            return name
        else:
            raise
    # Create with default color
    color = "ededed"
    try:
        l = req(
            "POST", f"{API}/repos/{repo}/labels", token, {"name": name, "color": color}
        )
        return l["name"]
    except urllib.error.HTTPError as e:
        if e.code == 403:
            print(
                f"WARNING: Cannot create label '{name}' due to permission error. Skipping.",
                file=sys.stderr,
            )
            return name
        else:
            print(f"Failed to create label '{name}': {e}", file=sys.stderr)
            return name


def issue_exists(repo, token, title):
    # search issues by title (state=all)
    try:
        issues = get_all(f"{API}/repos/{repo}/issues", token)
        for i in issues:
            if "pull_request" in i:  # skip PRs
                continue
            if i["title"] == title:
                return True
        return False
    except urllib.error.HTTPError as e:
        if e.code == 403:
            print(
                "WARNING: Cannot check existing issues due to permission error. Assuming issue doesn't exist.",
                file=sys.stderr,
            )
            return False
        raise


def create_issue(repo, token, item):
    milestone_no = (
        get_or_create_milestone(repo, token, item["milestone"])
        if item.get("milestone")
        else None
    )
    labels = []
    for name in item.get("labels", []):
        labels.append(get_or_create_label(repo, token, name))
    data = {"title": item["title"], "body": item.get("body", ""), "labels": labels}
    if milestone_no:
        data["milestone"] = milestone_no
    if issue_exists(repo, token, item["title"]):
        print(f"SKIP (exists): {item['title']}")
        return
    try:
        created = req("POST", f"{API}/repos/{repo}/issues", token, data)
        print(f"CREATED #{created['number']}: {created['title']}")
    except urllib.error.HTTPError as e:
        if e.code == 403:
            print(
                f"ERROR: Cannot create issue '{item['title']}' due to permission error.",
                file=sys.stderr,
            )
            print(
                "Make sure your token has 'repo' scope for private repos or 'public_repo' for public repos.",
                file=sys.stderr,
            )
        else:
            print(
                f"ERROR: Failed to create issue '{item['title']}': {e}", file=sys.stderr
            )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="owner/repo")
    ap.add_argument("--file", required=True, help="path to issues.json")
    ap.add_argument(
        "--token",
        default=os.getenv("GITHUB_TOKEN"),
        help="GitHub token (env GITHUB_TOKEN)",
    )
    args = ap.parse_args()
    if not args.token:
        print("Missing token: set --token or GITHUB_TOKEN", file=sys.stderr)
        print("\nTo create a GitHub token:", file=sys.stderr)
        print("1. Go to https://github.com/settings/tokens", file=sys.stderr)
        print("2. Click 'Generate new token (classic)'", file=sys.stderr)
        print(
            "3. Select scopes: 'repo' (private repos) or 'public_repo' (public repos)",
            file=sys.stderr,
        )
        print(
            "4. Copy the token and set it as GITHUB_TOKEN environment variable",
            file=sys.stderr,
        )
        sys.exit(1)

    with open(args.file, "r") as f:
        items = json.load(f)

    # Pre-create labels/milestones to avoid races
    milestones = sorted(set(i.get("milestone") for i in items if i.get("milestone")))
    for m in milestones:
        get_or_create_milestone(args.repo, args.token, m)

    all_labels = sorted({l for i in items for l in i.get("labels", [])})
    for name in all_labels:
        get_or_create_label(args.repo, args.token, name)

    # Create issues
    for item in items:
        create_issue(args.repo, args.token, item)
        time.sleep(0.2)  # be gentle


if __name__ == "__main__":
    main()
