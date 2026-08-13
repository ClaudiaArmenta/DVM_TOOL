"""Tests for the DVM Tool sidebar layout (Fix Prompt v2).

Validates:
  1. Vertical left sidebar (Overview + A1-A6) with status dots
  2. Right content panel with sections (one visible at a time)
  3. Auto-detect version on connect
  4. 90s idle interval, 500ms progress interval
  5. Per-analysis Run + Export buttons
  6. Overview: Run All / Run Selected / Export All / Export Selected + checklist
  7. Column-header tooltips (COLUMN_DESCRIPTIONS)
  8. Source labels: "SQL Statement Collection (SAP Note 1969700)", not "mini-check"
  9. Download components present
  10. App builds without errors
"""

import sys
import os
import io

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import pytest


# ===================================================================
# FIXTURES
# ===================================================================

@pytest.fixture(scope="session")
def app():
    """Build the Dash app once for all tests."""
    from hana_connection_manager.app import create_app
    application = create_app()
    return application


@pytest.fixture(scope="session")
def layout_tree(app):
    """Get the flat list of all component IDs in the layout."""
    from dash import html, dcc
    import dash_bootstrap_components as dbc

    ids = set()

    def walk(component):
        if hasattr(component, "id") and component.id:
            ids.add(component.id)
        if hasattr(component, "children"):
            children = component.children
            if isinstance(children, (list, tuple)):
                for child in children:
                    walk(child)
            elif children is not None:
                walk(children)

    walk(app.layout)
    return ids


# ===================================================================
# 1. SIDEBAR STRUCTURE
# ===================================================================

class TestSidebarLayout:
    """Test the vertical left sidebar navigation structure."""

    def test_sidebar_container_exists(self, layout_tree):
        assert "analyses-sidebar" in layout_tree

    def test_content_panel_exists(self, layout_tree):
        assert "analyses-content-panel" in layout_tree

    def test_sidebar_overview_item(self, layout_tree):
        assert "sidebar-item-overview" in layout_tree

    def test_sidebar_analysis_items(self, layout_tree):
        from hana_connection_manager.dvm.registry import ANALYSIS_SPECS
        for spec in ANALYSIS_SPECS:
            item_id = f"sidebar-item-{spec['id']}"
            assert item_id in layout_tree, f"Missing sidebar item: {item_id}"

    def test_status_dots_in_sidebar(self, layout_tree):
        from hana_connection_manager.dvm.registry import ANALYSIS_SPECS
        for spec in ANALYSIS_SPECS:
            dot_id = f"status-dot-{spec['id']}"
            assert dot_id in layout_tree, f"Missing status dot: {dot_id}"

    def test_sections_exist(self, layout_tree):
        assert "section-overview" in layout_tree
        from hana_connection_manager.dvm.registry import ANALYSIS_SPECS
        for spec in ANALYSIS_SPECS:
            section_id = f"section-{spec['id']}"
            assert section_id in layout_tree, f"Missing section: {section_id}"

    def test_no_old_horizontal_tab_bar(self, layout_tree):
        """The old horizontal section-tab-* IDs should NOT exist."""
        assert "section-tab-overview" not in layout_tree
        assert "section-tab-bar" not in layout_tree


# ===================================================================
# 2. AUTO-DETECT VERSION
# ===================================================================

class TestAutoVersion:
    """Test version auto-detect infrastructure."""

    def test_store_hana_version_exists(self, layout_tree):
        assert "store-hana-version" in layout_tree

    def test_header_version_text(self, layout_tree):
        assert "header-version-text" in layout_tree

    def test_version_panel(self, layout_tree):
        assert "version-panel" in layout_tree

    def test_detect_button(self, layout_tree):
        assert "btn-detect-version" in layout_tree

    def test_dropdown_version(self, layout_tree):
        assert "dropdown-hana-version" in layout_tree

    def test_version_select_module(self):
        from hana_connection_manager.dvm.version_select import (
            parse_hana_version,
            format_version_tuple,
        )
        parsed = parse_hana_version("2.00.089.02.1234")
        assert parsed == (2, 0, 89)
        assert format_version_tuple(parsed) == "2.00.089"


# ===================================================================
# 3. INTERVALS
# ===================================================================

