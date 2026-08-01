"""Reliability Auditor: an autonomous agent that stress-tests onchain execution.

The agent is given a goal, a set of tools, and no script. It decides what to probe,
executes real transactions through KeeperHub, reads back what actually happened, and
judges whether the platform's guarantees held. Findings are its own conclusions, not
hardcoded assertions.

The distinction that matters: the chaos harness runs fixed scenarios. This agent
chooses which claims are worth testing, runs them, interprets ambiguous results, and
decides when it has enough evidence to stop. The harness is its tooling.

Run:
    export GROQ_API_KEY=...  KEEPERHUB_API_KEY=kh_...
    python3 agent/auditor.py --budget 8
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "chaos"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "keeperhub"))

import scenarios as S  # noqa: E402
from kh import call_tool  # noqa: E402

WALLET = "0x22eC6D712F60Fb032b307D98E1c245af8401d950"

SYSTEM = """You are a reliability auditor for onchain AI agent execution.

KeeperHub claims to be a reliable execution layer for agents. Your job is to find out
where that holds and where it does not, by running real probes against live
infrastructure and reading back what actually happened onchain.

Cover the whole surface. Call list_probes first, then run EVERY probe it lists before
reporting. A two-probe audit is not an audit: a claim you never tested is a claim you
cannot speak to, and the passes matter as much as the failures.

Then:
- Prefer probes that could plausibly come back clean. A test that can only fail is not
  evidence, it is theatre.
- When a probe reports a FINDING, verify it before believing it. Read the execution
  record. Check whether the evidence actually supports the claim.
- A PASS is a real result and worth reporting. Do not manufacture problems.
- When two probes disagree or a result is ambiguous, say so rather than picking the
  more dramatic reading.

