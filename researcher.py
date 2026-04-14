"""
researcher.py - リアルタイム・トレンド・スキャナー
副業・AI・投資・時短術に関するトレンドを1時間ごとに収集・分析する
"""
import json
import logging
import time
from collections import Counter
from datetime import datetime

import feedparser
import requests
from bs4 import BeautifulSoup
from pytrends.request import TrendReq
from tenacity import retry, stop_after_attempt, wait_exponential

from config import config

logger = logging.getLogger(__name__)


class TrendResearcher:
    def __init__(self):
        self.pytrends = TrendReq(hl="ja-JP", tz=540)  # 日本時間
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; ResearchBot/1.0)"
        })

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=30))
    def get_google_trends(self, keywords: list[str]) -> list[dict]:
        """Google Trendsから急上昇キーワードを取得"""
        trends = []
        try:
            for i in range(0, len(keywords), 5):
                batch = keywords[i:i+5]
                self.pytrends.build_payload(batch, cat=0, timeframe="now 1-d", geo="JP")
                interest = self.pytrends.interest_over_time()

                if not interest.empty:
                    for kw in batch:
                        if kw in interest.columns:
                            avg_score = interest[kw].mean()
                            recent_score = float(interest[kw].iloc[-1]) if len(interest) > 0 else 0
                            momentum = recent_score - float(interest[kw].iloc[-6]) if len(interest) >= 6 else 0
                            trends.append({
                                "keyword": kw,
                                "score": float(avg_score),
                                "recent_score": recent_score,
                                "momentum": momentum,
                                "source": "google_trends"
                            })
                time.sleep(2)

        except Exception as e:
            logger.warning(f"Google Trends取得エラー: {e}")

        return sorted(trends, key=lambda x: x["momentum"], reverse=True)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def get_rss_articles(self) -> list[dict]:
        """RSSフィードから最新記事を取得"""
        articles = []
        for feed_url in config.rss_feeds:
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries[:10]:
                    title = entry.get("title", "")
                    summary = entry.get("summary", "")[:500]
                    link = entry.get("link", "")

                    is_relevant = any(
                        kw in title or kw in summary
                        for kw in config.trend_keywords
                    )
                    if is_relevant:
                        articles.append({
                            "title": title,
                            "summary": summary,
                            "url": link,
                            "published": entry.get("published", str(datetime.now())),
                            "source": feed_url
                        })
            except Exception as e:
                logger.warning(f"RSS取得エラー ({feed_url}): {e}")

        return articles[:20]

    def get_instagram_trending_hashtags(self) -> list[str]:
        """Instagramトレンドハッシュタグを収集（外部ソース経由）"""
        trending = []
        try:
            # トレンドタグ情報サイトをスクレイプ
            resp = self.session.get(
                "https://trends24.in/japan/",
                timeout=10
            )
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "lxml")
                items = soup.select(".trend-card__list li a")
                trending = [f"#{item.get_text(strip=True).replace(' ', '')}" for item in items[:15]]
        except Exception as e:
            logger.warning(f"トレンドタグ取得エラー: {e}")

        return trending

    def analyze_insights(
        self,
        trends: list[dict],
        articles: list[dict],
        trending_tags: list[str]
    ) -> dict:
        """
        収集データを統合して「なぜ今これが受けているのか」インサイトを生成
        """
        top_keywords = [t["keyword"] for t in trends[:5] if t["score"] > 50]
        rising_keywords = [t["keyword"] for t in trends if t["momentum"] > 10]

        article_themes = []
        for article in articles[:10]:
            title = article["title"]
            if any(kw in title for kw in ["AI", "ChatGPT", "Claude", "GPT"]):
                article_themes.append("AI活用")
            elif any(kw in title for kw in ["副業", "フリーランス", "在宅"]):
                article_themes.append("副業")
            elif any(kw in title for kw in ["投資", "NISA", "株", "資産"]):
                article_themes.append("投資")
            elif any(kw in title for kw in ["節約", "時短", "効率", "ライフハック"]):
                article_themes.append("時短・効率化")

        theme_counts = Counter(article_themes)

        content_angle, primary_theme = self._determine_content_angle(
            theme_counts, rising_keywords
        )

        insight = {
            "timestamp": datetime.now().isoformat(),
            "top_trending_keywords": top_keywords,
            "rapidly_rising_keywords": rising_keywords,
            "dominant_themes": theme_counts.most_common(3),
            "primary_theme": primary_theme,
            "hot_articles": [
                {"title": a["title"], "url": a["url"]}
                for a in articles[:5]
            ],
            "trending_tags": trending_tags[:10],
            "content_angle": content_angle,
            "why_trending": self._build_why_explanation(
                theme_counts, rising_keywords
            ),
            "recommended_hashtags": config.hashtag_sets.get(primary_theme, [])
        }
        return insight

    def _determine_content_angle(
        self,
        theme_counts: Counter,
        rising_keywords: list[str]
    ) -> tuple[str, str]:
        """今最も効果的なコンテンツの切り口とテーマを返す"""
        if not theme_counts:
            return "AIツールで仕事を10倍効率化する具体的な方法", "AI活用"

        top_theme = theme_counts.most_common(1)[0][0]
        angle_map = {
            "AI活用": "AIツールで仕事を10倍効率化する具体的な方法",
            "副業": "月3万円から始める現実的な副業戦略",
            "投資": "新NISAを最大活用する初心者向け入門",
            "時短・効率化": "残業ゼロを実現する時短テクニック集"
        }
        return angle_map.get(top_theme, "生産性を劇的に上げるAI活用法"), top_theme

    def _build_why_explanation(
        self,
        theme_counts: Counter,
        rising_keywords: list[str]
    ) -> str:
        reasons = []
        if "AI活用" in theme_counts:
            reasons.append("AIツールの急速な進化で一般層にも活用機会が広がっている")
        if "副業" in theme_counts:
            reasons.append("物価上昇と賃金停滞で副収入への需要が高まっている")
        if "投資" in theme_counts:
            reasons.append("新NISA制度で投資初心者が急増している")
        if "時短・効率化" in theme_counts:
            reasons.append("リモートワーク定着で個人の生産性向上への関心が高い")
        if not reasons:
            reasons.append("社会変化への対応として自己投資・スキルアップ需要が増加")
        return " / ".join(reasons)

    def run(self) -> dict:
        """トレンド収集のメインエントリーポイント"""
        logger.info("トレンド収集開始...")

        trends = self.get_google_trends(config.trend_keywords)
        articles = self.get_rss_articles()
        trending_tags = self.get_instagram_trending_hashtags()

        insight = self.analyze_insights(trends, articles, trending_tags)

        logger.info(
            f"トレンド収集完了: "
            f"テーマ={insight['primary_theme']}, "
            f"角度='{insight['content_angle']}'"
        )

        import os
        os.makedirs("data", exist_ok=True)
        with open("data/latest_insight.json", "w", encoding="utf-8") as f:
            json.dump(insight, f, ensure_ascii=False, indent=2)

        return insight
