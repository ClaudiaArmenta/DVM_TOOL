"""DVM Analyses: SQL provider layer.

Responsible for:
  - Loading the correct script variant from the SQL Statement Collection
    (SAP Note 1969700) for the target HANA version.
  - Validating that the loaded file is a real script (not a stub).
  - Patching Modification Section parameters via patcher.py.
  - Providing authored SQL for A6 (NSE) queries.

This module does NOT execute queries; it only produces SQL strings.
Execution is handled by the dvm_analyses callback via execution.py.
"""

import logging
from pathlib import Path
from typing import Tuple

from .version_select import select_variant, get_queries_dir, parse_hana_version
from .patcher import patch_params, validate_script_file

logger = logging.getLogger(__name__)


class MiniCheckNotFoundError(FileNotFoundError):
    """Raised when a required SQL Statement Collection script is not found."""
    pass


class MiniCheckStubWarning(UserWarning):
    """Warning that a script appears to be a stub, not a real SQL Statement Collection script."""
    pass


def get_sql_for_query(
    query_spec: dict,
    version_str: str,
) -> Tuple[str, str]:
    """Produce the SQL for a single query within an analysis.

    Args:
        query_spec: A query dict from ANALYSIS_SPECS. Must have either
                    'script_base' (file-based) or 'sql_authored' (A6 NSE).
        version_str: Target HANA version string (e.g., '2.00.080').

    Returns:
        Tuple of (sql_text, source_label).

    Raises:
        MiniCheckNotFoundError: If no variant file found for the given version.
        ValueError: If patch parameters don't match the script.
    """
    if query_spec.get("sql_authored"):
        sql_key = query_spec["sql_key"]
        sql = _get_nse_sql(sql_key, version_str)
        return sql, "authored SQL (NSE, custom query)"

    # ── File-based approach (A1–A5) ──
    script_base = query_spec["script_base"]
    patches = query_spec.get("patches", {})

    queries_dir = get_queries_dir()
    version_tuple = parse_hana_version(version_str)
    variant_file = select_variant(queries_dir, script_base, version_tuple)

    if not variant_file:
        raise MiniCheckNotFoundError(
            f"SQL Statement Collection script '{script_base}' not found in queries/ "
            f"for version {version_str}. Please place the real SAP Note 1969700 "
            f"script files into: {queries_dir}"
        )

    file_path = Path(queries_dir) / variant_file

    # ── Sanity guard: detect stubs ──
    warnings = validate_script_file(str(file_path))
    for w in warnings:
        logger.warning(w)

    sql = file_path.read_text(encoding="utf-8")

    # ── Apply Modification Section patches ──
    if patches:
        sql = patch_params(sql, patches)

    source_label = f"SQL Statement Collection (SAP Note 1969700): {variant_file}"
    if warnings:
        source_label += " [WARNING: possible stub]"

    return sql, source_label


# ──────────────────────────────────────────────────────────────
# A6: NSE Authored SQL (no mini-check file exists for NSE)
# ──────────────────────────────────────────────────────────────

_NSE_TABLES_SQL = """\
SELECT
  T.SCHEMA_NAME,
  T.TABLE_NAME,
  T.RECORD_COUNT,
  ROUND(P.DISK_SIZE / 1024 / 1024, 2) AS DISK_SIZE_MB,
  ROUND(P.ESTIMATED_MAX_MEMORY_SIZE_IN_TOTAL / 1024 / 1024, 2) AS EST_MAX_MEM_MB,
  T.LOAD_UNIT
FROM
  M_CS_TABLES T INNER JOIN
  M_TABLE_PERSISTENCE_STATISTICS P ON T.SCHEMA_NAME = P.SCHEMA_NAME AND T.TABLE_NAME = P.TABLE_NAME
WHERE
  T.LOAD_UNIT = 'PAGE'
ORDER BY
  P.DISK_SIZE DESC
LIMIT 100
"""

