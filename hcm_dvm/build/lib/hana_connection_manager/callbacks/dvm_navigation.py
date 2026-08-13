"""DVM navigation callbacks (vertical sidebar).

Handles:
  - Top-level nav: Analyses | Offline
  - Left sidebar: Overview | A1 | A2 | ... | A6 (switches right panel)
  - Goto from overview cards -> switch to that analysis section
  - Version panel open/close + version selection + auto-detect on connect
  - Connection badge updates from store
"""

from dash import Input, Output, State, html, no_update, ctx
import dash_bootstrap_components as dbc

from hana_connection_manager.dvm.execution import run_query
from hana_connection_manager.dvm.version_select import (
    parse_hana_version,
    format_version_tuple,
)
from hana_connection_manager.dvm.registry import get_all_analyses, ANALYSIS_SPECS

# All section IDs (overview + per-analysis)
_ANALYSIS_IDS = [s["id"] for s in ANALYSIS_SPECS]
_SECTION_IDS = ["overview"] + _ANALYSIS_IDS
_SECTION_ELEM_IDS = [f"section-{sid}" for sid in _SECTION_IDS]
_SIDEBAR_ITEM_IDS = ["sidebar-item-overview"] + [f"sidebar-item-{sid}" for sid in _ANALYSIS_IDS]

_HIDE = {"display": "none"}
_SHOW = {"display": "block"}


