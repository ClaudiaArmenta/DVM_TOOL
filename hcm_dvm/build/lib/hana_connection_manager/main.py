"""Application entry point for the DVM Tool.

Usage:
    python -m hana_connection_manager
    hana-dvm  (console script, if installed via pip)
"""

from .app import app
from .config import Config


def run():
    """Start the DVM Tool Dash server."""
    print("=" * 55)
    print("  DVM Tool – SAP HANA Data Volume Management")
    print(f"  Open http://localhost:{Config.port} in your browser")
    print("=" * 55)
    app.run(
        host=Config.host,
        port=Config.port,
        debug=Config.debug,
    )


if __name__ == "__main__":
    run()
