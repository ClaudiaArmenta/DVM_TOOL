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


# Custom document shell. The inline head script applies the saved light/dark
# theme *before* first paint (no flash) and wires the header theme toggle,
# persisting the choice to localStorage. Forcing data-theme on <html> overrides
# the OS preference; clearing it would fall back to prefers-color-scheme.
_INDEX_STRING = """<!DOCTYPE html>
<html>
    <head>
        <script>
        (function () {
          try {
            var s = localStorage.getItem('dvm-theme');
            if (s === 'dark' || s === 'light') {
              document.documentElement.setAttribute('data-theme', s);
            }
          } catch (e) {}
          function cur() {
            var t = document.documentElement.getAttribute('data-theme');
            if (t === 'dark' || t === 'light') return t;
            return (window.matchMedia &&
                    window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';
          }
          function paint() {
            var b = document.getElementById('btn-theme-toggle');
            if (!b) return;
            var t = cur();
            var i = b.querySelector('i');
            if (i) i.className = (t === 'dark') ? 'bi bi-sun' : 'bi bi-moon-stars';
            var lbl = (t === 'dark') ? 'Switch to light theme' : 'Switch to dark theme';
            b.setAttribute('title', lbl);
            b.setAttribute('aria-label', lbl);
          }
          document.addEventListener('click', function (e) {
            var b = e.target.closest ? e.target.closest('#btn-theme-toggle') : null;
            if (!b) return;
            var next = (cur() === 'dark') ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', next);
            try { localStorage.setItem('dvm-theme', next); } catch (er) {}
            paint();
          });
          document.addEventListener('DOMContentLoaded', paint);
          var iv = setInterval(function () {
            if (document.getElementById('btn-theme-toggle')) { paint(); clearInterval(iv); }
          }, 120);
          setTimeout(function () { clearInterval(iv); }, 6000);
        })();
        </script>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>"""


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

    # Apply saved theme before paint + wire the header theme toggle.
    app.index_string = _INDEX_STRING

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
