"""Layout for DVM Tool: Vertical Sidebar Navigation.

Architecture:
  - Fixed left sidebar (~240px): Overview | A1 | A2 | A3 | A4 | A5 | A6
    Each item has an icon, label, and status dot.
  - Right content panel: shows only the active section (one at a time).
  - Header: brand + top nav (Analyses | Offline) + version + connection.
  - Two intervals: progress (500ms, disabled when idle) and idle (90s).
  - Per-analysis Run + Export buttons in each section.
  - Overview: Run All / Run Selected + Export All / Export Selected + summary cards.
"""

from typing import List

from dash import html, dcc
import dash_bootstrap_components as dbc

from hana_connection_manager.layout import (
    get_connection_stores,
    get_connection_modal,
)
from .registry import get_all_analyses, ANALYSIS_SPECS


# ===================================================================
# PUBLIC
# ===================================================================

def create_layout(version_options: List[str]) -> html.Div:
    """Create the full app layout with vertical sidebar navigation."""
    analyses = get_all_analyses()

    return html.Div(
        [
            # Stores
            *get_connection_stores(),
            dcc.Store(id="store-hana-version", storage_type="session"),
            dcc.Store(id="store-analysis-results", storage_type="memory"),
            dcc.Store(id="store-run-progress", storage_type="memory"),
            dcc.Store(id="store-offline-results", storage_type="memory"),
            # Download components
            dcc.Download(id="download-excel"),
            dcc.Download(id="download-excel-single"),
            # Interval: fast poll while run active (500ms), disabled when idle
            dcc.Interval(id="interval-progress", interval=500, disabled=True),
            # Idle interval: 90s recurring check
            dcc.Interval(id="interval-idle", interval=90_000, disabled=False),
            # Connection modal
            get_connection_modal(),
            # Header
            _build_header(version_options),
            # Version popover panel (hidden by default)
            _build_version_panel(version_options),
            # Main content area: sidebar + content
            html.Div(
                [
                    # Analyses area (sidebar + content panel)
                    _build_analyses_area(analyses),
                    # Offline mode (replaces the whole analyses area when active)
                    _build_offline_screen(analyses),
                ],
                className="dvm-main-content",
            ),
        ],
        className="dvm-app-shell",
    )


# ===================================================================
# HEADER
# ===================================================================

def _build_header(version_options: List[str]) -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.I(className="bi bi-database-gear", style={
                                "fontSize": "20px", "color": "var(--dvm-primary)",
                            }),
                            html.Span("DVM Tool", className="dvm-header-title"),
                        ],
                        className="dvm-header-brand",
                    ),
                    html.Div(
                        [
                            html.Button("Analyses", id="nav-tab-analyses",
                                        className="dvm-nav-tab active", n_clicks=0,
                                        **{"data-i18n": "nav.analyses"}),
                            html.Button("Offline", id="nav-tab-offline",
                                        className="dvm-nav-tab", n_clicks=0,
                                        **{"data-i18n": "nav.offline"}),
                        ],
                        className="dvm-nav-tabs",
                    ),
                ],
                className="dvm-header-left",
            ),
            html.Div(
                [
                    # Theme toggle (light/dark). Icon + behavior handled client-side
                    # by the inline script in app.index_string; persists to localStorage.
                    html.Button(
                        html.I(className="bi bi-moon-stars"),
                        id="btn-theme-toggle", className="dvm-btn-icon",
                        n_clicks=0, title="Switch to dark theme",
                        **{"aria-label": "Switch theme"},
                    ),
                    html.Button(
                        [
                            html.Span("No version", id="header-version-text"),
                            html.I(className="bi bi-chevron-down",
                                   style={"fontSize": "10px", "marginLeft": "4px"}),
                        ],
                        id="btn-version-control", className="dvm-version-control",
                        n_clicks=0, title="Select HANA version",
                    ),
                    html.Span(
                        [
                            html.Span("", id="conn-status-dot",
                                      className="dvm-status-dot disconnected"),
                            html.Span("Not Connected", id="conn-status-text"),
                        ],
                        id="header-conn-badge",
                        className="dvm-connection-badge disconnected",
                    ),
                    html.Button([html.I(className="bi bi-plug"),
                                 html.Span("Connect", style={"marginLeft": "6px"},
                                           **{"data-i18n": "btn.connect"})],
                                id="btn-connect", className="btn btn-primary btn-sm", n_clicks=0),
                    html.Button([html.I(className="bi bi-x-lg")],
                                id="btn-disconnect", className="dvm-btn-icon", n_clicks=0,
                                title="Disconnect", style={"display": "none"}),
                ],
                className="dvm-header-right",
            ),
        ],
        className="dvm-header",
    )