Call run_probe to execute a probe, get_execution_detail to inspect any execution id or
transaction, and submit_report exactly once when you are done. Every claim in your
report must cite an execution id or transaction hash you actually observed."""


def tool_defs(names):
    return [
        {"type": "function", "function": {
            "name": "list_probes",
            "description": "List available probes with the claim each one tests.",
            "parameters": {"type": "object", "properties": {}}}},
        {"type": "function", "function": {
            "name": "run_probe",
            "description": ("Run one probe against live KeeperHub. Executes real "
                            "transactions on Sepolia. Returns verdict, detail, evidence."),
            "parameters": {"type": "object", "properties": {
                "name": {"type": "string", "enum": names}}, "required": ["name"]}}},
        {"type": "function", "function": {
            "name": "get_execution_detail",
            "description": "Fetch KeeperHub's own record for an execution id, to verify a claim.",
            "parameters": {"type": "object", "properties": {
                "execution_id": {"type": "string"}}, "required": ["execution_id"]}}},
        {"type": "function", "function": {
            "name": "submit_report",
            "description": "Submit final findings. Call exactly once, at the end.",
            "parameters": {"type": "object", "properties": {
                "summary": {"type": "string"},
                "findings": {"type": "array", "items": {"type": "object", "properties": {
                    "probe": {"type": "string"}, "severity": {"type": "string"},
                    "claim": {"type": "string"}, "evidence": {"type": "string"},
                    "verified": {"type": "boolean"}}}},
                "passes": {"type": "array", "items": {"type": "string"}},
            }, "required": ["summary", "findings"]}}},
    ]


class Auditor:
    def __init__(self, model: str, budget: int):
        from openai import OpenAI
        key = os.environ.get("GROQ_API_KEY")
        if not key:
            raise SystemExit("error: set GROQ_API_KEY")
        self.client = OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1")
        self.model, self.budget = model, budget
        self.probes = {f.__name__: f for f in S.SCENARIOS}
        self.log, self.report = [], None
        # probe -> True once an execution id from it has been fetched back
        self.verified = {}

    def _dispatch(self, name: str, args: dict) -> str:
        if name == "list_probes":
            return json.dumps([{"name": n, "tests": (f.__doc__ or "").strip().split("\n")[0]}
                               for n, f in self.probes.items()])
        if name == "run_probe":
            fn = self.probes.get(args.get("name"))
            if not fn:
                return json.dumps({"error": f"unknown probe {args.get('name')!r}"})
            t0 = time.time()
            try:
                r = fn(WALLET)
            except Exception as e:  # a probe blowing up is data, not a crash
                return json.dumps({"verdict": "ERROR", "detail": f"{type(e).__name__}: {e}"[:300]})
            self.log.append(r)
            print(f"    probe {r.name}: {r.verdict} ({time.time()-t0:.0f}s)", flush=True)
            return json.dumps({"probe": r.name, "verdict": r.verdict, "severity": r.severity,
                               "claim": r.claim, "detail": r.detail, "evidence": r.evidence})
        if name == "get_execution_detail":
            eid = str(args.get("execution_id", ""))
            try:
                out = call_tool("get_direct_execution_status", {"execution_id": eid})
            except Exception as e:
                return json.dumps({"error": str(e)[:200],
                                   "hint": "Use an execution id returned by a probe."})
            for r in self.log:
                if eid in {str(x) for x in r.evidence}:
                    self.verified[r.name] = True
            return out[:1200]
        if name == "submit_report":
            problems = self._validate(args)
            if problems:
                # Reject and make the agent try again. An auditor that can assert
                # things it never observed is worth nothing, so every claim is
                # checked against what actually ran before the report is accepted.
                print(f"    report REJECTED: {len(problems)} problem(s)", flush=True)
                # Hand back exactly what a valid report looks like from what has
                # already run. Without this the model re-runs probes to "get more
                # evidence" and burns its budget, when the evidence was never the
                # problem: the citations were.
                template = {
                    "summary": "<one paragraph on what held and what did not>",
                    "findings": [
                        {"probe": r.name, "severity": r.severity, "claim": r.claim,
                         "evidence": ", ".join(str(e) for e in r.evidence),
                         "verified": bool(self.verified.get(r.name))}
                        for r in self.log if r.verdict == "FINDING"],
                    "passes": [r.name for r in self.log if r.verdict == "PASS"],
                }
                return json.dumps({
                    "accepted": False, "problems": problems,
                    "instruction": "Do NOT run more probes. The evidence is not the "
                                   "problem, your citations are. Call submit_report "
                                   "again using valid_report below, replacing only "
                                   "summary and claim with your own wording.",
                    "valid_report": template})
            self.report = args
            return json.dumps({"accepted": True})
        return json.dumps({"error": "unknown tool"})

    def _validate(self, rep: dict) -> list:
        """Reject reports that assert more than the agent actually observed."""
        problems = []
        ran = {r.name: r for r in self.log}
        seen_ids = {str(e) for r in self.log for e in r.evidence}

        for f in rep.get("findings", []):
            probe = f.get("probe", "")
            if probe not in ran:
                problems.append(f"finding cites probe {probe!r}, which was never run")
                continue
            if ran[probe].verdict != "FINDING":
                problems.append(
                    f"{probe} returned {ran[probe].verdict}, so it cannot be a finding")
            ev = str(f.get("evidence", ""))
            if not ev or not any(s and s in ev for s in seen_ids):
                problems.append(
                    f"{probe}: evidence {ev[:40]!r} was not returned by any probe. "
                    f"Real evidence for it: {ran[probe].evidence}")
            if f.get("verified") and not self.verified.get(probe):
                problems.append(
                    f"{probe} is marked verified but get_execution_detail was never "
                    "called successfully on its evidence")

        for p in rep.get("passes", []):
            if p not in ran:
                problems.append(f"passes lists {p!r}, which was never run")
            elif ran[p].verdict != "PASS":
                problems.append(f"passes lists {p!r} but it returned {ran[p].verdict}")

        unrun = [n for n in self.probes if n not in ran]
        if unrun:
            problems.append(
                f"{len(unrun)} probe(s) were never run: {unrun}. Run every probe "
                "before reporting; an untested claim cannot be spoken to.")

        missing = [n for n, r in ran.items()
                   if r.verdict == "FINDING"
                   and n not in {f.get("probe") for f in rep.get("findings", [])}]
        if missing:
            problems.append(f"probes returned FINDING but are absent from the report: {missing}")
        return problems

    def run(self, goal: str) -> dict | None:
        msgs = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": goal}]
        tools = tool_defs(list(self.probes))

        for step in range(self.budget):
            r = self.client.chat.completions.create(
                model=self.model, messages=msgs, tools=tools, temperature=0.3)
            m = r.choices[0].message
            msgs.append(m.model_dump(exclude_none=True))

            if not m.tool_calls:
                if m.content:
                    print(f"  [agent] {m.content[:300]}", flush=True)
                # Nudge once toward a decision rather than ending on chatter.
                msgs.append({"role": "user", "content":
                             "Continue: run another probe or call submit_report."})
                continue

            for tc in m.tool_calls:
                args = json.loads(tc.function.arguments or "{}")
                print(f"  [step {step+1}] {tc.function.name}({str(args)[:70]})", flush=True)
                out = self._dispatch(tc.function.name, args)
                msgs.append({"role": "tool", "tool_call_id": tc.id,
                             "name": tc.function.name, "content": out})
            if self.report:
                return self.report
        return self.report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="llama-3.3-70b-versatile")
    ap.add_argument("--budget", type=int, default=8, help="max reasoning steps")
    ap.add_argument("--goal", default=(
        "Audit KeeperHub's execution guarantees. Probe both the idempotency surface "
        "and the read-then-act surface. Verify at least one finding against "
        "KeeperHub's own execution record before reporting it. Then submit_report."))
    ap.add_argument("--out", default="agent/last_audit.json")
    a = ap.parse_args()

    print(f"Reliability Auditor | model={a.model} budget={a.budget}\n")
    ag = Auditor(a.model, a.budget)
    rep = ag.run(a.goal)

    if not rep:
        print("\nagent ended without submitting a report (budget exhausted)")
        return 1

    print("\n" + "=" * 74)
    print("AGENT AUDIT REPORT")
    print("=" * 74)
    print(f"\n{rep.get('summary','')}\n")
    for f in rep.get("findings", []):
        mark = "verified" if f.get("verified") else "unverified"
        print(f"[{f.get('severity','?')}] {f.get('probe','?')} ({mark})")
        print(f"   {f.get('claim','')}")
        print(f"   evidence: {f.get('evidence','')}\n")
    if rep.get("passes"):
        print("held up:", ", ".join(rep["passes"]))

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump({"report": rep, "probes": [r.__dict__ for r in ag.log]},
              open(a.out, "w"), indent=2)
    print(f"\nwritten to {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
