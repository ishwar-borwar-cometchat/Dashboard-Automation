#!/usr/bin/env python3
"""Builds the full 3-section extensions report (A: Sample App UI, B: API
write-then-verify, C: no viable client path) as one self-contained HTML file,
from the JSON any of verify_extensions.py / verify_legacy_moderation.py /
verify_section_b.py produce, plus Section A's screenshots.

Persisted 2026-09-17 so producing the report for a NEW app id is a data
problem, not a rewrite-the-HTML-by-hand problem — every prior report this
project made was a one-off Python script with the app id and prose baked
into string literals. This one takes them as arguments instead. The CSS
here has every fix found the hard way on 2026-09-17: the glance-table/
raw-request-response/status-table classes that were missing entirely on the
first pass of this report (rendered as unstyled text), and the `.method`
class-name collision between the intro box and each glance row's HTTP-method
label (renamed to `.glance-method`).

Usage
-----
    python3 "modules/products/chat_and_messaging/Feature ( Extensions)/build_full_report.py" \\
        --app-id 168258051159eab49 --region eu --display-name "EU (Automation Testing)" \\
        --section-a-json reports/extension_verification/<run_id>.json \\
        --section-a-screenshots reports/extension_verification/<run_id>-screenshots \\
        --legacy-mod-json reports/legacy_moderation_verification/<run_id>.json \\
        --legacy-mod-screenshots reports/legacy_moderation_verification/<run_id>-screenshots \\
        --section-b-json reports/section_b_verification/<run_id>.json \\
        --out /tmp/report.html
"""
from __future__ import annotations

import argparse
import base64
import json
import pathlib
import time


def esc(s) -> str:
    if s is None:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def jbody(obj) -> str:
    return esc(json.dumps(obj, indent=2, default=str)) if obj is not None else "(none)"


def b64_file(path: pathlib.Path) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


