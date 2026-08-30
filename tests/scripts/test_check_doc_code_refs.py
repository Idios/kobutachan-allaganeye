"""Tests for scripts/check_doc_code_refs.py (#912 / #910).

保護機構は不発でも green になるため、本テストは **違反を注入して exit code の
生値を観測する** 形で書く。正常系だけを見て「ガードがある」と判断しない
(`tests/scripts/test_check_version_consistency.py` と同じ規律)。

本 file の主眼は `_EVASIONS` / `_FALSE_RED` の parametrize 群である。source-scan
guard は「走っているのに実際の回避形を見ていない」false-green に落ちやすく、本
repo では過去に (a) 行末コメントに書いただけの状態を配線済みと誤判定 (b) 行を
分けるだけで検査を素通り (c) ブロックコメント内の記述を実コードとして誤カウント
が実際に摘出されている。**手元 1 回きりの injection では再発を防げない**ため、
回避形を fixture として suite に常駐させる。

ここで使う Rust / TSX の断片は、すべて `gui/src-tauri/src/lib.rs` および
`gui/src/**` に **今日実在する行** を写したものである (docstring に出典行を記す)。
架空の回避形ではない。
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
SCRIPT_PATH = SCRIPTS_DIR / "check_doc_code_refs.py"

_spec = importlib.util.spec_from_file_location("check_doc_code_refs", SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
guard = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = guard
_spec.loader.exec_module(guard)


# --------------------------------------------------------------------------
# Rust spawn-site 抽出: false-green 回避形
# --------------------------------------------------------------------------

# (label, rust source) -- いずれも「spawn site が 0 個」でなければならない。
_EVASIONS: list[tuple[str, str]] = [
    (
        # lib.rs:3239 に実在: `format!("start_export spawn: {}", e)`
        "fn-name-survives-in-format-string",
        """
fn unrelated(e: String) -> String {
    format!("start_export spawn: {}", e)
}
""",
    ),
    (
        # lib.rs:5711 に実在: `.find("async fn start_detect(")`
        "declaration-form-inside-string-literal",
        """
fn scan(src: &str) -> usize {
    let start = src.find("async fn start_detect(").unwrap();
    let rest = &src[start + "async fn start_detect(".len()..];
    rest.len()
}
""",
    ),
    (
        # lib.rs:3495 に実在する形のコメント
        "call-mentioned-in-line-comment",
        """
async fn not_a_spawn_site() {
    // Must be before resolve_allaganeye_command(&app) / any spawn.
    let x = 1;
}
""",
    ),
    (
        "call-mentioned-in-block-comment",
        """
async fn not_a_spawn_site() {
    /* let cmd_spec = resolve_allaganeye_command(&app); */
    let x = 1;
}
""",
    ),
    (
        # lib.rs:1884 等に実在: `/// #[cfg(test)] で test ビルドのみに限定し ...`
        "call-mentioned-in-doc-comment",
        """
/// resolve_allaganeye_command(&app) を呼ぶのは spawn site だけ。
async fn documented_but_not_a_spawn_site() {
    let x = 1;
}
""",
    ),
    (
        "call-inside-raw-string",
        """
fn pattern() -> &'static str {
    r#"resolve_allaganeye_command(&app)"#
}
""",
    ),
    (
        # lib.rs:6460 / :6483 に実在: `mod enumerate_h264_encoders_tests {`
        "test-module-name-contains-command-name",
        """
#[cfg(test)]
mod start_export_wire_tests {
    fn helper() {
        let cmd_spec = resolve_allaganeye_command(&app);
    }
}
""",
    ),
    (
        "cfg-test-module-body-excluded",
        """
#[cfg(test)]
mod tests {
    async fn fake_site() {
        let cmd_spec = resolve_allaganeye_command(&app);
    }
}
""",
    ),
]

# (label, rust source) -- 「1 個検出されること」を要求する false-red 回避形。
_FALSE_RED: list[tuple[str, str, str]] = [
    (
        "plain-call",
        """
async fn start_detect() {
    let cmd_spec = resolve_allaganeye_command(&app);
}
""",
        "start_detect",
    ),
    (
        # 呼び出しが改行で分割されても 1 site
        "call-split-across-lines",
        """
async fn start_export() {
    let cmd_spec = resolve_allaganeye_command
        (&app);
}
""",
        "start_export",
    ),
    (
        # lib.rs:1885/2028/2049/2064 に実在: column-0 の `#[cfg(test)]` が
        # **mod ではなく fn / derive に付く**。これを「test 領域の開始」と
        # 誤認すると、以降の実 spawn site が全部消えて集合が空になる。
        "item-level-cfg-test-is-not-a-region",
        """
