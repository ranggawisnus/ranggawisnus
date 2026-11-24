#!/usr/bin/env python3
"""gitlab_stats.py — aggregate personal stats from a self-hosted (company) GitLab
into the GitHub profile README, between <!-- GITLAB_STATS:START --> markers.

Privacy: renders AGGREGATE numbers only (MRs merged, issues closed, commits,
weekly sparkline). No project names, no company identity, no repo URLs.

Env:
  GITLAB_URL   e.g. https://repo.nusatek.id (no trailing slash)
  GITLAB_TOKEN Personal Access Token with read_api scope
  TZ_OFFSET    hours offset for "updated" timestamp display (default 7 = WIB)

stdlib-only. Exit 0 = README updated or already current; exit 2 = config error.
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

README = os.environ.get("GITHUB_WORKSPACE", ".") + "/README.md"
START = "<!-- GITLAB_STATS:START -->"
END = "<!-- GITLAB_STATS:END -->"

GITLAB_URL = os.environ.get("GITLAB_URL", "").rstrip("/")
GITLAB_TOKEN = os.environ.get("GITLAB_TOKEN", "")
TZ = timezone(timedelta(hours=int(os.environ.get("TZ_OFFSET", "7"))))


def die(msg, code=2):
    print(f"::error::{msg}", file=sys.stderr)
    sys.exit(code)


def api(path, **params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{GITLAB_URL}/api/v4{path}" + (f"?{q}" if q else "")
    req = urllib.request.Request(url, headers={"PRIVATE-TOKEN": GITLAB_TOKEN,
                                               "User-Agent": "profile-stats"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def paged(path, max_pages=25, **params):
    """Paginate using x-next-page header (params mutated with page)."""
    out, page = [], 1
    while page <= max_pages:
        rows = api(path, page=page, per_page=100, **params)
        out.extend(rows)
        nxt = None
        # headers not returned by helper; detect short page instead
        if len(rows) < 100:
            break
        page += 1
    return out


def main():
    if not GITLAB_URL or not GITLAB_TOKEN:
        print("::warning::GITLAB_URL / GITLAB_TOKEN belum diset (repo secrets) — skip")
        sys.exit(0)

    me = api("/user")
    uid, uname = me["id"], me.get("username", "?")
    print(f"authenticated as {uname} (id={uid})")

    now = datetime.now(timezone.utc)
    d90 = (now - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ts30 = int((now - timedelta(days=30)).timestamp())
    ts56 = int((now - timedelta(days=56)).timestamp())

    # --- aggregate counts (90 days) ---
    mrs = paged("/merge_requests", scope="all", state="merged",
                author_id=uid, updated_after=d90)
    issues = paged("/issues", scope="all", state="closed",
                   author_id=uid, updated_after=d90)

    # --- commits & weekly series via push events (56 days) ---
    events = paged("/events", action="pushed", after=ts56)
    commits30 = sum(
        (e.get("push_data") or {}).get("commit_count") or 0
        for e in events
        if datetime.fromisoformat(e["created_at"].replace("Z", "+00:00")) >= now - timedelta(days=30)
    )
    # 8 weekly buckets (oldest -> newest)
    buckets = [0] * 8
    for e in events:
        t = datetime.fromisoformat(e["created_at"].replace("Z", "+00:00"))
        wk = int((now - t).total_seconds() // (7 * 86400))
        if 0 <= wk < 8:
            buckets[7 - wk] += 1

    bars = "▁▂▃▄▅▆▇█"
    peak = max(buckets) or 1
    spark = "".join(bars[min(7, round(b * 7 / peak))] for b in buckets)

    lines = [
        START,
        f"- 🔀 MR merged (90h): **{len(mrs)}**",
        f"- 🐞 Issues closed (90h): **{len(issues)}**",
        f"- ⌨️ Commits (30h): **{commits30}**",
        f"- 📈 Aktivitas 8 minggu: `{spark}`",
        f"<sub>Agregat dari GitLab internal — tanpa detail proyek. Update {now.astimezone(TZ).strftime('%d %b %Y')}.</sub>",
        END,
    ]
    section = "\n".join(lines)

    with open(README, encoding="utf-8") as f:
        txt = f.read()

    if START in txt and END in txt:
        pre = txt.split(START)[0]
        post = txt.split(END, 1)[1]
        new = pre + section + post
    elif "<!-- GITLAB_STATS -->" in txt:
        new = txt.replace("<!-- GITLAB_STATS -->", section)
    else:
        die(f"README tidak punya marker {START} / <!-- GITLAB_STATS -->")

    if new == txt:
        print("README sudah up-to-date, tidak ada perubahan")
        return

    with open(README, "w", encoding="utf-8") as f:
        f.write(new)
    print("README updated:")
    print(section)


if __name__ == "__main__":
    main()
