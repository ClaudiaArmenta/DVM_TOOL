"""Unit tests for hana_connection_manager.dvm.version_select module."""

import os
import tempfile
from pathlib import Path

import pytest

from hana_connection_manager.dvm.version_select import (
    parse_hana_version,
    format_version_tuple,
    parse_filename_version,
    get_base_name,
    list_matching_files,
    select_variant,
    scan_available_versions,
    get_queries_dir,
)


# ─── parse_hana_version ──────────────────────────────────────────────────


class TestParseHanaVersion:
    def test_simple_3_segment(self):
        assert parse_hana_version("2.00.077") == (2, 0, 77)

    def test_full_build_string(self):
        assert parse_hana_version("2.00.077.00.1699123456") == (2, 0, 77)

    def test_hana_1(self):
        assert parse_hana_version("1.00.120.00") == (1, 0, 120)

    def test_with_prefix_text(self):
        assert parse_hana_version("HANA version 2.00.059") == (2, 0, 59)

    def test_leading_trailing_whitespace(self):
        assert parse_hana_version("  2.00.040  ") == (2, 0, 40)

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            parse_hana_version("not-a-version")

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            parse_hana_version("")

    def test_numeric_only_raises(self):
        with pytest.raises(ValueError):
            parse_hana_version("200077")


# ─── format_version_tuple ────────────────────────────────────────────────


class TestFormatVersionTuple:
    def test_standard(self):
        assert format_version_tuple((2, 0, 77)) == "2.00.077"

    def test_hana1(self):
        assert format_version_tuple((1, 0, 120)) == "1.00.120"

    def test_larger_revision(self):
        assert format_version_tuple((2, 0, 85)) == "2.00.085"

    def test_short_tuple(self):
        assert format_version_tuple((2, 0)) == "2.0"


# ─── parse_filename_version ──────────────────────────────────────────────


class TestParseFilenameVersion:
    def test_standard_versioned(self):
        assert parse_filename_version("HANA_Backups_BackupProgress_1.00.100+.txt") == (
            1, 0, 100, 0
        )

    def test_four_segment(self):
        assert parse_filename_version(
            "HANA_Configuration_MiniChecks_2.00.059.01+.txt"
        ) == (2, 0, 59, 1)

    def test_no_version(self):
        assert parse_filename_version("HANA_Backups_BackupRuns.txt") == (0, 0, 0, 0)

    def test_higher_revision(self):
        assert parse_filename_version(
            "HANA_Configuration_MiniChecks_2.00.085+.txt"
        ) == (2, 0, 85, 0)


# ─── get_base_name ───────────────────────────────────────────────────────


class TestGetBaseName:
    def test_versioned(self):
        assert (
            get_base_name("HANA_Configuration_MiniChecks_2.00.059.01+.txt")
            == "HANA_Configuration_MiniChecks"
        )

    def test_unversioned(self):
        assert get_base_name("HANA_Backups_BackupRuns.txt") == "HANA_Backups_BackupRuns"

    def test_versioned_no_patch(self):
        assert (
            get_base_name("HANA_Backups_BackupProgress_1.00.100+.txt")
            == "HANA_Backups_BackupProgress"
        )


# ─── list_matching_files & select_variant (with temp dir) ────────────────


@pytest.fixture
def queries_tmpdir(tmp_path):
    """Create a temp directory with sample query files."""
    files = [
        "HANA_Configuration_MiniChecks_2.00.059.01+.txt",
        "HANA_Configuration_MiniChecks_2.00.073+.txt",
        "HANA_Configuration_MiniChecks_2.00.080+.txt",
        "HANA_Configuration_MiniChecks_2.00.085+.txt",
        "HANA_Backups_BackupRuns.txt",
        "HANA_Backups_BackupRuns_2.00.070+.txt",
        "HANA_Backups_BackupProgress_1.00.100+.txt",
    ]
    for f in files:
        (tmp_path / f).write_text("-- sample SQL")
    return str(tmp_path)


class TestListMatchingFiles:
    def test_finds_all_minichecks(self, queries_tmpdir):
        result = list_matching_files(queries_tmpdir, "HANA_Configuration_MiniChecks")
        assert len(result) == 4
        assert "HANA_Configuration_MiniChecks_2.00.059.01+.txt" in result
        assert "HANA_Configuration_MiniChecks_2.00.085+.txt" in result

    def test_finds_backup_runs(self, queries_tmpdir):
        result = list_matching_files(queries_tmpdir, "HANA_Backups_BackupRuns")
        assert len(result) == 2
        assert "HANA_Backups_BackupRuns.txt" in result
        assert "HANA_Backups_BackupRuns_2.00.070+.txt" in result

    def test_nonexistent_base(self, queries_tmpdir):
        result = list_matching_files(queries_tmpdir, "HANA_NonExistent")
        assert result == []

    def test_nonexistent_dir(self):
        result = list_matching_files("/nonexistent/path", "HANA_Anything")
        assert result == []