#[cfg(test)]
fn only_used_in_tests() -> u8 {
    7
}

async fn start_minimap() {
    let cmd_spec = resolve_allaganeye_command(&app);
}
""",
        "start_minimap",
    ),
    (
        # lib.rs:1884 等に実在: 実 attribute の 1 行上の doc comment に
        # `#[cfg(test)]` という文字列が入っている。
        "cfg-test-inside-doc-comment-is-not-a-region",
        """
/// #[cfg(test)] で test ビルドのみに限定し dead_code 警告を抑止。
#[cfg(test)]
fn helper() -> u8 {
    7
}

async fn detect_minimap_regions() {
    let cmd_spec = resolve_allaganeye_command(&app);
}
""",
        "detect_minimap_regions",
    ),
    (
        "async-and-pub-modifiers",
        """
pub async fn enumerate_h264_encoders() {
    let cmd_spec = resolve_allaganeye_command(&app);
}
""",
        "enumerate_h264_encoders",
    ),
]


@pytest.mark.parametrize(("label", "source"), _EVASIONS, ids=[e[0] for e in _EVASIONS])
def test_spawn_site_extraction_is_not_fooled(label: str, source: str) -> None:
    """回避形では spawn site が 1 個も検出されないこと (false-green 防止)."""
    assert guard.rust_cli_spawn_sites(source) == [], (
        f"回避形 {label!r} が spawn site として誤検出された。"
        " guard がこれを数えると doc の網羅宣言が偽でも green になる。"
    )


@pytest.mark.parametrize(
    ("label", "source", "expected_fn"), _FALSE_RED, ids=[e[0] for e in _FALSE_RED]
)
def test_spawn_site_extraction_finds_real_sites(
    label: str, source: str, expected_fn: str
) -> None:
    """実際の spawn site は取りこぼさないこと (false-red 防止)."""
    assert guard.rust_cli_spawn_sites(source) == [expected_fn], (
        f"{label!r} の実 spawn site を取りこぼした。"
        " 取りこぼすと「網羅である」が実際より狭く見え、guard が無害な緑を出す。"
    )


_Q = chr(34)
_BS = chr(92)
_SQ = chr(39)

# Rust の字句解析を狂わせて **実在する spawn site を空白化させる** 形。
# desync すると guard は「site 0 件」を返し、宣言との不一致で落ちる場合もあるが、
# doc 側の宣言も同時に空なら緑になる。いずれにせよ実態を見失っている。
_LEXER_ATTACKS: list[tuple[str, str, list[str]]] = [
    (
        # `'"'` の中の二重引用符を文字列開始と誤認すると以降が全部ずれる
        "char-literal-containing-double-quote",
        f"""
fn quote_char() -> char {{ {_SQ}{_Q}{_SQ} }}

async fn start_detect(app: A) {{
    let cmd_spec = resolve_allaganeye_command(&app);
}}
""",
        ["start_detect"],
    ),
    (
        "byte-char-literal-containing-double-quote",
        f"""
fn q() -> u8 {{ b{_SQ}{_Q}{_SQ} }}

async fn start_export(app: A) {{
    let cmd_spec = resolve_allaganeye_command(&app);
}}
""",
        ["start_export"],
    ),
    (
        # byte string の中の名前は site ではない
        "byte-string-literal-evasion",
        f"""
fn pattern() -> &{_SQ}static [u8] {{ b{_Q}resolve_allaganeye_command({_Q} }}
""",
        [],
    ),
    (
        "raw-string-with-multiple-hashes",
        f"r##{_Q}resolve_allaganeye_command({_Q}##",
        [],
    ),
    (
        # 文字列末尾のエスケープ済みバックスラッシュで閉じ引用符を食わないこと
        "escaped-backslash-at-end-of-string",
        f"""
fn p() -> &{_SQ}static str {{ {_Q}back{_BS}{_BS}{_Q} }}

async fn start_minimap(app: A) {{
    let cmd_spec = resolve_allaganeye_command(&app);
}}
""",
        ["start_minimap"],
    ),
    (
        # lifetime は char literal ではない
        "lifetime-and-generics",
        f"""
async fn detect_minimap_regions<{_SQ}a>(app: &{_SQ}a A) {{
    let cmd_spec = resolve_allaganeye_command(&app);
}}
""",
        ["detect_minimap_regions"],
    ),
    (
        # 宣言除外が `my_fn` のような識別子末尾に誤反応しないこと
        "identifier-ending-in-fn-before-call",
        """
async fn start_detect(app: A) {
    let my_fn
        = resolve_allaganeye_command(&app);
}
""",
        ["start_detect"],
    ),
    (
        # char literal 内の brace が cfg(test) mod の brace matching を壊さないこと
        "brace-inside-char-literal-in-cfg-test-mod",
        f"""
#[cfg(test)]
mod tests {{
    fn brace_char() -> char {{ {_SQ}}}{_SQ} }}
    fn fake() {{ let c = resolve_allaganeye_command(&app); }}
}}

