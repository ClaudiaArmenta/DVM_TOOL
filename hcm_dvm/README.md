# DVM Tool – SAP HANA Data Volume Management

A Dash-based desktop application for SAP HANA data volume analysis, built on top of the `hana_connection_manager` connection layer.

## Overview

The DVM Tool helps DBAs and administrators analyze SAP HANA data volumes by:

1. **Selecting** the target HANA version (auto-detected from bundled query files).
2. **Connecting** via SAP GUI (scripting) or native hdbcli.
3. **Running** a smoke-test sequence to validate connectivity and basic queries.
4. **Executing** versioned SQL analysis scripts against the connected system.

## Installation

```bash
# Base install (SAP GUI connection only, no native driver)
pip install .

# With native HANA driver
pip install ".[native]"

# With SAP GUI support (Windows only)
pip install ".[gui]"

# Full install
pip install ".[all]"

# Development
pip install -e ".[all,dev]"
```

## Running

The following methods start the DVM Tool and serve the UI at
`http://localhost:8051` (configurable via `CONN_MGR_PORT`).

```bash
# 1. Run as a Python module (no pip install required)
python -m hana_connection_manager

# 2. Run via the convenience script at the repo root (no pip install required)
python run.py

# 3. Console script (only available after pip install -e .)
hana-dvm
```

> **Note:** `hana-dvm` is a console entry point declared in `pyproject.toml`.
> It is only available on `PATH` after the package has been installed
> (e.g. `pip install -e .` or `pip install .`).  Methods 1 and 2 work
> directly from a source checkout without installation.

Optional dependencies (`hdbcli`, `pywin32`) are **not** required at import
time. The app starts and serves the UI regardless; features that need those
packages report a clear error only when actually invoked.

## Configuration (Environment Variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `CONN_MGR_HOST` | `0.0.0.0` | Bind address |
| `CONN_MGR_PORT` | `8051` | HTTP port |
| `CONN_MGR_DEBUG` | `false` | Dash debug mode |
| `HANA_HOST` | — | Pre-fill HANA hostname |
| `HANA_PORT` | `30015` | Pre-fill HANA SQL port |
| `HANA_USER` | — | Pre-fill HANA user |
| `HANA_PASSWORD` | — | Pre-fill HANA password |

## Project Structure

```
hana_connection_manager/
├── __init__.py            # Package marker + public API
├── __main__.py            # python -m entry
├── app.py                 # Dash app factory (create_app)
├── main.py                # run() entry point
├── config.py              # Connection & app config
├── connector.py           # Native hdbcli connector
├── sap_gui_connector.py   # SAP GUI scripting connector
├── dba_cockpit_executor.py# DBA Cockpit execution via GUI
├── query_executor.py      # Dispatch execute_query()
├── query_runner.py        # High-level query runner
├── connection_store.py    # In-memory connection state
├── exceptions.py          # Custom exceptions
├── logger.py              # Logging setup
├── layout.py              # Connection UI components
├── integration.py         # Integration helpers
├── callbacks/
│   ├── __init__.py        # register_all_callbacks()
│   ├── connection_callbacks.py  # Connection modal callbacks
│   ├── dvm_navigation.py  # DVM navigation callbacks
│   ├── dvm_smoke_test.py  # Smoke test execution callbacks
│   └── dvm_analyses.py    # Analysis run/progress/export callbacks
├── dvm/
│   ├── __init__.py        # DVM subpackage
│   ├── version_select.py  # HANA version parsing & file matching
│   ├── execution.py       # Thread-safe query execution (DBACOCKPIT lock)
│   ├── components.py      # Reusable Dash components
│   ├── analyses.py        # SQL builders for all 6 DVM analyses
│   ├── renderers.py       # Dash renderers (tables + charts) per analysis
│   ├── registry.py        # Analysis registration (auto-registers A1–A6)
│   ├── export.py          # Excel export (DVM_tool.xlsx)
│   └── layout.py          # Full DVM layout (landing, tabs, NSE, progress)
├── queries/               # 51 reference SQL scripts (.txt) for provenance
│   └── ...
└── assets/
    └── style.css          # SAP-styled CSS
```

## Architecture

- **Connection layer** (`connector.py`, `sap_gui_connector.py`, `query_executor.py`): Handles both native hdbcli and SAP GUI scripting connections. Files are unchanged from baseline.
- **DVM layer** (`dvm/`): Version-aware query selection, threaded execution, and UI components.
- **Callbacks** (`callbacks/`): Dash callback registration split by concern.

## SQL Generation

The DVM Tool authors its own focused, read-only SQL rather than loading the large
SAP mini-check files at runtime. This makes queries reliable through DBACOCKPIT and
easier to maintain.

Key principles:
- **Grounded**: Every query uses the exact monitoring views and column names from the
  reference mini-checks (SAP Note 1969700). The originals are kept in `queries/` for
  provenance.
- **Version-aware**: The user-selected HANA revision drives which SQL variant is
  generated. Columns that only exist on newer revisions (e.g. NSE/LOAD_UNIT from
  2.00.040+, IS_DYNAMIC from 2.00.080+) are conditionally included or omitted.
- **Read-only**: Only `SELECT` / `WITH ... SELECT` statements. Never DDL/DML.
- **Lean**: Returns only the columns each analysis needs; applies configurable row
  limits. No multi-hundred-line CTE machinery.
- **Labeled**: Each result is tagged "generated (rev X)" in the UI so the user knows
  the SQL was version-adapted.

If a generated query fails, the tool degrades gracefully: the analysis shows an error
with the SQL that was attempted, without aborting other analyses.

## Testing

```bash
pytest tests/ -v
```

## License

Internal SAP tooling. Not for redistribution.
