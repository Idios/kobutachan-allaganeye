# audit-prepare transactional crash recovery (Issue #800)

> brainstorming output: 2026-05-20
> follow-up to: Issue #798 / PR #801 (audit-{prepare,compare} reproducibility hardening)
> Codex finding origin: `/codex:adversarial-review` on `claude/audit-hardening-798` (2026-05-20)

## 1. 背景

Issue #798 で `scripts/audit-prepare.main()` を `<label>.new/` + `<label>.csv.new` 経由の atomic rename flow に書き直した (`scripts/audit-prepare.py:261-336`)。Codex adversarial-review が以下 2 つの crash window を指摘した:

- **W1**: `shutil.rmtree(per_boundary_dir)` 直後 / `per_boundary_dir_new.rename(per_boundary_dir)` 前
  - filesystem state: `per_boundary_dir` 不在 + 旧 `worksheet_csv`
  - 影響: 旧 worksheet が存在しない artifact dir を参照
- **W2**: `per_boundary_dir_new.rename(per_boundary_dir)` 直後 / `worksheet_csv_new.replace(worksheet_csv)` 前
  - filesystem state: 新 `per_boundary_dir` + 旧 `worksheet_csv`
  - 影響: 旧 worksheet が新 artifact dir を参照 (filesystem 上は consistent に見えるが内容 mismatch)

Issue #798 spec §3.2 / §9 で「Windows directory rename atomicity 限界は trade-off として受容」と記録し、`scripts/audit-prepare.py:304-332` のコメントブロックで明示済み。本 spec はその follow-up として transactional crash recovery を実装する。

## 2. 戦略

### 2.1 読み手の性質

`scripts/audit-compare.py` は `<label>/` も `<label>.csv` も読まない (`tests/baselines/v0.3.0/<label>.metadata.json` と `ground-truth/<label>.json` のみ消費)。worksheet を読むのは Idios (operator) のみ。これにより「機械が誤判定する」リスクは存在せず、設計目標は以下 2 点に絞れる:

- crash 発生を確実に検出する (filesystem state からは W2 を見分けられないため、別途 marker が必要)
- 次 `audit-prepare` run で auto-recover する (operator が `--verify` 等を手で叩く workflow は要らない)

### 2.2 採用案: tx-state sidecar + recovery-on-start (案 D)

`<label>.tx.json` を single source of truth として publish の進行状態を記録する。crash 後の次 run が `state == "swapping"` を検出したら artifacts + tx を全消去して regenerate する。

### 2.3 検討した代替案

| 案 | atomicity | UX 影響 | 実装複雑度 | 採否理由 |
| --- | --- | --- | --- | --- |
| A: manifest pointer (canonical file) | true atomic | operator path 変更 (`<label>-uuid/`) | 中 | dir browse ergonomics が壊れる |
| B: symlink/junction swap | near-atomic | Windows symlink 制限 (admin/dev mode 要) | 中 | cross-platform 信頼性低 |
| C: single archive (zip/tar) per epoch | true atomic | dir browse 不可 (operator 直接 PNG 参照不能) | 小 | operator UX を壊す |
| **D: tx-state sidecar + recovery-on-start** | detect+recover | 既存 layout 維持 | 小 | **採用** |

「真の atomic publish」(A/B/C) は人間 operator の workflow を壊す。読み手が機械でなく頻度も低いため、「crash 検出 + 次 run auto-recover」で十分。

## 3. 設計

### 3.1 ファイル構造

```text
worksheet/
├── obs-20260116/                # 既存: per-boundary artifact dir
├── obs-20260116.csv             # 既存: worksheet CSV
├── obs-20260116.tx.json         # 新規: transaction state (single source of truth)
├── obs-20260116.new/            # 既存: 生成中 temp dir
├── obs-20260116.csv.new         # 既存: 生成中 temp CSV
└── obs-20260116.tx.json.new     # 新規: tx-state 書き換え中 temp
```

### 3.2 tx-state schema (`<label>.tx.json`)

```json
{
  "schema_version": 1,
  "state": "consistent",
  "updated_at": "2026-05-20T12:34:56Z"
}
```