# ===================================================================
# VERSION PANEL
# ===================================================================

def _build_version_panel(version_options: List[str]) -> html.Div:
    dropdown_opts = [{"label": v, "value": v} for v in version_options]
    dropdown_opts.append({"label": "Custom revision...", "value": "__custom__"})

    return html.Div(
        html.Div(
            [
                html.Div(
                    [
                        html.I(className="bi bi-gear-wide-connected",
                               style={"fontSize": "18px", "color": "var(--dvm-primary)"}),
                        html.Span("Select HANA Version", style={
                            "fontWeight": "600", "fontSize": "14px"}),
                        html.Button(html.I(className="bi bi-x-lg"),
                                    id="btn-close-version-panel", className="dvm-btn-icon",
                                    n_clicks=0, style={"marginLeft": "auto"}),
                    ],
                    style={"display": "flex", "alignItems": "center", "gap": "8px",
                           "marginBottom": "12px"},
                ),
                html.P(
                    "Version drives script selection: each analysis uses the "
                    "revision-specific SQL Statement Collection file.",
                    style={"color": "var(--dvm-text-secondary)", "fontSize": "12px",
                           "margin": "0 0 12px"},
                ),
                html.Div(id="version-autodetect-info", style={"marginBottom": "8px"}),
                html.Div(
                    html.Button([html.I(className="bi bi-search me-2"), "Detect from system"],
                                id="btn-detect-version", className="btn btn-outline-secondary btn-sm",
                                n_clicks=0),
                    style={"marginBottom": "12px"},
                ),
                html.Div([
                    html.Label("Target HANA Revision", style={
                        "fontSize": "12px", "fontWeight": "600",
                        "color": "var(--dvm-text-secondary)",
                        "marginBottom": "4px", "display": "block"}),
                    dcc.Dropdown(id="dropdown-hana-version", options=dropdown_opts,
                                 placeholder="Select a HANA revision...",
                                 clearable=False, style={"fontSize": "13px"}),
                ], style={"marginBottom": "12px"}),
                html.Div([
                    html.Label("Custom Revision", style={
                        "fontSize": "12px", "fontWeight": "600",
                        "color": "var(--dvm-text-secondary)",
                        "marginBottom": "4px", "display": "block"}),
                    dbc.Input(id="input-custom-version", placeholder="e.g. 2.00.077",
                              type="text", style={"maxWidth": "200px"}),
                ], id="custom-version-container", style={"display": "none", "marginBottom": "12px"}),
                html.Div(id="version-validation-msg"),
                html.Div(
                    html.Button([html.I(className="bi bi-check-lg me-1"), "Apply"],
                                id="btn-version-continue", className="btn btn-primary btn-sm",
                                n_clicks=0),
                    style={"marginTop": "12px"},
                ),
            ],
            className="dvm-card-static",
            style={"maxWidth": "380px", "padding": "16px 20px"},
        ),
        id="version-panel", className="dvm-version-panel", style={"display": "none"},
    )


# ===================================================================
# ANALYSES AREA: VERTICAL SIDEBAR + RIGHT CONTENT PANEL
# ===================================================================

def _build_analyses_area(analyses) -> html.Div:
    """Build the analyses area: left sidebar + right content panel."""
    return html.Div(
        [
            # LEFT SIDEBAR
            _build_sidebar(analyses),
            # RIGHT CONTENT PANEL
            _build_content_panel(analyses),
        ],
        id="screen-analyses",
        className="dvm-analyses-layout",
        style={"display": "flex"},
    )


