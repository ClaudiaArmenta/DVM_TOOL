"""Integration helpers for embedding connection manager into other apps.

This module provides high-level functions that simplify integrating
the connection layer into new Dash applications.

Supports both HANA Native (hdbcli) and SAP GUI (DBACOCKPIT) execution modes.

Example - Minimal app with connection support:

    import dash
    from dash import html
    import dash_bootstrap_components as dbc
    from hana_connection_manager.integration import create_connected_app

    app, get_connector = create_connected_app("My HANA App")

    # For unified query execution (both modes):
    from hana_connection_manager.query_executor import execute_query

    @app.callback(...)
    def my_callback(conn_state):
        df = execute_query(conn_state, "SELECT * FROM DUMMY")
"""

from typing import Optional, Callable, Tuple
from dash import Dash, html, dcc
import dash_bootstrap_components as dbc

from .layout import get_connection_modal, get_connection_stores, get_connection_status_bar
from .callbacks import register_all_callbacks
from .connector import HANAConnector
from .config import HANAConnectionConfig
from .connection_store import ConnectionStore
from .query_executor import execute_query as _execute_query


def create_connected_app(
    title: str = "HANA App",
    port: int = 8050,
    state_file: Optional[str] = None,
    external_stylesheets: Optional[list] = None,
) -> Tuple[Dash, Callable]:
    """Create a Dash app pre-configured with the HANA connection layer.

    Returns a tuple of (app, get_connector_fn) where get_connector_fn
    returns a connected HANAConnector based on the current shared state.

    Args:
        title: Application title.
        port: Port to run on.
        state_file: Path to shared state file (default: ~/.hana_connection_state.json).
        external_stylesheets: Additional CSS stylesheets.

    Returns:
        Tuple of (Dash app instance, connector factory function).

    Usage:
        app, get_connector = create_connected_app("My Analysis App")

        @app.callback(...)
        def my_callback(conn_state):
            connector = get_connector(conn_state)
            if connector:
                df = connector.execute_query("SELECT ...")
    """
    stylesheets = external_stylesheets or []
    stylesheets.extend([
        dbc.themes.BOOTSTRAP,
        "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css",
    ])

    app = Dash(
        __name__,
        suppress_callback_exceptions=True,
        external_stylesheets=stylesheets,
        meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
        title=title,
    )

    # Register connection callbacks
    register_all_callbacks(app)

    store = ConnectionStore(state_file)

    def get_connector(conn_state: Optional[dict] = None) -> Optional[HANAConnector]:
        """Get a connected HANAConnector from the current state.

        Args:
            conn_state: Connection state dict (from Dash store).
                        If None, reads from the shared state file.

        Returns:
            Connected HANAConnector or None if not connected.
        """
        state = conn_state or store.load_state()
        if not state or not state.get("connected"):
            return None

        if state.get("type") != "hana_native":
            return None  # SAP GUI connections need different handling

        try:
            connector = HANAConnector.from_state(state)
            connector.connect()
            return connector
        except Exception:
            return None

    return app, get_connector


def embed_connection_components(layout_children: list) -> list:
    """Add connection manager components to an existing layout children list.

    Inserts the required stores, modal, and status bar components.

    Args:
        layout_children: Your existing layout children list.

    Returns:
        Updated children list with connection components prepended.

    Usage:
        my_layout = html.Div([
            *embed_connection_components([]),
            html.H1("My App"),
            # ... your content ...
        ])
    """
    connection_components = [
        *get_connection_stores(),
        get_connection_modal(),
    ]
    return connection_components + layout_children


def get_connector_from_state(conn_state: dict) -> Optional[HANAConnector]:
    """Create and connect a HANAConnector from a Dash store state dict.

    Convenience function for use inside Dash callbacks.

    Args:
        conn_state: The data from store-connection-state.

    Returns:
        Connected HANAConnector, or None if state is invalid/disconnected.

    Usage in a callback:
        @app.callback(Output(...), Input(...), State("store-connection-state", "data"))
        def my_callback(..., conn_state):
            connector = get_connector_from_state(conn_state)
            if connector is None:
                return "Not connected"
            df = connector.execute_query("SELECT ...")
            connector.disconnect()
            return format_results(df)
    """
    if not conn_state or not conn_state.get("connected"):
        return None

    if conn_state.get("type") != "hana_native":
        return None

    try:
        connector = HANAConnector.from_state(conn_state)
        connector.connect()
        return connector
    except Exception:
        return None


def get_connector_from_store(state_file: Optional[str] = None) -> Optional[HANAConnector]:
    """Create and connect a HANAConnector from the shared state file.

    Reads the persisted connection state and creates a connector.

    Args:
        state_file: Path to state file. Default: ~/.hana_connection_state.json

    Returns:
        Connected HANAConnector, or None if not connected.

    Usage:
        # In a standalone script or non-Dash app
        connector = get_connector_from_store()
        if connector:
            df = connector.execute_query("SELECT * FROM DUMMY")
            connector.disconnect()
    """
    store = ConnectionStore(state_file)
    state = store.load_state()
    return get_connector_from_state(state) if state else None


def execute_query_from_state(conn_state: dict, sql: str, **kwargs):
    """Execute SQL using the unified executor (supports both HANA Native and SAP GUI).

    This is the recommended way to execute queries in Dash callbacks.
    It automatically dispatches to the correct execution mode.

    Args:
        conn_state: Connection state dictionary (from store-connection-state).
        sql: SQL query string.
        **kwargs: Additional args passed to query_executor.execute_query
                  (sid, label, sql_exec_wait).

    Returns:
        pandas DataFrame with results.

    Raises:
        ConnectionError: If not connected.
        QueryError: If execution fails.

    Usage:
        @app.callback(Output(...), Input(...), State("store-connection-state", "data"))
        def my_callback(..., conn_state):
            df = execute_query_from_state(conn_state, "SELECT * FROM DUMMY")
            return df.to_dict("records")
    """
    return _execute_query(conn_state, sql, **kwargs)


def execute_query_from_store(sql: str, state_file: Optional[str] = None, **kwargs):
    """Execute SQL using the persisted connection state file.

    Reads state from file, then dispatches to the correct execution mode.

    Args:
        sql: SQL query string.
        state_file: Path to state file. Default: ~/.hana_connection_state.json
        **kwargs: Additional args (sid, label, sql_exec_wait).

    Returns:
        pandas DataFrame with results, or None if not connected.
    """
    store = ConnectionStore(state_file)
    state = store.load_state()
    if not state or not state.get("connected"):
        return None
    return _execute_query(state, sql, **kwargs)