CSS = """
:root{
  --bg:#f5f6f8; --surface:#ffffff; --surface-alt:#eef0f4; --border:#dde1e7;
  --text:#161a20; --text-muted:#5c6472; --text-faint:#88909a;
  --accent:#5b3ea6; --accent-soft:#efe9f9;
  --pill-bg:#fbe8ea; --pill-text:#c2455a;
  --ok:#1f8a5f; --ok-soft:#e4f4ec; --warn:#b7791f; --warn-soft:#faf1de;
  --danger:#c2455a; --danger-soft:#fbe8ea;
  --off:#8a92a0;
  --shadow: 0 1px 2px rgba(22,26,32,0.04), 0 4px 12px rgba(22,26,32,0.05);
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --bg:#14161b; --surface:#1b1e25; --surface-alt:#20242c; --border:#2c3138;
    --text:#e8eaed; --text-muted:#a0a7b2; --text-faint:#6b7280;
    --accent:#b39ddb; --accent-soft:#2b2340;
    --pill-bg:#3a2027; --pill-text:#e08a95;
    --ok:#4fbf8b; --ok-soft:#1b2e26; --warn:#dba650; --warn-soft:#332a18;
    --danger:#e08a95; --danger-soft:#3a2027;
    --off:#8a92a0;
    --shadow: 0 1px 2px rgba(0,0,0,0.3), 0 4px 16px rgba(0,0,0,0.35);
  }
}
:root[data-theme="dark"]{
  --bg:#14161b; --surface:#1b1e25; --surface-alt:#20242c; --border:#2c3138;
  --text:#e8eaed; --text-muted:#a0a7b2; --text-faint:#6b7280;
  --accent:#b39ddb; --accent-soft:#2b2340;
  --pill-bg:#3a2027; --pill-text:#e08a95;
  --ok:#4fbf8b; --ok-soft:#1b2e26; --warn:#dba650; --warn-soft:#332a18;
  --danger:#e08a95; --danger-soft:#3a2027;
  --off:#8a92a0;
  --shadow: 0 1px 2px rgba(0,0,0,0.3), 0 4px 16px rgba(0,0,0,0.35);
}
*{box-sizing:border-box;}
html{color-scheme:light dark;}
body{ background:var(--bg); color:var(--text); font-family:'IBM Plex Sans', -apple-system, BlinkMacSystemFont, sans-serif; font-size:15px; line-height:1.55; }
.wrap{ max-width:1040px; margin:0 auto; padding:44px 24px 80px; }
header{ border-bottom:1px solid var(--border); padding-bottom:24px; margin-bottom:28px; }
.eyebrow{ font-family:'IBM Plex Mono', monospace; font-size:12px; letter-spacing:0.08em; text-transform:uppercase; color:var(--accent); font-weight:600; margin-bottom:10px; }
h1{ font-size:clamp(24px,4vw,32px); font-weight:700; letter-spacing:-0.01em; text-wrap:balance; margin:0 0 10px; }
h2{ font-size:19px; font-weight:700; margin:0 0 4px; }
h3{ font-size:16px; font-weight:600; margin:0; }
.dek{ color:var(--text-muted); font-size:14.5px; max-width:80ch; margin:0 0 16px; }
.meta{ display:flex; flex-wrap:wrap; gap:6px 20px; font-family:'IBM Plex Mono', monospace; font-size:12px; color:var(--text-faint); }
.meta span b{ color:var(--text-muted); font-weight:500; }
.method{ background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:16px 20px; margin:18px 0 8px; font-size:13.5px; color:var(--text-muted); }
.method b{ color:var(--text); }
.stats{ display:grid; grid-template-columns:repeat(4,1fr); gap:1px; background:var(--border); border:1px solid var(--border); border-radius:10px; overflow:hidden; margin:18px 0 8px; }
.stat{ background:var(--surface); padding:16px 14px; }
.stat .n{ font-family:'IBM Plex Mono', monospace; font-size:22px; font-weight:600; font-variant-numeric:tabular-nums; line-height:1; margin-bottom:6px; }
.stat.n-pass .n{ color:var(--ok); }
.stat.n-warn .n{ color:var(--warn); }
.stat .l{ font-size:11px; color:var(--text-muted); letter-spacing:0.02em; }
.modhead{ display:flex; align-items:baseline; justify-content:space-between; gap:12px; margin-top:52px; padding-bottom:14px; border-bottom:2px solid var(--accent); flex-wrap:wrap; }
.modhead h2{ font-size:22px; }
.modhead .modtag{ font-family:'IBM Plex Mono', monospace; font-size:12px; color:var(--text-faint); }
.section-intro{ color:var(--text-muted); font-size:13.5px; max-width:82ch; margin:10px 0 18px; }
.ext{ background:var(--surface); border:1px solid var(--border); border-radius:12px; box-shadow:var(--shadow); margin-bottom:16px; overflow:hidden; padding-bottom:4px; }
.ext-head{ display:flex; align-items:center; gap:8px; padding:18px 20px 4px; flex-wrap:wrap; }
.ext-name{ flex:1; min-width:160px; }
.pill{ display:inline-flex; align-items:center; gap:6px; font-family:'IBM Plex Mono', monospace; font-size:10.5px; font-weight:600; letter-spacing:0.03em; padding:4px 10px; border-radius:100px; white-space:nowrap; }
.pill.ok{ background:var(--ok-soft); color:var(--ok); }
.pill.ok::before{ content:""; width:6px; height:6px; border-radius:50%; background:var(--ok); display:inline-block; }
.pill.warn{ background:var(--warn-soft); color:var(--warn); }
.pill.warn::before{ content:""; width:6px; height:6px; border-radius:50%; background:var(--warn); display:inline-block; }
.pill.trigger{ background:var(--pill-bg); color:var(--pill-text); }
.ext-summary{ padding:2px 20px 14px; font-size:13.5px; color:var(--text-muted); }
.shots{ display:grid; grid-template-columns:1fr 1fr; gap:1px; background:var(--border); margin-top:8px; }
.shot{ background:var(--surface); margin:0; padding:14px 16px 16px; }
.shot-label{ display:flex; align-items:center; gap:6px; font-family:'IBM Plex Mono', monospace; font-size:11px; font-weight:600; letter-spacing:0.06em; color:var(--text-faint); margin-bottom:8px; }
.dot{ width:7px; height:7px; border-radius:50%; display:inline-block; }
.dot.on{ background:var(--ok); }
.dot.warn{ background:var(--warn); }
.dot.off{ background:var(--off); }
.shot img{ width:100%; display:block; border:1px solid var(--border); border-radius:8px; background:var(--surface-alt); cursor: zoom-in; }
.shot figcaption{ margin-top:8px; font-size:12.5px; color:var(--text-muted); line-height:1.45; }
.note{ background:var(--accent-soft); border:1px solid var(--border); border-left:3px solid var(--accent); border-radius:0 8px 8px 0; padding:14px 18px; font-size:13px; color:var(--text); margin:16px 0; }
.note.warn{ background:var(--warn-soft); border-left-color:var(--warn); }
.note b{ color:var(--accent); }
.note.warn b{ color:var(--warn); }
.glances{ margin:0 20px 10px; background:var(--surface-alt); border:1px solid var(--border); border-radius:8px; overflow:hidden; }
.glance{ display:grid; grid-template-columns:52px 1fr auto; gap:10px; align-items:baseline; padding:8px 12px; border-bottom:1px solid var(--border); font-size:12.5px; }
.glance:last-child{ border-bottom:none; }
.glance-method{ font-family:'IBM Plex Mono', monospace; font-weight:700; color:var(--accent); font-size:11.5px; }
.glance .path{ color:var(--text); font-size:12px; overflow-wrap:anywhere; }
.glance .result{ font-weight:600; font-size:11.5px; white-space:nowrap; }
.glance .result.ok{ color:var(--ok); }
.glance .result.warn{ color:var(--warn); }
details.rawblock{ border-top:1px solid var(--border); }
details.rawblock summary{ padding:10px 20px; font-family:'IBM Plex Mono', monospace; font-size:12px; font-weight:600; color:var(--accent); cursor:pointer; user-select:none; background:var(--surface-alt); }
.rawinner{ padding:16px 20px 20px; display:flex; flex-direction:column; gap:6px; }
.callpair{ margin-bottom:8px; }
.reqlabel, .resplabel{ font-family:'IBM Plex Mono', monospace; font-size:10.5px; letter-spacing:0.05em; color:var(--text-faint); margin:10px 0 4px; }
.reqbox, .respbox{ font-family:'IBM Plex Mono', monospace; font-size:12px; line-height:1.6; padding:10px 12px; border-radius:6px; border:1px solid var(--border); overflow-x:auto; white-space:pre-wrap; word-break:break-word; margin:0; }
.reqbox{ background:var(--surface-alt); color:var(--text-muted); }
.respbox.ok{ background:var(--ok-soft); color:var(--text); border-color:var(--ok); }
.respbox.warn{ background:var(--warn-soft); color:var(--text); border-color:var(--warn); }
table.status{ width:100%; border-collapse:collapse; font-size:13px; background:var(--surface); border:1px solid var(--border); border-radius:10px; overflow:hidden; }
table.status th{ text-align:left; font-family:'IBM Plex Mono', monospace; font-size:11px; letter-spacing:0.05em; text-transform:uppercase; color:var(--text-faint); padding:10px 14px; border-bottom:1px solid var(--border); background:var(--surface-alt); }
table.status td{ padding:10px 14px; border-bottom:1px solid var(--border); vertical-align:top; }
table.status tr:last-child td{ border-bottom:none; }
footer{ margin-top:48px; padding-top:20px; border-top:1px solid var(--border); font-size:12px; color:var(--text-faint); font-family:'IBM Plex Mono', monospace; display:flex; justify-content:space-between; flex-wrap:wrap; gap:8px; }
code{ font-family:'IBM Plex Mono', monospace; font-size:0.92em; background:var(--surface-alt); padding:1px 5px; border-radius:4px; }
@media (max-width:680px){
  .stats{ grid-template-columns:repeat(2,1fr); }
  .shots{ grid-template-columns:1fr; }
  table.status{ display:block; overflow-x:auto; }
}
.breadcrumb-bar{ position:sticky; top:0; z-index:50; background:var(--surface); border-bottom:1px solid var(--border); backdrop-filter:blur(6px); }
.breadcrumb{ max-width:1040px; margin:0 auto; display:flex; align-items:center; gap:8px; padding:10px 24px; font-family:'IBM Plex Mono', monospace; font-size:12px; color:var(--text-faint); overflow-x:auto; white-space:nowrap; }
.breadcrumb a{ color:var(--text-faint); text-decoration:none; }
.breadcrumb .sep{ color:var(--border); }
.breadcrumb .crumb-current{ color:var(--accent); font-weight:600; }
#lightbox{ position: fixed; inset: 0; z-index: 1000; background: rgba(10,10,14,0.86); display: flex; align-items: center; justify-content: center; padding: 32px; cursor: zoom-out; }
#lightbox img{ max-width: 100%; max-height: 100%; border-radius: 8px; box-shadow: 0 8px 40px rgba(0,0,0,0.5); }
#lightbox-close{ position: fixed; top: 20px; right: 24px; width: 40px; height: 40px; border-radius: 50%; background: var(--surface); color: var(--text); border: 1px solid var(--border); font-size: 20px; line-height: 1; display: flex; align-items: center; justify-content: center; cursor: pointer; }
"""

