"""Dash application factory for DVM Tool.

Creates and configures the Dash app with Bootstrap and DVM layout.
The app instance is created lazily via create_app() to allow test isolation.
"""

import os

import dash
from dash import Dash
import dash_bootstrap_components as dbc

from .dvm.layout import create_layout
from .dvm.version_select import scan_available_versions, get_queries_dir
from .callbacks import register_all_callbacks


_pkg_dir = os.path.dirname(os.path.abspath(__file__))
_assets_folder = os.path.join(_pkg_dir, "assets")


def create_app() -> Dash:
    """Create and return a fully configured DVM Tool Dash application."""
    app = Dash(
        __name__,
        suppress_callback_exceptions=True,
        external_stylesheets=[
            dbc.themes.BOOTSTRAP,
            "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css",
        ],
        meta_tags=[
            {"name": "viewport", "content": "width=device-width, initial-scale=1"},
        ],
        title="DVM Tool – Data Volume Management",
        assets_folder=_assets_folder,
    )

    # Scan available HANA versions from query files
    queries_dir = get_queries_dir()
    version_options = scan_available_versions(queries_dir)

    # Set layout
    app.layout = create_layout(version_options)

    # Register all callbacks (connection + DVM)
    register_all_callbacks(app)

    return app


# Module-level singleton for use by entry points
app = create_app()
server = app.server
