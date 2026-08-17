"""Generate a standalone pass/fail/skip HTML report from reports/results.json."""
from __future__ import annotations

import html
import json
import pathlib
import sys
from collections import Counter, OrderedDict
from typing import Any, Dict, List

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"

STATUS_LABEL = {"passed": "PASS", "failed": "FAIL", "skipped": "SKIP"}


def _priority_rank(priority: str) -> int:
    p = (priority or "").lower()
    if "critical" in p:
        return 0
    if "high" in p:
        return 1
    if "medium" in p:
        return 2
    if "low" in p:
        return 3
    return 4


def build(results_path: pathlib.Path, out_path: pathlib.Path) -> pathlib.Path:
    data: Dict[str, Any] = json.loads(results_path.read_text())
    results: List[Dict[str, Any]] = data.get("results", [])

    counts = Counter(r["status"] for r in results)
    total = len(results)
    passed = counts.get("passed", 0)
    failed = counts.get("failed", 0)
    skipped = counts.get("skipped", 0)
    executed = passed + failed
    pass_rate = (passed / executed * 100) if executed else 0.0

    # group by scenario, preserving OV_ order
    scenarios: "OrderedDict[str, List[Dict[str, Any]]]" = OrderedDict()
    for r in sorted(results, key=lambda x: x.get("id") or "zzz"):
        scenarios.setdefault(r.get("scenario") or "Uncategorised", []).append(r)

    # critical/high failures
    blocking = [
        r for r in results
        if r["status"] == "failed" and _priority_rank(r.get("priority", "")) <= 1
    ]

    rows_html = []
    for scenario, items in scenarios.items():
        s_counts = Counter(i["status"] for i in items)
        rows_html.append(
            f'<tr class="group-row"><td colspan="6">'
            f'<span class="group-name">{html.escape(scenario)}</span>'
            f'<span class="group-chips">'
            f'<span class="chip pass">{s_counts.get("passed",0)} pass</span>'
            f'<span class="chip fail">{s_counts.get("failed",0)} fail</span>'
            f'<span class="chip skip">{s_counts.get("skipped",0)} skip</span>'
            f'</span></td></tr>'
        )
        for r in items:
            status = r["status"]
            label = STATUS_LABEL.get(status, status.upper())
            reason = (r.get("reason") or "").strip()
            reason_html = ""
            if reason:
                short = reason.splitlines()
                headline = next(
                    (ln for ln in short if ln.strip().startswith("E ")), short[-1] if short else ""
                )
                headline = headline.replace("E   ", "").replace("E ", "").strip()
                reason_html = (
                    f'<details class="reason"><summary>{html.escape(headline[:220])}</summary>'
                    f'<pre>{html.escape(reason[:6000])}</pre></details>'
                )
            shot = r.get("screenshot") or ""
            shot_html = (
                f'<a class="shot" href="{html.escape(shot)}" target="_blank">screenshot</a>'
                if shot else ""
            )
            rows_html.append(
                f'<tr class="case {status}" data-status="{status}" '
                f'data-priority="{html.escape((r.get("priority") or "").lower())}">'
                f'<td class="tcid">{html.escape(r.get("id") or "")}</td>'
                f'<td class="title">{html.escape(r.get("title") or "")}'
                f'<div class="expected">{html.escape(r.get("expected") or "")}</div></td>'
                f'<td class="sentiment">{html.escape(r.get("sentiment") or "")}</td>'
                f'<td class="priority p{_priority_rank(r.get("priority",""))}">'
                f'{html.escape(r.get("priority") or "")}</td>'
                f'<td class="status"><span class="badge {status}">{label}</span></td>'
                f'<td class="detail">{reason_html}{shot_html}'
                f'<div class="dur">{r.get("duration", 0)}s</div></td></tr>'
            )

    blocking_html = ""
    if blocking:
        items = "".join(
            f'<li><b>{html.escape(b.get("id",""))}</b> — {html.escape(b.get("title",""))} '
            f'<span class="pri">({html.escape(b.get("priority",""))})</span></li>'
            for b in blocking
        )
        blocking_html = (
            f'<div class="callout"><h3>Blocking failures '
            f'({len(blocking)} Critical/High)</h3><ul>{items}</ul></div>'
        )

    doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(data.get('module','Overview'))} E2E Report — CometChat Dashboard</title>
