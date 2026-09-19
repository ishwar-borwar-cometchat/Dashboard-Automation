#!/usr/bin/env python3
"""Turns a running test script's log into live-progress data for the QA Console.

Generic: works for any script that prints one "=== <step name> ===" header per
step and ends with a line starting "exit=" (the run wrapper appends it). Nothing
here is specific to an app, module or step list.

  python3 tools/live_progress.py --log /tmp/run.log --start-ms 1789806027000 \
      --steps "Stickers,Polls,..." --out steps.json [--est-from old1.log old2.log]

Each time the number of finished steps changes it rewrites --out (a JSON object
ready to merge into the `runs/<id>` doc: steps, phase, logTail) and prints one
"progress N/M" line, so a Monitor can wake the caller to push it to the db.
Step time estimates come from earlier logs (--est-from): the "[time]" lines the
scripts print are summed per step; later logs override earlier ones.
"""
import argparse, json, re, time

HDR = re.compile(r"^=== (.+?) ===")
TIMED = re.compile(r"\[time\].*?:\s*(.*)")
SEG = re.compile(r"([\d.]+)s")

def sections(lines):
    out, cur = {}, None
    for l in lines:
        m = HDR.match(l)
        if m:
            cur = m.group(1); out[cur] = []
        elif cur:
            out[cur].append(l)
    return out

def estimates(paths):
    est = {}
    for p in paths or []:
        try:
            secs = sections(open(p).read().splitlines())
        except OSError:
            continue
        for name, body in secs.items():
            tot = 0.0
            for l in body:
                if "[time]" in l:
                    tot += sum(float(x) for x in SEG.findall(l))
            if tot:
                est[name] = round(tot)
    return est

def verdict(body):
    txt = "\n".join(body)
    if "NOT AVAILABLE" in txt: return "skip"
    if re.search(r"\[(MISMATCH|ERROR|NOT SENT)\]", txt): return "fail"
    if "[UNTESTABLE]" in txt: return "warn"
    return "ok"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True)
    ap.add_argument("--start-ms", type=int, required=True)
    ap.add_argument("--steps", required=True, help="comma-separated step names, in run order")
    ap.add_argument("--out", required=True)
    ap.add_argument("--est-from", nargs="*", default=[])
    ap.add_argument("--poll", type=float, default=2.0)
    a = ap.parse_args()
    names = [s.strip() for s in a.steps.split(",") if s.strip()]
    est = estimates(a.est_from)
    fallback = round(sum(est.values()) / len(est)) if est else 0
    fin, last_end, last_key = {}, a.start_ms / 1000, None
    while True:
        try: lines = open(a.log).read().splitlines()
        except OSError: lines = []
        secs = sections(lines)
        exited = any(l.startswith("exit=") for l in lines)
        order = [n for n in names if n in secs]
        # a step is finished once the next header appears, or the run has exited
        done = {}
        for i, n in enumerate(order):
            nxt = i + 1 < len(order)
            if nxt or exited:
                done[n] = verdict(secs[n])
        for n in names:
            if n in done and n not in fin:
                now = time.time(); fin[n] = round(now - last_end); last_end = now
        key = (len(done), exited)
        if key != last_key:
            last_key = key
            steps, running_set = [], False
            for n in names:
                e = est.get(n, fallback)
                if n in done:
                    steps.append({"name": n, "state": done[n], "sec": fin.get(n, 0), "estSec": e})
                elif n in secs and not exited and not running_set:
                    running_set = True
                    steps.append({"name": n, "state": "running", "estSec": e, "startedAt": int(last_end * 1000)})
                else:
                    steps.append({"name": n, "state": "skip" if exited else "pending", "estSec": e})
            cur = next((s["name"] for s in steps if s["state"] == "running"), None)
            phase = (f"Finished: {len(done)} of {len(names)} steps" if exited
                     else (f"Running step {len(done) + 1} of {len(names)}: {cur}" if cur else "Starting…"))
            tail = [re.sub(r"\s+$", "", l)[:160] for l in lines
                    if re.match(r"===|\s+(OFF|ON|DENY|ALLOW)\b|\d+/\d+ checks|\[restore\]", l)][-8:]
            json.dump({"steps": steps, "phase": phase, "logTail": tail}, open(a.out, "w"))
            print(f"progress {len(done)}/{len(names)} exited={exited}", flush=True)
            if exited: break
        time.sleep(a.poll)

if __name__ == "__main__":
    main()
