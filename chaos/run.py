"""Run the chaos scenarios and print a scoreboard."""
import sys, time, json, traceback
from scenarios import SCENARIOS, Result

WALLET = "0x22eC6D712F60Fb032b307D98E1c245af8401d950"

def main():
    only = sys.argv[1:] or None
    results = []
    for fn in SCENARIOS:
        if only and fn.__name__ not in only:
            continue
        print(f"  running {fn.__name__} ...", flush=True)
        try:
            results.append(fn(WALLET))
        except Exception as e:
            results.append(Result(fn.__name__, "", "ERROR", f"{type(e).__name__}: {e}"[:200]))
        time.sleep(1)

    print("\n" + "="*78)
    print("KEEPERHUB CHAOS HARNESS")
    print("="*78)
    print(f"{'scenario':<24}{'verdict':<10}{'sev':<8}claim")
    print("-"*78)
    for r in results:
        print(f"{r.name:<24}{r.verdict:<10}{r.severity:<8}{r.claim[:38]}")
    print("-"*78)
    f = [r for r in results if r.verdict == "FINDING"]
    print(f"\n{len(f)} finding(s) of {len(results)} scenarios\n")
    for r in f:
        print(f"[{r.severity}] {r.name}")
        print(f"   claim: {r.claim}")
        print(f"   {r.detail}")
        if r.evidence: print(f"   evidence: {', '.join(map(str,r.evidence))}")
        print()
    for r in results:
        if r.verdict == "ERROR": print(f"[error] {r.name}: {r.detail}")
    json.dump([r.__dict__ for r in results], open("last_run.json","w"), indent=2)

main()