class TestSelectVariant:
    def test_exact_match(self, queries_tmpdir):
        # Target 2.00.080 -> pick _2.00.080+.txt
        result = select_variant(
            queries_tmpdir, "HANA_Configuration_MiniChecks", (2, 0, 80)
        )
        assert result == "HANA_Configuration_MiniChecks_2.00.080+.txt"

    def test_between_versions(self, queries_tmpdir):
        # Target 2.00.082 -> still pick _2.00.080+ (highest <= target)
        result = select_variant(
            queries_tmpdir, "HANA_Configuration_MiniChecks", (2, 0, 82)
        )
        assert result == "HANA_Configuration_MiniChecks_2.00.080+.txt"

    def test_highest_version(self, queries_tmpdir):
        # Target 2.00.999 -> pick _2.00.085+ (the highest threshold)
        result = select_variant(
            queries_tmpdir, "HANA_Configuration_MiniChecks", (2, 0, 999)
        )
        assert result == "HANA_Configuration_MiniChecks_2.00.085+.txt"

    def test_below_all_thresholds(self, queries_tmpdir):
        # Target 2.00.050 -> below all thresholds (even the lowest has .01 patch)
        result = select_variant(
            queries_tmpdir, "HANA_Configuration_MiniChecks", (2, 0, 50)
        )
        assert result is None

    def test_unversioned_file_selected(self, queries_tmpdir):
        # "HANA_Backups_BackupRuns.txt" has threshold (0,0,0,0), always matches
        result = select_variant(
            queries_tmpdir, "HANA_Backups_BackupRuns", (2, 0, 60)
        )
        # Target 2.00.060 < 2.00.070 threshold, but (0,0,0) <= target
        assert result == "HANA_Backups_BackupRuns.txt"

    def test_versioned_file_beats_unversioned(self, queries_tmpdir):
        # Target 2.00.080 -> _2.00.070+ has threshold (2,0,70) <= (2,0,80)
        # and (0,0,0,0) for unversioned also <= target. But 070 > 000 so pick versioned
        result = select_variant(
            queries_tmpdir, "HANA_Backups_BackupRuns", (2, 0, 80)
        )
        assert result == "HANA_Backups_BackupRuns_2.00.070+.txt"

    def test_nonexistent_base(self, queries_tmpdir):
        result = select_variant(queries_tmpdir, "HANA_NonExistent", (2, 0, 80))
        assert result is None


# ─── scan_available_versions ─────────────────────────────────────────────


class TestScanAvailableVersions:
    def test_returns_sorted_descending(self, queries_tmpdir):
        versions = scan_available_versions(queries_tmpdir)
        # Should contain distinct versions from the files
        assert "2.00.085" in versions
        assert "2.00.080" in versions
        assert "2.00.073" in versions
        assert "1.00.100" in versions
        # Sorted descending
        assert versions[0] == "2.00.085"
        assert versions[-1] == "1.00.100"

    def test_excludes_unversioned(self, queries_tmpdir):
        versions = scan_available_versions(queries_tmpdir)
        # (0,0,0) from unversioned files should not appear
        assert "0.00.000" not in versions

    def test_empty_dir(self, tmp_path):
        versions = scan_available_versions(str(tmp_path))
        assert versions == []

    def test_nonexistent_dir(self):
        versions = scan_available_versions("/nonexistent/dir")
        assert versions == []


# ─── get_queries_dir ─────────────────────────────────────────────────────


class TestGetQueriesDir:
    def test_env_override(self, tmp_path, monkeypatch):
        env_dir = str(tmp_path / "custom_queries")
        os.makedirs(env_dir)
        monkeypatch.setenv("DVM_QUERIES_DIR", env_dir)
        result = get_queries_dir()
        assert result == env_dir

    def test_default_package_dir(self, monkeypatch):
        monkeypatch.delenv("DVM_QUERIES_DIR", raising=False)
        result = get_queries_dir()
        # Should point to hana_connection_manager/queries/
        assert "hana_connection_manager" in result
        assert result.endswith("queries")
