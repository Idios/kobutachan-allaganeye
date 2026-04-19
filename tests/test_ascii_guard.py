"""Guard test: prevent non-ASCII characters in runtime output strings (#308).

Windows cp932 encoding causes UnicodeEncodeError when print() / logger.*()
emit characters like U+2192 (->), U+2014 (--), U+2248 (~=), etc.

This test scans all production .py files and fails if any problematic
non-ASCII characters appear in:
  1. String literals inside print() / logger.*() calls
  2. Docstrings (pytest -v displays them)
  3. f-string / format-string content passed to print/logger

Japanese text (CJK Unified Ideographs, Hiragana, Katakana) is allowed
because it is explicitly permitted by coding-conventions.md and cp932
handles it natively.
"""

from __future__ import annotations

import ast
import pathlib
import re

# Build banned-char mapping at runtime via chr() so this file itself
# does not contain the literal non-ASCII codepoints in any string constant
# (which would cause the self-scan to flag this very file).
_BANNED_CHARS: dict[str, str] = {
    chr(0x2192): "->",  # RIGHTWARDS ARROW
    chr(0x2014): "--",  # EM DASH
    chr(0x2248): "~=",  # ALMOST EQUAL TO
    chr(0x2265): ">=",  # GREATER-THAN OR EQUAL TO
    chr(0x00B1): "+-",  # PLUS-MINUS SIGN
    chr(0x2081): "1",  # SUBSCRIPT ONE
    chr(0x2082): "2",  # SUBSCRIPT TWO
    chr(0x2713): "OK",  # CHECK MARK
}

# Unicode ranges that are OK (Japanese text, handled by cp932)
_ALLOWED_RANGES = [
    (0x3000, 0x303F),  # CJK Symbols and Punctuation
    (0x3040, 0x309F),  # Hiragana
    (0x30A0, 0x30FF),  # Katakana
    (0x4E00, 0x9FFF),  # CJK Unified Ideographs
    (0xFF00, 0xFFEF),  # Halfwidth and Fullwidth Forms
]

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
_SRC_DIR = _PROJECT_ROOT / "allaganeye"


def _is_allowed_non_ascii(ch: str) -> bool:
    """Return True if the non-ASCII character is allowed (Japanese text)."""
    code = ord(ch)
    return any(lo <= code <= hi for lo, hi in _ALLOWED_RANGES)


def _find_banned_chars_in_string(s: str) -> list[tuple[str, str]]:
    """Return list of (char, replacement) for banned chars found in string."""
    found = []
    for ch in s:
        if ord(ch) > 127 and not _is_allowed_non_ascii(ch):
            replacement = _BANNED_CHARS.get(ch, f"U+{ord(ch):04X}")
            found.append((ch, replacement))
    return found


def _scan_file_for_banned_chars(filepath: pathlib.Path) -> list[str]:
    """Scan a Python file for non-ASCII chars in string literals and comments.

    Returns a list of human-readable violation descriptions.
    """
    violations: list[str] = []
    source = filepath.read_text("utf-8")
    rel = filepath.relative_to(_PROJECT_ROOT)

    # 1. Check string literals via AST (catches print/logger args, docstrings)
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [f"{rel}: SyntaxError -- could not parse"]

    for node in ast.walk(tree):
        # Check all string constants (includes docstrings, format strings, etc.)
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            banned = _find_banned_chars_in_string(node.value)
            if banned:
                line = node.lineno
                for ch, repl in banned:
                    violations.append(
                        f"{rel}:{line}: "
                        f"U+{ord(ch):04X} {ch!r} in string literal "
                        f"(use {repl!r} instead)"
                    )

    # 2. Check comments (lines starting with # after stripping)
    for lineno, line in enumerate(source.splitlines(), 1):
        comment_match = re.search(r"#(.+)$", line)
        if comment_match:
            comment_text = comment_match.group(1)
            banned = _find_banned_chars_in_string(comment_text)
            if banned:
                for ch, repl in banned:
                    violations.append(
                        f"{rel}:{lineno}: "
                        f"U+{ord(ch):04X} {ch!r} in comment "
                        f"(use {repl!r} instead)"
                    )

    return violations


def test_no_banned_non_ascii_in_production_code():
    """All .py files in allaganeye/ must not contain banned non-ASCII chars.

    Enforces coding-conventions.md section 'Character Encoding'.
    Prevents regression of #308 fix (Windows cp932 UnicodeEncodeError).
    """
    all_violations: list[str] = []

    for py_file in sorted(_SRC_DIR.rglob("*.py")):
        violations = _scan_file_for_banned_chars(py_file)
        all_violations.extend(violations)

    if all_violations:
        msg = (
            f"Found {len(all_violations)} non-ASCII violation(s) "
            f"in production code.\n"
            f"See coding-conventions.md 'Character Encoding' section.\n\n"
        )
        msg += "\n".join(all_violations)
        raise AssertionError(msg)


def test_no_banned_non_ascii_in_test_code():
    """All .py files in tests/ must not contain banned non-ASCII chars.

    pytest -v displays docstrings and test names, which can trigger
    UnicodeEncodeError on Windows cp932.
    """
    tests_dir = _PROJECT_ROOT / "tests"
    all_violations: list[str] = []

    for py_file in sorted(tests_dir.rglob("*.py")):
        violations = _scan_file_for_banned_chars(py_file)
        all_violations.extend(violations)

    if all_violations:
        msg = (
            f"Found {len(all_violations)} non-ASCII violation(s) "
            f"in test code.\n"
            f"See coding-conventions.md 'Character Encoding' section.\n\n"
        )
        msg += "\n".join(all_violations)
        raise AssertionError(msg)


def test_banned_chars_detection_works():
    """Verify the scanner correctly detects banned characters."""
    arrow = chr(0x2192)
    em_dash = chr(0x2014)

    # ASCII arrow should not be flagged
    found = _find_banned_chars_in_string("a -> b")
    assert found == [], "ASCII arrow should not be flagged"

    # Unicode arrow should be flagged
    found = _find_banned_chars_in_string(f"a {arrow} b")
    assert len(found) == 1
    assert found[0] == (arrow, "->")

    # Em dash should be flagged
    found = _find_banned_chars_in_string(f"foo {em_dash} bar")
    assert len(found) == 1
    assert found[0] == (em_dash, "--")


def test_japanese_text_allowed():
    """Japanese characters are allowed (cp932 supports them natively)."""
    # Build Japanese strings via chr() to keep this file ASCII-clean
    kanji = chr(0x8A66) + chr(0x5408) + chr(0x5206) + chr(0x5272)
    katakana = chr(0x30C6) + chr(0x30B9) + chr(0x30C8)
    hiragana = chr(0x3072) + chr(0x3089) + chr(0x304C) + chr(0x306A)

    found = _find_banned_chars_in_string(kanji)
    assert found == [], "Japanese kanji should be allowed"

    found = _find_banned_chars_in_string(katakana)
    assert found == [], "Katakana should be allowed"

    found = _find_banned_chars_in_string(hiragana)
    assert found == [], "Hiragana should be allowed"
