# 価格比較・アービトラージ自動化システム 基本設計・仕様書

## 1. システム全体概要

本システムは、「携帯買取（相場比較）」と「家電・ホビー（アービトラージ）」の2つの独立した収集・比較エンジンを統合バッチによって集中管理し、GitHub Pages上にジャンル別のダッシュボードを展開する自動化システムである。

```text
[ローカルサーバー: Windows Server]
  │ 
  ├─ run_GetValue.bat (統合トリガー)
  │    ├─ 引数: keitai_iphone ── [毎時00分] ──> scrape_iphone.py
  │    ├─ 引数: kaden_game    ── [11:30/17:30] > scrape_kaden.py (game)
  │    └─ 引数: kaden_tobacco ── [11:40/17:40] > scrape_kaden.py (tobacco)
  │
  └─ GitHub API による自動ファイルプッシュ (json / js)
       │
[公開サーバー: GitHub Pages]
  └─ ジャンルごとに独立した HTML / JSON 構造で超軽量・高速表示
```

---

## 2. カテゴリ・ディレクトリ階層設計（買取一丁目の構成に準拠）

買取一丁目のカテゴリツリーに準拠し、大カテゴリ配下に中カテゴリを配置する疎結合設計を採用する。中古品は利益率が低いため対象外とする。

### GitHub Pages（公開Webサイト側）のディレクトリツリー
```text
roku-suke.github.io/
│
├── index.html                       # 総合ポータル（各ジャンルへのリンクハブ）
│
├── keitai/                          # 【大カテゴリ: 携帯】
│   └── iphone/                      # URL: .../keitai/iphone/
│       ├── index.html               # iPhone価格比較ダッシュボード本体
│       ├── current_data.json        # リアルタイム最新相場 ＋ 30日動向（毎時更新・50KB）
│       └── history_archive.json     # 長期推移グラフ用アーカイブ（日次最高値のみ・遅延読込）
│
├── kaden/                           # 【大カテゴリ: 家電】
│   ├── game/                        # URL: .../kaden/game/
│   │   ├── index.html               # ゲーム機・ソフト比較画面
│   │   └── data.json                # ゲーム相場・楽天安値TOP3データ
│   │
│   ├── tobacco/                     # URL: .../kaden/tobacco/ (次回実装)
│   │   ├── index.html               # 電子タバコ比較画面
│   │   └── data.json                # タバコ相場データ
│   │
│   └── (将来拡張: camera/, pc/ など)
│
├── toreca/                          # 【大カテゴリ: トレカ】(ロードマップ)
│   └── (pokemon/, onepiece/ など)
│
└── liquor/                          # 【大カテゴリ: お酒】(ロードマップ)
    └── (whisky/ など)
```

### ローカルサーバー（`C:\python\`）のディレクトリツリー
```text
C:\python\
│
├── run_GetValue.bat                 # 唯一の実行バッチ（引数で内部スクリプトを呼び分け）
│
├── configs/
│   └── iphone_models.json           # 毎年9月に新機種・定価のみを更新する設定ファイル
│
├── scripts/
│   ├── scrape_iphone.py             # iPhone専用スクレイピングスクリプト
│   └── scrape_kaden.py              # 一丁目×楽天 アービトラージ汎用スクリプト
│
├── data/                            # 生成データの一時保管・GitHub同期ミラー
│   ├── keitai/iphone/
│   └── kaden/game/
│
└── logs/                            # 各スクリプトのエラーログ・実行ログ保管
```

---

## 3. エンジン別 詳細仕様

### A. 携帯（iPhone）相場比較エンジン
* **目的**：Apple公式定価と主要買取6店舗（一丁目、一番、楽園、ルデヤ、MobileMix、モバステ）の横並び相場比較
* **更新頻度**：毎時00分（相場急変を検知）
* **年次モデルチェンジ運用（2世代ローテーション）**:
  * スクリプト本体は改修せず、`configs/iphone_models.json` の型番・定価リストのみを書き換える。
  * 最新機種（例: 18）は毎時更新。前年機種（例: 17）は画面上で「過去世代」として参照可能にし、主要モデルのみ低頻度追跡または確定履歴として保持。2年経過した世代は表から引退。
* **データ2層分離（高速表示と長期分析の両立）**:
  * **`current_data.json`**: 最新価格スナップショット ＋ 直近30日間の動向判定結果（矢印・傾向）。常に100KB以下を維持し、スマホで一瞬で表示
  * **`history_archive.json`**: 1日1回（深夜）、各機種の「日次最高買取価格」のみを1行追記。年間でも約150KBの軽量サイズ。画面上の「年間推移グラフを表示」ボタンが押された時のみ遅延読み込みする。