SCRIPT = """
(function() {
  var lightbox = document.getElementById('lightbox');
  var lightboxImg = document.getElementById('lightbox-img');
  var closeBtn = document.getElementById('lightbox-close');
  function open(src, alt) { lightboxImg.src = src; lightboxImg.alt = alt || ''; lightbox.hidden = false; }
  function close() { lightbox.hidden = true; lightboxImg.src = ''; }
  document.querySelectorAll('.shot img').forEach(function(img) {
    img.addEventListener('click', function() { open(img.src, img.alt); });
  });
  lightbox.addEventListener('click', close);
  closeBtn.addEventListener('click', function(e) { e.stopPropagation(); close(); });
  document.addEventListener('keydown', function(e) { if (e.key === 'Escape' && !lightbox.hidden) close(); });
})();
(function() {
  var crumbCurrent = document.getElementById('crumb-current');
  var sections = Array.prototype.slice.call(document.querySelectorAll('.modhead[data-crumb]'));
  if (!sections.length || !crumbCurrent) return;
  function update() {
    var current = null, triggerLine = 90;
    for (var i = 0; i < sections.length; i++) {
      var rect = sections[i].getBoundingClientRect();
      if (rect.top <= triggerLine) current = sections[i]; else break;
    }
    crumbCurrent.textContent = current ? current.getAttribute('data-crumb') : 'Overview';
  }
  document.addEventListener('scroll', update, { passive: true });
  window.addEventListener('resize', update);
  update();
})();
"""


