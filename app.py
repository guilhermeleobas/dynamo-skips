from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from cpython_test_runner import parse_pytest_output

st.set_page_config(page_title="Dynamo Skips Dashboard", layout="wide")

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
RAW_GLOB = "all_tests_output_*.txt"


def _list_raw_outputs() -> list[Path]:
    if not DATA_DIR.is_dir():
        return []
    files = list(DATA_DIR.glob(RAW_GLOB))
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def _parse_run_date_and_commit(path: Path) -> tuple[str, str]:
    """
    Return (YYYYMMDD, commit_or_label) from all_tests_output_<commit>_<date>.txt.
    If the name does not match, use file mtime for the date and the stem as label.
    """
    name = path.name
    prefix = "all_tests_output_"
    suffix = ".txt"
    if name.startswith(prefix) and name.endswith(suffix):
        core = name[len(prefix) : -len(suffix)]
        i = core.rfind("_")
        if i != -1:
            commit_part, date_part = core[:i], core[i + 1 :]
            if len(date_part) == 8 and date_part.isdigit():
                return date_part, commit_part or "unknown"
    m = datetime.fromtimestamp(path.stat().st_mtime)
    return m.strftime("%Y%m%d"), path.stem


def _files_grouped_by_run_date(files: list[Path]) -> dict[str, list[Path]]:
    by_date: dict[str, list[Path]] = defaultdict(list)
    for p in files:
        ymd, _ = _parse_run_date_and_commit(p)
        by_date[ymd].append(p)
    for ymd in by_date:
        by_date[ymd].sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return dict(by_date)


def _format_run_date(yyyymmdd: str) -> str:
    try:
        d = datetime.strptime(yyyymmdd, "%Y%m%d").date()
        return d.isoformat()
    except ValueError:
        return yyyymmdd


def _explanation_snippet(reason: str, max_len: int = 120) -> str:
    if not reason:
        return ""
    text = reason.replace("\\n", "\n")
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("Explanation:"):
            rest = line[len("Explanation:") :].strip()
            return (rest[:max_len] + "…") if len(rest) > max_len else rest
    compact = " ".join(text.split())
    return (compact[:max_len] + "…") if len(compact) > max_len else compact


def _graph_break_key(reason: str) -> str:
    """Use the first reason line as the graph-break key (e.g. Unsupported function call)."""
    if not reason:
        return "Unknown"
    text = reason.replace("\\n", "\n").strip()
    if not text:
        return "Unknown"

    first_line = text.split("\n", 1)[0].strip().strip("'\"")
    return first_line or "Unknown"


@st.cache_data
def load_parsed_output(path_str: str):
    path = Path(path_str)
    if not path.is_file():
        return None, None, path.name
    text = path.read_text(encoding="utf-8", errors="replace")
    summary, details = parse_pytest_output(text, warn_on_count_mismatch=False)
    return summary, details, path.name


def _normalize_cpython_module_keys(
    summary: dict, details: dict
) -> tuple[dict, dict]:
    """
    Use full CPython test file stems (test_set) everywhere so tables and Plotly
    hovers do not show shortened names (set).
    """

    def norm(name: str) -> str:
        return name if name.startswith("test_") else f"test_{name}"

    return {norm(k): v for k, v in summary.items()}, {
        norm(k): v for k, v in details.items()
    }


def _totals_from_summary(summary: dict) -> dict:
    """Aggregate totals from a normalized module summary dict."""
    total = passed = skipped = failed = 0
    for s in summary.values():
        total += s["total"]
        passed += s["passed"]
        skipped += s["skipped"]
        failed += s["failed"]
    pr = (passed / total * 100) if total else 0.0
    skip_pct = (skipped / total * 100) if total else 0.0
    return {
        "total": total,
        "passed": passed,
        "skipped": skipped,
        "failed": failed,
        "pass_rate_pct": round(pr, 2),
        "skip_rate_pct": round(skip_pct, 2),
    }


def _run_display_label(path: Path) -> str:
    ymd, commit = _parse_run_date_and_commit(path)
    return f"{_format_run_date(ymd)} · {commit} · {path.name}"


