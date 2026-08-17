"""Reusable UI components for DVM Tool.

Provides styled tables (with column-header tooltips), badges, and collapsible elements
following the DVM design system.
"""

import uuid
from typing import Optional, Dict

import pandas as pd
from dash import html
import dash_bootstrap_components as dbc


# ===================================================================
# COLUMN DESCRIPTIONS (for header tooltips)
# ===================================================================

# Sourced from SAP Note 1969700 SQL Statement Collection script headers
# and general HANA column semantics.
COLUMN_DESCRIPTIONS: Dict[str, str] = {
    # A1: Top Tables
    "SCHEMA_NAME": "Database schema name",
    "TABLE_NAME": "Table name",
    "DDTEXT": "SAP Data Dictionary description of the table",
    "HOST": "HANA host name",
    "RECORD_COUNT": "Number of records (rows) in the table",
    "TABLE_MEM_GB": "Table memory consumption in GB (current in-memory size)",
    "TAB_MEM_GB": "Table memory consumption in GB",
    "DISK_SIZE_MB": "Table disk size in MB",
    "DISK_GB": "Table disk size in GB",
    "MEM_GB": "Table memory consumption in GB",
    "NSE_GB": "Native Storage Extension (warm data) size in GB",
    "TOTAL_DISK_GB": "Total disk footprint in GB (data + delta + LOB)",
    "CURRENT_MEM_GB": "Current in-memory size in GB",
    "PARTITIONING": "Partitioning specification (e.g. HASH 4, RANGE)",
    "PART_COUNT": "Number of partitions",
    "LOADED": "Column store load status (FULL, PARTIALLY, NO)",
    "TABLE_TYPE": "Table type (COLUMN, ROW)",
    "STORE": "Storage type (CS = Column Store, RS = Row Store)",
    "MIN_TABLE_DISK_SIZE_MB": "Minimum disk size filter threshold in MB",
    # A2: DB Size History
    "SNAPSHOT_TIME": "Timestamp of the resource measurement",
    "ALLOC_LIM_GB": "Global allocation limit in GB",
    "HANA_USED_GB": "Memory used by HANA processes in GB",
    "HANA_ALLOC_GB": "Memory allocated by HANA processes in GB",
    "CPU_PCT": "CPU utilization percentage",
    "SYS_CPU_PCT": "System (OS) CPU utilization percentage",
    "MEM_USED_PCT": "Memory utilization percentage",
    # A3: Memory Overview
    "CATEGORY": "Memory category or area",
    "SUBAREA": "Memory sub-area within a category",
    "DETAIL": "Detailed memory area description",
    "USED_GB": "Memory used in GB",
    "SIZE_GB": "Allocated memory size in GB",
    "EXCLUSIVE_SIZE_GB": "Exclusive (non-shared) memory size in GB",
    "COUNT": "Number of allocators or instances",
    "COMPONENT": "SAP component or heap allocator name",
    # A4: Top Growing Tables
    "GROWTH_MB": "Absolute growth in MB over the measured period",
    "GROWTH_PCT": "Growth percentage over the measured period",
    "GROWTH_RECORDS": "Number of new records over the period",
    "BEGIN_SIZE_MB": "Size at the beginning of the measurement period in MB",
    "END_SIZE_MB": "Size at the end of the measurement period in MB",
    "SPACE_LAYER": "Storage layer measured (DISK, CURMEM, TOTMEM)",
    "OBJECT_LEVEL": "Granularity level (TABLE or PARTITION)",
    # A5: Partitioned Tables
    "PARTITION_SPEC": "Partition specification string",
    "LEVEL_1_TYPE": "First-level partition type (HASH, RANGE, ROUNDROBIN)",
    "LEVEL_1_COUNT": "Number of first-level partitions",
    "LEVEL_2_TYPE": "Second-level partition type (if applicable)",
    "LEVEL_2_COUNT": "Number of second-level partitions",
    "TOTAL_PARTS": "Total number of partition segments",
    "MEM_SIZE_GB": "In-memory size of all partitions in GB",
    "DISK_SIZE_GB": "On-disk size of all partitions in GB",
    # A6: NSE
    "LOAD_UNIT": "Load unit (PAGE = NSE/warm, COLUMN = hot)",
    "PAGE_LOADABLE": "Whether the column/table is page-loadable (NSE)",
    "PERSISTENT_MEMORY_SIZE_IN_TOTAL": "Total persistent memory (NSE) in bytes",
    "BUFFER_SIZE": "Buffer cache size for page-loaded data",
    "NSE_DISK_SIZE_MB": "NSE on-disk size in MB",
    "NSE_BUFFER_MB": "NSE buffer cache consumption in MB",
    "PARTITION_ID": "Internal partition ID",
    # Generic / common
    "RESULT_ROWS": "Maximum number of result rows returned",
    "ORDER_BY": "Column used for ordering the results",
    "BEGIN_TIME": "Start of the measurement time window",
    "END_TIME": "End of the measurement time window",
    "TIME_AGGREGATE_BY": "Time aggregation granularity",
    "AGGREGATE_BY": "Grouping/aggregation criterion",
}


