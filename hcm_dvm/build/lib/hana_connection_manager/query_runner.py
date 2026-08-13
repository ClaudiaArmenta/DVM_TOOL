"""High-level query runner that loads SQL files and executes them.

Provides a convenient interface for executing named SQL queries
from .sql files with optional time range parameter substitution.
"""

import os
from pathlib import Path
from typing import Optional, Dict

import pandas as pd

from .connector import HANAConnector
from .exceptions import QueryError
from .logger import get_logger

logger = get_logger("query_runner")


class QueryRunner:
    """Load and execute SQL query files against HANA.

    Looks for .sql files in a configurable directory and executes them
    through a HANAConnector instance.

    Usage:
        from hana_connection_manager import HANAConnector, QueryRunner

        connector = HANAConnector(config)
        connector.connect()

        runner = QueryRunner(connector, queries_dir="/path/to/queries")
        df = runner.run("memory_overview", time_from="2024-01-01", time_to="2024-01-02")

        # Or run raw SQL
        df = runner.run_raw("SELECT * FROM M_HOST_INFORMATION")
    """

    def __init__(
        self,
        connector: Optional[HANAConnector] = None,
        queries_dir: Optional[str] = None,
    ):
        """Initialize the query runner.

        Args:
            connector: HANAConnector instance. If None, creates one from env.
            queries_dir: Directory containing .sql files.
                         If None, looks for a 'queries' folder next to this file.
        """
        self.connector = connector or HANAConnector()
        self._queries_dir = Path(queries_dir) if queries_dir else None
        self._query_cache: Dict[str, str] = {}

    @property
    def queries_dir(self) -> Optional[Path]:
        """Get the queries directory."""
        return self._queries_dir

    @queries_dir.setter
    def queries_dir(self, path: str):
        """Set the queries directory."""
        self._queries_dir = Path(path)
        self._query_cache.clear()

    def load_query(self, query_name: str) -> str:
        """Load a SQL query file by name (without .sql extension).

        Args:
            query_name: Name of the query file (e.g. 'memory_overview').

        Returns:
            SQL string content.

        Raises:
            QueryError: If query file not found.
        """
        if query_name in self._query_cache:
            return self._query_cache[query_name]

        if not self._queries_dir:
            raise QueryError(
                f"No queries directory configured",
                "Set queries_dir on the QueryRunner instance.",
            )

        query_path = self._queries_dir / f"{query_name}.sql"
        if not query_path.exists():
            raise QueryError(
                f"Query file not found: {query_name}",
                f"Expected at: {query_path}",
            )

        sql = query_path.read_text(encoding="utf-8")
        self._query_cache[query_name] = sql
        logger.debug(f"Loaded query: {query_name}")
        return sql

    def run(
        self,
        query_name: str,
        params: tuple = (),
        time_from: Optional[str] = None,
        time_to: Optional[str] = None,
    ) -> pd.DataFrame:
        """Load and execute a named query.

        Substitutes {{TIME_FROM}} and {{TIME_TO}} placeholders if provided.

        Args:
            query_name: Name of the .sql file (without extension).
            params: SQL parameters tuple.
            time_from: Start timestamp to substitute.
            time_to: End timestamp to substitute.

        Returns:
            pandas DataFrame with results.
        """
        sql = self.load_query(query_name)

        if time_from:
            sql = sql.replace("{{TIME_FROM}}", time_from)
        if time_to:
            sql = sql.replace("{{TIME_TO}}", time_to)

        logger.info(f"Executing query: {query_name}")
        return self.connector.execute_query(sql, params)

    def run_raw(self, sql: str, params: tuple = ()) -> pd.DataFrame:
        """Execute raw SQL directly.

        Args:
            sql: SQL query string.
            params: Optional parameters.

        Returns:
            pandas DataFrame with results.
        """
        return self.connector.execute_query(sql, params)

    def list_queries(self) -> list:
        """List all available query names in the queries directory.

        Returns:
            Sorted list of query names (without .sql extension).
        """
        if not self._queries_dir or not self._queries_dir.exists():
            return []
        return sorted(
            f.stem for f in self._queries_dir.glob("*.sql")
        )