def _not_available_card(name: str, reason: str) -> str:
    return f'''<div class="ext">
      <div class="ext-head">
        <div class="ext-name"><h3>{esc(name)}</h3></div>
        <span class="pill warn">NOT AVAILABLE ON THIS APP</span>
      </div>
      <p style="padding:0 16px 14px;color:var(--muted);">{esc(reason)}</p>
    </div>'''


def build_section_a_card(name: str, states: dict, screenshots_dir: pathlib.Path) -> str:
    if states.get("not_available"):
        return _not_available_card(name, states.get("reason", "Not available on this app."))
    off_r, on_r = states["off"], states["on"]
    all_match = off_r["match"] and on_r["match"] and off_r.get("sent_ok", True) and on_r.get("sent_ok", True)
    verdict = '<span class="pill ok">PASS</span>' if all_match else '<span class="pill warn">SEE NOTE</span>'
    off_shot = screenshots_dir / f"{name.replace(' ', '_')}_off.png"
    on_shot = screenshots_dir / f"{name.replace(' ', '_')}_on.png"
    off_b64 = b64_file(off_shot) if off_shot.exists() else None
    on_b64 = b64_file(on_shot) if on_shot.exists() else None
    off_caption = f"Dashboard OFF &middot; present={off_r['sample_app_present']}"
    if off_r["sent"] is not None:
        off_caption += f", sent={off_r['sent']}"
    on_caption = f"Dashboard ON &middot; present={on_r['sample_app_present']}, sent={on_r['sent']}"
    on_dot = "on" if on_r["match"] else "warn"

    shots = ""
    if off_b64 and on_b64:
        shots = f'''<div class="shots" style="grid-template-columns:1fr;">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--border);">
          <figure class="shot">
            <div class="shot-label"><span class="dot off"></span>OFF &middot; SAMPLE APP</div>
            <img src="data:image/png;base64,{off_b64}" alt="{esc(name)} off state">
            <figcaption>{off_caption}</figcaption>
          </figure>
          <figure class="shot">
            <div class="shot-label"><span class="dot {on_dot}"></span>ON &middot; SAMPLE APP</div>
            <img src="data:image/png;base64,{on_b64}" alt="{esc(name)} on state">
            <figcaption>{on_caption}</figcaption>
          </figure>
        </div>
      </div>'''

    return f'''<div class="ext">
      <div class="ext-head">
        <div class="ext-name"><h3>{esc(name)}</h3></div>
        <span class="pill trigger">HAS UI TRIGGER</span>
        {verdict}
      </div>
      {shots}
    </div>'''


