"""Build the static scoreboard from real harness output.

Reads chaos/last_run.json and emits site/index.html. No backend, no API keys in the
page: the numbers are baked from an actual run so the published page cannot drift from
what the harness measured.
"""
import json, os, re, datetime, html

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
run = json.load(open(os.path.join(ROOT, "chaos", "last_run.json")))

SEV = {"HIGH": "high", "MEDIUM": "med", "-": "none"}
TX = re.compile(r"^0x[0-9a-fA-F]{64}$")

def ev(items):
    out = []
    for e in items or []:
        e = str(e)
        if TX.match(e):
            out.append(f'<a href="https://sepolia.etherscan.io/tx/{e}" target="_blank" '
                       f'rel="noopener">{e[:10]}…{e[-6:]}</a>')
        else:
            out.append(f"<code>{html.escape(e)}</code>")
    return " ".join(out) or "<span class=dim>-</span>"

rows, findings = [], []
for r in run:
    v, sev = r["verdict"], r.get("severity", "-")
    rows.append(f"""<tr class="{v.lower()}">
      <td><code>{html.escape(r['name'])}</code></td>
      <td><span class="v {v.lower()}">{v}</span></td>
      <td><span class="s {SEV.get(sev,'none')}">{sev}</span></td>
      <td>{html.escape(r.get('claim',''))}</td></tr>""")
    if v == "FINDING":
        findings.append(f"""<article class="{SEV.get(sev,'none')}">
          <h3><span class="s {SEV.get(sev,'none')}">{sev}</span> <code>{html.escape(r['name'])}</code></h3>
          <p class="claim">Claim tested: {html.escape(r.get('claim',''))}</p>
          <p>{html.escape(r.get('detail',''))}</p>
          <p class="ev">{ev(r.get('evidence'))}</p></article>""")

n, f = len(run), len(findings)
p = n - f
hi = sum(1 for r in run if r.get("severity") == "HIGH")
built = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

open(os.path.join(ROOT, "site", "index.html"), "w").write(f"""<!doctype html>
<html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Does the execution layer hold?</title>
<style>
:root{{--bg:#0b0e14;--fg:#e6e9ef;--dim:#8b93a7;--line:#1e2430;--card:#111725;
--high:#ff6b6b;--med:#ffb454;--ok:#3ddc97;--link:#6cb6ff}}
@media(prefers-color-scheme:light){{:root{{--bg:#fbfcfd;--fg:#131720;--dim:#5b6478;
--line:#e3e8ef;--card:#fff;--link:#0b62d6}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.6 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}}
.wrap{{max-width:1000px;margin:0 auto;padding:48px 20px 80px}}
h1{{font-size:clamp(28px,5vw,44px);line-height:1.15;margin:0 0 12px;letter-spacing:-.02em}}
.sub{{color:var(--dim);max-width:64ch;margin:0 0 36px}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px;margin:0 0 40px}}
.stat{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}}
.stat b{{display:block;font-size:30px;line-height:1.1;font-variant-numeric:tabular-nums}}
.stat span{{color:var(--dim);font-size:13px}}
.scroll{{overflow-x:auto;border:1px solid var(--line);border-radius:12px;background:var(--card)}}
table{{border-collapse:collapse;width:100%;min-width:640px;font-size:14px}}
th,td{{text-align:left;padding:11px 14px;border-bottom:1px solid var(--line)}}
th{{color:var(--dim);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.06em}}
tr:last-child td{{border-bottom:0}}
code{{font:13px ui-monospace,SFMono-Regular,Menlo,monospace}}
.v{{font-size:11px;font-weight:700;letter-spacing:.06em;padding:3px 8px;border-radius:99px}}
.v.finding{{background:rgba(255,107,107,.14);color:var(--high)}}
.v.pass{{background:rgba(61,220,151,.14);color:var(--ok)}}
.s{{font-size:11px;font-weight:700;letter-spacing:.05em}}
.s.high{{color:var(--high)}} .s.med{{color:var(--med)}} .s.none{{color:var(--dim)}}
h2{{margin:52px 0 6px;font-size:22px;letter-spacing:-.01em}}
.lede{{color:var(--dim);margin:0 0 20px}}
article{{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--dim);
border-radius:10px;padding:18px 20px;margin:0 0 14px}}
article.high{{border-left-color:var(--high)}} article.med{{border-left-color:var(--med)}}
article h3{{margin:0 0 8px;font-size:16px}}
.claim{{color:var(--dim);font-size:14px;margin:0 0 8px}}
article p{{margin:0 0 8px}}
.ev{{font-size:13px;color:var(--dim);margin:12px 0 0!important}}
a{{color:var(--link)}}
.dim{{color:var(--dim)}}
footer{{margin-top:56px;padding-top:20px;border-top:1px solid var(--line);
color:var(--dim);font-size:13px}}
</style></head><body><div class=wrap>

<h1>Does the execution layer hold?</h1>
<p class=sub>KeeperHub is the execution and reliability layer for onchain agents.
Nothing let anyone check that claim, so we built something that tries to break it.
Every result below comes from real transactions on live infrastructure. Every finding
cites evidence you can verify yourself.</p>

<div class=stats>
  <div class=stat><b>{n}</b><span>scenarios</span></div>
  <div class=stat><b>{f}</b><span>findings</span></div>
  <div class=stat><b>{hi}</b><span>high severity</span></div>
  <div class=stat><b>{p}</b><span>passed</span></div>
</div>

<div class=scroll><table>
<thead><tr><th>scenario</th><th>verdict</th><th>sev</th><th>claim tested</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>

<h2>Findings</h2>
<p class=lede>Each states a guarantee a builder would reasonably assume, and what
happened when we leaned on it.</p>
{''.join(findings)}

<h2>What held up</h2>
<p class=lede>{p} of {n} scenarios passed, and most were written expecting a failure.
Dedupe is atomic under concurrent retries. Idempotency keys are bound to payloads, so
reuse with a changed payload is refused rather than silently returning a stale result.
Reverts report as failures with a reason. Unaffordable sends are refused before
submission with no nonce consumed. Concurrent transfers all land, so a busy agent does
not head-of-line block itself. This is a test suite, not a hit piece.</p>

<footer>Built {built} from <code>chaos/last_run.json</code>.
Transactions on Ethereum Sepolia. Gas sponsored by KeeperHub.</footer>
</div></body></html>""")
print("wrote site/index.html")
