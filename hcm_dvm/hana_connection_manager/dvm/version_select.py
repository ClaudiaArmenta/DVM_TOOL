"""Version selection utilities for DVM Tool.

Provides:
  - parse_hana_version(): Parse a raw HANA version string into (major, minor, rev).
  - format_version_tuple(): Format a version tuple back to display string.
  - parse_filename_version(): Extract version threshold from a script filename.
  - get_base_name(): Extract the script base name (without version suffix).
  - list_matching_files(): Find all script files for a given base name.
  - select_variant(): Choose the correct script variant for a given HANA version.
  - scan_available_versions(): Scan a directory for all distinct version thresholds.

Version comparison is always NUMERIC per segment — never string-based.
"""

import re
from pathlib import Path
from typing import List, Optional, Tuple

# Regex to find version patterns like 2.00.077, 1.00.120, 2.00.059.01
_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)(?:\.(\d+))?")

# Regex to extract version threshold from filename: _M.mm.rrr+ or _M.mm.rrr.pp+
_FILENAME_VERSION_RE = re.compile(
    r"_(\d+)\.(\d+)\.(\d+)(?:\.(\d+))?\+\.txt$"
)


def parse_hana_version(version_str: str) -> Tuple[int, int, int]:
    """Parse a HANA version string into (major, minor, revision).

    Handles formats like:
      - "2.00.077"
      - "2.00.077.00.1699123456"
      - "1.00.120.00"

    Raises:
        ValueError: If no valid version pattern found.
    """
    version_str = version_str.strip()
    match = _VERSION_RE.search(version_str)
    if not match:
        raise ValueError(f"Cannot parse HANA version from: '{version_str}'")
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def format_version_tuple(version: Tuple[int, ...]) -> str:
    """Format a version tuple as 'M.mm.rrr'."""
    if len(version) < 3:
        return ".".join(str(v) for v in version)
    major, minor, revision = version[0], version[1], version[2]
    return f"{major}.{minor:02d}.{revision:03d}"


def parse_filename_version(filename: str) -> Tuple[int, int, int, int]:
    """Extract version threshold from a script filename.

    Returns (major, minor, rev, patch). No version suffix => (0,0,0,0).
    """
    match = _FILENAME_VERSION_RE.search(filename)
    if not match:
        return (0, 0, 0, 0)
    return (
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3)),
        int(match.group(4)) if match.group(4) else 0,
    )


def get_base_name(filename: str) -> str:
    """Extract the script base name (without version suffix and extension).

    E.g. 'HANA_Config_MiniChecks_2.00.059.01+.txt' -> 'HANA_Config_MiniChecks'
    """
    name = filename
    if name.endswith(".txt"):
        name = name[:-4]
    suffix_re = re.compile(r"_\d+\.\d+\.\d+(?:\.\d+)?\+$")
    match = suffix_re.search(name)
    if match:
        name = name[: match.start()]
    return name


def list_matching_files(queries_dir: str, base_name: str) -> List[str]:
    """Find all script files matching a given base name."""
    p = Path(queries_dir)
    if not p.exists():
        return []
    matching = []
    for f in p.iterdir():
        if not f.is_file() or not f.name.endswith(".txt"):
            continue
        if get_base_name(f.name) == base_name:
            matching.append(f.name)
    return sorted(matching)


def select_variant(
    queries_dir: str,
    base_name: str,
    target_version: Tuple[int, int, int],
) -> Optional[str]:
    """Select the best script variant for a given HANA version.

    Algorithm:
      1. List all files matching the base name.
      2. Parse each file's version threshold.
      3. Keep only those whose threshold <= the target version (numerically).
      4. Among candidates, pick the one with the highest threshold.
    """
    files = list_matching_files(queries_dir, base_name)
    if not files:
        return None

    candidates = []
    for fname in files:
        threshold = parse_filename_version(fname)
        threshold_3 = (threshold[0], threshold[1], threshold[2])
        if threshold_3 <= target_version:
            candidates.append((threshold, fname))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0])
    return candidates[-1][1]


def scan_available_versions(queries_dir: str) -> List[str]:
    """Scan a directory for distinct version thresholds across all script files.

    Returns list of version strings sorted descending (highest first).
    """
    p = Path(queries_dir)
    if not p.exists():
        return []

    versions = set()
    for f in p.iterdir():
        if not f.is_file() or not f.name.endswith(".txt"):
            continue
        threshold = parse_filename_version(f.name)
        if threshold != (0, 0, 0, 0):
            v_str = format_version_tuple(threshold[:3])
            versions.add(v_str)

    return sorted(versions, key=lambda s: parse_hana_version(s), reverse=True)


def get_queries_dir() -> str:
    """Resolve the queries directory (inside this package)."""
    import os

    env_dir = os.environ.get("DVM_QUERIES_DIR")
    if env_dir and Path(env_dir).exists():
        return env_dir
    # Default: hana_connection_manager/queries/ alongside dvm/
    pkg_queries = Path(__file__).parent.parent / "queries"
    if pkg_queries.exists():
        return str(pkg_queries)
    # Fallback: CWD/queries
    cwd_queries = Path.cwd() / "queries"
    if cwd_queries.exists():
        return str(cwd_queries)
    return str(pkg_queries)
