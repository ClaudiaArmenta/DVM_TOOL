"""Execution layer for DVM Tool.

Provides:
  - run_query(): Execute SQL via the connection layer (single session).
  - QueryResult dataclass for structured results.

For SAP GUI: session-parameterized execution via DBACockpitSQLExecutor.
  - Single session: one executor, serial queries via /nDBACOCKPIT.
For native (hdbcli): direct execution.
"""

import time
import threading
import traceback
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any

import pandas as pd

from hana_connection_manager import execute_query
from hana_connection_manager.exceptions import ConnectionError, QueryError
from hana_connection_manager.dba_cockpit_executor import (
    DBACockpitSQLExecutor,
    DBACockpitConfig,
    DBACockpitExecutionError,
)

logger = logging.getLogger("dvm.execution")

# Per-session locks for SAP GUI execution
_session_locks: dict = {}
_session_locks_mutex = threading.Lock()

# Retry settings
_MAX_RETRIES = 2
_RETRY_DELAY_SEC = 2.0


@dataclass
class QueryResult:
    """Result of a query execution."""

    success: bool = False
    df: Optional[pd.DataFrame] = None
    sql: str = ""
    elapsed_ms: float = 0.0
    row_count: int = 0
    col_count: int = 0
    error: str = ""
    exception_text: str = ""


def _get_session_lock(session_id: str) -> threading.Lock:
    """Get or create a per-session lock."""
    with _session_locks_mutex:
        if session_id not in _session_locks:
            _session_locks[session_id] = threading.Lock()
        return _session_locks[session_id]


def run_query(
    conn_state: dict,
    sql: str,
    *,
    sid: str = "",
    label: str = "QUERY",
    sql_exec_wait: float = 10.0,
    retries: int = _MAX_RETRIES,
) -> QueryResult:
    """Execute a SQL query with timing and error handling.

    Dispatches to the appropriate backend (native or SAP GUI).
    For SAP GUI, uses a per-session lock to serialize within one session.
    """
    result = QueryResult(sql=sql)

    if not conn_state or not conn_state.get("connected"):
        result.error = "Not connected to SAP HANA."
        return result

    last_exception = None

    for attempt in range(1 + retries):
        try:
            conn_type = conn_state.get("type", "native")
            session_id = conn_state.get("session_id", "default")
            lock = _get_session_lock(session_id) if conn_type == "sap_gui" else threading.Lock()

            with lock:
                t0 = time.perf_counter()
                df = execute_query(
                    conn_state,
                    sql,
                    sid=sid,
                    label=label,
                    sql_exec_wait=sql_exec_wait,
                )
                elapsed = (time.perf_counter() - t0) * 1000.0

            result.success = True
            result.df = df
            result.elapsed_ms = elapsed
            result.row_count = len(df) if df is not None else 0
            result.col_count = len(df.columns) if df is not None else 0
            return result

        except (ConnectionError, QueryError) as e:
            last_exception = e
            result.error = str(e)
            result.exception_text = traceback.format_exc()
            break  # Don't retry logic errors

        except Exception as e:
            last_exception = e
            result.error = f"Query failed (attempt {attempt + 1}/{1 + retries}): {str(e)}"
            result.exception_text = traceback.format_exc()
            if attempt < retries:
                time.sleep(_RETRY_DELAY_SEC)
            continue

    if last_exception:
        result.error = f"Query failed: {str(last_exception)}"
        result.exception_text = traceback.format_exc()
    return result


def run_query_on_executor(
    executor: DBACockpitSQLExecutor,
    sql: str,
    lock: Optional[threading.Lock] = None,
) -> QueryResult:
    """Execute a SQL query on a specific DBACockpitSQLExecutor.

    Used for multi-session parallel execution. The executor already has
    DBACOCKPIT open on its session — just execute the SQL.

    Args:
        executor: A ready DBACockpitSQLExecutor with DBACOCKPIT open.
        sql: SQL to execute.
        lock: Per-session lock (acquired here). If None, no locking.
    """
    result = QueryResult(sql=sql)

    if executor is None:
        result.error = "Executor not available (session setup failed)."
        return result

    try:
        if lock:
            lock.acquire()
        try:
            t0 = time.perf_counter()
            df = executor.execute(sql)
            elapsed = (time.perf_counter() - t0) * 1000.0
        finally:
            if lock:
                lock.release()

        result.success = True
        result.df = df
        result.elapsed_ms = elapsed
        result.row_count = len(df) if df is not None else 0
        result.col_count = len(df.columns) if df is not None else 0

    except DBACockpitExecutionError as e:
        result.error = str(e)
        result.exception_text = traceback.format_exc()

    except Exception as e:
        result.error = f"Session execution failed: {type(e).__name__}: {e}"
        result.exception_text = traceback.format_exc()

    return result


def run_query_from_file(
    conn_state: dict,
    file_path: str,
    *,
    sid: str = "",
    label: str = "FILE_QUERY",
    sql_exec_wait: float = 10.0,
    retries: int = _MAX_RETRIES,
) -> QueryResult:
    """Load SQL from a file and execute it."""
    path = Path(file_path)
    if not path.exists():
        result = QueryResult(sql=f"-- File not found: {file_path}")
        result.error = f"SQL file not found: {file_path}"
        return result

    try:
        sql = path.read_text(encoding="utf-8")
    except Exception as e:
        result = QueryResult()
        result.error = f"Cannot read file {file_path}: {e}"
        return result

    return run_query(conn_state, sql, sid=sid, label=label, sql_exec_wait=sql_exec_wait, retries=retries)
