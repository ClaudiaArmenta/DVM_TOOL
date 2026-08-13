"""DVM smoke test callbacks.

Runs the Connection & Query Check sequence:
  1. Version probe: SELECT VERSION FROM M_DATABASE
  2. Trivial probe: SELECT 1 AS OK FROM DUMMY
  3. Mini-check probe: Load a real script file chosen by version

All queries run SEQUENTIALLY via the execution layer (DBACOCKPIT lock).
"""

from pathlib import Path

from dash import Input, Output, State, html, no_update

from hana_connection_manager.dvm.execution import run_query, run_query_from_file
from hana_connection_manager.dvm.version_select import (
    parse_hana_version,
    format_version_tuple,
    select_variant,
    get_queries_dir,
)
from hana_connection_manager.dvm.components import (
    results_table,
    status_badge,
    elapsed_badge,
    row_col_badge,
    collapsible_sql,
    error_display,
    smoke_test_step_card,
)


# Scripts to probe (in order of preference for step 3)
_PROBE_SCRIPTS = [
    "HANA_Configuration_Overview",
    "HANA_Configuration_MiniChecks",
]

# Fallback SQL if script probes fail
_FALLBACK_SQL = (
    "SELECT TOP 50 TABLE_NAME, LOAD_UNIT FROM M_CS_TABLES WHERE LOAD_UNIT = 'PAGE'"
)


