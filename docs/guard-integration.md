# allaganeye-guard 連携仕様

## 1. 概要

[kobutachan-allaganeye-guard](https://github.com/Idios/kobutachan-allaganeye-guard) は、allaganeye が処理する動画ファイルのセキュリティ検査を行う独立ツール。外部ユーザーから受領したバグ再現データに攻撃コードやマルウェアが含まれていないことを、allaganeye のパイプラインに渡す前に検証する。

### なぜ独立ツールか

- **セキュリティ境界の分離**: 検査対象（allaganeye）と検査ツールを同一コードベースに置かない
- **依存方向の明確化**: allaganeye → guard の一方向依存。guard は allaganeye に依存しない
- **独立したリリースサイクル**: CVE 対応等のセキュリティ更新を allaganeye のリリースと独立して行える

```
allaganeye-guard（セキュリティ検査）
       ↑ subprocess 呼び出し
allaganeye（動画処理）
```

---

## 1.1. 推奨 guard バージョン

外部動画の検査には以下のバージョン以上の guard を使用すること。

| 推奨バージョン | 更新日 | 根拠 |
|---|---|---|
| v0.4.0 | 2026-04-12 | #262: バッチ検査、エラーハンドリング改善 |

> このテーブルはディレクターが guard リリース issue（`[info] allaganeye-guard`）を検出した際に更新する。更新後、リリース issue をクローズする。

---

## 2. guard が検査する脅威

| ID | 脅威 | 検査フェーズ |
|---|---|---|
| T1 | 不正コンテナ（FFmpeg 脆弱性を突く細工） | Phase 1 + 2 |
| T2 | MKV 添付ファイルにマルウェア混入 | Phase 2 |
| T3 | 字幕トラックによるレンダラ脆弱性攻撃 | Phase 2 + 3 |
| T4 | ポリグロットファイル（拡張子偽装） | Phase 1 |
| T5 | メタデータによるパストラバーサル | Phase 1 + 2 |
| T6 | メタデータによるコマンドインジェクション | Phase 2 |
| T7 | リソース枯渇（圧縮爆弾的構造） | Phase 1 + 2 |
| T8 | 未知のコーデックによる予測不能な動作 | Phase 2 |

---

## 3. 検査パイプライン

```
入力ファイル
    │
    ▼
  Phase 1: ファイルレベル検査（FFmpeg 不使用）
  - マジックバイト検証
  - 拡張子と実体の一致
  - ファイルサイズ上限
  - ファイル名の安全性
  - ポリグロット検出
    │ PASS
    ▼
  Phase 2: コンテナレベル検査（MediaConch / MKVToolNix / ffprobe）
  - コンテナ仕様準拠
  - 添付ファイル検出
  - ストリーム種別・コーデック許可リスト
  - duration/サイズ比妥当性
  - メタデータ文字列の安全性
    │ PASS
    ▼
  Phase 3: パターン検査（YARA / ClamAV）
  - 既知エクスプロイトパターン
  - マルウェアシグネチャ
    │ PASS
    ▼
  検査完了: PASS
```

各 Phase で FAIL が出た時点で後続はスキップし、即座に結果を返す。

---

## 4. allaganeye からの利用方法

### 4.1 手動実行（推奨）

外部から受領したファイルを処理する前に手動で検査する。

```bash
# 検査
allaganeye-guard verify received_file.mkv

# PASS なら処理
allaganeye split received_file.mkv -o output/
```

ワンライナー:

```bash
# UNIX
allaganeye-guard verify received_file.mkv && allaganeye split received_file.mkv

# PowerShell
allaganeye-guard verify received_file.mkv; if ($LASTEXITCODE -eq 0) { allaganeye split received_file.mkv }
```

### 4.2 自動呼び出し（将来実装）

allaganeye の `split` コマンドに `--verify` オプションを追加し、処理前に guard を自動呼び出しする。

```bash
# 自動検査付き
allaganeye split --verify received_file.mkv

# strict モード
allaganeye split --verify --verify-strict received_file.mkv

# 検査スキップ（自己責任）
allaganeye split --skip-verify received_file.mkv
```

自動呼び出し時、allaganeye は guard を subprocess として実行し `--json` 出力を解析する。

#### guard 未インストール時の振る舞い

| 設定 | 振る舞い |
|---|---|
| `--verify` 明示指定 | guard が見つからなければエラー終了 |
| デフォルト（auto） | 見つかれば実行、なければスキップして警告表示 |
| `--skip-verify` | 検査をスキップ |

---

## 5. guard の Exit Code と allaganeye の対応

### guard の Exit Code

| コード | 意味 |
|---|---|
| 0 | PASS（警告なし） |
| 1 | PASS with warnings |
| 2 | FAIL（セキュリティ検査不合格） |
| 3 | ERROR（ツール実行エラー、依存ツール不足） |
| 4 | 入力エラー（ファイル不存在、引数不正） |

### allaganeye 側の対応

| guard exit code | allaganeye の動作 |
|---|---|
| 0 | 処理を続行 |
| 1 | 警告を表示して処理を続行 |
| 2 | 処理を中断。FAIL 理由を表示 |
| 3, 4 | 処理を中断。エラー内容を表示 |

allaganeye 側で検査不合格を表す exit code は **6**（Security verification failed）を新設する。

---

## 6. JSON インターフェース

allaganeye が guard を subprocess で呼び出す際は `--json` フラグを使用する。

### 出力スキーマ

```json
{
  "version": "0.1.0",
  "file": "recording.mkv",
  "file_size_bytes": 48531234567,
  "result": "pass",
  "warnings": 0,
  "phases": [
    {
      "name": "file_level",
      "result": "pass",
      "checks": [
        {
          "id": "1.1",
          "name": "magic_bytes",
          "result": "pass",
          "detail": "Matroska (EBML)"
        }
      ]
    }
  ],
  "timestamp": "2026-04-05T12:00:00+09:00",
  "duration_ms": 1234
}
```

### result フィールドの判定

| 値 | 条件 |
|---|---|
| `pass` | 全 Phase が pass（WARN があっても pass） |
| `fail` | いずれかの Phase で FAIL |
| `error` | ツール実行エラー |

### 後方互換性

- `version` フィールドで互換性を判定する
- フィールドの追加は許容（minor バージョン）
- フィールドの削除・型変更は禁止（major バージョン変更が必要）

---

## 7. パッケージ依存管理

### allaganeye 側の pyproject.toml

```toml
[project.optional-dependencies]
guard = ["kobutachan-allaganeye-guard"]
```

- 基本インストールに guard を含めない（オプション依存）
- `pip install allaganeye[guard]` で guard も一緒にインストール可能
- guard がなくても allaganeye 本体は正常動作する

---

## 8. 外部動画データの検査ルール

GitHub の issue・PR に添付またはリンクされた動画ファイルについて、以下のルールに従う。

| データの出所 | guard 検査 |
|---|---|
| Idios が作成した issue/PR の添付・リンク | 不要（自己録画データ） |
| Idios 以外が作成した issue/PR の添付・リンク | **必須** |
| 外部ユーザーから直接受領したファイル（§9） | **必須** |
| `ALLAGANEYE_SAMPLE_VIDEO_DIR` の既存データ | 不要（検証済み） |

### 検査手順

1. ファイルをダウンロードし、隔離ディレクトリに保存する
2. guard を最新版に更新する（`git pull && pip install -e .`）。YARA ルールセットは随時更新されるため、古いバージョンでの検査は不十分な可能性がある
3. `allaganeye-guard verify <file>` を実行する
4. **PASS するまで allaganeye で処理しない**
5. guard 未インストールの場合は先にインストールする（§7 参照）
6. FAIL の場合は処理せず、issue・PR にコメントして提供者に確認を求める
7. 検査結果（PASS / FAIL）を issue・PR にコメントとして記録する

---

## 9. バグ報告時の運用フロー

外部ユーザーからバグ再現データを受領する際の手順。

### 情報収集（段階的）

| Stage | 内容 | 動画データ |
|---|---|---|
| 1 | `--verbose` 出力 + `debug-brightness` CSV | 不要 |
| 2 | 問題箇所周辺を切り出した最小再現動画 | 必要（同意必須） |
| 3 | フル動画（最終手段） | 必要（同意必須） |

### 受領時の必須手順

1. Issue Template の同意チェックボックスが全てチェック済みであることを確認
2. ファイルをダウンロードし、隔離ディレクトリに保存
3. **`allaganeye-guard verify` を実行**（PASS するまで allaganeye で処理しない）
4. 調査完了後、ローカルデータを削除し Issue にコメントで報告

### プライバシー同意

動画ファイルには個人情報（音声、チャットログ、プレイヤー名等）が含まれうる。再現性を保つためデータは改変しない方針のため、提供者から以下の同意を取得する:

- 個人情報が含まれる可能性の理解
- 開発者がバグ調査目的で閲覧することへの同意
- バグ解決後にデータが削除されることの理解

同意は GitHub Issue Template のチェックボックスで取得する（`.github/ISSUE_TEMPLATE/bug_report.yml`）。

---

## 10. allaganeye 側の実装タスク

guard 連携のために allaganeye 側で必要な変更。

| # | 変更内容 | 対象ファイル | 優先度 |
|---|---|---|---|
| 1 | exit code 6（Security verification failed）追加 | `exceptions.py`, `docs/cli-spec.md` | P1 |
| 2 | `--verify` / `--skip-verify` オプション | `cli.py`, `commands/split_matches.py` | P2 |
| 3 | guard subprocess 呼び出し関数 | 新規 `guard.py` | P2 |
| 4 | `.github/ISSUE_TEMPLATE/bug_report.yml` | `.github/` | P2 |
| 5 | バグ報告ガイド | `docs/bug-report-guide.md` | P2 |
| 6 | 統合テスト | `tests/test_guard_integration.py` | P3 |

---

## 11. 保守と定期見直し

guard はセキュリティツールのため、以下の定期見直しが必要（詳細は guard リポジトリの `docs/maintenance-policy.md`）。

| 対象 | 頻度 | 担当 |
|---|---|---|
| YARA ルールセット | 月次 + FFmpeg CVE 公開時 | guard リードエンジニア |
| コーデック許可リスト | allaganeye レイヤーリリース時 | guard ディレクター |
| バックエンドツールバージョン | 四半期ごと | guard リードエンジニア |
| 脅威モデル | 半年ごと | guard ディレクター |

### allaganeye リリース時の連携チェック

allaganeye の各レイヤーリリース時に以下を確認する:

1. guard の最新バージョンとの互換性（JSON スキーマ）
2. allaganeye が新たに対応したコーデックが guard の許可リストに含まれているか
3. exit code 体系の衝突がないか
4. `allaganeye split --verify` の統合テストが通るか
