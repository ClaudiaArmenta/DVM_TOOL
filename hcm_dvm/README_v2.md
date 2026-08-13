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
│   └── dvm_smoke_test.py  # Smoke test execution callbacks
├── dvm/
│   ├── __init__.py        # DVM subpackage
│   ├── version_select.py  # HANA version parsing & file matching
│   ├── execution.py       # Thread-safe query execution
│   ├── components.py      # Reusable Dash components
│   ├── registry.py        # Analysis registration
│   └── layout.py          # DVM Tool layout
├── queries/               # 51 versioned SQL scripts (.txt)
│   ├── HANA_DVM_01_OVERVIEW_SPS12.txt
│   ├── HANA_DVM_01_OVERVIEW_REV20.txt
│   └── ...
└── assets/
    └── style.css          # SAP-styled CSS
```

## Architecture

- **Connection layer** (`connector.py`, `sap_gui_connector.py`, `query_executor.py`): Handles both native hdbcli and SAP GUI scripting connections.
- **DVM layer** (`dvm/`): Version-aware query selection, threaded execution, and UI components.
- **Callbacks** (`callbacks/`): Dash callback registration split by concern.

## Testing

```bash
pytest tests/ -v
```

## License

Internal SAP tooling. Not for redistribution.