def build_multi_run_overview(paths: list[Path]) -> pd.DataFrame:
    """One row per report file with run-level metrics (newest paths first in input ok)."""
    rows: list[dict] = []
    for p in paths:
        ymd, commit = _parse_run_date_and_commit(p)
        summary, _, source_name = load_parsed_output(str(p))
        if not summary:
            rows.append(
                {
                    "YMD": ymd,
                    "Date": _format_run_date(ymd),
                    "Commit": commit,
                    "File": source_name,
                    "Run": _run_display_label(p),
                    "Total": None,
                    "Passed": None,
                    "Skipped": None,
                    "Failed": None,
                    "Pass rate %": None,
                    "Skip rate %": None,
                    "Parse OK": False,
                }
            )
            continue
        summary, _ = _normalize_cpython_module_keys(summary, {})
        t = _totals_from_summary(summary)
        rows.append(
            {
                "YMD": ymd,
                "Date": _format_run_date(ymd),
                "Commit": commit,
                "File": source_name,
                "Run": _run_display_label(p),
                "Total": t["total"],
                "Passed": t["passed"],
                "Skipped": t["skipped"],
                "Failed": t["failed"],
                "Pass rate %": t["pass_rate_pct"],
                "Skip rate %": t["skip_rate_pct"],
                "Parse OK": True,
            }
        )
    return pd.DataFrame(rows)


def summary_to_dataframe(summary: dict) -> pd.DataFrame:
    rows = []
    total = passed = skipped = failed = 0
    for name in sorted(summary.keys()):
        s = summary[name]
        t, p, sk, f = s["total"], s["passed"], s["skipped"], s["failed"]
        total += t
        passed += p
        skipped += sk
        failed += f
        fail_pct = (sk / t * 100) if t else 0.0
        rows.append(
            {
                "Test": name,
                "Total": t,
                "Dynamo pass": p,
                "Dynamo skips": sk,
                "Dynamo failed": f,
                "% Failures": round(fail_pct, 2),
            }
        )
    total_fail_pct = (skipped / total * 100) if total else 0.0
    rows.append(
        {
            "Test": "TOTAL",
            "Total": total,
            "Dynamo pass": passed,
            "Dynamo skips": skipped,
            "Dynamo failed": failed,
            "% Failures": round(total_fail_pct, 2),
        }
    )
    return pd.DataFrame(rows)


def graph_break_counts(details: dict) -> tuple[dict[str, int], int]:
    reasons: list[str] = []
    for tests in details.values():
        for t in tests:
            if t.get("status") != "SKIPPED":
                continue
            r = t.get("reason") or ""
            if not r.strip():
                continue
            reasons.append(_graph_break_key(r))
    c = Counter(reasons)
    total = sum(c.values())
    return dict(c.most_common()), total


st.title("PyTorch Dynamo CPython test results")
st.markdown("Analysis of test skips and graph break reasons")

raw_files = _list_raw_outputs()
by_run_date = _files_grouped_by_run_date(raw_files) if raw_files else {}

with st.sidebar:
    mode = st.radio(
        "Dashboard view",
        options=["Individual run", "All runs summary"],
        horizontal=False,
    )

    if mode == "Individual run":
        st.subheader("Data source")
        if not raw_files:
            st.warning(
                f"No `{RAW_GLOB}` files in `{DATA_DIR}`. Run the test runner first."
            )
            selected = None
        else:
            dates_sorted = sorted(by_run_date.keys(), reverse=True)
            date_labels = {d: _format_run_date(d) for d in dates_sorted}
            picked_date = st.selectbox(
                "Run date",
                options=dates_sorted,
                index=0,
                format_func=lambda d: date_labels.get(d, d),
            )
            candidates = by_run_date[picked_date]
            if len(candidates) == 1:
                selected = candidates[0]
            else:
                selected = st.selectbox(
                    "Run (same calendar day)",
                    options=candidates,
                    format_func=lambda p: (
                        f"{_parse_run_date_and_commit(p)[1]} — {p.name}"
                    ),
                )
            st.caption(f"Directory: `{DATA_DIR}`")
    else:
        selected = raw_files[0] if raw_files else None

if selected is None:
    st.error("Add test output under `data/` (see README).")
    st.stop()

all_runs_df = build_multi_run_overview(raw_files)

summary, details, source_name = load_parsed_output(str(selected))
_run_ymd, _run_commit = _parse_run_date_and_commit(selected)

