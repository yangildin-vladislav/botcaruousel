"""
CarouselGenerator — делает 2 слайда для TikTok карусели.
Слайд 1: размытый фон + имя артиста + название трека
Слайд 2: размытый фон (продолжение) + текст трека
Вместе они образуют цельную картину при листании.
"""

import io
from PIL import Image, ImageFilter, ImageDraw, ImageFont, ImageEnhance
import textwrap
import urllib.request
import os
import math

# ── Размеры TikTok (9:16) ────────────────────────────────────────────────────
SLIDE_W = 1080
SLIDE_H = 1920
CANVAS_W = SLIDE_W * 2  # общий холст = 2 слайда рядом

# ── Цвета ────────────────────────────────────────────────────────────────────
TEXT_COLORS = {
    "white":  (255, 255, 255),
    "yellow": (255, 230, 80),
    "cyan":   (80, 230, 255),
    "pink":   (255, 100, 200),
    "orange": (255, 160, 50),
}

# ── Шрифты (Google Fonts CDN — скачиваем при первом запуске) ────────────────
FONTS_DIR = os.path.join(os.path.dirname(__file__), "fonts")
os.makedirs(FONTS_DIR, exist_ok=True)

FONT_URLS = {
    "bold":   "https://github.com/google/fonts/raw/main/ofl/montserrat/static/Montserrat-Bold.ttf",
    "light":  "https://github.com/google/fonts/raw/main/ofl/montserrat/static/Montserrat-Light.ttf",
    "italic": "https://github.com/google/fonts/raw/main/ofl/montserrat/static/Montserrat-BoldItalic.ttf",
}

def download_font(style: str) -> str:
    path = os.path.join(FONTS_DIR, f"font_{style}.ttf")
    if not os.path.exists(path):
        print(f"Downloading font: {style}...")
        urllib.request.urlretrieve(FONT_URLS[style], path)
    return path


