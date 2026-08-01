"""agentaudit: run the suite against any execution layer.

    python3 -m agentaudit.cli --adapter mock          # offline, no key needed
    python3 -m agentaudit.cli --adapter keeperhub     # live, needs KEEPERHUB_API_KEY
"""
import argparse, json, sys
from . import scenarios  # noqa: F401  registers them
from .core import run
from .adapters import KeeperHubAdapter, MockAdapter


def build(name: str, chain: str):
    if name == "keeperhub":
        return KeeperHubAdapter(chain_id=chain)
    if name == "mock":
        return MockAdapter()
    if name == "mock-broken":
        return MockAdapter(dedupe=False, honest_errors=False)
    raise SystemExit(f"unknown adapter {name!r}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--adapter", default="mock",
                    choices=("mock", "mock-broken", "keeperhub"))
    ap.add_argument("--chain", default="11155111")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--json", metavar="PATH")
    a = ap.parse_args()

    adapter = build(a.adapter, a.chain)
    print(f"agentaudit | adapter={adapter.name} chain={adapter.chain_id}\n")
    res = run(adapter, only=a.only)

    f = [r for r in res if r.verdict == "FINDING"]
    hi = [r for r in f if r.severity == "HIGH"]
    print("\n" + "=" * 66)
    print(f"{len(f)} finding(s) of {len(res)} scenarios | {len(hi)} HIGH | "
          f"{len(res)-len(f)} passed")
    print("=" * 66)
    for r in f:
        print(f"\n[{r.severity}] {r.name}\n   {r.detail}")
        if r.evidence:
            print(f"   evidence: {', '.join(map(str, r.evidence))}")
    if a.json:
        json.dump([r.__dict__ for r in res], open(a.json, "w"), indent=2)
        print(f"\nwritten to {a.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
