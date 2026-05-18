# フロントライン動画・参考リソース

設計・テスト・UI 検知ロジックの参考として、既存のフロントライン動画やガイドを収集したリスト。

> **注意**: YouTube の動画 URL は変更・削除される可能性があります。リンク切れを発見した場合は issue で報告してください。

---

## 1. UI・HUD・画面構成の参考

試合中の UI 要素（スコアボード、ミニマップ、キルログ等）の位置や見た目を把握するための資料。L1（暗転検知）・L3 (new) (VTuber UI 適応)・L4 (former L3, OCR) の設計に直接役立つ。

| リソース | URL | 備考 |
| --- | --- | --- |
| FF14 フロントラインの画面や操作の設定例【パッチ7.1/PvP】 | YouTube で「ぷちっとこなこな フロントライン 設定」検索 | HUD レイアウト・操作設定の実例。画面構成の理解に有用 |
| フロントライン リザルト画面の見方 砕氷戦編 | [Lodestone ブログ](https://na.finalfantasyxiv.com/lodestone/character/12820627/blog/4252808/) | リザルト画面のスコア内訳を詳細解説。L4 (former L3) OCR 対象の理解に有用 |
| PvP用のHUDレイアウト | [エオキナ.com](https://www.mandra-queen.com/entry/pvp-starting-guide-4-ff14) | PvP 向け HUD 配置のガイド。UI 要素の標準位置を把握 |
| FF14 公式 UI ガイド | [Lodestone UIガイド](https://jp.finalfantasyxiv.com/uiguide/know/) | 公式の UI 要素リファレンス |
| フロントライン関連のキャラクターコンフィグ設定 | [Lodestone ブログ](https://na.finalfantasyxiv.com/lodestone/character/46737606/blog/5469424) | ゲームパッド・クロスホットバー等の設定例 |

## 2. 試合の流れ・画面遷移

試合開始→戦闘中→リザルト→退出までの画面遷移を理解するための資料。L1（暗転・ロード画面検知）の設計に直接役立つ。

### 典型的な画面遷移パターン

```text
待機画面 → ロード画面（暗転）→ マップ表示 → 試合中（15〜20分）
→ リザルト画面（スコアボード + MVP）→ ロード画面（暗転）→ キャラクター画面
→ [次の試合キューに入る] → 待機画面 → ロード画面（暗転）→ …
```

| リソース | URL | 備考 |
| --- | --- | --- |
| フロントライン攻略（開放方法やルール） | [ゲームエイト](https://game8.jp/ff14/512268) | ルール・開始〜終了の流れを解説 |
| フロントラインに行ってみよう！ | [note.com](https://note.com/dopelight/n/n6b3bc345a91a) | 初参加者向け、画面の流れが分かりやすい |

### YouTube 検索キーワード（長時間配信アーカイブ）

以下のキーワードで YouTube を直接検索すると、複数試合の連続録画（試合間の暗転が確認できる動画）が見つかる:

- `FF14 フロントライン 配信`（フィルタ: 長い動画 > 20分）
- `FF14 FL 連戦`
- `FFXIV Frontline stream`（フィルタ: Live）
- `FF14 PvP デイリー フロントライン`

## 3. ハイライト・ショート動画

投稿価値の評価（L5 (former L4)）の参考。どのような場面が「見どころ」として切り出されているかのパターン把握。

### YouTube 検索キーワード

- `FF14 フロントライン キル集`
- `FF14 FL ハイライト`
- `FFXIV Frontline highlights`
- `FFXIV Frontline montage`
- `FF14 PvP shorts`

### よくあるハイライトパターン

| パターン | 説明 | L5 (former L4) 評価での重み |
| --- | --- | --- |
| マルチキル | 短時間に複数キル | 高 |
| LB（リミットブレイク）キル | LB で敵集団を殲滅 | 高 |
| 逆転劇 | スコア差を覆す | 高 |
| 1対多で生存・反撃 | 数的不利から生還 | 中〜高 |
| 拠点制圧 | 敵拠点を単独〜少数で奪取 | 中 |
| MVP 獲得 | リザルトで MVP 表示 | 中 |

## 4. ルール・マップ解説

各マップの仕様を理解し、スコアボードの点数構造を把握するための資料。

| リソース | URL | 備考 |
| --- | --- | --- |
| AkhMorning Frontline Guide | [akhmorning.com](https://www.akhmorning.com/pvp/frontline/) | 全マップの詳細ガイド（英語） |
| Olivia's Frontline Guide 2.21 | [公式フォーラム](https://forum.square-enix.com/ffxiv/threads/495504-Olivia-s-Frontline-Guide-2.21) | 戦術ガイド（英語） |
| 公式 Frontline ページ | [Lodestone](https://na.finalfantasyxiv.com/lodestone/playguide/contentsguide/frontline/) | 公式ルール説明 |
| フロントライン攻略 | [ゲームエイト](https://game8.jp/ff14/512268) | 全ルールの日本語解説 |
| フロントラインの各ルール簡易解説 | [うわさの調べ](https://uwasablog.com/game230406/) | パッチ6.5 時点の簡潔な解説 |
| Revival PvP Community | Discord で「Revival FFXIV PvP」を検索 | FFXIV PvP コミュニティ（英語）。Web サイトは Cloudflare 保護のためブラウザアクセス推奨 |

## 5. OBS 配信設定（録画環境の参考）

入力動画の特性（コーデック、解像度、フレームレート）を理解するための資料。

| リソース | URL | 備考 |
| --- | --- | --- |
| OBSでFF14配信 2023最新版 | [ブログ](https://ff14-0t0.blogspot.com/2023/01/obsff142023obsyoutube-studioff14.html) | OBS + YouTube Studio の設定例 |

---

## 動画サンプルの取得

テスト用に短い動画クリップが必要な場合、`yt-dlp` で取得可能:

```bash
# 特定の動画の一部をダウンロード（例: 最初の5分）
yt-dlp --download-sections "*0:00-5:00" -o "sample_%(id)s.%(ext)s" "<URL>"
```

> 著作権に注意: テスト用の短いサンプルに留め、リポジトリにはコミットしないこと。
> プロジェクトのサンプルデータは環境変数 `ALLAGANEYE_SAMPLE_VIDEO_DIR` で指定したディレクトリの自前の録画を使用する（詳細は `CLAUDE.md` 参照）。
