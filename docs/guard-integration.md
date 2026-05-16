# allaganeye-guard 連携仕様

## 1. 概要

[kobutachan-allaganeye-guard](https://github.com/Idios/kobutachan-allaganeye-guard) は、allaganeye が処理する動画ファイルのセキュリティ検査を行う独立ツール。外部ユーザーから受領したバグ再現データに攻撃コードやマルウェアが含まれていないことを、allaganeye のパイプラインに渡す前に検証する。

### 運用原則 (2026-04-21 確定)

allaganeye と allaganeye-guard は**プログラムレベルでの結合を行わない**。両ツールは独立した CLI として存在し、エージェント (= Claude Code セッションで動くこのアシスタント + 人間メンテナ Idios の両方) が外部から受け取った動画データを扱う際に、allaganeye で処理する前に `allaganeye-guard verify` を**手動で実行する**運用に一本化する。

### なぜ結合しないか

- **セキュリティ境界の分離**: 検査対象 (allaganeye) と検査ツールを同一コードベース・同一プロセスに置かない。結合すると allaganeye 側の脆弱性が検査フェーズ前に露出しうる
- **依存方向の明確化**: allaganeye と guard は**運用上の一方向依存** (guard verify が先、allaganeye split が後)。パッケージ依存関係としては**完全独立**
- **独立したリリースサイクル**: CVE 対応等のセキュリティ更新を allaganeye のリリースと独立して行える
- **allaganeye 側の軽量化**: guard を optional-deps にすらしないことで、allaganeye の依存グラフとインストール手順を最小に保つ

```text
allaganeye-guard (セキュリティ検査 CLI)
      │  ← 運用ルールによる手動チェーン (プログラム結合なし)
      ▼
allaganeye (動画処理 CLI)
```

---

## 1.1. 推奨 guard バージョン

外部動画の検査には以下のバージョン以上の guard を使用すること。

| 推奨バージョン | 更新日 | 根拠 |
| --- | --- | --- |
| v0.4.0 | 2026-04-12 | #262: バッチ検査、エラーハンドリング改善 |

> このテーブルはメンテナ (Idios) が guard リリース issue (`[info] allaganeye-guard`) を検出した際に更新する。更新後、リリース issue をクローズする。

---

## 2. guard が検査する脅威

| ID | 脅威 | 検査フェーズ |
| --- | --- | --- |
| T1 | 不正コンテナ (FFmpeg 脆弱性を突く細工) | Phase 1 + 2 |
| T2 | MKV 添付ファイルにマルウェア混入 | Phase 2 |
| T3 | 字幕トラックによるレンダラ脆弱性攻撃 | Phase 2 + 3 |
| T4 | ポリグロットファイル (拡張子偽装) | Phase 1 |
| T5 | メタデータによるパストラバーサル | Phase 1 + 2 |
| T6 | メタデータによるコマンドインジェクション | Phase 2 |
| T7 | リソース枯渇 (圧縮爆弾的構造) | Phase 1 + 2 |
| T8 | 未知のコーデックによる予測不能な動作 | Phase 2 |

---

## 3. 検査パイプライン

```text
入力ファイル
    │
    ▼
  Phase 1: ファイルレベル検査 (FFmpeg 不使用)
  - マジックバイト検証
  - 拡張子と実体の一致
  - ファイルサイズ上限
  - ファイル名の安全性
  - ポリグロット検出
    │ PASS
    ▼
  Phase 2: コンテナレベル検査 (MediaConch / MKVToolNix / ffprobe)
  - コンテナ仕様準拠
  - 添付ファイル検出
  - ストリーム種別・コーデック許可リスト
  - duration/サイズ比妥当性
  - メタデータ文字列の安全性
    │ PASS
    ▼
  Phase 3: パターン検査 (YARA / ClamAV)
  - 既知エクスプロイトパターン
  - マルウェアシグネチャ
    │ PASS
    ▼
  検査完了: PASS
```

各 Phase で FAIL が出た時点で後続はスキップし、即座に結果を返す。

---

## 4. 使用方法

外部から受領したファイルを処理する前に、エージェント (Claude + 人間メンテナ Idios の両方) が手動で検査する。

```bash
# 検査
allaganeye-guard verify received_file.mkv

# PASS (exit 0、または exit 1 = warnings あり) なら処理
allaganeye split received_file.mkv -o output/
```

ワンライナー:

```bash
# UNIX / Git Bash
allaganeye-guard verify received_file.mkv && allaganeye split received_file.mkv

# PowerShell
allaganeye-guard verify received_file.mkv; if ($LASTEXITCODE -eq 0) { allaganeye split received_file.mkv }
```

### guard の Exit Code と対応

エージェントは以下の exit code を基に判断する。

| コード | 意味 | 対応 |
| --- | --- | --- |
| 0 | PASS (警告なし) | `allaganeye split` で処理続行 |
| 1 | PASS with warnings | 警告を確認した上で処理続行 |
| 2 | FAIL (セキュリティ検査不合格) | 処理を中止。提供者に確認または報告 |
| 3 | ERROR (ツール実行エラー、依存ツール不足) | guard 側のインストール・依存関係を確認 |
| 4 | 入力エラー (ファイル不存在、引数不正) | 引数を見直す |

allaganeye 側には guard の exit code を反映する統合 exit code は設けない (本ドキュメント §1 「運用原則」参照)。

---

## 5. 外部動画データの検査ルール

GitHub の issue・PR に添付またはリンクされた動画ファイルについて、以下のルールに従う。

| データの出所 | guard 検査 |
| --- | --- |
| Idios が作成した issue/PR の添付・リンク | 不要 (自己録画データ) |
| Idios 以外が作成した issue/PR の添付・リンク | **必須** |
| 外部ユーザーから直接受領したファイル (§6) | **必須** |
| `ALLAGANEYE_SAMPLE_VIDEO_DIR` の既存データ | 不要 (検証済み) |

### 検査手順

1. ファイルをダウンロードし、隔離ディレクトリに保存する
2. guard を最新版に更新する (`git pull && pip install -e .`)。YARA ルールセットは随時更新されるため、古いバージョンでの検査は不十分な可能性がある
3. `allaganeye-guard verify <file>` を実行する
4. **PASS するまで allaganeye で処理しない**
5. guard 未インストールの場合は先にインストールする ([kobutachan-allaganeye-guard](https://github.com/Idios/kobutachan-allaganeye-guard) リポジトリ参照)
6. FAIL の場合は処理せず、issue・PR にコメントして提供者に確認を求める
7. 検査結果 (PASS / FAIL) を issue・PR にコメントとして記録する

---

## 6. バグ報告時の運用フロー

外部ユーザーからバグ再現データを受領する際の手順。報告者向けの案内 (プライバシー配慮・同意項目の意味・添付動画のサイズ制約等) は [`docs/bug-report-guide.md`](bug-report-guide.md) を参照 (本節はメンテナ側の受領後手順に特化)。

### 情報収集 (段階的)

| Stage | 内容 | 動画データ |
| --- | --- | --- |
| 1 | `--verbose` 出力 + `debug-brightness` CSV | 不要 |
| 2 | 問題箇所周辺を切り出した最小再現動画 | 必要 (同意必須) |
| 3 | フル動画 (最終手段) | 必要 (同意必須) |

### 受領時の必須手順 (メンテナ側)

1. Issue Template (`.github/ISSUE_TEMPLATE/bug_report.yml`) の同意チェックボックスが全てチェック済みであることを確認
2. ファイルをダウンロードし、隔離ディレクトリに保存
3. **エージェント (Claude + Idios) が `allaganeye-guard verify` を実行**。PASS するまで allaganeye で処理しない
4. 調査完了後、ローカルデータを削除し Issue にコメントで報告

### プライバシー同意

動画ファイルには個人情報 (音声、チャットログ、プレイヤー名等) が含まれうる。再現性を保つためデータは改変しない方針のため、提供者から以下の同意を取得する:

- 個人情報が含まれる可能性の理解
- メンテナがバグ調査目的で閲覧することへの同意
- バグ解決後にデータが削除されることの理解

同意は GitHub Issue Template のチェックボックスで取得する (`.github/ISSUE_TEMPLATE/bug_report.yml`)。なお**セキュリティ検査の実行はメンテナ側の責務**であり、Issue Template ではユーザーに guard 実行を求めない。

---

## 参考: 過去の program-integration 計画について

2026-04-21 以前、本ドキュメントには allaganeye 側に `--verify` CLI オプション、`allaganeye/guard.py` subprocess ラッパー、exit code 6 (SecurityVerificationError)、`pyproject.toml` の `[guard]` optional-deps、`tests/test_guard_integration.py` 統合テスト等を追加する program-integration 計画が含まれていた (旧 §4.2 / §5 / §6 / §7 / §10 / §11)。

本方針転換によりこれらの構想は全て破棄し、本ドキュメントからも削除した。関連 issue (#454 / #455 / #456 / #457 / #460) と PR #488 はクローズ済み。復活が必要になった場合は本 §1 「運用原則」を先に見直すこと。