- `schema_version` (int): 将来 schema 変更時の forward compat
- `state` (str): `"consistent"` または `"swapping"` のいずれか
- `updated_at` (str): ISO 8601 UTC、debug / forensic 用 (recovery 判定には未使用)

以下のいずれも backwards-compat の観点で「不在扱い (= recovery 不要)」とする。warning は stderr に 1 行出力する (operator が「なぜ tx-state が無視されたか」を debug できるように):

- JSON parse fail (file 自体は存在するが parse 不能)
- top-level が dict でない
- `schema_version` が `1` でない (forward compat: 将来 schema_version=2 の baseline を v1 tool で読む場合に「too old」を通知)
- `state` が `"consistent"` / `"swapping"` 以外

file 自体が不在の場合は warn 不要 (legacy baseline / 初回 run の正常ケース)。

### 3.3 主要フロー (`audit-prepare.main()` 改修後)

```text
Step 0: Recovery-on-start (新規)
  tx = _read_tx_state(tx_path)
  if tx and tx.state == "swapping":
      # 前回 crash したので artifacts は信頼不能
      shutil.rmtree(per_boundary_dir, ignore_errors=True)
      worksheet_csv.unlink(missing_ok=True)
      tx_path.unlink(missing_ok=True)
  # `.new` 系は Step 1 で常に cleanup される

Step 1: Pre-clean .new residue (既存、変更なし)
  rmtree(per_boundary_dir_new, ignore_errors=True)
  worksheet_csv_new.unlink(missing_ok=True)
  per_boundary_dir_new.mkdir(parents=True, exist_ok=True)

Step 2: Generate into temp (既存、変更なし)
  [brightness CSV + PNG + worksheet CSV を .new に生成]
  on exception: cleanup .new + raise (既存)

Step 3: Atomic publish (改修)
  3a: _write_tx_state_atomic(tx_path, state="swapping")    # marker (atomic)
  3b: rmtree(per_boundary_dir) if exists                   # W1 window 開始
  3c: per_boundary_dir_new.rename(per_boundary_dir)        # W2 window 開始
  3d: worksheet_csv_new.replace(worksheet_csv)             # W2 window 終了
  3e: _write_tx_state_atomic(tx_path, state="consistent")  # commit (atomic)
```

`<label>.tx.json` 自身の書き込みは `<label>.tx.json.new` に書いてから `os.replace` する single-file atomic op (Windows + POSIX で保証)。これにより tx-state 自体は partial-write 不能。

### 3.4 Recovery 表 (全 crash point)

| crash 発生点 | filesystem state | tx.state | 次 run の振る舞い |
| --- | --- | --- | --- |
| Step 2 中 | `.new/` あり (または try/except で cleanup 済) | absent or "consistent" | Step 1 で `.new` 消去 → 通常通り再生成 |
| Step 3a 直後 | 旧 dir + 旧 csv + tx="swapping" | "swapping" | Step 0 で旧 dir + 旧 csv + tx 消去 → 再生成 |
| Step 3b 後 (W1) | dir 不在 + 旧 csv + tx="swapping" | "swapping" | Step 0 で旧 csv + tx 消去 → 再生成 |
| Step 3c 後 (W2) | 新 dir + 旧 csv + tx="swapping" | "swapping" | Step 0 で新 dir + 旧 csv + tx 消去 → 再生成 (新 dir も信頼しない) |
| Step 3d 後 (publish 直前) | 新 dir + 新 csv + tx="swapping" | "swapping" | Step 0 で全消去 → 再生成 (内容は正しいが tx 未 commit のため捨てる、wasteful だが safe) |
| Step 3e 後 (正常完了) | 新 dir + 新 csv + tx="consistent" | "consistent" | Step 0 何もしない、通常上書きで再生成 |
| tx.json corrupted (parse fail / 未知 state) | 任意 | unparseable | warn + None 扱い (= 無視)、通常 flow |
| tx.json 不在 (legacy baseline) | 旧 dir + 旧 csv | absent | Step 0 何もしない、通常上書きで再生成 (backwards compat) |

Step 3d 後 / 3e 前の "wasteful regenerate" は許容: audit-prepare の所要時間は 12 boundary × 数 100ms オーダーで再生成コストは低い。複雑な「正しさ判定」を入れるより単純 cleanup のほうが test しやすい。

### 3.5 audit-compare 側の変更

