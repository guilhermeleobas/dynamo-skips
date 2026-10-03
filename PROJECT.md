# Dynamo Skips - Project Overview

## Purpose

This project provides a static dashboard (GitHub Pages) for analyzing PyTorch Dynamo CPython test results from raw unittest output files.

Primary goals:
- Track pass/skip/fail behavior per module.
- Surface graph-break patterns from skipped tests.
- Compare run-level metrics across saved outputs.

## Current Status

`build_site.py` pre-parses every log into JSON; the page in `web/` (Bootstrap + DataTables + Plotly.js) renders it client-side. Supports both single-run and multi-run analysis.

Implemented:
- Parsing raw outputs from `data/all_tests_output_<commit>_<date>.txt`.
- View selector:
  - `Individual run`
  - `All runs summary`
- Individual run views:
  - `Overview` tab with module-level charts and summary table.
  - `Graph breaks` tab with grouped key statistics.
  - `Module details` tab with status filters and search.
- All-runs summary view:
  - Aggregate metrics across parsed runs.
  - Pass-rate trend by date.
  - Stacked run counts (passed/skipped/failed).
  - Run table with parse status and rates.

## Data Flow

```text
cpython_test_runner.py
  -> raw output files in data/
  -> build_site.py parses with parse_pytest_output into site/data/*.json
  -> GitHub Actions deploys site/ to GitHub Pages on push to main
```

## Graph Break Key Logic

Graph-break grouping uses the first line of each skip reason as the key.

Example key:
- `Unsupported function call`

This produces stable grouped categories even when the rest of the message contains long explanation or stack context.


## Run Locally

```bash
pixi run serve   # builds site/ and serves it on http://localhost:8000
```

## Known Gaps / Next Improvements

- Add tests for parser edge cases and graph-break key extraction.
- Add optional export of graph-break and module tables.

## Deployment Options

- GitHub Pages via `.github/workflows/pages.yml` (Settings → Pages → Source: GitHub Actions).
- Any static host: serve the output of `python build_site.py`.

## Reference

- PyTorch Dynamo docs: https://pytorch.org/docs/main/dynamo/
