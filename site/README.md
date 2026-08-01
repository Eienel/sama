# Scoreboard

Static page showing what the chaos harness found. No backend and no keys in the page:
`build.py` bakes the numbers from `chaos/last_run.json`, so the published page cannot
drift from what the harness actually measured.

```bash
cd chaos && python3 run.py     # produces chaos/last_run.json
python3 site/build.py          # regenerates site/index.html
```

## Deploying to Vercel

The output is a single static file, so no framework or build step is needed.

```bash
npm i -g vercel
vercel deploy site --prod
```

Or point a Vercel project at this repo with root directory `site`, framework preset
"Other", and no build command. `vercel.json` sets `cleanUrls`.

Regenerate and redeploy after any harness run so the page keeps matching the evidence.
