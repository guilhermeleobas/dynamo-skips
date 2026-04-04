import streamlit as st
import pandas as pd
from pathlib import Path
import plotly.express as px
import plotly.graph_objects as go
from collections import Counter
import re

st.set_page_config(page_title="Dynamo Skips Dashboard", layout="wide")

st.title("🚀 PyTorch Dynamo CPython Test Results")
st.markdown("Analysis of test skips and graph break reasons")

# Configuration
SCRIPTS_DIR = Path.home() / "git" / "scripts"
DATA_DIR = SCRIPTS_DIR

@st.cache_data
def load_excel_data():
    """Load the latest Excel results file"""
    xlsx_files = sorted(DATA_DIR.glob("cpython_test_results_*.xlsx"), reverse=True)
    if not xlsx_files:
        return None, None

    latest_file = xlsx_files[0]

    # Load summary sheet
    summary = pd.read_excel(latest_file, sheet_name="Summary")
    return latest_file, summary

@st.cache_data
def load_test_output():
    """Load the full test output log"""
    output_file = DATA_DIR / "all_tests_output.txt"
    if not output_file.exists():
        return None

    with open(output_file, 'r') as f:
        return f.read()

@st.cache_data
def extract_graph_breaks(output_text):
    """Extract and analyze graph break reasons"""
    if not output_text:
        return {}

    pattern = r"Explanation: ([^\n]+)"
    matches = re.findall(pattern, output_text)

    # Clean up and count
    cleaned = [m.split('\\n')[0][:80] for m in matches]
    return dict(Counter(cleaned).most_common(20))

# Load data
latest_file, summary = load_excel_data()
output_text = load_test_output()
graph_breaks = extract_graph_breaks(output_text)

if summary is None:
    st.error("No Excel results found. Run the test script first.")
    st.stop()

# Key Metrics
col1, col2, col3, col4 = st.columns(4)

with col1:
    total_tests = summary[summary['Test'] == 'TOTAL']['Total'].values[0]
    st.metric("Total Tests", f"{total_tests:,}")

with col2:
    passing = summary[summary['Test'] == 'TOTAL']['Dynamo pass'].values[0]
    st.metric("Passing", f"{passing:,}")

with col3:
    skipped = summary[summary['Test'] == 'TOTAL']['Dynamo skips'].values[0]
    st.metric("Skipped", f"{skipped:,}")

with col4:
    pass_rate = (passing / total_tests * 100) if total_tests > 0 else 0
    st.metric("Pass Rate", f"{pass_rate:.1f}%")

st.divider()

# Tabs for different views
tab1, tab2, tab3 = st.tabs(["📊 Overview", "⚠️ Graph Breaks", "📋 Module Details"])

with tab1:
    st.subheader("Test Results by Module")

    # Remove TOTAL row for visualization
    summary_viz = summary[summary['Test'] != 'TOTAL'].copy()
    summary_viz = summary_viz.sort_values('% Failures', ascending=False)

    col1, col2 = st.columns(2)

    with col1:
        # Pass vs Skip chart
        fig = px.bar(summary_viz,
                    x='Test',
                    y=['Dynamo pass', 'Dynamo skips'],
                    barmode='stack',
                    title='Pass vs Skip by Module',
                    labels={'value': 'Count', 'variable': 'Status'})
        fig.update_layout(height=500)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        # Failure percentage chart
        fig = px.bar(summary_viz,
                    x='Test',
                    y='% Failures',
                    title='Failure % by Module',
                    color='% Failures',
                    color_continuous_scale='RdYlGn_r')
        fig.update_layout(height=500)
        st.plotly_chart(fig, use_container_width=True)

    # Summary table
    st.subheader("Module Summary Table")
    st.dataframe(summary, use_container_width=True)

with tab2:
    st.subheader("Top Graph Break Reasons")

    if graph_breaks:
        # Create DataFrame
        gb_df = pd.DataFrame([
            {"Reason": reason, "Count": count}
            for reason, count in graph_breaks.items()
        ])

        col1, col2 = st.columns(2)

        with col1:
            fig = px.bar(gb_df,
                        x='Count',
                        y='Reason',
                        orientation='h',
                        title='Top 20 Graph Break Reasons',
                        labels={'Count': 'Number of Tests'})
            fig.update_layout(height=600)
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.write("### Statistics")
            total_graph_breaks = gb_df['Count'].sum()
            st.metric("Total Graph Breaks", total_graph_breaks)
            st.metric("Top Issue", gb_df.iloc[0]['Reason'][:60])
            st.metric("Top Issue Count", gb_df.iloc[0]['Count'])

            # Percentage breakdown
            st.write("### Top 5 Issues")
            for idx, row in gb_df.head(5).iterrows():
                pct = (row['Count'] / total_graph_breaks * 100)
                st.write(f"**{idx+1}. {row['Reason'][:70]}**")
                st.progress(pct/100)
                st.caption(f"{row['Count']} tests ({pct:.1f}%)")
    else:
        st.warning("No graph break data available")

with tab3:
    st.subheader("Detailed Module Results")

    # Module selector
    modules = [m for m in summary['Test'].values if m != 'TOTAL']
    selected_module = st.selectbox("Select Module", modules)

    if selected_module:
        module_data = summary[summary['Test'] == selected_module].iloc[0]

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Tests", int(module_data['Total']))
        with col2:
            st.metric("Pass Rate", f"{module_data['Total'] - module_data['Dynamo skips']}/{module_data['Total']}")
        with col3:
            st.metric("Failure %", module_data['% Failures'])

        # Try to load module sheet
        try:
            module_sheet = pd.read_excel(latest_file, sheet_name=selected_module)
            st.write("### Test Details")
            st.dataframe(module_sheet, use_container_width=True)
        except Exception as e:
            st.warning(f"Could not load detailed data: {e}")

# Footer
st.divider()
st.caption(f"📁 Data from: {latest_file.name if latest_file else 'No data'}")
st.caption("Generated with Streamlit • Data from cpython_test_runner.py")
