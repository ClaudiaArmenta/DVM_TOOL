"""Offline mode callbacks.

Handles:
  - Display SQL for each analysis (with copy)
  - Upload CSV/XLSX result files
  - Parse uploaded files into DataFrames
  - Render results with same renderers as live mode
  - Export offline results to DVM_tool.xlsx
"""

import io
import base64
import logging

from dash import Input, Output, State, html, no_update, ctx, dcc
import dash_bootstrap_components as dbc
import pandas as pd

from hana_connection_manager.dvm.registry import get_all_analyses, ANALYSIS_SPECS
from hana_connection_manager.dvm.analyses import get_sql_for_query, MiniCheckNotFoundError
from hana_connection_manager.dvm.renderers import RENDERERS
from hana_connection_manager.dvm.export import export_to_excel
from hana_connection_manager.dvm.components import results_table, parse_output_params

logger = logging.getLogger(__name__)

# Cache: analysis_id -> set of expected output column names (from the SQL docs).
_COL_INDEX = None


def _get_col_index(analyses, version="2.00.080"):
    """Map each analysis to the union of its queries' documented output columns."""
    global _COL_INDEX
    if _COL_INDEX is not None:
        return _COL_INDEX
    idx = {}
    for spec in analyses:
        cols = set()
        for q in spec.get("queries", []):
            try:
                sql, _ = get_sql_for_query(q, version)
                cols |= set(parse_output_params(sql).keys())
            except Exception:
                pass
        idx[spec["id"]] = cols
    _COL_INDEX = idx
    return idx


def _detect_analysis(df, analyses, version="2.00.080"):
    """Guess which analysis an uploaded file belongs to, from its columns.

    Returns (analysis_id or None, score 0..1). Uses the documented output
    columns of each analysis, plus heuristics for the custom-shaped A2 data.
    """
    up = set(str(c).upper().strip() for c in df.columns)

    def has(*subs):
        return any(all(s in c for s in subs) for c in up)

    ids = {s["id"] for s in analyses}
    # A2 data is user-shaped (not the raw SQL output) — detect it by signature.
    if "a2_db_size_history" in ids:
        snapshot = has("DISK", "SIZE") or has("COLUMN", "STORE") or has("ROW", "STORE")
        has_time = any(c in ("DATE", "MONTH", "YEAR", "TIME") or "DATE" in c
                       or "TIME" in c or "SNAPSHOT" in c for c in up)
        history = has_time and (has("MEMORY", "USED") or has("MEM", "USED")
                                or has("DISK", "USED"))
        if snapshot or history:
            return "a2_db_size_history", 1.0

    idx = _get_col_index(analyses, version)
    best_id, best = None, 0.0
    for aid, cols in idx.items():
        if not cols:
            continue
        score = len(up & cols) / max(1, len(up))
        if score > best:
            best, best_id = score, aid
    return (best_id if best >= 0.4 else None), best


def _parse_upload(content: str, filename: str) -> pd.DataFrame:
    """Parse an uploaded file (CSV or XLSX) into a DataFrame."""
    # content is base64-encoded with a MIME prefix
    content_type, content_string = content.split(",", 1)
    decoded = base64.b64decode(content_string)

    if filename.endswith(".csv"):
        # Try common encodings
        for enc in ["utf-8", "latin1", "cp1252"]:
            try:
                df = pd.read_csv(io.BytesIO(decoded), encoding=enc, sep=None, engine="python")
                return df
            except Exception:
                continue
        return pd.read_csv(io.BytesIO(decoded))
    elif filename.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(decoded))
    else:
        raise ValueError(f"Unsupported file type: {filename}")