class TestIntervals:
    """Test interval configuration."""

    def test_progress_interval_exists(self, layout_tree):
        assert "interval-progress" in layout_tree

    def test_idle_interval_exists(self, layout_tree):
        assert "interval-idle" in layout_tree

    def test_progress_interval_500ms_disabled(self, app):
        """Progress interval should be 500ms and disabled by default."""
        # Direct access: intervals are top-level children
        interval = None
        for child in app.layout.children:
            if getattr(child, "id", None) == "interval-progress":
                interval = child
                break
        assert interval is not None, "interval-progress not found in layout"
        assert interval.interval == 500
        assert interval.disabled is True

    def test_idle_interval_90s_enabled(self, app):
        """Idle interval should be 90000ms and enabled."""
        interval = None
        for child in app.layout.children:
            if getattr(child, "id", None) == "interval-idle":
                interval = child
                break
        assert interval is not None, "interval-idle not found in layout"
        assert interval.interval == 90_000
        assert interval.disabled is False


# ===================================================================
# 4. PER-ANALYSIS RUN & EXPORT BUTTONS
# ===================================================================

class TestPerAnalysisButtons:
    """Test per-analysis Run and Export buttons."""

    def test_run_buttons(self, layout_tree):
        from hana_connection_manager.dvm.registry import ANALYSIS_SPECS
        for spec in ANALYSIS_SPECS:
            btn_id = f"btn-run-{spec['id']}"
            assert btn_id in layout_tree, f"Missing Run button: {btn_id}"

    def test_export_buttons(self, layout_tree):
        from hana_connection_manager.dvm.registry import ANALYSIS_SPECS
        for spec in ANALYSIS_SPECS:
            btn_id = f"btn-export-{spec['id']}"
            assert btn_id in layout_tree, f"Missing Export button: {btn_id}"


# ===================================================================
# 5. OVERVIEW CONTROLS
# ===================================================================

class TestOverviewControls:
    """Test Overview section controls."""

    def test_run_all_button(self, layout_tree):
        assert "btn-run-all-analyses" in layout_tree

    def test_run_selected_button(self, layout_tree):
        assert "btn-run-selected" in layout_tree

    def test_export_all_button(self, layout_tree):
        assert "btn-export-excel" in layout_tree

    def test_export_selected_button(self, layout_tree):
        assert "btn-export-selected" in layout_tree

    def test_checklist(self, layout_tree):
        assert "checklist-analyses" in layout_tree

    def test_progress_container(self, layout_tree):
        assert "progress-container" in layout_tree
        assert "progress-bar-fill" in layout_tree
        assert "progress-text" in layout_tree
        assert "progress-pct" in layout_tree

    def test_overview_status_summaries(self, layout_tree):
        from hana_connection_manager.dvm.registry import ANALYSIS_SPECS
        for spec in ANALYSIS_SPECS:
            assert f"overview-status-{spec['id']}" in layout_tree
            assert f"overview-summary-{spec['id']}" in layout_tree


# ===================================================================
# 6. COLUMN TOOLTIPS
# ===================================================================

class TestColumnTooltips:
    """Test column-header tooltip descriptions."""

    def test_column_descriptions_exist(self):
        from hana_connection_manager.dvm.components import COLUMN_DESCRIPTIONS
        assert len(COLUMN_DESCRIPTIONS) >= 50
        assert "SCHEMA_NAME" in COLUMN_DESCRIPTIONS
        assert "TABLE_NAME" in COLUMN_DESCRIPTIONS
        assert "RECORD_COUNT" in COLUMN_DESCRIPTIONS
        assert "NSE_GB" in COLUMN_DESCRIPTIONS
        assert "GROWTH_MB" in COLUMN_DESCRIPTIONS

    def test_get_col_tooltip(self):
        from hana_connection_manager.dvm.components import _get_col_tooltip
        tooltip = _get_col_tooltip("SCHEMA_NAME")
        assert "schema" in tooltip.lower()

    def test_table_renders_with_tooltips(self):
        from hana_connection_manager.dvm.components import results_table
        df = pd.DataFrame({"SCHEMA_NAME": ["SYS"], "TABLE_NAME": ["T1"], "DISK_GB": [1.5]})
        result = results_table(df)
        # Just check it renders without error
        assert result is not None


# ===================================================================
# 7. SOURCE LABELS
# ===================================================================

class TestSourceLabels:
    """Test source label wording."""

    def test_file_based_source_label(self):
        from hana_connection_manager.dvm.analyses import get_sql_for_query
        # We can't fully test without real files, but test the structure
        # by verifying the label format in the code
        import inspect
        source = inspect.getsource(get_sql_for_query)
        assert "SQL Statement Collection (SAP Note 1969700)" in source
        assert "mini-check" not in source.replace("MiniCheck", "").replace("mini_check", "")

    def test_no_minicheck_in_source_labels(self):
        """Ensure 'mini-check' is not used in user-facing label strings."""
        import inspect
        from hana_connection_manager.dvm import analyses
        source = inspect.getsource(analyses)
        # Allow class names (MiniCheckNotFoundError) but not user-facing strings
        lines = source.split("\n")
        for line in lines:
            if "source_label" in line and "mini-check" in line.lower():
                pytest.fail(f"Found 'mini-check' in source label line: {line}")


