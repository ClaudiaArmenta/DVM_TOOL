"""SQL Modification Section patcher for DVM Tool.

Patches parameter values in SAP mini-check SQL scripts (SAP Note 1969700).

The Modification Section in these scripts is a subquery from DUMMY with
the pattern:

    SELECT                  /* Modification section */
      '%' SCHEMA_NAME,
      'NONE' AGGREGATE_BY,
      50 RESULT_ROWS,
      -1 MIN_TABLE_DISK_SIZE_MB
    FROM DUMMY

This module patches individual parameter values by anchoring on the
parameter name (the alias after the value), restricted to lines within
the Modification Section block only.

IMPORTANT: The regex MUST match only the declaration line in the Modification
Section (e.g. `'NONE' AGGREGATE_BY`), not reference uses like `BI.AGGREGATE_BY`
or `TIME_AGGREGATE_BY`. The anchor is: start-of-value at beginning of trimmed
line (indentation + value + whitespace + PARAM_NAME + optional comma/comment).
"""

import re
import logging
from pathlib import Path
from typing import Union, Dict

logger = logging.getLogger(__name__)

# Minimum file size (bytes) for a real mini-check script.
# Scripts below this are likely stubs and will trigger a warning.
_MIN_REAL_SCRIPT_SIZE = 5 * 1024  # 5 KB


def validate_script_file(file_path: str) -> list:
    """Validate a mini-check script file, returning warnings (empty = OK).

    Checks:
      - File size >= 5 KB (real scripts are typically 10-50+ KB)
      - Contains a Modification Section marker
    """
    warnings = []
    p = Path(file_path)
    if not p.exists():
        return [f"File does not exist: {file_path}"]

    size = p.stat().st_size
    if size < _MIN_REAL_SCRIPT_SIZE:
        warnings.append(
            f"Script '{p.name}' is suspiciously small ({size} bytes, "
            f"expected >= {_MIN_REAL_SCRIPT_SIZE}). It may be a stub, "
            f"not the real SAP mini-check. Real scripts are typically 10-50+ KB."
        )

    content = p.read_text(encoding="utf-8", errors="replace")
    if "Modification section" not in content and "Modification Section" not in content:
        warnings.append(
            f"Script '{p.name}' does not contain a 'Modification section' marker. "
            f"It may be incomplete or fabricated."
        )

    return warnings


def _find_modification_section(sql: str) -> tuple:
    """Find the start and end offsets of the Modification Section block.

    Returns (start, end) character offsets of the SELECT...FROM DUMMY block
    that contains the '/* Modification section */' comment.
    Returns (0, len(sql)) if not found (fall back to whole file).
    """
    # Find the modification section comment
    mod_match = re.search(
        r'/\*\s*Modification\s+[Ss]ection\s*\*/',
        sql
    )
    if not mod_match:
        # Fall back: try to find SELECT ... FROM DUMMY pattern
        return 0, len(sql)

    # Walk backward from the comment to find the preceding SELECT
    # (the Modification Section is always inside a SELECT ... FROM DUMMY)
    pos = mod_match.start()
    # Find the FROM DUMMY that closes this section
    from_dummy = re.search(r'\bFROM\s+DUMMY\b', sql[pos:])
    if from_dummy:
        end = pos + from_dummy.end()
    else:
        end = len(sql)

    # The SELECT keyword precedes the comment — find it
    # Look backward for SELECT (within a reasonable range)
    lookback = sql[max(0, pos - 200):pos]
    select_match = list(re.finditer(r'\bSELECT\b', lookback, re.IGNORECASE))
    if select_match:
        start = max(0, pos - 200) + select_match[-1].start()
    else:
        start = pos

    return start, end


def patch_param(sql: str, param_name: str, new_value: Union[str, int, float]) -> str:
    """Patch a single parameter in the SQL Modification Section.

    Args:
        sql: Full SQL text from a mini-check script.
        param_name: The parameter alias to patch (e.g., 'RESULT_ROWS', 'SCHEMA_NAME').
        new_value: New value. Strings are quoted with single quotes. Numbers are bare.

    Returns:
        Patched SQL text.

    Raises:
        ValueError: If the parameter name is not found exactly once in the
                    Modification Section.
    """
    # Build the replacement value string
    if isinstance(new_value, str):
        escaped = new_value.replace("'", "''")
        value_str = f"'{escaped}'"
    elif isinstance(new_value, (int, float)):
        value_str = str(int(new_value)) if isinstance(new_value, int) else str(new_value)
    else:
        value_str = str(new_value)

    # Find the Modification Section boundaries
    mod_start, mod_end = _find_modification_section(sql)
    mod_section = sql[mod_start:mod_end]

    # Pattern: match lines like:
    #   '...' PARAM_NAME,      /* comment */
    #   -1 PARAM_NAME,
    #   'value' PARAM_NAME
    #
    # The key constraint: PARAM_NAME must be a standalone word at the alias
    # position (after whitespace following the value). We exclude lines where
    # PARAM_NAME appears as part of BI.PARAM_NAME or TIME_PARAM_NAME by
    # requiring the value to be at the start of the meaningful content
    # (after leading whitespace only).
    pattern = re.compile(
        r"^([ \t]+)"  # group 1: leading whitespace (indentation)
        r"("  # group 2: the old value
        r"'[^']*'"  # string literal
        r"|-?\d+(?:\.\d+)?"  # number (int or float, possibly negative)
        r"|[A-Z_][A-Z_0-9]*(?:\([^)]*\))?"  # identifier like CURRENT_TIMESTAMP
        r")"
        r"(\s+)"  # group 3: whitespace between value and alias
        + re.escape(param_name)
        + r"(?=\s*[,\s]|$)"  # followed by comma, whitespace, or end of line
        + r"(?![A-Z_0-9])",  # NOT followed by more identifier chars (excludes TIME_AGGREGATE_BY etc.)
        re.MULTILINE,
    )

    matches = list(pattern.finditer(mod_section))
    if len(matches) == 0:
        raise ValueError(
            f"Parameter '{param_name}' not found in Modification Section. "
            f"Available params in this script may differ from expected."
        )
    if len(matches) > 1:
        raise ValueError(
            f"Parameter '{param_name}' found {len(matches)} times in Modification "
            f"Section — expected exactly 1. Cannot safely patch."
        )

    match = matches[0]
    # Replace only the value part (group 2) within the modification section
    new_mod_section = (
        mod_section[:match.start(2)]
        + value_str
        + mod_section[match.end(2):]
    )
    return sql[:mod_start] + new_mod_section + sql[mod_end:]


def patch_params(sql: str, patches: Dict[str, Union[str, int, float]]) -> str:
    """Patch multiple parameters in sequence.

    Args:
        sql: Full SQL text.
        patches: Dict of {param_name: new_value}. Empty dict = no-op.

    Returns:
        Patched SQL text.
    """
    if not patches:
        return sql
    for param_name, new_value in patches.items():
        sql = patch_param(sql, param_name, new_value)
    return sql