def _build_sidebar(analyses) -> html.Div:
    """Build the fixed left sidebar with navigation items."""
    nav_items = []

    # Overview item (default active)
    nav_items.append(
        html.Button(
            [
                html.I(className="bi bi-grid-1x2", style={"fontSize": "16px"}),
                html.Span("Overview", className="dvm-sidebar-label",
                          **{"data-i18n": "sidebar.overview"}),
            ],
            id="sidebar-item-overview",
            className="dvm-sidebar-item active",
            n_clicks=0,
        )
    )

    # Per-analysis items
    for spec in analyses:
        short = spec["id"].split("_")[0].upper()
        icon = spec.get("icon", "bi-table")
        title = spec["title"].split(": ", 1)[-1] if ": " in spec["title"] else spec["title"]

        nav_items.append(
            html.Button(
                [
                    html.I(className=f"bi {icon}", style={"fontSize": "16px"}),
                    html.Div(
                        [
                            html.Span(f"{short}: {title}", className="dvm-sidebar-label",
                                      **{"data-i18n": f"analysis.{spec['id']}.short"}),
                        ],
                        className="dvm-sidebar-text",
                    ),
                    html.Span("", id=f"status-dot-{spec['id']}",
                              className="dvm-status-indicator pending"),
                ],
                id=f"sidebar-item-{spec['id']}",
                className="dvm-sidebar-item",
                n_clicks=0,
            )
        )

    return html.Div(
        html.Nav(nav_items, className="dvm-sidebar-nav"),
        className="dvm-sidebar",
        id="analyses-sidebar",
    )


def _build_content_panel(analyses) -> html.Div:
    """Build the right content panel with all sections (show one at a time)."""
    sections = [_build_overview_section(analyses)]
    for spec in analyses:
        sections.append(_build_analysis_section(spec))

    return html.Div(
        sections,
        className="dvm-content-panel",
        id="analyses-content-panel",
    )


# ===================================================================
# OVERVIEW SECTION
# ===================================================================