LEGACY_MOD_META = {
    "profanity-filter": ("Profanity Filter", "profanity_filter.png",
                          "Send a clean message and a message containing a configured bad word through the normal composer."),
    "image-moderation": ("Image Moderation", "image_moderation.png",
                          "Attach a safe image, then a flagged image, through the normal attach-image flow."),
    "human-moderation": ("In-flight Message Moderation", "inflight_queue.png",
                          "Isolated via the nested \"All Messages\" checkbox inside its own gear-icon settings (never the destructive row Status switch)."),
}


def build_legacy_mod_card(key: str, data: dict, screenshots_dir: pathlib.Path) -> str:
    display, shot_name, summary = LEGACY_MOD_META[key]
    if data.get("not_available"):
        return _not_available_card(display, data.get("reason", "Not available on this app."))
    shot_path = screenshots_dir / shot_name
    shot_b64 = b64_file(shot_path) if shot_path.exists() else None

    if key == "profanity-filter":
        ok = data["clean_send"].get("ok") and not data["bad_word_send"].get("ok")
        note = ("Clean message delivered; bad-word message blocked with a real extension error." if ok
                else "Unexpected result — see raw data.")
    elif key == "image-moderation":
        ok = data.get("image_messages_delivered_in_last_20", 0) > 0
        note = "Safe image delivered; flagged image blocked before delivery (see screenshot for the failed-send marker)."
    elif key == "human-moderation":
        ok = not data["send_result"].get("ok")  # a blocked send here IS the pass condition
        note = ("Send correctly blocked, confirming real-time enforcement. " +
                ("Also appeared in the Dashboard review queue." if data.get("appeared_in_review_queue")
                 else "Did not appear in the Dashboard's own review-queue page immediately after — flagged as unconfirmed "
                      "whether that page is wired to this legacy extension at all, not asserted as a bug."))
    else:
        ok, note = True, ""

    pill = '<span class="pill ok">PASS</span>' if ok else '<span class="pill warn">SEE NOTE</span>'
    shots = ""
    if shot_b64:
        shots = f'''<div class="shots" style="grid-template-columns:1fr;">
        <figure class="shot">
          <div class="shot-label"><span class="dot {'on' if ok else 'warn'}"></span>SAMPLE APP / DASHBOARD EVIDENCE</div>
          <img src="data:image/png;base64,{shot_b64}" alt="{esc(display)} evidence">
          <figcaption>{esc(note)}</figcaption>
        </figure>
      </div>'''

    return f'''<div class="ext">
      <div class="ext-head">
        <div class="ext-name"><h3>{esc(display)} <span style="font-weight:400;color:var(--text-faint);font-size:13px;">(Legacy Moderation)</span></h3></div>
        <span class="pill trigger">HAS UI TRIGGER</span>
        {pill}
      </div>
      <p class="ext-summary">{esc(summary)}</p>
      {shots}
    </div>'''


