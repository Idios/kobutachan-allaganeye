"""``ExportMatch`` builders shared by the export-path test modules (#934 P1-3).

The resolver-level path contract tests live in
``tests/test_path_schema_contracts.py`` and the pool-routing tests live in
``tests/test_export_pool.py``. Both need the same two builders, so they live
here rather than in either test module.

**Why a non-test module.** Importing a helper out of a ``test_*`` module makes
pytest collect that module as a side effect of the import and couples the two
test files: renaming or splitting one breaks the other. Every other shared
test helper in this repo already follows this convention
(``tests/detection_cache.py``, ``tests/presence_harness.py``,
``tests/split_baseline_compare.py``), and this module keeps that consistent --
there is no precedent here for importing from a ``test_*`` module.
"""

from __future__ import annotations

from allaganeye.export.pool import ExportMatch


def make_matches(n: int) -> list[ExportMatch]:
    """``n`` back-to-back matches, 10 s each, all ``type_label='match'``."""
    return [
        ExportMatch(
            index=i, start=float(i * 10), end=float((i + 1) * 10), type_label="match"
        )
        for i in range(n)
    ]


def make_pair(a: str, b: str) -> list[ExportMatch]:
    """Two matches whose only difference is the ``{type}`` token."""
    return [
        ExportMatch(index=0, start=0.0, end=10.0, type_label=a),
        ExportMatch(index=1, start=10.0, end=20.0, type_label=b),
    ]
