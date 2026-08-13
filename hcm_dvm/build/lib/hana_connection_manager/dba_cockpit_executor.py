"""DBACOCKPIT SQL Executor via SAP GUI Scripting.

Session-parameterized executor: takes an SAP GUI session object and operates
on it. Separates open_dbacockpit() (called once per session) from execute()
(called per query, reuses the open DBACOCKPIT).

Design:
  - open_dbacockpit(): runs /nDBACOCKPIT, navigates tree to SQL Editor
  - execute(sql): inserts SQL via .text, presses F8, reads results from grid
  - After F8: waits ~1s for status bar to settle, checks for HANA errors
  - Direct grid read descends to real nested GuiGridView (validates Type)
  - If 0 rows returned, re-checks status bar for masked errors
  - Export path also available but E_INVALIDARG falls back to direct grid

Requires:
  - Active SAP GUI session with scripting enabled
  - DBACOCKPIT transaction authorization
  - pywin32 package (for COM interop on Windows)
"""

import io
import time
import logging
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Any, List

import pandas as pd

from .logger import get_logger

logger = get_logger("dba_cockpit")


class DBACockpitExecutionError(Exception):
    """Raised when DBACOCKPIT SQL execution fails."""
    pass


@dataclass
class DBACockpitConfig:
    """Configuration for DBACOCKPIT executor."""

    export_dir: str = "C:/temp"
    wait_seconds: float = 1.0
    sql_exec_wait: float = 10.0
    export_wait: float = 5.0
    file_unlock_timeout: int = 15
    sid: str = ""
    label: str = "EXPORT"