async fn start_export(app: A) {{
    let cmd_spec = resolve_allaganeye_command(&app);
}}
""",
        ["start_export"],
    ),
    (
        "nested-block-comment",
        """
/* outer /* inner */ still comment resolve_allaganeye_command(&app) */
async fn start_detect(app: A) {
    let cmd_spec = resolve_allaganeye_command(&app);
}
""",
        ["start_detect"],
    ),
    (
        # impl block の method は column 0 でないため、column 0 だけを見ると
        # 直前の別 fn へ誤帰属する
        "spawn-inside-impl-block-method",
        """
async fn start_detect(app: A) {
    let cmd_spec = resolve_allaganeye_command(&app);
}

impl Foo {
    async fn method_spawn(&self, app: A) {
        let cmd_spec = resolve_allaganeye_command(&app);
    }
}
""",
        ["start_detect", "method_spawn"],
    ),
]


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    _LEXER_ATTACKS,
    ids=[a[0] for a in _LEXER_ATTACKS],
)
def test_rust_lexer_survives_attacks(
    label: str, source: str, expected: list[str]
) -> None:
    """字句解析の desync で spawn site を取り違えないこと."""
    assert guard.rust_cli_spawn_sites(source) == expected, (
        f"{label!r} で走査がずれた。desync すると実在する spawn site が空白化され、"
        " guard は実態を見失ったまま結論を出す。"
    )


def test_unclosed_fence_is_structural_not_silent() -> None:
    """閉じ忘れた code fence を構造エラーにすること.

    fence が閉じられていないと以降の doc 全体が走査対象から外れる。参照が何本
    壊れていても緑になるので、最悪の失敗モードとして exit 2 で落とす。
    """
    text = "line1\n```text\nunclosed\n[x](../ghost.ts)\n"
    with pytest.raises(guard.GuardStructureError):
        list(guard.iter_prose_lines(text))


def test_blockquote_fence_is_recognised() -> None:
    """blockquote 内の fence も fence として扱うこと.

    `> ```` の中の擬似コードを実参照と誤認すると false-red になる。
    """
    text = "> ```\n> [x](../ghost.ts)\n> ```\nafter\n"
    assert [ln for _, ln in guard.iter_prose_lines(text)] == ["after"]


def test_two_spawn_sites_in_one_fn_are_counted_twice() -> None:
    """同一 fn 内の 2 本目の spawn を潰さないこと.

    fn 名の **集合** で比較すると、既にカウント済みの fn に 2 本目の CLI spawn を
    足しても集合は不変で green のままになる。argv 表 (sec 2.3) だけが非網羅になる
    ため、site 数で比較する必要がある。
    """
    source = """
async fn start_export() {
    let cmd_spec = resolve_allaganeye_command(&app);
    let verify_spec = resolve_allaganeye_command(&app);
}
"""
    assert guard.rust_cli_spawn_sites(source) == ["start_export", "start_export"]


def test_spawn_site_helper_extraction_ignores_the_resolver_itself() -> None:
    """`resolve_allaganeye_command` の宣言そのものは site ではないこと."""
    source = """
fn resolve_allaganeye_command(app: &tauri::AppHandle) -> AllaganeyeCommand {
    resolve_python_fallback(None)
}
"""
    assert guard.rust_cli_spawn_sites(source) == []


# --------------------------------------------------------------------------
# AllaganeyeCommand の choke point 保全
# --------------------------------------------------------------------------


def test_allagan_command_leak_detects_extracted_spawn_helper() -> None:
    """spec を受け取る spawn helper への抽出を検出すること.

    5 サイトは `Command::new(&cmd_spec.program)` を verbatim 重複しており、
    `fn build_cli_command(spec: &AllaganeyeCommand) -> Command` への抽出は自然な
    refactor である。抽出後も `resolve_allaganeye_command` の enclosing fn 集合は
    不変なので、resolver だけを見る guard は 6 本目の spawn を永久に見逃す。
    """
    source = """
fn build_cli_command(spec: &AllaganeyeCommand) -> tokio::process::Command {
    tokio::process::Command::new(&spec.program)
}
"""
    leaks = guard.allagan_command_signature_leaks(source, allowed=frozenset())
    assert leaks == ["build_cli_command"]


def test_allagan_command_leak_allows_the_resolver_family() -> None:
    """既存の sub-resolver 3 本は allowlist で緑のままであること (false-red 防止)."""
    source = """
fn resolve_from_env(env_value: Option<String>) -> Option<AllaganeyeCommand> {
    None
}
fn resolve_python_fallback(cwd: Option<PathBuf>) -> AllaganeyeCommand {
    todo!()
}
"""
    allowed = frozenset({"resolve_from_env", "resolve_python_fallback"})
    assert guard.allagan_command_signature_leaks(source, allowed=allowed) == []


# --------------------------------------------------------------------------
# symbol 照合: 末尾 word boundary + コメント除去
# --------------------------------------------------------------------------


def test_symbol_match_rejects_longer_identifier() -> None:
    """`styles.error` が `styles.errorMessage` に誤マッチしないこと.

    素朴な substring 一致だと、rename 先が元の名前を prefix に含む限り永久に
    green のままになる (`styles.error` -> `styles.errorText` 等)。
    """
    assert not guard.symbol_present("const a = styles.errorMessage;", "styles.error")
    assert guard.symbol_present("const a = styles.error;", "styles.error")


def test_symbol_match_rejects_prefix_rename() -> None:
    """prefix を伸ばす rename を見逃さないこと (Codex adversarial-review 指摘).

    末尾境界だけを見ていると、doc の `fallback-notice-` が
    `old-fallback-notice-${index}` に前方一致して緑のままになる。testid /
    CSS class は `-` を含むので、`-` も境界文字として扱う必要がある。
    """
    assert guard.symbol_present(
        "data-testid={`fallback-notice-${m.index}`}", "fallback-notice-"
    )
    assert not guard.symbol_present(
        "data-testid={`old-fallback-notice-${m.index}`}", "fallback-notice-"
    )


def test_symbol_match_rejects_leading_identifier_extension() -> None:
    """識別子始まりの symbol は先頭境界も要求すること."""
    assert guard.symbol_present("const a = handleApply();", "handleApply")
    assert not guard.symbol_present("const a = legacyhandleApply();", "handleApply")


def test_allagan_command_leak_detects_impl_block_method() -> None:
    """impl block の method に置かれた spawn helper も検出すること.

    `_FN_DECL` を column 0 に限定していると、helper を impl の中へ移すだけで
    choke point の破壊が不可視になる (Codex adversarial-review 指摘)。
    """
    source = """
impl CliSpawner {
    fn build_cli_command(spec: &AllaganeyeCommand) -> Command {
        Command::new(&spec.program)
    }
}
"""
    assert guard.allagan_command_signature_leaks(source, allowed=frozenset()) == [
        "build_cli_command"
    ]


def test_symbol_match_allows_leading_partial() -> None:
    """先頭側は境界を要求しないこと.

    doc は CSS class を `.recentName` のように先頭ドット付きで書くことがあり、
    source 側は `styles.recentName`。先頭境界まで要求すると false-red になる。
    """
    assert guard.symbol_present("className={styles.recentName}", ".recentName")


def test_symbol_not_found_when_only_in_comment() -> None:
    """コメントにしか残っていない名前を「実在」と判定しないこと."""
    assert not guard.symbol_present(
        guard.strip_comments("// 旧実装は handleOldName を呼んでいた\n", ".tsx"),
        "handleOldName",
    )
    assert not guard.symbol_present(
        guard.strip_comments("/* handleOldName */\n", ".tsx"), "handleOldName"
    )


def test_symbol_found_inside_string_literal() -> None:
    """文字列リテラル内は除去しないこと.

    `data-testid` / `aria-label` の値は source では文字列の中にあるため、
    TS 側で文字列まで剥がすと軒並み false-red になる。
    """
    kept = guard.strip_comments('const t = "phase-row-detecting";\n', ".tsx")
    assert guard.symbol_present(kept, "phase-row-detecting")


def test_strip_comments_preserves_line_count() -> None:
    """行番号を報告に使うため、除去は行数を保つこと."""
    src = "a\n// c1\n/* c2\n   c3 */\nb\n"
    assert guard.strip_comments(src, ".ts").count("\n") == src.count("\n")


def test_strip_comments_hash_family() -> None:
    """`#` コメント言語 (yml / py / sh) も剥がすこと."""
    assert not guard.symbol_present(
        guard.strip_comments("# version-check job はここ\n", ".yml"), "version-check"
    )
    assert guard.symbol_present(
        guard.strip_comments("  version-check:\n", ".yml"), "version-check"
    )


