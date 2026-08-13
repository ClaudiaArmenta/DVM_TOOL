"""DVM analyses callbacks.

Handles:
  - "Run All Analyses" / "Run Selected" with live 0-100% progress.
  - Incremental rendering: each analysis section fills as it completes.
  - Per-analysis "Run" buttons (from each section).
  - Per-analysis "Export" buttons (export single analysis to xlsx).
  - "Export All" / "Export Selected" from Overview.
  - Status dot updates (pending/running/done/error) on section tabs.
  - Worker thread + fast dcc.Interval (500ms during run, disabled when idle).
"""

import io
import time
import uuid
import logging
import threading
import traceback
from pathlib import Path
from typing import List, Dict, Optional

from dash import Input, Output, State, html, no_update, ctx, dcc
import dash_bootstrap_components as dbc
import pandas as pd

from hana_connection_manager.dvm.registry import get_all_analyses, ANALYSIS_SPECS
from hana_connection_manager.dvm.analyses import get_sql_for_query, MiniCheckNotFoundError
from hana_connection_manager.dvm.execution import run_query, QueryResult
from hana_connection_manager.dvm.renderers import RENDERERS
from hana_connection_manager.dvm.version_select import get_queries_dir
from hana_connection_manager.dvm.export import export_to_excel

logger = logging.getLogger(__name__)

# ===================================================================
# MODULE-LEVEL PROGRESS STATE (shared between worker thread and Interval)
# ===================================================================

_run_state_lock = threading.Lock()
_run_state: Dict[str, dict] = {}


def _get_run_state(run_id: str) -> Optional[dict]:
    with _run_state_lock:
        return _run_state.get(run_id)


def _set_run_state(run_id: str, state: dict):
    with _run_state_lock:
        _run_state[run_id] = state


def _clear_run_state(run_id: str):
    with _run_state_lock:
        _run_state.pop(run_id, None)


# ===================================================================
# QUERY HELPERS
# ===================================================================

def _get_table_description_sql() -> Optional[str]:
    queries_dir = get_queries_dir()
    script_path = Path(queries_dir) / "SQLStatements_table_description.sql"
    if script_path.exists():
        return script_path.read_text(encoding="utf-8")
    return None


def _execute_single_query(conn_state, query_spec, version_str, sid="", label=""):
    """Execute a single query spec and return a result dict."""
    try:
        sql, source_label = get_sql_for_query(query_spec, version_str)
        qr = run_query(conn_state, sql, sid=sid, label=label)
        return {
            "success": qr.success,
            "sql": qr.sql,
            "elapsed_ms": qr.elapsed_ms,
            "row_count": qr.row_count,
            "col_count": qr.col_count,
            "error": qr.error,
            "exception_text": qr.exception_text,
            "source_label": source_label,
            "df": qr.df,
            "enrichment_df": None,
        }
    except MiniCheckNotFoundError as e:
        return {"success": False, "sql": "", "elapsed_ms": 0, "row_count": 0,
                "col_count": 0, "error": str(e), "exception_text": "",
                "source_label": "script not found", "df": None, "enrichment_df": None}
    except ValueError as e:
        return {"success": False, "sql": "", "elapsed_ms": 0, "row_count": 0,
                "col_count": 0, "error": f"Patch error: {e}",
                "exception_text": traceback.format_exc(),
                "source_label": "patch failed", "df": None, "enrichment_df": None}
    except Exception as e:
        return {"success": False, "sql": "", "elapsed_ms": 0, "row_count": 0,
                "col_count": 0, "error": f"Unexpected error: {e}",
                "exception_text": traceback.format_exc(),
                "source_label": "error", "df": None, "enrichment_df": None}


def _run_enrichment(conn_state, spec, results):
    enrichments = spec.get("enrichments")
    if not enrichments:
        return results
    for enrichment in enrichments:
        if enrichment.get("type") == "table_description":
            desc_sql = _get_table_description_sql()
            if not desc_sql:
                continue
            try:
                qr = run_query(conn_state, desc_sql,
                               sid=conn_state.get("system_id", ""),
                               label="table_description")
                if qr.success and qr.df is not None and not qr.df.empty:
                    for r in results:
                        r["enrichment_df"] = qr.df
            except Exception as e:
                logger.warning(f"  Table description enrichment failed: {e}")
    return results