def _build_overview_section(analyses) -> html.Div:
    """Overview: Intro + Run All/Selected, Export All/Selected, summary cards."""
    # Checkboxes for selecting analyses
    checklist_options = [
        {"label": f"  {s['id'].split('_')[0].upper()}: {s['title'].split(': ', 1)[-1]}",
         "value": s["id"]}
        for s in analyses
    ]
    all_ids = [s["id"] for s in analyses]

    # Summary cards per analysis
    cards = []
    for spec in analyses:
        short = spec["id"].split("_")[0].upper()
        cards.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.I(className=f"bi {spec.get('icon', 'bi-table')}",
                                   style={"fontSize": "18px", "color": "var(--dvm-primary)"}),
                            html.Div(
                                [
                                    html.Div(f"{short}: {spec['title'].split(': ', 1)[-1]}",
                                             className="dvm-analysis-card-title",
                                             **{"data-i18n": f"analysis.{spec['id']}.short"}),
                                    html.Div(spec.get("description", ""),
                                             className="dvm-analysis-card-desc",
                                             **{"data-i18n": f"analysis.{spec['id']}.desc"}),
                                ],
                            ),
                        ],
                        style={"display": "flex", "gap": "10px", "flex": "1",
                               "alignItems": "flex-start"},
                    ),
                    html.Div(
                        [
                            html.Span("", id=f"overview-status-{spec['id']}",
                                      className="dvm-status-indicator pending"),
                            html.Span("", id=f"overview-summary-{spec['id']}",
                                      style={"fontSize": "12px",
                                             "color": "var(--dvm-text-secondary)"}),
                        ],
                        style={"display": "flex", "gap": "8px", "alignItems": "center"},
                    ),
                    html.Button(
                        [html.I(className="bi bi-arrow-right")],
                        id=f"btn-goto-{spec['id']}",
                        className="btn btn-outline-secondary btn-sm",
                        n_clicks=0, title="View details",
                    ),
                ],
                className="dvm-analysis-card",
                id=f"card-{spec['id']}",
            )
        )

    return html.Div(
        html.Div(
            [
                # Language selector (landing) — EN default / ES / PT
                html.Div(
                    [
                        html.Span("Language", className="dvm-lang-label",
                                  **{"data-i18n": "lang.label"}),
                        html.Div(
                            [
                                html.Button("EN", className="dvm-tab-pill active",
                                            n_clicks=0, **{"data-lang": "en"}),
                                html.Button("ES", className="dvm-tab-pill",
                                            n_clicks=0, **{"data-lang": "es"}),
                                html.Button("PT", className="dvm-tab-pill",
                                            n_clicks=0, **{"data-lang": "pt"}),
                            ],
                            className="dvm-tab-pills dvm-lang-pills",
                        ),
                    ],
                    className="dvm-lang-switch",
                ),

                # Title area
                html.Div([
                    html.I(className="bi bi-bar-chart-line",
                           style={"fontSize": "28px", "color": "var(--dvm-primary)"}),
                    html.Div([
                        html.H2("DVM Analyses", className="dvm-page-title",
                                **{"data-i18n": "overview.title"}),
                        html.P("Run analyses individually or as a batch. "
                               "Queries execute serially via a single DBACOCKPIT session.",
                               style={"color": "var(--dvm-text-secondary)",
                                      "fontSize": "14px", "margin": "6px 0 0"},
                               **{"data-i18n": "overview.subtitle"}),
                    ]),
                ], style={"display": "flex", "gap": "14px", "alignItems": "flex-start",
                          "marginBottom": "16px"}),

                # Intro text block
                html.Div([
                    html.P([
                        "This tool automates the ",
                        html.Strong("SAP HANA Database Volume Management (DVM)"),
                        " checks described in ",
                        html.A("SAP Note 1969700", href="https://me.sap.com/notes/1969700",
                               target="_blank", style={"color": "var(--dvm-primary)"}),
                        ". It connects to HANA via SAP GUI (DBACOCKPIT) and runs "
                        "revision-specific SQL from the SQL Statement Collection "
                        "to identify space consumers, growth trends, and memory distribution."
                    ], style={"fontSize": "13px", "color": "var(--dvm-text-secondary)",
                              "margin": "0 0 10px", "lineHeight": "1.5"}),
                    html.Div([
                        html.Div([
                            html.Strong("A1", style={"color": "var(--dvm-primary)", "marginRight": "4px"}),
                            html.Span("Top tables by disk and memory size", **{"data-i18n": "info.a1"}),
                        ], style={"fontSize": "12px", "marginBottom": "3px"}),
                        html.Div([
                            html.Strong("A2", style={"color": "var(--dvm-primary)", "marginRight": "4px"}),
                            html.Span("Memory & disk resource trend (~1 year, monthly)", **{"data-i18n": "info.a2"}),
                        ], style={"fontSize": "12px", "marginBottom": "3px"}),
                        html.Div([
                            html.Strong("A3", style={"color": "var(--dvm-primary)", "marginRight": "4px"}),
                            html.Span("Memory distribution by subarea (pie chart)", **{"data-i18n": "info.a3"}),
                        ], style={"fontSize": "12px", "marginBottom": "3px"}),
                        html.Div([
                            html.Strong("A4", style={"color": "var(--dvm-primary)", "marginRight": "4px"}),
                            html.Span("Top growing tables over last 30 days", **{"data-i18n": "info.a4"}),
                        ], style={"fontSize": "12px", "marginBottom": "3px"}),
                        html.Div([
                            html.Strong("A5", style={"color": "var(--dvm-primary)", "marginRight": "4px"}),
                            html.Span("Partitioned column-store tables", **{"data-i18n": "info.a5"}),
                        ], style={"fontSize": "12px", "marginBottom": "3px"}),
                        # A6 (NSE) temporarily hidden — analysis is a work in progress.
                    ], style={"paddingLeft": "8px", "borderLeft": "3px solid var(--dvm-primary)",
                              "marginBottom": "4px"}),
                ], className="dvm-info-card", style={"marginBottom": "20px", "padding": "14px 16px"}),

                # How-to (step-by-step) + slow-run disclaimer
                html.Div(
                    [
                        html.Div(
                            [
                                html.I(className="bi bi-signpost-split",
                                        style={"fontSize": "18px",
                                               "color": "var(--dvm-primary)"}),
                                html.H3("How to use this tool",
                                        className="dvm-howto-title",
                                        **{"data-i18n": "howto.title"}),
                            ],
                            className="dvm-howto-head",
                        ),
                        html.Ol(
                            [
                                html.Li("Pick the HANA revision (top-right) so each "
                                        "analysis uses the matching SQL.",
                                        **{"data-i18n": "howto.step1"}),
                                html.Li("Connect to HANA via SAP GUI (DBACOCKPIT) with "
                                        "the Connect button.",
                                        **{"data-i18n": "howto.step2"}),
                                html.Li("Select the analyses you want and press Run All "
                                        "or Run Selected.",
                                        **{"data-i18n": "howto.step3"}),
                                html.Li("Review each result, then export or copy the "
                                        "tables you need.",
                                        **{"data-i18n": "howto.step4"}),
                            ],
                            className="dvm-howto-steps",
                        ),
                        html.Div(
                            [
                                html.I(className="bi bi-hourglass-split"),
                                html.Span("Some analyses run heavy SQL and can take a "
                                          "while. If a query seems slow, just give it "
                                          "time — don't refresh. Results appear as each "
                                          "analysis finishes.",
                                          **{"data-i18n": "howto.disclaimer"}),
                            ],
                            className="dvm-howto-disclaimer",
                        ),
                    ],
                    className="dvm-howto-card",
                ),

                # Still-running message (hidden by default, shown during execution)
                html.Div(
                    [html.I(className="bi bi-hourglass-split me-2",
                            style={"color": "var(--dvm-primary)"}),
                     html.Span("Analyses are still running. Please wait for completion.",
                               style={"fontSize": "13px"},
                               **{"data-i18n": "overview.stillRunning"})],
                    id="overview-still-running",
                    className="dvm-warning-card",
                    style={"display": "none", "marginBottom": "16px"},
                ),

                # Selection area
                html.Div(
                    [
                        html.Div([
                            html.Label("Select analyses to run or export:",
                                       style={"fontSize": "12px", "fontWeight": "600",
                                              "color": "var(--dvm-text-secondary)",
                                              "marginBottom": "6px", "display": "block"},
                                       **{"data-i18n": "overview.selectLabel"}),
                            dcc.Checklist(
                                id="checklist-analyses",
                                options=checklist_options,
                                value=all_ids,
                                className="dvm-checklist",
                                inputClassName="dvm-check-input",
                                labelClassName="dvm-check-label",
                            ),
                        ], style={"marginBottom": "16px"}),
                    ],
                    className="dvm-selection-area",
                ),

                # Action bar
                html.Div(
                    [
                        html.Button([html.I(className="bi bi-play-fill me-2"),
                                     html.Span("Run All", **{"data-i18n": "btn.runAll"})],
                                    id="btn-run-all-analyses",
                                    className="btn btn-primary", n_clicks=0),
                        html.Button([html.I(className="bi bi-play me-2"),
                                     html.Span("Run Selected", **{"data-i18n": "btn.runSelected"})],
                                    id="btn-run-selected",
                                    className="btn btn-outline-primary", n_clicks=0),
                        html.Div(style={"flex": "1"}),
                        html.Button([html.I(className="bi bi-file-earmark-excel me-2"),
                                     html.Span("Export All", **{"data-i18n": "btn.exportAll"})],
                                    id="btn-export-excel",
                                    className="btn btn-outline-primary btn-sm",
                                    n_clicks=0, style={"display": "none"}),
                        html.Button([html.I(className="bi bi-file-earmark-excel me-2"),
                                     html.Span("Export Selected", **{"data-i18n": "btn.exportSelected"})],
                                    id="btn-export-selected",
                                    className="btn btn-outline-secondary btn-sm",
                                    n_clicks=0, style={"display": "none"}),
                    ],
                    style={"display": "flex", "gap": "8px", "marginBottom": "20px",
                           "alignItems": "center", "flexWrap": "wrap"},
                ),

                # Progress
                html.Div(
                    [
                        html.Div([
                            html.Span("", id="progress-text",
                                      style={"fontSize": "12px", "fontWeight": "500",
                                             "color": "var(--dvm-text-secondary)"}),
                            html.Span("", id="progress-pct",
                                      style={"fontSize": "12px", "fontWeight": "600",
                                             "color": "var(--dvm-primary)"}),
                        ], className="dvm-progress-label"),
                        html.Div(
                            html.Div(id="progress-bar-fill", className="dvm-progress-fill",
                                     style={"width": "0%"}),
                            className="dvm-progress-track",
                        ),
                    ],
                    id="progress-container", className="dvm-progress-container",
                    style={"display": "none"},
                ),

                # Status messages
                html.Div(id="analyses-run-status", style={"marginTop": "12px"}),

                # Summary cards
                html.Div(cards, id="analysis-cards-container",
                         style={"marginTop": "20px"}),
            ],
            className="dvm-card-static",
        ),
        id="section-overview",
        style={"display": "block"},
    )


