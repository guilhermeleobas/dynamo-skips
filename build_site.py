#!/usr/bin/env python3
"""
Build the static dashboard (GitHub Pages) from the raw test logs in data/.

Parses every data/all_tests_output_*.txt once and writes:

    site/index.html, site/app.js, site/style.css   (copied from web/)
    site/data/runs.json                            (run index + per-run module summaries)
    site/data/runs/<run id>.json                   (per-test rows, loaded on demand)

Usage:
    python build_site.py [--out site]
"""

import argparse
import json
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path

from cpython_test_runner import parse_pytest_output

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
WEB_DIR = ROOT / "web"
RAW_PREFIX = "all_tests_output_"
RAW_SUFFIX = ".txt"

# Short status codes keep the per-run JSON small.
STATUS_CODES = {"PASSED": "P", "SKIPPED": "S", "FAILED": "F", "ERROR": "E"}


def parse_run_date_and_commit(path: Path) -> tuple[str, str]:
    """
    Return (YYYYMMDD, commit_or_label) from all_tests_output_<commit>_<date>.txt.
    If the name does not match, use file mtime for the date and the stem as label.
    """
    name = path.name
    if name.startswith(RAW_PREFIX) and name.endswith(RAW_SUFFIX):
        core = name[len(RAW_PREFIX) : -len(RAW_SUFFIX)]
        i = core.rfind("_")
        if i != -1:
            commit_part, date_part = core[:i], core[i + 1 :]
            if len(date_part) == 8 and date_part.isdigit():
                return date_part, commit_part or "unknown"
    m = datetime.fromtimestamp(path.stat().st_mtime)
    return m.strftime("%Y%m%d"), path.stem


def format_run_date(yyyymmdd: str) -> str:
    try:
        return datetime.strptime(yyyymmdd, "%Y%m%d").date().isoformat()
    except ValueError:
        return yyyymmdd


def graph_break_key(reason: str) -> str:
    """Use the first reason line as the graph-break key (e.g. Unsupported function call)."""
    text = (reason or "").replace("\\n", "\n").strip()
    if not text:
        return "Unknown"
    first_line = text.split("\n", 1)[0].strip().strip("'\"")
    return first_line or "Unknown"


def norm_module(name: str) -> str:
    """Use full CPython test file stems (test_set) everywhere."""
    return name if name.startswith("test_") else f"test_{name}"


def build_run(path: Path) -> tuple[dict, dict | None]:
    """Return (index entry, detail payload or None if nothing parsed)."""
    ymd, commit = parse_run_date_and_commit(path)
    entry = {
        "id": path.stem.removeprefix(RAW_PREFIX),
        "ymd": ymd,
        "date": format_run_date(ymd),
        "commit": commit,
        "file": path.name,
        "parse_ok": False,
    }
    text = path.read_text(encoding="utf-8", errors="replace")
    summary, details = parse_pytest_output(text, warn_on_count_mismatch=False)
    if not summary:
        return entry, None

    summary = {norm_module(k): v for k, v in summary.items()}
    details = {norm_module(k): v for k, v in details.items()}
    modules = sorted(summary)

    entry["parse_ok"] = True
    entry["modules"] = {
        m: {k: summary[m].get(k, 0) for k in ("total", "passed", "skipped", "failed", "error")}
        for m in modules
    }
    for k in ("total", "passed", "skipped", "failed", "error"):
        entry[k] = sum(s[k] for s in entry["modules"].values())

    # Reasons repeat heavily (same graph break hit by many tests): store each once.
    reasons: list[str] = []
    reason_idx: dict[str, int] = {}
    tests = []
    breaks: Counter[str] = Counter()
    for mi, m in enumerate(modules):
        for t in details.get(m, []):
            r = t.get("reason") or ""
            if r not in reason_idx:
                reason_idx[r] = len(reasons)
                reasons.append(r)
            tests.append([mi, t["test_name"], STATUS_CODES.get(t["status"], "E"), reason_idx[r]])
            if t["status"] == "SKIPPED" and r.strip():
                breaks[graph_break_key(r)] += 1

    entry["graph_breaks"] = breaks.most_common()
    payload = {"modules": modules, "reasons": reasons, "tests": tests}
    return entry, payload


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT / "site")
    args = ap.parse_args()
    out: Path = args.out

    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(WEB_DIR, out)
    (out / "data" / "runs").mkdir(parents=True)

    runs = []
    for path in sorted(DATA_DIR.glob(f"{RAW_PREFIX}*{RAW_SUFFIX}")):
        entry, payload = build_run(path)
        runs.append(entry)
        if payload is not None:
            (out / "data" / "runs" / f"{entry['id']}.json").write_text(
                json.dumps(payload, separators=(",", ":"))
            )
        print(f"{'ok  ' if entry['parse_ok'] else 'FAIL'} {path.name}")

    runs.sort(key=lambda r: (r["ymd"], r["commit"]), reverse=True)
    index = {"generated": datetime.now().astimezone().isoformat(timespec="seconds"), "runs": runs}
    (out / "data" / "runs.json").write_text(json.dumps(index, separators=(",", ":")))
    print(f"Wrote {len(runs)} runs to {out}")


if __name__ == "__main__":
    main()
