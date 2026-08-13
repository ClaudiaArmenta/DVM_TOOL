"""Layout components for the HANA Connection Manager.

Provides both a standalone layout (for running as its own app)
and embeddable components (for integration into other apps).

Embeddable API:
    - get_connection_modal(): The connection form modal
    - get_connection_stores(): Required dcc.Store components
    - get_connection_status_bar(): Header status bar widget
    - get_connect_button(): A "Connect to HANA" trigger button
"""

from dash import html, dcc
import dash_bootstrap_components as dbc


# ============================================================
# EMBEDDABLE COMPONENTS
# ============================================================

def get_connection_stores():
    """Get the dcc.Store components required for connection state.

    Returns:
        List of dcc.Store components that must be placed in the layout.
    """
    return [
        dcc.Store(id="store-connection-state", storage_type="session"),
        dcc.Store(id="store-gui-sessions", storage_type="memory"),
    ]


def get_connection_status_bar():
    """Get the connection status indicator widget.

    Returns:
        html.Div with connection status icon and text.
    """
    return html.Div(
        [
            html.I(
                className="bi bi-circle-fill",
                id="conn-status-icon",
                style={"fontSize": "10px", "color": "#FF6B6B", "marginRight": "8px"},
            ),
            html.Span(
                "Not Connected",
                id="conn-status-text",
                style={"fontSize": "13px", "fontWeight": "600"},
            ),
        ],
        style={
            "display": "flex",
            "alignItems": "center",
            "padding": "6px 14px",
            "borderRadius": "16px",
            "border": "1px solid #E5E5E5",
            "background": "#F8F9FA",
        },
    )


def get_connect_button(button_id="btn-connect"):
    """Get a 'Connect to HANA' button that triggers the modal.

    Args:
        button_id: HTML ID for the button. Default: 'btn-connect'.

    Returns:
        html.Button component.
    """
    return html.Button(
        [html.I(className="bi bi-plug me-2"), "Connect to HANA"],
        id=button_id,
        className="btn btn-primary",
        n_clicks=0,
    )


def get_disconnect_button(button_id="btn-disconnect"):
    """Get a 'Disconnect' button.

    Args:
        button_id: HTML ID for the button.

    Returns:
        html.Button component.
    """
    return html.Button(
        [html.I(className="bi bi-x-circle me-2"), "Disconnect"],
        id=button_id,
        className="btn btn-outline-secondary",
        n_clicks=0,
    )