# ===================================================================
# PER-ANALYSIS SECTION
# ===================================================================

def _build_analysis_section(spec) -> html.Div:
    """Build a single analysis section with Run + Export + results area."""
    aid = spec["id"]
    short = aid.split("_")[0].upper()
    title = spec["title"]

    return html.Div(
        html.Div(
            [
                # Section header with title + Run + Export
                html.Div(
                    [
                        html.Div([
                            html.I(className=f"bi {spec.get('icon', 'bi-table')}",
                                   style={"fontSize": "22px", "color": "var(--dvm-primary)"}),
                            html.Div([
                                html.H2(title, className="dvm-page-title",
                                        style={"margin": "0"},
                                        **{"data-i18n": f"analysis.{aid}.short"}),
                                html.P(spec.get("description", ""),
                                       style={"color": "var(--dvm-text-secondary)",
                                              "fontSize": "13px", "margin": "4px 0 0"},
                                       **{"data-i18n": f"analysis.{aid}.desc"}),
                            ]),
                        ], style={"display": "flex", "gap": "12px",
                                  "alignItems": "flex-start", "flex": "1"}),
                        html.Div([
                            html.Button(
                                [html.I(className="bi bi-play-fill me-1"), "Run"],
                                id=f"btn-run-{aid}",
                                className="btn btn-primary btn-sm", n_clicks=0,
                            ),
                            html.Button(
                                [html.I(className="bi bi-file-earmark-excel me-1"), "Export"],
                                id=f"btn-export-{aid}",
                                className="btn btn-outline-primary btn-sm", n_clicks=0,
                            ),
                        ], style={"display": "flex", "gap": "6px"}),
                    ],
                    style={"display": "flex", "justifyContent": "space-between",
                           "alignItems": "flex-start", "marginBottom": "20px",
                           "flexWrap": "wrap", "gap": "12px"},
                ),

                # Results content area
                html.Div(
                    html.Div(
                        [
                            html.I(className="bi bi-inbox",
                                   style={"fontSize": "24px",
                                          "color": "var(--dvm-border)"}),
                            html.P("No results yet. Run this analysis or use Run All.",
                                   style={"fontSize": "13px",
                                          "color": "var(--dvm-text-secondary)",
                                          "margin": "6px 0 0"}),
                        ],
                        className="dvm-empty-state",
                    ),
                    id=f"tab-content-{aid}",
                ),
            ],
            className="dvm-card-static",
        ),
        id=f"section-{aid}",
        style={"display": "none"},
    )