# ===================================================================
# SERIALIZATION (io.StringIO fix for pandas >= 2.1)
# ===================================================================

def _serialize_results(results_list):
    """Serialize result dicts for dcc.Store (DataFrames -> JSON)."""
    serialized = []
    for r in results_list:
        entry = {k: v for k, v in r.items() if k not in ("df", "enrichment_df")}
        if r.get("df") is not None:
            entry["df_json"] = r["df"].to_json(orient="split", date_format="iso")
        else:
            entry["df_json"] = None
        if r.get("enrichment_df") is not None:
            entry["enrichment_df_json"] = r["enrichment_df"].to_json(orient="split", date_format="iso")
        else:
            entry["enrichment_df_json"] = None
        serialized.append(entry)
    return serialized


def _deserialize_results(serialized_list):
    """Deserialize stored results (JSON -> DataFrames via io.StringIO)."""
    results = []
    for entry in serialized_list:
        r = dict(entry)
        if r.get("df_json"):
            try:
                r["df"] = pd.read_json(io.StringIO(r["df_json"]), orient="split")
            except Exception as e:
                logger.warning(f"Failed to deserialize df_json: {e}")
                r["df"] = None
        else:
            r["df"] = None
        if r.get("enrichment_df_json"):
            try:
                r["enrichment_df"] = pd.read_json(io.StringIO(r["enrichment_df_json"]), orient="split")
            except Exception as e:
                logger.warning(f"Failed to deserialize enrichment_df_json: {e}")
                r["enrichment_df"] = None
        else:
            r["enrichment_df"] = None
        results.append(r)
    return results


# ===================================================================
# WORKER THREAD for live progress
# ===================================================================

def _worker_run_analyses(run_id, conn_state, version_str, sid, analysis_ids):
    """Worker thread: executes selected analyses serially, updating progress.

    After each analysis completes, its results are immediately available
    in state['results'][aid] for the poll callback to render incrementally.
    """
    analyses = [s for s in ANALYSIS_SPECS
                if s["id"] in analysis_ids and s.get("enabled", True)]
    total_queries = sum(len(spec["queries"]) for spec in analyses)
    for spec in analyses:
        if spec.get("enrichments"):
            total_queries += 1

    state = {
        "total": total_queries,
        "completed": 0,
        "current_label": "",
        "current_aid": "",
        "done": False,
        "results": {},
        "analysis_ids": analysis_ids,
    }
    _set_run_state(run_id, state)

    for spec in analyses:
        aid = spec["id"]
        state["current_aid"] = aid
        results = []
        for query_spec in spec["queries"]:
            state["current_label"] = f"{aid.split('_')[0].upper()}: {query_spec['label']}"
            _set_run_state(run_id, state)

            r = _execute_single_query(
                conn_state, query_spec, version_str,
                sid=sid, label=f"{aid}_{query_spec['label']}",
            )
            results.append(r)
            state["completed"] += 1
            _set_run_state(run_id, state)

        # Enrichment
        if spec.get("enrichments"):
            state["current_label"] = f"{aid.split('_')[0].upper()}: enrichment"
            _set_run_state(run_id, state)
            results = _run_enrichment(conn_state, spec, results)
            state["completed"] += 1
            _set_run_state(run_id, state)

        # Store results immediately for this analysis
        state["results"][aid] = results
        _set_run_state(run_id, state)

    state["done"] = True
    state["current_aid"] = ""
    state["current_label"] = ""
    _set_run_state(run_id, state)


# ===================================================================
# CALLBACKS
# ===================================================================

