"""Unified query execution layer.

Provides a single interface to execute SQL queries regardless of the
connection mode (HANA Native or SAP GUI). This is the key module that
consuming applications should use for query execution.

Usage:
    from hana_connection_manager.query_executor import execute_query, load_and_execute

    # Execute raw SQL
    df = execute_query(conn_state, "SELECT * FROM M_HOST_INFORMATION")

    # Load SQL from file and execute with time params
    df = load_and_execute(
        conn_state,
        sql_file="cpu_analyzer.sql",
        queries_dir="/path/to/queries",
        time_from="2024-01-01 00:00:00",
        time_to="2024-01-02 00:00:00",
    )
"""

import io
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Tuple

import pandas as pd

from .connector import HANAConnector
from .config import HANAConnectionConfig
from .exceptions import ConnectionError, QueryError
from .logger import get_logger

logger = get_logger("executor")


# ============================================================
# CORE EXECUTION FUNCTIONS
# ============================================================

def execute_query(
    conn_state: dict,
    sql: str,
    *,
    sid: str = "",
    label: str = "EXPORT",
    sql_exec_wait: float = 5.0,
) -> pd.DataFrame:
    """Execute SQL using the appropriate connection mode.

    Dispatches to HANA Native (hdbcli) or SAP GUI (DBACOCKPIT) based
    on the connection state type.

    Args:
        conn_state: Connection state dictionary (from store-connection-state).
        sql: SQL query string to execute.
        sid: System ID for export filename (SAP GUI mode only).
        label: Label for export filename (SAP GUI mode only).
        sql_exec_wait: Max wait for SQL execution in SAP GUI mode.

    Returns:
        pandas DataFrame with query results.

    Raises:
        ConnectionError: If not connected or connection fails.
        QueryError: If query execution fails.

    Usage:
        from hana_connection_manager.query_executor import execute_query

        # In a Dash callback:
        @app.callback(Output(...), Input(...), State("store-connection-state", "data"))
        def my_callback(..., conn_state):
            df = execute_query(conn_state, "SELECT * FROM M_HOST_INFORMATION")
            return df.to_dict("records")
    """
    if not conn_state or not conn_state.get("connected"):
        raise ConnectionError("Not connected. Establish a connection first.")

    conn_type = conn_state.get("type", "")

    if conn_type == "hana_native":
        return _run_query_hana(conn_state, sql)
    elif conn_type == "sap_gui":
        return _run_query_gui(conn_state, sql, sid=sid, label=label,
                              sql_exec_wait=sql_exec_wait)
    else:
        raise ConnectionError(
            f"Unknown connection type: '{conn_type}'. Expected 'hana_native' or 'sap_gui'."
        )


def load_and_execute(
    conn_state: dict,
    sql_file: str,
    queries_dir: str,
    time_from: Optional[str] = None,
    time_to: Optional[str] = None,
    *,
    sid: str = "",
    label: str = "",
    sql_exec_wait: float = 5.0,
) -> pd.DataFrame:
    """Load a SQL file, substitute time placeholders, and execute.

    Args:
        conn_state: Connection state dictionary.
        sql_file: Filename of the SQL file (e.g., 'cpu_analyzer.sql').
        queries_dir: Path to the directory containing SQL files.
        time_from: Start timestamp (replaces {{TIME_FROM}} in SQL).
        time_to: End timestamp (replaces {{TIME_TO}} in SQL).
        sid: System ID for export filename (SAP GUI mode).
        label: Label for export filename (defaults to sql_file stem).
        sql_exec_wait: Max wait for SQL execution in SAP GUI mode.

    Returns:
        pandas DataFrame with query results.

    Usage:
        df = load_and_execute(
            conn_state,
            sql_file="memory_overview.sql",
            queries_dir="/path/to/queries",
            time_from="2024-01-01 00:00:00",
            time_to="2024-01-02 00:00:00",
        )
    """
    sql = _load_and_fill_sql(sql_file, queries_dir, time_from, time_to)
    _label = label or sql_file.replace(".sql", "").upper()
    return execute_query(conn_state, sql, sid=sid, label=_label,
                         sql_exec_wait=sql_exec_wait)


# ============================================================
# INTERNAL DISPATCH FUNCTIONS
# ============================================================

