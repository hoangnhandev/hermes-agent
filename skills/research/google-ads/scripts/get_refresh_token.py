#!/usr/bin/env python3
"""Obtain a Google Ads API OAuth refresh token (stdlib only — no deps).

One-shot helper for Phase 00 Step 6. Reads a Desktop OAuth client-secret JSON,
runs an OAuth flow on localhost (prints a URL to open in a browser), exchanges
the callback code for tokens, and writes the refresh token + client creds into
google-ads.env (built from google-ads.env.example with the OAuth vars filled).
Also backs the token up to data/.refresh-token.json (gitignored) IMMEDIATELY so
it survives any env-assembly error.

The refresh token / client_secret are NEVER printed to stdout.

Usage:
    python3 scripts/get_refresh_token.py <client_secret.json> [google-ads.env.out]

    # google-ads.env.out defaults to skills/research/google-ads/google-ads.env

Notes:
- Requires the OAuth app to be in Testing mode with the signing-in account added
  as a Test User (or be the project owner). An "Access blocked / 403 access_denied"
  means the account is neither — add it under Cloud Console → OAuth consent screen
  → Audience → Test users, then re-run.
- google-ads-python's load_from_env() later reads these GOOGLE_ADS_* vars; this
  script just materializes them into the env file.
"""
import json
import re
import sys
import urllib.parse
import urllib.request
import http.server
import socketserver
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/adwords"]
PORT = 8765


def load_client_config(path):
    """Return (client_id, client_secret, project_id, token_uri) from the JSON."""
    cfg = json.load(open(path))["installed"]
    return (cfg["client_id"], cfg["client_secret"], cfg.get("project_id", ""),
            cfg.get("token_uri", "https://oauth2.googleapis.com/token"))


def build_auth_url(client_id, redirect):
    return "https://accounts.google.com/o/oauth2/auth?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": redirect, "response_type": "code",
        "scope": " ".join(SCOPES), "access_type": "offline", "prompt": "consent",
    })


def wait_for_code(port):
    """Run a one-shot localhost server; return (code, error) from the callback."""
    got = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            p = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if "code" in p:
                got["code"] = p["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write("OK — return to terminal.".encode())
            else:
                got["error"] = p.get("error", ["unknown"])[0]
                self.send_response(400)
                self.end_headers()

        def log_message(self, *a):
            pass

    with socketserver.TCPServer(("127.0.0.1", port), Handler) as srv:
        srv.handle_request()
    return got.get("code"), got.get("error")


def exchange_code(code, client_id, client_secret, redirect, token_uri):
    data = urllib.parse.urlencode({
        "code": code, "client_id": client_id, "client_secret": client_secret,
        "redirect_uri": redirect, "grant_type": "authorization_code",
    }).encode()
    req = urllib.request.Request(
        token_uri, data=data, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def write_env(env_path, example_path, repl):
    """Build google-ads.env from .example, filling the keys in `repl` (dict sub)."""
    tpl = example_path.read_text() if example_path.exists() else ""
    out, applied = [], set()
    for ln in tpl.splitlines():
        m = re.match(r"^([A-Z_]+)=", ln)
        if m and m.group(1) in repl:
            out.append(f"{m.group(1)}={repl[m.group(1)]}")
            applied.add(m.group(1))
        else:
            out.append(ln)
    env_path.write_text("\n".join(out) + "\n")
    return applied


def main():
    if len(sys.argv) < 2:
        print("usage: get_refresh_token.py <client_secret.json> [google-ads.env.out]")
        sys.exit(2)
    secrets = Path(sys.argv[1])
    env_out = Path(sys.argv[2]) if len(sys.argv) > 2 else \
        Path(__file__).resolve().parent.parent / "google-ads.env"
    example = env_out.parent / "google-ads.env.example"
    backup = env_out.parent / "data" / ".refresh-token.json"

    client_id, client_secret, project_id, token_uri = load_client_config(secrets)
    redirect = f"http://localhost:{PORT}"
    print("AUTH_URL:", build_auth_url(client_id, redirect), flush=True)
    print(f"(Open that URL, consent; the browser then hits http://localhost:{PORT}.)",
          flush=True)

    code, err = wait_for_code(PORT)
    if not code:
        print("ERROR: no code received:", err)
        sys.exit(1)

    tok = exchange_code(code, client_id, client_secret, redirect, token_uri)
    refresh = tok.get("refresh_token")
    if not refresh:
        print("ERROR: no refresh_token in token response")
        sys.exit(4)

    # Back up the token FIRST (gitignored data/) so it survives env-assembly errors.
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_text(json.dumps({
        "client_id": client_id, "client_secret": client_secret,
        "refresh_token": refresh, "project_id": project_id,
    }, indent=2))

    repl = {
        "GOOGLE_ADS_CLIENT_ID": client_id,
        "GOOGLE_ADS_CLIENT_SECRET": client_secret,
        "GOOGLE_ADS_REFRESH_TOKEN": refresh,
        "GOOGLE_CLOUD_PROJECT_ID": project_id,
    }
    applied = write_env(env_out, example, repl)

    written = env_out.read_text()
    verify = [f"{k}={'OK' if f'{k}={v}' in written and 'your_' not in v else 'FAIL'}"
              for k, v in repl.items()]
    print(f"REFRESH_OK: backup={backup} | env={env_out} "
          f"| applied={sorted(applied)} | verify={verify}")


if __name__ == "__main__":
    main()
