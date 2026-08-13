"""SAP GUI Scripting connector.

Detects active SAP GUI sessions and extracts system information
using the SAP GUI Scripting API (Windows COM automation).

Requirements:
  - Windows OS
  - SAP GUI for Windows installed
  - Scripting enabled (client and server)
  - pywin32 package
"""

import platform
from typing import Optional, List, Any
from dataclasses import dataclass

from .logger import get_logger
from .exceptions import SessionError

logger = get_logger("sap_gui")


@dataclass
class SAPGUISession:
    """Represents a detected SAP GUI session."""

    system_id: str
    client: str
    user: str
    session_id: str
    connection_string: str
    application_server: str
    system_number: str
    language: str
    transaction: str
    is_active: bool = True

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "session_id": self.session_id,
            "system_id": self.system_id,
            "client": self.client,
            "user": self.user,
            "application_server": self.application_server,
            "system_number": self.system_number,
            "language": self.language,
            "transaction": self.transaction,
            "connection_string": self.connection_string,
            "is_active": self.is_active,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SAPGUISession":
        """Create from dictionary."""
        return cls(
            system_id=data.get("system_id", ""),
            client=data.get("client", ""),
            user=data.get("user", ""),
            session_id=data.get("session_id", ""),
            connection_string=data.get("connection_string", ""),
            application_server=data.get("application_server", ""),
            system_number=data.get("system_number", ""),
            language=data.get("language", ""),
            transaction=data.get("transaction", ""),
            is_active=data.get("is_active", True),
        )


