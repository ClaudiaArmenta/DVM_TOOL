"""Multi-session SAP GUI pool for parallel DBACOCKPIT execution.

Design:
  - Creates additional SAP GUI sessions via session.createSession()
  - Each session opens DBACOCKPIT with /nDBACOCKPIT (the /n runs the transaction
    in that session -- NOT /o which creates a new session)
  - One worker per session: pulls queries from a shared queue, executes them
    serially within that session, while N sessions run concurrently
  - Per-session lock ensures one query at a time per session
  - Extra sessions are closed when the run finishes (user's original stays open)

Typical SAP GUI limit: 6 sessions per connection.
"""

import time
import threading
import logging
from typing import Any, Optional, List

from hana_connection_manager.dba_cockpit_executor import (
    DBACockpitSQLExecutor,
    DBACockpitConfig,
    DBACockpitExecutionError,
)

logger = logging.getLogger("dvm.session_pool")

# Maximum sessions SAP GUI typically allows per connection
MAX_SAP_GUI_SESSIONS = 6


class SessionPool:
    """Manages a pool of SAP GUI sessions for parallel DBACOCKPIT execution.

    Usage:
        pool = SessionPool(connection, base_session)
        pool.create_sessions(count=3)  # creates N-1 extra sessions
        executors = pool.get_executors()  # list of DBACockpitSQLExecutor, one per session
        ...
        pool.close_extra_sessions()  # leaves user's original session open
    """

    def __init__(self, connection: Any, base_session: Any, cfg: Optional[DBACockpitConfig] = None):
        """Initialize pool.

        Args:
            connection: The SAP GUI connection COM object.
            base_session: The user's original session (will NOT be closed).
            cfg: Config for DBACockpitSQLExecutor instances.
        """
        self._connection = connection
        self._base_session = base_session
        self._cfg = cfg or DBACockpitConfig()
        self._extra_sessions: List[Any] = []
        self._executors: List[DBACockpitSQLExecutor] = []
        self._locks: List[threading.Lock] = []
        self._lock = threading.Lock()

    @property
    def session_count(self) -> int:
        """Total sessions available (base + extra)."""
        return 1 + len(self._extra_sessions)

    def create_sessions(self, count: int) -> int:
        """Create additional SAP GUI sessions and open DBACOCKPIT in each.

        Args:
            count: Total desired session count (including base). Capped at MAX.

        Returns:
            Number of sessions actually created (excluding base).
        """
        # Target extra sessions: count-1 (base is always #1)
        max_extra = min(count - 1, MAX_SAP_GUI_SESSIONS - 1)
        if max_extra <= 0:
            # Just set up the base session executor
            self._setup_base_executor()
            return 0

        created = 0
        for i in range(max_extra):
            try:
                session = self._create_one_session()
                if session is not None:
                    self._extra_sessions.append(session)
                    created += 1
                    logger.info(f"  Created extra session {created}/{max_extra}")
                else:
                    logger.warning(f"  Failed to create session {i+1}")
                    break
            except Exception as e:
                logger.warning(f"  Session creation failed at {i+1}: {e}")
                break
            time.sleep(1.5)

        # Setup executors for all sessions (base + extras)
        self._setup_all_executors()
        logger.info(f"  Session pool ready: {self.session_count} sessions, {len(self._executors)} executors")
        return created

    def _setup_base_executor(self):
        """Create executor for base session and open DBACOCKPIT."""
        executor = DBACockpitSQLExecutor(self._base_session, self._cfg)
        try:
            executor.open_dbacockpit()
        except Exception as e:
            logger.error(f"  Failed to open DBACOCKPIT on base session: {e}")
            raise
        self._executors = [executor]
        self._locks = [threading.Lock()]

    def _setup_all_executors(self):
        """Create executors for all sessions and open DBACOCKPIT in each."""
        all_sessions = [self._base_session] + list(self._extra_sessions)
        self._executors = []
        self._locks = []

        for i, session in enumerate(all_sessions):
            try:
                # Initialize COM for this thread (needed if called from worker)
                executor = DBACockpitSQLExecutor(session, self._cfg)
                executor.open_dbacockpit()
                self._executors.append(executor)
                self._locks.append(threading.Lock())
                logger.info(f"  DBACOCKPIT opened on session {i+1}/{len(all_sessions)}")
            except Exception as e:
                logger.warning(f"  Failed to open DBACOCKPIT on session {i+1}: {e}")
                # Still add executor (will fail on execute)
                self._executors.append(None)
                self._locks.append(threading.Lock())

    def _create_one_session(self) -> Optional[Any]:
        """Create a single new session via createSession().

        Uses session.createSession() then finds the new session in
        connection.Children.
        """
        try:
            before_count = self._connection.Children.Count
            self._base_session.createSession()
            time.sleep(2)

            after_count = self._connection.Children.Count
            if after_count > before_count:
                new_session = self._connection.Children(after_count - 1)
                return new_session
            else:
                logger.warning("  createSession() did not increase session count")
                return None

        except Exception as e:
            logger.warning(f"  createSession() failed: {e}")
            return None

    def get_executors(self) -> List[Optional[DBACockpitSQLExecutor]]:
        """Return list of executors (one per session). None entries = failed setup."""
        return list(self._executors)

    def get_locks(self) -> List[threading.Lock]:
        """Return per-session locks."""
        return list(self._locks)

    def close_extra_sessions(self):
        """Close all extra sessions, leaving only the base session open.

        Uses /nex to close each extra session.
        """
        for session in reversed(self._extra_sessions):
            try:
                session.findById("wnd[0]/tbar[0]/okcd").text = "/nex"
                session.findById("wnd[0]").sendVKey(0)
                time.sleep(0.5)
                logger.info("  Closed extra session")
            except Exception as e:
                logger.warning(f"  Could not close session: {e}")
        self._extra_sessions.clear()
        self._executors = self._executors[:1]  # Keep base executor
        self._locks = self._locks[:1]
        logger.info("  All extra sessions closed")


class PerSessionLock:
    """Per-session lock manager.

    Each session gets its own lock to ensure one-query-at-a-time within a
    session, while allowing concurrency across sessions.
    """

    def __init__(self):
        self._locks: dict = {}
        self._master_lock = threading.Lock()

    def get_lock(self, session_id: str) -> threading.Lock:
        """Get or create a lock for a specific session."""
        with self._master_lock:
            if session_id not in self._locks:
                self._locks[session_id] = threading.Lock()
            return self._locks[session_id]

    def clear(self):
        """Remove all locks."""
        with self._master_lock:
            self._locks.clear()
