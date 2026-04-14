"""
config.py - 設定管理モジュール
すべての設定値と定数を一元管理する
"""
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    # Instagram Graph API 認証
    instagram_access_token: str = field(
        default_factory=lambda: os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
    )
    instagram_account_id: str = field(
        default_factory=lambda: os.getenv("INSTAGRAM_ACCOUNT_ID", "")
    )
    facebook_app_id: str = field(
        default_factory=lambda: os.getenv("FACEBOOK_APP_ID", "")
    )
    facebook_app_secret: str = field(
        default_factory=lambda: os.getenv("FACEBOOK_APP_SECRET", "")
    )

    # Claude API
    anthropic_api_key: str = field(
        default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", "")
    )

    # 画像生成
    stability_api_key: str = field(
        default_factory=lambda: os.getenv("STABILITY_API_KEY", "")
    )
    unsplash_access_key: str = field(
        default_factory=lambda: os.getenv("UNSPLASH_ACCESS_KEY", "")
    )

    # 導線URL
    note_url: str = field(default_factory=lambda: os.getenv("NOTE_PROFILE_URL", ""))
    affiliate_url: str = field(default_factory=lambda: os.getenv("AFFILIATE_URL", ""))
    line_url: str = field(default_factory=lambda: os.getenv("LINE_URL", ""))
    linktree_url: str = field(default_factory=lambda: os.getenv("LINKTREE_URL", ""))

    # 投稿制御
    daily_post_limit: int = field(
        default_factory=lambda: int(os.getenv("DAILY_POST_LIMIT", "3"))
    )
    min_interval_minutes: int = field(
        default_factory=lambda: int(os.getenv("MIN_INTERVAL_MINUTES", "60"))
    )
    dry_run: bool = field(
        default_factory=lambda: os.getenv("DRY_RUN", "false").lower() == "true"
    )

    # パス
    log_file: str = "agent_history.log"
    db_file: str = "data/posts.db"
    images_dir: str = "data/images"

    # トレンド収集設定（副業・AI・投資・時短術）
    trend_keywords: list = field(default_factory=lambda: [
        "副業", "AI副業", "投資", "時短術", "ChatGPT", "Claude", "自動化",
        "FIRE", "不労所得", "フリーランス", "在宅ワーク", "節税", "積立NISA"
    ])

    # RSSフィード（トレンド収集用）
    rss_feeds: list = field(default_factory=lambda: [
        "https://b.hatena.ne.jp/hotentry/it.rss",
        "https://b.hatena.ne.jp/hotentry/money.rss",
        "https://zenn.dev/feed",
        "https://note.com/hashtag/副業/feed.rss",
    ])

    # Instagramハッシュタグ（ジャンル別）
    hashtag_sets: dict = field(default_factory=lambda: {
        "AI活用": [
            "#AI副業", "#ChatGPT活用", "#Claude", "#AI時代の生き方",
            "#AIツール", "#自動化", "#生産性向上", "#テクノロジー",
            "#デジタルスキル", "#未来の働き方", "#副業", "#在宅ワーク"
        ],
        "副業": [
            "#副業", "#副業始め方", "#副業収入", "#フリーランス",
            "#在宅ワーク", "#リモートワーク", "#ノマドワーカー",
            "#起業", "#スモールビジネス", "#個人事業主", "#自由な働き方"
        ],
        "投資": [
            "#投資初心者", "#新NISA", "#積立NISA", "#インデックス投資",
            "#資産形成", "#FIRE", "#経済的自由", "#お金の勉強",
            "#マネーリテラシー", "#不労所得", "#配当金", "#長期投資"
        ],
        "時短・効率化": [
            "#時短術", "#生産性", "#仕事効率化", "#タスク管理",
            "#ライフハック", "#時間管理", "#朝活", "#ルーティン",
            "#目標達成", "#自己成長", "#スキルアップ"
        ]
    })

    # 投稿スケジュール（JST）
    schedule_times: list = field(default_factory=lambda: [
        {"hour": 8,  "minute": 0,  "type": "morning_insight"},
        {"hour": 12, "minute": 0,  "type": "tips"},
        {"hour": 18, "minute": 0,  "type": "deep_carousel"},
        {"hour": 21, "minute": 0,  "type": "sales_funnel"},
    ])

    # NGワード（アカウント凍結対策）
    ng_words: list = field(default_factory=lambda: [
        "フォロバ", "いいね返し", "相互フォロー", "無料プレゼント",
        "今だけ", "絶対儲かる", "100%", "保証", "詐欺", "騙し",
        "緊急", "今すぐ登録", "期間限定"
    ])

    # Instagram Graph API エンドポイント
    ig_api_base: str = "https://graph.facebook.com/v19.0"

    def validate(self) -> list[str]:
        """必須設定が揃っているか確認、不足項目のリストを返す"""
        missing = []
        if not self.instagram_access_token:
            missing.append("INSTAGRAM_ACCESS_TOKEN")
        if not self.instagram_account_id:
            missing.append("INSTAGRAM_ACCOUNT_ID")
        if not self.anthropic_api_key:
            missing.append("ANTHROPIC_API_KEY")
        return missing


config = Config()