def register(app):
    """Register smoke test callbacks."""

    @app.callback(
        [
            Output("smoke-test-results", "children"),
            Output("smoke-test-loading-target", "children"),
            Output("btn-run-smoke-test", "style"),
            Output("btn-rerun-smoke-test", "style"),
        ],
        [
            Input("btn-run-smoke-test", "n_clicks"),
            Input("btn-rerun-smoke-test", "n_clicks"),
        ],
        [
            State("store-connection-state", "data"),
            State("store-hana-version", "data"),
        ],
        prevent_initial_call=True,
    )
    def run_smoke_test(run_clicks, rerun_clicks, conn_state, version_data):
        if not run_clicks and not rerun_clicks:
            return no_update, no_update, no_update, no_update

        # Validate connection
        if not conn_state or not conn_state.get("connected"):
            return (
                html.Div(
                    [
                        html.I(
                            className="bi bi-exclamation-triangle me-2",
                            style={"color": "#E76500"},
                        ),
                        html.Span(
                            "Not connected. Please connect to SAP HANA first.",
                            style={"fontSize": "13px", "color": "#E76500"},
                        ),
                    ],
                    style={
                        "padding": "14px",
                        "background": "#FFF3CD",
                        "borderRadius": "8px",
                        "borderLeft": "4px solid #E76500",
                    },
                ),
                "",
                {"display": "inline-block"},
                {"display": "none"},
            )

        # Get version tuple
        if version_data and version_data.get("parsed"):
            version_tuple = tuple(version_data["parsed"])
        else:
            version_tuple = (2, 0, 80)

        sid = conn_state.get("system_id", "")
        steps = []

        # ======== Step 1: Version Probe ========
        version_sql = "SELECT VERSION FROM M_DATABASE"
        step1_result = run_query(
            conn_state, version_sql, sid=sid, label="VERSION_PROBE"
        )

        step1_content = [
            html.Div(
                [
                    html.Span(
                        "Step 1: ",
                        style={"fontWeight": "700", "fontSize": "13px"},
                    ),
                    html.Span(
                        "Version Probe",
                        style={"fontWeight": "500", "fontSize": "13px"},
                    ),
                    html.Span(
                        " \u2014 SELECT VERSION FROM M_DATABASE",
                        style={
                            "fontSize": "12px",
                            "color": "#556B82",
                            "marginLeft": "8px",
                        },
                    ),
                ],
                style={"marginBottom": "10px"},
            ),
            html.Div(
                [
                    status_badge(step1_result.success),
                    elapsed_badge(step1_result.elapsed_ms)
                    if step1_result.success
                    else "",
                    row_col_badge(step1_result.row_count, step1_result.col_count)
                    if step1_result.success
                    else "",
                ],
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "marginBottom": "8px",
                },
            ),
        ]

        if (
            step1_result.success
            and step1_result.df is not None
            and not step1_result.df.empty
        ):
            raw_version = str(step1_result.df.iloc[0, 0])
            try:
                parsed = parse_hana_version(raw_version)
                step1_content.append(
                    html.Div(
                        [
                            html.Span(
                                f"Raw: {raw_version}",
                                style={"fontSize": "12px", "marginRight": "12px"},
                            ),
                            html.Span(
                                f"Parsed: ({parsed[0]}, {parsed[1]}, {parsed[2]})",
                                style={
                                    "fontSize": "12px",
                                    "color": "#0070F2",
                                    "fontWeight": "600",
                                },
                            ),
                        ],
                        style={"marginBottom": "8px"},
                    )
                )
            except ValueError as e:
                step1_content.append(
                    html.Div(
                        f"Raw: {raw_version} (parse error: {e})",
                        style={"fontSize": "12px", "color": "#E76500"},
                    )
                )

        if not step1_result.success:
            step1_content.append(
                error_display(step1_result.error, step1_result.exception_text)
            )

        step1_content.append(collapsible_sql(version_sql, "step1"))
        steps.append(smoke_test_step_card(step1_content))

        # ======== Step 2: Trivial Probe ========
        trivial_sql = "SELECT 1 AS OK FROM DUMMY"
        step2_result = run_query(
            conn_state, trivial_sql, sid=sid, label="TRIVIAL_PROBE"
        )

        step2_content = [
            html.Div(
                [
                    html.Span(
                        "Step 2: ",
                        style={"fontWeight": "700", "fontSize": "13px"},
                    ),
                    html.Span(
                        "Trivial Probe",
                        style={"fontWeight": "500", "fontSize": "13px"},
                    ),
                    html.Span(
                        " \u2014 SELECT 1 AS OK FROM DUMMY",
                        style={
                            "fontSize": "12px",
                            "color": "#556B82",
                            "marginLeft": "8px",
                        },
                    ),
                ],
                style={"marginBottom": "10px"},
            ),
            html.Div(
                [
                    status_badge(step2_result.success),
                    elapsed_badge(step2_result.elapsed_ms)
                    if step2_result.success
                    else "",
                    row_col_badge(step2_result.row_count, step2_result.col_count)
                    if step2_result.success
                    else "",
                ],
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "marginBottom": "8px",
                },
            ),
        ]

        if step2_result.success and step2_result.df is not None:
            step2_content.append(results_table(step2_result.df))

        if not step2_result.success:
            step2_content.append(
                error_display(step2_result.error, step2_result.exception_text)
            )

        step2_content.append(collapsible_sql(trivial_sql, "step2"))
        steps.append(smoke_test_step_card(step2_content))

        # ======== Step 3: Mini-Check Probe ========
        queries_dir = get_queries_dir()

        selected_file = None
        for base_name in _PROBE_SCRIPTS:
            variant = select_variant(queries_dir, base_name, version_tuple)
            if variant:
                selected_file = variant
                break

        step3_content = [
            html.Div(
                [
                    html.Span(
                        "Step 3: ",
                        style={"fontWeight": "700", "fontSize": "13px"},
                    ),
                    html.Span(
                        "Mini-Check Probe",
                        style={"fontWeight": "500", "fontSize": "13px"},
                    ),
                    html.Span(
                        " \u2014 Real script file for chosen version",
                        style={
                            "fontSize": "12px",
                            "color": "#556B82",
                            "marginLeft": "8px",
                        },
                    ),
                ],
                style={"marginBottom": "10px"},
            ),
        ]

        if selected_file:
            step3_content.append(
                html.Div(
                    [
                        html.Span(
                            "Selected: ",
                            style={"fontSize": "12px", "color": "#556B82"},
                        ),
                        html.Code(
                            selected_file,
                            style={
                                "fontSize": "11px",
                                "padding": "2px 6px",
                                "background": "#F5F6F7",
                                "borderRadius": "4px",
                            },
                        ),
                        html.Span(
                            f" (for version {format_version_tuple(version_tuple)})",
                            style={
                                "fontSize": "11px",
                                "color": "#556B82",
                                "marginLeft": "8px",
                            },
                        ),
                    ],
                    style={"marginBottom": "10px"},
                )
            )

            file_path = str(Path(queries_dir) / selected_file)
            step3_result = run_query_from_file(
                conn_state,
                file_path,
                sid=sid,
                label="MINICHECK_PROBE",
                sql_exec_wait=15.0,
            )

            step3_content.append(
                html.Div(
                    [
                        status_badge(step3_result.success),
                        elapsed_badge(step3_result.elapsed_ms)
                        if step3_result.success
                        else "",
                        row_col_badge(
                            step3_result.row_count, step3_result.col_count
                        )
                        if step3_result.success
                        else "",
                    ],
                    style={
                        "display": "flex",
                        "alignItems": "center",
                        "marginBottom": "8px",
                    },
                )
            )

            if step3_result.success and step3_result.df is not None:
                step3_content.append(results_table(step3_result.df))

            if not step3_result.success:
                step3_content.append(
                    error_display(step3_result.error, step3_result.exception_text)
                )
                # Fallback
                step3_content.append(
                    html.Div(
                        [
                            html.I(
                                className="bi bi-arrow-return-right me-2",
                                style={"color": "#E76500"},
                            ),
                            html.Span(
                                "Trying fallback query...",
                                style={
                                    "fontSize": "12px",
                                    "color": "#E76500",
                                    "fontWeight": "500",
                                },
                            ),
                        ],
                        style={"marginTop": "8px", "marginBottom": "8px"},
                    )
                )

                fallback_result = run_query(
                    conn_state, _FALLBACK_SQL, sid=sid, label="FALLBACK_PROBE"
                )
                step3_content.append(
                    html.Div(
                        [
                            status_badge(fallback_result.success, "Fallback"),
                            elapsed_badge(fallback_result.elapsed_ms)
                            if fallback_result.success
                            else "",
                            row_col_badge(
                                fallback_result.row_count, fallback_result.col_count
                            )
                            if fallback_result.success
                            else "",
                        ],
                        style={
                            "display": "flex",
                            "alignItems": "center",
                            "marginBottom": "8px",
                        },
                    )
                )
                if fallback_result.success and fallback_result.df is not None:
                    step3_content.append(results_table(fallback_result.df))
                if not fallback_result.success:
                    step3_content.append(
                        error_display(
                            fallback_result.error, fallback_result.exception_text
                        )
                    )
                step3_content.append(collapsible_sql(_FALLBACK_SQL, "step3-fb"))

            step3_content.append(collapsible_sql(step3_result.sql, "step3"))

        else:
            # No matching script
            step3_content.append(
                html.Div(
                    [
                        html.I(
                            className="bi bi-info-circle me-2",
                            style={"color": "#E76500"},
                        ),
                        html.Span(
                            f"No matching script for version "
                            f"{format_version_tuple(version_tuple)}. Trying fallback.",
                            style={"fontSize": "12px"},
                        ),
                    ],
                    style={
                        "padding": "10px",
                        "background": "#FFF3CD",
                        "borderRadius": "6px",
                        "marginBottom": "10px",
                    },
                )
            )
            fallback_result = run_query(
                conn_state, _FALLBACK_SQL, sid=sid, label="FALLBACK_PROBE"
            )
            step3_content.append(
                html.Div(
                    [
                        status_badge(fallback_result.success, "Fallback"),
                        elapsed_badge(fallback_result.elapsed_ms)
                        if fallback_result.success
                        else "",
                        row_col_badge(
                            fallback_result.row_count, fallback_result.col_count
                        )
                        if fallback_result.success
                        else "",
                    ],
                    style={
                        "display": "flex",
                        "alignItems": "center",
                        "marginBottom": "8px",
                    },
                )
            )
            if fallback_result.success and fallback_result.df is not None:
                step3_content.append(results_table(fallback_result.df))
            if not fallback_result.success:
                step3_content.append(
                    error_display(
                        fallback_result.error, fallback_result.exception_text
                    )
                )
            step3_content.append(collapsible_sql(_FALLBACK_SQL, "step3-nofile"))

        steps.append(smoke_test_step_card(step3_content))

        # ======== Summary ========
        all_passed = step1_result.success and step2_result.success
        summary_icon = (
            "bi-check-circle-fill" if all_passed else "bi-exclamation-triangle-fill"
        )
        summary_color = "#107E3E" if all_passed else "#E76500"
        summary_text = (
            "All checks passed."
            if all_passed
            else "Some checks failed. Review the results above."
        )

        steps.append(
            html.Div(
                [
                    html.I(
                        className=f"bi {summary_icon} me-2",
                        style={"color": summary_color, "fontSize": "16px"},
                    ),
                    html.Span(
                        summary_text,
                        style={
                            "fontSize": "14px",
                            "fontWeight": "600",
                            "color": summary_color,
                        },
                    ),
                ],
                style={
                    "padding": "14px",
                    "background": "#E8F5E9" if all_passed else "#FFF3CD",
                    "borderRadius": "8px",
                    "marginTop": "16px",
                },
            )
        )

        return (
            html.Div(steps),
            "",
            {"display": "none"},
            {"display": "inline-block", "marginLeft": "0px"},
        )