class SAPGUIConnector:
    """Detect and interact with active SAP GUI sessions.

    Uses the SAP GUI Scripting API via Windows COM automation.
    Requires:
      - SAP GUI for Windows installed
      - Scripting enabled on client
      - Scripting enabled on server (sapgui/user_scripting = TRUE)

    Usage:
        connector = SAPGUIConnector()
        if connector.is_available():
            sessions = connector.detect_sessions()
            for sess in sessions:
                print(f"{sess.system_id} / {sess.client} - {sess.user}")

            # Get raw COM session for scripting
            session_obj = connector.get_session(sessions[0].session_id)
    """

    def __init__(self):
        self._sap_gui = None
        self._application = None
        self._sessions: List[SAPGUISession] = []

    @staticmethod
    def is_available() -> bool:
        """Check if SAP GUI Scripting is available on this platform."""
        if platform.system() != "Windows":
            return False
        try:
            import win32com.client
            return True
        except ImportError:
            return False

    @staticmethod
    def _safe_get(obj, attr, default=""):
        """Read a late-bound COM property without letting one bad read abort everything."""
        if obj is None:
            return default
        try:
            value = getattr(obj, attr)
            return default if value is None else str(value)
        except Exception:
            return default

    @staticmethod
    def _safe_count(obj):
        """Return obj.Children.Count defensively (0 on any failure)."""
        try:
            return int(obj.Children.Count)
        except Exception as e:
            logger.warning(f"Could not read Children.Count: {e}")
            return 0

    @staticmethod
    def _probe_children(obj, max_probe=16):
        """Probe children by direct index access when .Count is unreliable.

        Some SAP GUI versions/COM configurations report Children.Count == 0
        while sessions are still accessible by index. This method probes
        sequential indices until access fails.

        Returns:
            List of COM objects successfully accessed by index.
        """
        children = []
        for idx in range(max_probe):
            try:
                child = obj.Children(idx)
                if child is None:
                    break
                children.append(child)
            except Exception:
                break
        return children

    def detect_sessions(self) -> List[SAPGUISession]:
        """Detect all active SAP GUI sessions.

        Returns:
            List of SAPGUISession objects with system details.

        Raises:
            SessionError: If detection fails at the COM/ROT level.
        """
        self._sessions = []

        if not self.is_available():
            logger.warning("SAP GUI Scripting not available (requires Windows + pywin32)")
            return []

        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass

        try:
            import win32com.client

            rot_entry = win32com.client.GetObject("SAPGUI")
            if rot_entry is None:
                logger.info("No SAP GUI instance found in Running Object Table")
                return []

            self._application = rot_entry.GetScriptingEngine
            if self._application is None:
                logger.warning("SAP GUI Scripting engine not available.")
                return []

            conn_count = self._safe_count(self._application)
            logger.info(f"Found {conn_count} SAP GUI connection(s)")

            total_connections_seen = 0

            for conn_idx in range(conn_count):
                total_connections_seen += 1
                try:
                    connection = self._application.Children(conn_idx)
                except Exception as e:
                    logger.warning(
                        f"Connection [{conn_idx}]: could not access — {e}"
                    )
                    continue

                conn_string = self._safe_get(connection, "ConnectionString", "")
                sess_count = self._safe_count(connection)
                logger.info(
                    f"Connection [{conn_idx}] .Children.Count={sess_count}"
                    + (f" (conn_string={conn_string})" if conn_string else "")
                )

                # Collect session COM objects: prefer .Count, but fall back
                # to probe-by-index when Count reports 0 (known COM quirk).
                if sess_count > 0:
                    session_objs = []
                    for si in range(sess_count):
                        try:
                            session_objs.append(connection.Children(si))
                        except Exception as e:
                            logger.warning(
                                f"Connection [{conn_idx}] session [{si}]: "
                                f"index access failed — {e}"
                            )
                else:
                    # Count was 0 — probe by index in case Count lied
                    logger.info(
                        f"Connection [{conn_idx}]: .Count=0, probing by index..."
                    )
                    session_objs = self._probe_children(connection)
                    if session_objs:
                        logger.info(
                            f"Connection [{conn_idx}]: probe found "
                            f"{len(session_objs)} session(s) despite .Count=0"
                        )
                    else:
                        # Also try connection.Sessions collection as fallback
                        try:
                            sessions_coll = connection.Sessions
                            if sessions_coll is not None:
                                probe_count = 0
                                try:
                                    probe_count = int(sessions_coll.Count)
                                except Exception:
                                    pass
                                if probe_count > 0:
                                    for si in range(probe_count):
                                        try:
                                            session_objs.append(sessions_coll(si))
                                        except Exception:
                                            break
                                else:
                                    # Probe .Sessions by index too
                                    for si in range(16):
                                        try:
                                            s = sessions_coll(si)
                                            if s is None:
                                                break
                                            session_objs.append(s)
                                        except Exception:
                                            break
                                if session_objs:
                                    logger.info(
                                        f"Connection [{conn_idx}]: found "
                                        f"{len(session_objs)} via .Sessions"
                                    )
                        except Exception as e:
                            logger.debug(
                                f"Connection [{conn_idx}]: .Sessions fallback failed — {e}"
                            )

                if not session_objs:
                    logger.warning(
                        f"Connection [{conn_idx}] has 0 accessible sessions. "
                        "Likely causes: not logged on in this SAP GUI window, "
                        "or server-side scripting is disabled "
                        "(sapgui/user_scripting = TRUE not set), "
                        "or client-side scripting is disabled in SAP GUI Options."
                    )
                    continue

                logger.info(
                    f"Connection [{conn_idx}] has {len(session_objs)} session(s)"
                )

                for sess_idx, session in enumerate(session_objs):

                    # Read session ID defensively
                    session_id = self._safe_get(session, "Id") or f"/app/con[{conn_idx}]/ses[{sess_idx}]"

                    # Try to read session.Info; if it fails, still append with minimal data
                    info = None
                    try:
                        info = session.Info
                    except Exception as e:
                        logger.warning(
                            f"Connection [{conn_idx}] session [{sess_idx}]: "
                            f"could not read session.Info — {e}. "
                            "Appending session with minimal details."
                        )

                    gui_session = SAPGUISession(
                        system_id=self._safe_get(info, "SystemName"),
                        client=self._safe_get(info, "Client"),
                        user=self._safe_get(info, "User"),
                        session_id=session_id,
                        connection_string=conn_string,
                        application_server=self._safe_get(info, "ApplicationServer"),
                        system_number=self._safe_get(info, "SystemNumber"),
                        language=self._safe_get(info, "Language"),
                        transaction=self._safe_get(info, "Transaction"),
                        is_active=True,
                    )
                    self._sessions.append(gui_session)

                    logger.info(
                        f"Detected: {gui_session.system_id} "
                        f"client {gui_session.client} "
                        f"user {gui_session.user} "
                        f"id {session_id}"
                    )

            # Post-loop diagnostic: connections existed but nothing survived
            if total_connections_seen > 0 and not self._sessions:
                logger.warning(
                    f"Found {total_connections_seen} connection(s) but could not "
                    "read any sessions. Most common causes:\n"
                    "  1. No user is logged on in the SAP GUI window(s).\n"
                    "  2. Server-side scripting is not enabled "
                    "(profile parameter sapgui/user_scripting = TRUE).\n"
                    "  3. Client-side scripting is not enabled "
                    "(SAP GUI > Options > Accessibility & Scripting > "
                    "Scripting > Enable Scripting)."
                )

        except Exception as e:
            logger.error(f"Failed to detect SAP GUI sessions: {e}")
            raise SessionError(
                "Cannot connect to SAP GUI",
                f"Ensure SAP GUI is running and scripting is enabled. Error: {e}",
            )

        return self._sessions

    def get_session(self, session_id: Optional[str] = None) -> Any:
        """Get a specific SAP GUI session COM object for scripting.

        Args:
            session_id: Session ID (e.g. '/app/con[0]/ses[0]').
                        If None, returns the first active session.

        Returns:
            The raw COM session object for further scripting.

        Raises:
            SessionError: If session cannot be found.
        """
        if self._application:
            try:
                return self._find_session(self._application, session_id)
            except Exception:
                pass

        app = self._get_scripting_engine()
        self._application = app
        return self._find_session(app, session_id)

    @staticmethod
    def _get_scripting_engine() -> Any:
        """Acquire the SAP GUI Scripting engine from the Running Object Table."""
        if platform.system() != "Windows":
            raise SessionError("SAP GUI Scripting requires Windows")

        import win32com.client

        try:
            rot_entry = win32com.client.GetObject("SAPGUI")
            if rot_entry:
                app = rot_entry.GetScriptingEngine
                if app:
                    return app
        except Exception:
            pass

        try:
            sap_gui = win32com.client.Dispatch("SapGui.ScriptingCtrl.1")
            if sap_gui:
                app = sap_gui.Viewer.GetScriptingEngine
                if app:
                    return app
        except Exception:
            pass

        raise SessionError(
            "Could not acquire SAP GUI Scripting engine",
            "Ensure SAP GUI is running and scripting is enabled.",
        )

    @staticmethod
    def _find_session(app, session_id: Optional[str] = None) -> Any:
        """Find a session by ID or return the first available."""
        if session_id:
            try:
                return app.findById(session_id)
            except Exception:
                pass

        # Try to return first available session via direct index access
        # (don't rely on .Count which can lie on some SAP GUI versions)
        try:
            connection = app.Children(0)
            if connection is not None:
                try:
                    session = connection.Children(0)
                    if session is not None:
                        return session
                except Exception:
                    pass
                # Fallback: try .Sessions(0)
                try:
                    session = connection.Sessions(0)
                    if session is not None:
                        return session
                except Exception:
                    pass
        except Exception:
            pass

        raise SessionError("No active SAP GUI session found")