### B. 家電・その他（一丁目 × 楽天市場）アービトラージエンジン
* **目的**：買取一丁目の買取相場と、楽天市場の販売価格（正規店TOP3／市場全体TOP3）を突合し、利ざやを抽出。
* **更新頻度**：毎日 11:30 / 17:30（一丁目の価格改定直後）
* **カテゴリ規模と実行順序**:
  * **ゲーム**（約250件）：所要時間 約4分
  * **電子タバコ**（34件）：所要時間 約40秒（次回実装）
  * **トレカ**（85件）：所要時間 約1.5分（ロードマップ）
  * **お酒**（25件）：所要時間 約30秒（ロードマップ）
* **画面表示ルール**:
  * 1つのページに詰め込まず、サブカテゴリごとにページ（`kaden/game/index.html` 等）を分離。
  * 各ページの上部にジャンル特有の絞り込みバー（ゲームなら「本体」「ソフト」、タバコなら「本体」「スティック」等）を画面上部に固定配置。

---

## 4. バッチおよびタスクスケジューラ仕様

### 統合バッチ: `run_GetValue.bat`
```bat
@echo off
chcp 65001 > nul
cd /d C:\python

set TARGET=%1

if /i "%TARGET%"=="keitai_iphone" goto RUN_IPHONE
if /i "%TARGET%"=="kaden_game"    goto RUN_KADEN_GAME
if /i "%TARGET%"=="kaden_tobacco" goto RUN_KADEN_TOBACCO

echo [ERROR] 不正な引数です: %TARGET%
exit /b 1

:RUN_IPHONE
python scripts\scrape_iphone.py
exit /b 0

:RUN_KADEN_GAME
python scripts\scrape_kaden.py game
exit /b 0

:RUN_KADEN_TOBACCO
python scripts\scrape_kaden.py tobacco
exit /b 0
```

### タスクスケジューラ登録一覧

| タスク名 | トリガー | 実行プログラム | 引数の追加 |
| :--- | :--- | :--- | :--- |
| **Tracker_Keitai_iPhone** | 毎日 毎時00分 | `C:\python\run_GetValue.bat` | `keitai_iphone` |
| **Tracker_Kaden_Game** | 毎日 11:30, 17:30 | `C:\python\run_GetValue.bat` | `kaden_game` |
| **Tracker_Kaden_Tobacco** | 毎日 11:40, 17:40 | `C:\python\run_GetValue.bat` | `kaden_tobacco` |

---

## 5. 安定稼働のための技術要件

1. **Seleniumフリーズ防止（Windows Server対策）**:
   * `page_load_strategy = 'eager'`（DOM読み込み完了で即復帰）
   * `imagesEnabled = false`（画像ダウンロード物理遮断による超高速化）
   * `driver.set_page_load_timeout(15)`（外部通信ブロック時の強制タイムアウト）
2. **GitHub API直接連携**:
   * ローカルGitコマンド（`git push`）の競合や失敗を回避するため、Pythonから `requests.put` でBase64エンコードデータを直接GitHub API経由でリポジトリへ反映。
3. **ブラウザキャッシュ対策**:
   * 画面側のfetch処理に `?t=Date.now()` を付与し、常にCDN・ブラウザのキャッシュをバイパスして最新データを取得。
4. **リアルタイム同時接続計測**:
   * Firebase Realtime Database によるプレゼンス監視を行い、各画面のヘッダーに現在の閲覧人数をリアルタイム表示。

---

## 6. 開発・改修ロードマップ（進行状況）

### フェーズ1：アーキテクチャの定義と基盤安定化
- [x] スクレイピングのフリーズ問題解決（Selenium `eager`化・画像オフ）
- [x] GitHub APIによる直接連携の構築
- [x] 今後の拡張を見据えた仕様・ファイル構成の決定（本仕様書の作成）

### フェーズ2：ディレクトリ構成の再編・バッチ統合【← 現在ここ】
- [ ] ローカルサーバー（`C:\python`）のフォルダ構成を仕様書通りに整理
- [ ] `run_GetValue.bat` を作成し、既存の個別バッチを廃止・統合
- [ ] GitHubリポジトリ側のフォルダ構成を `kaden/game/` 等に移行・整理
- [ ] タスクスケジューラの設定を引数方式（`keitai_iphone`, `kaden_game`）へ変更

### フェーズ3：iPhoneシステムの高度化
- [ ] `scrape_iphone.py` と 機種設定（`config_iphone.json`）の分離
- [ ] iPhoneのデータ出力を `current_data.json` と `history_archive.json` に分離するロジック実装
- [ ] iPhone画面（HTML）に年間推移グラフ描画機能を追加

### フェーズ4：家電アービトラージの横展開
- [ ] 電子タバコ（`kaden_tobacco`）のスクリプト実装と画面追加
- [ ] トレカ（`toreca`）のスクリプト実装と画面追加