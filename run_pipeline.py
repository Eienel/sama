"""End to end: audit, score, publish onchain, rebuild the scoreboard.

One command runs the whole product:

  1. the agent decides what to probe and runs it against live KeeperHub
  2. the full harness executes real transactions and records verdicts
  3. the score is published to the ERC-8004 Validation Registry, onchain
  4. docs and the static scoreboard are regenerated from that same run

Every stage reads the artefacts the previous stage wrote, so the published number,
the page, and the README cannot disagree with what actually executed.

    export KEEPERHUB_API_KEY=kh_...  GROQ_API_KEY=...
    python3 run_pipeline.py                 # everything
    python3 run_pipeline.py --skip-agent    # harness onward
    python3 run_pipeline.py --skip-publish  # no onchain write
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def step(n: int, total: int, title: str) -> None:
    print(f"\n[{n}/{total}] {title}", flush=True)


def run(cmd: list, cwd: str | None = None, required: bool = True) -> bool:
    r = subprocess.run(cmd, cwd=cwd or ROOT, capture_output=True, text=True)
    tail = (r.stdout or r.stderr).strip().splitlines()
    for line in tail[-14:]:
        print("   ", line)
    if r.returncode != 0:
        print(f"    exit {r.returncode}")
        if required:
            raise SystemExit(f"pipeline halted: {' '.join(cmd[:3])} failed")
        print("    continuing (optional stage)")
    return r.returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-agent", action="store_true")
    ap.add_argument("--skip-publish", action="store_true")
    ap.add_argument("--budget", type=int, default=6)
    a = ap.parse_args()

    if not os.environ.get("KEEPERHUB_API_KEY"):
        raise SystemExit("error: set KEEPERHUB_API_KEY")

    total, n, t0 = 5, 0, time.time()

    n += 1
    step(n, total, "Agent selects and runs probes")
    if a.skip_agent:
        print("    skipped")
    elif not os.environ.get("GROQ_API_KEY"):
        print("    no GROQ_API_KEY, skipping the reasoning stage")
    else:
        run([PY, "agent/auditor.py", "--budget", str(a.budget)], required=False)

    n += 1
    step(n, total, "Full harness against live KeeperHub")
    run([PY, "run.py"], cwd=os.path.join(ROOT, "chaos"))

    n += 1
    step(n, total, "Publish verdict to ERC-8004 Validation Registry")
    if a.skip_publish:
        print("    skipped")
    else:
        run([PY, "validator/publish.py", "--publish"], required=False)

    n += 1
    step(n, total, "Sync docs from the run")
    run([PY, "chaos/sync_readme.py"])

    n += 1
    step(n, total, "Rebuild the scoreboard")
    run([PY, "site/build.py"])

    run_data = json.load(open(os.path.join(ROOT, "chaos", "last_run.json")))
    findings = [r for r in run_data if r["verdict"] == "FINDING"]
    high = [r for r in findings if r.get("severity") == "HIGH"]
    st_path = os.path.join(ROOT, "validator", "state.json")
    st = json.load(open(st_path)) if os.path.exists(st_path) else {}
    pub = st.get("last_publish", {})

    print("\n" + "=" * 70)
    print(f"PIPELINE COMPLETE in {time.time()-t0:.0f}s")
    print("=" * 70)
    print(f"  scenarios   {len(run_data)}")
    print(f"  findings    {len(findings)} ({len(high)} HIGH)")
    print(f"  passed      {len(run_data)-len(findings)}")
    if pub:
        print(f"  score       {pub.get('score')}/100 published onchain")
        print(f"  response tx {pub.get('response_tx')}")
    print("  scoreboard  site/index.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