# --------------------------------------------------------------------------
# doc 走査: fenced block / escape
# --------------------------------------------------------------------------


def test_fenced_code_blocks_are_skipped() -> None:
    """fenced block 内の link / backtick を参照として扱わないこと.

    `docs/system-architecture.md` は fenced block を 3 本持つ (text / mermaid /
    text)。ここを走査すると図中の疑似コードを実参照と誤認する。
    """
    text = "before\n```text\n[X](../nope/missing.ts) の `ghost`\n```\nafter\n"
    assert [ln for _, ln in guard.iter_prose_lines(text)] == ["before", "after"]


def test_table_pipe_escape_is_unescaped_before_matching() -> None:
    """markdown table の `\\|` を source 比較の前に戻すこと."""
    line = '| x | ([P.tsx](../gui/P.tsx) の `data-pane="in\\|out"`) |'
    refs = guard.symbol_refs(line)
    assert refs == [("../gui/P.tsx", 'data-pane="in|out"')]


# --------------------------------------------------------------------------
# doc 側の網羅宣言 parse
# --------------------------------------------------------------------------


def test_declared_spawn_sites_parses_backticked_list() -> None:
    doc = (
        "網羅性の根拠は `gui/src-tauri/src/lib.rs` で CLI (`cmd_spec.program`) を "
        "spawn する箇所が以下 2 つに限られること: `start_detect` / `start_export`。"
        "ffprobe / ffmpeg を直接 spawn する経路は対象外。\n"
    )
    assert guard.declared_spawn_sites(doc) == (["start_detect", "start_export"], 2)


