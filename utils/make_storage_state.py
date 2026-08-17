"""Build auth/storage_state.json for Playwright from a browser session export.

Two supported inputs (you can combine both):

1. A cURL command copied from Chrome DevTools -> Network -> right-click any
   app.cometchat.com request -> Copy -> "Copy as cURL (bash)".
   This is the only way to capture httpOnly session cookies.

2. A JSON blob produced by pasting utils/devtools_snippet.js into the DevTools
   console on the logged-in dashboard tab. This captures localStorage and
   sessionStorage (where the dashboard may keep its access token).

Usage:
    python utils/make_storage_state.py --curl curl.txt --storage storage.json
    python utils/make_storage_state.py --curl curl.txt
    python utils/make_storage_state.py --storage storage.json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import shlex
from typing import Any, Dict, List
from urllib.parse import urlparse

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "auth" / "storage_state.json"

DEFAULT_DOMAIN = ".cometchat.com"


def cookies_from_curl(curl_text: str) -> List[Dict[str, Any]]:
    """Extract cookies from a `Copy as cURL (bash)` string."""
    text = curl_text.replace("\\\n", " ").replace("^\n", " ").strip()
    try:
        tokens = shlex.split(text)
    except ValueError:
        tokens = text.split()

    url = ""
    cookie_header = ""

    for i, tok in enumerate(tokens):
        if tok.startswith("http"):
            url = url or tok
        elif tok in ("-H", "--header") and i + 1 < len(tokens):
            header = tokens[i + 1]
            if header.lower().startswith("cookie:"):
                cookie_header = header.split(":", 1)[1].strip()
        elif tok in ("-b", "--cookie") and i + 1 < len(tokens):
            cookie_header = tokens[i + 1]

    if not cookie_header:
        raise SystemExit(
            "No Cookie header found in the cURL text. Make sure you used "
            "'Copy as cURL (bash)' on a request to app.cometchat.com."
        )

    host = urlparse(url).hostname if url else None
    domain = DEFAULT_DOMAIN
    if host:
        parts = host.split(".")
        domain = "." + ".".join(parts[-2:]) if len(parts) >= 2 else host

    cookies: List[Dict[str, Any]] = []
    for pair in cookie_header.split(";"):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        name, value = pair.split("=", 1)
        cookies.append(
            {
                "name": name.strip(),
                "value": value.strip(),
                "domain": domain,
                "path": "/",
                "expires": -1,
                "httpOnly": False,
                "secure": True,
                "sameSite": "Lax",
            }
        )
    return cookies


def origins_from_storage(blob: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convert the devtools snippet output into Playwright `origins`."""
    origin = blob.get("origin") or "https://app.cometchat.com"
    items = blob.get("localStorage") or {}
    return [
        {
            "origin": origin,
            "localStorage": [
                {"name": k, "value": v if isinstance(v, str) else json.dumps(v)}
                for k, v in items.items()
            ],
        }
    ]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--curl", help="file containing the 'Copy as cURL (bash)' text")
    ap.add_argument("--storage", help="file containing the devtools snippet JSON output")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    if not args.curl and not args.storage:
        ap.error("provide at least one of --curl / --storage")

    state: Dict[str, Any] = {"cookies": [], "origins": []}

    if args.curl:
        state["cookies"] = cookies_from_curl(pathlib.Path(args.curl).read_text())

    if args.storage:
        blob = json.loads(pathlib.Path(args.storage).read_text())
        state["origins"] = origins_from_storage(blob)
        for c in blob.get("cookies", []) or []:
            names = {x["name"] for x in state["cookies"]}
            if c.get("name") not in names:
                state["cookies"].append(
                    {
                        "name": c["name"],
                        "value": c["value"],
                        "domain": c.get("domain", DEFAULT_DOMAIN),
                        "path": c.get("path", "/"),
                        "expires": -1,
                        "httpOnly": False,
                        "secure": True,
                        "sameSite": "Lax",
                    }
                )

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(state, indent=2))
    print(
        f"Wrote {out}\n"
        f"  cookies: {len(state['cookies'])}\n"
        f"  localStorage keys: "
        f"{sum(len(o['localStorage']) for o in state['origins'])}"
    )


if __name__ == "__main__":
    main()