# ===================================================================
# OFFLINE MODE
# ===================================================================

def _build_offline_screen(analyses) -> html.Div:
    query_options = []
    for spec in analyses:
        for q in spec["queries"]:
            short = spec["id"].split("_")[0].upper()
            label = f"{short}: {q['label']}"
            value = f"{spec['id']}::{q['label']}"
            query_options.append({"label": label, "value": value})

    return html.Div(
        html.Div(
            [
                html.Div([
                    html.I(className="bi bi-cloud-slash",
                           style={"fontSize": "28px", "color": "var(--dvm-primary)"}),
                    html.Div([
                        html.H2("Offline Mode", className="dvm-page-title"),
                        html.P("Use when you cannot connect the app directly to HANA. "
                               "Copy the SQL, run it elsewhere, upload results.",
                               style={"color": "var(--dvm-text-secondary)", "fontSize": "14px",
                                      "margin": "6px 0 0"}),
                    ]),
                ], style={"display": "flex", "gap": "14px", "alignItems": "flex-start",
                          "marginBottom": "24px"}),
                # How-to
                html.Div([
                    html.I(className="bi bi-lightbulb", style={"flexShrink": "0", "marginTop": "2px"}),
                    html.Div([
                        html.Strong("How to use offline mode:", style={"display": "block",
                                    "marginBottom": "4px"}),
                        html.Ol([
                            html.Li("Select the SQL for each analysis below and copy it."),
                            html.Li("Run it in DBACOCKPIT SQL Editor, hdbsql, or HANA Studio."),
                            html.Li("Export the result grid as CSV or XLSX."),
                            html.Li("Upload the result files below to render charts and tables."),
                        ], style={"paddingLeft": "18px", "margin": "0", "fontSize": "13px"}),
                    ]),
                ], className="dvm-info-card", style={"marginBottom": "24px"}),
                # SQL display
                html.Div([
                    html.H3("1. Get SQL", className="dvm-section-title", style={"marginBottom": "12px"}),
                    html.Div([
                        html.Label("Select analysis query:", style={
                            "fontSize": "12px", "fontWeight": "600",
                            "color": "var(--dvm-text-secondary)",
                            "marginBottom": "4px", "display": "block"}),
                        dcc.Dropdown(id="offline-query-selector", options=query_options,
                                     value=query_options[0]["value"] if query_options else None,
                                     clearable=False, style={"fontSize": "13px", "maxWidth": "400px"}),
                    ], style={"marginBottom": "12px"}),
                    html.Div(id="offline-sql-display"),
                    html.Button([html.I(className="bi bi-clipboard me-2"), "Copy SQL"],
                                id="btn-offline-copy", className="btn btn-outline-primary btn-sm",
                                n_clicks=0, style={"marginTop": "8px"}),
                    dcc.Clipboard(id="clipboard-offline-sql", style={"display": "none"}),
                ], style={"marginBottom": "32px"}),
                # Upload
                html.Div([
                    html.H3("2. Upload Results", className="dvm-section-title",
                            style={"marginBottom": "12px"}),
                    html.Div([
                        html.Label("Upload for analysis:", style={
                            "fontSize": "12px", "fontWeight": "600",
                            "color": "var(--dvm-text-secondary)",
                            "marginBottom": "4px", "display": "block"}),
                        dcc.Dropdown(id="offline-upload-target",
                                     options=[{"label": s["title"], "value": s["id"]} for s in analyses],
                                     value=analyses[0]["id"] if analyses else None,
                                     clearable=False, style={"fontSize": "13px", "maxWidth": "300px"}),
                    ], style={"marginBottom": "12px"}),
                    dcc.Upload(id="offline-upload",
                               children=html.Div([
                                   html.I(className="bi bi-cloud-arrow-up"),
                                   html.P("Drag & drop CSV or XLSX file, or click to browse"),
                               ], className="dvm-upload-zone"),
                               multiple=True, accept=".csv,.xlsx,.xls"),
                    html.Div(id="offline-upload-status", style={"marginTop": "12px"}),
                ], style={"marginBottom": "32px"}),
                # Results
                html.Div([
                    html.H3("3. View Results", className="dvm-section-title",
                            style={"marginBottom": "12px"}),
                    html.Button([html.I(className="bi bi-file-earmark-excel me-2"),
                                 "Export to DVM_tool.xlsx"],
                                id="btn-offline-export", className="btn btn-outline-primary btn-sm",
                                n_clicks=0, style={"marginBottom": "12px"}),
                    html.Div(id="offline-results-display"),
                ]),
            ],
            className="dvm-card-static",
        ),
        id="screen-offline", style={"display": "none"},
    )
