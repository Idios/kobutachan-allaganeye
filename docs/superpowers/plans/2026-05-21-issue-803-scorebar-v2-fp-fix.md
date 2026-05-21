# scorebar V2 post-match FP fix (#803) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** scorebar V2 detection の Rescue path が post-match content (Limsa / colorful interior) の彩度高領域を scorebar と誤検出する false positive (#803) を、span の width 上限 + 中央位置 gate で解消する。副次的に #797 (obs-20260116 M6 end miss) の束ね解決を狙う。

**Architecture:** `allaganeye/video/detector.py::_find_scorebar_horizontal_range` (Rescue path の動的 span 検出) に 2 つの gate を追加する。(1) span width が `_SCOREBAR_SCAN_MAX_WIDTH_PX` を超えたら reject、(2) span が画面中央 x=960 を含まなければ reject。Primary path (`_emblem_and_check` / `_EMBLEM_POSITIONS` 絶対座標) は無変更 (Phase 1 で zero FP を確認済)。span が gate で `None` になると `_has_scorebar_v2` は Rescue path を skip し、Primary path の結果 (post-match では False) が最終値になる。

**Tech Stack:** Python 3.12, numpy, opencv-python-headless, pytest, ruff, pyright

**Spec:** [docs/superpowers/specs/2026-05-21-issue-803-scorebar-v2-post-match-fp-fix-design.md](../specs/2026-05-21-issue-803-scorebar-v2-post-match-fp-fix-design.md) (§0 に Phase 1 実証データ・確定 root cause・確定 Fix)

---

## 確定済の前提 (Phase 1 investigation、spec §0)