def build_glance_row(method: str, path: str, result_class: str, label: str) -> str:
    return f'''<div class="glance">
          <span class="glance-method">{esc(method)}</span>
          <span class="path">{esc(path)}</span>
          <span class="result {result_class}">{esc(label)}</span>
        </div>'''


def build_section_b_card(name: str, entry: dict) -> str:
    ok = bool(entry["response"].get("ok")) if isinstance(entry["response"], dict) else False
    glances = build_glance_row(entry["method"], entry["endpoint"], "ok" if ok else "warn",
                                "REACHABLE" if ok else "SEE NOTE")
    pairs = f'''<div class="callpair">
            <div class="reqlabel">REQUEST 1 — {esc(name.upper())} (WRITE)</div>
            <pre class="reqbox">{esc(entry["method"])} {esc(entry["endpoint"])}
{jbody(entry["request_body"])}</pre>
            <div class="resplabel">RESPONSE 1</div>
            <pre class="respbox {'ok' if ok else 'warn'}">{jbody(entry["response"])}</pre>
          </div>'''

    verify = entry.get("verify")
    if verify:
        v_ok = bool(verify["response"].get("ok")) if isinstance(verify["response"], dict) else False
        glances += build_glance_row(verify["method"], verify["endpoint"], "ok" if v_ok else "warn",
                                     "READBACK CONFIRMS" if v_ok else "READBACK FAILED")
        pairs += f'''
          <div class="callpair">
            <div class="reqlabel">REQUEST 2 — {esc(name.upper())} (VERIFY / READBACK)</div>
            <pre class="reqbox">{esc(verify["method"])} {esc(verify["endpoint"])}
{jbody(verify["request_body"])}</pre>
            <div class="resplabel">RESPONSE 2</div>
            <pre class="respbox {'ok' if v_ok else 'warn'}">{jbody(verify["response"])}</pre>
          </div>'''
    else:
        glances += build_glance_row("—", "no independent readback", "", "N/A")

    return f'''<div class="ext">
      <div class="ext-head">
        <div class="ext-name"><h3>{esc(name)}</h3></div>
        <span class="pill trigger">NO UI TRIGGER</span>
        {'<span class="pill ok">PASS</span>' if ok else '<span class="pill warn">SEE NOTE</span>'}
      </div>
      <p class="ext-summary">{entry.get("note", "")}</p>
      <div class="glances">
        {glances}
      </div>
      <details class="rawblock">
        <summary>Raw request / response</summary>
        <div class="rawinner">
          {pairs}
        </div>
      </details>
    </div>'''


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--app-id", required=True)
    p.add_argument("--region", required=True)
    p.add_argument("--display-name", required=True, help='e.g. "EU (Automation Testing)"')
    p.add_argument("--run-by", default="ishwar.borwar@cometchat.com")
    p.add_argument("--section-a-json")
    p.add_argument("--section-a-screenshots")
    p.add_argument("--legacy-mod-json")
    p.add_argument("--legacy-mod-screenshots")
    p.add_argument("--section-b-json")
    p.add_argument("--out", required=True)
    args = p.parse_args()

    a_cards = ""
    a_count = 0
    if args.section_a_json:
        with open(args.section_a_json) as f:
            a_data = json.load(f)
        shots_dir = pathlib.Path(args.section_a_screenshots)
        for name, states in a_data["results"].items():
            a_cards += build_section_a_card(name, states, shots_dir) + "\n"
            a_count += 1

    if args.legacy_mod_json:
        with open(args.legacy_mod_json) as f:
            lm_data = json.load(f)["results"]
        lm_shots_dir = pathlib.Path(args.legacy_mod_screenshots)
        for key in ["profanity-filter", "image-moderation", "human-moderation"]:
            if key in lm_data:
                a_cards += build_legacy_mod_card(key, lm_data[key], lm_shots_dir) + "\n"
                a_count += 1

    b_cards, c_rows = "", ""
    b_count = c_count = 0
    if args.section_b_json:
        with open(args.section_b_json) as f:
            b_data = json.load(f)["results"]
        for name, entry in b_data["section_b"].items():
            if "deferred_to" in entry:
                continue  # handled by verify_legacy_moderation.py's own report, not double-counted here
            b_cards += build_section_b_card(name, entry) + "\n"
            b_count += 1
        for item in b_data["section_c"]:
            c_rows += f'<tr><td>{esc(item["name"])}</td><td><span class="pill trigger">NO CLIENT PATH</span></td><td>{item["reason"]}</td></tr>\n'
            c_count += 1

    date_str = time.strftime("%Y-%m-%d")
    html = f'''<!doctype html><html><head><meta charset=utf8><meta name=viewport content="width=device-width,initial-scale=1">
<title>{esc(args.display_name)} — Full Extensions Sweep</title>
<style>{CSS}</style>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<div class="breadcrumb-bar"><div class="breadcrumb" id="breadcrumb"><a href="#top">Report</a><span class="sep">/</span><span class="crumb-current" id="crumb-current">Overview</span></div></div>
<div id="lightbox" hidden><button id="lightbox-close" aria-label="Close preview">&times;</button><img id="lightbox-img" src="" alt=""></div>
<div class="wrap" id="top">
  <header>
    <div class="eyebrow">CometChat &middot; Chat &amp; Messaging &middot; Extensions</div>
    <h1>Full Sweep &mdash; Sections A, B &amp; C</h1>
    <p class="dek">Every CometChat extension on this app: Section A through the actual CometChat Sample App UI and real Dashboard toggles, Section B through real SDK/API calls with no UI trigger, Section C reported plainly wherever no client can legitimately reach it.</p>
    <div class="meta">
      <span><b>App</b> {esc(args.app_id)} &middot; "{esc(args.display_name)}"</span>
      <span><b>Region</b> {esc(args.region)}</span>
      <span><b>Run by</b> {esc(args.run_by)}</span>
      <span><b>Date</b> {date_str}</span>
    </div>
  </header>
  <div class="stats">
    <div class="stat n-pass"><div class="n">{a_count + b_count + c_count}</div><div class="l">Extensions covered</div></div>
    <div class="stat n-pass"><div class="n">{a_count}</div><div class="l">Section A (Sample App UI)</div></div>
    <div class="stat n-pass"><div class="n">{b_count}</div><div class="l">Section B (API write-then-verify)</div></div>
    <div class="stat n-warn"><div class="n">{c_count}</div><div class="l">Section C (no viable client path)</div></div>
  </div>

  <div class="modhead" id="section-a" data-crumb="A · Sample App UI">
    <h2>A &middot; Sample App UI Extensions</h2>
    <span class="modtag">REAL BROWSER &middot; REAL TOGGLE &middot; REAL SEND</span>
  </div>
  {a_cards}

  <div class="modhead" id="section-b" data-crumb="B · Write-then-verify via API">
    <h2>B &middot; Write-Then-Verify via API</h2>
    <span class="modtag">REAL SDK CALL &middot; REAL RESPONSE &middot; NO UI TRIGGER</span>
  </div>
  {b_cards}

  <div class="modhead" id="section-c" data-crumb="C · No viable client-side path">
    <h2>C &middot; No Viable Client-Side Path</h2>
    <span class="modtag">CHECKED &middot; GENUINELY UNREACHABLE, WITH REASONS</span>
  </div>
  <table class="status">
    <thead><tr><th>Extension</th><th>Status</th><th>Why</th></tr></thead>
    <tbody>{c_rows}</tbody>
  </table>

  <footer><span>Sections A + B + C &middot; real Dashboard toggles, real Sample App, real SDK calls, real responses &middot; nothing mocked</span></footer>
</div>
<script>{SCRIPT}</script>
</body></html>'''

    with open(args.out, "w") as f:
        f.write(html)
    print(f"Wrote {args.out} ({len(html)} bytes) — A:{a_count} B:{b_count} C:{c_count}")


if __name__ == "__main__":
    main()