def test_declared_spawn_sites_raises_when_anchor_missing() -> None:
    """anchor を失ったら **構造エラー**にすること.

    prose を改稿して anchor が消えたときに「0 件と一致した」で緑を返すと、
    検査が自己崩壊したまま CI が通る。ガードが無いより有害になる。
    """
    with pytest.raises(guard.GuardStructureError):
        guard.declared_spawn_sites("網羅についての説明が書かれていない doc\n")


def test_declared_spawn_sites_raises_when_list_empty() -> None:
    with pytest.raises(guard.GuardStructureError):
        guard.declared_spawn_sites(
            "spawn する箇所が以下 3 つに限られること: 特になし。\n"
        )


# --------------------------------------------------------------------------
# 実 repo に対する統合検査 + 違反注入
# --------------------------------------------------------------------------


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_repo_is_clean() -> None:
    """現 repo が exit 0 であること (guard を有効化できる前提)."""
    result = _run()
    assert result.returncode == guard.EXIT_OK, (
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_exit_code_contract_is_documented() -> None:
    """exit code の意味が docstring に書かれていること."""
    doc = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "exit code" in doc
    for code in ("0", "1", "2"):
        assert f"* {code} --" in doc


def test_blind_spot_is_disclosed_in_docstring() -> None:
    """「この gate が見ていない集合」が docstring に明記されていること.

    参照先が存在することしか見ず記述内容の正しさは見ない、という限界を書かない
    と「doc と code の整合が保証された」という過剰な主張になる。
    """
    doc = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "見ていない集合" in doc


def test_dollar_is_a_boundary_so_template_prefixes_are_checkable() -> None:
    """`$` を境界扱いし、テンプレートリテラルの固定 prefix を照合できること.

    source 側は `` data-testid={`fallback-notice-${m.index}`} `` なので、doc が
    `fallback-notice-` と書いたら一致してほしい。一方 prefix を変える rename
    (`fallback-notice-v2-`) は次の文字が識別子文字なので弾けること。
    """
    source = "data-testid={`fallback-notice-${m.index}`}"
    assert guard.symbol_present(source, "fallback-notice-")
    renamed = "data-testid={`fallback-notice-v2-${m.index}`}"
    assert not guard.symbol_present(renamed, "fallback-notice-")


# --- 合成 repo を使った違反注入 ------------------------------------------

_SYNTHETIC_LIB_RS = """
fn resolve_allaganeye_command(app: &tauri::AppHandle) -> AllaganeyeCommand {
    resolve_python_fallback(None)
}

fn resolve_python_fallback(cwd: Option<PathBuf>) -> AllaganeyeCommand {
    todo!()
}

fn detect_command_args(req: &Req) -> Vec<String> {
    vec![]
}

async fn start_detect(app: tauri::AppHandle) {
    let cmd_spec = resolve_allaganeye_command(&app);
    let mut cmd = tokio::process::Command::new(&cmd_spec.program);
}

async fn start_export(app: tauri::AppHandle) {
    let cmd_spec = resolve_allaganeye_command(&app);
    let mut cmd = tokio::process::Command::new(&cmd_spec.program);
}
"""

_SYNTHETIC_ARCH_MD = """# Synthetic

### 2.3 GUI -> CLI subprocess 経路

網羅性の根拠は `gui/src-tauri/src/lib.rs` で CLI (`cmd_spec.program`) を spawn する
箇所が以下 2 つに限られること: `start_detect` / `start_export`。ffprobe は対象外。

| 画面 | argv | 実装 |
| --- | --- | --- |
| DetectingScreen | `allaganeye detect` (`detect_command_args`) | x |

参照: [lib.rs](../gui/src-tauri/src/lib.rs) の `start_detect`
"""


def _make_repo(root: Path) -> None:
    """guard が exit 0 を返す最小の合成 repo を作る。"""
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "gui" / "src-tauri" / "src").mkdir(parents=True, exist_ok=True)
    (root / "gui" / "src-tauri" / "src" / "lib.rs").write_text(
        _SYNTHETIC_LIB_RS, encoding="utf-8"
    )
    (root / "docs" / "system-architecture.md").write_text(
        _SYNTHETIC_ARCH_MD, encoding="utf-8"
    )


