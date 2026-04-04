# Dynamo Skips - Project Overview

## Purpose

This project provides a Streamlit dashboard for analyzing PyTorch Dynamo CPython test results from raw unittest output files.

Primary goals:
- Track pass/skip/fail behavior per module.
- Surface graph-break patterns from skipped tests.
- Compare run-level metrics across saved outputs.

## Current Status

The dashboard is implemented in `app.py` and supports both single-run and multi-run analysis.

Implemented:
- Parsing raw outputs from `data/all_tests_output_<commit>_<date>.txt`.
- Sidebar mode selector:
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
  -> app.py reads + parses with parse_pytest_output
  -> Streamlit dashboard visualizes per-run + cross-run metrics
```

## Graph Break Key Logic

Graph-break grouping uses the first line of each skip reason as the key.

Example key:
- `Unsupported function call`

This produces stable grouped categories even when the rest of the message contains long explanation or stack context.


## Run Locally

```bash
pixi install
pixi run streamlit run app.py
```

## Known Gaps / Next Improvements

- Tighten static typing in `app.py` (several editor type warnings are currently tolerated).
- Add tests for parser edge cases and graph-break key extraction.
- Add optional export of graph-break and module tables.
- Improve deploy docs with a pinned `requirements.txt` or container path.

## Deployment Options

- Streamlit Cloud (fastest path).
- Self-hosted Streamlit behind a reverse proxy (Nginx/Caddy) for TLS.

## Reference

- PyTorch Dynamo docs: https://pytorch.org/docs/main/dynamo/