if not summary:
    st.error(f"Could not parse results from `{source_name}`.")
    st.stop()

summary, details = _normalize_cpython_module_keys(summary, details)
summary_df = summary_to_dataframe(summary)
graph_breaks, graph_breaks_total = graph_break_counts(details)

# Key metrics
col1, col2, col3, col4 = st.columns(4)
total_row = summary_df[summary_df["Test"] == "TOTAL"].iloc[0]
total_tests = int(total_row["Total"])
passing = int(total_row["Dynamo pass"])
skipped = int(total_row["Dynamo skips"])
pass_rate = (passing / total_tests * 100) if total_tests else 0.0

with col1:
    st.metric("Total tests", f"{total_tests:,}")
with col2:
    st.metric("Passing", f"{passing:,}")
with col3:
    st.metric("Skipped", f"{skipped:,}")
with col4:
    st.metric("Pass rate", f"{pass_rate:.1f}%")

st.divider()

if mode == "Individual run":
    tab1, tab2, tab3 = st.tabs(["Overview", "Graph breaks", "Module details"])

    with tab1:
        st.subheader("Test results by module")
        summary_viz = summary_df[summary_df["Test"] != "TOTAL"].copy()
        summary_viz = summary_viz.sort_values("% Failures", ascending=False)

        col1, col2 = st.columns(2)
        with col1:
            tot = summary_viz["Total"].replace(0, pd.NA)
            pct_viz = summary_viz.assign(
                **{
                    "Pass %": (summary_viz["Dynamo pass"] / tot * 100).fillna(0.0),
                    "Skip %": (summary_viz["Dynamo skips"] / tot * 100).fillna(0.0),
                    "Failed %": (summary_viz["Dynamo failed"] / tot * 100).fillna(0.0),
                }
            )
            fig = px.bar(
                pct_viz,
                x="Test",
                y=["Pass %", "Skip %", "Failed %"],
                barmode="stack",
                title="Pass vs skip vs failed (% of module tests)",
                labels={"value": "% of module tests", "variable": "Status"},
            )
            fig.update_layout(height=500, margin=dict(b=160))
            fig.update_xaxes(tickangle=45)
            fig.update_yaxes(range=[0, 100], ticksuffix="%")
            st.plotly_chart(fig, width="stretch")
        with col2:
            fig = px.bar(
                summary_viz,
                x="Test",
                y="% Failures",
                title="Skip rate (% of tests) by module",
                color="% Failures",
                color_continuous_scale="RdYlGn_r",
            )
            fig.update_layout(height=500, margin=dict(b=160))
            fig.update_xaxes(tickangle=45)
            st.plotly_chart(fig, width="stretch")

        st.subheader("Module summary")
        st.dataframe(summary_df, width="stretch")

    with tab2:
        st.subheader("All graph break keys (from skipped tests)")

        if graph_breaks and graph_breaks_total > 0:
            gb_df = pd.DataFrame(
                [
                    {"Reason": reason, "Count": count}
                    for reason, count in graph_breaks.items()
                ]
            )
            gb_df["Percent"] = gb_df["Count"] / graph_breaks_total * 100.0
            st.metric("Categorized skips (total)", f"{graph_breaks_total:,}")
            top = gb_df.iloc[0]
            st.metric("Top issue (truncated)", str(top["Reason"])[:60])
            st.metric("Top issue share", f"{top['Percent']:.1f}%")
            st.caption(f"{int(top['Count'])} tests")
            st.write("### All grouped keys")
            st.dataframe(
                gb_df,
                column_config={
                    "Percent": st.column_config.NumberColumn(format="%.2f%%")
                },
                width="stretch",
                height=420,
            )
        else:
            st.warning("No skipped-test reasons found to summarize.")

    with tab3:
        st.subheader("Detailed module results")
        modules = sorted(summary.keys())
        selected_module = st.selectbox(
            "Module",
            options=[None, *modules],
            index=0,
            format_func=lambda m: "All modules" if m is None else m,
            placeholder="Search module",
        )

        if selected_module is None:
            s = {
                "total": total_tests,
                "passed": passing,
                "skipped": skipped,
                "failed": int(total_row["Dynamo failed"]),
            }
            mod_tests = []
            for module_name in modules:
                for test in details.get(module_name, []):
                    row = dict(test)
                    row["module"] = module_name
                    mod_tests.append(row)
        else:
            s = summary[selected_module]
            mod_tests = details.get(selected_module, [])

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Total", s["total"])
        with c2:
            st.metric("Passed", s["passed"])
        with c3:
            st.metric("Skipped", s["skipped"])
        with c4:
            st.metric("Failed", s["failed"])

        if mod_tests:
            detail_df = pd.DataFrame(mod_tests)
            filter_status = st.multiselect(
                "Filter by status",
                options=["PASSED", "SKIPPED", "FAILED"],
                default=["PASSED", "SKIPPED", "FAILED"],
            )
            if filter_status:
                detail_df = detail_df[detail_df["status"].isin(filter_status)]
            q = st.text_input("Search test name or reason", "")
            if q.strip():
                mask = detail_df["test_name"].str.contains(
                    q, case=False, regex=False, na=False
                ) | detail_df["reason"].str.contains(
                    q, case=False, regex=False, na=False
                )
                detail_df = detail_df[mask]
            st.dataframe(detail_df, width="stretch", height=480)
        else:
            st.info("No per-test rows parsed for this module.")

