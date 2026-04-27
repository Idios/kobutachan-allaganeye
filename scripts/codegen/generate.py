"""Generate language-specific types from schemas/metadata.schema.json (#612).

Single entry point that drives both the Python and TypeScript generators
so contributors run one command after editing the JSON Schema.

Usage::

    python scripts/codegen/generate.py        # both languages
    python scripts/codegen/generate.py --py   # Python only
    python scripts/codegen/generate.py --ts   # TypeScript only

CI calls this script and then ``git diff --exit-code`` on the generated
files; mismatch fails the build with a hint to re-run + commit.

Cross-platform notes:

* The Python output uses ``datamodel-code-generator`` (installed via
  ``pip install -e ".[dev]"``), invoked through ``python -m`` so the venv
  resolves correctly on Windows / Linux / macOS.
* The TypeScript output uses ``json-schema-to-typescript``, invoked via
  ``node gui/scripts/generate-ts.mjs`` so dependency resolution honours
  the gui/ workspace's ``node_modules``.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA_PATH = REPO_ROOT / "schemas" / "metadata.schema.json"
PYTHON_OUT = REPO_ROOT / "allaganeye" / "metadata_types.py"
TS_RUNNER = REPO_ROOT / "gui" / "scripts" / "generate-ts.mjs"
TS_OUT = REPO_ROOT / "gui" / "src" / "types" / "metadata.generated.ts"

PY_HEADER = (
    "# AUTO-GENERATED -- DO NOT EDIT.\n"
    "# Regenerate with `python scripts/codegen/generate.py` (issue #612).\n"
    "# Source: schemas/metadata.schema.json"
)


def generate_python() -> None:
    """Run datamodel-code-generator to produce a TypedDict module."""
    args = [
        sys.executable,
        "-m",
        "datamodel_code_generator",
        "--input",
        str(SCHEMA_PATH),
        "--input-file-type",
        "jsonschema",
        "--output",
        str(PYTHON_OUT),
        "--output-model-type",
        "typing.TypedDict",
        "--target-python-version",
        "3.11",
        "--use-standard-collections",
        "--use-double-quotes",
        "--disable-timestamp",
        "--use-schema-description",
        "--custom-file-header",
        PY_HEADER,
    ]
    subprocess.run(args, check=True, cwd=REPO_ROOT)
    print(f"generated: {PYTHON_OUT.relative_to(REPO_ROOT)}")


def generate_typescript() -> None:
    """Run gui/scripts/generate-ts.mjs (Node) to produce TS interfaces."""
    args = ["node", str(TS_RUNNER)]
    subprocess.run(args, check=True, cwd=REPO_ROOT)
    print(f"generated: {TS_OUT.relative_to(REPO_ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate metadata types from JSON Schema (issue #612)."
    )
    parser.add_argument(
        "--ts", action="store_true", help="Generate TypeScript output only"
    )
    parser.add_argument("--py", action="store_true", help="Generate Python output only")
    args = parser.parse_args()
    do_py = args.py or not (args.ts or args.py)
    do_ts = args.ts or not (args.ts or args.py)
    if do_py:
        generate_python()
    if do_ts:
        generate_typescript()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