def _run_query_hana(conn_state: dict, sql: str) -> pd.DataFrame:
    """Execute SQL against a HANA native connection and return a DataFrame."""
    cfg = HANAConnectionConfig(
        host=conn_state.get("host", ""),
        port=int(conn_state.get("port", 30015)),
        user=conn_state.get("user", ""),
        password=conn_state.get("password", ""),
        encrypt=conn_state.get("encrypt", False),
        sslValidateCertificate=conn_state.get("sslValidateCertificate", False),
        tenant=conn_state.get("tenant", ""),
    )
    connector = HANAConnector(cfg)
    connector.connect()
    try:
        return connector.execute_query(sql)
    finally:
        connector.disconnect()


def _run_query_gui(
    conn_state: dict,
    sql: str,
    *,
    sid: str = "",
    label: str = "EXPORT",
    sql_exec_wait: float = 5.0,
) -> pd.DataFrame:
    """Execute SQL via DBACOCKPIT in SAP GUI and return a DataFrame.

    Args:
        conn_state: Connection state (must have session_id for SAP GUI).
        sql: SQL query to execute.
        sid: System ID embedded in export filename.
        label: Label embedded in export filename.
        sql_exec_wait: Seconds to wait after F8 for result grid.
    """
    import pythoncom
    from .sap_gui_connector import SAPGUIConnector
    from .dba_cockpit_executor import DBACockpitSQLExecutor, DBACockpitConfig

    pythoncom.CoInitialize()
    session = SAPGUIConnector().get_session(conn_state.get("session_id"))
    cfg = DBACockpitConfig(sid=sid, label=label, sql_exec_wait=sql_exec_wait)
    return DBACockpitSQLExecutor(session, cfg).execute(sql)


# ============================================================
# SQL FILE HELPERS
# ============================================================

def _load_and_fill_sql(
    sql_file: str,
    queries_dir: str,
    time_from: Optional[str] = None,
    time_to: Optional[str] = None,
) -> str:
    """Read a SQL file and substitute time placeholders.

    Handles timestamp formatting (adds :00 if seconds missing).
    """
    path = Path(queries_dir) / sql_file
    if not path.exists():
        raise QueryError(
            f"SQL file not found: {sql_file}",
            f"Expected at: {path}",
        )
    sql = path.read_text(encoding="utf-8")

    if time_from:
        tf = time_from.replace("T", " ")
        if len(tf) == 16:
            tf += ":00"
        sql = sql.replace("{{TIME_FROM}}", tf)

    if time_to:
        tt = time_to.replace("T", " ")
        if len(tt) == 16:
            tt += ":00"
        sql = sql.replace("{{TIME_TO}}", tt)

    return sql


# ============================================================
# BATCH EXPORT HELPER
# ============================================================

def auto_export_datasets(
    store_vals: Dict[str, str],
    query_labels: Dict[str, str],
    sid: str = "",
    export_dir: str = "C:/temp",
) -> Tuple[List[str], List[str]]:
    """Write each loaded DataFrame to an XLSX file.

    Used after HANA native queries to save results locally
    (matching the SAP GUI export behavior for consistency).

    Args:
        store_vals: Dict mapping sql_filename -> JSON string (DataFrame as JSON).
        query_labels: Dict mapping sql_filename -> short label for filename.
        sid: System identifier embedded in filename.
        export_dir: Destination directory.

    Returns:
        Tuple of (saved_paths, errors) where both are lists of strings.

    Usage:
        saved, errors = auto_export_datasets(
            {"cpu_analyzer.sql": df.to_json(orient="records")},
            {"cpu_analyzer.sql": "CPU"},
            sid="PRD",
        )
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    sid_part = f"_{sid}" if sid else ""
    out_dir = Path(export_dir)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.warning("Could not create export dir %s: %s", export_dir, exc)
        return [], [str(exc)]

    saved, errors = [], []

    # Accept both dict {sql_file: json} and list [(label, json)]
    if isinstance(store_vals, dict):
        items = [
            (query_labels.get(sf, sf.replace(".sql", "")), sv)
            for sf, sv in store_vals.items()
        ]
    else:
        items = store_vals

    for lbl, json_str in items:
        if not json_str:
            continue
        try:
            df = pd.read_json(io.StringIO(json_str), orient="records",
                              convert_dates=False)
            fname = f"RCA_{lbl}{sid_part}_{ts}.xlsx"
            fpath = str(out_dir / fname)
            df.to_excel(fpath, index=False)
            saved.append(fpath)
            logger.info("Auto-exported %s -> %s", lbl, fpath)
        except Exception as exc:
            logger.warning("Auto-export failed for %s: %s", lbl, exc)
            errors.append(lbl)

    return saved, errors