<style>
  :root {{
    --bg:#0f1115; --panel:#171a21; --panel2:#1d212a; --line:#2a2f3a;
    --fg:#e7e9ee; --muted:#9aa3b2;
    --pass:#3fb950; --fail:#f85149; --skip:#d29922; --accent:#58a6ff;
  }}
  @media (prefers-color-scheme: light) {{
    :root {{ --bg:#f6f7f9; --panel:#fff; --panel2:#f0f2f5; --line:#e1e4e8;
             --fg:#1b1f24; --muted:#5b6472;
             --pass:#1a7f37; --fail:#cf222e; --skip:#9a6700; --accent:#0969da; }}
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--fg);
    font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }}
  .wrap {{ max-width:1180px; margin:0 auto; padding:32px 20px 64px; }}
  header h1 {{ margin:0 0 4px; font-size:24px; letter-spacing:-0.2px; }}
  header .meta {{ color:var(--muted); font-size:13px; }}
  header .meta code {{ background:var(--panel2); padding:1px 6px; border-radius:4px; }}
  .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
    gap:12px; margin:24px 0; }}
  .card {{ background:var(--panel); border:1px solid var(--line); border-radius:10px;
    padding:16px; }}
  .card .n {{ font-size:30px; font-weight:650; letter-spacing:-1px; }}
  .card .l {{ color:var(--muted); font-size:12px; text-transform:uppercase;
    letter-spacing:.6px; margin-top:2px; }}
  .card.pass .n {{ color:var(--pass); }} .card.fail .n {{ color:var(--fail); }}
  .card.skip .n {{ color:var(--skip); }}
  .bar {{ display:flex; height:10px; border-radius:6px; overflow:hidden;
    background:var(--panel2); margin:4px 0 24px; }}
  .bar i {{ display:block; }} .bar .p {{ background:var(--pass); }}
  .bar .f {{ background:var(--fail); }} .bar .s {{ background:var(--skip); }}
  .callout {{ background:color-mix(in srgb, var(--fail) 10%, var(--panel));
    border:1px solid var(--fail); border-radius:10px; padding:14px 18px; margin-bottom:24px; }}
  .callout h3 {{ margin:0 0 8px; font-size:14px; color:var(--fail); }}
  .callout ul {{ margin:0; padding-left:18px; }} .callout .pri {{ color:var(--muted); }}
  .filters {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:14px; }}
  .filters button {{ background:var(--panel); color:var(--fg); border:1px solid var(--line);
    border-radius:20px; padding:6px 14px; cursor:pointer; font-size:13px; }}
  .filters button.on {{ border-color:var(--accent); color:var(--accent); }}
  table {{ width:100%; border-collapse:collapse; background:var(--panel);
    border:1px solid var(--line); border-radius:10px; overflow:hidden; }}
  th {{ text-align:left; font-size:11px; text-transform:uppercase; letter-spacing:.6px;
    color:var(--muted); padding:10px 12px; border-bottom:1px solid var(--line); }}
  td {{ padding:11px 12px; border-bottom:1px solid var(--line); vertical-align:top; }}
  tr.group-row td {{ background:var(--panel2); font-weight:600; font-size:13px; }}
  .group-chips {{ float:right; display:flex; gap:6px; }}
  .chip {{ font-size:11px; font-weight:500; padding:2px 8px; border-radius:10px;
    background:var(--bg); color:var(--muted); }}
  .chip.pass {{ color:var(--pass); }} .chip.fail {{ color:var(--fail); }}
  .chip.skip {{ color:var(--skip); }}
  .tcid {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12px;
    color:var(--muted); white-space:nowrap; }}
  .title {{ font-weight:500; max-width:420px; }}
  .expected {{ color:var(--muted); font-size:12px; font-weight:400; margin-top:3px; }}
  .badge {{ display:inline-block; padding:3px 10px; border-radius:5px; font-size:11px;
    font-weight:700; letter-spacing:.5px; }}
  .badge.passed {{ background:color-mix(in srgb,var(--pass) 18%,transparent); color:var(--pass); }}
  .badge.failed {{ background:color-mix(in srgb,var(--fail) 18%,transparent); color:var(--fail); }}
  .badge.skipped {{ background:color-mix(in srgb,var(--skip) 18%,transparent); color:var(--skip); }}
  .priority {{ font-size:12px; white-space:nowrap; }}
  .priority.p0 {{ color:var(--fail); font-weight:600; }}
  .priority.p1 {{ color:var(--skip); }} .priority.p2, .priority.p3 {{ color:var(--muted); }}
  .sentiment {{ font-size:12px; color:var(--muted); }}
  .detail {{ max-width:360px; font-size:12px; }}
  .reason summary {{ cursor:pointer; color:var(--muted); }}
  .reason pre {{ white-space:pre-wrap; word-break:break-word; background:var(--bg);
    border:1px solid var(--line); border-radius:6px; padding:10px; font-size:11px;
    max-height:320px; overflow:auto; }}
  .shot {{ color:var(--accent); font-size:12px; }}
  .dur {{ color:var(--muted); font-size:11px; margin-top:4px; }}
  footer {{ color:var(--muted); font-size:12px; margin-top:22px; }}