def register(app):
    """Register DVM analyses callbacks."""
    analyses = get_all_analyses()
    n_analyses = len(analyses)

    # Per-analysis Run and Export buttons
    for spec in analyses:
        _register_single_analysis_run(app, spec)
        _register_single_analysis_export(app, spec)

    # ==============================================================
    # Run All / Run Selected: Start worker thread + enable interval
    # ==============================================================
    @app.callback(
        [
            Output("store-run-progress", "data"),
            Output("interval-progress", "disabled"),
            Output("progress-container", "style"),
            Output("analyses-run-status", "children"),
        ]
        + [Output(f"status-dot-{s['id']}", "className", allow_duplicate=True)
           for s in analyses],
        [
            Input("btn-run-all-analyses", "n_clicks"),
            Input("btn-run-selected", "n_clicks"),
        ],
        [
            State("store-connection-state", "data"),
            State("store-hana-version", "data"),
            State("checklist-analyses", "value"),
        ],
        prevent_initial_call=True,
    )
    def start_run(run_all_clicks, run_sel_clicks, conn_state, version_data, selected):
        n_base = 4
        n_out = n_base + n_analyses
        triggered = ctx.triggered_id

        if not conn_state or not conn_state.get("connected"):
            msg = html.Div(
                [html.I(className="bi bi-exclamation-triangle me-2"),
                 html.Span("Not connected. Please connect first.")],
                className="dvm-warning-card",
            )
            return [no_update, no_update, no_update, msg] + [no_update] * n_analyses

        if not version_data or not version_data.get("formatted"):
            msg = html.Div(
                [html.I(className="bi bi-exclamation-triangle me-2"),
                 html.Span("No HANA version detected or selected.")],
                className="dvm-warning-card",
            )
            return [no_update, no_update, no_update, msg] + [no_update] * n_analyses

        # Determine which analyses to run
        if triggered == "btn-run-all-analyses":
            analysis_ids = [s["id"] for s in analyses]
        else:
            analysis_ids = selected or []

        if not analysis_ids:
            msg = html.Div(
                [html.I(className="bi bi-info-circle me-2"),
                 html.Span("No analyses selected.")],
                className="dvm-info-card",
            )
            return [no_update, no_update, no_update, msg] + [no_update] * n_analyses

        version_str = version_data["formatted"]
        sid = conn_state.get("system_id", "")
        run_id = str(uuid.uuid4())[:8]

        t = threading.Thread(
            target=_worker_run_analyses,
            args=(run_id, conn_state, version_str, sid, analysis_ids),
            daemon=True,
        )
        t.start()

        # Set status dots: "running" for selected, unchanged for others
        dots = []
        for spec in analyses:
            if spec["id"] in analysis_ids:
                dots.append("dvm-status-indicator running")
            else:
                dots.append(no_update)

        return [
            {"run_id": run_id, "analysis_ids": analysis_ids},
            False,  # enable interval
            {"display": "block"},  # show progress
            "",
        ] + dots

    # ==============================================================
    # Interval: poll progress + render incrementally
    # ==============================================================
    @app.callback(
        [
            Output("progress-bar-fill", "style"),
            Output("progress-text", "children"),
            Output("progress-pct", "children"),
            Output("interval-progress", "disabled", allow_duplicate=True),
            Output("store-analysis-results", "data"),
            Output("btn-export-excel", "style"),
            Output("btn-export-selected", "style"),
        ]
        + [Output(f"tab-content-{s['id']}", "children", allow_duplicate=True) for s in analyses]
        + [Output(f"overview-status-{s['id']}", "className", allow_duplicate=True) for s in analyses]
        + [Output(f"overview-summary-{s['id']}", "children", allow_duplicate=True) for s in analyses]
        + [Output(f"status-dot-{s['id']}", "className", allow_duplicate=True) for s in analyses],
        Input("interval-progress", "n_intervals"),
        [
            State("store-run-progress", "data"),
            State("store-hana-version", "data"),
            State("store-analysis-results", "data"),
        ],
        prevent_initial_call=True,
    )
    def poll_progress(n_intervals, progress_data, version_data, current_store):
        n_base = 7
        n_outputs = n_base + 4 * n_analyses
        if not progress_data or not progress_data.get("run_id"):
            return [no_update] * n_outputs

        run_id = progress_data["run_id"]
        state = _get_run_state(run_id)
        if not state:
            return [no_update] * n_outputs

        total = max(state["total"], 1)
        completed = state["completed"]
        pct = int(completed / total * 100)
        current = state.get("current_label", "")

        version_str = version_data.get("formatted", "2.00.080") if version_data else "2.00.080"

        # Per-analysis incremental outputs
        tab_contents = [no_update] * n_analyses
        overview_statuses = [no_update] * n_analyses
        overview_summaries = [no_update] * n_analyses
        status_dots = [no_update] * n_analyses

        # Track what's already been rendered to the store
        already_rendered = set()
        if current_store:
            already_rendered = set(current_store.keys())

        # Render newly completed analyses
        new_store = dict(current_store) if current_store else {}
        for idx, spec in enumerate(analyses):
            aid = spec["id"]
            if aid in state["results"] and aid not in already_rendered:
                # This analysis just completed - render it
                results = state["results"][aid]
                renderer_fn = RENDERERS.get(aid)

                if renderer_fn:
                    try:
                        tab_contents[idx] = renderer_fn(results, version_str)
                    except Exception as e:
                        tab_contents[idx] = html.Div(f"Render error: {e}",
                                                      className="dvm-error-card")
                else:
                    tab_contents[idx] = html.Div("No renderer.", className="dvm-empty-state")

                # Overview status
                all_ok = all(r["success"] for r in results)
                total_rows = sum(r.get("row_count", 0) for r in results)
                total_ms = sum(r.get("elapsed_ms", 0) for r in results)
                if all_ok:
                    overview_statuses[idx] = "dvm-status-indicator done"
                    overview_summaries[idx] = f"{total_rows} rows, {total_ms:.0f}ms"
                    status_dots[idx] = "dvm-status-indicator done"
                else:
                    overview_statuses[idx] = "dvm-status-indicator error"
                    overview_summaries[idx] = "Error"
                    status_dots[idx] = "dvm-status-indicator error"

                # Add to store
                new_store[aid] = _serialize_results(results)

        store_update = new_store if new_store != (current_store or {}) else no_update

        # Base outputs
        if not state["done"]:
            return [
                {"width": f"{pct}%"},
                f"Running: {current} ({completed}/{total})",
                f"{pct}%",
                False,  # keep interval
                store_update,
                no_update,
                no_update,
            ] + tab_contents + overview_statuses + overview_summaries + status_dots

        # Done
        _clear_run_state(run_id)
        total_queries = sum(len(r) for r in state["results"].values())
        success_count = sum(1 for results in state["results"].values()
                           for r in results if r["success"])

        return [
            {"width": "100%"},
            f"Done ({success_count}/{total_queries} queries OK)",
            "100%",
            True,  # disable interval
            store_update,
            {"display": "inline-flex"},  # show export all
            {"display": "inline-flex"},  # show export selected
        ] + tab_contents + overview_statuses + overview_summaries + status_dots

    # ==============================================================
    # Render results into tabs (initial load from store)
    # ==============================================================
    @app.callback(
        [Output(f"tab-content-{s['id']}", "children") for s in analyses],
        Input("store-analysis-results", "data"),
        State("store-hana-version", "data"),
    )
    def render_results(store_data, version_data):
        if not store_data:
            return [html.Div(
                [html.I(className="bi bi-inbox", style={"fontSize": "24px",
                         "color": "var(--dvm-border)"}),
                 html.P("No results yet. Run this analysis or use Run All.")],
                className="dvm-empty-state",
            )] * n_analyses

        version_str = version_data.get("formatted", "2.00.080") if version_data else "2.00.080"
        tab_contents = []

        for spec in analyses:
            aid = spec["id"]
            renderer_fn = RENDERERS.get(aid)

            if aid not in store_data:
                tab_contents.append(html.Div(
                    [html.I(className="bi bi-inbox", style={"fontSize": "24px",
                             "color": "var(--dvm-border)"}),
                     html.P("No results yet. Run this analysis or use Run All.")],
                    className="dvm-empty-state",
                ))
                continue

            results = _deserialize_results(store_data[aid])

            if renderer_fn:
                try:
                    tab_contents.append(renderer_fn(results, version_str))
                except Exception as e:
                    tab_contents.append(html.Div(f"Render error: {e}",
                                                  className="dvm-error-card"))
            else:
                tab_contents.append(html.Div(f"No renderer for {aid}.",
                                             className="dvm-empty-state"))

        return tab_contents

    # ==============================================================
    # Export All / Export Selected (from Overview)
    # ==============================================================
    @app.callback(
        Output("download-excel", "data"),
        [
            Input("btn-export-excel", "n_clicks"),
            Input("btn-export-selected", "n_clicks"),
        ],
        [
            State("store-analysis-results", "data"),
            State("checklist-analyses", "value"),
        ],
        prevent_initial_call=True,
    )
    def export_excel(n_all, n_sel, store_data, selected):
        if not store_data:
            return no_update
        triggered = ctx.triggered_id

        if triggered == "btn-export-excel":
            target_ids = list(store_data.keys())
        else:
            target_ids = [aid for aid in (selected or []) if aid in store_data]

        if not target_ids:
            return no_update

        all_results = {}
        for aid in target_ids:
            if aid in store_data:
                all_results[aid] = _deserialize_results(store_data[aid])

        try:
            xlsx_bytes = export_to_excel(all_results)
        except Exception as e:
            logger.warning(f"Excel export failed: {e}")
            return no_update
        return dcc.send_bytes(xlsx_bytes, "DVM_tool.xlsx")