def _run_on(root: Path) -> subprocess.CompletedProcess[str]:
    return _run("--repo-root", str(root))


def test_synthetic_repo_baseline_is_green(tmp_path: Path) -> None:
    """注入前の合成 repo が exit 0 であること (注入試験の前提)."""
    _make_repo(tmp_path)
    result = _run_on(tmp_path)
    assert result.returncode == guard.EXIT_OK, result.stderr


def test_injected_missing_link_fails(tmp_path: Path) -> None:
    """存在しないファイルへのリンクを注入したら exit 1 になること."""
    _make_repo(tmp_path)
    doc = tmp_path / "docs" / "system-architecture.md"
    doc.write_text(
        doc.read_text(encoding="utf-8") + "\n[ghost](../gui/src-tauri/src/ghost.rs)\n",
        encoding="utf-8",
    )
    result = _run_on(tmp_path)
    assert result.returncode == guard.EXIT_DRIFT, result.stdout + result.stderr
    assert "ghost.rs" in result.stderr


def test_injected_missing_symbol_fails(tmp_path: Path) -> None:
    """存在しない symbol への参照を注入したら exit 1 になること."""
    _make_repo(tmp_path)
    doc = tmp_path / "docs" / "system-architecture.md"
    doc.write_text(
        doc.read_text(encoding="utf-8")
        + "\n参照: [lib.rs](../gui/src-tauri/src/lib.rs) の `no_such_symbol`\n",
        encoding="utf-8",
    )
    result = _run_on(tmp_path)
    assert result.returncode == guard.EXIT_DRIFT, result.stdout + result.stderr
    assert "no_such_symbol" in result.stderr


def test_injected_sixth_spawn_site_fails(tmp_path: Path) -> None:
    """宣言にない spawn site を lib.rs に足したら exit 1 になること.

    #912 の受け入れ条件そのもの: 6 個目の CLI spawn site を追加したときに
    sec 2.3 未更新が検知されること。
    """
    _make_repo(tmp_path)
    lib = tmp_path / "gui" / "src-tauri" / "src" / "lib.rs"
    lib.write_text(
        lib.read_text(encoding="utf-8")
        + """
async fn start_undocumented(app: tauri::AppHandle) {
    let cmd_spec = resolve_allaganeye_command(&app);
    let mut cmd = tokio::process::Command::new(&cmd_spec.program);
}
""",
        encoding="utf-8",
    )
    result = _run_on(tmp_path)
    assert result.returncode == guard.EXIT_DRIFT, result.stdout + result.stderr
    assert "start_undocumented" in result.stderr


def test_injected_spawn_outside_lib_rs_fails(tmp_path: Path) -> None:
    """lib.rs 以外の .rs へ spawn が移動したら exit 1 になること.

    sec 2.3 の散文は `lib.rs で` とスコープされているため、別 module へ移すと
    その一文は真のまま網羅宣言だけが偽になる。
    """
    _make_repo(tmp_path)
    other = tmp_path / "gui" / "src-tauri" / "src" / "process_util"
    other.mkdir(parents=True, exist_ok=True)
    (other / "mod.rs").write_text(
        """
async fn spawn_from_another_module(app: tauri::AppHandle) {
    let cmd_spec = resolve_allaganeye_command(&app);
}
""",
        encoding="utf-8",
    )
    result = _run_on(tmp_path)
    assert result.returncode == guard.EXIT_DRIFT, result.stdout + result.stderr
    assert "spawn_from_another_module" in result.stderr


