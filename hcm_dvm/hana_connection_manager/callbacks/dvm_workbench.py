"""SQL Workbench callbacks.

Handles:
  - Load patched SQL for selected analysis query
  - Edit and reset SQL
  - Execute (with read-only guard)
  - Free-form query mode
  - Origin badge display
"""

import re
import logging

from dash import Input, Output, State, html, no_update, ctx, dcc
import dash_bootstrap_components as dbc
import pandas as pd

from hana_connection_manager.dvm.registry import get_all_analyses, ANALYSIS_SPECS
from hana_connection_manager.dvm.analyses import get_sql_for_query, MiniCheckNotFoundError
from hana_connection_manager.dvm.execution import run_query
from hana_connection_manager.dvm.components import results_table

logger = logging.getLogger(__name__)

# Read-only guard: reject any DML/DDL
_DML_PATTERN = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|MERGE|UPSERT|GRANT|REVOKE|CALL)\b",
    re.IGNORECASE | re.MULTILINE,
)

# Allowed: SELECT or WITH...SELECT
_SELECT_PATTERN = re.compile(
    r"^\s*(SELECT|WITH)\b",
    re.IGNORECASE,
)


def _validate_sql(sql: str) -> str:
    """Validate SQL is read-only. Returns error message or empty string."""
    if not sql or not sql.strip():
        return "SQL is empty."
    # Check for DML
    match = _DML_PATTERN.search(sql)
    if match:
        return f"Blocked: '{match.group(1).upper()}' statements are not allowed. Only SELECT / WITH...SELECT queries are permitted."
    # Check it starts with SELECT or WITH
    if not _SELECT_PATTERN.match(sql.strip()):
        return "Only SELECT or WITH...SELECT queries are allowed."
    return ""


def _is_read_only(sql: str) -> bool:
    """Check if SQL is a read-only query (SELECT or WITH...SELECT).

    Returns True if the query is safe to execute, False otherwise.
    Used by the read-only guard to block DDL/DML.
    """
    return _validate_sql(sql) == ""


def register(app):
    """Register SQL Workbench callbacks."""
    analyses = get_all_analyses()

    # ──────────────────────────────────────────────────────────────
    # Load SQL when query selector changes
    # ──────────────────────────────────────────────────────────────
    @app.callback(
        [
            Output("workbench-sql-editor", "value"),
            Output("workbench-origin-badge", "children"),
            Output("workbench-origin-badge", "style"),
            Output("store-workbench-sql", "data"),
        ],
        Input("workbench-query-selector", "value"),
        State("store-hana-version", "data"),
        prevent_initial_call=True,
    )
    def load_query_sql(selector_value, version_data):
        if not selector_value or selector_value == "__freeform__":
            return (
                "",
                "",
                {"display": "none"},
                {"default_sql": "", "origin": "free-form"},
            )

        version_str = "2.00.080"
        if version_data and version_data.get("formatted"):
            version_str = version_data["formatted"]

        # Parse selector: "analysis_id::query_label"
        parts = selector_value.split("::", 1)
        if len(parts) != 2:
            return no_update, no_update, no_update, no_update

        analysis_id, query_label = parts
        spec = next((s for s in analyses if s["id"] == analysis_id), None)
        if not spec:
            return no_update, no_update, no_update, no_update

        query_spec = next((q for q in spec["queries"] if q["label"] == query_label), None)
        if not query_spec:
            return no_update, no_update, no_update, no_update

        try:
            sql, source_label = get_sql_for_query(query_spec, version_str)
        except (MiniCheckNotFoundError, ValueError) as e:
            return (
                f"-- Error loading SQL: {e}",
                "error",
                {"display": "inline-flex"},
                {"default_sql": "", "origin": "error"},
            )

        origin = source_label
        badge_class = "dvm-badge dvm-badge-info"
        if "mini-check" in source_label:
            if query_spec.get("patches"):
                origin = f"from mini-check (patched)"
                badge_class = "dvm-badge dvm-badge-info"
            else:
                origin = "from mini-check"
        elif "authored" in source_label:
            origin = "authored SQL"

        return (
            sql,
            origin,
            {"display": "inline-flex"},
            {"default_sql": sql, "origin": origin},
        )

    # ──────────────────────────────────────────────────────────────
    # Reset to default
    # ──────────────────────────────────────────────────────────────
    @app.callback(
        [
            Output("workbench-sql-editor", "value", allow_duplicate=True),
            Output("workbench-origin-badge", "children", allow_duplicate=True),
        ],
        Input("btn-workbench-reset", "n_clicks"),
        State("store-workbench-sql", "data"),
        prevent_initial_call=True,
    )
    def reset_sql(n_clicks, stored):
        if not n_clicks or not stored:
            return no_update, no_update
        return stored.get("default_sql", ""), stored.get("origin", "")

    # ──────────────────────────────────────────────────────────────
    # Execute SQL
    # ──────────────────────────────────────────────────────────────
    @app.callback(
        [
            Output("workbench-guard-msg", "children"),
            Output("workbench-results", "children"),
        ],
        Input("btn-workbench-run", "n_clicks"),
        [
            State("workbench-sql-editor", "value"),
            State("store-connection-state", "data"),
            State("store-workbench-sql", "data"),
        ],
        prevent_initial_call=True,
    )
    def execute_workbench(n_clicks, sql, conn_state, stored):
        if not n_clicks:
            return no_update, no_update

        # Connection check
        if not conn_state or not conn_state.get("connected"):
            return (
                html.Div(
                    [html.I(className="bi bi-exclamation-triangle me-2"),
                     html.Span("Not connected. Please connect first.")],
                    className="dvm-warning-card",
                ),
                no_update,
            )

        # Read-only guard
        error = _validate_sql(sql)
        if error:
            return (
                html.Div(
                    [html.I(className="bi bi-shield-exclamation me-2"),
                     html.Span(error)],
                    className="dvm-error-card",
                ),
                no_update,
            )

        # Determine origin label
        origin = "user-edited"
        if stored:
            if stored.get("default_sql") and sql.strip() == stored["default_sql"].strip():
                origin = stored.get("origin", "from mini-check")
            elif stored.get("origin") == "free-form":
                origin = "free-form"

        # Execute
        qr = run_query(
            conn_state, sql,
            sid=conn_state.get("system_id", ""),
            label="WORKBENCH",
        )

        if not qr.success:
            return (
                "",  # clear guard msg
                html.Div(
                    [
                        html.Div(
                            [html.I(className="bi bi-x-circle me-2"),
                             html.Span(f"Query failed: {qr.error}")],
                            className="dvm-error-card",
                        ),
                    ],
                ),
            )

        # Render results
        elapsed = f"{qr.elapsed_ms:.0f} ms" if qr.elapsed_ms < 1000 else f"{qr.elapsed_ms/1000:.1f} s"
        header = html.Div(
            [
                html.Span(f"\u2713 {qr.row_count} rows \u00d7 {qr.col_count} cols",
                          className="dvm-badge dvm-badge-success"),
                html.Span(elapsed, className="dvm-badge dvm-badge-neutral",
                          style={"marginLeft": "6px"}),
                html.Span(origin, className="dvm-badge dvm-badge-info",
                          style={"marginLeft": "6px"}),
            ],
            style={"marginBottom": "12px"},
        )

        table = results_table(qr.df, max_rows=200)

        return "", html.Div([header, table])