class DBACockpitSQLExecutor:
    """Execute SQL via DBACOCKPIT transaction in SAP GUI.

    Lifecycle per session:
      1. open_dbacockpit() — run /nDBACOCKPIT, navigate to SQL Editor (once)
      2. execute(sql) — insert SQL, F8, read grid (repeatable)

    The executor reuses the open DBACOCKPIT across multiple queries on the same
    session, avoiding the overhead of re-navigating the tree each time.
    """

    def __init__(self, session: Any, cfg: Optional[DBACockpitConfig] = None):
        """Initialize executor.

        Args:
            session: Active SAP GUI COM session object.
            cfg: Configuration options. Uses defaults if None.
        """
        self.s = session
        self.cfg = cfg or DBACockpitConfig()
        self._dbacockpit_open = False

    def _wait(self, seconds: Optional[float] = None):
        """Wait for SAP GUI processing."""
        time.sleep(seconds or self.cfg.wait_seconds)

    # ══════════════════════════════════════════════════════════════
    # PUBLIC API
    # ══════════════════════════════════════════════════════════════

    def open_dbacockpit(self):
        """Open /nDBACOCKPIT in this session and navigate to SQL Editor.

        Call this ONCE per session. Subsequent execute() calls reuse the
        already-open SQL Editor.
        """
        s = self.s
        logger.info("  Opening /nDBACOCKPIT")
        s.findById("wnd[0]/tbar[0]/okcd").text = "/ndbacockpit"
        s.findById("wnd[0]").sendVKey(0)
        self._wait(3)

        # Navigate tree to SQL Editor
        logger.info("  Navigating tree to SQL Editor")
        tree = self._find_tree()
        self._navigate_tree_to_sql_editor(tree)
        self._dbacockpit_open = True
        logger.info("  DBACOCKPIT SQL Editor ready")

    def execute(self, sql: str) -> pd.DataFrame:
        """Execute SQL in the already-open DBACOCKPIT and return results.

        If DBACOCKPIT is not yet open, opens it first.

        Args:
            sql: SQL query string.

        Returns:
            DataFrame with query results.

        Raises:
            DBACockpitExecutionError: On SQL error or read failure.
        """
        if not self._dbacockpit_open:
            self.open_dbacockpit()

        s = self.s

        try:
            # ── 1. Switch to INPUT tab and insert SQL ──
            self._switch_to_input_tab()
            editor = self._find_sql_editor()
            editor.text = sql
            self._wait(0.5)

            # ── 2. Set Max.No. of Rows ──
            self._find_max_rows_field()

            # ── 3. Execute (F8) ──
            logger.info("  Executing SQL (F8)")
            s.findById("wnd[0]/tbar[1]/btn[8]").press()

            # ── 4. Wait ~1s for status bar to settle ──
            self._wait(1.0)

            # ── 5. Check for HANA error in status bar ──
            error_text = self._check_status_bar_error()
            if error_text:
                raise DBACockpitExecutionError(f"HANA SQL error: {error_text}")

            # ── 6. Poll for result grid ──
            grid = self._poll_for_grid()

            # ── 7. Read results from grid ──
            df = self._read_grid_direct(grid)

            # ── 8. If 0 rows, re-check status bar for masked error ──
            if df.empty:
                self._wait(0.5)
                error_text_2 = self._check_status_bar_error()
                if error_text_2:
                    raise DBACockpitExecutionError(
                        f"HANA SQL error (masked as empty result): {error_text_2}"
                    )

            logger.info(f"  Query complete: {df.shape[0]} rows, {df.shape[1]} cols")
            return df

        except DBACockpitExecutionError:
            raise
        except Exception as e:
            logger.error(f"  Execution failed: {type(e).__name__}: {e}")
            raise DBACockpitExecutionError(
                f"DBACOCKPIT execution failed: {type(e).__name__}: {e}"
            )

    # ══════════════════════════════════════════════════════════════
    # INTERNAL: Tree Navigation
    # ══════════════════════════════════════════════════════════════

    def _find_control(self, *id_paths):
        """Try multiple control IDs, return the first found or raise."""
        s = self.s
        errors = []
        for path in id_paths:
            try:
                ctrl = s.findById(path)
                if ctrl:
                    return ctrl
            except Exception as e:
                errors.append(f"{path} -> {e}")
                continue
        raise DBACockpitExecutionError(
            f"Could not find control. Tried:\n  " + "\n  ".join(errors)
        )

    def _find_tree(self):
        """Find the DBACOCKPIT navigation tree control."""
        tree_paths = [
            "wnd[0]/shellcont[1]/shell/shellcont[1]/shell",
            "wnd[0]/usr/shellcont/shell/shellcont[1]/shell",
            "wnd[0]/shellcont/shell/shellcont[1]/shell",
            "wnd[0]/usr/shellcont[1]/shell/shellcont[1]/shell",
        ]
        return self._find_control(*tree_paths)

    def _navigate_tree_to_sql_editor(self, tree):
        """Navigate the DBA Cockpit tree to SQL Editor.

        Strategies:
          1. Try common node IDs for Performance
          2. Enumerate nodes by text
          3. Try SQL Editor node IDs
          4. Enumerate for 'SQL Editor'
        """
        perf_nodes = [
            "       1004-", "      1004-", "     1004-", "1004-",
            "       1003-", "      1003-", "       1005-",
        ]
        sql_editor_nodes = [
            ("        106", "Task"), ("       106", "Task"),
            ("      106", "Task"), ("106", "Task"),
            ("        107", "Task"), ("       107", "Task"),
            ("        105", "Task"), ("       105", "Task"),
        ]

        # Try expanding Performance node
        perf_opened = False
        for node_id in perf_nodes:
            try:
                tree.selectedNode = node_id
                tree.doubleClickNode(node_id)
                self._wait(1.5)
                perf_opened = True
                logger.info(f"  Opened Performance node: '{node_id}'")
                break
            except Exception:
                continue

        if not perf_opened:
            logger.info("  Finding Performance node by enumeration")
            try:
                node_keys = self._get_all_node_keys(tree)
                for nk in node_keys:
                    try:
                        text = tree.getNodeTextByKey(nk)
                        if "erform" in text or "ERFORM" in text:
                            tree.selectedNode = nk
                            tree.doubleClickNode(nk)
                            self._wait(1.5)
                            perf_opened = True
                            break
                    except Exception:
                        continue
            except Exception:
                pass

        if not perf_opened:
            raise DBACockpitExecutionError(
                "Cannot find 'Performance' node in DBACOCKPIT tree."
            )

        # Try clicking SQL Editor node
        sql_found = False
        for node_id, column in sql_editor_nodes:
            try:
                tree.selectItem(node_id, column)
                tree.doubleClickItem(node_id, column)
                self._wait(3)
                sql_found = True
                logger.info(f"  Opened SQL Editor node: '{node_id}'")
                break
            except Exception:
                continue

        if not sql_found:
            logger.info("  Finding SQL Editor node by enumeration")
            try:
                node_keys = self._get_all_node_keys(tree)
                for nk in node_keys:
                    try:
                        text = tree.getNodeTextByKey(nk)
                        if "SQL" in text.upper() and "EDITOR" in text.upper():
                            tree.selectItem(nk, "Task")
                            tree.doubleClickItem(nk, "Task")
                            self._wait(3)
                            sql_found = True
                            break
                    except Exception:
                        continue
            except Exception:
                pass

        if not sql_found:
            raise DBACockpitExecutionError(
                "Cannot find 'SQL Editor' node in DBACOCKPIT tree."
            )

    def _get_all_node_keys(self, tree) -> List[str]:
        """Get all node keys from the tree control."""
        keys = []
        try:
            top_key = tree.getNodeKeyByPath("1")
            keys.append(top_key)
            queue = [top_key]
            for _ in range(200):
                if not queue:
                    break
                current = queue.pop(0)
                try:
                    child_key = tree.getNodeFirstChildKey(current)
                    if child_key:
                        keys.append(child_key)
                        queue.append(child_key)
                except Exception:
                    pass
                try:
                    next_key = tree.getNodeNextSiblingKey(current)
                    if next_key:
                        keys.append(next_key)
                        queue.append(next_key)
                except Exception:
                    pass
        except Exception:
            for i in range(1, 300):
                for fmt in [f"       {i}-", f"      {i}-", f"     {i}-",
                            f"    {i}-", f"   {i}-", f"  {i}-", f" {i}-", f"{i}-",
                            f"        {i}", f"       {i}", f"      {i}", f"{i}"]:
                    keys.append(fmt)
        return keys

    # ══════════════════════════════════════════════════════════════
    # INTERNAL: SQL Editor
    # ══════════════════════════════════════════════════════════════

    def _switch_to_input_tab(self):
        """Switch to the INPUT tab in DBACOCKPIT SQL Editor."""
        s = self.s
        input_tab_paths = [
            "wnd[0]/usr/tabsSQL/tabpINPUT",
        ]
        for path in input_tab_paths:
            try:
                tab = s.findById(path)
                tab.select()
                self._wait(0.3)
                return
            except Exception:
                continue
        # May already be on INPUT tab — not critical

    def _find_sql_editor(self):
        """Find the SQL input editor control."""
        editor_paths = [
            "wnd[0]/usr/tabsSQL/tabpINPUT/"
            "ssubINPUT_REF1:SAPLSHDBCCMS:0109/"
            "cntlSQL_INPUT_CONT_HDB/shellcont/shell",
            "wnd[0]/usr/tabsSQL/tabpINPUT/"
            "ssubINPUT_REF1:SAPLSHDBCCMS:0109/"
            "cntlSQL_INPUT_CONT/shellcont/shell",
            "wnd[0]/usr/tabsSQL/tabpINPUT/"
            "ssubINPUT_REF1:SAPLDBACOCKPIT_SQL:0109/"
            "cntlSQL_INPUT_CONT_HDB/shellcont/shell",
            "wnd[0]/usr/tabsSQL/tabpINPUT/"
            "ssubINPUT_REF1:SAPLDBACOCKPIT_SQL:0109/"
            "cntlSQL_INPUT_CONT/shellcont/shell",
        ]
        return self._find_control(*editor_paths)

    def _find_max_rows_field(self):
        """Find and set the Max Rows field (best effort)."""
        s = self.s
        row_paths = [
            "wnd[0]/usr/txtDYN_VIEW_SQL-ROW_MAX",
            "wnd[0]/usr/txtMAX_ROWS",
            "wnd[0]/usr/tabsSQL/tabpINPUT/ssubINPUT_REF1:SAPLSHDBCCMS:0109/txtDYN_VIEW_SQL-ROW_MAX",
        ]
        for path in row_paths:
            try:
                field = s.findById(path)
                field.text = "9999999"
                return
            except Exception:
                continue

    # ══════════════════════════════════════════════════════════════
    # INTERNAL: Error Detection
    # ══════════════════════════════════════════════════════════════

    def _check_status_bar_error(self) -> Optional[str]:
        """Check SAP GUI status bar for SQL execution errors.

        Returns error text if detected, None otherwise.
        Reads wnd[0]/sbar — checks MessageType == 'E' or known HANA error
        patterns in the text.
        """
        s = self.s
        status_bar_paths = [
            "wnd[0]/sbar",
            "wnd[0]/sbar/pane[0]",
        ]
        for path in status_bar_paths:
            try:
                sbar = s.findById(path)
                msg_type = getattr(sbar, "MessageType", "")
                text = getattr(sbar, "Text", "") or ""

                # Explicit error type
                if msg_type == "E" and text:
                    return text

                # Pattern-based detection for HANA errors
                if text and any(kw in text.lower() for kw in [
                    "invalid column", "invalid table", "sql error",
                    "not found", "syntax error", "insufficient privilege",
                    "not authorized", "column store error", "general error",
                    "feature not supported", "cannot use", "duplicate",
                ]):
                    return text
            except Exception:
                continue
        return None

    # ══════════════════════════════════════════════════════════════
    # INTERNAL: Result Grid
    # ══════════════════════════════════════════════════════════════

    def _poll_for_grid(self) -> Any:
        """Poll for the result grid to appear after F8.

        Does NOT have a "wait until RowCount > 0" gate — returns as soon as
        the grid control is found.
        """
        s = self.s
        _poll_start = time.time()
        _poll_interval = 2.0
        _max_wait = max(self.cfg.sql_exec_wait, 10.0)

        while True:
            # Check for late-arriving error
            _err = self._check_status_bar_error()
            if _err:
                raise DBACockpitExecutionError(f"HANA SQL error: {_err}")

            try:
                grid = self._find_result_grid()
                if grid is not None:
                    return grid
            except Exception:
                pass

            if time.time() - _poll_start >= _max_wait:
                # Final error check
                _err_final = self._check_status_bar_error()
                if _err_final:
                    raise DBACockpitExecutionError(f"HANA SQL error: {_err_final}")
                # Try one more time
                try:
                    return self._find_result_grid()
                except Exception:
                    raise DBACockpitExecutionError(
                        f"Result grid not found after {_max_wait:.0f}s timeout."
                    )
            self._wait(_poll_interval)

    def _find_result_grid(self):
        """Find the SQL output result grid control."""
        grid_paths = [
            "wnd[0]/usr/tabsSQL/tabpOUTPUT/"
            "ssubOUTPUT_REF1:SAPLSHDBCCMS:0110/"
            "cntlSQL_OUTPUT_CONT_HDB/shellcont/shell",
            "wnd[0]/usr/tabsSQL/tabpOUTPUT/"
            "ssubOUTPUT_REF1:SAPLSHDBCCMS:0110/"
            "cntlSQL_OUTPUT_CONT/shellcont/shell",
            "wnd[0]/usr/tabsSQL/tabpOUTPUT/"
            "ssubOUTPUT_REF1:SAPLDBACOCKPIT_SQL:0110/"
            "cntlSQL_OUTPUT_CONT_HDB/shellcont/shell",
            "wnd[0]/usr/tabsSQL/tabpOUTPUT/"
            "ssubOUTPUT_REF1:SAPLDBACOCKPIT_SQL:0110/"
            "cntlSQL_OUTPUT_CONT/shellcont/shell",
        ]
        return self._find_control(*grid_paths)

    def _read_grid_direct(self, grid) -> pd.DataFrame:
        """Read result grid directly via GetCellValue.

        Descends to the real nested GuiGridView that holds data:
          - Validates .Type (GuiGridView, GuiALVGridControl, GuiShell)
          - If the first container reports RowCount == 0, looks for child grids
          - Reads ColumnOrder for column IDs
          - Pulls cells with GetCellValue(row, col_id)
        """
        logger.info("  Reading grid directly")

        # Descend to the real GuiGridView
        real_grid = self._descend_to_real_grid(grid)

        # Validate grid type
        grid_type = getattr(real_grid, "Type", "unknown")
        grid_subtype = getattr(real_grid, "SubType", "")
        logger.info(f"  Grid Type={grid_type}, SubType={grid_subtype}")

        # Get column IDs from ColumnOrder
        columns = self._get_grid_columns(real_grid)
        if not columns:
            return pd.DataFrame()

        # Get row count
        try:
            row_count = real_grid.RowCount
        except Exception as e:
            raise DBACockpitExecutionError(f"Cannot read grid RowCount: {e}")

        if row_count == 0:
            logger.info("  Grid RowCount = 0")
            clean_cols = [c.upper().strip().replace(" ", "_") for c in columns]
            return pd.DataFrame(columns=clean_cols)

        # Read cells — cap at 50000 rows
        max_rows = min(row_count, 50000)
        logger.info(f"  Reading {max_rows} rows x {len(columns)} cols")
        data = []
        for row_idx in range(max_rows):
            row_data = []
            for col_id in columns:
                try:
                    val = real_grid.GetCellValue(row_idx, col_id)
                    row_data.append(val)
                except Exception:
                    row_data.append("")
            data.append(row_data)

        clean_cols = [c.upper().strip().replace(" ", "_") for c in columns]
        df = pd.DataFrame(data, columns=clean_cols)
        logger.info(f"  Grid read complete: {df.shape[0]} rows")
        return df

    def _descend_to_real_grid(self, grid) -> Any:
        """Descend into nested containers to find the real GuiGridView with data.

        The DBACOCKPIT result may wrap the grid in GuiContainerShell or similar.
        We need the actual grid with ColumnOrder and GetCellValue.
        """
        real_grid = grid

        # Check if this is a container wrapping the real grid
        try:
            grid_type = getattr(grid, "Type", "")

            # If it's already a grid view, check if it has data
            if "Grid" in grid_type:
                try:
                    row_count = grid.RowCount
                    if row_count > 0:
                        return grid
                except Exception:
                    pass

            # Try to find children that are grids
            if hasattr(grid, "Children"):
                try:
                    child_count = grid.Children.Count
                    for i in range(child_count):
                        child = grid.Children(i)
                        child_type = getattr(child, "Type", "")
                        if "Grid" in child_type or "ALV" in child_type:
                            try:
                                rc = child.RowCount
                                if rc > 0:
                                    logger.info(f"  Found nested grid child[{i}] Type={child_type} rows={rc}")
                                    return child
                            except Exception:
                                pass
                    # If no child has rows, try the first grid child anyway
                    for i in range(child_count):
                        child = grid.Children(i)
                        child_type = getattr(child, "Type", "")
                        if "Grid" in child_type or "ALV" in child_type:
                            return child
                except Exception:
                    pass

            # Try SubNodes pattern
            if hasattr(grid, "SubNodes"):
                try:
                    for i in range(grid.SubNodes.Count):
                        sub = grid.SubNodes(i)
                        sub_type = getattr(sub, "Type", "")
                        if "Grid" in sub_type:
                            return sub
                except Exception:
                    pass

        except Exception:
            pass

        return real_grid

    def _get_grid_columns(self, grid) -> List[str]:
        """Get column IDs from a grid control."""
        # Primary: ColumnOrder property
        try:
            col_order = grid.ColumnOrder
            if col_order:
                cols = list(col_order)
                if cols:
                    return cols
        except Exception:
            pass

        # Fallback: ColumnCount + GetColumnId / GetColumnTitle
        try:
            col_count = grid.ColumnCount
            cols = []
            for i in range(col_count):
                try:
                    col_id = grid.GetColumnId(i)
                    cols.append(col_id)
                except Exception:
                    try:
                        col_title = grid.GetColumnTitle(i)
                        cols.append(col_title or f"COL_{i}")
                    except Exception:
                        cols.append(f"COL_{i}")
            if cols:
                return cols
        except Exception:
            pass

        return []

    # ══════════════════════════════════════════════════════════════
    # INTERNAL: Export (fallback, not primary path)
    # ══════════════════════════════════════════════════════════════

    def _latest_excel(self, folder: Path) -> Optional[Path]:
        """Find the most recently modified Excel file in folder."""
        files = [
            f for f in folder.glob("*.xls*")
            if not f.name.startswith("~$") and f.stat().st_size > 0
        ]
        if not files:
            return None
        return max(files, key=lambda f: f.stat().st_mtime)

    def _wait_until_readable(self, file_path: Path, timeout: Optional[int] = None) -> bool:
        """Wait until file is unlocked and readable."""
        max_wait = timeout or self.cfg.file_unlock_timeout
        for _ in range(max_wait):
            try:
                with open(file_path, "rb"):
                    return True
            except PermissionError:
                time.sleep(1)
        return False