_NSE_TABLES_SQL_PRE060 = """\
SELECT
  T.SCHEMA_NAME,
  T.TABLE_NAME,
  T.RECORD_COUNT,
  ROUND(T.DISK_SIZE / 1024 / 1024, 2) AS DISK_SIZE_MB,
  ROUND(T.MEMORY_SIZE_IN_PAGE_LOADABLE_MAIN / 1024 / 1024, 2) AS PAGE_LOADABLE_MB,
  T.LOAD_UNIT
FROM
  M_CS_TABLES T
WHERE
  T.LOAD_UNIT = 'PAGE'
ORDER BY
  T.DISK_SIZE DESC
LIMIT 100
"""

_NSE_PARTITIONS_SQL = """\
SELECT
  P.SCHEMA_NAME,
  P.TABLE_NAME,
  P.PART_ID,
  P.LOAD_UNIT,
  P.RECORD_COUNT,
  ROUND(P.DISK_SIZE / 1024 / 1024, 2) AS DISK_SIZE_MB,
  ROUND(P.MEMORY_SIZE_IN_MAIN / 1024 / 1024, 2) AS MEM_MAIN_MB,
  ROUND(P.MEMORY_SIZE_IN_PAGE_LOADABLE_MAIN / 1024 / 1024, 2) AS PAGE_LOADABLE_MB
FROM
  M_CS_TABLES P
WHERE
  P.LOAD_UNIT = 'PAGE'
ORDER BY
  P.DISK_SIZE DESC
LIMIT 100
"""

_NSE_COLUMNS_SQL = """\
SELECT
  C.SCHEMA_NAME,
  C.TABLE_NAME,
  C.COLUMN_NAME,
  C.LOAD_UNIT,
  C.MEMORY_SIZE_IN_MAIN,
  C.PERSISTENT_MEMORY_SIZE_IN_TOTAL,
  ROUND(C.MEMORY_SIZE_IN_MAIN / 1024 / 1024, 2) AS MEM_MAIN_MB,
  ROUND(C.PERSISTENT_MEMORY_SIZE_IN_TOTAL / 1024 / 1024, 2) AS PERSIST_MEM_MB
FROM
  M_CS_ALL_COLUMNS C
WHERE
  C.LOAD_UNIT = 'PAGE'
ORDER BY
  C.MEMORY_SIZE_IN_MAIN DESC
LIMIT 200
"""

_NSE_COLUMNS_SQL_PRE060 = """\
SELECT
  C.SCHEMA_NAME,
  C.TABLE_NAME,
  C.COLUMN_NAME,
  C.MEMORY_SIZE_IN_MAIN,
  ROUND(C.MEMORY_SIZE_IN_MAIN / 1024 / 1024, 2) AS MEM_MAIN_MB
FROM
  M_CS_COLUMNS C INNER JOIN
  M_CS_TABLES T ON C.SCHEMA_NAME = T.SCHEMA_NAME AND C.TABLE_NAME = T.TABLE_NAME
WHERE
  T.LOAD_UNIT = 'PAGE'
ORDER BY
  C.MEMORY_SIZE_IN_MAIN DESC
LIMIT 200
"""


def _get_nse_sql(sql_key: str, version_str: str) -> str:
    """Return authored SQL for NSE queries, revision-aware."""
    version_tuple = parse_hana_version(version_str)

    if sql_key == "nse_tables":
        if version_tuple >= (2, 0, 60):
            return _NSE_TABLES_SQL
        return _NSE_TABLES_SQL_PRE060

    elif sql_key == "nse_partitions":
        return _NSE_PARTITIONS_SQL

    elif sql_key == "nse_columns":
        if version_tuple >= (2, 0, 60):
            return _NSE_COLUMNS_SQL
        return _NSE_COLUMNS_SQL_PRE060

    else:
        raise ValueError(f"Unknown NSE SQL key: {sql_key}")
