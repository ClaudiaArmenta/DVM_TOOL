"""Excel export for DVM Tool.

Exports analysis results to Excel workbooks.
Supports:
  - Full export (all analyses): DVM_tool.xlsx with one sheet per analysis.
  - Subset export (selected analyses): DVM_tool.xlsx with only selected sheets.
  - Per-analysis export: DVM_<analysis_id>.xlsx with that analysis' sheets.

A6 (NSE) always gets three sheets: NSE_Tables, NSE_Partitions, NSE_Columns.
"""

import io
from typing import Dict, List, Optional

import pandas as pd


# Sheet name mapping per analysis
_SHEET_MAP = {
    "a1_top_tables": ["A1_Top_by_Disk", "A1_Top_by_Memory"],
    "a2_db_size_history": ["A2_DB_Size_History"],
    "a3_memory_overview": ["A3_Memory_Overview"],
    "a4_top_growing": ["A4_Growth_Records", "A4_Growth_Disk", "A4_Growth_Memory"],
    "a5_partitioned_tables": ["A5_Partitioned_Tables"],
    "a6_nse": ["A6_NSE_Tables", "A6_NSE_Partitions", "A6_NSE_Columns"],
}


def export_to_excel(
    all_results: Dict[str, List[dict]],
    analysis_ids: Optional[List[str]] = None,
) -> bytes:
    """Export analysis results to an Excel workbook (bytes).

    Args:
        all_results: dict mapping analysis_id -> list of QueryResult-like dicts,
                     each with 'df', 'success', 'label' keys.
        analysis_ids: optional list of analysis IDs to include. If None, includes all.

    Returns:
        Bytes of the .xlsx file.
    """
    output = io.BytesIO()

    # Determine which analyses to include
    if analysis_ids is None:
        target_ids = list(_SHEET_MAP.keys())
    else:
        target_ids = [aid for aid in analysis_ids if aid in _SHEET_MAP]

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        sheets_written = 0
        for analysis_id in target_ids:
            sheet_names = _SHEET_MAP.get(analysis_id, [])
            results = all_results.get(analysis_id, [])
            for i, sheet_name in enumerate(sheet_names):
                if i < len(results) and results[i].get("success") and results[i].get("df") is not None:
                    df = results[i]["df"]
                    safe_name = sheet_name[:31]
                    df.to_excel(writer, sheet_name=safe_name, index=False)
                    sheets_written += 1
                else:
                    error_msg = "No data"
                    if i < len(results):
                        error_msg = results[i].get("error", "No data")
                    empty_df = pd.DataFrame({"Status": [error_msg]})
                    safe_name = sheet_name[:31]
                    empty_df.to_excel(writer, sheet_name=safe_name, index=False)
                    sheets_written += 1

        # Ensure at least one sheet
        if sheets_written == 0:
            pd.DataFrame({"Status": ["No results available"]}).to_excel(
                writer, sheet_name="Info", index=False)

    return output.getvalue()


def export_single_analysis(
    analysis_id: str,
    results: List[dict],
) -> bytes:
    """Export a single analysis to its own Excel file.

    Args:
        analysis_id: the analysis ID (e.g. 'a1_top_tables')
        results: list of QueryResult-like dicts for that analysis

    Returns:
        Bytes of the .xlsx file.
    """
    return export_to_excel({analysis_id: results}, analysis_ids=[analysis_id])