# ===================================================================
# 8. DOWNLOAD COMPONENTS
# ===================================================================

class TestDownloads:
    """Test download components."""

    def test_download_excel(self, layout_tree):
        assert "download-excel" in layout_tree

    def test_download_excel_single(self, layout_tree):
        assert "download-excel-single" in layout_tree


# ===================================================================
# 9. EXPORT MODULE
# ===================================================================

class TestExport:
    """Test export module."""

    def test_export_full(self):
        from hana_connection_manager.dvm.export import export_to_excel
        results = {
            "a1_top_tables": [
                {"success": True, "df": pd.DataFrame({"A": [1]}), "source_label": "test"},
                {"success": True, "df": pd.DataFrame({"B": [2]}), "source_label": "test"},
            ],
        }
        xlsx_bytes = export_to_excel(results)
        assert isinstance(xlsx_bytes, bytes)
        assert len(xlsx_bytes) > 100

    def test_export_subset(self):
        from hana_connection_manager.dvm.export import export_to_excel
        results = {
            "a1_top_tables": [
                {"success": True, "df": pd.DataFrame({"A": [1]}), "source_label": "test"},
                {"success": True, "df": pd.DataFrame({"B": [2]}), "source_label": "test"},
            ],
            "a2_db_size_history": [
                {"success": True, "df": pd.DataFrame({"C": [3]}), "source_label": "test"},
            ],
        }
        xlsx_bytes = export_to_excel(results, analysis_ids=["a1_top_tables"])
        assert isinstance(xlsx_bytes, bytes)
        # Read it and verify only A1 sheets
        wb = pd.ExcelFile(io.BytesIO(xlsx_bytes))
        sheet_names = wb.sheet_names
        assert any("A1" in s for s in sheet_names)
        assert not any("A2" in s for s in sheet_names)


# ===================================================================
# 10. APP BUILD
# ===================================================================

class TestAppBuild:
    """Test the app builds without errors."""

    def test_app_creates(self, app):
        assert app is not None

    def test_callbacks_registered(self, app):
        """Should have a significant number of callbacks."""
        n = len(app.callback_map)
        assert n >= 20, f"Only {n} callbacks registered, expected >= 20"

    def test_offline_elements_exist(self, layout_tree):
        assert "screen-offline" in layout_tree
        assert "offline-query-selector" in layout_tree
        assert "offline-upload" in layout_tree

    def test_goto_buttons(self, layout_tree):
        from hana_connection_manager.dvm.registry import ANALYSIS_SPECS
        for spec in ANALYSIS_SPECS:
            goto_id = f"btn-goto-{spec['id']}"
            assert goto_id in layout_tree, f"Missing goto button: {goto_id}"

    def test_tab_content_areas(self, layout_tree):
        from hana_connection_manager.dvm.registry import ANALYSIS_SPECS
        for spec in ANALYSIS_SPECS:
            content_id = f"tab-content-{spec['id']}"
            assert content_id in layout_tree, f"Missing content area: {content_id}"


# ===================================================================
# 11. RENDERERS
# ===================================================================

class TestRenderers:
    """Test renderer source badge uses correct label pattern."""

    def test_source_badge_recognizes_sql_collection(self):
        from hana_connection_manager.dvm.renderers import _source_badge
        badge = _source_badge("SQL Statement Collection (SAP Note 1969700): some_file.sql")
        assert "dvm-badge-info" in badge.className

    def test_source_badge_nse(self):
        from hana_connection_manager.dvm.renderers import _source_badge
        badge = _source_badge("authored SQL (NSE, custom query)")
        assert "dvm-badge-neutral" in badge.className


# ===================================================================
# 12. DESERIALIZATION
# ===================================================================

class TestDeserialization:
    """Test result serialization/deserialization."""

    def test_serialize_deserialize_roundtrip(self):
        from hana_connection_manager.callbacks.dvm_analyses import (
            _serialize_results,
            _deserialize_results,
        )
        df = pd.DataFrame({"X": [1, 2, 3], "Y": ["a", "b", "c"]})
        results = [
            {"success": True, "df": df, "enrichment_df": None, "row_count": 3,
             "col_count": 2, "elapsed_ms": 42, "error": None, "source_label": "test"},
        ]
        serialized = _serialize_results(results)
        deserialized = _deserialize_results(serialized)
        assert len(deserialized) == 1
        assert deserialized[0]["success"] is True
        assert deserialized[0]["df"] is not None
        assert len(deserialized[0]["df"]) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