</style></head><body><div class="wrap">
<header>
  <h1>{html.escape(data.get('module','Overview'))} — E2E Test Report</h1>
  <div class="meta">CometChat Dashboard &middot;
    app <code>{html.escape(data.get('app_id',''))}</code> &middot;
    <code>{html.escape(data.get('base_url',''))}</code> &middot;
    run {html.escape(data.get('generated_at',''))}</div>
</header>

<div class="cards">
  <div class="card"><div class="n">{total}</div><div class="l">Total cases</div></div>
  <div class="card pass"><div class="n">{passed}</div><div class="l">Passed</div></div>
  <div class="card fail"><div class="n">{failed}</div><div class="l">Failed</div></div>
  <div class="card skip"><div class="n">{skipped}</div><div class="l">Skipped</div></div>
  <div class="card"><div class="n">{pass_rate:.0f}%</div>
    <div class="l">Pass rate ({executed} run)</div></div>
</div>

<div class="bar">
  <i class="p" style="width:{(passed/total*100) if total else 0:.2f}%"></i>
  <i class="f" style="width:{(failed/total*100) if total else 0:.2f}%"></i>
  <i class="s" style="width:{(skipped/total*100) if total else 0:.2f}%"></i>
</div>

{blocking_html}

<div class="filters">
  <button class="on" data-f="all">All ({total})</button>
  <button data-f="failed">Failed ({failed})</button>
  <button data-f="passed">Passed ({passed})</button>
  <button data-f="skipped">Skipped ({skipped})</button>
</div>

<table>
  <thead><tr><th>ID</th><th>Test case</th><th>Type</th><th>Priority</th>
  <th>Status</th><th>Detail</th></tr></thead>
  <tbody>{''.join(rows_html)}</tbody>
</table>

<footer>Generated by the CometChat Dashboard E2E suite (pytest + Playwright).
Skipped cases carry the reason they could not be executed.</footer>
</div>
<script>
  const btns = document.querySelectorAll('.filters button');
  btns.forEach(b => b.addEventListener('click', () => {{
    btns.forEach(x => x.classList.remove('on'));
    b.classList.add('on');
    const f = b.dataset.f;
    document.querySelectorAll('tr.case').forEach(r => {{
      r.style.display = (f === 'all' || r.dataset.status === f) ? '' : 'none';
    }});
    document.querySelectorAll('tr.group-row').forEach(g => {{
      let n = g.nextElementSibling, any = false;
      while (n && n.classList.contains('case')) {{
        if (n.style.display !== 'none') any = true;
        n = n.nextElementSibling;
      }}
      g.style.display = any ? '' : 'none';
    }});
  }}));
</script>
</body></html>"""

    out_path.write_text(doc, encoding="utf-8")
    return out_path


if __name__ == "__main__":
    src = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else REPORTS / "results.json"
    dst = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else REPORTS / "overview_report.html"
    path = build(src, dst)
    print(f"Report written to {path}")