def _get_col_tooltip(col_name: str) -> str:
    """Get tooltip text for a column header."""
    upper = col_name.upper().strip()
    if upper in COLUMN_DESCRIPTIONS:
        return COLUMN_DESCRIPTIONS[upper]
    # Try partial matches for common patterns
    if "GB" in upper and "SIZE" in upper:
        return f"Size in GB ({col_name})"
    if "MB" in upper and "SIZE" in upper:
        return f"Size in MB ({col_name})"
    if "PCT" in upper or "PERCENT" in upper:
        return f"Percentage value ({col_name})"
    if "COUNT" in upper:
        return f"Count ({col_name})"
    if "TIME" in upper or "TIMESTAMP" in upper:
        return f"Timestamp ({col_name})"
    return col_name


# ===================================================================
# TABLE COMPONENT
# ===================================================================

_OUTPUT_PARAMS_CACHE: dict = {}


def parse_output_params(sql: Optional[str]) -> dict:
    """Extract column definitions from a SQL Statement Collection script.

    The scripts document their result columns in an ``[OUTPUT PARAMETERS]``
    header section, one per line as ``- COLUMN:  description`` (descriptions may
    wrap onto continuation lines). Returns {COLUMN_UPPER: description}.
    """
    if not sql:
        return {}
    key = hash(sql)
    cached = _OUTPUT_PARAMS_CACHE.get(key)
    if cached is not None:
        return cached

    import re
    defs: dict = {}
    m = re.search(r"\[OUTPUT PARAMETERS\](.*?)(?:\n[ \t]*\[[A-Z]|\*/)", sql, re.S)
    if m:
        current = None
        for line in m.group(1).splitlines():
            hit = re.match(r"^\s*-\s*([A-Za-z0-9_]+)\s*:\s*(.*)$", line)
            if hit:
                current = hit.group(1).upper().strip()
                defs[current] = hit.group(2).strip()
            elif current and line.strip():
                defs[current] = (defs[current] + " " + line.strip()).strip()

    _OUTPUT_PARAMS_CACHE[key] = defs
    return defs


def results_table(
    df: Optional[pd.DataFrame],
    max_rows: int = 100,
    max_col_width: str = "300px",
    name: Optional[str] = None,
    sql: Optional[str] = None,
) -> html.Div:
    """Render a pandas DataFrame as a professional styled HTML table.

    Column headers show a tooltip (title attribute) with their description —
    taken from the related SQL's ``[OUTPUT PARAMETERS]`` when ``sql`` is given,
    otherwise a heuristic label. Each table carries a Copy / CSV / Excel toolbar
    handled client-side by assets/table-tools.js (exports only the rows shown).
    ``name`` sets the download filename.
    """
    col_defs = parse_output_params(sql)
    if df is None or df.empty:
        return html.Div(
            [
                html.I(className="bi bi-inbox",
                       style={"fontSize": "20px", "color": "var(--dvm-border)"}),
                html.P("No rows returned.",
                       style={"fontSize": "13px", "color": "var(--dvm-text-secondary)",
                              "margin": "6px 0 0"}),
            ],
            className="dvm-empty-state",
        )

    display_df = df.head(max_rows)
    truncated = len(df) > max_rows

    # Detect numeric columns for right-alignment
    numeric_cols = set()
    for col in display_df.columns:
        if display_df[col].dtype.kind in ("i", "f", "u"):
            numeric_cols.add(col)

    header = html.Thead(
        html.Tr(
            [
                html.Th(
                    html.Span(
                        col,
                        title=(col_defs.get(str(col).upper().strip())
                               or _get_col_tooltip(col)),
                        className="dvm-th-text",
                    ),
                    className="dvm-table-th" + (" dvm-table-num" if col in numeric_cols else ""),
                )
                for col in display_df.columns
            ]
        ),
        className="dvm-table-header",
    )

    rows = []
    for idx, (_, row) in enumerate(display_df.iterrows()):
        cells = []
        for col_name, val in zip(display_df.columns, row):
            cell_val = _format_cell(val, col_name in numeric_cols)
            cells.append(
                html.Td(
                    cell_val,
                    className="dvm-table-td" + (" dvm-table-num" if col_name in numeric_cols else ""),
                    title=str(val) if val is not None else "",
                )
            )
        row_class = "dvm-table-row-even" if idx % 2 == 0 else "dvm-table-row-odd"
        rows.append(html.Tr(cells, className=row_class))

    body = html.Tbody(rows)
    table = html.Table([header, body], className="dvm-table")

    caption = html.Div(
        f"{len(display_df)}" + (f" of {len(df)}" if truncated else "") + " rows",
        className="dvm-table-caption",
    )

    # Per-table Copy / CSV toolbar (handled client-side by table-tools.js).
    toolbar = html.Div(
        [
            html.Button(
                [html.I(className="bi bi-clipboard"),
                 html.Span("Copy", **{"data-i18n": "table.copy"})],
                type="button", className="dvm-table-btn",
                title="Copy this table to clipboard",
                **{"data-table-copy": "1", "data-i18n-title": "table.copyTitle"},
            ),
            html.Button(
                [html.I(className="bi bi-filetype-csv"),
                 html.Span("CSV", **{"data-i18n": "table.csv"})],
                type="button", className="dvm-table-btn",
                title="Download this table as CSV",
                **{"data-table-export": "1", "data-table-name": (name or "table"),
                   "data-i18n-title": "table.csvTitle"},
            ),
            html.Button(
                [html.I(className="bi bi-file-earmark-excel"),
                 html.Span("Excel", **{"data-i18n": "table.excel"})],
                type="button", className="dvm-table-btn",
                title="Download this table as Excel",
                **{"data-table-export-xls": "1", "data-table-name": (name or "table"),
                   "data-i18n-title": "table.excelTitle"},
            ),
        ],
        className="dvm-table-toolbar",
    )

    return html.Div(
        [
            toolbar,
            html.Div(table, className="dvm-table-scroll"),
            caption,
        ],
        className="dvm-table-container",
    )


