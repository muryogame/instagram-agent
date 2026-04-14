"""
token_refresh.py - Instagramアクセストークン自動更新
60日で切れるトークンを自動で更新してGitHub Secretsに反映する
"""
import logging
import os
import re
import subprocess
from datetime import datetime

import requests
from dotenv import load_dotenv, set_key

load_dotenv()
logger = logging.getLogger(__name__)


def refresh_long_lived_token() -> str | None:
    """
    現在の長期トークンを使って新しい長期トークンを取得する
    （長期トークンは有効期限内であれば更新可能）
    """
    access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
    app_id = os.getenv("FACEBOOK_APP_ID", "")
    app_secret = os.getenv("FACEBOOK_APP_SECRET", "")

    if not all([access_token, app_id, app_secret]):
        logger.error("必要な環境変数が不足しています")
        return None

    try:
        resp = requests.get(
            "https://graph.facebook.com/v19.0/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": app_id,
                "client_secret": app_secret,
                "fb_exchange_token": access_token,
            },
            timeout=15
        )
        data = resp.json()

        if "access_token" in data:
            new_token = data["access_token"]
            expires_in = data.get("expires_in", 0)
            days = expires_in // 86400
            logger.info(f"トークン更新成功: 有効期限 約{days}日")
            return new_token
        else:
            logger.error(f"トークン更新失敗: {data}")
            return None

    except Exception as e:
        logger.error(f"トークン更新エラー: {e}")
        return None


def update_env_file(new_token: str):
    """.envファイルのトークンを更新する"""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    set_key(env_path, "INSTAGRAM_ACCESS_TOKEN", new_token)
    logger.info(".envファイルのトークンを更新しました")


def update_github_secret(new_token: str):
    """GitHub CLIを使ってSecretsを更新する"""
    try:
        result = subprocess.run(
            ["gh", "secret", "set", "INSTAGRAM_ACCESS_TOKEN",
             "--body", new_token,
             "--repo", "muryogame/instagram-agent"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            logger.info("GitHub Secretsのトークンを更新しました")
        else:
            logger.warning(f"GitHub Secrets更新失敗: {result.stderr}")
    except FileNotFoundError:
        logger.warning("GitHub CLIがインストールされていません（手動更新が必要）")
    except Exception as e:
        logger.warning(f"GitHub Secrets更新エラー: {e}")


def check_token_validity() -> dict:
    """現在のトークンの有効期限を確認する"""
    access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
    if not access_token:
        return {"valid": False, "error": "トークンが未設定"}

    try:
        resp = requests.get(
            "https://graph.facebook.com/v19.0/debug_token",
            params={
                "input_token": access_token,
                "access_token": f"{os.getenv('FACEBOOK_APP_ID')}|{os.getenv('FACEBOOK_APP_SECRET')}"
            },
            timeout=15
        )
        data = resp.json().get("data", {})
        is_valid = data.get("is_valid", False)
        expires_at = data.get("expires_at", 0)

        if expires_at:
            expires_dt = datetime.fromtimestamp(expires_at)
            days_left = (expires_dt - datetime.now()).days
            return {
                "valid": is_valid,
                "expires_at": expires_dt.strftime("%Y-%m-%d"),
                "days_left": days_left
            }
        return {"valid": is_valid, "expires_at": "無期限"}

    except Exception as e:
        return {"valid": False, "error": str(e)}


def run():
    """トークン更新のメイン処理"""
    logging.basicConfig(level=logging.INFO)

    # 現在のトークン状態を確認
    status = check_token_validity()
    logger.info(f"現在のトークン状態: {status}")

    # 30日以内に切れる場合は更新
    days_left = status.get("days_left", 0)
    if not status.get("valid") or (isinstance(days_left, int) and days_left < 30):
        logger.info("トークンを更新します...")
        new_token = refresh_long_lived_token()

        if new_token:
            update_env_file(new_token)
            update_github_secret(new_token)
            logger.info("トークン更新完了")
        else:
            logger.error("トークン更新に失敗しました。手動で更新が必要です。")
    else:
        logger.info(f"トークンは有効です（残り{days_left}日）。更新不要。")


if __name__ == "__main__":
    run()
