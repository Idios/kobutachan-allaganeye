#!/usr/bin/env python3
"""doc -> code 参照が silent に壊れていないかを検査する (#912 / #910)。

`.github/workflows/ci.yml` の `doc-code-refs` job から引数なしで呼ばれる。
標準ライブラリのみを使う (CI job に pip install を持たせないため)。

    python scripts/check_doc_code_refs.py [--repo-root DIR]

exit code:

* 0 -- 全参照が解決した
* 1 -- 参照が壊れている (doc か code のどちらかを直す)
* 2 -- 構造エラー (anchor 消失 / 走査対象ゼロ / ファイル欠損)

1 と 2 を分けるのは `scripts/check_version_consistency.py` と同じ理由による。
「ズレている」と「検査自体が壊れた」を CI ログ上で区別するためで、検査の
自己崩壊を 0 で通すとガードが無いより有害になる。本 script では特に、doc の
散文を改稿して anchor が消えた場合に「0 件と 0 件が一致した」で緑を返さない
ことを重視している。

## 検査する 3 つの契約

**C1 (link)** `docs/*.md` の相対リンク先が実在すること。

**C2 (symbol)** ``[File.tsx](path) の `symbol` `` 形の参照について、`symbol` が
リンク先ファイルに実在すること (#910)。`の` は doc が使う所属の明示 (「File.tsx
**の** symbol」) なので、この形だけが「その symbol はそのファイルにある」と主張
している。照合はリンク先の **コメントを除去した** source に対して行い、末尾に
識別子文字が続かないことを要求する。前者はリネーム後にコメントだけ古い名前が
残った状態を stale と判定するため、後者は `styles.error` が `styles.errorMessage`
に誤マッチして rename を見逃すのを防ぐため。

**C3 (spawn)** `docs/system-architecture.md` §2.3 の「GUI -> CLI の spawn 箇所は
N つに限られる」という網羅宣言が、`gui/src-tauri/src/**/*.rs` の実態と一致する
こと (#912)。宣言した以上「網羅が壊れたら気づく」機構が要る。壊れた SSoT は
散在していた頃より有害になりうるため。

## この gate が見ていない集合

**参照先が存在することしか見ず、記述内容の正しさは見ない。** symbol 名が実在
しても、その symbol の振る舞いに関する doc の説明が正しいかは検査しない。
具体的には以下が検査外である。

* **`の` 形以外の backtick** — `docs/ui-interaction-spec.md` にはコードリンクの
  後ろに並ぶ backtick が 322 span あるが、C2 が見るのはそのうち `の` で束縛
  された 81 span だけで、**241 span は無検査である** (2026-08-07 実測)。残りは
  散文・UI ラベル (`[× 閉じる]`)・CSS 値 (`pointer-events: none`)・テンプレート
  (`${index}`) が大半で、リンク先ファイルへの所属を主張していない。全部を
  検査対象にすると 98/314 が red になり、その大半が正常な散文だった (実測)
  ため、束縛が明示された形だけを見ている。
  **この無検査集合には実際に stale なコード名が含まれていた** (2026-08-07 実測:
  `setCurrentT` / `loadErrorHint` / `addErrorHint` / `PROGRESS_EVENT` /
  `var(--ae-accent)` はいずれも repo に存在しなかった)。**この 5 件は #960 で実名へ
  直し、`の` 束縛形へ寄せて C2 の検査対象に入れた**ので、現在は残っていない。
  ただし C2 が無検査集合を持つ構造は変わっておらず、**同種の stale がまた入りうる**
  (束縛形を使わずに書けば検査されない)。上の 241 span という数字は当時の実測値。
* **`docs/superpowers/**`** — plan / spec の archive は走査対象外。実測で 168 本
  のリンクが既に壊れている (相対パスの階層ミス) が、archival 文書なので本 gate
  の射程には入れていない。
* **記述の意味** — argv の中身、状態遷移の説明、しきい値などの正しさ。
* **C2 の同名衝突** — 同じファイルに同名の別物があっても区別しない。照合は
  字句レベルであり、宣言か使用か、scope はどこかを解決しない。
* **C3 の provenance** — spawn の検出は `resolve_allaganeye_command` の呼び出しと
  `AllaganeyeCommand` の signature 露出を key にしており、AST 解析ではない。
  `AllaganeyeCommand` を経由せずに CLI パスを組み立てる新規経路は検出できない。
* **`#` コメント言語の文字列** — `.yml` / `.py` 等では文字列中の `#` 以降も
  コメントとして除去する。C2 が false-red 側に倒れることはあっても、
  false-green にはならない。

Refs: https://github.com/Idios/kobutachan-allaganeye/issues/912
Refs: https://github.com/Idios/kobutachan-allaganeye/issues/910
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_STRUCTURAL = 2


class GuardStructureError(Exception):
    """検査自体が成立しなかった (anchor 消失 / 走査対象ゼロ / ファイル欠損)。"""


@dataclass(frozen=True)
class Violation:
    """壊れた参照 1 件。"""

    check: str
    location: str
    message: str

    def render(self) -> str:
        return f"  [{self.check}] {self.location}: {self.message}"


# --- 走査対象 -------------------------------------------------------------

# top-level docs/*.md のみ。docs/superpowers/** (plan / spec の archive) は除外。
_DOC_GLOB = "docs/*.md"

# §2.3 の網羅宣言が置かれている doc。
_ARCH_DOC = "docs/system-architecture.md"

# CLI spawn を持ちうる Rust の走査範囲。lib.rs 以外へ spawn が移動しても
# 気づけるように、src-tauri 配下を再帰的に見る (process_util/ 等のサブ
# ディレクトリを取りこぼさないため)。
_RUST_GLOBS = ("gui/src-tauri/src/**/*.rs", "gui/src-tauri/tests/**/*.rs")

# CLI spawn 経路の choke point。
_RESOLVER = "resolve_allaganeye_command"

# `AllaganeyeCommand` を signature に持ってよい fn。この allowlist の外に
# 露出したら、spec を受け取る spawn helper への抽出が起きたとみなす。
_RESOLVER_FAMILY = frozenset(
    {
        "resolve_allaganeye_command",
        "resolve_from_env",
        "resolve_from_resource_dir",
        "resolve_python_fallback",
    }
)

_COMMAND_TYPE = "AllaganeyeCommand"

# --- 字句ユーティリティ ---------------------------------------------------

_C_STYLE_SUFFIXES = frozenset({".ts", ".tsx", ".js", ".jsx", ".mjs", ".rs"})
_BLOCK_ONLY_SUFFIXES = frozenset({".css", ".scss"})
_HASH_SUFFIXES = frozenset({".py", ".yml", ".yaml", ".sh", ".bash", ".toml", ".ps1"})

# symbol の境界判定に使う文字クラス。
#
# `-` を含めるのは、doc が参照するのが JS 識別子だけでなく testid / CSS class
# (`fallback-notice-` / `phase-row-detecting`) でもあるため。含めないと
# `fallback-notice-` が `old-fallback-notice-` に前方一致して **prefix を変える
# rename を見逃す**。
#
# `$` は含めない (境界として扱う)。doc がテンプレートリテラルの固定 prefix を
# 参照できるようにするため (source 側は `` `fallback-notice-${m.index}` ``)。
# rename 検出力は落ちない: `fallback-notice-v2-` へ改名されれば次の文字が `v`
# なので弾ける。実測で `gui/src/**` の識別子に `$` を含むものは 0 件。
_IDENT_CHAR = re.compile(r"[A-Za-z0-9_-]")

# インデントされた fn も拾う。impl block の method 内に spawn が置かれたとき、
# column 0 だけを見ていると直前の別 fn に誤って帰属し、診断が実態と食い違う。
_FN_DECL = re.compile(
    r"^[ \t]*(?:pub(?:\s*\([^)]*\))?\s+)?(?:const\s+)?(?:async\s+)?(?:unsafe\s+)?fn\s+"
    r"([A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)

# Rust の char literal (`'x'` / `'\n'` / `'\''` / `'\\'`)。lifetime (`'a`) は
# 閉じ引用符が無いので一致しない。
_RUST_CHAR_LITERAL = re.compile(r"'(?:\\.|[^'\\\n])'")

# 呼び出しではなく宣言 (`fn resolve_allaganeye_command(`) を除くための判定。
# 単なる endswith("fn") だと `my_fn` のような識別子末尾にも一致してしまう。
_FN_KEYWORD_TAIL = re.compile(r"(?<![A-Za-z0-9_])fn$")


def strip_comments(source: str, suffix: str) -> str:
    """コメントを空白へ潰す。オフセットと行数は保存する。

    **文字列リテラルは残す。** `data-testid` / `aria-label` の値は source では
    文字列の中にあるため、ここで文字列まで剥がすと C2 が軒並み false-red になる。
    Rust の spawn 走査だけは別途 `strip_rust_comments_and_strings` を使う。
    """
    out = list(source)
    n = len(source)
    i = 0
    has_line = suffix in _C_STYLE_SUFFIXES
    has_hash = suffix in _HASH_SUFFIXES
    has_block = suffix in _C_STYLE_SUFFIXES or suffix in _BLOCK_ONLY_SUFFIXES

    while i < n:
        ch = source[i]
        if has_line and ch == "/" and i + 1 < n and source[i + 1] == "/":
            while i < n and source[i] != "\n":
                out[i] = " "
                i += 1
        elif has_hash and ch == "#":
            while i < n and source[i] != "\n":
                out[i] = " "
                i += 1
        elif has_block and ch == "/" and i + 1 < n and source[i + 1] == "*":
            out[i] = out[i + 1] = " "
            i += 2
            while i < n and not (
                source[i] == "*" and i + 1 < n and source[i + 1] == "/"
            ):
                if source[i] != "\n":
                    out[i] = " "
                i += 1
            for j in range(i, min(i + 2, n)):
                out[j] = " "
            i = min(i + 2, n)
        else:
            i += 1
    return "".join(out)


def strip_rust_comments_and_strings(source: str) -> str:
    """Rust のコメントと文字列リテラルを空白へ潰す (長さ保存)。

    文字列まで潰すのは、`format!("start_export spawn: {}", e)` (lib.rs:3239) や
    `.find("async fn start_detect(")` (lib.rs:5711) のように **関数名と宣言形が
    文字列として実在する**ため。これを残すと裸名 scan は素通りする。
    """
    out = list(source)
    n = len(source)
    i = 0
    while i < n:
        ch = source[i]
        if ch == "/" and i + 1 < n and source[i + 1] == "/":
            while i < n and source[i] != "\n":
                out[i] = " "
                i += 1
        elif ch == "/" and i + 1 < n and source[i + 1] == "*":
            depth = 1
            out[i] = out[i + 1] = " "
            i += 2
            while i < n and depth:
                if source[i] == "/" and i + 1 < n and source[i + 1] == "*":
                    depth += 1
                    out[i] = out[i + 1] = " "
                    i += 2
                elif source[i] == "*" and i + 1 < n and source[i + 1] == "/":
                    depth -= 1
                    out[i] = out[i + 1] = " "
                    i += 2
                else:
                    if source[i] != "\n":
                        out[i] = " "
                    i += 1
        elif ch == "'" and (m := _RUST_CHAR_LITERAL.match(source, i)):
            # char literal。`'"'` / `b'"'` / `'}'` を先に食っておかないと、
            # 中の `"` が文字列の開始と誤認されて以降の走査が丸ごとずれ、
            # **実在する spawn site が空白化されて false-green になる**。
            # `'a` / `'static` のような lifetime は閉じ引用符が無いので
            # ここには一致せず、通常の文字として素通りする。
            for j in range(i, m.end()):
                out[j] = " "
            i = m.end()
        elif ch == "r" and (m := re.match(r'r(#*)"', source[i:])):
            # raw string r"..." / r#"..."#
            hashes = m.group(1)
            terminator = '"' + hashes
            end = source.find(terminator, i + len(m.group(0)))
            end = n if end < 0 else end + len(terminator)
            for j in range(i, end):
                if source[j] != "\n":
                    out[j] = " "
            i = end
        elif ch == '"':
            out[i] = " "
            i += 1
            while i < n:
                if source[i] == chr(92):  # backslash escape
                    out[i] = " "
                    if i + 1 < n and source[i + 1] != "\n":
                        out[i + 1] = " "
                    i += 2
                    continue
                if source[i] == '"':
                    out[i] = " "
                    i += 1
                    break
                if source[i] != "\n":
                    out[i] = " "
                i += 1
        else:
            i += 1
    return "".join(out)


def strip_cfg_test_modules(source: str) -> str:
    """`#[cfg(test)] mod X { .. }` の本体を空白へ潰す (長さ保存)。

    **`#[cfg(test)]` そのものを「test 領域の開始」と読んではいけない。**
    lib.rs には item 単位の `#[cfg(test)]` が column 0 に 4 件あり
    (:1885 / :2028 / :2049 / :2064)、いずれも最初の spawn site (:2460) より
    **前**にある。ここを領域開始とみなすと 5 サイトが全部消えて集合が空になり、
    guard は「宣言 0 件 == 実測 0 件」で緑を返す。直後が `mod NAME {` の場合
    だけを test モジュールとみなし、brace matching で終端を求める。

    呼び出し前に comment / string が除去済みであることを前提とする。
    """
    out = list(source)
    for m in re.finditer(r"#\[\s*cfg\s*\(\s*test\s*\)\s*\]", source):
        tail = source[m.end() :]
        head = re.match(
            r"\s*(?:pub(?:\s*\([^)]*\))?\s+)?mod\s+[A-Za-z_][A-Za-z0-9_]*\s*\{", tail
        )
        if head is None:
            continue  # item 単位の cfg(test)。領域ではない
        start = m.end() + head.end() - 1  # 開き brace の位置
        depth = 0
        i = start
        while i < len(source):
            if source[i] == "{":
                depth += 1
            elif source[i] == "}":
                depth -= 1
                if depth == 0:
                    i += 1
                    break
            i += 1
        for j in range(m.start(), min(i, len(source))):
            if source[j] != "\n":
                out[j] = " "
    return "".join(out)


def symbol_present(haystack: str, symbol: str) -> bool:
    """`symbol` が `haystack` に、識別子境界付きで現れるか。

    **末尾側は常に要求する。** 要求しないと `styles.error` が
    `styles.errorMessage` に誤マッチし、名前を伸ばす rename を永久に見逃す。

    **先頭側は symbol が識別子文字で始まるときだけ要求する。** doc は CSS class
    を `.recentName` のように先頭ドット付きで書くことがあり、source 側は
    `styles.recentName` なので、無条件に先頭境界を求めると false-red になる。
    一方で `fallback-notice-` のような識別子始まりの symbol に先頭境界を課さない
    と、`old-fallback-notice-` へ **prefix を変える rename** を見逃す。
    """
    if not symbol:
        return False
    leading_required = _IDENT_CHAR.match(symbol[0]) is not None
    start = 0
    while True:
        idx = haystack.find(symbol, start)
        if idx < 0:
            return False
        end = idx + len(symbol)
        preceding = haystack[idx - 1] if idx > 0 else ""
        following = haystack[end] if end < len(haystack) else ""
        blocked_before = leading_required and preceding and _IDENT_CHAR.match(preceding)
        blocked_after = following and _IDENT_CHAR.match(following)
        if not blocked_before and not blocked_after:
            return True
        start = idx + 1


# --- doc 走査 -------------------------------------------------------------

# blockquote 内の fence (`> ```) も fence として扱うため、行頭の `>` を許す。
_FENCE = re.compile(r"^[ \t]*(?:>[ \t]*)*(?:```|~~~)")
_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
_SYMBOL_REF = re.compile(r"\[[^\]]+\]\((\.\.?/[^)\s]+)\)\s*の\s*`([^`]+)`")


def iter_prose_lines(text: str) -> Iterator[tuple[int, str]]:
    """fenced code block を除いた行を (1-origin 行番号, 行) で返す。

    `docs/system-architecture.md` は fenced block を 3 本持つ (text / mermaid /
    text)。走査すると図中の疑似コードを実参照と誤認する。
    """
    inside = False
    opened_at = 0
    for lineno, line in enumerate(text.splitlines(), start=1):
        if _FENCE.match(line):
            inside = not inside
            opened_at = lineno if inside else 0
            continue
        if inside:
            continue
        yield lineno, line
    if inside:
        # 閉じ忘れた fence は「以降の doc 全体を走査対象から外す」= 参照が
        # 何本壊れていても緑になる、という最悪の失敗モードを作る。
        raise GuardStructureError(
            f"{opened_at} 行目で開いた code fence が閉じられていない。"
            "以降が走査対象から丸ごと外れて緑になるため、構造エラーとして落とす。"
        )


def _unescape_markdown(value: str) -> str:
    """markdown table 用の escape を戻す (`\\|` -> `|`)。"""
    return value.replace(chr(92) + "|", "|")


def link_targets(line: str) -> list[str]:
    """行に含まれる相対リンク先を返す (URL / 純アンカーは除く)。"""
    found: list[str] = []
    for target in _LINK.findall(line):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        base = target.split("#", 1)[0]
        if base:
            found.append(base)
    return found


def symbol_refs(line: str) -> list[tuple[str, str]]:
    """``[File](path) の `symbol` `` を (path, symbol) で返す。"""
    return [
        (target, _unescape_markdown(symbol))
        for target, symbol in _SYMBOL_REF.findall(line)
    ]


# --- Rust 走査 ------------------------------------------------------------


def _fn_declarations(source: str) -> list[tuple[int, str]]:
    """column 0 の fn 宣言を (オフセット, 名前) で返す。"""
    return [(m.start(), m.group(1)) for m in _FN_DECL.finditer(source)]


def rust_fn_names(source: str) -> set[str]:
    """column 0 の fn 名の集合 (comment / string 除去済み source を渡すこと)。"""
    return {name for _, name in _fn_declarations(source)}


def rust_cli_spawn_sites(source: str) -> list[str]:
    """CLI spawn site の enclosing fn 名を出現順に返す。

    fn 名の **集合** ではなく **出現ごと** に返す。集合で比較すると、既に
    カウント済みの fn に 2 本目の CLI spawn を足しても集合が不変で green の
    ままになり、argv 表 (§2.3) だけが非網羅になる。
    """
    cleaned = strip_cfg_test_modules(strip_rust_comments_and_strings(source))
    declarations = _fn_declarations(cleaned)

    sites: list[str] = []
    for match in re.finditer(rf"\b{_RESOLVER}\s*\(", cleaned):
        # `fn resolve_allaganeye_command(` という宣言そのものは site ではない。
        preceding = cleaned[: match.start()].rstrip()
        if _FN_KEYWORD_TAIL.search(preceding):
            continue
        prior = [name for offset, name in declarations if offset < match.start()]
        enclosing = prior[-1] if prior else "<top-level>"
        if enclosing == _RESOLVER:
            continue
        sites.append(enclosing)
    return sites


def allagan_command_signature_leaks(source: str, allowed: frozenset[str]) -> list[str]:
    """`AllaganeyeCommand` を signature に持つ fn のうち allowlist 外を返す。

    5 サイトは `Command::new(&cmd_spec.program)` を verbatim 重複しており、
    `fn build_cli_command(spec: &AllaganeyeCommand)` への抽出は自然な refactor
    である。抽出後も resolver の enclosing fn 集合は不変なので、resolver だけを
    見る guard は 6 本目の spawn を永久に見逃す。型の露出を別途見張ることで
    choke point の破壊に気づく。
    """
    cleaned = strip_cfg_test_modules(strip_rust_comments_and_strings(source))
    leaks: list[str] = []
    for match in _FN_DECL.finditer(cleaned):
        name = match.group(1)
        body = cleaned.find("{", match.end())
        signature = cleaned[match.end() : body if body >= 0 else len(cleaned)]
        if _COMMAND_TYPE in signature and name not in allowed:
            leaks.append(name)
    return leaks


# --- doc 側の宣言 parse ---------------------------------------------------

_SPAWN_CLAIM = re.compile(r"以下\s*(\d+)\s*つに限られること\s*[:：]\s*([^。]*)")
_BACKTICK = re.compile(r"`([^`]+)`")
_SNAKE_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


def declared_spawn_sites(doc_text: str) -> tuple[list[str], int]:
    """§2.3 の網羅宣言から (関数名リスト, 宣言された件数) を取り出す。

    anchor か列挙が見つからない場合は `GuardStructureError` を投げる。prose を
    改稿して anchor が消えたときに「0 件と一致した」で緑を返すと、検査が
    自己崩壊したまま CI が通るため。
    """
    match = _SPAWN_CLAIM.search(doc_text)
    if match is None:
        raise GuardStructureError(
            f"{_ARCH_DOC} の網羅宣言 anchor "
            "(「以下 N つに限られること: ...」) が見つからない。"
            "散文を改稿したなら scripts/check_doc_code_refs.py の _SPAWN_CLAIM も直すこと。"
        )
    declared_count = int(match.group(1))
    names = [n for n in _BACKTICK.findall(match.group(2)) if _SNAKE_IDENT.match(n)]
    if not names:
        raise GuardStructureError(
            f"{_ARCH_DOC} の網羅宣言から関数名を 1 つも取り出せなかった。"
            "関数名は backtick で囲むこと (guard の parse anchor)。"
        )
    return names, declared_count


_SECTION_23 = re.compile(r"^###\s+2\.3\b")
_ANY_HEADING = re.compile(r"^#{1,6}\s")


def _section_23_lines(doc_text: str) -> list[str]:
    """§2.3 の本文行だけを返す (他節の表を巻き込まないため)。

    doc 全体の表を走査すると、§2.1 の起動コマンド表にある `allaganeye` 等を
    argv 構築関数と誤認する。節が見つからない場合は構造エラー。
    """
    lines = list(iter_prose_lines(doc_text))
    start = next((i for i, (_, ln) in enumerate(lines) if _SECTION_23.match(ln)), None)
    if start is None:
        raise GuardStructureError(
            f"{_ARCH_DOC} に「### 2.3」節が見つからない。"
            "節番号を変えたなら scripts/check_doc_code_refs.py の _SECTION_23 も直すこと。"
        )
    body: list[str] = []
    for _, line in lines[start + 1 :]:
        if _ANY_HEADING.match(line):
            break
        body.append(line)
    return body


def declared_argv_builders(doc_text: str) -> list[str]:
    """§2.3 の argv 表に現れる argv 構築関数名を返す。

    表の各行は末尾に括弧書きで Rust 側の argv 構築関数名を持つ。argv を変更した
    ときにどの行を直すべきかが一意に決まるようにするための規約なので、その
    関数名が実在することを検査する。
    """
    names: list[str] = []
    for line in _section_23_lines(doc_text):
        if not line.lstrip().startswith("|"):
            continue
        for token in _BACKTICK.findall(line):
            if _SNAKE_IDENT.match(token) and token not in names:
                names.append(token)
    if not names:
        raise GuardStructureError(
            f"{_ARCH_DOC} §2.3 の表から argv 構築関数名を 1 つも取り出せなかった。"
            "関数名は backtick で囲むこと (guard の parse anchor)。"
        )
    return names


# --- 検査 -----------------------------------------------------------------


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - I/O 障害
        raise GuardStructureError(f"読み込めない: {path} ({exc})") from exc


def _docs(repo_root: Path) -> list[Path]:
    docs = sorted(repo_root.glob(_DOC_GLOB))
    if not docs:
        raise GuardStructureError(
            f"走査対象の doc が 0 件 ({_DOC_GLOB})。走査が壊れている。"
        )
    return docs


def check_link_targets(repo_root: Path) -> list[Violation]:
    """C1: 相対リンク先が実在すること。"""
    violations: list[Violation] = []
    checked = 0
    for doc in _docs(repo_root):
        text = _read(doc)
        for lineno, line in iter_prose_lines(text):
            for target in link_targets(line):
                checked += 1
                if not (doc.parent / target).exists():
                    violations.append(
                        Violation(
                            "link",
                            f"{doc.relative_to(repo_root).as_posix()}:{lineno}",
                            f"リンク先が存在しない: {target}",
                        )
                    )
    if checked == 0:
        raise GuardStructureError("相対リンクが 1 件も見つからない。走査が壊れている。")
    return violations


def check_symbol_refs(repo_root: Path) -> list[Violation]:
    """C2: ``[File](path) の `symbol` `` の symbol が実在すること。"""
    violations: list[Violation] = []
    checked = 0
    cache: dict[Path, str] = {}
    for doc in _docs(repo_root):
        text = _read(doc)
        for lineno, line in iter_prose_lines(text):
            for target, symbol in symbol_refs(line):
                checked += 1
                location = f"{doc.relative_to(repo_root).as_posix()}:{lineno}"
                path = doc.parent / target.split("#", 1)[0]
                if not path.is_file():
                    violations.append(
                        Violation("symbol", location, f"参照先が存在しない: {target}")
                    )
                    continue
                if path not in cache:
                    cache[path] = strip_comments(_read(path), path.suffix.lower())
                if not symbol_present(cache[path], symbol):
                    violations.append(
                        Violation(
                            "symbol",
                            location,
                            f"`{symbol}` が {target} に見つからない "
                            "(コメント内のみ / リネーム済み / 別ファイル所属の可能性)",
                        )
                    )
    if checked == 0:
        raise GuardStructureError(
            "`[File](path) の `symbol`` 形の参照が 1 件も見つからない。走査が壊れている。"
        )
    return violations


def check_spawn_coverage(repo_root: Path) -> list[Violation]:
    """C3: §2.3 の GUI -> CLI spawn 網羅宣言が実態と一致すること。"""
    doc_path = repo_root / _ARCH_DOC
    if not doc_path.is_file():
        raise GuardStructureError(f"{_ARCH_DOC} が存在しない。")
    doc_text = _read(doc_path)
    declared, declared_count = declared_spawn_sites(doc_text)
    location = _ARCH_DOC

    lib_path = repo_root / "gui/src-tauri/src/lib.rs"
    if not lib_path.is_file():
        raise GuardStructureError(f"{lib_path} が存在しない。")
    lib_source = _read(lib_path)

    violations: list[Violation] = []

    # 宣言された件数と列挙の長さが食い違っていないか (doc 内の自己整合)。
    if len(declared) != declared_count:
        violations.append(
            Violation(
                "spawn",
                location,
                f"「以下 {declared_count} つ」と書かれているが列挙は {len(declared)} 件",
            )
        )

    # 実測の spawn site と突合。集合ではなく出現順の列で比較する。
    actual = rust_cli_spawn_sites(lib_source)
    if sorted(actual) != sorted(declared):
        violations.append(
            Violation(
                "spawn",
                location,
                f"§2.3 の宣言 {sorted(declared)} と lib.rs の実測 {sorted(actual)} が不一致",
            )
        )

    # 同一 fn に 2 本目の spawn が生えていないか。
    for name in sorted(set(actual)):
        if actual.count(name) > 1:
            violations.append(
                Violation(
                    "spawn",
                    "gui/src-tauri/src/lib.rs",
                    f"{name} に CLI spawn が {actual.count(name)} 箇所ある "
                    "(§2.3 の argv 表は 1 fn = 1 行を前提にしている)",
                )
            )

    # lib.rs の外へ spawn が移動していないか + choke point が壊れていないか。
    # **どちらも全 Rust ファイルに対して行う。** lib.rs だけを見ていると、
    # `fn build_cli_command(spec: &AllaganeyeCommand)` を別 module へ置くだけで、
    # 5 サイトの集合を一切変えずに 6 本目の spawn を生やせてしまう。
    rust_paths = sorted(
        {p for pattern in _RUST_GLOBS for p in repo_root.glob(pattern) if p.is_file()}
    )
    if not rust_paths:
        raise GuardStructureError(
            f"Rust ソースが 1 件も見つからない ({', '.join(_RUST_GLOBS)})。走査が壊れている。"
        )
    for rs_path in rust_paths:
        rs_source = lib_source if rs_path == lib_path else _read(rs_path)
        relative = rs_path.relative_to(repo_root).as_posix()

        if rs_path != lib_path:
            outside = rust_cli_spawn_sites(rs_source)
            if outside:
                violations.append(
                    Violation(
                        "spawn",
                        relative,
                        f"lib.rs の外に CLI spawn がある: {sorted(set(outside))}。"
                        f"{_ARCH_DOC} §2.3 は lib.rs に限定して網羅を主張している",
                    )
                )

        leaks = allagan_command_signature_leaks(rs_source, allowed=_RESOLVER_FAMILY)
        if leaks:
            violations.append(
                Violation(
                    "spawn",
                    relative,
                    f"{_COMMAND_TYPE} が resolver 以外の signature に露出している: "
                    f"{sorted(leaks)}。spawn の choke point が壊れており、"
                    "この guard は網羅を保証できない",
                )
            )

    # argv 表が指す argv 構築関数が実在すること。
    known_fns = rust_fn_names(strip_rust_comments_and_strings(lib_source))
    for name in declared_argv_builders(doc_text):
        if name not in known_fns:
            violations.append(
                Violation(
                    "spawn",
                    location,
                    f"§2.3 の表が指す `{name}` が lib.rs の fn として存在しない",
                )
            )

    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else ""
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="検査対象の repo ルート (既定: 本 script の 1 つ上)",
    )
    args = parser.parse_args(argv)
    repo_root: Path = args.repo_root.resolve()

    # 診断は日本語を含む。Windows の既定 code page (cp932) のまま出すと
    # CI ログ / 呼び出し側の capture で化けるため UTF-8 に固定する。
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    try:
        violations = [
            *check_link_targets(repo_root),
            *check_symbol_refs(repo_root),
            *check_spawn_coverage(repo_root),
        ]
    except GuardStructureError as exc:
        print(f"ERROR: 検査自体が壊れている: {exc}", file=sys.stderr)
        return EXIT_STRUCTURAL

    if violations:
        print("ERROR: doc -> code 参照が壊れている。\n", file=sys.stderr)
        for violation in violations:
            print(violation.render(), file=sys.stderr)
        print(
            "\ndoc 側の記述か code 側の名前のどちらかを直すこと。"
            "\n契約の詳細は scripts/check_doc_code_refs.py の docstring を参照。",
            file=sys.stderr,
        )
        return EXIT_DRIFT

    print("OK: doc -> code 参照はすべて解決した (link / symbol / spawn)")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
