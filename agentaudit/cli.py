"""agentaudit: run the suite against any execution layer.

    python3 -m agentaudit.cli --adapter mock          # offline, no key needed
    python3 -m agentaudit.cli --adapter keeperhub     # live, needs KEEPERHUB_API_KEY
"""
import argparse, json, sys
from . import scenarios  # noqa: F401  registers them
from .core import run
from .adapters import KeeperHubAdapter, LocalEVMAdapter, MockAdapter


def build(name: str, chain: str):
    if name == "keeperhub":
        return KeeperHubAdapter(chain_id=chain)
    if name == "mock":
        return MockAdapter()
    if name == "mock-broken":
        return MockAdapter(dedupe=False, honest_errors=False)
    if name == "local-evm":
        return LocalEVMAdapter()
    raise SystemExit(f"unknown adapter {name!r}")


def compare(names: list, chain: str, only=None) -> int:
    """Run the same suite against several execution layers and show the difference.

    This is the question a builder actually has: not "is this provider perfect", but
    "what does using it buy me over signing transactions myself". A raw signer is the
    honest baseline, since that is what you get with no execution layer at all.
    """
    runs = {}
    for n in names:
        print(f"\n--- {n} ---", flush=True)
        try:
            runs[n] = {r.name: r for r in run(build(n, chain), only=only)}
        except Exception as e:
            print(f"    adapter unavailable: {str(e)[:120]}")

    if len(runs) < 2:
        print("\nneed at least two working adapters to compare")
        return 1

    scenarios = sorted({s for r in runs.values() for s in r})
    w = max(len(s) for s in scenarios) + 2
    print("\n" + "=" * (w + 14 * len(runs)))
    print("COMPARISON".ljust(w) + "".join(n[:12].ljust(14) for n in runs))
    print("=" * (w + 14 * len(runs)))
    for s in scenarios:
        row = s.ljust(w)
        for n in runs:
            r = runs[n].get(s)
            row += (("PASS" if r.verdict == "PASS" else
                     f"FINDING/{r.severity[:1]}") if r else "-").ljust(14)
        print(row)

    print("-" * (w + 14 * len(runs)))
    print("passed".ljust(w) + "".join(
        f"{sum(1 for r in v.values() if r.verdict=='PASS')}/{len(v)}".ljust(14)
        for v in runs.values()))

    # The interesting cell is where one layer protects you and another does not.
    base = names[0]
    if base in runs:
        gained = [s for s in scenarios
                  if runs[base].get(s) and runs[base][s].verdict == "FINDING"
                  and any(n != base and runs[n].get(s) and runs[n][s].verdict == "PASS"
                          for n in runs)]
        if gained:
            print(f"\nGuarantees another layer provides that {base} does not:")
            for s in gained:
                who = [n for n in runs if n != base and runs[n].get(s)
                       and runs[n][s].verdict == "PASS"]
                print(f"  {s:<28} held by: {', '.join(who)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--adapter", default="mock",
                    choices=("mock", "mock-broken", "local-evm", "keeperhub"))
    ap.add_argument("--chain", default="11155111")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--json", metavar="PATH")
    ap.add_argument("--compare", nargs="*", metavar="ADAPTER",
                    help="run the suite against several layers and diff them")
    a = ap.parse_args()

    if a.compare is not None:
        return compare(a.compare or ["local-evm", "keeperhub"], a.chain, a.only)

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