def load_font(style: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        path = download_font(style)
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


# ── Generator ────────────────────────────────────────────────────────────────
class CarouselGenerator:
    def __init__(self, settings: dict):
        self.settings = settings

    def make_carousel(
        self,
        photo_bytes: bytes,
        artist: str,
        track: str,
        lyrics: str,
    ) -> tuple[bytes, bytes]:
        """Returns (slide1_bytes, slide2_bytes) as JPEG."""

        s = self.settings
        blur_radius = s.get("blur", 18)
        text_color = TEXT_COLORS.get(s.get("text_color", "white"), (255, 255, 255))
        font_style = s.get("font", "bold")
        font_size = s.get("font_size", 52)
        use_gradient = s.get("gradient", True)

        # 1. Загружаем и растягиваем фото на ДВОЙНОЙ холст
        img = Image.open(io.BytesIO(photo_bytes)).convert("RGB")
        canvas = img.resize((CANVAS_W, SLIDE_H), Image.LANCZOS)

        # 2. Размытие
        bg = canvas.filter(ImageFilter.GaussianBlur(radius=blur_radius))

        # 3. Затемнение
        bg = ImageEnhance.Brightness(bg).enhance(0.45)

        # 4. Градиентный оверлей (опционально)
        if use_gradient:
            grad = Image.new("RGBA", (CANVAS_W, SLIDE_H), (0, 0, 0, 0))
            draw_g = ImageDraw.Draw(grad)
            for y in range(SLIDE_H):
                alpha = int(180 * (y / SLIDE_H) ** 1.5)
                draw_g.line([(0, y), (CANVAS_W, y)], fill=(0, 0, 0, alpha))
            bg = bg.convert("RGBA")
            bg = Image.alpha_composite(bg, grad).convert("RGB")

        draw = ImageDraw.Draw(bg)

        # ── СЛАЙД 1: Артист + Трек ──────────────────────────────────────────
        font_artist = load_font(font_style, font_size + 10)
        font_track  = load_font(font_style, font_size)
        font_hint   = load_font("light", 32)

        # Маленький разделитель
        line_y = SLIDE_H // 2 - 20

        # Имя артиста
        a_bbox = draw.textbbox((0, 0), artist.upper(), font=font_artist)
        a_w = a_bbox[2] - a_bbox[0]
        a_x = (SLIDE_W - a_w) // 2
        a_y = line_y - 140

        # Тень
        draw.text((a_x + 3, a_y + 3), artist.upper(), font=font_artist, fill=(0, 0, 0, 180))
        draw.text((a_x, a_y), artist.upper(), font=font_artist, fill=text_color)

        # Линия-разделитель
        line_color = (*text_color[:3], 120)
        line_margin = 80
        draw.rectangle(
            [line_margin, line_y + 10, SLIDE_W - line_margin, line_y + 14],
            fill=(*text_color[:3],)
        )

        # Название трека
        t_bbox = draw.textbbox((0, 0), track, font=font_track)
        t_w = t_bbox[2] - t_bbox[0]
        t_x = (SLIDE_W - t_w) // 2
        t_y = line_y + 30

        draw.text((t_x + 2, t_y + 2), track, font=font_track, fill=(0, 0, 0, 180))
        draw.text((t_x, t_y), track, font=font_track, fill=text_color)

        # Подсказка "листай →"
        hint = "листай →"
        h_bbox = draw.textbbox((0, 0), hint, font=font_hint)
        h_w = h_bbox[2] - h_bbox[0]
        draw.text(
            ((SLIDE_W - h_w) // 2, SLIDE_H - 120),
            hint, font=font_hint,
            fill=(*text_color[:3], 160)
        )

        # ── СЛАЙД 2: Текст трека ──────────────────────────────────────────
        font_lyrics = load_font(font_style, font_size - 4)
        font_title2 = load_font("light", 34)

        # Заголовок на слайде 2
        title2 = f"{artist} — {track}"
        t2_bbox = draw.textbbox((0, 0), title2, font=font_title2)
        t2_w = t2_bbox[2] - t2_bbox[0]
        draw.text(
            (SLIDE_W + (SLIDE_W - t2_w) // 2, 100),
            title2, font=font_title2,
            fill=(*text_color[:3], 180)
        )

        # Текст трека — wrapping
        max_chars = max(10, int(SLIDE_W * 0.85 / (font_size * 0.55)))
        lines = []
        for raw_line in lyrics.split("\n"):
            wrapped = textwrap.wrap(raw_line.strip(), width=max_chars) if raw_line.strip() else [""]
            lines.extend(wrapped)

        line_height = font_size + 18
        total_text_h = len(lines) * line_height
        start_y = max(180, (SLIDE_H - total_text_h) // 2)

        for i, line in enumerate(lines):
            l_bbox = draw.textbbox((0, 0), line, font=font_lyrics)
            l_w = l_bbox[2] - l_bbox[0]
            lx = SLIDE_W + (SLIDE_W - l_w) // 2
            ly = start_y + i * line_height
            # Тень
            draw.text((lx + 2, ly + 2), line, font=font_lyrics, fill=(0, 0, 0, 200))
            draw.text((lx, ly), line, font=font_lyrics, fill=text_color)

        # ── Вертикальная линия-стык ──────────────────────────────────────
        # (тонкий акцент посередине — на обоих слайдах по краю)
        stitch_color = (*text_color[:3], 60)
        draw.rectangle([SLIDE_W - 2, 0, SLIDE_W + 2, SLIDE_H], fill=stitch_color)

        # ── Crop в 2 слайда ──────────────────────────────────────────────
        slide1_img = bg.crop((0, 0, SLIDE_W, SLIDE_H))
        slide2_img = bg.crop((SLIDE_W, 0, CANVAS_W, SLIDE_H))

        def to_bytes(im: Image.Image) -> bytes:
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=95)
            return buf.getvalue()

        return to_bytes(slide1_img), to_bytes(slide2_img)
