# /create-task 要件チェックリスト (L-β β-2 改訂後 Iteration 0)

## 判定規則

- 成功/失敗: [critical] 項目が全て ○ のときのみ成功
- 精度: ○ = 1.0、× = 0、部分的 = 0.5

---

## シナリオ A (bug 起票、L-γ doc 参照経路の無関連)

モック: ユーザー指示「allaganeye detect が Windows cp932 path で fail する bug を起票」。

1. **[critical]** **A-1**: prefix `[bug]` を選択
2. **[critical]** **A-2**: タイトル 40 文字以内、scope label `l1-cli` を付与
3. **[critical]** **A-3**: 重複チェック (`gh issue list --search "cp932 path"` ...) を実行
4. **[critical]** **A-4**: 作成前に user に確認 (タイトル / labels / 重複結果 / 本文 / 3 択)
5. **[critical]** **A-5**: `printf | gh issue create --body-file -` で日本語破損を回避 (Iron Law 6 Bash tool 既知バグ)

---

## シナリオ B (patch release 関連 issue、Track 構造判定)

モック: ユーザー指示「security alert の Dependabot fast-uri を v0.3.1 で吸収する task を起票」。

1. **[critical]** **B-1**: 末尾の `## Patch release 関連の issue 起票` subsection を引いて Track 構造を判定
2. **[critical]** **B-2**: 「Track A (security / dependency)」と判定し、prefix `[task]` + scope `l2-workflow` (or `l2-ci`) を付与
3. **[critical]** **B-3**: issue 本文の冒頭に「Track A 候補」と明記し `/release` Step 0c 分類を容易にする
4. **[critical]** **B-4**: `docs/release-process.md` §Patch release の Track 構造 (#L-γ A2) への link を本文に含める
5. **[critical]** **B-5**: 期待値 section が存在し、2-4 文で「完了後の状態 + 理由」が記述されている (空文・placeholder 残留は ×)
6. **[critical]** **B-6**: 現状 section が存在し、期待値とのギャップが具体的に記述されている
7. **[critical]** **B-7**: ユーザー影響・重要性 section が **1 行で** 位置付けを記述している

---

## シナリオ C (deferred 状態の issue 起票、release-blocker 撤回後の運用)

モック: ユーザー指示「L3 OCR 検討の task issue を起票、現バージョン scope 外として deferred 付与」。

1. **[critical]** **C-1**: prefix `[task]` を選択
2. **[critical]** **C-2**: `deferred` ラベル付与
3. **[critical]** **C-3**: `release-blocker` ラベルは付与しない (M8 撤回、2026-05-17 確定)
4. **[critical]** **C-4**: 本文に「次 release タイミングで `/release` Step 0c に再評価される」前提を明示 (or scope 外の reason 明記)
5. **[critical]** **C-5**: 期待値 section が存在し、2-4 文で「完了後の状態 + 理由」が記述されている
6. **[critical]** **C-6**: 現状 section が存在し、期待値とのギャップが具体的に記述されている
7. **[critical]** **C-7**: ユーザー影響・重要性 section が 1 行で位置付けを記述している

---

## シナリオ D (refactor 起票、preamble + ブロッカー section)

モック: ユーザー指示「`gui/src-tauri/src/lib.rs` の spawn site を `tauri-plugin-shell::Command` に移行する refactor を起票、現バージョン scope 外として deferred 付与」。

1. **[critical]** **D-1**: prefix `[refactor]` を選択
2. **[critical]** **D-2**: scope label `l2a-gui` + `deferred` ラベル付与
3. **[critical]** **D-3**: 期待値 section が存在し、2-4 文で「Tauri 2 公式 API への移行後の状態 + 戦略的価値」が記述されている
4. **[critical]** **D-4**: 現状 section が存在し、5 spawn site が `tokio::process::Command` 直接使用の状態とのギャップが記述されている
5. **[critical]** **D-5**: ユーザー影響・重要性 section が 1 行で位置付け (例: 「ユーザー影響なし、メンテ性負債」) を記述
6. **[critical]** **D-6**: ブロッカー section が存在し、`process_util::apply_no_window` / `PROCESS_TRACKER` 再設計などの実装ハードルが記述されている (該当時のみ、不要なら省略可)
7. **[critical]** **D-7**: 該当箇所 / 対応方針 / 関連 section が記載されている

---

## シナリオ E (risk 起票、preamble + 顕在化時被害詳細)

モック: ユーザー指示「Dependabot security alert (high) の risk を起票、tauri 2.10.3 の Origin Confusion 脆弱性」。

1. **[critical]** **E-1**: prefix `[risk]` を選択
2. **[critical]** **E-2**: 重複チェック (`gh issue list --search "tauri Origin Confusion"`) を実行
3. **[critical]** **E-3**: 期待値 section が存在し、リスク低減後の状態 (tauri 2.11.1 以降への bump 完了) が記述されている
4. **[critical]** **E-4**: 現状 section が存在し、現バージョン (tauri 2.10.3) と脆弱性の存在が記述されている
5. **[critical]** **E-5**: ユーザー影響・重要性 section が 1 行で被害規模 (例: 「medium、Remote→Local IPC invocation 経路」) を記述
6. **[critical]** **E-6**: 顕在化時の被害詳細 section が存在し、攻撃ベクター・影響範囲が記述されている
7. **[critical]** **E-7**: 該当箇所 / 対応方針 が記載されている
