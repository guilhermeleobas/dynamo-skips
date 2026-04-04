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


def graph_break_counts(details: dict, top_n: int = 20) -> tuple[dict[str, int], int]:
    reasons: list[str] = []
    for tests in details.values():
        for t in tests:
            if t.get("status") != "SKIPPED":
                continue
            r = t.get("reason") or ""
            if not r.strip():
                continue
            reasons.append(_explanation_snippet(r, max_len=200))
    c = Counter(reasons)
    total = sum(c.values())
    return dict(c.most_common(top_n)), total


st.title("PyTorch Dynamo CPython test results")
st.markdown("Analysis of test skips and graph break reasons")

raw_files = _list_raw_outputs()
by_run_date = _files_grouped_by_run_date(raw_files) if raw_files else {}

with st.sidebar:
    st.subheader("Data source")
    if not raw_files:
        st.warning(f"No `{RAW_GLOB}` files in `{DATA_DIR}`. Run the test runner first.")
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

if selected is None:
    st.error("Add test output under `data/` (see README).")
    st.stop()

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
        fig.update_layout(height=500)
        fig.update_yaxes(range=[0, 100], ticksuffix="%")
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        fig = px.bar(
            summary_viz,
            x="Test",
            y="% Failures",
            title="Skip rate (% of tests) by module",
            color="% Failures",
            color_continuous_scale="RdYlGn_r",
        )
        fig.update_layout(height=500)
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Module summary")
    st.dataframe(summary_df, use_container_width=True)

with tab2:
    st.subheader("Top graph break explanations (from skipped tests)")

    if graph_breaks and graph_breaks_total > 0:
        gb_df = pd.DataFrame(
            [{"Reason": reason, "Count": count} for reason, count in graph_breaks.items()]
        )
        gb_df["Percent"] = gb_df["Count"] / graph_breaks_total * 100.0
        col1, col2 = st.columns(2)
        with col1:
            fig = px.bar(
                gb_df,
                x="Percent",
                y="Reason",
                orientation="h",
                title="Top reasons (share of categorized skips)",
                labels={"Percent": "% of categorized skips"},
            )
            fig.update_layout(height=600)
            fig.update_xaxes(ticksuffix="%")
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            st.write("### Statistics")
            st.metric("Categorized skips (total)", f"{graph_breaks_total:,}")
            top = gb_df.iloc[0]
            st.metric("Top issue (truncated)", str(top["Reason"])[:60])
            st.metric("Top issue share", f"{top['Percent']:.1f}%")
            st.caption(f"{int(top['Count'])} tests")
            st.write("### Top 5")
            for rank, (_, row) in enumerate(gb_df.head(5).iterrows(), start=1):
                st.write(f"**{rank}.** {row['Reason'][:90]}")
                st.progress(row["Percent"] / 100.0)
                st.caption(f"{row['Percent']:.1f}% · {int(row['Count'])} tests")
    else:
        st.warning("No skipped-test reasons found to summarize.")

with tab3:
    st.subheader("Detailed module results")
    modules = sorted(summary.keys())
    selected_module = st.selectbox("Module", modules)

    if selected_module:
        s = summary[selected_module]
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Total", s["total"])
        with c2:
            st.metric("Passed", s["passed"])
        with c3:
            st.metric("Skipped", s["skipped"])
        with c4:
            st.metric("Failed", s["failed"])

        mod_tests = details.get(selected_module, [])
        if mod_tests:
            detail_df = pd.DataFrame(mod_tests)
            filter_status = st.multiselect(
                "Filter by status",
                options=["PASSED", "SKIPPED", "FAILED"],
                default=["SKIPPED", "FAILED"],
            )
            if filter_status:
                detail_df = detail_df[detail_df["status"].isin(filter_status)]
            q = st.text_input("Search test name or reason", "")
            if q.strip():
                mask = detail_df["test_name"].str.contains(
                    q, case=False, regex=False, na=False
                ) | detail_df["reason"].str.contains(q, case=False, regex=False, na=False)
                detail_df = detail_df[mask]
            st.dataframe(detail_df, use_container_width=True, height=480)
        else:
            st.info("No per-test rows parsed for this module.")

st.divider()
try:
    run_day = datetime.strptime(_run_ymd, "%Y%m%d").date()
    day_s = run_day.isoformat()
except ValueError:
    day_s = _run_ymd
st.caption(f"Run date: **{day_s}** · commit / id: `{_run_commit}` · file: `{source_name}`")
st.caption("Streamlit · parsed with `cpython_test_runner.parse_pytest_output`")
