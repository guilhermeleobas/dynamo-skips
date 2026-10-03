# 🚀 Dynamo Skips App

Dashboard for analyzing PyTorch Dynamo CPython test results and graph break reasons.

## Overview

**Live dashboard:** https://guilhermeleobas.github.io/dynamo-skips/

A static site (GitHub Pages) with interactive views of:
- Per-run results: pass/skip/fail by module, graph break reasons, per-test details with search
- Trends across all saved runs

Built with [Bootstrap](https://getbootstrap.com/), [DataTables](https://datatables.net/) and [Plotly.js](https://plotly.com/javascript/), all loaded from CDNs.

## Running CPython Tests

Generate fresh test data using the test runner script:

```bash
pixi run test-runner
```

`run.sh` automates the weekly run: it builds PyTorch at `viable/strict`, runs the tests, and commits/pushes the new file under `data/`.

## Data Sources

The dashboard reads from:
- `data/all_tests_output_*.txt` - Full test output logs

**Filename Format**: `all_tests_output_<11-char-commit>_<YYYYMMDD>.txt`

## Building the site

`build_site.py` parses every log in `data/` once and writes a static site to `site/`:

- `site/index.html`, `app.js`, `style.css` - copied from `web/`
- `site/data/runs.json` - run index with per-module summaries and graph break counts
- `site/data/runs/<run>.json` - per-test rows, fetched only when a run's details are opened

Preview locally:

```bash
pixi run serve
```

Then open http://localhost:8000.

## Deployment

`.github/workflows/pages.yml` rebuilds and deploys the site on every push to `main`, so the weekly `run.sh` push also updates the dashboard. One-time setup: in the repo settings, under **Pages → Build and deployment**, set **Source** to **GitHub Actions**.

## License

MIT
