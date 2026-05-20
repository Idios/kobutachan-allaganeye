# audit-{prepare,compare} reproducibility hardening (#798)

> **Status**: draft (brainstorming output)
> **Parent issue**: [#798](https://github.com/Idios/kobutachan-allaganeye/issues/798)
> **Predecessor spec**: [docs/superpowers/specs/2026-05-19-v030-baseline-audit-design.md](2026-05-19-v030-baseline-audit-design.md) (#796)
> **Delivered audit PR**: [#799](https://github.com/Idios/kobutachan-allaganeye/pull/799) (merged into `develop-0.3.0` as `d1b3ac3`)

## §1 背景

Issue #796 (v0.3.0 OBS baseline audit、PR #799) を Iron Law 6 Pre-flight Step 5 で `/codex:adversarial-review` に通した結果、Round 3 が medium 2 件を残した。Round 1 (high 2 + medium 2) と Round 2 (high 1 + medium 1) は全 fix 済みで、Round 3 finding は本 PR の deliverable (Iteration 1/2 完了、`tests/baselines/v0.3.0/ground-truth/obs-*.json` 5 件、`docs/v030-baseline-audit.md` 確定) には**影響しない**。convergence cycle を抑制するため follow-up issue #798 として独立 fix する判断を取った。

Round 3 finding は以下 2 件:

- **R3#1 (medium)**: `audit-compare.py:295-308` で `ALLAGANEYE_SAMPLE_VIDEO_DIR` 未設定 or video resolve 失敗時 `actual_source_size = None` となり、`validate_ground_truth_against_baseline` が `source_size_bytes` 比較を silently skip する。stale / 差し替え recording に対する audit を防げない
- **R3#2 (medium)**: `audit-prepare.py:268-292` で `shutil.rmtree(per_boundary_dir)` → 各 boundary export → 最後に worksheet write の順序。export 失敗時 artifact dir は消えた / 部分生成、worksheet は前 run のまま残り、atomic でない

future re-run (e.g., PR #793 merge 後の baseline regenerate に伴う audit 更新) で stale 状態を mask する穴を塞ぐ目的。

## §2 採用方針

- **R3#1**: `source_size_bytes` を REQUIRED ground-truth field 化 + audit-compare main で video resolve 失敗時 fail-close (exit code 3)。`--skip-source-size-check` flag で operator escape (stderr に WARNING 出力)
- **R3#2**: audit-prepare main を temp sibling dir + temp worksheet 経由の atomic rename / replace flow に書き直し。mid-run failure 時は既存 artifacts に触れず temp のみ cleanup
- **TDD**: 3 件 (R3#1 / R3#2 / `--skip-source-size-check` flag) のテストを Red-Green-Refactor で先に書く。failure injection は `monkeypatch` で `export_brightness_csv` / `export_sample_frames` を raise させる

## §3 設計

### §3.1 R3#1 — `source_size_bytes` REQUIRED 化 + fail-close

**変更箇所**: `scripts/audit-compare.py`

**Schema 強化**:

```python
_REQUIRED_GROUND_TRUTH_FIELDS = (
    "source_file",
    "source_dir_label",
    "tolerance_sec",
    "matches",
    "source_size_bytes",  # ← 追加 (R3#1)
)
```

既存 5 件の ground-truth file (`obs-2026{0116,0118,0119,0127,0209}.json`) はいずれも `source_size_bytes` を含むため migration 不要 (本 spec 起票時点で確認済み)。

**`validate_ground_truth_against_baseline` 強化**:

```python
def validate_ground_truth_against_baseline(
    baseline: dict[str, Any],
    ground_truth: dict[str, Any],
    *,
    recording_label: str | None = None,
    actual_source_size: int | None = None,
    skip_source_size_check: bool = False,  # ← 追加
) -> None:
    ...
    # source_size_bytes は REQUIRED field なので、ground_truth に必ず存在する。
    # ただし actual_source_size と突合するかは flag 次第。
    if not skip_source_size_check:
        if actual_source_size is None:
            raise ValueError(
                "actual_source_size is required for source_size_bytes validation. "
                "Set ALLAGANEYE_SAMPLE_VIDEO_DIR + ensure video resolves, "
                "or pass skip_source_size_check=True explicitly."
            )
            # Operators discover the CLI counterpart `--skip-source-size-check`
            # via `audit-compare --help`; the error message stays focused on
            # the programmatic escape route to avoid lying about the CLI flag
            # at intermediate commit boundaries.
        gt_size = ground_truth["source_size_bytes"]
        if gt_size != actual_source_size:
            raise ValueError(...)
```

**`main()` flow 変更**:

```python
parser.add_argument(
    "--skip-source-size-check",
    action="store_true",
    help="Skip source_size_bytes verification (operator escape; "
         "logged to stderr; ground-truth schema validation is NOT skipped).",
)

...

actual_source_size: int | None = None
sample_video_dir = os.environ.get("ALLAGANEYE_SAMPLE_VIDEO_DIR")
if sample_video_dir and "source" in baseline:
    video_candidate = Path(sample_video_dir) / baseline["source"]
    if video_candidate.exists():
        actual_source_size = video_candidate.stat().st_size

if args.skip_source_size_check:
    print(
        "WARNING: --skip-source-size-check is set; source_size_bytes "
        "verification skipped. Ground-truth schema validation still runs.",
        file=sys.stderr,
    )

try:
    validate_ground_truth_against_baseline(
        baseline,
        ground_truth,
        recording_label=args.recording_label,
        actual_source_size=actual_source_size,
        skip_source_size_check=args.skip_source_size_check,
    )
except ValueError as exc:
    print(f"ERROR: {exc}", file=sys.stderr)
    return 3
```

**Exit code mapping (変更なし、運用拡張)**:

| Code | 意味 | 該当ケース |
| --- | --- | --- |
| 0 | 正常終了 | validation 成功 + findings 出力 |
| 2 | input file 不在 | baseline / ground-truth file 欠落 |
| 3 | validation 失敗 | schema 違反 / source 不一致 / size 不一致 / **video resolve 失敗 (新規 R3#1)** |

### §3.2 R3#2 — atomic rename flow

**変更箇所**: `scripts/audit-prepare.py` の `main()`

**現状 flow (broken)**:

1. `shutil.rmtree(per_boundary_dir)` で旧 artifacts 即時削除
2. 各 boundary に対し `export_brightness_csv` + `export_sample_frames` を `per_boundary_dir` 直書き
3. 最後に `write_worksheet_csv(rows, worksheet_csv)`

step 2 で例外発生時: per_boundary_dir は partial / 空、worksheet_csv は前 run の stale 状態。

**新 flow (atomic)**:

```python
per_boundary_dir = args.worksheet_dir / args.recording_label
worksheet_csv = args.worksheet_dir / f"{args.recording_label}.csv"
per_boundary_dir_new = args.worksheet_dir / f"{args.recording_label}.new"
worksheet_csv_new = args.worksheet_dir / f"{args.recording_label}.csv.new"

# (1) 前 run の temp 残骸を片付け (旧 final artifacts には触れない)
if per_boundary_dir_new.exists():
    shutil.rmtree(per_boundary_dir_new)
worksheet_csv_new.unlink(missing_ok=True)

per_boundary_dir_new.mkdir(parents=True, exist_ok=True)

# (2) 全 artifact を temp に生成。失敗時は temp のみ cleanup、旧 artifacts は不変
try:
    for row in rows:
        ts = float(row["timestamp_sec"])
        export_brightness_csv(
            video_path=video_path,
            boundary_timestamp=ts,
            out_path=per_boundary_dir_new / row["brightness_csv_ref"],
            window_sec=args.window_sec,
            interval_sec=args.interval_sec,
        )
        export_sample_frames(
            video_path=video_path,
            boundary_timestamp=ts,
            out_dir=per_boundary_dir_new,
        )
    write_worksheet_csv(rows, worksheet_csv_new)
except Exception:
    if per_boundary_dir_new.exists():
        shutil.rmtree(per_boundary_dir_new)
    worksheet_csv_new.unlink(missing_ok=True)
    raise

# (3) 全 success: 旧を消して新を rename / replace (POSIX: atomic; Windows: replace は atomic、
#     dir rename は brief window あり)
if per_boundary_dir.exists():
    shutil.rmtree(per_boundary_dir)
per_boundary_dir_new.rename(per_boundary_dir)
worksheet_csv_new.replace(worksheet_csv)
```

**Atomicity 保証範囲**:

- **POSIX**: `Path.rename` / `Path.replace` は同一 filesystem 内で atomic (renameat2)
- **Windows**: `Path.replace` (= `os.replace`) は file に対して atomic (`MoveFileExW` with `MOVEFILE_REPLACE_EXISTING`)。directory に対しては rmtree → rename の 2 step。step 間で process crash すると per_boundary_dir 不在 + per_boundary_dir_new 残存 (recoverable: 次 run の (1) で per_boundary_dir_new を rmtree、Idios が再 run でクリーン状態)
- 「mid-run failure で旧 artifacts + worksheet が混ざる」現状の broken 状態は解消、悪化はしない (= 失敗時は旧 artifacts intact)

**Recovery 性**: process crash 後の状態は以下のいずれか、いずれも `audit-prepare.py` の次回 run で正しく回復する。

| Crash 位置 | per_boundary_dir | worksheet_csv | per_boundary_dir_new | worksheet_csv_new |
| --- | --- | --- | --- | --- |
| (2) artifact 生成中 | 旧 (intact) | 旧 (intact) | partial → cleanup | 不在 → cleanup |
| (3) 旧 rmtree 直後 / dir rename 前 | 不在 | 旧 (intact) | 完全 | 完全 |
| (3) dir rename 後 / csv replace 前 | 新 (rename 完了) | 旧 | 不在 | 完全 |
| (3) csv replace 後 | 新 | 新 | 不在 | 不在 |

中間状態 3 種いずれも次 run で `per_boundary_dir_new` / `worksheet_csv_new` を rmtree / unlink して再生成すれば収束。「worksheet と per_boundary_dir の不整合」が永続化しない (= 旧側で揃うか新側で揃うか、混ざらない)。

### §3.3 影響範囲

- `tests/baselines/v0.3.0/ground-truth/obs-*.json` 5 件: 全件 `source_size_bytes` 既存のため schema migration 不要 (本 spec 起票時点で確認済み)
- `tests/baselines/v0.3.0/audit-worksheet/` 生成物: 新 atomic flow で再生成すれば同一内容 (worksheet 列・PNG・brightness CSV のセマンティクスは変更なし)
- `docs/v030-baseline-audit.md`: 内容変更不要 (audit 結論は変わらず)。本 spec PR で audit doc に "R3#1/R3#2 #798 で解消" 旨を追記する

## §4 Components (files touched)

| ファイル | 変更内容 |
| --- | --- |
| `scripts/audit-compare.py` | `_REQUIRED_GROUND_TRUTH_FIELDS` 拡張 / `validate_ground_truth_against_baseline` に `skip_source_size_check` parameter 追加 / `main()` で fail-close + `--skip-source-size-check` flag handling |
| `scripts/audit-prepare.py` | `main()` を temp sibling + atomic rename flow に書き直し |
| `tests/test_audit_compare.py` | R3#1 のテスト 4 件追加 |
| `tests/test_audit_prepare.py` | R3#2 のテスト 3 件追加 |
| `docs/v030-baseline-audit.md` | retrospect 節に "R3#1/R3#2 解消 (#798)" 1 行追記 |

## §5 Testing strategy

### §5.1 R3#1 tests (`tests/test_audit_compare.py`)

1. **test_validate_rejects_missing_source_size**: `source_size_bytes` を持たない ground-truth で `validate_ground_truth_against_baseline` が `ValueError` raise (REQUIRED field 化の確認)
2. **test_validate_rejects_none_actual_size_when_check_enabled**: `actual_source_size=None` + `skip_source_size_check=False` で `ValueError` raise
3. **test_validate_skip_flag_bypasses_size_check**: `skip_source_size_check=True` で `actual_source_size=None` でも other validation のみ実行 + ValueError なし
4. **test_main_video_unresolved_fails_close**: `monkeypatch.delenv("ALLAGANEYE_SAMPLE_VIDEO_DIR")` で `main()` が exit code 3 を return
5. **test_main_skip_flag_proceeds_without_video**: `--skip-source-size-check` を argv に渡すと video 不在でも exit 0 + stderr に WARNING

### §5.2 R3#2 tests (`tests/test_audit_prepare.py`)

1. **test_main_atomic_failure_preserves_old_artifacts**:
   - 事前に `per_boundary_dir/obs-fake/frame-around-100.000.png` + `obs-fake.csv` を sentinel 内容で配置
   - `monkeypatch.setattr(mod, "export_sample_frames", side_effect=RuntimeError)`
   - `main()` が raise したあと、旧 sentinel が残っていることを確認
   - `per_boundary_dir_new` (`.new` suffix) が cleanup されていることを確認
2. **test_main_atomic_success_replaces_old_artifacts**:
   - 事前に旧 sentinel を配置
   - `main()` が exit 0、新 PNG / brightness / worksheet に置き換わっていることを確認 (sentinel は消えている)
   - `per_boundary_dir_new` / `worksheet_csv_new` (`.new` suffix) が temp 状態でなく cleanup されていることを確認
3. **test_main_recovers_from_stale_new_dir**:
   - 事前に `per_boundary_dir_new` に partial junk を仕込んでおく (前 run crash 想定)
   - `main()` を回す → step (1) の cleanup で junk が rmtree され、cleanly succeed することを確認

### §5.3 既存テストの retention

`tests/test_audit_prepare.py::test_main_writes_worksheet_csv` などの既存 11 件 + `tests/test_audit_compare.py` の既存 14 件は temp-suffix 経路でも振る舞いが変わらないため引き続き pass する。`monkeypatch.setattr(mod, "export_brightness_csv" / "export_sample_frames", lambda **kw: None)` で stub している既存テストは新 flow でも同等に動く (stub 呼び出しが temp dir に向くだけで semantics 変化なし)。

## §6 受け入れ条件

| # | 条件 | 実証 |
| --- | --- | --- |
| 1 | `_REQUIRED_GROUND_TRUTH_FIELDS` に `source_size_bytes` 含まれる | `scripts/audit-compare.py:27-32` grep |
| 2 | source_size_bytes 欠落 ground-truth で `validate` が `ValueError` raise | `test_validate_rejects_missing_source_size` PASS |
| 3 | `ALLAGANEYE_SAMPLE_VIDEO_DIR` 未設定 / video 不在で `audit-compare` main が exit 3 | `test_main_video_unresolved_fails_close` PASS |
| 4 | `--skip-source-size-check` で size check skip + stderr WARNING + 他 schema validation 維持 | `test_main_skip_flag_proceeds_without_video` PASS + `test_validate_skip_flag_bypasses_size_check` PASS |
| 5 | `audit-prepare` mid-run failure → 旧 artifacts intact + temp cleanup | `test_main_atomic_failure_preserves_old_artifacts` PASS |
| 6 | `audit-prepare` success → 旧 artifacts atomic 置換 + temp cleanup | `test_main_atomic_success_replaces_old_artifacts` PASS |
| 7 | 前 run crash 由来の stale `.new` dir で次 run が cleanly recover | `test_main_recovers_from_stale_new_dir` PASS |
| 8 | 全テスト pass: `python -m pytest tests/test_audit_*.py -v`、`ruff check .`、`ruff format --check .`、`pyright` | CI green (Iron Law 6 サブ条) |
| 9 | Codex `/codex:adversarial-review` を PR Pre-flight Step 5 で実行、finding ゼロまたは finding を本 PR 内 (A) で fix | PR description に Codex round 結果記録 |

## §7 Out of scope (defer)

- **#797 obs-20260116 M6 end detector tuning**: PR #793 (#576 fps filter retirement) の merge 後の実機検証が前提のため、別 brainstorming/spec/plan session で扱う。本 spec は detector path を変更しない
- **PNG file overwriting** (audit doc §retrospect item 4): adjacent boundary で同 timestamp の PNG が overwrite される (obs-20260116 M3 end + M4 start = 3367.125)。audit doc に「未対応、低 impact」と明示済、issue #798 本文 §「調査範囲」に含まれない。本 PR で touch する `audit-prepare.main()` 周辺の改修と隣接するが、Iron Law 3 を踏襲し本 spec ではスコープ外。将来必要になれば別 issue を起票
- **ground-truth schema migration (新 field 追加)**: source_size_bytes 以外の field (source_duration, source_fps 等の REQUIRED 化) は本 spec 対象外
- **audit pipeline の e2e regression テスト化**: `slow` marker + 実 video が必要なため別 issue
- **`audit-compare.py` の output 形式変更** (例: CSV / JSON 出力追加): 本 spec はバリデーション層のみ touch

## §8 関連

- 親 issue: [#798](https://github.com/Idios/kobutachan-allaganeye/issues/798)
- audit deliverable PR: [#799](https://github.com/Idios/kobutachan-allaganeye/pull/799) (merged into `develop-0.3.0` as `d1b3ac3`)
- predecessor spec: [docs/superpowers/specs/2026-05-19-v030-baseline-audit-design.md](2026-05-19-v030-baseline-audit-design.md) (#796)
- audit doc: [docs/v030-baseline-audit.md](../../v030-baseline-audit.md)
- 並行 deferred issue: [#797](https://github.com/Idios/kobutachan-allaganeye/issues/797) (本 spec §7 で out of scope)
- PR #793 (#576 fps filter retirement): OPEN, develop-0.3.0 base, 本 spec の前提に含まれない
- workflow: [docs/l2-workflow.md](../../l2-workflow.md) §「PR 作成 Pre-flight」 (Iron Law 6 サブ条)

## §9 Risks / Open Questions

| # | リスク | 緩和策 |
| --- | --- | --- |
| 1 | Windows での directory rename atomic 保証なし (rmtree → rename の brief window) | §3.2 Recovery 性 table で全中間状態を recoverable に設計。次 run cleanup で確実に復旧 |
| 2 | `Path.replace` のディレクトリ対応が Python version 依存 (Python 3.9+ で OK、3.8 以下は file のみ) | プロジェクト要求 Python 3.10+ (pyproject.toml 確認、3.10 を前提)、影響なし |
| 3 | 新 atomic flow で `--workers` 並列化が将来必要になった場合 temp dir lock 競合 | 本 spec は逐次処理を維持 (現状の audit script も逐次)。並列化は別 issue |
| 4 | `--skip-source-size-check` が CI で誤って常用される | flag 名を明示的に長く (`--skip-source-size-check`) し、stderr WARNING を必須化。CI 設定での使用は git grep で検出可能 |
| 5 | ground-truth file を手動編集する operator が source_size_bytes を忘れて schema check で fail | error message に「set source_size_bytes to ffprobe size in bytes」を含めて即座に直せるよう誘導 |
