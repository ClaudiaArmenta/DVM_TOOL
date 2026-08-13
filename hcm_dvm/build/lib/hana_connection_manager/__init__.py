"""HANA Connection Manager - Reusable SAP HANA connection layer.

A standalone package that provides:
  - SAP HANA database connectivity (hdbcli)
  - SAP GUI session detection and scripting
  - DBACOCKPIT SQL execution via SAP GUI
  - Unified query execution (dispatches to HANA Native or SAP GUI)
  - Query runner with SQL file management
  - Persistent connection state (shared between apps)
  - Dash UI components for connection management
  - Integration helpers for embedding into new apps

Quick Start (standalone):
    python -m hana_connection_manager

Quick Start (as library):
    from hana_connection_manager import (
        HANAConnector,
        HANAConnectionConfig,
        QueryRunner,
        ConnectionStore,
        execute_query,
    )

    # Option 1: Direct connection
    config = HANAConnectionConfig(host="hana01", port=30015, user="SYSTEM", password="...")
    with HANAConnector(config) as conn:
        df = conn.execute_query("SELECT * FROM DUMMY")

    # Option 2: Use shared connection state (works with both HANA Native and SAP GUI)
    store = ConnectionStore()
    state = store.load_state()
    df = execute_query(state, "SELECT * FROM DUMMY")

Quick Start (embedded in another Dash app):
    from hana_connection_manager.integration import (
        create_connected_app,
        get_connector_from_state,
        embed_connection_components,
    )
    from hana_connection_manager.query_executor import execute_query
    from hana_connection_manager.layout import (
        get_connection_modal,
        get_connection_stores,
        get_connect_button,
    )
    from hana_connection_manager.callbacks import register_all_callbacks
"""

__version__ = "1.0.0"

# Core classes
from .config import HANAConnectionConfig, ConnectionManagerConfig, Config
from .connector import HANAConnector
from .sap_gui_connector import SAPGUIConnector, SAPGUISession
from .dba_cockpit_executor import DBACockpitSQLExecutor, DBACockpitConfig
from .query_runner import QueryRunner
from .connection_store import ConnectionStore, ConnectionState
from .exceptions import (
    HanaConnectionManagerError,
    ConnectionError,
    QueryError,
    SessionError,
)
from .logger import get_logger

# Unified execution API
from .query_executor import (
    execute_query,
    load_and_execute,
    auto_export_datasets,
)

__all__ = [
    # Config
    "HANAConnectionConfig",
    "ConnectionManagerConfig",
    "Config",
    # Connectors
    "HANAConnector",
    "SAPGUIConnector",
    "SAPGUISession",
    "DBACockpitSQLExecutor",
    "DBACockpitConfig",
    # Query execution (unified)
    "execute_query",
    "load_and_execute",
    "auto_export_datasets",
    # Query runner
    "QueryRunner",
    # State
    "ConnectionStore",
    "ConnectionState",
    # Exceptions
    "HanaConnectionManagerError",
    "ConnectionError",
    "QueryError",
    "SessionError",
    # Logging
    "get_logger",
]
