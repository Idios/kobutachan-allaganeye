#!/usr/bin/env python3
"""README のスクショが GUI の現状を写しているかを検査する (#944)。

`.github/workflows/ci.yml` の `screenshot-freshness` job から引数なしで呼ばれる。
標準ライブラリのみを使う (CI job に pip install を持たせないため)。

    python scripts/check_screenshot_freshness.py [--repo-root DIR] [--update]

exit code:

* 0 -- スクショは現行の GUI source から撮られている
* 1 -- GUI source が変わったのにスクショが撮り直されていない
* 2 -- 構造エラー (manifest 欠損 / glob が空 / 宣言と実体の不一致)

`--update` は再撮影後に digest を書き戻すためのもの。**撮り直しとセットで**使う。

## なぜ git を使わないか (実測に基づく設計判断)

素朴な実装は「スクショの commit 日時 >= 画面 tsx の commit 日時なら OK」だが、
本 repo ではこれが **無条件 green** になる。2026-08-20 に実測した 2 点:

1. **CI が shallow clone である。** `actions/checkout@v4` の既定は
   `fetch-depth: 1` で、本 repo のどの workflow も `fetch-depth` を設定して
   いない。depth-1 の clone で `git log -- <path>` を撃つと、`image/03-complete.png`
   も `gui/src/screens/MinimapScreen.tsx` も **同じ 1 commit** を返す。全ファイルが
   同一日時になるので比較は常に成立する。
2. **squash merge が blob 変化点を潰している。** 仮に `fetch-depth: 0` にしても、
   v0.3.0 の squash merge (`aefcb8c`) 以前の履歴は HEAD から到達できない。
   その結果 `image/03-complete.png` の blob 最終変化点も `MinimapScreen.tsx` の
   それも `aefcb8c` に揃い、**スクショが実際に陳腐化していた当日でも** blob 追跡
   ベースの比較は green を返した。

よって照合対象は git 履歴ではなく **source の内容ハッシュ** である。内容ハッシュ
は shallow checkout でも squash merge でも壊れない。

## 契約

`image/screenshot-manifest.json` が SSoT で、以下を宣言する。

* `screenshots` -- 撮影対象の一覧 (`file` と `screen`)。
  `scripts/capture-readme-screens.mjs` が**同じ表**を読んで撮影する。
* `sources` / `source_exclude` -- スクショの見た目を決める source の glob。
* `sources_sha256` -- 上記 source 集合の内容ハッシュ。

CI は `sources` を解決して内容ハッシュを再計算し、`sources_sha256` と突合する。
不一致 = 「GUI を変えたのにスクショを撮り直していない」。

## fail-closed の 5 点

「検査が空回りして緑」を潰すため、以下はすべて exit 2 にする。

1. manifest が無い / JSON として壊れている
2. `sources` の解決結果が **0 件** (glob が rename で腐ると空集合同士が一致して
   永久に緑になる。最も危険な false-green)
3. `source_exclude` に **何にもマッチしないパターン**がある (腐った宣言)
4. `screenshots` の宣言と `image/[0-9][0-9]-*.png` の実体が**集合として不一致**
   (宣言し忘れたスクショは誰も鮮度を見ていない状態になる)
5. coverage 対象 (`gui/index.html` / `gui/vite.config.ts` / `gui/src/**`) に
   `sources` でも `source_exclude` でも拾われないファイルがある (新しい拡張子が
   黙って検査対象外になるのを防ぐ)

## この gate が見ていない集合

* **撮り直した画像が正しい画面・正しい状態を写しているかは検査しない。**
  `--update` は「撮り直した」という人間の申告を信じる仕組みであって、撮影の
  事実を検証しない。真っ黒な PNG を置いて `--update` を撃てば通る。
  これを CI 側で閉じるには GUI を CI で描画して突合するしかないが、撮影は
  決定的ではない (下記) ため画像の突合自体が成立しない。
  **ただし `--update` を撃たずに commit 済み PNG だけを差し替えた場合は
  `screenshots[].sha256` との不一致で赤になる** (Codex adversarial-review
  2026-08-20 で「真っ黒な PNG を commit する事故」が指摘されたため追加)。
  検知できるのは「記録後に画像が変わった」ことまでで、「記録時の画像が正しい」
  ことではない。
* **画像の byte 同一性は検査しない。** そもそも撮影は決定的ではない。2026-08-20 の
  実測では、source を一切変えずに 2 回連続で撮影したとき
  `01-drop.png` / `03-complete.png` / `05-export.png` は byte 一致したが、
  `02-detecting.png` と `04-preview.png` は **毎回変わった** (進捗表示と
  video pane の描画タイミング依存)。画像ハッシュを契約にすると常時赤になる。
* **粒度が repo 全体である。** どの source がどのスクショに効くかは区別せず、
  `gui` 配下が 1 文字でも変われば **全スクショが赤**になる。意図的な選択で、
  per-screenshot の依存表は「子コンポーネントの変更を依存に入れ忘れる」穴
  (#944 が既知の限界として挙げた形) を必ず作るため、穴を作らない側に倒した。
  代償として GUI を触る PR は毎回 5 枚の撮り直しを要求される。
* **GUI 以外に起因する見た目の変化** -- フォント・OS・ブラウザ版・画面解像度は
  source に現れないため検知できない。
* **同梱 README.txt / docs 側の画像** -- 対象は `image/` 直下の連番 PNG のみ。

Refs: https://github.com/Idios/kobutachan-allaganeye/issues/944
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from collections.abc import Iterable, Sequence

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_STRUCTURAL = 2

MANIFEST_REL = "image/screenshot-manifest.json"
SCREENSHOT_GLOB = "[0-9][0-9]-*.png"
# SCREENSHOT_GLOB と同じ集合を名前側から縛る (書き込み先の検証に使う)。
_SCREENSHOT_NAME_RE = re.compile(r"[0-9]{2}-[a-z0-9-]+\.png")

# 鮮度の対象になる source の探索範囲。ここに入るファイルは `sources` か
# `source_exclude` のどちらかに必ず拾われなければならない (fail-closed 5)。
_COVERAGE_ROOTS = ("gui/src",)
_COVERAGE_FILES = ("gui/index.html", "gui/vite.config.ts")


class GuardStructureError(RuntimeError):
    """検査自体が成立しないときに送出する (exit 2)。"""


def load_manifest(repo_root: Path) -> dict[str, Any]:
    path = repo_root / MANIFEST_REL
    if not path.is_file():
        raise GuardStructureError(f"{MANIFEST_REL} が無い ({path})。")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GuardStructureError(
            f"{MANIFEST_REL} が JSON として壊れている: {exc}"
        ) from exc
    if not isinstance(manifest, dict):
        raise GuardStructureError(f"{MANIFEST_REL} の最上位が object でない。")
    for key, kind in (
        ("screenshots", list),
        ("sources", list),
        ("source_exclude", list),
    ):
        if not isinstance(manifest.get(key), kind):
            raise GuardStructureError(
                f"{MANIFEST_REL} の `{key}` が {kind.__name__} でない。"
            )
    for entry in manifest["screenshots"]:
        if not isinstance(entry, dict) or "file" not in entry or "screen" not in entry:
            raise GuardStructureError(
                f"{MANIFEST_REL} の screenshots に `file` / `screen` を持たない要素がある: {entry!r}"
            )
        # `file` は scripts/capture-readme-screens.mjs が
        # `resolve(IMAGE_DIR, file)` に渡して PNG を **書き込む** 先になる。
        # `../../x.png` や絶対パスは image/ の外を指し、既存ファイルを上書き
        # しうる (node の path.resolve で実測)。書き込み経路へ届く前に落とす。
        if not _SCREENSHOT_NAME_RE.fullmatch(entry["file"]):
            raise GuardStructureError(
                f"{MANIFEST_REL} の screenshots[].file `{entry['file']}` が"
                " image/ 直下の連番 PNG 名 (NN-name.png) になっていない。"
            )
    return manifest


def _validate_pattern(pattern: str) -> None:
    """repo 外へ出る glob を弾く。

    走査範囲が repo 内に閉じているのは `compute_digest` の `relative_to`
    が成り立つ前提である。絶対パスは `Path.glob` が `NotImplementedError`
    を投げて exit code 1 でも 2 でもない形で落ちるため、先に構造エラーへ倒す。
    """
    normalized = pattern.replace("\\", "/")
    head = normalized.split("/", 1)[0]
    if normalized.startswith("/") or ":" in head:
        raise GuardStructureError(
            f"glob `{pattern}` が絶対パスになっている。走査範囲は repo 内に限る。"
        )
    if ".." in normalized.split("/"):
        raise GuardStructureError(
            f"glob `{pattern}` が `..` で repo の外を指している。走査範囲は repo 内に限る。"
        )


def _expand(repo_root: Path, patterns: Iterable[str]) -> list[set[Path]]:
    """各 glob をそれぞれ解決する (パターン単位の空判定を残すため)。"""
    resolved: list[set[Path]] = []
    for pattern in patterns:
        _validate_pattern(pattern)
        resolved.append({p for p in repo_root.glob(pattern) if p.is_file()})
    return resolved


def resolve_sources(repo_root: Path, manifest: dict[str, Any]) -> list[Path]:
    """`sources` から `source_exclude` を差し引いた集合をソートして返す。"""
    excluded: set[Path] = set()
    for pattern, matched in zip(
        manifest["source_exclude"],
        _expand(repo_root, manifest["source_exclude"]),
        strict=True,
    ):
        if not matched:
            raise GuardStructureError(
                f"source_exclude のパターン `{pattern}` が 1 件もマッチしない。"
                " 腐った除外宣言は検査範囲を黙って狭めるため落とす。"
            )
        excluded |= matched

    included: set[Path] = set()
    for pattern, matched in zip(
        manifest["sources"], _expand(repo_root, manifest["sources"]), strict=True
    ):
        if not matched:
            raise GuardStructureError(
                f"sources のパターン `{pattern}` が 1 件もマッチしない。"
                " glob が腐ると空集合同士が一致して永久に緑になるため落とす。"
            )
        included |= matched

    resolved = sorted(included - excluded)
    if not resolved:
        raise GuardStructureError(
            "sources の解決結果が 0 件。「0 件と 0 件が一致した」で緑を返さない。"
        )
    return resolved


def _normalize_newlines(data: bytes) -> bytes:
    """CRLF / CR を LF に畳む。

    本 repo は `core.autocrlf=true` を使うため、同じ commit でも Windows の
    作業ツリーは CRLF、ubuntu runner の checkout は LF になる。改行をそのまま
    hash に含めると **手元で緑・CI で赤** が常に起きる (PR #976 の初回 CI で
    実際に発生)。同型の事故は #612 / #816 でも起きており、`.gitattributes` に
    対症の `eol=lf` が積まれている。ここでは hash 側を改行非依存にして根を断つ。

    `sources` は text の glob (html / ts / tsx / css) に限られるため、この
    正規化で意味のある差分が消えることはない。
    """
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def compute_digest(repo_root: Path, paths: Sequence[Path]) -> str:
    """path と内容の両方を含む安定ハッシュ。rename でも変わる。

    改行は正規化する (`_normalize_newlines` の docstring 参照)。
    """
    outer = hashlib.sha256()
    for path in sorted(paths):
        rel = path.relative_to(repo_root).as_posix()
        inner = hashlib.sha256(_normalize_newlines(path.read_bytes())).hexdigest()
        outer.update(f"{rel}\0{inner}\n".encode())
    return outer.hexdigest()


def check_screenshot_declarations(repo_root: Path, manifest: dict[str, Any]) -> None:
    declared = {entry["file"] for entry in manifest["screenshots"]}
    on_disk = {p.name for p in (repo_root / "image").glob(SCREENSHOT_GLOB)}
    missing = sorted(declared - on_disk)
    undeclared = sorted(on_disk - declared)
    if missing:
        raise GuardStructureError(
            f"manifest が宣言するスクショが image/ に無い: {', '.join(missing)}"
        )
    if undeclared:
        raise GuardStructureError(
            f"image/ にあるスクショが manifest に宣言されていない: {', '.join(undeclared)}"
            " (宣言し忘れたスクショは鮮度が誰にも見られない)"
        )


def check_screenshot_hashes(repo_root: Path, manifest: dict[str, Any]) -> list[str]:
    """commit 済み PNG が manifest 記録時から変わっていないかを見る。

    source hash だけでは「真っ黒な PNG を commit してしまった」事故を検知でき
    ない (Codex adversarial-review 2026-08-20)。各 PNG の sha256 を持つことで、
    **撮影後に画像が差し替わった**ことは検知できる。

    これは「その PNG が現在の GUI を写している」証明ではない。射程の限界は
    module docstring の「この gate が見ていない集合」を参照。
    """
    problems: list[str] = []
    for entry in manifest["screenshots"]:
        path = repo_root / "image" / entry["file"]
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        recorded = entry.get("sha256")
        if not recorded:
            problems.append(f"  - {entry['file']}: manifest に sha256 が無い")
        elif recorded != actual:
            problems.append(
                f"  - {entry['file']}: 記録 {recorded[:12]}... / 実体 {actual[:12]}..."
            )
    return problems


def check_coverage(
    repo_root: Path, manifest: dict[str, Any], resolved: Sequence[Path]
) -> None:
    """coverage 対象のファイルが 1 つ残らず宣言に拾われていることを確かめる。"""
    universe: set[Path] = set()
    for rel in _COVERAGE_FILES:
        path = repo_root / rel
        if path.is_file():
            universe.add(path)
    for rel in _COVERAGE_ROOTS:
        root = repo_root / rel
        if root.is_dir():
            universe |= {p for p in root.rglob("*") if p.is_file()}

    excluded: set[Path] = set()
    for matched in _expand(repo_root, manifest["source_exclude"]):
        excluded |= matched

    uncovered = sorted(universe - set(resolved) - excluded)
    if uncovered:
        listed = ", ".join(p.relative_to(repo_root).as_posix() for p in uncovered[:10])
        more = "" if len(uncovered) <= 10 else f" ... 他 {len(uncovered) - 10} 件"
        raise GuardStructureError(
            f"sources / source_exclude のどちらにも拾われないファイルがある: {listed}{more}"
            f"\n{MANIFEST_REL} の sources か source_exclude に追加すること"
            " (新しい拡張子が黙って検査対象外になるのを防ぐため)。"
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else ""
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="検査対象の repo ルート (既定: 本 script の 1 つ上)",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="再撮影後に sources_sha256 と各 PNG の sha256 を書き戻す"
        " (撮り直しとセットで使う)",
    )
    args = parser.parse_args(argv)
    repo_root: Path = args.repo_root.resolve()

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    try:
        manifest = load_manifest(repo_root)
        check_screenshot_declarations(repo_root, manifest)
        resolved = resolve_sources(repo_root, manifest)
        check_coverage(repo_root, manifest, resolved)
        actual = compute_digest(repo_root, resolved)
    except GuardStructureError as exc:
        print(f"ERROR: 検査自体が壊れている: {exc}", file=sys.stderr)
        return EXIT_STRUCTURAL

    recorded = manifest.get("sources_sha256")
    if args.update:
        manifest["sources_sha256"] = actual
        for entry in manifest["screenshots"]:
            png = repo_root / "image" / entry["file"]
            entry["sha256"] = hashlib.sha256(png.read_bytes()).hexdigest()
        # 原本を失わない順序で書く: temp へ書いてから os.replace で差し替える。
        # 途中で落ちても manifest が truncate された状態にはならない。
        target = repo_root / MANIFEST_REL
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        os.replace(tmp, target)
        print(
            f"OK: sources_sha256 ({actual[:12]}...、{len(resolved)} files) と"
            f" PNG {len(manifest['screenshots'])} 枚の sha256 を更新した"
        )
        return EXIT_OK

    hash_problems = check_screenshot_hashes(repo_root, manifest)
    if hash_problems:
        print(
            "ERROR: commit 済みのスクショが manifest 記録時から変わっている。\n",
            file=sys.stderr,
        )
        for problem in hash_problems:
            print(problem, file=sys.stderr)
        print(
            "\n意図した差し替えなら撮り直したうえで"
            " `python scripts/check_screenshot_freshness.py --update` を実行すること。",
            file=sys.stderr,
        )
        return EXIT_DRIFT

    if recorded != actual:
        print(
            "ERROR: GUI source が変わったのに README のスクショが撮り直されていない。\n",
            file=sys.stderr,
        )
        print(f"  manifest の sources_sha256: {recorded}", file=sys.stderr)
        print(f"  現在の source から再計算    : {actual}", file=sys.stderr)
        print(
            "\n撮り直し手順:"
            "\n  1. cd gui && npm run dev            (別ターミナルで起動したまま)"
            "\n  2. npm install --no-save playwright && npx playwright install chromium"
            "\n  3. node scripts/capture-readme-screens.mjs"
            "\n  4. python scripts/check_screenshot_freshness.py --update"
            f"\n\n契約の詳細は scripts/{Path(__file__).name} の docstring を参照。",
            file=sys.stderr,
        )
        return EXIT_DRIFT

    print(
        f"OK: スクショ {len(manifest['screenshots'])} 枚は現行の GUI source"
        f" ({len(resolved)} files) から撮られている"
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