def test_injected_choke_point_extraction_outside_lib_fails(tmp_path: Path) -> None:
    """別 module へ置いた spawn helper も exit 1 になること.

    lib.rs だけに leak 検査をかけていると、helper を process_util へ移すだけで
    5 サイトの集合を変えずに 6 本目の spawn を生やせる (Codex 指摘)。
    """
    _make_repo(tmp_path)
    other = tmp_path / "gui" / "src-tauri" / "src" / "process_util"
    other.mkdir(parents=True, exist_ok=True)
    (other / "mod.rs").write_text(
        """
impl CliSpawner {
    fn build_cli_command(spec: &AllaganeyeCommand) -> Command {
        Command::new(&spec.program)
    }
}
""",
        encoding="utf-8",
    )
    result = _run_on(tmp_path)
    assert result.returncode == guard.EXIT_DRIFT, result.stdout + result.stderr
    assert "build_cli_command" in result.stderr


def test_injected_unclosed_fence_is_structural(tmp_path: Path) -> None:
    """doc に閉じ忘れ fence を注入したら exit 2 になること.

    fence 前に有効な参照が 1 本でもあれば zero-count の構造ガードは通ってしまう
    ので、fence 自体を構造エラーにする必要がある (Codex 指摘)。
    """
    _make_repo(tmp_path)
    doc = tmp_path / "docs" / "system-architecture.md"
    doc.write_text(
        doc.read_text(encoding="utf-8")
        + "\n```text\nunclosed\n[gone](../gui/src-tauri/src/ghost.rs)\n",
        encoding="utf-8",
    )
    result = _run_on(tmp_path)
    assert result.returncode == guard.EXIT_STRUCTURAL, result.stdout + result.stderr


def test_injected_choke_point_extraction_fails(tmp_path: Path) -> None:
    """spec を受け取る spawn helper を足したら exit 1 になること."""
    _make_repo(tmp_path)
    lib = tmp_path / "gui" / "src-tauri" / "src" / "lib.rs"
    lib.write_text(
        lib.read_text(encoding="utf-8")
        + """
fn build_cli_command(spec: &AllaganeyeCommand) -> tokio::process::Command {
    tokio::process::Command::new(&spec.program)
}
""",
        encoding="utf-8",
    )
    result = _run_on(tmp_path)
    assert result.returncode == guard.EXIT_DRIFT, result.stdout + result.stderr
    assert "build_cli_command" in result.stderr


def test_injected_count_prose_mismatch_fails(tmp_path: Path) -> None:
    """列挙を増やして「以下 N つ」を据え置いたら exit 1 になること (doc 内の自己整合)."""
    _make_repo(tmp_path)
    doc = tmp_path / "docs" / "system-architecture.md"
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(
            "`start_detect` / `start_export`",
            "`start_detect` / `start_export` / `start_third`",
        ),
        encoding="utf-8",
    )
    result = _run_on(tmp_path)
    assert result.returncode == guard.EXIT_DRIFT, result.stdout + result.stderr


def test_removed_anchor_is_structural_not_green(tmp_path: Path) -> None:
    """anchor を壊したら exit 2 (構造エラー) になること -- 緑で素通りしないこと.

    「検査自体が壊れた」を 0 で返すのが最悪の失敗モード。ガードが無いより有害
    になるため、専用の exit code で落ちることを pin する。
    """
    _make_repo(tmp_path)
    doc = tmp_path / "docs" / "system-architecture.md"
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(
            "以下 2 つに限られること:", "だいたい以下です:"
        ),
        encoding="utf-8",
    )
    result = _run_on(tmp_path)
    assert result.returncode == guard.EXIT_STRUCTURAL, result.stdout + result.stderr


def test_renamed_section_heading_is_structural_not_green(tmp_path: Path) -> None:
    """sec 2.3 の見出しを変えたら exit 2 になること (argv 表の検査が無言で消えない)."""
    _make_repo(tmp_path)
    doc = tmp_path / "docs" / "system-architecture.md"
    doc.write_text(
        doc.read_text(encoding="utf-8").replace("### 2.3 ", "### 2.4 "),
        encoding="utf-8",
    )
    result = _run_on(tmp_path)
    assert result.returncode == guard.EXIT_STRUCTURAL, result.stdout + result.stderr


def test_no_docs_is_structural_not_green(tmp_path: Path) -> None:
    """走査対象が 0 件なら exit 2 になること."""
    (tmp_path / "docs").mkdir()
    result = _run_on(tmp_path)
    assert result.returncode == guard.EXIT_STRUCTURAL, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# MAX_PATH (#965)