def get_connection_modal():
    """Get the full connection modal component.

    Returns:
        dbc.Modal with connection form (HANA Native + SAP GUI panels).
    """
    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle(
                    [html.I(className="bi bi-database me-2"), "Connect to SAP HANA"]
                ),
                close_button=True,
            ),
            dbc.ModalBody(
                [
                    # Connection type selector
                    html.Div(
                        [
                            html.Label("Connection Type",
                                       style={"fontWeight": "600", "marginBottom": "8px",
                                              "fontSize": "13px", "color": "#556B82"}),
                            dbc.RadioItems(
                                id="conn-type-selector",
                                options=[
                                    {"label": "  HANA Native (Direct)", "value": "hana_native"},
                                    {"label": "  SAP GUI (Active Session)", "value": "sap_gui"},
                                ],
                                value="hana_native",
                                labelStyle={
                                    "display": "flex", "alignItems": "center",
                                    "padding": "10px 14px", "marginBottom": "6px",
                                    "borderRadius": "8px", "cursor": "pointer",
                                    "border": "1px solid #E5E5E5", "fontSize": "14px",
                                },
                                inputStyle={"marginRight": "8px"},
                            ),
                        ],
                        style={"marginBottom": "20px"},
                    ),

                    # SAP GUI Panel
                    html.Div(
                        id="conn-panel-sap-gui",
                        children=[
                            html.Div(
                                [
                                    html.I(className="bi bi-display",
                                           style={"fontSize": "32px", "color": "#0070F2",
                                                  "marginBottom": "8px"}),
                                    html.P("Detect Active SAP GUI Sessions",
                                           style={"fontWeight": "500", "margin": "0"}),
                                    html.P("Finds running SAP GUI windows on your machine",
                                           style={"fontSize": "12px", "color": "#999",
                                                  "margin": "4px 0 12px"}),
                                    html.Button(
                                        [html.I(className="bi bi-search me-2"),
                                         "Detect Sessions"],
                                        id="btn-detect-gui",
                                        className="btn btn-primary w-100",
                                        n_clicks=0,
                                    ),
                                ],
                                style={"textAlign": "center", "padding": "24px",
                                       "border": "1px solid #E5E5E5",
                                       "borderRadius": "8px", "marginBottom": "16px"},
                            ),
                            html.Div(id="gui-sessions-list"),
                            # Manual attach button (shown by detect callback when 0 sessions)
                            html.Div(
                                [
                                    html.Hr(style={"borderColor": "#E5E5E5", "margin": "12px 0"}),
                                    html.Span(
                                        "Or try attaching directly (bypasses enumeration):",
                                        style={"fontSize": "12px", "color": "#666"},
                                    ),
                                    html.Button(
                                        [html.I(className="bi bi-link-45deg me-1"),
                                         "Attach to /app/con[0]/ses[0]"],
                                        id="btn-manual-attach",
                                        className="btn btn-sm btn-outline-primary",
                                        n_clicks=0,
                                        style={"marginTop": "6px"},
                                    ),
                                ],
                                id="manual-attach-container",
                                style={"display": "none"},
                            ),
                            html.Div(
                                [
                                    html.I(className="bi bi-info-circle me-2",
                                           style={"color": "#0070F2"}),
                                    html.Span(
                                        "Requires SAP GUI for Windows with scripting enabled.",
                                        style={"fontSize": "12px", "color": "#666"},
                                    ),
                                ],
                                style={"display": "flex", "alignItems": "flex-start",
                                       "marginTop": "12px"},
                            ),
                        ],
                        style={"display": "none"},
                    ),

                    # HANA Native Panel
                    html.Div(
                        id="conn-panel-hana-native",
                        children=[
                            html.Div(
                                [
                                    # Host
                                    html.Div(
                                        [
                                            html.Label("Host *",
                                                       style={"fontSize": "12px",
                                                              "fontWeight": "600",
                                                              "color": "#556B82"}),
                                            dbc.Input(
                                                id="conn-host",
                                                placeholder="e.g. hana01.company.com",
                                                type="text",
                                            ),
                                        ],
                                        style={"marginBottom": "12px"},
                                    ),
                                    # Port + Instance
                                    html.Div(
                                        [
                                            html.Div(
                                                [
                                                    html.Label("Port *",
                                                               style={"fontSize": "12px",
                                                                      "fontWeight": "600",
                                                                      "color": "#556B82"}),
                                                    dbc.Input(
                                                        id="conn-port",
                                                        placeholder="30015",
                                                        value="30015",
                                                        type="number",
                                                    ),
                                                ],
                                                style={"flex": "1"},
                                            ),
                                            html.Div(
                                                [
                                                    html.Label("Instance No.",
                                                               style={"fontSize": "12px",
                                                                      "fontWeight": "600",
                                                                      "color": "#556B82"}),
                                                    dbc.Input(
                                                        id="conn-instance",
                                                        placeholder="00",
                                                        type="text",
                                                        maxLength=2,
                                                    ),
                                                ],
                                                style={"flex": "1"},
                                            ),
                                        ],
                                        style={"display": "flex", "gap": "12px",
                                               "marginBottom": "12px"},
                                    ),
                                    # Tenant
                                    html.Div(
                                        [
                                            html.Label("Tenant Database",
                                                       style={"fontSize": "12px",
                                                              "fontWeight": "600",
                                                              "color": "#556B82"}),
                                            dbc.Input(
                                                id="conn-tenant",
                                                placeholder="e.g. HDB (leave empty for SYSTEMDB)",
                                                type="text",
                                            ),
                                        ],
                                        style={"marginBottom": "12px"},
                                    ),
                                    html.Hr(style={"borderColor": "#E5E5E5",
                                                   "margin": "16px 0"}),
                                    # User
                                    html.Div(
                                        [
                                            html.Label("User *",
                                                       style={"fontSize": "12px",
                                                              "fontWeight": "600",
                                                              "color": "#556B82"}),
                                            dbc.Input(
                                                id="conn-user",
                                                placeholder="e.g. SYSTEM",
                                                type="text",
                                            ),
                                        ],
                                        style={"marginBottom": "12px"},
                                    ),
                                    # Password
                                    html.Div(
                                        [
                                            html.Label("Password *",
                                                       style={"fontSize": "12px",
                                                              "fontWeight": "600",
                                                              "color": "#556B82"}),
                                            dbc.Input(
                                                id="conn-password",
                                                placeholder="Enter password",
                                                type="password",
                                            ),
                                        ],
                                        style={"marginBottom": "12px"},
                                    ),
                                    # SSL options
                                    html.Div(
                                        [
                                            dbc.Checklist(
                                                id="conn-encrypt",
                                                options=[{"label": "  Encrypt connection (TLS/SSL)",
                                                          "value": "encrypt"}],
                                                value=["encrypt"],
                                                style={"fontSize": "13px"},
                                            ),
                                        ],
                                        style={"marginBottom": "8px"},
                                    ),
                                    html.Div(
                                        [
                                            dbc.Checklist(
                                                id="conn-validate-cert",
                                                options=[{"label": "  Validate server certificate",
                                                          "value": "validate"}],
                                                value=[],
                                                style={"fontSize": "13px"},
                                            ),
                                        ],
                                    ),
                                ],
                                style={"padding": "20px", "border": "1px solid #E5E5E5",
                                       "borderRadius": "8px"},
                            ),
                        ],
                    ),

                    # Connection result message
                    html.Div(id="conn-result", style={"marginTop": "16px"}),
                ]
            ),
            dbc.ModalFooter(
                [
                    html.Button("Test Connection", id="btn-test-connection",
                                className="btn btn-outline-primary me-2", n_clicks=0),
                    html.Button("Connect", id="btn-establish-connection",
                                className="btn btn-primary", n_clicks=0),
                ]
            ),
        ],
        id="connection-modal",
        is_open=False,
        size="lg",
        centered=True,
    )


