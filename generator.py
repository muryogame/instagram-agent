"""
generator.py - 高コンバージョン・コンテンツ・ジェネレーター
Instagramに最適化された3パターンのコンテンツを自動生成する
"""
import json
import logging
import os
import re
import textwrap
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import anthropic
import requests
from PIL import Image, ImageDraw, ImageFont

from config import config

logger = logging.getLogger(__name__)


@dataclass
class GeneratedPost:
    post_type: str          # educational / empathy / sales_funnel
    caption: str            # Instagram投稿文（ハッシュタグ含む）
    image_path: str         # 生成した画像のローカルパス
    image_url: Optional[str]  # 公開可能な画像URL（Graph API用）
    hashtags: list[str]
    theme: str
    created_at: str


class ContentGenerator:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=config.anthropic_api_key)
        self.images_dir = Path(config.images_dir)
        self.images_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # パターン1: 教育型（知識欲・信頼構築）
    # ------------------------------------------------------------------
    def generate_educational(self, insight: dict) -> GeneratedPost:
        """読者の知識欲を満たし、信頼を構築するInstagram投稿"""
        theme = insight.get("primary_theme", "AI活用")
        angle = insight.get("content_angle", "")
        why = insight.get("why_trending", "")

        prompt = f"""
あなたはInstagramで10万フォロワーを持つ副業・AI活用の専門インフルエンサーです。
以下のトレンド情報を元に、「教育型」Instagram投稿を作成してください。

【トレンドテーマ】{theme}
【コンテンツ角度】{angle}
【なぜ今受けているか】{why}

【要件】
- 冒頭3行で「おっ、気になる」と思わせる（Instagramは最初3行が勝負）
- 実践的な数字・具体例を3〜5つ含める（「月3万円」「5分でできる」など）
- 読者に価値を提供しつつ、「もっと知りたい」と思わせる終わり方
- プロフィールのリンク（linktree）へ自然に誘導する一文を最後に追加
- 絵文字を適切に使用（見やすさUP）
- 総文字数: 400〜600文字
- 語尾は「です・ます」調

【導線URL】{config.linktree_url}

【ハッシュタグ】（本文の後に改行して追加）
{' '.join(insight.get('recommended_hashtags', [])[:12])}

投稿文のみを出力してください（説明文は不要）。
"""
        caption = self._call_claude(prompt)
        image_path = self._generate_image(
            title=f"{theme}で差をつける方法",
            subtitle=angle,
            style="educational",
            theme=theme
        )
        return GeneratedPost(
            post_type="educational",
            caption=caption,
            image_path=image_path,
            image_url=None,
            hashtags=insight.get("recommended_hashtags", []),
            theme=theme,
            created_at=datetime.now().isoformat()
        )

    # ------------------------------------------------------------------
    # パターン2: 共感・煽り型（PASONA法則）
    # ------------------------------------------------------------------
    def generate_empathy(self, insight: dict) -> GeneratedPost:
        """読者の悩みを言語化し、解決への欲求を高める投稿（PASONA法則）"""
        theme = insight.get("primary_theme", "副業")
        angle = insight.get("content_angle", "")
        keywords = insight.get("top_trending_keywords", [])

        pain_map = {
            "AI活用": "AIに仕事を奪われそうで不安",
            "副業": "会社の給料だけじゃ将来が不安",
            "投資": "貯金してるだけじゃお金が増えない",
            "時短・効率化": "残業続きで自分の時間がない"
        }
        pain = pain_map.get(theme, "このままの生活を続けていいのか不安")

        prompt = f"""
あなたはInstagramで共感を集める副業・マネーリテラシー系インフルエンサーです。
PASONA法則（Problem→Agitation→Solution→Offer→Narrowing→Action）を使って
「共感・煽り型」Instagram投稿を作成してください。

【テーマ】{theme}
【読者の悩み（Problem）】{pain}
【解決角度】{angle}
【トレンドキーワード】{', '.join(keywords[:3])}

【PASONA構成】
P (Problem): 読者が「これ私のことだ」と感じる悩みを言語化（2〜3行）
A (Agitation): そのまま放置するとどうなるか、将来の恐怖を煽る（2〜3行）
S (Solution): 解決策を提示（具体的に3ステップ）
O (Offer): 今すぐできるアクションを提示
N (Narrowing): 「行動できる人は限られている」という限定性
A (Action): プロフィールリンクへ誘導（{config.linktree_url}）

【要件】
- 冒頭は「〇〇な人に見てほしい」「これを知らないと損する」系の強い一言から始める
- 絵文字で視認性を上げる（⚠️❗✅など）
- 総文字数: 450〜650文字

【ハッシュタグ】（本文後に追加）
{' '.join(insight.get('recommended_hashtags', [])[:12])}

投稿文のみ出力してください。
"""
        caption = self._call_claude(prompt)
        image_path = self._generate_image(
            title=pain,
            subtitle="解決策あります",
            style="empathy",
            theme=theme
        )
        return GeneratedPost(
            post_type="empathy",
            caption=caption,
            image_path=image_path,
            image_url=None,
            hashtags=insight.get("recommended_hashtags", []),
            theme=theme,
            created_at=datetime.now().isoformat()
        )

    # ------------------------------------------------------------------
    # パターン3: 導線型（セールス・ファネル）
    # ------------------------------------------------------------------
    def generate_sales_funnel(self, insight: dict) -> GeneratedPost:
        """note・アフィリエイトへ自然に誘導するセールス投稿"""
        theme = insight.get("primary_theme", "AI活用")
        angle = insight.get("content_angle", "")

        prompt = f"""
あなたはInstagramを使ってnoteやアフィリエイトで月100万円を稼ぐマーケターです。
「導線型」Instagram投稿を作成してください。

【テーマ】{theme}
【コンテンツ角度】{angle}

【投稿の目的】
プロフィールのリンク（{config.linktree_url}）から
note記事またはアフィリエイトページへ自然に誘導すること。

【構成】
1. インパクトある「結果・実績・数字」から始める（例：「3ヶ月で副業収入が月5万円になった話」）
2. 具体的なストーリーや体験談（3〜5行）
3. 「詳細はプロフィールリンクのnoteに書いてます」という自然な誘導
4. 読者に「保存」を促す一言（「後で読み返せるように保存しておいて！」）
5. 読者との対話を促すコメント誘導（「あなたはどう思いますか？」）

【要件】
- 押しつけがましくなく、自然な流れで誘導
- 共感ベースのストーリーテリング
- 総文字数: 350〜500文字
- 「今すぐ」「絶対」「保証」などのNGワードは使わない

【ハッシュタグ】
{' '.join(insight.get('recommended_hashtags', [])[:10])}

投稿文のみ出力してください。
"""
        caption = self._call_claude(prompt)
        image_path = self._generate_image(
            title="実績公開",
            subtitle=angle[:20] if angle else "収益化の秘密",
            style="sales",
            theme=theme
        )
        return GeneratedPost(
            post_type="sales_funnel",
            caption=caption,
            image_path=image_path,
            image_url=None,
            hashtags=insight.get("recommended_hashtags", []),
            theme=theme,
            created_at=datetime.now().isoformat()
        )

    # ------------------------------------------------------------------
    # 投稿タイプに応じた生成ディスパッチャー
    # ------------------------------------------------------------------
    def generate(self, post_type: str, insight: dict) -> GeneratedPost:
        dispatch = {
            "morning_insight": self.generate_educational,
            "tips": self.generate_educational,
            "deep_carousel": self.generate_empathy,
            "sales_funnel": self.generate_sales_funnel,
            "educational": self.generate_educational,
            "empathy": self.generate_empathy,
        }
        generator_fn = dispatch.get(post_type, self.generate_educational)
        return generator_fn(insight)

    # ------------------------------------------------------------------
    # Claude API呼び出し
    # ------------------------------------------------------------------
    def _call_claude(self, prompt: str) -> str:
        try:
            message = self.client.messages.create(
                model="claude-opus-4-6",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}]
            )
            return message.content[0].text.strip()
        except Exception as e:
            logger.error(f"Claude API呼び出しエラー: {e}")
            raise

    # ------------------------------------------------------------------
    # 画像生成（テキストオーバーレイ式）
    # ------------------------------------------------------------------
    def _generate_image(
        self,
        title: str,
        subtitle: str,
        style: str,
        theme: str
    ) -> str:
        """
        Instagram用正方形画像を生成する（1080x1080px）
        Stability AIがあれば使用、なければPillowで高品質テキスト画像を生成
        """
        if config.stability_api_key:
            return self._generate_with_stability(title, subtitle, theme)
        else:
            return self._generate_text_image(title, subtitle, style, theme)

    def _generate_text_image(
        self,
        title: str,
        subtitle: str,
        style: str,
        theme: str
    ) -> str:
        """Pillowで高品質なInstagram画像を生成"""
        size = (1080, 1080)

        # スタイル別カラーパレット
        palettes = {
            "educational": {
                "bg": [(20, 30, 70), (10, 60, 120)],    # ネイビー系（信頼・知性）
                "text": (255, 255, 255),
                "accent": (80, 200, 255)
            },
            "empathy": {
                "bg": [(80, 20, 20), (160, 40, 40)],    # レッド系（緊張・共感）
                "text": (255, 255, 255),
                "accent": (255, 200, 50)
            },
            "sales": {
                "bg": [(20, 80, 20), (30, 140, 60)],    # グリーン系（成長・お金）
                "text": (255, 255, 255),
                "accent": (200, 255, 100)
            }
        }
        palette = palettes.get(style, palettes["educational"])

        img = Image.new("RGB", size, palette["bg"][0])
        draw = ImageDraw.Draw(img)

        # グラデーション背景
        for y in range(size[1]):
            ratio = y / size[1]
            r = int(palette["bg"][0][0] * (1 - ratio) + palette["bg"][1][0] * ratio)
            g = int(palette["bg"][0][1] * (1 - ratio) + palette["bg"][1][1] * ratio)
            b = int(palette["bg"][0][2] * (1 - ratio) + palette["bg"][1][2] * ratio)
            draw.line([(0, y), (size[0], y)], fill=(r, g, b))

        # フォント（システムフォントを使用）
        font_paths = [
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/home/takah/.local/share/fonts/NotoSansCJKjp-Bold.otf",
            "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]
        title_font = None
        sub_font = None
        for fp in font_paths:
            if os.path.exists(fp):
                try:
                    title_font = ImageFont.truetype(fp, 72)
                    sub_font = ImageFont.truetype(fp, 40)
                    label_font = ImageFont.truetype(fp, 32)
                    break
                except Exception:
                    continue
        if title_font is None:
            title_font = ImageFont.load_default()
            sub_font = title_font
            label_font = title_font

        # テーマラベル（上部）
        theme_label = f"[ {theme} ]"
        draw.text((540, 180), theme_label, font=label_font,
                  fill=palette["accent"], anchor="mm")

        # タイトル（中央・折り返し）
        wrapped_title = textwrap.fill(title, width=14)
        draw.text((540, 480), wrapped_title, font=title_font,
                  fill=palette["text"], anchor="mm", align="center")

        # サブタイトル
        draw.text((540, 700), subtitle[:24], font=sub_font,
                  fill=palette["accent"], anchor="mm")

        # 装飾ライン
        draw.rectangle([(100, 800), (980, 804)], fill=palette["accent"])

        # CTAテキスト
        draw.text((540, 860), "→ プロフィールのリンクをチェック",
                  font=sub_font, fill=palette["text"], anchor="mm")

        # 保存
        filename = f"{style}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        output_path = self.images_dir / filename
        img.save(str(output_path), "JPEG", quality=95)
        logger.info(f"画像生成完了: {output_path}")
        return str(output_path)

    def _generate_with_stability(
        self,
        title: str,
        subtitle: str,
        theme: str
    ) -> str:
        """Stability AI APIで本格的な画像を生成"""
        try:
            prompt_map = {
                "AI活用": "futuristic technology workspace, minimalist, blue gradient, professional",
                "副業": "successful entrepreneur working laptop cafe, warm tones, aspirational",
                "投資": "growing money plant, green tones, prosperity, minimalist financial",
                "時短・効率化": "organized productive desk setup, clean minimal, white and gold"
            }
            img_prompt = prompt_map.get(
                theme,
                "modern minimalist business lifestyle, professional, instagram worthy"
            )

            resp = requests.post(
                "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image",
                headers={
                    "Authorization": f"Bearer {config.stability_api_key}",
                    "Accept": "application/json"
                },
                json={
                    "text_prompts": [{"text": img_prompt, "weight": 1}],
                    "cfg_scale": 7,
                    "height": 1024,
                    "width": 1024,
                    "steps": 30,
                    "samples": 1
                },
                timeout=60
            )
            resp.raise_for_status()
            data = resp.json()

            import base64
            filename = f"stability_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
            output_path = self.images_dir / filename
            img_data = base64.b64decode(data["artifacts"][0]["base64"])
            with open(str(output_path), "wb") as f:
                f.write(img_data)
            logger.info(f"Stability AI画像生成完了: {output_path}")
            return str(output_path)

        except Exception as e:
            logger.warning(f"Stability AI失敗、テキスト画像にフォールバック: {e}")
            return self._generate_text_image(title, subtitle, "educational", theme)