else:
    st.subheader("Summary across all saved test runs")

    if all_runs_df.empty:
        st.warning("No run files found to summarize.")
    else:
        parsed_runs = all_runs_df[all_runs_df["Parse OK"] == True].copy()

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Saved runs", len(all_runs_df))
        with c2:
            st.metric("Parsed runs", len(parsed_runs))
        with c3:
            agg_total = (
                int(parsed_runs["Total"].fillna(0).sum()) if not parsed_runs.empty else 0
            )
            st.metric("Total tests (all parsed runs)", f"{agg_total:,}")
        with c4:
            avg_pass = (
                float(parsed_runs["Pass rate %"].dropna().mean())
                if not parsed_runs.empty
                else 0.0
            )
            st.metric("Avg pass rate", f"{avg_pass:.1f}%")

        st.caption(
            "Totals in this view are aggregated across all parsed report files in `data/`."
        )

        if not parsed_runs.empty:
            trend_df = parsed_runs.sort_values(["YMD", "Commit"]).copy()
            trend_df["Run label"] = trend_df["Date"]

            trend_col1, trend_col2 = st.columns(2)
            with trend_col1:
                fig = px.line(
                    trend_df,
                    x="Run label",
                    y="Pass rate %",
                    markers=True,
                    title="Pass rate trend by run",
                )
                fig.update_layout(height=420, margin=dict(b=120))
                fig.update_xaxes(tickangle=45)
                fig.update_yaxes(range=[0, 100], ticksuffix="%")
                st.plotly_chart(fig, width="stretch")

            with trend_col2:
                status_cols = ["Passed", "Skipped", "Failed"]
                long_df = trend_df.melt(
                    id_vars=["Run label"],
                    value_vars=status_cols,
                    var_name="Status",
                    value_name="Count",
                )
                fig = px.bar(
                    long_df,
                    x="Run label",
                    y="Count",
                    color="Status",
                    barmode="stack",
                    title="Passed / skipped / failed counts by run",
                )
                fig.update_layout(height=420, margin=dict(b=120))
                fig.update_xaxes(tickangle=45)
                st.plotly_chart(fig, width="stretch")

        st.subheader("Run table")
        shown = all_runs_df.sort_values(["YMD", "Commit"], ascending=[False, False])
        st.dataframe(
            shown[
                [
                    "Date",
                    "Commit",
                    "Total",
                    "Passed",
                    "Skipped",
                    "Failed",
                    "Pass rate %",
                    "Skip rate %",
                    "Parse OK",
                    "File",
                ]
            ],
            width="stretch",
            height=420,
        )

st.divider()
try:
    run_day = datetime.strptime(_run_ymd, "%Y%m%d").date()
    day_s = run_day.isoformat()
except ValueError:
    day_s = _run_ymd
st.caption(f"Run date: **{day_s}** · commit / id: `{_run_commit}` · file: `{source_name}`")
st.caption("Streamlit · parsed with `cpython_test_runner.parse_pytest_output`")