- **root cause**: `_find_scorebar_horizontal_range` が span に下限 (`_SCOREBAR_SCAN_MIN_WIDTH_PX=500`) しか持たず、(a) 全幅 1912px すら accept (width 上限なし)、(b) 画面端 span (1410..1919 / 8..544) を accept (位置検証なし)
- **FP 実測 (obs-20260116)**: 6544-6555 span=1410..1919 (右端) / 6800-6850 span=8..1919 (全幅) / 6895 span=8..544 (左端)。いずれも `Primary=False / Rescue=True`
- **正常 span 実測**: in-match 600..1320 (width ~715、1080p OBS は最大 ~1090)、4K Game DVR ~613-620 (中央寄り、#522)
- **criteria 訂正 (spec §0.5)**: 6540 は scorebar HUD 残存のため `True` が正しい。`False` を返すべきは 6541 (Limsa ワープ後の消失点)。消失点 6540-6541 は ground truth M6 end 6540 と一致

## File Structure

- **Modify** `allaganeye/video/detector.py`
  - 定数 `_SCOREBAR_SCAN_MAX_WIDTH_PX` を `_SCOREBAR_SCAN_MIN_WIDTH_PX` の近く (line ~1011-1018) に追加
  - `_find_scorebar_horizontal_range` (line ~1073-1141) の末尾に width 上限 gate + 中央位置 gate を追加
- **Modify** `tests/test_scorebar_v2.py`
  - `TestFindScorebarHorizontalRange` に新 gate test 4 件を追加
  - `TestHasScorebarV2` に統合 test 2 件を追加
  - 既存 `test_two_disjoint_regions_returns_longest` を新 gate に合わせて更新 (現状の `(100,700)` は中央 960 を含まず gate で None になるため)
- **Modify** `CHANGELOG.md` — `## [Unreleased]` に `### Fixed` を追加 (現状なし) して #803 entry
- **Modify** `docs/v030-baseline-audit.md` — #797 status を Phase 5/5' 結果で更新 (Task 5)
- **Delete (untracked)** `scripts/debug-scorebar-v2-fp.py` — throw-away、PR 提出前に削除 (Task 5)

---

## Task 1: Rescue span gating (#803 core)

スコープは `_find_scorebar_horizontal_range` への 2 gate 追加と、その unit / 統合 test。Primary path は触らない。

**Files:**
- Modify: `allaganeye/video/detector.py` (定数 + `_find_scorebar_horizontal_range`)
- Test: `tests/test_scorebar_v2.py`

- [ ] **Step 1: 失敗する test を追加する**

`tests/test_scorebar_v2.py` の `class TestFindScorebarHorizontalRange:` の末尾 (`test_opencv_unavailable_returns_none` メソッドの直前、line ~253 あたり) に以下 4 メソッドを追加:

```python
    def test_overwide_band_returns_none(self):
        """Near-full-width band (post-match interior) -> None (#803).

        obs-20260116 t=6800/6850: a colorful interior produces a ~1912px
        saturated band at screen top. A real FL scorebar tops out at
        ~1090px (1080p OBS), so this is gated out by width.
        """
        # 8..1919 -> width 1912 >> _SCOREBAR_SCAN_MAX_WIDTH_PX (1440)
        frame = _make_hires_frame_with_strip(8, 1919)
        assert _find_scorebar_horizontal_range(frame) is None

    def test_right_edge_band_returns_none(self):
        """Right-side band not straddling center (chat panel) -> None (#803).

        obs-20260116 t=6544-6555 (Limsa): a chat panel at 1410..1919.
        Width 510 passes the min-width floor but the band does not contain
        screen center x=960, so it is gated out by position.
        """
        frame = _make_hires_frame_with_strip(1410, 1919)
        assert _find_scorebar_horizontal_range(frame) is None

    def test_left_edge_band_returns_none(self):
        """Left-side band not straddling center (minimap) -> None (#803).

        obs-20260116 t=6895: a left-side widget at 8..544. Width 537
        passes the min-width floor but does not contain center x=960.
        """
        frame = _make_hires_frame_with_strip(8, 544)
        assert _find_scorebar_horizontal_range(frame) is None

    def test_centered_band_within_max_width_returns_range(self):
        """Centered in-match-like band within bounds -> range returned (#803 guard).

        Regression guard: a normal in-match span (600..1320, width 721,
        straddles center 960, < max) must still be accepted.
        """
        frame = _make_hires_frame_with_strip(600, 1320)
        assert _find_scorebar_horizontal_range(frame) == (600, 1320)
```

`class TestHasScorebarV2:` の末尾 (`test_thresholds_are_documented_constants` の直前、line ~371 あたり) に以下 2 メソッドを追加:

```python
    def test_offcenter_layout_returns_false_after_gating(self):
        """Emblem-like features at a right-edge layout -> span gated -> False (#803).

        Simulates post-match content (obs-20260116 t=6555 Limsa chat panel):
        a saturated band with emblem-like features at the screen edge.
        Primary absolute path finds no emblems at 600/828/1263; the Rescue
        path's span (1410..1919) is rejected by the center gate, so V2
        returns False instead of a false positive.
        """
        frame = _make_hires_frame_with_emblems_at_layout(1410, 1919)
        assert _has_scorebar_v2(frame) is False

    def test_overwide_layout_returns_false_after_gating(self):
        """Emblem-like features spread across near-full width -> False (#803).

        Simulates obs-20260116 t=6800/6850 (colorful interior). Rescue
        span (~8..1919) is rejected by the width gate; Primary finds no
        emblems at the absolute positions -> False.
        """
        frame = _make_hires_frame_with_emblems_at_layout(8, 1919)
        assert _has_scorebar_v2(frame) is False
```

- [ ] **Step 2: test を実行して失敗を確認する**

Run: `pytest tests/test_scorebar_v2.py -k "overwide or edge_band or centered_band_within or offcenter_layout or overwide_layout" -v`

Expected: 6 件中、少なくとも `test_overwide_band_returns_none` / `test_right_edge_band_returns_none` / `test_left_edge_band_returns_none` / `test_offcenter_layout_returns_false_after_gating` / `test_overwide_layout_returns_false_after_gating` が FAIL (gate 未実装なので span が返り `assert ... is None` / `is False` が満たされない)。`test_centered_band_within_max_width_returns_range` は現状でも PASS する可能性がある (regression guard なので可)。

- [ ] **Step 3: width 上限の定数を追加する**

`allaganeye/video/detector.py` の `_SCOREBAR_SCAN_MIN_WIDTH_PX = 500` の docstring 直後 (`_SCOREBAR_SCAN_MAX_GAP_PX = 80` の定義の前) に以下を追加:

```python
_SCOREBAR_SCAN_MAX_WIDTH_PX = 1440
"""Maximum detected span (pixels) to accept as scorebar.

1080p OBS scorebar tops out at ~1090 px and 4K Game DVR at ~620 px
(#522).  Post-match content (Limsa exterior, colorful interiors) can
produce a near-full-width saturated band (observed ~1912 px on
obs-20260116 at t=6800/6850), which is not a scorebar.  1440 px (75% of
the 1920 px probe width) clears the real ~1090 px maximum with margin
while rejecting the ~1912 px false positive (#803).
"""
```

- [ ] **Step 4: `_find_scorebar_horizontal_range` に gate を追加する**

`allaganeye/video/detector.py` の `_find_scorebar_horizontal_range` 末尾の以下のブロック:

```python
    longest = max(merged, key=lambda r: r[1] - r[0])
    span_width = longest[1] - longest[0] + 1
    if span_width < _SCOREBAR_SCAN_MIN_WIDTH_PX:
        return None

    return longest
```

を、以下に置き換える:

```python
    longest = max(merged, key=lambda r: r[1] - r[0])
    span_width = longest[1] - longest[0] + 1
    if span_width < _SCOREBAR_SCAN_MIN_WIDTH_PX:
        return None
    # Reject implausibly wide spans (#803): a real FL scorebar tops out at
    # ~1090 px (1080p OBS).  A near-full-width band (e.g. ~1912 px from a
    # colorful post-match interior) is not a scorebar.
    if span_width > _SCOREBAR_SCAN_MAX_WIDTH_PX:
        return None
    # Reject spans that do not straddle screen center (#803): the FL
    # scorebar is horizontally centered, so an edge-confined band (e.g. a
    # right-side chat panel at 1410..1919 or a left-side widget at 8..544)
    # is not a scorebar.
    center_x = _SCOREBAR_V2_PROBE_WIDTH // 2
    if not (longest[0] <= center_x <= longest[1]):
        return None

    return longest
```

- [ ] **Step 5: 新 test を実行して PASS を確認する**

Run: `pytest tests/test_scorebar_v2.py -k "overwide or edge_band or centered_band_within or offcenter_layout or overwide_layout" -v`

Expected: 6 件すべて PASS。

- [ ] **Step 6: 新 gate で壊れる既存 test を更新する**

`tests/test_scorebar_v2.py` の `test_two_disjoint_regions_returns_longest` (現状 `(100,700)` を期待) は、longest run `(100,700)` が中央 960 を含まないため新 gate で `None` になる。以下に置き換える:

```python
    def test_two_disjoint_regions_returns_longest(self):
        """Two far-apart regions -> only the larger one returned.

        The longest run must also satisfy the #803 gates (straddle center,
        within max width), so the larger region is centered here.
        """
        # (700, 1300) width 601 + (1500, 1700) width 201
        # gap = 1500 - 1300 - 1 = 199 > MAX_GAP_PX (80) -> not bridged.
        # Longest (700, 1300) straddles center 960 and is within max width.
        frame = _make_hires_frame_with_strips([(700, 1300), (1500, 1700)])
        result = _find_scorebar_horizontal_range(frame)
        assert result == (700, 1300)
```

- [ ] **Step 7: scorebar test を全件実行して PASS を確認する**

Run: `pytest tests/test_scorebar_v2.py tests/test_scorebar.py tests/test_scorebar_regression.py tests/test_detector.py -v`

Expected: 全件 PASS (新 6 件 + 更新した `test_two_disjoint_regions_returns_longest` + 既存全件)。FAIL があれば、その test が中央位置/width gate と矛盾していないか確認 (Step 6 同様に正常 span を中央寄せ + max width 内に修正、ただし test の意図を保つこと)。

- [ ] **Step 8: lint と型チェックを実行する**

Run: `ruff check allaganeye/video/detector.py tests/test_scorebar_v2.py && ruff format --check allaganeye/video/detector.py tests/test_scorebar_v2.py && pyright allaganeye/video/detector.py`

Expected: いずれも error なし。`ruff` が PATH にない場合は `python -m ruff` を使う。

- [ ] **Step 9: commit する**

```bash
git add allaganeye/video/detector.py tests/test_scorebar_v2.py
git commit -m "$(cat <<'EOF'
fix(detector): scorebar V2 Rescue span を width 上限 + 中央位置で gate (Refs #803)

post-match content (Limsa / colorful interior) の彩度高領域を Rescue path が
scorebar と誤検出する FP を解消。_find_scorebar_horizontal_range に
(1) span width <= _SCOREBAR_SCAN_MAX_WIDTH_PX (1440)、(2) span が画面中央
x=960 を含む、の 2 gate を追加。Primary path は無変更 (zero FP 維持)。

obs-20260116 の FP span (右端 1410..1919 / 全幅 8..1919 / 左端 8..544) を
全 reject、in-match (600..1320) と 4K Game DVR (#522、~615 中央寄り) は通す。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Phase 3 regression — 5 baseline audit-compare (実機、Idios 依頼)

Iron Law 6 の実機検証 trigger (detector.py logic 変更)。mock 不可。Idios の RTX 5090 環境で 5 baseline を再 detect して ground truth と比較する。

**Files:** なし (実機検証のみ)

- [ ] **Step 1: 5 baseline を再 detect + compare する (Idios 実機)**

Run (各 label について、`ALLAGANEYE_SAMPLE_VIDEO_DIR` 設定済の前提):

```bash
for label in obs-20260116 obs-20260118 obs-20260119 obs-20260127 obs-20260209; do
  python scripts/audit-prepare.py "$label"
  python scripts/audit-compare.py "$label"
done
```

(Windows cmd では `for /L` ではなく 5 回個別実行、または PowerShell の `foreach`。各 detect は GPU で ~12min wall、計 ~1h。)

Expected:
- **obs-20260118 / 119 / 127 / 209**: 変更前と同じ agreed 数を維持 (それぞれ 12/12, 18/18, 6/6, 6/6 agreed、boundary_shift / silent_miss / false_positive = 0)
- **obs-20260116**: post-match (6555-6850) の Rescue FP が解消され、M6 が動画末尾まで伸びる誤分類が改善方向に変わる。M6 end は #803 単独では 6540-6541 (= scorebar 消失点) 付近に近づくが、V6.2 (Task 4) 未導入時は in-match 分類 logic 次第。最低限、変更前 (53/54 agreed) を下回らないこと

- [ ] **Step 2: 既存 5 baseline の scorebar 分類カウントを確認する (Idios 実機)**

変更前後で scorebar 分類 (12 match_boundary / 10 in_match / 2 non_fl) が保持されることを確認。`audit-compare.py` の出力 (category counts) を変更前と突き合わせる。

Expected: 分類カウントに regression なし。1 件でも変化したら Task 1 の gate 閾値 (1440 / 中央条件) を再調整 (`_SCOREBAR_SCAN_MAX_WIDTH_PX` を上げる等)。判断点が出たら AskUserQuestion (Iron Law 5)。

- [ ] **Step 3: 結果を記録する**

実機結果 (audit-compare の category counts、obs-20260116 の M6 boundary 値) を Task 5 の PR 本文 Self-Test Report に貼るためテキストで保存。

---

## Task 3: CHANGELOG 更新

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: `### Fixed` セクションに #803 entry を追加する**

`CHANGELOG.md` の `## [Unreleased]` 内、`### Changed` の前 (または `### Added` の後) に `### Fixed` セクションを新設 (現状なし) し、以下を記載:

```markdown
### Fixed

- **detect (scorebar V2)**: post-match content (試合終了後の Limsa /
  colorful interior 等) の彩度高領域を Rescue path が scorebar と誤検出
  する false positive を解消 (#803)。`_find_scorebar_horizontal_range` に
  span width 上限 (`_SCOREBAR_SCAN_MAX_WIDTH_PX=1440`) と中央位置要求
  (span が画面中央 x=960 を含む) の 2 gate を追加。obs-20260116 で試合終了
  (6540) 直後の post-match 区間 (6544-6850) が試合内と誤分類されていた問題
  を修正。Primary path (絶対座標 emblem) は無変更。
```

- [ ] **Step 2: commit する**

```bash
git add CHANGELOG.md
git commit -m "$(cat <<'EOF'
docs(changelog): scorebar V2 post-match FP fix を Fixed に記載 (Refs #803)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4 (条件付き、#797): V6.2 二分探索の再導入

**前提:** Task 2 (Phase 3) が pass し、Idios が「#797 の束ねを進める」と判断した場合のみ着手する。Phase 3 で #803 単独でも M6 end が改善する場合や、収束見込みが不確実な場合は本 Task を skip し Task 5 を Phase 5' (#803 単独 PR) で進める。

本 Task の complete code は、revert された commit `f7f8879` の中身に依存するため、**着手時に以下の調査 step を先に実施してから詳細を確定する** (現時点では V6.2 の正確な diff が未確認のため complete code を確定できない)。

- [ ] **Step 1: revert された V6.2 実装を確認する**

Run: `MSYS_NO_PATHCONV=1 git show f7f8879`

(MSYS path 変換回避は memory feedback 参照。) V6.2 (scorebar HUD 二分探索) の追加箇所・関数・呼び出し元を把握する。`22c8979` (revert commit) も `git show 22c8979` で確認。

- [ ] **Step 2: V6.2 を現 main (Task 1 gate 適用後) に再適用する**

`f7f8879` の logic を cherry-pick または手動再実装する。Task 1 の gate 追加と conflict する場合は解決。二分探索が「`_has_scorebar_v2` が True→False に切り替わる timestamp」を `[match_start, video_end]` で探す実装を確認・修正する。

- [ ] **Step 3: TDD で二分探索の unit test を追加する**

二分探索ロジックの unit test (synthetic な scorebar-present 判定関数を mock し、境界 timestamp に収束することを確認) を `tests/` の該当ファイルに追加。`f7f8879` 確認後に test 対象関数のシグネチャを確定して complete code を書く。

- [ ] **Step 4: obs-20260116 で M6 end の収束を実機検証する (Idios)**

Run: `python scripts/audit-prepare.py obs-20260116 && python scripts/audit-compare.py obs-20260116`

Expected: M6 end が `6540 ±5s` (= 6535-6545) に収束。収束すれば Task 5 を Phase 5 (束ね PR) で進める。**収束しなければ** V6.2 を再 revert し、Task 5 を Phase 5' (#803 単独 PR) で進め、`docs/v030-baseline-audit.md` に「V2 gating 後も V6.2 で 6540±5s に収束せず、別 root cause を v0.3.x で再調査」と記録 (Iron Law 5、独断で defer 理由を確定しない場合は AskUserQuestion)。

- [ ] **Step 5: commit する**

V6.2 再導入が収束した場合のみ。commit message に `Refs #797` を含める (Closes 禁止、Iron Law 4)。

---

## Task 5: PR 作成 (Phase 5 束ね or Phase 5' 単独)

**Files:**
- Modify: `docs/v030-baseline-audit.md` (#797 status)
- Delete (untracked): `scripts/debug-scorebar-v2-fp.py`

- [ ] **Step 1: throw-away debug script を削除する**

```bash
rm scripts/debug-scorebar-v2-fp.py
```

(untracked なので git からは外れない。PR に含めないための clean-up。)

- [ ] **Step 2: `docs/v030-baseline-audit.md` の #797 status を更新する**

Task 4 の結果に応じて記載:
- **収束 (束ね)**: #797 を「#803 の Rescue gating + V6.2 再導入で M6 end を 6540±5s に収束、PR で解決」と更新
- **非収束 (単独)**: #797 を「#803 で post-match FP は解消したが M6 end の 6540±5s 収束は別 root cause、v0.3.x で継続」と更新

commit:

```bash
git add docs/v030-baseline-audit.md
git commit -m "$(cat <<'EOF'
docs(audit): #797 status を #803 fix 結果で更新 (Refs #797 #803)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 3: Iron Law 6 PR Pre-flight を実行する**

```bash
gh pr list --search "803" --state open   # Step 0 ハードゲート
gh pr list --search "797" --state open
git fetch origin develop-0.3.0           # Step 1 base 同期
git log HEAD..origin/develop-0.3.0       # Step 2 取り込み未済 commit
gh pr list --search "803" --state all    # Step 4 並行 PR 重複
gh pr list --search "797" --state all
```

Step 3 (touched files 交差: `allaganeye/video/detector.py` / `tests/test_scorebar_v2.py` / `CHANGELOG.md` / `docs/v030-baseline-audit.md`) を手動確認。Step 5: `/codex:adversarial-review` を focus「Iron Law 3 scope / scorebar gate の 4K Game DVR (#522) regression / 中央位置 gate の境界 off-by-one / 同 issue 過去 PR (V6.2 revert) の root cause」で実行。

- [ ] **Step 4: 全自動チェックを実行する (PR 作成前)**

Run: `ruff check . && ruff format --check . && pyright && pytest`

Expected: 全 pass。Python のみの変更なので GUI job (npm lint/typecheck/test/build, cargo check) は該当なし (touched files に `gui/` を含まないことを Step 3 で確認済の前提)。`bash scripts/check-markdownlint.sh` で CHANGELOG / spec / plan / audit doc の markdownlint も pass させる。

- [ ] **Step 5: PR を作成する**

base は `develop-0.3.0`。title は Phase に応じて:
- **束ね**: `fix(detector): scorebar V2 post-match FP fix + HUD 二分探索 reintroduce (Refs #803 #797)`
- **単独**: `fix(detector): scorebar V2 post-match FP fix (Refs #803)`

PR 本文に必須:
- **Iron Law 1 逐条検証**: #803 (+ #797) の `## 受け入れ条件` 各項目を引用し、対応 diff / test を引用。**criteria 訂正の記録**: 「6540 で False」は実機で scorebar 残存と判明したため「6541 で False / 6540 は True」に訂正、根拠は spec §0.5 + Phase 1 実証データ
- **Self-Test Report**: `[x]` machine-verified (ruff / ruff format / pyright / pytest) と plain `-` machine-unverifiable (Task 2 の 5 baseline audit-compare 結果、Task 4 の M6 end 収束) を分離
- **Iron Law 4**: Closes/Fixes/Resolves キーワード禁止 (`Refs #803` のみ)
- session-id / `EXECUTOR:` directive (`docs/l2-workflow.md` §resume-plan handoff protocol)

- [ ] **Step 6: issue #803 に criteria 訂正コメントを投稿する**

PR 作成後、issue #803 に Phase 1 実証データ (6540=scorebar 残存 / 6541=消失、Rescue path 単独 FP) と criteria 訂正 (6540 で False → 6541 で False) を `gh issue comment` で記録 (Iron Law 5、独断で issue 本文を書き換えず、コメントで根拠を残す)。日本語本文は `printf | gh issue comment 803 --body-file -` または HEREDOC (memory feedback)。

---

## Self-Review

### Spec coverage

| spec 要件 | 対応 task |
| --- | --- |
| §0.4 Rescue span gating (width 上限 + 中央位置) | Task 1 Step 3-4 |
| §1.1 6541=False / 6450/6520/6540=True | Task 1 (unit/統合 test) + Task 2 (実機) |
| §1.1 5 baseline regression なし | Task 2 |
| §1.1 #522 / #307 regression なし | Task 1 Step 7 (既存 test) + Task 2 (#522 4K span 通過) |
| §0.5 criteria 訂正の記録 | Task 5 Step 5 (PR 本文) + Step 6 (issue コメント) |
| §3.4 Phase 4 V6.2 (#797) | Task 4 (条件付き) |
| §3.5/§3.6 Phase 5/5' PR | Task 5 |
| §4 TDD | Task 1 Step 1-5 (test 先行) |
| §5 CHANGELOG / debug script 削除 | Task 3 / Task 5 Step 1 |

### Placeholder scan

Task 1-3, 5 は complete code / exact command。Task 4 (V6.2) のみ `f7f8879` の中身に依存するため complete code を確定できず、調査 step (Step 1 で `git show`) を先頭に置く条件付き Task として明示分離 (spec §3.4 の optional 構造に対応)。これは placeholder ではなく段階的計画。

### Type consistency

- 新定数 `_SCOREBAR_SCAN_MAX_WIDTH_PX` (int, 1440) — Task 1 Step 3 で定義、Step 4 で参照、CHANGELOG (Task 3) / PR (Task 5) で言及。一貫
- `_SCOREBAR_V2_PROBE_WIDTH` (既存, 1920) — Task 1 Step 4 で `center_x = _SCOREBAR_V2_PROBE_WIDTH // 2` に使用 (既存 import 済、tests も import 済)
- test helper `_make_hires_frame_with_strip` / `_make_hires_frame_with_strips` / `_make_hires_frame_with_emblems_at_layout` — 既存定義を再利用 (新規定義なし)
