"""Entry point for the packaged DVM Tool executable.

Starts the Dash server on a free local port and opens the default browser.
Used by PyInstaller (see dvm_tool.spec). Run directly for a local smoke test:

    python launcher.py
"""

import os
import socket
import sys
import threading
import time
import webbrowser

# Make the app importable regardless of the working directory (covers the
# embedded-Python portable bundle where launcher.py sits next to the package).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _free_port(preferred: int = 8051) -> int:
    """Return the first bindable local port, preferring the usual one."""
    for candidate in (preferred, 8052, 8053, 8060, 0):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("127.0.0.1", candidate))
            port = s.getsockname()[1]
            s.close()
            return port
        except OSError:
            continue
    return preferred


def main():
    port = _free_port()
    # Import after choosing the port so app creation (asset/query scan) runs once.
    from hana_connection_manager.app import app

    url = f"http://127.0.0.1:{port}"

    def _open_browser():
        # Wait for the server to be up, then open the default browser. Use the
        # Windows-native os.startfile first (most reliable on locked-down PCs),
        # falling back to webbrowser. Retry a couple of times.
        time.sleep(2.5)
        for _ in range(3):
            try:
                os.startfile(url)  # noqa: S606 (Windows: opens default browser)
                return
            except Exception:
                try:
                    webbrowser.open(url)
                    return
                except Exception:
                    time.sleep(1.5)

    threading.Thread(target=_open_browser, daemon=True).start()

    print("=" * 60)
    print("  DVM Tool - SAP HANA Data Volume Management")
    print("")
    print("  If your browser does not open automatically, paste this")
    print("  address into your browser (Chrome / Edge):")
    print("")
    print(f"      {url}")
    print("")
    print("  Keep this window open. Close it to stop the tool.")
    print("=" * 60)

    # Flask/Dash dev server, no reloader (single process for the frozen exe).
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