# ===================================================================
# PER-ANALYSIS RUN BUTTON
# ===================================================================

def _register_single_analysis_run(app, spec):
    """Register a per-analysis Run button callback."""
    analysis_id = spec["id"]

    @app.callback(
        [
            Output(f"tab-content-{analysis_id}", "children", allow_duplicate=True),
            Output(f"overview-status-{analysis_id}", "className", allow_duplicate=True),
            Output(f"overview-summary-{analysis_id}", "children", allow_duplicate=True),
            Output(f"status-dot-{analysis_id}", "className", allow_duplicate=True),
            Output("store-analysis-results", "data", allow_duplicate=True),
        ],
        Input(f"btn-run-{analysis_id}", "n_clicks"),
        [
            State("store-connection-state", "data"),
            State("store-hana-version", "data"),
            State("store-analysis-results", "data"),
        ],
        prevent_initial_call=True,
    )
    def run_single_analysis(n_clicks, conn_state, version_data, current_store, _spec=spec):
        if not n_clicks:
            return no_update, no_update, no_update, no_update, no_update

        if not conn_state or not conn_state.get("connected"):
            return (
                html.Div([html.I(className="bi bi-exclamation-triangle me-2"),
                          html.Span("Not connected.")], className="dvm-warning-card"),
                "dvm-status-indicator error",
                "Not connected",
                "dvm-status-indicator error",
                no_update,
            )

        if not version_data or not version_data.get("formatted"):
            return (
                html.Div([html.I(className="bi bi-exclamation-triangle me-2"),
                          html.Span("No version selected.")], className="dvm-warning-card"),
                "dvm-status-indicator error",
                "No version",
                "dvm-status-indicator error",
                no_update,
            )

        version_str = version_data["formatted"]
        sid = conn_state.get("system_id", "")

        results = []
        for query_spec in _spec["queries"]:
            r = _execute_single_query(conn_state, query_spec, version_str,
                                      sid=sid, label=f"{_spec['id']}_{query_spec['label']}")
            results.append(r)
        results = _run_enrichment(conn_state, _spec, results)

        all_ok = all(r["success"] for r in results)
        total_rows = sum(r.get("row_count", 0) for r in results)
        total_ms = sum(r.get("elapsed_ms", 0) for r in results)

        # Render tab content
        renderer_fn = RENDERERS.get(_spec["id"])
        if renderer_fn:
            try:
                content = renderer_fn(results, version_str)
            except Exception as e:
                content = html.Div(f"Render error: {e}", className="dvm-error-card")
        else:
            content = html.Div("No renderer.", className="dvm-empty-state")

        # Status
        if all_ok:
            ov_class = "dvm-status-indicator done"
            summary = f"{total_rows} rows, {total_ms:.0f}ms"
            dot_class = "dvm-status-indicator done"
        else:
            ov_class = "dvm-status-indicator error"
            summary = "Error"
            dot_class = "dvm-status-indicator error"

        # Update store
        new_store = dict(current_store) if current_store else {}
        new_store[_spec["id"]] = _serialize_results(results)

        return content, ov_class, summary, dot_class, new_store


# ===================================================================
# PER-ANALYSIS EXPORT BUTTON
# ===================================================================

def _register_single_analysis_export(app, spec):
    """Register a per-analysis Export button callback."""
    analysis_id = spec["id"]

    @app.callback(
        Output("download-excel-single", "data", allow_duplicate=True),
        Input(f"btn-export-{analysis_id}", "n_clicks"),
        State("store-analysis-results", "data"),
        prevent_initial_call=True,
    )
    def export_single(n_clicks, store_data, _aid=analysis_id):
        if not n_clicks or not store_data or _aid not in store_data:
            return no_update

        results = _deserialize_results(store_data[_aid])
        try:
            xlsx_bytes = export_to_excel({_aid: results})
        except Exception as e:
            logger.warning(f"Export for {_aid} failed: {e}")
            return no_update
        short = _aid.split("_")[0].upper()
        return dcc.send_bytes(xlsx_bytes, f"DVM_{short}.xlsx")