def register(app):
    """Register DVM navigation callbacks."""
    analyses = get_all_analyses()
    n = len(analyses)

    # ==============================================================
    # Top-level Nav: Analyses | Offline
    # ==============================================================
    @app.callback(
        [
            Output("screen-analyses", "style", allow_duplicate=True),
            Output("screen-offline", "style", allow_duplicate=True),
            Output("nav-tab-analyses", "className"),
            Output("nav-tab-offline", "className"),
        ],
        [
            Input("nav-tab-analyses", "n_clicks"),
            Input("nav-tab-offline", "n_clicks"),
        ],
        prevent_initial_call=True,
    )
    def nav_tab_click(analyses_clicks, offline_clicks):
        triggered = ctx.triggered_id
        if triggered == "nav-tab-analyses":
            return {"display": "flex"}, _HIDE, "dvm-nav-tab active", "dvm-nav-tab"
        elif triggered == "nav-tab-offline":
            return _HIDE, _SHOW, "dvm-nav-tab", "dvm-nav-tab active"
        return no_update, no_update, no_update, no_update

    # ==============================================================
    # Sidebar Navigation: click sidebar items to switch sections
    # ==============================================================
    @app.callback(
        [Output(eid, "style", allow_duplicate=True) for eid in _SECTION_ELEM_IDS]
        + [Output(sid, "className", allow_duplicate=True) for sid in _SIDEBAR_ITEM_IDS],
        [Input(sid, "n_clicks") for sid in _SIDEBAR_ITEM_IDS],
        prevent_initial_call=True,
    )
    def sidebar_item_click(*args):
        triggered = ctx.triggered_id
        if not triggered:
            return [no_update] * (2 * len(_SECTION_IDS))

        # Find which sidebar item was clicked
        target_idx = None
        for i, sid in enumerate(_SIDEBAR_ITEM_IDS):
            if triggered == sid:
                target_idx = i
                break

        if target_idx is None:
            return [no_update] * (2 * len(_SECTION_IDS))

        # Show only the target section
        section_styles = [_SHOW if i == target_idx else _HIDE
                          for i in range(len(_SECTION_IDS))]
        # Highlight the active sidebar item
        sidebar_classes = ["dvm-sidebar-item active" if i == target_idx else "dvm-sidebar-item"
                           for i in range(len(_SECTION_IDS))]

        return section_styles + sidebar_classes

    # ==============================================================
    # Goto from overview cards -> switch to analysis section
    # ==============================================================
    @app.callback(
        [Output(eid, "style", allow_duplicate=True) for eid in _SECTION_ELEM_IDS]
        + [Output(sid, "className", allow_duplicate=True) for sid in _SIDEBAR_ITEM_IDS],
        [Input(f"btn-goto-{s['id']}", "n_clicks") for s in analyses],
        prevent_initial_call=True,
    )
    def goto_analysis(*args):
        triggered = ctx.triggered_id
        if not triggered:
            return [no_update] * (2 * len(_SECTION_IDS))

        # Find which analysis
        target_aid = None
        for spec in analyses:
            if triggered == f"btn-goto-{spec['id']}":
                target_aid = spec["id"]
                break

        if not target_aid:
            return [no_update] * (2 * len(_SECTION_IDS))

        # Find index in _SECTION_IDS (offset by 1 for overview)
        target_idx = _SECTION_IDS.index(target_aid)

        section_styles = [_SHOW if i == target_idx else _HIDE
                          for i in range(len(_SECTION_IDS))]
        sidebar_classes = ["dvm-sidebar-item active" if i == target_idx else "dvm-sidebar-item"
                           for i in range(len(_SECTION_IDS))]

        return section_styles + sidebar_classes

    # ==============================================================
    # Version Panel: open/close
    # ==============================================================
    @app.callback(
        Output("version-panel", "style"),
        [
            Input("btn-version-control", "n_clicks"),
            Input("btn-close-version-panel", "n_clicks"),
            Input("btn-version-continue", "n_clicks"),
        ],
        State("version-panel", "style"),
        prevent_initial_call=True,
    )
    def toggle_version_panel(open_clicks, close_clicks, apply_clicks, current_style):
        triggered = ctx.triggered_id
        if triggered == "btn-version-control":
            if current_style and current_style.get("display") == "none":
                return {"display": "block"}
            return {"display": "none"}
        return {"display": "none"}

    # ==============================================================
    # Auto-detect version on connection
    # ==============================================================
    @app.callback(
        [
            Output("store-hana-version", "data"),
            Output("header-version-text", "children"),
            Output("dropdown-hana-version", "value"),
        ],
        Input("store-connection-state", "data"),
        State("store-hana-version", "data"),
        prevent_initial_call=True,
    )
    def auto_detect_version_on_connect(conn_state, current_version):
        if not conn_state or not conn_state.get("connected"):
            return no_update, no_update, no_update

        # Only auto-detect if no version is already set
        if current_version and current_version.get("formatted"):
            return no_update, no_update, no_update

        try:
            result = run_query(
                conn_state,
                "SELECT VERSION FROM M_DATABASE",
                sid=conn_state.get("system_id", ""),
                label="AUTO_VERSION_DETECT",
            )
            if not result.success or result.df is None or result.df.empty:
                return no_update, no_update, no_update

            raw_version = str(result.df.iloc[0, 0])
            parsed = parse_hana_version(raw_version)
            formatted = format_version_tuple(parsed)

            version_data = {"raw": raw_version, "parsed": list(parsed), "formatted": formatted}
            header_text = f"HANA {formatted}"
            return version_data, header_text, formatted
        except Exception:
            return no_update, no_update, no_update

    # ==============================================================
    # Manual Version Detection (button in panel)
    # ==============================================================
    @app.callback(
        [
            Output("version-autodetect-info", "children"),
            Output("dropdown-hana-version", "value", allow_duplicate=True),
        ],
        Input("btn-detect-version", "n_clicks"),
        State("store-connection-state", "data"),
        prevent_initial_call=True,
    )
    def detect_version(n_clicks, conn_state):
        if not n_clicks:
            return no_update, no_update

        if not conn_state or not conn_state.get("connected"):
            return (html.Div([html.I(className="bi bi-exclamation-triangle me-2"),
                              html.Span("Not connected. Please connect first.")],
                             className="dvm-warning-card"), no_update)

        result = run_query(conn_state, "SELECT VERSION FROM M_DATABASE",
                           sid=conn_state.get("system_id", ""), label="VERSION_DETECT")

        if not result.success:
            return (html.Div([html.I(className="bi bi-x-circle me-2"),
                              html.Span(f"Detection failed: {result.error}")],
                             className="dvm-error-card"), no_update)

        if result.df is None or result.df.empty:
            return (html.Div([html.I(className="bi bi-info-circle me-2"),
                              html.Span("No version data returned.")],
                             className="dvm-info-card"), no_update)

        raw_version = str(result.df.iloc[0, 0])
        try:
            parsed = parse_hana_version(raw_version)
            formatted = format_version_tuple(parsed)
        except ValueError:
            return (html.Div([html.I(className="bi bi-exclamation-triangle me-2"),
                              html.Span(f"Could not parse '{raw_version}'.")],
                             className="dvm-warning-card"), no_update)

        msg = html.Div([html.I(className="bi bi-check-circle me-2"),
                         html.Span(["Detected: ", html.Strong(formatted,
                                    style={"color": "var(--dvm-primary)"})])],
                        className="dvm-success-card")
        return msg, formatted

    # ==============================================================
    # Show/hide custom version input
    # ==============================================================
    @app.callback(
        Output("custom-version-container", "style"),
        Input("dropdown-hana-version", "value"),
        prevent_initial_call=True,
    )
    def toggle_custom_input(value):
        if value == "__custom__":
            return {"display": "block", "marginBottom": "12px"}
        return {"display": "none", "marginBottom": "12px"}

    # ==============================================================
    # Version Apply (manual override)
    # ==============================================================
    @app.callback(
        [
            Output("store-hana-version", "data", allow_duplicate=True),
            Output("version-validation-msg", "children"),
            Output("header-version-text", "children", allow_duplicate=True),
        ],
        Input("btn-version-continue", "n_clicks"),
        [State("dropdown-hana-version", "value"), State("input-custom-version", "value")],
        prevent_initial_call=True,
    )
    def version_apply(n_clicks, dropdown_val, custom_val):
        if not n_clicks:
            return no_update, no_update, no_update
        if dropdown_val == "__custom__":
            version_str = (custom_val or "").strip()
        else:
            version_str = (dropdown_val or "").strip()
        if not version_str:
            return (no_update, html.Span("Please select or enter a HANA version.",
                    style={"fontSize": "12px", "color": "var(--dvm-error)"}), no_update)
        try:
            parsed = parse_hana_version(version_str)
            formatted = format_version_tuple(parsed)
        except ValueError as e:
            return (no_update, html.Span(f"Invalid version: {e}",
                    style={"fontSize": "12px", "color": "var(--dvm-error)"}), no_update)
        version_data = {"raw": version_str, "parsed": list(parsed), "formatted": formatted}
        return version_data, "", f"HANA {formatted}"

    # ==============================================================
    # Connection badge
    # ==============================================================
    @app.callback(
        [
            Output("header-conn-badge", "children"),
            Output("header-conn-badge", "className"),
            Output("btn-connect", "style"),
            Output("btn-disconnect", "style"),
        ],
        Input("store-connection-state", "data"),
    )
    def update_conn_badge(conn_state):
        if not conn_state or not conn_state.get("connected"):
            return (
                [html.Span("", className="dvm-status-dot disconnected", id="conn-status-dot"),
                 html.Span("Not Connected", id="conn-status-text")],
                "dvm-connection-badge disconnected",
                {"display": "inline-flex"},
                {"display": "none"},
            )
        sid = conn_state.get("system_id", "")
        host = conn_state.get("host", "")
        label = sid or host or "Connected"
        return (
            [html.Span("", className="dvm-status-dot connected", id="conn-status-dot"),
             html.Span(label, id="conn-status-text")],
            "dvm-connection-badge connected",
            {"display": "none"},
            {"display": "inline-flex"},
        )