def register(app):
    """Register Offline mode callbacks."""
    analyses = get_all_analyses()

    # ──────────────────────────────────────────────────────────────
    # Display SQL for selected query
    # ──────────────────────────────────────────────────────────────
    @app.callback(
        [
            Output("offline-sql-display", "children"),
            Output("clipboard-offline-sql", "content"),
        ],
        Input("offline-query-selector", "value"),
        State("store-hana-version", "data"),
    )
    def display_offline_sql(selector_value, version_data):
        if not selector_value:
            return html.Div("Select a query above.", className="dvm-empty-state"), ""

        version_str = "2.00.080"
        if version_data and version_data.get("formatted"):
            version_str = version_data["formatted"]

        # Parse "analysis_id::query_label"
        parts = selector_value.split("::", 1)
        if len(parts) != 2:
            return html.Div("Invalid selection."), ""

        analysis_id, query_label = parts
        spec = next((s for s in analyses if s["id"] == analysis_id), None)
        if not spec:
            return html.Div("Analysis not found."), ""

        query_spec = next((q for q in spec["queries"] if q["label"] == query_label), None)
        if not query_spec:
            return html.Div("Query not found."), ""

        try:
            sql, source_label = get_sql_for_query(query_spec, version_str)
        except (MiniCheckNotFoundError, ValueError) as e:
            return (
                html.Div(
                    [html.I(className="bi bi-exclamation-triangle me-2"),
                     html.Span(f"Could not load SQL: {e}")],
                    className="dvm-error-card",
                ),
                "",
            )

        # Truncate display but keep full for clipboard
        display_sql = sql if len(sql) <= 5000 else sql[:5000] + "\n\n-- ... (truncated for display, full SQL copied)"

        return (
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(source_label, className="dvm-badge dvm-badge-info"),
                            html.Span(f"{len(sql):,} chars", className="dvm-badge dvm-badge-neutral",
                                      style={"marginLeft": "6px"}),
                        ],
                        style={"marginBottom": "8px"},
                    ),
                    html.Pre(
                        html.Code(display_sql),
                        className="dvm-code-readonly",
                    ),
                ],
            ),
            sql,  # Full SQL for clipboard
        )

    # ──────────────────────────────────────────────────────────────
    # Copy SQL button -> trigger clipboard
    # ──────────────────────────────────────────────────────────────
    @app.callback(
        Output("clipboard-offline-sql", "n_clicks"),
        Input("btn-offline-copy", "n_clicks"),
        prevent_initial_call=True,
    )
    def trigger_copy(n_clicks):
        if not n_clicks:
            return no_update
        return 1  # Trigger the clipboard component

    # ──────────────────────────────────────────────────────────────
    # Upload results
    # ──────────────────────────────────────────────────────────────
    _title_by_id = {s["id"]: s["title"] for s in analyses}

    @app.callback(
        [
            Output("offline-upload-status", "children"),
            Output("store-offline-results", "data"),
        ],
        Input("offline-upload", "contents"),
        [
            State("offline-upload", "filename"),
            State("offline-upload-target", "value"),
            State("store-offline-results", "data"),
            State("store-hana-version", "data"),
        ],
        prevent_initial_call=True,
    )
    def process_upload(contents, filenames, target_analysis, existing_data, version_data):
        if not contents:
            return no_update, no_update

        existing_data = existing_data or {}
        version_str = version_data.get("formatted", "2.00.080") if version_data else "2.00.080"
        auto = (not target_analysis) or target_analysis == "__auto__"

        grouped = {}      # analysis_id -> list of result dicts
        detected = []     # (filename, analysis_id, auto?)
        errors = []

        for content, filename in zip(contents, filenames):
            try:
                df = _parse_upload(content, filename)
            except Exception as e:
                errors.append(f"{filename}: {e}")
                continue

            if auto:
                aid, _score = _detect_analysis(df, analyses, version_str)
            else:
                aid = target_analysis

            if not aid:
                errors.append(f"{filename}: couldn't auto-detect the analysis "
                              f"(pick it manually and re-upload)")
                continue

            grouped.setdefault(aid, []).append({
                "success": True,
                "df_json": df.to_json(orient="split", date_format="iso"),
                "enrichment_df_json": None,
                "row_count": len(df),
                "col_count": len(df.columns),
                "elapsed_ms": 0,
                "error": "",
                "sql": f"-- Uploaded from {filename}",
                "source_label": f"uploaded ({filename})",
                "exception_text": "",
            })
            detected.append((filename, aid, auto))

        for aid, lst in grouped.items():
            existing_data[aid] = lst

        # Status: list what each file was assigned to (auto-detected or manual).
        rows = []
        for filename, aid, was_auto in detected:
            title = _title_by_id.get(aid, aid)
            tag = " (auto)" if was_auto else ""
            rows.append(html.Div(
                [html.I(className="bi bi-check-circle-fill me-2",
                        style={"color": "var(--dvm-success)"}),
                 html.Span(f"{filename}  →  {title}{tag}")],
                style={"fontSize": "13px", "padding": "2px 0"},
            ))
        for err in errors:
            rows.append(html.Div(
                [html.I(className="bi bi-exclamation-triangle me-2",
                        style={"color": "var(--dvm-warning)"}),
                 html.Span(err)],
                style={"fontSize": "13px", "padding": "2px 0"},
            ))

        cls = "dvm-warning-card" if (errors and not detected) else "dvm-success-card"
        status = html.Div(rows or [html.Span("No files processed.")],
                          className=cls,
                          style={"flexDirection": "column", "alignItems": "stretch"})
        return status, existing_data

    # ──────────────────────────────────────────────────────────────
    # Render offline results
    # ──────────────────────────────────────────────────────────────
    @app.callback(
        Output("offline-results-display", "children"),
        Input("store-offline-results", "data"),
        State("store-hana-version", "data"),
    )
    def render_offline_results(offline_data, version_data):
        if not offline_data:
            return html.Div(
                [html.I(className="bi bi-cloud-arrow-up",
                        style={"fontSize": "24px", "color": "var(--dvm-border)"}),
                 html.P("Upload result files to see rendered output.")],
                className="dvm-empty-state",
            )

        version_str = version_data.get("formatted", "2.00.080") if version_data else "2.00.080"

        sections = []
        for spec in analyses:
            aid = spec["id"]
            if aid not in offline_data:
                continue

            serialized = offline_data[aid]
            # Deserialize
            results = []
            for entry in serialized:
                r = dict(entry)
                if r.get("df_json"):
                    try:
                        r["df"] = pd.read_json(io.StringIO(r["df_json"]), orient="split")
                    except Exception:
                        r["df"] = None
                else:
                    r["df"] = None
                r["enrichment_df"] = None
                results.append(r)

            renderer_fn = RENDERERS.get(aid)
            if renderer_fn:
                try:
                    content = renderer_fn(results, version_str)
                except Exception as e:
                    content = html.Div(f"Render error: {e}", className="dvm-error-card")
            else:
                content = results_table(results[0].get("df") if results else None)

            sections.append(
                html.Div(
                    [
                        html.H4(spec["title"], style={
                            "fontSize": "14px", "fontWeight": "600",
                            "color": "var(--dvm-text)", "marginBottom": "8px",
                        }),
                        content,
                    ],
                    style={"marginBottom": "24px", "paddingBottom": "16px",
                           "borderBottom": "1px solid var(--dvm-border)"},
                )
            )

        if not sections:
            return html.Div("No results uploaded yet.", className="dvm-empty-state")
        return html.Div(sections)

    # ──────────────────────────────────────────────────────────────
    # Export offline results
    # ──────────────────────────────────────────────────────────────
    @app.callback(
        Output("download-excel", "data", allow_duplicate=True),
        Input("btn-offline-export", "n_clicks"),
        State("store-offline-results", "data"),
        prevent_initial_call=True,
    )
    def export_offline(n_clicks, offline_data):
        if not n_clicks or not offline_data:
            return no_update

        # Deserialize all
        all_results = {}
        for aid, serialized in offline_data.items():
            results = []
            for entry in serialized:
                r = dict(entry)
                if r.get("df_json"):
                    try:
                        r["df"] = pd.read_json(io.StringIO(r["df_json"]), orient="split")
                    except Exception:
                        r["df"] = None
                else:
                    r["df"] = None
                r["enrichment_df"] = None
                results.append(r)
            all_results[aid] = results

        try:
            xlsx_bytes = export_to_excel(all_results)
        except Exception as e:
            logger.warning(f"Offline export failed: {e}")
            return no_update

        return dcc.send_bytes(xlsx_bytes, "DVM_tool.xlsx")
