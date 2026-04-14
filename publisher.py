"""
publisher.py - Instagram Graph API パブリッシャー
画像アップロードから投稿公開まで、レートリミット対応で安全に実行する
"""
import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

from config import config
from generator import GeneratedPost

logger = logging.getLogger(__name__)


class RateLimitError(Exception):
    pass


class ShadowBanRisk(Exception):
    pass


@dataclass
class PublishResult:
    success: bool
    post_id: Optional[str]
    permalink: Optional[str]
    error: Optional[str]
    timestamp: str


class InstagramPublisher:
    def __init__(self):
        self.base_url = config.ig_api_base
        self.account_id = config.instagram_account_id
        self.access_token = config.instagram_access_token
        self.db_path = config.db_file
        self._init_db()

    # ------------------------------------------------------------------
    # DB初期化（投稿履歴管理）
    # ------------------------------------------------------------------
    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id TEXT,
                permalink TEXT,
                post_type TEXT,
                theme TEXT,
                caption TEXT,
                image_path TEXT,
                published_at TEXT,
                impressions INTEGER DEFAULT 0,
                likes INTEGER DEFAULT 0,
                comments INTEGER DEFAULT 0,
                saves INTEGER DEFAULT 0,
                reach INTEGER DEFAULT 0
            )
        """)
        conn.commit()
        conn.close()

    # ------------------------------------------------------------------
    # 投稿前チェック
    # ------------------------------------------------------------------
    def check_daily_limit(self) -> bool:
        """1日の投稿上限チェック"""
        conn = sqlite3.connect(self.db_path)
        today = date.today().isoformat()
        count = conn.execute(
            "SELECT COUNT(*) FROM posts WHERE published_at LIKE ?",
            (f"{today}%",)
        ).fetchone()[0]
        conn.close()
        if count >= config.daily_post_limit:
            logger.warning(f"本日の投稿上限({config.daily_post_limit})に達しています")
            return False
        return True

    def shadow_ban_check(self, caption: str) -> tuple[bool, list[str]]:
        """
        シャドウバン・リスクチェッカー
        NGワード、過度なハッシュタグ、スパム的表現を検出
        """
        risks = []

        # NGワードチェック
        found_ng = [w for w in config.ng_words if w in caption]
        if found_ng:
            risks.append(f"NGワード検出: {found_ng}")

        # ハッシュタグ数チェック（30個以上はリスク）
        hashtag_count = caption.count("#")
        if hashtag_count > 30:
            risks.append(f"ハッシュタグ過多: {hashtag_count}個（推奨: 15〜25個）")

        # URL過多チェック（2個以上はリスク）
        url_count = caption.count("http")
        if url_count >= 2:
            risks.append(f"URL過多: {url_count}個（Instagramはキャプション内リンク非推奨）")

        # 文字数チェック（2200文字以内）
        if len(caption) > 2200:
            risks.append(f"文字数超過: {len(caption)}文字（上限: 2200文字）")

        is_safe = len(risks) == 0
        if not is_safe:
            logger.warning(f"シャドウバンリスク検出: {risks}")
        return is_safe, risks

    # ------------------------------------------------------------------
    # 画像アップロード（公開URLが必要なため imgbb/imgur を使用）
    # ------------------------------------------------------------------
    def upload_image_to_hosting(self, image_path: str) -> str:
        """
        画像を一時ホスティングサービスにアップロードして公開URLを取得
        Instagram Graph APIは公開URLが必要
        """
        # ImgBBを使用（無料プランで動作）
        imgbb_key = os.getenv("IMGBB_API_KEY", "")
        if imgbb_key:
            return self._upload_to_imgbb(image_path, imgbb_key)

        # フォールバック: Catbox
        return self._upload_to_catbox(image_path)

    def _upload_to_imgbb(self, image_path: str, api_key: str) -> str:
        import base64
        with open(image_path, "rb") as f:
            img_data = base64.b64encode(f.read()).decode("utf-8")

        resp = requests.post(
            "https://api.imgbb.com/1/upload",
            data={"key": api_key, "image": img_data},
            timeout=30
        )
        resp.raise_for_status()
        return resp.json()["data"]["url"]

    def _upload_to_catbox(self, image_path: str) -> str:
        with open(image_path, "rb") as f:
            resp = requests.post(
                "https://catbox.moe/user/api.php",
                data={"reqtype": "fileupload"},
                files={"fileToUpload": f},
                timeout=30
            )
        resp.raise_for_status()
        url = resp.text.strip()
        if not url.startswith("http"):
            raise ValueError(f"Catbox upload failed: {url}")
        return url

    # ------------------------------------------------------------------
    # Instagram Graph API 投稿フロー
    # ------------------------------------------------------------------
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=10, max=300),
        retry=retry_if_exception_type(RateLimitError)
    )
    def _create_media_container(self, image_url: str, caption: str) -> str:
        """Step 1: メディアコンテナを作成"""
        resp = requests.post(
            f"{self.base_url}/{self.account_id}/media",
            params={
                "image_url": image_url,
                "caption": caption,
                "access_token": self.access_token
            },
            timeout=30
        )
        data = resp.json()

        if "error" in data:
            err_code = data["error"].get("code", 0)
            if err_code in [4, 32, 613]:  # レートリミット系
                raise RateLimitError(data["error"]["message"])
            raise ValueError(f"メディアコンテナ作成失敗: {data['error']}")

        return data["id"]

    def _wait_for_container(self, container_id: str, max_wait: int = 60) -> bool:
        """Step 2: コンテナが準備完了になるまで待機"""
        for _ in range(max_wait // 5):
            resp = requests.get(
                f"{self.base_url}/{container_id}",
                params={
                    "fields": "status_code",
                    "access_token": self.access_token
                },
                timeout=15
            )
            status = resp.json().get("status_code", "")
            if status == "FINISHED":
                return True
            elif status == "ERROR":
                logger.error("コンテナ処理エラー")
                return False
            time.sleep(5)
        return False

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=10, max=300),
        retry=retry_if_exception_type(RateLimitError)
    )
    def _publish_container(self, container_id: str) -> str:
        """Step 3: コンテナを公開して投稿IDを取得"""
        resp = requests.post(
            f"{self.base_url}/{self.account_id}/media_publish",
            params={
                "creation_id": container_id,
                "access_token": self.access_token
            },
            timeout=30
        )
        data = resp.json()

        if "error" in data:
            err_code = data["error"].get("code", 0)
            if err_code in [4, 32, 613]:
                raise RateLimitError(data["error"]["message"])
            raise ValueError(f"投稿公開失敗: {data['error']}")

        return data["id"]

    def _get_post_permalink(self, post_id: str) -> Optional[str]:
        """投稿のパーマリンクを取得"""
        try:
            resp = requests.get(
                f"{self.base_url}/{post_id}",
                params={
                    "fields": "permalink",
                    "access_token": self.access_token
                },
                timeout=15
            )
            return resp.json().get("permalink")
        except Exception:
            return None

    # ------------------------------------------------------------------
    # メイン投稿メソッド
    # ------------------------------------------------------------------
    def publish(self, post: GeneratedPost) -> PublishResult:
        timestamp = datetime.now().isoformat()

        # DRY_RUNモード
        if config.dry_run:
            logger.info(f"[DRY_RUN] 投稿をシミュレート: {post.post_type}")
            logger.info(f"[DRY_RUN] キャプション冒頭: {post.caption[:100]}...")
            self._save_to_db(post, "dry_run_id", None)
            return PublishResult(
                success=True,
                post_id="dry_run_id",
                permalink=None,
                error=None,
                timestamp=timestamp
            )

        # 日次上限チェック
        if not self.check_daily_limit():
            return PublishResult(
                success=False, post_id=None, permalink=None,
                error="日次投稿上限到達", timestamp=timestamp
            )

        # シャドウバンチェック
        is_safe, risks = self.shadow_ban_check(post.caption)
        if not is_safe:
            logger.warning(f"シャドウバンリスクのため投稿をスキップ: {risks}")
            return PublishResult(
                success=False, post_id=None, permalink=None,
                error=f"シャドウバンリスク: {risks}", timestamp=timestamp
            )

        try:
            # 画像をホスティングサービスにアップロード
            logger.info(f"画像アップロード中: {post.image_path}")
            image_url = self.upload_image_to_hosting(post.image_path)
            logger.info(f"画像URL取得: {image_url}")

            # メディアコンテナ作成
            logger.info("Instagramメディアコンテナ作成中...")
            container_id = self._create_media_container(image_url, post.caption)

            # コンテナ準備待ち
            if not self._wait_for_container(container_id):
                raise ValueError("メディアコンテナの準備がタイムアウト")

            # 公開
            logger.info("Instagram投稿を公開中...")
            post_id = self._publish_container(container_id)
            permalink = self._get_post_permalink(post_id)

            self._save_to_db(post, post_id, permalink)
            logger.info(f"投稿成功! ID: {post_id}, URL: {permalink}")

            return PublishResult(
                success=True,
                post_id=post_id,
                permalink=permalink,
                error=None,
                timestamp=timestamp
            )

        except Exception as e:
            logger.error(f"投稿失敗: {e}")
            return PublishResult(
                success=False, post_id=None, permalink=None,
                error=str(e), timestamp=timestamp
            )

    def _save_to_db(
        self,
        post: GeneratedPost,
        post_id: str,
        permalink: Optional[str]
    ):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """INSERT INTO posts
               (post_id, permalink, post_type, theme, caption, image_path, published_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (post_id, permalink, post.post_type, post.theme,
             post.caption, post.image_path, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
