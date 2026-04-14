"""
main.py - 自律型Instagramエージェント オーケストレーター
24時間365日、スケジュールに従って投稿サイクルを自律実行する
"""
import logging
import sys
import time
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from rich.console import Console

from config import config
from generator import ContentGenerator
from monitor import (
    AgentLogger, EngagementTracker, LearningLoop,
    send_slack_notification, setup_logging
)
from publisher import InstagramPublisher
from researcher import TrendResearcher

setup_logging()
logger = logging.getLogger(__name__)
console = Console()


# ------------------------------------------------------------------
# 投稿サイクルの実行
# ------------------------------------------------------------------
def run_post_cycle(post_type: str):
    """
    1サイクル: トレンド収集 → コンテンツ生成 → 投稿 → ログ記録
    """
    cycle_start = datetime.now().isoformat()
    logger.info(f"=== 投稿サイクル開始: {post_type} @ {cycle_start} ===")

    researcher = TrendResearcher()
    generator = ContentGenerator()
    publisher = InstagramPublisher()
    learning = LearningLoop()

    try:
        # Step 1: トレンド収集
        logger.info("Step 1/4: トレンド収集中...")
        insight = researcher.run()
        AgentLogger.log_action("trend_research", {
            "primary_theme": insight.get("primary_theme"),
            "content_angle": insight.get("content_angle"),
            "top_keywords": insight.get("top_trending_keywords", [])[:3]
        })

        # Step 2: 推奨戦略を反映
        recommendation = learning.load_recommendation()
        if recommendation.get("prioritize_theme"):
            logger.info(
                f"学習ループ反映: テーマ={recommendation['prioritize_theme']}, "
                f"タイプ={recommendation.get('prioritize_type')}"
            )
            # 学習結果のテーマをインサイトに反映（過半数の場合のみ）
            if insight.get("primary_theme") != recommendation["prioritize_theme"]:
                theme_counts = dict(insight.get("dominant_themes", []))
                if theme_counts.get(recommendation["prioritize_theme"], 0) > 0:
                    insight["primary_theme"] = recommendation["prioritize_theme"]

        # Step 3: コンテンツ生成
        logger.info(f"Step 2/4: コンテンツ生成中 (タイプ={post_type})...")
        post = generator.generate(post_type, insight)
        AgentLogger.log_action("content_generation", {
            "post_type": post.post_type,
            "theme": post.theme,
            "caption_length": len(post.caption),
            "image_path": post.image_path
        })

        # Step 4: 投稿
        logger.info("Step 3/4: Instagram投稿中...")
        result = publisher.publish(post)

        if result.success:
            msg = (
                f"投稿成功! タイプ={post_type}, "
                f"テーマ={post.theme}, "
                f"ID={result.post_id}"
            )
            logger.info(msg)
            AgentLogger.log_action("publish", {
                "post_id": result.post_id,
                "permalink": result.permalink,
                "post_type": post_type,
                "theme": post.theme
            }, success=True)
            send_slack_notification(f"✅ {msg}\n{result.permalink or ''}")
        else:
            logger.error(f"投稿失敗: {result.error}")
            AgentLogger.log_error("publish", result.error, {
                "post_type": post_type,
                "theme": post.theme
            })
            send_slack_notification(f"❌ 投稿失敗: {result.error}")

        logger.info("Step 4/4: サイクル完了")

    except Exception as e:
        logger.error(f"サイクル実行エラー: {e}", exc_info=True)
        AgentLogger.log_error("cycle_error", str(e), {"post_type": post_type})
        send_slack_notification(f"🚨 エラー発生: {e}")


def run_engagement_update():
    """エンゲージメント更新ジョブ（2時間ごと）"""
    logger.info("エンゲージメント更新開始...")
    tracker = EngagementTracker()
    tracker.update_post_metrics()

    learning = LearningLoop()
    learning.analyze_performance()


# ------------------------------------------------------------------
# スケジューラー設定
# ------------------------------------------------------------------
def build_scheduler() -> BlockingScheduler:
    scheduler = BlockingScheduler(timezone="Asia/Tokyo")

    # 投稿スケジュール
    for schedule in config.schedule_times:
        hour = schedule["hour"]
        minute = schedule["minute"]
        post_type = schedule["type"]

        scheduler.add_job(
            run_post_cycle,
            trigger=CronTrigger(hour=hour, minute=minute, timezone="Asia/Tokyo"),
            args=[post_type],
            id=f"post_{post_type}",
            name=f"Instagram投稿: {post_type}",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300  # 5分以内の遅延は許容
        )
        logger.info(f"スケジュール登録: {hour:02d}:{minute:02d} → {post_type}")

    # エンゲージメント更新（2時間ごと）
    scheduler.add_job(
        run_engagement_update,
        trigger=CronTrigger(hour="*/2", minute=30, timezone="Asia/Tokyo"),
        id="engagement_update",
        name="エンゲージメント更新",
        max_instances=1
    )

    return scheduler


# ------------------------------------------------------------------
# エントリーポイント
# ------------------------------------------------------------------
def main():
    console.print("\n[bold cyan]Instagram 自律型収益化エージェント v1.0[/bold cyan]")
    console.print("=" * 50)

    # 設定チェック
    missing = config.validate()
    if missing:
        console.print(f"[bold red]必須設定が不足しています: {missing}[/bold red]")
        console.print("[yellow].env.exampleを参考に.envファイルを作成してください[/yellow]")
        sys.exit(1)

    if config.dry_run:
        console.print("[bold yellow]DRY_RUNモード: 実際には投稿しません[/bold yellow]")

    console.print(f"[green]投稿スケジュール:[/green]")
    for s in config.schedule_times:
        console.print(f"  {s['hour']:02d}:{s['minute']:02d} → {s['type']}")

    console.print("\n[bold]スケジューラーを起動します...[/bold]")
    send_slack_notification("🚀 Instagramエージェント起動")

    scheduler = build_scheduler()
    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("エージェントを停止します")
        send_slack_notification("⏹ Instagramエージェント停止")
        scheduler.shutdown()


if __name__ == "__main__":
    # 引数処理
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "run-now":
            # 即時実行（テスト用）
            post_type = sys.argv[2] if len(sys.argv) > 2 else "educational"
            setup_logging()
            run_post_cycle(post_type)
        elif command == "update-metrics":
            setup_logging()
            run_engagement_update()
        elif command == "schedule":
            main()
        else:
            print(f"不明なコマンド: {command}")
            print("使用方法: python main.py [run-now|update-metrics|schedule]")
    else:
        main()
