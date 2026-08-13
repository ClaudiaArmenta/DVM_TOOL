"""Connection callbacks: handle connection modal interactions.

Handles:
  - Connection type switching (HANA Native vs SAP GUI)
  - Port auto-fill from instance number
  - SAP GUI session detection
  - Test connection (with visible feedback for both HANA Native and SAP GUI)
  - Establish connection
  - Disconnect
  - SAP GUI session "Use" action
  - Manual attach (findById bypass)

Note: The header connection badge is updated reactively by dvm_navigation
from store-connection-state. Connection callbacks only write to:
  - store-connection-state
  - conn-result (modal feedback)
  - connection-modal.is_open
"""

from dash import Input, Output, State, html, no_update, ctx, ALL
import dash_bootstrap_components as dbc


def register(app):
    """Register connection-related callbacks with a Dash app."""

    # Toggle connection modal
    @app.callback(
        Output("connection-modal", "is_open"),
        [Input("btn-connect", "n_clicks")],
        [State("connection-modal", "is_open")],
        prevent_initial_call=True,
    )
    def toggle_connection_modal(n_clicks, is_open):
        if n_clicks:
            return not is_open
        return is_open

    # Show/hide connection panels based on type selection
    @app.callback(
        [
            Output("conn-panel-sap-gui", "style"),
            Output("conn-panel-hana-native", "style"),
        ],
        Input("conn-type-selector", "value"),
    )
    def switch_connection_panel(conn_type):
        if conn_type == "sap_gui":
            return {"display": "block"}, {"display": "none"}
        else:
            return {"display": "none"}, {"display": "block"}

    # Auto-fill port from instance number
    @app.callback(
        Output("conn-port", "value"),
        Input("conn-instance", "value"),
        State("conn-port", "value"),
        prevent_initial_call=True,
    )
    def update_port_from_instance(instance, current_port):
        if instance and instance.isdigit() and len(instance) <= 2:
            return f"3{instance.zfill(2)}15"
        return current_port

    # Detect SAP GUI sessions
    @app.callback(
        [
            Output("gui-sessions-list", "children"),
            Output("store-gui-sessions", "data"),
            Output("manual-attach-container", "style"),
        ],
        Input("btn-detect-gui", "n_clicks"),
        prevent_initial_call=True,
    )
    def detect_gui_sessions(n_clicks):
        if not n_clicks:
            return no_update, no_update, no_update

        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass

        from ..sap_gui_connector import SAPGUIConnector

        connector = SAPGUIConnector()

        if not connector.is_available():
            return (
                html.Div(
                    [
                        html.I(className="bi bi-exclamation-triangle me-2",
                               style={"color": "#E76500"}),
                        html.Span("SAP GUI Scripting is not available.",
                                  style={"fontWeight": "500"}),
                        html.P(
                            "Requirements: Windows OS, SAP GUI for Windows, pywin32.",
                            style={"fontSize": "12px", "color": "#666", "margin": "8px 0 0"},
                        ),
                    ],
                    style={"padding": "14px", "borderRadius": "8px",
                           "background": "#FFF3CD",
                           "borderLeft": "4px solid #E76500", "marginTop": "12px"},
                ),
                [],
                {"display": "none"},
            )

        try:
            sessions = connector.detect_sessions()
        except Exception as e:
            return (
                html.Div(
                    [
                        html.I(className="bi bi-x-circle me-2",
                               style={"color": "#BB0000"}),
                        html.Span(f"Detection failed: {str(e)}",
                                  style={"fontSize": "13px"}),
                    ],
                    style={"padding": "12px", "background": "#FFEBEE",
                           "borderRadius": "8px",
                           "borderLeft": "4px solid #BB0000", "marginTop": "12px"},
                ),
                [],
                {"display": "none"},
            )

        if not sessions:
            return (
                html.Div(
                    [
                        html.I(className="bi bi-info-circle me-2",
                               style={"color": "#0070F2"}),
                        html.Span("No active SAP GUI sessions found.",
                                  style={"fontSize": "13px"}),
                        html.P(
                            "Open SAP GUI and log into a system first, then click Detect Sessions.",
                            style={"fontSize": "12px", "color": "#666", "margin": "6px 0 0"},
                        ),
                    ],
                    style={"padding": "12px", "background": "#D1EFFF",
                           "borderRadius": "8px",
                           "borderLeft": "4px solid #0070F2", "marginTop": "12px"},
                ),
                [],
                {"display": "block"},
            )

        # Store session info
        sessions_data = [s.to_dict() for s in sessions]

        # Render session cards
        session_cards = []
        for sess in sessions:
            session_cards.append(
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div(
                                    [
                                        html.I(className="bi bi-display me-2",
                                               style={"color": "#0070F2"}),
                                        html.Span(f"{sess.system_id}",
                                                  style={"fontWeight": "500",
                                                         "fontSize": "14px"}),
                                        html.Span(f" / Client {sess.client}",
                                                  style={"color": "#666",
                                                         "fontSize": "13px"}),
                                    ],
                                    style={"display": "flex", "alignItems": "center"},
                                ),
                                html.Div(
                                    [
                                        html.Span(f"User: {sess.user}",
                                                  style={"marginRight": "16px"}),
                                        html.Span(f"Server: {sess.application_server}",
                                                  style={"marginRight": "16px"}),
                                        html.Span(f"TCode: {sess.transaction}"),
                                    ],
                                    style={"display": "flex", "marginTop": "6px",
                                           "fontSize": "12px", "color": "#666"},
                                ),
                            ],
                            style={"flex": "1"},
                        ),
                        html.Button(
                            [html.I(className="bi bi-link-45deg me-1"), "Use"],
                            id={"type": "btn-use-session", "index": sess.session_id},
                            className="btn btn-sm btn-primary",
                            n_clicks=0,
                        ),
                    ],
                    style={
                        "display": "flex", "alignItems": "center",
                        "padding": "14px", "border": "1px solid #E5E5E5",
                        "borderRadius": "8px", "marginBottom": "8px",
                        "background": "white",
                    },
                )
            )

        return (
            html.Div(
                [
                    html.Div(
                        [
                            html.I(className="bi bi-check-circle me-2",
                                   style={"color": "#107E3E"}),
                            html.Span(f"Found {len(sessions)} active session(s)",
                                      style={"fontWeight": "500"}),
                        ],
                        style={"marginBottom": "12px", "fontSize": "14px"},
                    ),
                    html.Div(session_cards),
                ],
                style={"marginTop": "16px"},
            ),
            sessions_data,
            {"display": "none"},
        )

    # ──────────────────────────────────────────────────────────────
    # Test / Establish Connection
    # ──────────────────────────────────────────────────────────────
    @app.callback(
        [
            Output("conn-result", "children"),
            Output("store-connection-state", "data"),
            Output("connection-modal", "is_open", allow_duplicate=True),
        ],
        [
            Input("btn-test-connection", "n_clicks"),
            Input("btn-establish-connection", "n_clicks"),
        ],
        [
            State("conn-type-selector", "value"),
            State("conn-host", "value"),
            State("conn-port", "value"),
            State("conn-user", "value"),
            State("conn-password", "value"),
            State("conn-encrypt", "value"),
            State("conn-validate-cert", "value"),
            State("conn-tenant", "value"),
            State("store-connection-state", "data"),
            State("store-gui-sessions", "data"),
        ],
        prevent_initial_call=True,
    )
    def handle_connection(test_clicks, connect_clicks, conn_type,
                          host, port, user, password, encrypt, validate_cert,
                          tenant, current_state, gui_sessions):
        """Handle test and connect actions."""
        triggered = ctx.triggered_id
        if not triggered:
            return no_update, no_update, no_update

        is_test = triggered == "btn-test-connection"

        # ── SAP GUI mode: Test Connection verifies the first session ──
        if conn_type == "sap_gui":
            if is_test:
                # Test: try to verify the first detected session responds
                if not gui_sessions:
                    return (
                        html.Div(
                            [
                                html.I(className="bi bi-exclamation-triangle me-2",
                                       style={"color": "#E76500"}),
                                html.Span("No sessions detected yet. Click 'Detect Sessions' first.",
                                          style={"fontSize": "13px"}),
                            ],
                            style={"padding": "12px", "background": "#FFF3CD",
                                   "borderRadius": "8px",
                                   "borderLeft": "4px solid #E76500"},
                        ),
                        current_state,
                        no_update,
                    )

                # Try to execute a test query on the first session
                first_session = gui_sessions[0]
                session_id = first_session.get("session_id", "")
                sid = first_session.get("system_id", "")

                test_state = {
                    "connected": True,
                    "type": "sap_gui",
                    "session_id": session_id,
                    "system_id": sid,
                    "client": first_session.get("client", ""),
                    "user": first_session.get("user", ""),
                }

                try:
                    from ..dvm.execution import run_query as exec_query
                    result = exec_query(
                        test_state,
                        "SELECT 'OK' AS STATUS FROM DUMMY",
                        sid=sid,
                        label="TEST_CONNECTION",
                    )
                    if result.success:
                        return (
                            html.Div(
                                [
                                    html.I(className="bi bi-check-circle me-2",
                                           style={"color": "#107E3E"}),
                                    html.Span(
                                        f"Test successful: SAP GUI session "
                                        f"{sid}/{first_session.get('client', '')} responds.",
                                        style={"fontWeight": "500"}),
                                ],
                                style={"padding": "12px", "background": "#E8F5E9",
                                       "borderRadius": "8px",
                                       "borderLeft": "4px solid #107E3E"},
                            ),
                            current_state,
                            no_update,
                        )
                    else:
                        return (
                            html.Div(
                                [
                                    html.I(className="bi bi-x-circle me-2",
                                           style={"color": "#BB0000"}),
                                    html.Span(f"Test failed: {result.error}",
                                              style={"fontWeight": "500"}),
                                ],
                                style={"padding": "12px", "background": "#FFEBEE",
                                       "borderRadius": "8px",
                                       "borderLeft": "4px solid #BB0000"},
                            ),
                            current_state,
                            no_update,
                        )
                except Exception as e:
                    return (
                        html.Div(
                            [
                                html.I(className="bi bi-x-circle me-2",
                                       style={"color": "#BB0000"}),
                                html.Span(f"Test error: {str(e)}",
                                          style={"fontWeight": "500"}),
                            ],
                            style={"padding": "12px", "background": "#FFEBEE",
                                   "borderRadius": "8px",
                                   "borderLeft": "4px solid #BB0000"},
                        ),
                        current_state,
                        no_update,
                    )
            else:
                # Connect: redirect user to pick a session
                return (
                    html.Div(
                        [
                            html.I(className="bi bi-info-circle me-2",
                                   style={"color": "#0070F2"}),
                            html.Span("Select an active session from the detected list above.",
                                      style={"fontSize": "13px"}),
                        ],
                        style={"padding": "12px", "background": "#D1EFFF",
                               "borderRadius": "8px",
                               "borderLeft": "4px solid #0070F2"},
                    ),
                    current_state,
                    no_update,
                )

        # ── HANA Native mode ──
        # Validate inputs
        errors = []
        if not host:
            errors.append("Host is required")
        if not port:
            errors.append("Port is required")
        if not user:
            errors.append("User is required")
        if not password:
            errors.append("Password is required")

        if errors:
            return (
                html.Div(
                    [
                        html.I(className="bi bi-exclamation-circle me-2",
                               style={"color": "#BB0000"}),
                        html.Span("Please fill in required fields:",
                                  style={"fontWeight": "500"}),
                        html.Ul(
                            [html.Li(e, style={"fontSize": "13px"}) for e in errors],
                            style={"marginTop": "6px", "marginBottom": "0",
                                   "paddingLeft": "20px"},
                        ),
                    ],
                    style={"padding": "12px", "background": "#FFEBEE",
                           "borderRadius": "8px",
                           "borderLeft": "4px solid #BB0000"},
                ),
                current_state,
                no_update,
            )

        # Attempt connection
        try:
            from ..connector import HANAConnector
            from ..config import HANAConnectionConfig
            from ..connection_store import ConnectionStore

            config = HANAConnectionConfig(
                host=host,
                port=int(port),
                user=user,
                password=password,
                encrypt="encrypt" in (encrypt or []),
                sslValidateCertificate="validate" in (validate_cert or []),
                tenant=tenant or "",
            )

            connector = HANAConnector(config)
            connector.connect()

            # Test query
            connector.execute_query("SELECT 'OK' AS STATUS FROM DUMMY")
            connector.disconnect()

            action_label = "Test successful" if is_test else "Connected"
            conn_info = config.display_string

            new_state = {
                "connected": not is_test,
                "type": "hana_native",
                "info": conn_info,
                "host": host,
                "port": int(port),
                "user": user,
                "password": password,
                "encrypt": "encrypt" in (encrypt or []),
                "sslValidateCertificate": "validate" in (validate_cert or []),
                "tenant": tenant or "",
                "system_id": (tenant or "").upper() or "",
                "client": "",
            }

            # Persist state if connecting (not just testing)
            if not is_test:
                try:
                    store = ConnectionStore()
                    store.save_state(new_state)
                except Exception:
                    pass

            result_msg = html.Div(
                [
                    html.I(className="bi bi-check-circle me-2",
                           style={"color": "#107E3E"}),
                    html.Span(f"{action_label}: {conn_info}",
                              style={"fontWeight": "500"}),
                ],
                style={"padding": "12px", "background": "#E8F5E9",
                       "borderRadius": "8px",
                       "borderLeft": "4px solid #107E3E"},
            )

            return (
                result_msg,
                new_state if not is_test else current_state,
                False if not is_test else no_update,
            )

        except Exception as e:
            return (
                html.Div(
                    [
                        html.I(className="bi bi-x-circle me-2",
                               style={"color": "#BB0000"}),
                        html.Span(f"Connection failed: {str(e)}",
                                  style={"fontWeight": "500"}),
                    ],
                    style={"padding": "12px", "background": "#FFEBEE",
                           "borderRadius": "8px",
                           "borderLeft": "4px solid #BB0000"},
                ),
                current_state,
                no_update,
            )

    # ──────────────────────────────────────────────────────────────
    # "Use" button on session cards
    # ──────────────────────────────────────────────────────────────
    @app.callback(
        [
            Output("store-connection-state", "data", allow_duplicate=True),
            Output("connection-modal", "is_open", allow_duplicate=True),
            Output("conn-result", "children", allow_duplicate=True),
        ],
        Input({"type": "btn-use-session", "index": ALL}, "n_clicks"),
        State("store-gui-sessions", "data"),
        prevent_initial_call=True,
    )
    def use_session(n_clicks_list, sessions_data):
        """Handle clicking 'Use' on a detected session card."""
        if not n_clicks_list or not any(n_clicks_list):
            return no_update, no_update, no_update

        triggered = ctx.triggered_id
        if not triggered:
            return no_update, no_update, no_update

        session_id = triggered.get("index", "")

        # Look up session info
        session_info = None
        if sessions_data:
            for s in sessions_data:
                if s.get("session_id") == session_id:
                    session_info = s
                    break

        if not session_info:
            session_info = {"session_id": session_id, "system_id": "SAP",
                           "client": "", "user": "", "application_server": ""}

        system_id = session_info.get("system_id", "SAP")
        client = session_info.get("client", "")
        user = session_info.get("user", "")
        server = session_info.get("application_server", "")
        conn_info = f"{system_id}/{client} ({user}@{server})"

        new_state = {
            "connected": True,
            "type": "sap_gui",
            "info": conn_info,
            "session_id": session_id,
            "system_id": system_id,
            "client": client,
            "user": user,
        }

        # Persist state
        try:
            from ..connection_store import ConnectionStore
            store = ConnectionStore()
            store.save_state(new_state)
        except Exception:
            pass

        result_msg = html.Div(
            [
                html.I(className="bi bi-check-circle me-2",
                       style={"color": "#107E3E"}),
                html.Span(f"Connected via SAP GUI: {conn_info}",
                          style={"fontWeight": "500"}),
            ],
            style={"padding": "12px", "background": "#E8F5E9",
                   "borderRadius": "8px",
                   "borderLeft": "4px solid #107E3E"},
        )

        return (
            new_state,
            False,  # close modal
            result_msg,
        )

    # ──────────────────────────────────────────────────────────────
    # Manual Attach (findById bypass) callback
    # ──────────────────────────────────────────────────────────────
    @app.callback(
        [
            Output("store-connection-state", "data", allow_duplicate=True),
            Output("connection-modal", "is_open", allow_duplicate=True),
            Output("gui-sessions-list", "children", allow_duplicate=True),
            Output("store-gui-sessions", "data", allow_duplicate=True),
        ],
        Input("btn-manual-attach", "n_clicks"),
        prevent_initial_call=True,
    )
    def handle_manual_attach(n_clicks):
        """Handle the 'Attach directly' button when enumeration fails.

        Uses the same COM pattern as the working connector: CoInitialize on
        this thread, GetObject, findById directly.
        """
        if not n_clicks:
            return no_update, no_update, no_update, no_update

        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass

        session = None
        session_info = None

        try:
            import win32com.client

            rot_entry = win32com.client.GetObject("SAPGUI")
            if rot_entry is None:
                raise Exception("No SAP GUI in ROT")

            app = rot_entry.GetScriptingEngine
            if app is None:
                raise Exception("Scripting engine not available")

            # Try /app/con[0]/ses[0] first, then ses[1]
            for path in ["/app/con[0]/ses[0]", "/app/con[0]/ses[1]"]:
                try:
                    session = app.findById(path)
                    if session is not None:
                        break
                except Exception:
                    continue

            if session is not None:
                # Read session info
                info = None
                try:
                    info = session.Info
                except Exception:
                    pass

                def _safe(obj, attr, default=""):
                    if obj is None:
                        return default
                    try:
                        v = getattr(obj, attr)
                        return default if v is None else str(v)
                    except Exception:
                        return default

                sid = _safe(session, "Id") or "/app/con[0]/ses[0]"
                session_info = {
                    "session_id": sid,
                    "system_id": _safe(info, "SystemName"),
                    "client": _safe(info, "Client"),
                    "user": _safe(info, "User"),
                    "application_server": _safe(info, "ApplicationServer"),
                    "system_number": _safe(info, "SystemNumber"),
                    "language": _safe(info, "Language"),
                    "transaction": _safe(info, "Transaction"),
                    "connection_string": "",
                    "is_active": True,
                }

        except Exception:
            pass

        if session is None or session_info is None:
            fail_msg = html.Div(
                [
                    html.I(className="bi bi-x-circle me-2",
                           style={"color": "#BB0000"}),
                    html.Div([
                        html.Span("Manual attach failed.",
                                  style={"fontWeight": "500", "fontSize": "13px"}),
                        html.P(
                            "findById(/app/con[0]/ses[0]) could not reach the session. "
                            "Please verify SAP GUI is running with scripting enabled "
                            "and you are logged in.",
                            style={"fontSize": "12px", "color": "#666",
                                   "margin": "6px 0 0"},
                        ),
                    ]),
                ],
                style={"padding": "14px", "background": "#FFEBEE",
                       "borderRadius": "8px",
                       "borderLeft": "4px solid #BB0000", "marginTop": "12px",
                       "display": "flex", "alignItems": "flex-start", "gap": "8px"},
            )
            return no_update, no_update, fail_msg, no_update

        # Success -- establish the connection
        system_id = session_info.get("system_id", "SAP")
        client = session_info.get("client", "")
        user = session_info.get("user", "")
        server = session_info.get("application_server", "")
        s_id = session_info.get("session_id", "/app/con[0]/ses[0]")
        conn_info = f"{system_id}/{client} ({user}@{server})"

        new_state = {
            "connected": True,
            "type": "sap_gui",
            "info": conn_info,
            "session_id": s_id,
            "system_id": system_id,
            "client": client,
            "user": user,
        }

        # Persist
        try:
            from ..connection_store import ConnectionStore
            store = ConnectionStore()
            store.save_state(new_state)
        except Exception:
            pass

        success_msg = html.Div(
            [
                html.I(className="bi bi-check-circle me-2",
                       style={"color": "#107E3E"}),
                html.Span(
                    f"Attached via findById: {conn_info}",
                    style={"fontWeight": "500"}),
            ],
            style={"padding": "12px", "background": "#E8F5E9",
                   "borderRadius": "8px",
                   "borderLeft": "4px solid #107E3E", "marginTop": "12px"},
        )

        return new_state, False, success_msg, [session_info]

    # ──────────────────────────────────────────────────────────────
    # Disconnect
    # ──────────────────────────────────────────────────────────────
    @app.callback(
        [
            Output("store-connection-state", "data", allow_duplicate=True),
            Output("conn-result", "children", allow_duplicate=True),
        ],
        Input("btn-disconnect", "n_clicks"),
        prevent_initial_call=True,
    )
    def disconnect(n_clicks):
        if not n_clicks:
            return no_update, no_update

        empty_state = {"connected": False, "type": "", "info": ""}

        try:
            from ..connection_store import ConnectionStore
            store = ConnectionStore()
            store.save_state(empty_state)
        except Exception:
            pass

        return (
            empty_state,
            html.Div(
                [
                    html.I(className="bi bi-info-circle me-2",
                           style={"color": "#0070F2"}),
                    html.Span("Disconnected.", style={"fontSize": "13px"}),
                ],
                style={"padding": "12px", "background": "#D1EFFF",
                       "borderRadius": "8px",
                       "borderLeft": "4px solid #0070F2"},
            ),
        )
