# Dynamo Skips App - Project Overview

## 📋 Project Purpose

Build an interactive Streamlit dashboard to visualize and analyze PyTorch Dynamo CPython test results across multiple test runs. The goal is to:

- **Track evolution**: Monitor how graph breaks change over time across PyTorch versions
- **Identify patterns**: Find the most common graph break reasons
- **Aggregate data**: Compare results across test modules and time periods
- **Enable insights**: Help developers prioritize which Dynamo issues to tackle

## 📊 Current Data Flow

```
cpython_test_runner.py
    ↓ (runs tests with PYTORCH_TEST_WITH_DYNAMO=1)
    ↓ (parses unittest output)
    ↓ (saves raw text with commit hash & date)
    ↓
data/all_tests_output_<commit>_<date>.txt   (4MB+ raw output)
    ↓
dashboard (Streamlit) - TO BE BUILT
    ↓ (visualizes metrics, trends, patterns)
```

## 🎯 Features to Implement

### Phase 1: MVP (Basic Dashboard)
- [x] Read and parse raw test output files
- [ ] Create Overview tab with key metrics
  - Total tests, pass rate, skip rate
  - Pass/skip breakdown by module
  - Summary table of all modules
- [ ] Create Graph Breaks tab
  - Top graph break reasons
  - Count and percentage breakdown
  - Visual charts (bar chart of top reasons)
- [ ] Create Module Details tab
  - Module selector dropdown
  - Per-test results with reasons

### Phase 2: Time Series & Trends
- [ ] Support multiple test runs (from raw data files)
- [ ] Track metrics over time (dates/versions)
- [ ] Line charts showing evolution of:
  - Total graph breaks
  - Pass rate by module
  - Specific graph break categories
- [ ] Time range selector

### Phase 3: Advanced Analysis
- [ ] Graph break categorization (custom grouping)
- [ ] Search/filter by:
  - Module name
  - Test name
  - Graph break reason (keyword search)
- [ ] Export filtered results
- [ ] Performance comparisons between versions

## 📁 Project Structure

```
dynamo-skips-app/
├── PROJECT.md                    # This file - project overview & todos
├── README.md                      # User-facing documentation
├── pixi.toml                      # Pixi dependencies
├── app.py                         # Main Streamlit app (TO BE BUILT)
├── cpython_test_runner.py         # Test runner (generates data)
├── data/
│   └── all_tests_output_<commit>_<date>.txt    # Raw test output (~4MB)
├── src/
│   ├── parser.py                  # Parse raw test output (TO BE CREATED)
│   ├── models.py                  # Data models (TO BE CREATED)
│   └── visualizations.py          # Chart functions (TO BE CREATED)
└── .gitignore
```

## 🔧 Key Files

### cpython_test_runner.py (Existing)
- Runs CPython tests with Dynamo enabled
- Parses unittest output into structured data
- Generates Excel spreadsheets with summary + per-module tabs
- Can reuse previous outputs with `--reuse-output`

**Important**: The script outputs:
- Raw test output (can be saved with `--save-output`)
- Excel file with:
  - Summary sheet: aggregated stats per module
  - Individual sheets: per-test details with reasons

### Current Data Format
Test output format (from unittest -v):
```
test_name (__main__.ClassName.test_name) ... [status] '[reason]'
```

Statuses: `ok` (PASSED), `skipped` (SKIPPED), `FAIL` (FAILED)

Reasons for skips often contain:
- "Graph break" explanations
- Dynamo tracing errors
- Unsupported operations

## 📈 Key Metrics to Track

1. **Overall**: Total tests, pass rate, skip rate, fail rate
2. **By Module**: Same metrics broken down by test module
3. **Graph Breaks**: Top reasons, distribution, categories
4. **Trends**: Changes over time across test runs

## 🚀 Getting Started

### Run Tests (if needed)
```bash
cd ~/git/dynamo-skips-app
python ~/git/scripts/cpython_test_runner.py --save-output
```

### View Current Data
```bash
head -100 data/all_tests_output_*.txt
```

### Start Building Dashboard
```bash
pixi install
pixi run streamlit run app.py
```

## 📝 Implementation Notes

### Data Parsing Strategy
Currently, the raw output is 4MB+ and contains:
- Test file markers: `=== TEST FILE: test/dynamo/cpython/3_13/test_*.py ===`
- Test result lines: `test_name (__main__.Class.test_name) ... status 'reason'`
- Multi-line reasons with escaped newlines

The `cpython_test_runner.py` has a robust parser that extracts:
1. Per-module summaries (total, passed, failed, skipped)
2. Per-test details (test name, status, reason)

### Streamlit Integration
- Read raw output or Excel files
- Parse incrementally to avoid memory issues with 4MB files
- Cache parsed data with `@st.cache_data`
- Use columns/tabs for different views

### Graph Break Extraction
Need to parse reason strings to extract graph break categories:
- Look for patterns like "builtin `xxx`", "Failed to trace", "Unsupported method", etc.
- Group similar reasons by category for better insights

## 🔄 Next Steps (For Next Chat)

1. **Create parser module** (`src/parser.py`)
   - Read raw output file
   - Extract graph break reasons
   - Categorize them

2. **Create data models** (`src/models.py`)
   - TestResult dataclass
   - Module statistics dataclass
   - GraphBreak category dataclass

3. **Build dashboard** (`app.py`)
   - Overview tab with metrics
   - Graph breaks tab with visualizations
   - Module details tab with search

4. **Add time series support**
   - Track multiple test runs
   - Compare across versions/dates

## 📚 References

- Test runner: `/home/guilhermel/git/dynamo-skips-app/cpython_test_runner.py`
- Raw data: `/home/guilhermel/git/dynamo-skips-app/data/all_tests_output_*.txt`
- PyTorch Dynamo docs: https://pytorch.org/docs/main/dynamo/
