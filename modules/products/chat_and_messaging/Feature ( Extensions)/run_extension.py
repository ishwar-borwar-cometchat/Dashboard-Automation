#!/usr/bin/env python3
"""
Extract and execute requests for a given extension (by top-level item name)
from the CometChat Extensions API Postman collection.

Usage:
    python3 run_extension.py <extension-name> [--list] [--path "a/b/c"] [--dry-run]

--list      just list the requests found under that extension (name + method + path)
--path      only run the request whose folder path contains this substring
--dry-run   print the resolved curl command instead of executing it

Requires CC_APP_ID + CC_AUTH_TOKEN in the environment (or --app-id/--auth-token
on the command line) — no credentials are hardcoded in this file. For any
endpoint gated by HTTP Basic Auth, also set CC_BASIC_AUTH_USER/CC_BASIC_AUTH_PASS.
"""
import json
import os
import sys
import subprocess
import argparse
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

COLLECTION_PATH = "/Users/admin/Documents/Claude/Dashboard/CometChat Extensions API (team — auth baked).postman_collection.json"

# Override any of these per-run with --app-id / --region / --auth-token, or
# the CC_APP_ID / CC_REGION / CC_AUTH_TOKEN env vars — no need to edit this
# file to point testing at a different app. No credentials are hardcoded
# here; set the env vars (or a local, gitignored .env you source yourself)
# before running.
VARS = {
    "protocol": "https",
    "domain": "cometchat.io",
    "region": os.environ.get("CC_REGION", "eu"),
    "appId": os.environ.get("CC_APP_ID", ""),
    "authToken": os.environ.get("CC_AUTH_TOKEN", ""),
    "chatApiVersion": "v3",
    "appToken": "",
    "webhookToken": "",
    "apiKey": "",
    "onBehalfOf": "",
    "sfaEnabled": "0",
}
VARS["baseUrl"] = "{{protocol}}://extensions-{{region}}.{{domain}}"

BASIC_AUTH_USER = os.environ.get("CC_BASIC_AUTH_USER", "")
BASIC_AUTH_PASS = os.environ.get("CC_BASIC_AUTH_PASS", "")


def resolve(s):
    if s is None:
        return s
    prev = None
    while prev != s:
        prev = s
        for k, v in VARS.items():
            s = s.replace("{{%s}}" % k, str(v))
    return s


def walk(item, path=()):
    """Yield (path_tuple, request_dict) for every leaf request."""
    if "request" in item:
        yield path + (item.get("name"),), item["request"]
    for sub in item.get("item", []):
        yield from walk(sub, path + (item.get("name"),))


def find_extension(data, name):
    for top in data.get("item", []):
        if top.get("name") == name:
            return top
    return None


def build_curl(request):
    method = request.get("method", "GET")
    url = resolve(request.get("url", {}).get("raw", ""))
    headers = request.get("header", []) or []
    auth = request.get("auth")
    if auth and auth.get("type") == "basic":
        # Drop empty query params (e.g. an unresolved ?appToken=) so the
        # server's dual-mode auth check actually falls through to Basic auth
        # instead of short-circuiting on "appToken present but invalid".
        parts = urlsplit(url)
        kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if v]
        url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), parts.fragment))
    cmd = ["curl", "-sS", "-i", "-X", method]
    if auth and auth.get("type") == "basic":
        cmd += ["-u", f"{BASIC_AUTH_USER}:{BASIC_AUTH_PASS}"]
    for h in headers:
        if h.get("disabled"):
            continue
        key = h.get("key")
        val = resolve(h.get("value", ""))
        cmd += ["-H", f"{key}: {val}"]
    body = request.get("body")
    if body:
        mode = body.get("mode")
        if mode == "raw":
            cmd += ["--data-raw", resolve(body.get("raw", ""))]
        elif mode == "urlencoded":
            for p in body.get("urlencoded", []):
                if p.get("disabled"):
                    continue
                cmd += ["--data-urlencode", f"{p.get('key')}={resolve(p.get('value',''))}"]
        elif mode == "formdata":
            for p in body.get("formdata", []):
                if p.get("disabled"):
                    continue
                if p.get("type") == "file":
                    cmd += ["-F", f"{p.get('key')}=@{p.get('src')}"]
                else:
                    cmd += ["-F", f"{p.get('key')}={resolve(p.get('value',''))}"]
    cmd.append(url)
    return cmd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("extension")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--path", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--app-id", default=None, help="Override the app id (default: CC_APP_ID env or the Sample App)")
    ap.add_argument("--region", default=None, help="Override the region, e.g. us/eu/in (default: CC_REGION env or eu)")
    ap.add_argument("--auth-token", default=None, help="Override the authtoken (default: CC_AUTH_TOKEN env) — must belong to --app-id")
    args = ap.parse_args()

    if args.app_id:
        VARS["appId"] = args.app_id
    if args.region:
        VARS["region"] = args.region
    if args.auth_token:
        VARS["authToken"] = args.auth_token

    with open(COLLECTION_PATH) as f:
        data = json.load(f)

    ext = find_extension(data, args.extension)
    if not ext:
        names = [t.get("name") for t in data.get("item", [])]
        print(f"Extension '{args.extension}' not found. Available: {names}", file=sys.stderr)
        sys.exit(1)

    requests_found = list(walk(ext))
    if args.path:
        requests_found = [r for r in requests_found if args.path in "/".join(r[0])]

    if args.list:
        for path, req in requests_found:
            print(f"{req.get('method','GET'):6} {'/'.join(path)}")
        return

    if not requests_found:
        print("No requests matched.", file=sys.stderr)
        sys.exit(1)

    for path, req in requests_found:
        cmd = build_curl(req)
        print("=" * 80)
        print("REQUEST:", "/".join(path))
        print("URL:", resolve(req.get("url", {}).get("raw", "")))
        if args.dry_run:
            print("CURL:", " ".join(cmd))
            continue
        result = subprocess.run(cmd, capture_output=True, text=True)
        print(result.stdout)
        if result.returncode != 0:
            print("STDERR:", result.stderr, file=sys.stderr)


if __name__ == "__main__":
    main()
