"""Mock GitLab server + end-to-end test untuk scripts/gitlab_stats.py.

Mock math (relatif terhadap now):
- MR: page1 = 100 item, page2 = 1 item  -> total 101 (uji pagination)
- Issues: 3 item (1 halaman)
- Push events: wk0 x3 (usia 0,1,2 hr), wk1 x3 (7,8,9), wk3 x3 (21,22,23), wk7 x1 (49) = 10 event
  -> commits 30h = 9 event x 4 = 36
  -> bucket mingguan: idx7=3, idx6=3, idx4=3, idx0=1 (4 bucket non-zero)
"""
import json
import os
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

NOW = datetime.now(timezone.utc)


def iso(age_days):
    return (NOW - timedelta(days=age_days)).strftime("%Y-%m-%dT%H:%M:%SZ")


EVENTS = []
for wk, n in ((0, 3), (1, 3), (3, 3), (7, 1)):
    for i in range(n):
        EVENTS.append({"created_at": iso(wk * 7 + i), "action": "pushed",
                       "push_data": {"commit_count": 4}})

PAGES = {
    "/api/v4/merge_requests": [[{"id": i} for i in range(100)], [{"id": 99}]],
    "/api/v4/issues": [[{"id": i} for i in range(3)]],
    "/api/v4/events": [EVENTS],
}
SINGLE = {"/api/v4/user": {"id": 42, "username": "kantor-me"}}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.headers.get("PRIVATE-TOKEN") != "test-token":
            self.send_response(401)
            self.end_headers()
            return
        base, _, qs = self.path.partition("?")
        page = int(parse_qs(qs).get("page", ["1"])[0])
        rows = PAGES.get(base)
        if rows is None:
            single = SINGLE.get(base)
            if single is not None:
                body = json.dumps(single).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps(rows[page - 1] if page - 1 < len(rows) else []).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


srv = HTTPServer(("127.0.0.1", 0), Handler)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

os.environ.update({
    "GITLAB_URL": f"http://127.0.0.1:{port}",
    "GITLAB_TOKEN": "test-token",
    "GITHUB_WORKSPACE": os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
    "TZ_OFFSET": "7",
})

here = os.path.dirname(os.path.abspath(__file__))
r = subprocess.run([sys.executable, os.path.join(here, "..", "scripts", "gitlab_stats.py")],
                   capture_output=True, text=True, env=os.environ)
print(r.stdout)
print(r.stderr, file=sys.stderr)
print("exit:", r.returncode)

readme = open(os.path.join(here, "..", "README.md"), encoding="utf-8").read()
ok = True
if "<!-- GITLAB_STATS:START -->" not in readme:
    print("FAIL: marker START tidak muncul"); ok = False
if "**101**" not in readme:
    print("FAIL: angka MR (harus 101, 2 halaman digabung) tidak benar"); ok = False
if "**3**" not in readme:
    print("FAIL: angka issues (harus 3) tidak benar"); ok = False
if "**36**" not in readme:
    print("FAIL: angka commits (harus 36) tidak benar"); ok = False
spark_line = next((l for l in readme.splitlines() if "Aktivitas 8 minggu" in l), "")
nonzero = sum(1 for c in spark_line if c in "▂▃▄▅▆▇█")
if nonzero != 4:
    print("FAIL: sparkline harus 4 bucket non-zero:", spark_line); ok = False
if "nusatek" in readme.lower() or "kantor-me" in readme:
    print("FAIL: bocor identitas kantor!"); ok = False
if "## 📫 Kontak" not in readme:
    print("FAIL: section Kontak hilang"); ok = False
print("RESULT:", "ALL PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