# ============================================================
# STANDALONE LAYOUT
# ============================================================

def create_standalone_layout():
    """Create the full standalone app layout for the Connection Manager.

    This layout is used when running the Connection Manager as its own app.
    """
    return html.Div(
        [
            # Stores
            *get_connection_stores(),

            # Header
            html.Div(
                [
                    html.Div(
                        [
                            html.I(className="bi bi-database",
                                   style={"fontSize": "24px", "color": "#0070F2",
                                          "marginRight": "12px"}),
                            html.Span("HANA Connection Manager",
                                      style={"fontSize": "18px", "fontWeight": "700",
                                             "color": "#1D2D3E"}),
                        ],
                        style={"display": "flex", "alignItems": "center"},
                    ),
                    get_connection_status_bar(),
                ],
                style={
                    "display": "flex",
                    "justifyContent": "space-between",
                    "alignItems": "center",
                    "padding": "16px 32px",
                    "borderBottom": "1px solid #E5E5E5",
                    "background": "white",
                },
            ),

            # Main content
            html.Div(
                [
                    html.Div(
                        [
                            html.H4("Connection Management",
                                     style={"marginBottom": "8px", "color": "#1D2D3E"}),
                            html.P(
                                "Manage SAP HANA connections. Connected state is shared "
                                "with other applications via a persistent state file.",
                                style={"color": "#556B82", "marginBottom": "24px"},
                            ),

                            # Action buttons
                            html.Div(
                                [
                                    get_connect_button(),
                                    html.Span("  "),
                                    get_disconnect_button(),
                                ],
                                style={"marginBottom": "24px"},
                            ),

                            # Info card
                            html.Div(
                                [
                                    html.H6(
                                        [html.I(className="bi bi-info-circle me-2"),
                                         "How it works"],
                                        style={"color": "#0070F2"},
                                    ),
                                    html.Ul(
                                        [
                                            html.Li("Click 'Connect to HANA' to open the connection dialog"),
                                            html.Li("Enter your HANA system details or detect SAP GUI sessions"),
                                            html.Li("Connection state is persisted to ~/.hana_connection_state.json"),
                                            html.Li("Other apps import this package to use the active connection"),
                                        ],
                                        style={"fontSize": "13px", "color": "#556B82",
                                               "paddingLeft": "20px"},
                                    ),
                                ],
                                style={
                                    "padding": "20px",
                                    "background": "#E1F4FF",
                                    "borderRadius": "8px",
                                    "border": "1px solid #B3DCFF",
                                },
                            ),
                        ],
                        style={
                            "maxWidth": "700px",
                            "margin": "40px auto",
                            "padding": "32px",
                            "background": "white",
                            "borderRadius": "12px",
                            "boxShadow": "0 2px 8px rgba(0,0,0,0.06)",
                        },
                    ),
                ],
                style={"padding": "20px"},
            ),

            # Connection Modal
            get_connection_modal(),
        ]
    )
