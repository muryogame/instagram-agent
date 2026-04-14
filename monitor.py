"""
monitor.py - 自律実行・監視・学習ループシステム
投稿後のエンゲージメントを追跡し、次回生成に反映するフィードバックループ
"""
import json
import logging
import logging.handlers
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

import requests

from config import config

logger = logging.getLogger(__name__)


def setup_logging():
    """ログ設定（ローテーション付き）"""
    log_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # ファイルハンドラ（10MB x 5ファイルでローテーション）
    os.makedirs("logs", exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        config.log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(log_formatter)

    # コンソールハンドラ（richで色付き出力）
    try:
        from rich.logging import RichHandler
        console_handler = RichHandler(rich_tracebacks=True)
    except ImportError:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(log_formatter)

    logging.basicConfig(
        level=logging.INFO,
        handlers=[file_handler, console_handler]
    )


class EngagementTracker:
    """Instagram Graph APIでエンゲージメントを追跡する"""

    def __init__(self):
        self.base_url = config.ig_api_base
        self.access_token = config.instagram_access_token
        self.db_path = config.db_file

    def fetch_post_insights(self, post_id: str) -> Optional[dict]:
        """
        投稿のインサイト（いいね・コメント・保存・リーチ）を取得
        """
        if config.dry_run or not post_id or post_id == "dry_run_id":
            return None
        try:
            resp = requests.get(
                f"{self.base_url}/{post_id}/insights",
                params={
                    "metric": "impressions,reach,likes,comments,saves,profile_visits",
                    "access_token": self.access_token
                },
                timeout=15
            )
            data = resp.json()
            if "data" not in data:
                return None

            metrics = {}
            for item in data["data"]:
                metrics[item["name"]] = item["values"][0]["value"] if item.get("values") else 0
            return metrics

        except Exception as e:
            logger.warning(f"インサイト取得エラー (post_id={post_id}): {e}")
            return None

    def update_post_metrics(self):
        """DBの全投稿のメトリクスを更新"""
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            """SELECT id, post_id, published_at FROM posts
               WHERE post_id != 'dry_run_id'
               AND published_at > ?""",
            ((datetime.now() - timedelta(days=7)).isoformat(),)
        ).fetchall()
        conn.close()

        updated = 0
        for row_id, post_id, _ in rows:
            metrics = self.fetch_post_insights(post_id)
            if metrics:
                conn = sqlite3.connect(self.db_path)
                conn.execute(
                    """UPDATE posts SET
                       impressions=?, likes=?, comments=?, saves=?, reach=?
                       WHERE id=?""",
                    (
                        metrics.get("impressions", 0),
                        metrics.get("likes", 0),
                        metrics.get("comments", 0),
                        metrics.get("saves", 0),
                        metrics.get("reach", 0),
                        row_id
                    )
                )
                conn.commit()
                conn.close()
                updated += 1

        logger.info(f"エンゲージメント更新完了: {updated}件")


class LearningLoop:
    """
    投稿パフォーマンスを分析して次回生成戦略を最適化する簡易学習ループ
    """

    def __init__(self):
        self.db_path = config.db_file

    def analyze_performance(self) -> dict:
        """過去7日間の投稿パフォーマンスを分析"""
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            """SELECT post_type, theme, impressions, likes, comments, saves, reach
               FROM posts
               WHERE published_at > ?
               AND post_id != 'dry_run_id'""",
            ((datetime.now() - timedelta(days=7)).isoformat(),)
        ).fetchall()
        conn.close()

        if not rows:
            return {"status": "insufficient_data", "recommendation": None}

        # タイプ別・テーマ別の平均エンゲージメント計算
        type_stats = {}
        theme_stats = {}

        for post_type, theme, impressions, likes, comments, saves, reach in rows:
            # エンゲージメント率 = (likes + comments*2 + saves*3) / reach
            if reach and reach > 0:
                eng_rate = (likes + comments * 2 + saves * 3) / reach
            else:
                eng_rate = 0

            if post_type not in type_stats:
                type_stats[post_type] = []
            type_stats[post_type].append(eng_rate)

            if theme not in theme_stats:
                theme_stats[theme] = []
            theme_stats[theme].append(eng_rate)

        # 平均計算
        type_avg = {k: sum(v)/len(v) for k, v in type_stats.items()}
        theme_avg = {k: sum(v)/len(v) for k, v in theme_stats.items()}

        # 最良パフォーマンス
        best_type = max(type_avg, key=type_avg.get) if type_avg else None
        best_theme = max(theme_avg, key=theme_avg.get) if theme_avg else None

        analysis = {
            "status": "analyzed",
            "period": "7 days",
            "total_posts": len(rows),
            "type_engagement_rates": type_avg,
            "theme_engagement_rates": theme_avg,
            "best_performing_type": best_type,
            "best_performing_theme": best_theme,
            "recommendation": self._build_recommendation(best_type, best_theme)
        }

        # 分析結果を保存
        os.makedirs("data", exist_ok=True)
        with open("data/performance_analysis.json", "w", encoding="utf-8") as f:
            json.dump(analysis, f, ensure_ascii=False, indent=2)

        logger.info(
            f"パフォーマンス分析完了: "
            f"最良タイプ={best_type}, 最良テーマ={best_theme}"
        )
        return analysis

    def _build_recommendation(
        self,
        best_type: Optional[str],
        best_theme: Optional[str]
    ) -> dict:
        """分析に基づく次回投稿戦略の推奨"""
        type_weight_map = {
            "educational": {"educational": 0.5, "empathy": 0.3, "sales_funnel": 0.2},
            "empathy": {"educational": 0.3, "empathy": 0.5, "sales_funnel": 0.2},
            "sales_funnel": {"educational": 0.2, "empathy": 0.3, "sales_funnel": 0.5}
        }
        return {
            "prioritize_type": best_type or "educational",
            "prioritize_theme": best_theme or "AI活用",
            "type_weights": type_weight_map.get(best_type, type_weight_map["educational"])
        }

    def load_recommendation(self) -> dict:
        """保存された推奨戦略を読み込む"""
        try:
            with open("data/performance_analysis.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("recommendation", {})
        except FileNotFoundError:
            return {}


class AgentLogger:
    """エージェントの行動履歴を記録する"""

    @staticmethod
    def log_action(action: str, details: dict, success: bool = True):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "success": success,
            "details": details
        }
        with open(config.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    @staticmethod
    def log_error(action: str, error: str, context: dict = None):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "success": False,
            "error": error,
            "context": context or {}
        }
        with open(config.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def send_slack_notification(message: str):
    """Slack Webhookで通知送信（設定時のみ）"""
    webhook_url = os.getenv("SLACK_WEBHOOK_URL", "")
    if not webhook_url:
        return
    try:
        requests.post(
            webhook_url,
            json={"text": f"[Instagram Agent] {message}"},
            timeout=10
        )
    except Exception as e:
        logger.warning(f"Slack通知失敗: {e}")
