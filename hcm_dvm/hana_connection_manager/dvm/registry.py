"""Analysis registry for DVM Tool.

Provides the canonical list of analyses with metadata used by:
  - layout.py (analysis cards, tabs)
  - dvm_analyses.py (execution orchestration)
  - renderers.py (result rendering)

Each analysis spec:
  - id: unique key (e.g. 'a1_top_tables')
  - title: display title
  - description: short description
  - icon: Bootstrap icon class
  - group: grouping key
  - queries: list of query dicts, each with:
      - label: display name for the query
      - script_base: base filename for select_variant() (A1-A5)
      - patches: dict of Modification Section param overrides
      - sql_authored + sql_key: for A6 NSE (no file-based)
  - enrichments (optional): list of enrichment specs run post-query
  - renderer: renderer function name

Modification Section params used by the real scripts:
  - ORDER_BY: ordering criterion (e.g. 'TOTAL_DISK', 'CURRENT_MEM')
  - RESULT_ROWS: max rows returned
  - MIN_TABLE_DISK_SIZE_MB: minimum disk threshold
  - BEGIN_TIME: time window start (e.g. 'C-D30' = current - 30 days)
  - END_TIME: time window end (e.g. 'C' = current)
  - TIME_AGGREGATE_BY: time aggregation granularity
  - AGGREGATE_BY: grouping criterion
  - OBJECT_LEVEL: TABLE or PARTITION
  - SPACE_LAYER: DISK, CURMEM, TOTMEM
"""

from typing import Dict, List

# Ordered list of analysis specifications
ANALYSIS_SPECS: List[Dict] = [
    {
        "id": "a1_top_tables",
        "title": "A1: Top Tables by Size",
        "description": "Largest tables by disk and memory (SAP Note 1969700), enriched with table descriptions.",
        "icon": "bi-hdd-stack",
        "group": "sizing",
        "queries": [
            {
                "label": "Top Tables by Disk",
                "script_base": "HANA_Tables_LargestTables_ABAP",
                "patches": {
                    "ORDER_BY": "TOTAL_DISK",
                    "RESULT_ROWS": 50,
                    "MIN_TABLE_DISK_SIZE_MB": -1,
                },
            },
            {
                "label": "Top Tables by Memory",
                "script_base": "HANA_Tables_LargestTables_ABAP",
                "patches": {
                    "ORDER_BY": "CURRENT_MEM",
                    "RESULT_ROWS": 50,
                    "MIN_TABLE_DISK_SIZE_MB": -1,
                },
            },
        ],
        "enrichments": [
            {
                "type": "table_description",
                "script_file": "SQLStatements_table_description.sql",
                "join_keys": ["SCHEMA_NAME", "TABLE_NAME"],
                "columns": ["DDTEXT", "DISK_GB", "NSE_GB", "MEM_GB", "PARTITIONING", "PART_COUNT"],
            },
        ],
        "renderer": "render_a1",
    },
    {
        "id": "a2_db_size_history",
        "title": "A2: DB Size & Memory History",
        "description": ("Memory and disk size from the DBACOCKPIT DB Size "
                        "History screen, last year grouped by month."),
        "icon": "bi-graph-up",
        "group": "sizing",
        "queries": [
            {
                # Read straight from the DBACOCKPIT screen
                # System Information > DB Size History (NO SQL). Columns come
                # from that grid (Date / Memory / Disk Data / Disk Log / Disk
                # Trace). render_a2 rolls the rows up to one point per month for
                # the last year and feeds both the chart and the table.
                "label": "DB Size History (DBACOCKPIT screen)",
                "gui_screen": "db_size_history",
            },
        ],
        "renderer": "render_a2",
    },
    {
        "id": "a3_memory_overview",
        "title": "A3: Memory Overview",
        "description": "Memory resource consumption by subarea.",
        "icon": "bi-memory",
        "group": "memory",
        "queries": [
            {
                "label": "Memory Top Consumers",
                "script_base": "HANA_Memory_TopConsumers",
                "patches": {"AGGREGATE_BY": "SUBAREA"},
            },
        ],
        "renderer": "render_a3",
    },
    {
        "id": "a4_top_growing",
        "title": "A4: Top Growing Tables (30d)",
        "description": "Tables with highest growth in records, disk, and memory over 30 days.",
        "icon": "bi-arrow-up-right-circle",
        "group": "sizing",
        "queries": [
            {
                "label": "Growth by Records (30d)",
                "script_base": "HANA_Tables_TopGrowingTables_Records_History",
                "patches": {
                    "BEGIN_TIME": "C-D30",
                    "OBJECT_LEVEL": "TABLE",
                    "RESULT_ROWS": 30,
                },
            },
            {
                "label": "Growth by Disk (30d)",
                "script_base": "HANA_Tables_TopGrowingTables_Size_History",
                "patches": {
                    "BEGIN_TIME": "C-D30",
                    "SPACE_LAYER": "DISK",
                    "RESULT_ROWS": 30,
                },
            },
            {
                "label": "Growth by Memory (30d)",
                "script_base": "HANA_Tables_TopGrowingTables_Size_History",
                "patches": {
                    "BEGIN_TIME": "C-D30",
                    "SPACE_LAYER": "CURMEM",
                    "RESULT_ROWS": 30,
                },
            },
        ],
        "renderer": "render_a4",
    },
    {
        "id": "a5_partitioned_tables",
        "title": "A5: Partitioned Tables",
        "description": "Column-store partitioned tables overview.",
        "icon": "bi-grid-3x3",
        "group": "structure",
        "queries": [
            {
                "label": "Partitioned CS Tables",
                "script_base": "HANA_Tables_ColumnStore_PartitionedTables",
                "patches": {},
            },
        ],
        "renderer": "render_a5",
    },
    {
        "id": "a6_nse",
        "title": "A6: NSE (Native Storage Extension)",
        "description": "Page-loadable (NSE) tables, partitions, and columns.",
        "icon": "bi-layers",
        "group": "nse",
        "queries": [
            {
                "label": "NSE Tables",
                "sql_authored": True,
                "sql_key": "nse_tables",
            },
            {
                "label": "NSE Partitions",
                "sql_authored": True,
                "sql_key": "nse_partitions",
            },
            {
                "label": "NSE Columns",
                "sql_authored": True,
                "sql_key": "nse_columns",
            },
        ],
        "renderer": "render_a6",
    },
]


def get_all_analyses() -> List[Dict]:
    """Return the ordered list of enabled analysis specs.

    Specs with ``"enabled": False`` (e.g. A6 NSE, a work in progress) are
    hidden from the UI and execution while remaining defined for later.
    """
    return [spec for spec in ANALYSIS_SPECS if spec.get("enabled", True)]


def get_analysis_by_id(analysis_id: str) -> Dict:
    """Lookup a single analysis by ID."""
    for spec in ANALYSIS_SPECS:
        if spec["id"] == analysis_id:
            return spec
    raise KeyError(f"Unknown analysis: {analysis_id}")