def top_rows_control(options=(10, 20, 30, 50), default=50) -> html.Div:
    """'Show top N' pills that filter the table right after them (client-side,
    handled by assets/table-tools.js). Wrap the control + results_table in a
    div with class 'dvm-topn-wrap'."""
    return html.Div(
        [
            html.Span("Show top:", className="dvm-topn-label",
                      **{"data-i18n": "table.showTop"}),
            html.Div(
                [html.Button(str(n), type="button",
                             className="dvm-tab-pill" + (" active" if n == default else ""),
                             **{"data-toprows": str(n)})
                 for n in options],
                className="dvm-tab-pills",
            ),
        ],
        className="dvm-topn",
    )


def _format_cell(val, is_numeric: bool) -> str:
    """Format a cell value for display."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    if is_numeric:
        if isinstance(val, float):
            if abs(val) >= 1000:
                return f"{val:,.1f}"
            return f"{val:.2f}"
        elif isinstance(val, int):
            return f"{val:,}"
    return str(val)


# ===================================================================
# BADGES AND UTILITIES
# ===================================================================

def status_badge(success: bool, text: str = "") -> html.Span:
    """Render a success/failure badge."""
    if success:
        cls = "dvm-badge dvm-badge-success"
        icon = "bi-check-circle-fill"
        default_text = "OK"
    else:
        cls = "dvm-badge dvm-badge-error"
        icon = "bi-x-circle-fill"
        default_text = "FAILED"

    return html.Span(
        [html.I(className=f"bi {icon} me-1"), text or default_text],
        className=cls,
    )


def elapsed_badge(ms: float) -> html.Span:
    """Render an elapsed time badge."""
    display = f"{ms:.0f} ms" if ms < 1000 else f"{ms / 1000:.1f} s"
    return html.Span(
        [html.I(className="bi bi-clock me-1"), display],
        className="dvm-badge dvm-badge-neutral",
    )


def row_col_badge(rows: int, cols: int) -> html.Span:
    """Render a row/column count badge."""
    return html.Span(
        f"{rows:,} rows \u00d7 {cols} cols",
        className="dvm-badge dvm-badge-info",
    )


def collapsible_sql(sql: str, step_id: str = "") -> html.Div:
    """Render a collapsible SQL code block."""
    if not sql:
        return html.Div()

    display_sql = sql if len(sql) <= 3000 else sql[:3000] + "\n... (truncated)"

    return html.Div(
        html.Details(
            [
                html.Summary("Show SQL", className="dvm-sql-toggle"),
                html.Pre(
                    html.Code(display_sql),
                    className="dvm-code-readonly",
                ),
            ],
        ),
        style={"marginTop": "8px"},
    )


def error_display(error: str, exception_text: str = "") -> html.Div:
    """Render an error message with optional raw exception."""
    if not error:
        return html.Div()

    children = [
        html.Div(
            [html.I(className="bi bi-exclamation-triangle me-2"),
             html.Span(error)],
            className="dvm-error-card",
        ),
    ]

    if exception_text:
        children.append(
            html.Details(
                [
                    html.Summary("Raw Exception",
                                 style={"fontSize": "11px", "color": "var(--dvm-text-secondary)",
                                        "cursor": "pointer", "marginTop": "6px"}),
                    html.Pre(exception_text, className="dvm-code-readonly",
                             style={"fontSize": "10px", "maxHeight": "150px"}),
                ],
            )
        )

    return html.Div(children, style={"marginBottom": "12px"})