#
# Windows の ``os.stat`` は 260 文字を超えるパスに対し、ファイルが実在していても
# ``FileNotFoundError`` を返す。``Path.exists()`` / ``Path.is_file()`` は内部で
# ``os.stat`` を呼ぶので、深い場所へ checkout した repo でこの guard をローカル
# 実行すると、実在するリンク先を「存在しない」と報告して exit 1 になっていた。
#
# **「エラーが消えた」だけでは検査が no-op 化したのと区別できない**ので、
# 拡張パスへ寄せた後も「実在しないものは False を返す」ことを対で固定する。
# ---------------------------------------------------------------------------

_LONG_SEGMENT = "d" * 48


def _make_deep_dir(base: Path) -> Path:
    """``base`` の下に 260 文字を超えるディレクトリを作って返す。

    作成自体に拡張パスが要る (``os.makedirs`` も ``os.stat`` 系を通る) ため、
    Windows では ``\\\\?\\`` を前置して掘る。
    """
    deep = base
    for _ in range(6):
        deep = deep / _LONG_SEGMENT
    target = str(deep)
    if os.name == "nt":
        os.makedirs("\\\\?\\" + os.path.abspath(target), exist_ok=True)
    else:
        os.makedirs(target, exist_ok=True)
    return deep


def test_extended_is_noop_off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """POSIX では変換しない (MAX_PATH 相当の制約が無いため)."""
    monkeypatch.setattr(guard.os, "name", "posix")
    assert guard._extended(Path("docs/a.md")) == "docs/a.md"


@pytest.mark.skipif(os.name != "nt", reason="拡張パス形式は Windows 固有")
def test_extended_prefixes_a_drive_path() -> None:
    got = guard._extended(Path("C:/x/y.md"))
    assert got.startswith("\\\\?\\C:\\"), got


@pytest.mark.skipif(os.name != "nt", reason="拡張パス形式は Windows 固有")
def test_extended_uses_the_unc_form_for_unc_paths() -> None:
    """UNC は ``\\\\?\\UNC\\server\\share`` 形。素朴な前置では解決できない.

    ``\\\\server\\share\\x`` に ``\\\\?\\`` をそのまま足すと ``\\\\?\\\\\\server\\...``
    になり、直そうとした「実在するのに存在しないと報告する」症状を UNC 上で
    そのまま再現してしまう。
    """
    got = guard._extended(Path("//server/share/x.md"))
    assert got.startswith("\\\\?\\UNC\\server\\share"), got
    assert not got.startswith("\\\\?\\\\\\"), got


@pytest.mark.skipif(os.name != "nt", reason="拡張パス形式は Windows 固有")
def test_extended_is_idempotent_on_already_extended_paths() -> None:
    already = "\\\\?\\C:\\x\\y.md"
    assert guard._extended(Path(already)) == already


def test_exists_finds_a_file_behind_max_path(tmp_path: Path) -> None:
    """260 文字超のパスでも実在判定が True になること (#965 の本体).

    Windows では素の ``Path.exists()`` が False を返すことも同時に確認する
    (返さないなら、この環境ではそもそも症状が再現しておらず、本 test は
    「修正が効いた」ことの証拠になっていない)。
    """
    deep = _make_deep_dir(tmp_path)
    target = deep / "b.md"
    if os.name == "nt":
        with open("\\\\?\\" + os.path.abspath(str(target)), "w", encoding="utf-8") as f:
            f.write("# b\n")
    else:
        target.write_text("# b\n", encoding="utf-8")

    assert len(str(target)) > 260, f"deep path is only {len(str(target))} chars"
    if os.name == "nt":
        assert not target.exists(), (
            "素の Path.exists() が True を返した = この環境では MAX_PATH 症状が "
            "再現していない。本 test は修正の証拠になっていないので、"
            "再現条件 (パス長 / longpath 設定) を見直すこと"
        )
    assert guard._exists(target) is True
    assert guard._is_file(target) is True


def test_exists_still_reports_missing_files_behind_max_path(tmp_path: Path) -> None:
    """拡張パスへ寄せても「実在しないものは False」が保たれること.

    これが無いと、`_exists` が常に True を返す実装 (= 検査の no-op 化) でも
    上の test は緑になる。「エラーが消えた」と「検査が黙った」を分ける。
    """
    deep = _make_deep_dir(tmp_path)
    missing = deep / "NOPE.md"
    assert len(str(missing)) > 260
    assert guard._exists(missing) is False
    assert guard._is_file(missing) is False
