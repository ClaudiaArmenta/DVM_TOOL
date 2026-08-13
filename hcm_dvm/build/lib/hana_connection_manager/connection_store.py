"""Connection state persistence and sharing between apps.

Provides a file-based state store that enables multiple applications
to share connection credentials and status. The state is persisted to
a JSON file that any app can read/write.
"""

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

from .logger import get_logger

logger = get_logger("store")

DEFAULT_STATE_FILE = os.path.join(
    os.path.expanduser("~"), ".hana_connection_state.json"
)


@dataclass
class ConnectionState:
    """Structured representation of a persisted connection state."""

    connected: bool = False
    type: str = ""  # "hana_native" or "sap_gui"
    info: str = ""
    host: str = ""
    port: int = 30015
    user: str = ""
    password: str = ""
    encrypt: bool = True
    sslValidateCertificate: bool = False
    tenant: str = ""
    system_id: str = ""
    session_id: str = ""
    client: str = ""
    last_connected: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConnectionState":
        """Create from dictionary, ignoring unknown keys."""
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


class ConnectionStore:
    """File-based connection state persistence.

    Stores connection state in a JSON file so that multiple applications
    can share the same HANA connection parameters. When one app establishes
    a connection, other apps can read the state and create their own
    connector instances.

    Security Note:
        The state file contains credentials (password in plaintext).
        For production use, consider encrypting or using a credential vault.
        The default file location is ~/.hana_connection_state.json.

    Usage:
        # App A saves connection state after connecting
        store = ConnectionStore()
        store.save_state({"connected": True, "host": "...", "user": "...", ...})

        # App B reads the state and creates a connector
        store = ConnectionStore()
        state = store.load_state()
        if state and state.get("connected"):
            from hana_connection_manager import HANAConnector
            connector = HANAConnector.from_state(state)
            connector.connect()
    """

    def __init__(self, state_file: Optional[str] = None):
        """Initialize the connection store.

        Args:
            state_file: Path to the JSON state file.
                        Default: ~/.hana_connection_state.json
        """
        self._state_file = Path(state_file or DEFAULT_STATE_FILE)

    @property
    def state_file(self) -> Path:
        """Get the state file path."""
        return self._state_file

    def save_state(self, state: Dict[str, Any]) -> None:
        """Persist connection state to file.

        Args:
            state: Dictionary with connection parameters and status.
        """
        try:
            state["last_connected"] = datetime.now().isoformat()
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, default=str)
            logger.info(f"Connection state saved to {self._state_file}")
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    def load_state(self) -> Optional[Dict[str, Any]]:
        """Load connection state from file.

        Returns:
            Dictionary with connection state, or None if file doesn't exist.
        """
        if not self._state_file.exists():
            return None
        try:
            with open(self._state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
            logger.debug(f"Loaded state from {self._state_file}")
            return state
        except Exception as e:
            logger.error(f"Failed to load state: {e}")
            return None

    def load_connection_state(self) -> Optional[ConnectionState]:
        """Load state as a typed ConnectionState object.

        Returns:
            ConnectionState instance or None.
        """
        raw = self.load_state()
        if raw is None:
            return None
        return ConnectionState.from_dict(raw)

    def clear_state(self) -> None:
        """Remove the state file (disconnect)."""
        try:
            if self._state_file.exists():
                self._state_file.unlink()
                logger.info("Connection state cleared")
        except Exception as e:
            logger.error(f"Failed to clear state: {e}")

    def is_connected(self) -> bool:
        """Check if there is an active connection state.

        Returns:
            True if state file exists and shows connected.
        """
        state = self.load_state()
        return state is not None and state.get("connected", False)

    def get_connection_info(self) -> str:
        """Get human-readable connection info string.

        Returns:
            Connection info string or 'Not Connected'.
        """
        state = self.load_state()
        if state and state.get("connected"):
            return state.get("info", "Connected")
        return "Not Connected"
