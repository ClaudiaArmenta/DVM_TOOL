"""SAP HANA database connector using hdbcli.

Provides a connection manager that handles connect/disconnect lifecycle
and executes SQL queries returning pandas DataFrames.
"""

from typing import Optional
import pandas as pd

from .config import HANAConnectionConfig
from .exceptions import ConnectionError, QueryError
from .logger import get_logger

logger = get_logger("connector")


class HANAConnector:
    """Manages connections to SAP HANA and executes queries.

    Usage:
        # Direct usage
        connector = HANAConnector(config)
        connector.connect()
        df = connector.execute_query("SELECT * FROM DUMMY")
        connector.disconnect()

        # Context manager
        with HANAConnector(config) as conn:
            df = conn.execute_query("SELECT * FROM DUMMY")

        # From connection state dict (e.g., from ConnectionStore)
        connector = HANAConnector.from_state(state_dict)
        connector.connect()
    """

    def __init__(self, config: Optional[HANAConnectionConfig] = None):
        """Initialize the connector.

        Args:
            config: HANA connection parameters. If None, loads from environment.
        """
        self.config = config or HANAConnectionConfig.from_env()
        self._connection = None

    @classmethod
    def from_state(cls, state: dict) -> "HANAConnector":
        """Create a connector from a connection state dictionary.

        Args:
            state: Dictionary with connection parameters (as stored by ConnectionStore).

        Returns:
            HANAConnector instance (not yet connected).
        """
        config = HANAConnectionConfig.from_dict(state)
        return cls(config)

    @property
    def is_connected(self) -> bool:
        """Check if the connection is active."""
        return self._connection is not None and self._connection.isconnected()

    def connect(self):
        """Establish connection to HANA.

        Raises:
            ConnectionError: If hdbcli is not installed or connection fails.
        """
        try:
            from hdbcli import dbapi

            connect_kwargs = {
                "address": self.config.host,
                "port": self.config.port,
                "user": self.config.user,
                "password": self.config.password,
                "encrypt": self.config.encrypt,
                "sslValidateCertificate": self.config.sslValidateCertificate,
            }

            # If tenant is specified, use databaseName parameter
            if self.config.tenant:
                connect_kwargs["databaseName"] = self.config.tenant

            self._connection = dbapi.connect(**connect_kwargs)
            logger.info(f"Connected to HANA at {self.config.host}:{self.config.port}")

        except ImportError:
            raise ConnectionError(
                "hdbcli not installed",
                "Install with: pip install hdbcli",
            )
        except Exception as e:
            raise ConnectionError(
                f"Failed to connect to HANA: {e}",
                f"Host: {self.config.host}, Port: {self.config.port}",
            )

    def disconnect(self):
        """Close the HANA connection."""
        if self._connection:
            try:
                self._connection.close()
            except Exception:
                pass
            self._connection = None
            logger.info("Disconnected from HANA")

    def execute_query(self, sql: str, params: tuple = ()) -> pd.DataFrame:
        """Execute a SQL query and return results as a DataFrame.

        Args:
            sql: SQL query string.
            params: Optional query parameters.

        Returns:
            pandas DataFrame with query results.

        Raises:
            ConnectionError: If not connected.
            QueryError: If query execution fails.
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to HANA. Call connect() first.")
        try:
            cursor = self._connection.cursor()
            cursor.execute(sql, params)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            cursor.close()
            return pd.DataFrame(rows, columns=columns)
        except Exception as e:
            raise QueryError(f"Query execution failed: {e}", sql[:200])

    def execute_script(self, sql: str) -> None:
        """Execute a SQL statement that does not return results (DDL/DML).

        Args:
            sql: SQL statement to execute.

        Raises:
            ConnectionError: If not connected.
            QueryError: If execution fails.
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to HANA. Call connect() first.")
        try:
            cursor = self._connection.cursor()
            cursor.execute(sql)
            cursor.close()
        except Exception as e:
            raise QueryError(f"Script execution failed: {e}", sql[:200])

    def test_connection(self) -> bool:
        """Test the connection by running SELECT 'OK' FROM DUMMY.

        Returns:
            True if connection is working.

        Raises:
            ConnectionError: If connection test fails.
        """
        try:
            self.connect()
            result = self.execute_query("SELECT 'OK' AS STATUS FROM DUMMY")
            self.disconnect()
            return len(result) > 0
        except Exception as e:
            self.disconnect()
            raise ConnectionError(f"Connection test failed: {e}")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False

    def __repr__(self):
        status = "connected" if self.is_connected else "disconnected"
        return f"HANAConnector({self.config.display_string}, {status})"
