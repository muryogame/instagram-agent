# Instagram 自律型収益化エージェント セットアップガイド

## 必要なもの

### Instagram側の準備
1. **Instagramビジネスアカウント**に切り替え（個人アカウント→プロアカウント→ビジネス）
2. **Facebookページ**にInstagramアカウントを紐付け
3. **Facebook Developers** (developers.facebook.com) でアプリを作成
   - 製品を追加: `Instagram Graph API`
   - アクセス許可: `instagram_basic`, `instagram_content_publish`, `instagram_manage_insights`
4. **長期トークン**を取得（通常60日間有効）
5. **Instagram Business Account ID** を取得

### API Keys一覧
| 変数名 | 取得場所 | 必須 |
|--------|----------|------|
| INSTAGRAM_ACCESS_TOKEN | Facebook Developers | ✅ |
| INSTAGRAM_ACCOUNT_ID | Graph API Explorer | ✅ |
| ANTHROPIC_API_KEY | console.anthropic.com | ✅ |
| IMGBB_API_KEY | api.imgbb.com | ✅（画像ホスティング） |
| STABILITY_API_KEY | platform.stability.ai | 任意（AI画像生成） |
| SLACK_WEBHOOK_URL | Slack App設定 | 任意（通知） |

---

## インストール手順

```bash
cd /home/takah/claude/company/x_agent

# 仮想環境作成
python3 -m venv .venv
source .venv/bin/activate

# 依存パッケージインストール
pip install -r requirements.txt

# 日本語フォントインストール（Ubuntu/WSL）
sudo apt-get install -y fonts-noto-cjk

# .envファイル作成
cp .env.example .env
# .envを編集してAPIキーを設定
nano .env

# dataディレクトリ作成
mkdir -p data/images logs
```

---

## 動作確認（ドライラン）

```bash
# DRY_RUN=true に設定してテスト実行
DRY_RUN=true python main.py run-now educational
```

---

## 本番実行

### ローカル24時間稼働
```bash
python main.py schedule
```

### GitHub Actions（推奨・無料）
1. GitHubリポジトリを作成
2. Secrets設定: `Settings > Secrets and variables > Actions`
   - 上記APIキーをすべて追加
3. `.github/workflows/instagram-agent.yml` がスケジュールを管理
4. 手動実行: `Actions > Instagram 自律収益化エージェント > Run workflow`

---

## 収益化フロー

```
Instagram投稿
    ↓（bio linkまたはストーリーリンク）
Linktree
    ├── note記事（有料マガジン月980円〜）
    ├── Brain/Infotop（情報商材アフィリエイト）
    └── 公式LINE（リスト収集 → 高単価商品販売）
```

---

## ファイル構成

```
x_agent/
├── main.py          # オーケストレーター
├── researcher.py    # トレンドスキャナー
├── generator.py     # コンテンツ生成（Claude API）
├── publisher.py     # Instagram投稿エンジン
├── monitor.py       # 監視・学習ループ
├── config.py        # 設定管理
├── .env             # APIキー（gitignore済）
├── .env.example     # テンプレート
├── requirements.txt
├── data/
│   ├── posts.db           # 投稿履歴DB
│   ├── images/            # 生成画像
│   ├── latest_insight.json
│   └── performance_analysis.json
├── logs/
├── agent_history.log
└── workflows/
    └── .ghost-workflows.json
```

---

## 拡張予定

- [ ] Threadsへの横展開（Meta Graph API対応）
- [ ] Reels自動生成（動画コンテンツ）
- [ ] A/Bテスト機能（複数バリエーション比較）
- [ ] TikTokへの展開
