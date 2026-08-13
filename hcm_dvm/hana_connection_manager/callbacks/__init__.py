"""Callback registration for connection + DVM callbacks."""

from .connection_callbacks import register as register_connection
from .dvm_navigation import register as register_dvm_navigation
from .dvm_analyses import register as register_dvm_analyses
from .dvm_offline import register as register_dvm_offline


def register_all_callbacks(app):
    """Register all callbacks with a Dash app (connection + DVM)."""
    register_connection(app)
    register_dvm_navigation(app)
    register_dvm_analyses(app)
    register_dvm_offline(app)