なし。worksheet を読まないため tx-state を見る必要がない。将来 audit-compare が worksheet を消費する場合に備えて helper を提供してもよいが、本 spec の scope 外 (YAGNI)。

## 4. 実装コンポーネント

| 場所 | 変更内容 |
| --- | --- |
| `scripts/audit-prepare.py` | `_read_tx_state` / `_write_tx_state_atomic` / `_recover_stale_artifacts` 関数を追加。`main()` に Step 0 と Step 3a/3e を組み込む |
| `tests/test_audit_prepare.py` | failure-injection tests を 6 件追加 (§5 参照) |
| `docs/v030-baseline-audit.md` | "Known limitation (Issue #800)" 節を「解消済み (#新 PR で fix)」に更新 |
| `scripts/audit-prepare.py:304-332` | step (3) コメントブロックを更新 (W1/W2 が tx-state で検出 + recover 可能になった旨を追記) |

### 4.1 Helper 関数 sketch

```python
_TX_STATE_FILENAME = "{label}.tx.json"
_TX_SCHEMA_VERSION = 1
_TX_STATE_CONSISTENT = "consistent"
_TX_STATE_SWAPPING = "swapping"


def _read_tx_state(tx_path: Path) -> dict[str, Any] | None:
    """Return parsed tx-state, or None if file missing / corrupted / unknown shape.

    Returning None always means "no committed transactional state" (= no
    recovery needed). Callers must not use None to distinguish "file missing"
    from "file corrupted"; both fall back to legacy behavior.

    Warns on stderr for any malformed case (parse fail / type mismatch /
    schema version mismatch / unknown state value) so the operator can
    debug why their tx-state was ignored. File-not-exist is the legacy /
    first-run case and is NOT warned.
    """
    if not tx_path.exists():
        return None
    try:
        data = json.loads(tx_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(
            f"WARNING: {tx_path} is unreadable ({exc}); treating as missing",
            file=sys.stderr,
        )
        return None
    if not isinstance(data, dict):
        print(
            f"WARNING: {tx_path} top-level is not an object; treating as missing",
            file=sys.stderr,
        )
        return None
    if data.get("schema_version") != _TX_SCHEMA_VERSION:
        print(
            f"WARNING: {tx_path} has unsupported schema_version "
            f"{data.get('schema_version')!r} (expected {_TX_SCHEMA_VERSION}); "
            "treating as missing",
            file=sys.stderr,
        )
        return None
    if data.get("state") not in (_TX_STATE_CONSISTENT, _TX_STATE_SWAPPING):
        print(
            f"WARNING: {tx_path} has unknown state {data.get('state')!r}; "
            "treating as missing",
            file=sys.stderr,
        )
        return None
    return data


def _write_tx_state_atomic(tx_path: Path, *, state: str) -> None:
    """Atomically write tx-state via temp file + os.replace.

    On POSIX and Windows, replace() of a single file is atomic, so the
    on-disk tx-state is never partially-written.
    """
    payload = {
        "schema_version": _TX_SCHEMA_VERSION,
        "state": state,
        "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    tx_new = tx_path.with_suffix(tx_path.suffix + ".new")
    tx_new.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tx_new.replace(tx_path)


def _recover_stale_artifacts(
    *,
    per_boundary_dir: Path,
    worksheet_csv: Path,
    tx_path: Path,
) -> None:
    """When tx-state == swapping on startup, wipe all artifacts.

    Called from main() Step 0. Idempotent. Does not raise on missing paths.
    """
    shutil.rmtree(per_boundary_dir, ignore_errors=True)
    worksheet_csv.unlink(missing_ok=True)
    tx_path.unlink(missing_ok=True)
```

### 4.2 `main()` 改修箇所

```python
def main(argv: list[str] | None = None) -> int:
    # ... (既存 argparse / metadata load / rows build) ...

    per_boundary_dir = args.worksheet_dir / args.recording_label
    per_boundary_dir_new = args.worksheet_dir / f"{args.recording_label}.new"
    worksheet_csv = args.worksheet_dir / f"{args.recording_label}.csv"
    worksheet_csv_new = args.worksheet_dir / f"{args.recording_label}.csv.new"
    tx_path = args.worksheet_dir / f"{args.recording_label}.tx.json"

    # Step 0: Recovery-on-start (新規)
    tx = _read_tx_state(tx_path)
    if tx is not None and tx["state"] == _TX_STATE_SWAPPING:
        print(
            f"WARNING: previous {args.recording_label} run crashed mid-publish; "
            "cleaning up stale artifacts before regenerating",
            file=sys.stderr,
        )
        _recover_stale_artifacts(
            per_boundary_dir=per_boundary_dir,
            worksheet_csv=worksheet_csv,
            tx_path=tx_path,
        )

    # Step 1: Pre-clean .new residue (既存)
    # ...

    # Step 2: Generate into temp (既存)
    # ...

    # Step 3: Atomic publish (改修)
    _write_tx_state_atomic(tx_path, state=_TX_STATE_SWAPPING)
    if per_boundary_dir.exists():
        shutil.rmtree(per_boundary_dir)
    per_boundary_dir_new.rename(per_boundary_dir)
    worksheet_csv_new.replace(worksheet_csv)
    _write_tx_state_atomic(tx_path, state=_TX_STATE_CONSISTENT)

    print(f"Worksheet: {worksheet_csv}", file=sys.stderr)
    print(f"Per-boundary artifacts: {per_boundary_dir}", file=sys.stderr)
    return 0
```

## 5. Testing (failure-injection)

`tests/test_audit_prepare.py` に以下を追加:

| test 名 | 注入点 | 期待 recovery |
| --- | --- | --- |
| `test_recovers_from_crash_after_rmtree` | Step 3b 後 (W1) | 次 run で全消去 → 完全 regenerate、最終 state は "consistent" |
| `test_recovers_from_crash_after_dir_rename` | Step 3c 後 (W2) | 次 run で全消去 → 完全 regenerate、最終 state は "consistent" |
| `test_recovers_from_crash_before_tx_commit` | Step 3d 後 (publish 直前) | 次 run で全消去 → 完全 regenerate、最終 state は "consistent" |
| `test_no_recovery_when_state_consistent` | crash なし | 通常上書き、最終 state は "consistent"、recovery WARNING ログなし |
| `test_tx_state_missing_legacy_compat` | tx.json 削除した古 baseline | 通常上書き、recovery WARNING ログなし |
| `test_tx_state_corrupted_treated_as_missing` | tx.json に invalid JSON / non-dict / 未知 schema_version / 未知 state の 4 variants (parametrize) | warn ログ出力 + 通常 flow |

### 5.1 Failure injection 手法

`monkeypatch.setattr` で `shutil.rmtree` / `Path.rename` / `Path.replace` をラップし、特定 path で 1 回だけ `RuntimeError("simulated crash")` を上げる。

```python
def _make_crashing_rmtree(target_path, original_rmtree):
    """Wrap shutil.rmtree to crash AFTER deleting target_path once."""
    crashed = {"value": False}

    def crashing_rmtree(path, *args, **kwargs):
        original_rmtree(path, *args, **kwargs)
        if not crashed["value"] and Path(path) == Path(target_path):
            crashed["value"] = True
            raise RuntimeError("simulated crash after rmtree")

    return crashing_rmtree
```

Step 3b 後 W1 のテストでは:

1. fixture で旧 dir + 旧 csv + tx="consistent" を準備
2. `shutil.rmtree` をラップし `per_boundary_dir` の削除直後に crash
3. `pytest.raises(RuntimeError): main([...])`
4. assert: tx.state == "swapping" / per_boundary_dir 不在 / worksheet_csv は旧のまま
5. monkeypatch を解除して `main([...])` を再度実行
6. assert: tx.state == "consistent" / per_boundary_dir + worksheet_csv が新しい内容で存在
7. WARNING ログに「previous ... crashed mid-publish」が含まれる

`test_recovers_from_crash_after_dir_rename` は `Path.rename` をラップ、`test_recovers_from_crash_before_tx_commit` は `Path.replace` をラップ (= csv replace 完了直後に crash) する。

### 5.2 既存 test の regression check

`tests/test_audit_prepare.py` の既存 3 件 (`test_main_atomic_success_replaces_old_artifacts` / `test_main_atomic_failure_preserves_old_artifacts` / `test_main_recovers_from_stale_new_dir`) は引き続き green であること。特に第 2 件は「失敗時に既存 artifacts が保持される」を確認しており、tx-state が swapping のまま残るので次 run で消去される動作と整合性確認が必要。

## 6. 受け入れ条件

1. `scripts/audit-prepare.main()` Step 3 開始時に `<label>.tx.json` を `state: "swapping"` で atomic 書き込みする
2. Step 3 完了時 (csv replace 直後) に `state: "consistent"` で atomic 書き込みする
3. `main()` Step 0 で tx.state == "swapping" を検出したら artifacts (`<label>/` + `<label>.csv` + `<label>.tx.json`) を全消去し、stderr に WARNING を出力する
4. tx.json 不在 / JSON parse fail / top-level non-dict / 未知 schema_version / 未知 state は backwards-compat で通常 flow を許容する (file 不在以外は stderr に WARNING 1 行を出力する)
5. tx-state 書き込みは `<label>.tx.json.new` 経由の `os.replace` で single-file atomic を保証する
6. failure-injection tests 6 件すべて green (W1 / W2 / before commit / no-crash / legacy / corrupted)
7. 既存 `test_audit_prepare.py` の 3 件が引き続き green
8. ruff check / ruff format --check / pyright / pytest tests/test_audit_prepare.py が全 green
9. `docs/v030-baseline-audit.md` の "Known limitation (Issue #800)" 節を「解消済み (#新 PR で fix)」に更新する
10. `scripts/audit-prepare.py:304-332` の step (3) コメントブロックを更新し、W1/W2 が tx-state で検出 + recover 可能になった旨を追記する
11. PR 作成 Pre-flight Step 5 で `/codex:adversarial-review` を実行し、additional crash window 指摘がゼロであることを確認する

## 7. Out of scope

- 「真の atomic publish」(manifest pointer / symlink / archive 案 A/B/C) — 案 D で要件を満たすため
- audit-compare 側の tx-state 読み込み — 現状 audit-compare は worksheet を読まないため YAGNI
- automatic cleanup of old `.tx.json` files — 1 ファイル per label で増えない、cleanup 不要
- multi-process concurrent `audit-prepare` の lock / coordination — 現状 operator が単一 process で順次実行する想定
- tx-state を audit doc / PR コメント等の外部に export する機能 — debug 時は手で `cat <label>.tx.json` すれば足りる
- Issue #797 (M6 end miss) — 別 issue、本 spec の scope 外
- M6 end miss を含む detector 改修一般 — Issue #797 系で別管理

## 8. 関連

- 親 audit issue: #796 (`docs/v030-baseline-audit.md`)
- predecessor hardening issue: #798 (PR #801 = merged commit `4cd3044`)
- predecessor spec: `docs/superpowers/specs/2026-05-20-audit-script-hardening-design.md` §3.2 Recovery 性 table / §9 Risks #1
- 該当コード: `scripts/audit-prepare.py:261-336` (atomic swap flow)

## 9. Risks register

| # | risk | mitigation |
| --- | --- | --- |
| 1 | tx-state file が部分書き込みされる | `.new` 経由の `os.replace` で single-file atomic を保証 (cross-platform) |
| 2 | tx-state が腐敗して通常 flow に戻れない | parse fail / 未知 schema / 未知 state は warn + None 扱い (= 通常 flow) で fallback |
| 3 | recovery が誤って正常 artifacts を消す | tx.state == "swapping" のときのみ recovery 実行。正常完了時は "consistent" を書くため発動しない |
| 4 | 単純な regeneration ループ (failure 後の retry も失敗) | Step 2 の生成失敗は try/except で `.new` cleanup + raise (= 既存挙動)。tx-state は "swapping" のまま残り、次 run の Step 0 で再度 cleanup される |
| 5 | concurrent `audit-prepare` 実行 | scope 外 (Out of scope §7)。operator は単一 process 想定 |
| 6 | legacy baseline (tx.json 不在) の動作変更 | 受け入れ条件 #4 で「通常 flow を許容」を明示。test `test_tx_state_missing_legacy_compat` で担保 |
| 7 | failure injection test が flaky になる | monkeypatch で deterministic に crash を注入。`Path.rename` / `Path.replace` の wrap は path 一致でのみ発動するため side-effect なし |
