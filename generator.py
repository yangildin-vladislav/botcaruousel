"""
CarouselGenerator v6
════════════════════
Холст: 2160×1080 (два слайда 1080×1080)

Фото:
  - Обрезается в квадрат 1:1
  - Размер 864×864, центрировано на стыке слайдов (x=648..1512)
  - Скруглённые углы 50px

Слайд 1 (0..1080):  размытый фон + артист + трек (центр левой зоны)
Слайд 2 (1080..2160): правая часть фото + текст ВЫРОВНЕН ПО ЦЕНТРУ слайда 2

Шрифт: font.ttf (пользовательский, рядом с файлом)
       Fallback: Carlito-Bold → DejaVuSans-Bold
"""

import io
import os
import textwrap
from pathlib import Path
from PIL import Image, ImageFilter, ImageDraw, ImageFont, ImageEnhance

# ── Размеры ──────────────────────────────────────────────────────────────────
CANVAS_W = 2160
CANVAS_H = 1080
SLIDE_W  = 1080
SLIDE_H  = 1080

PHOTO_SZ = 864
PHOTO_X  = SLIDE_W - PHOTO_SZ // 2    # 648
PHOTO_Y  = (CANVAS_H - PHOTO_SZ) // 2 # 108
CORNER_R = 50

# Левая зона (артист/трек): 0..PHOTO_X
ARTIST_X0 = 50
ARTIST_X1 = PHOTO_X - 30              # 618
ARTIST_CX = (ARTIST_X0 + ARTIST_X1) // 2  # ~334

# Правая зона (текст трека): полностью слайд 2 (относительно холста: 1080..2160)
LYRICS_PAD = 60   # отступ по бокам внутри слайда 2

# ── Шрифты ───────────────────────────────────────────────────────────────────
_HERE = Path(__file__).parent

def _find_font() -> str:
    """Ищет font.ttf рядом со скриптом, затем системные fallback."""
    custom = _HERE / "font.ttf"
    if custom.exists():
        return str(custom)
    fallbacks = [
        "/usr/share/fonts/truetype/crosextra/Carlito-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for f in fallbacks:
        if Path(f).exists():
            return f
    return None

FONT_PATH = _find_font()

def get_font(size: int) -> ImageFont.FreeTypeFont:
    if FONT_PATH:
        try:
            return ImageFont.truetype(FONT_PATH, size)
        except Exception:
            pass
    return ImageFont.load_default()

TEXT_COLORS = {
    "white":  (255, 255, 255),
    "yellow": (255, 225, 60),
    "cyan":   (60, 220, 255),
    "pink":   (255, 80, 190),
    "orange": (255, 150, 40),
    "red":    (255, 60, 60),
    "green":  (60, 220, 120),
}


# ── Вспомогательные ───────────────────────────────────────────────────────────
def crop_square(img: Image.Image) -> Image.Image:
    w, h = img.size
    s = min(w, h)
    return img.crop(((w-s)//2, (h-s)//2, (w+s)//2, (h+s)//2))


def rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([(0,0),(size,size)], radius=radius, fill=255)
    return mask


def make_bg(photo: Image.Image, blur: int) -> Image.Image:
    bg = photo.resize((CANVAS_W, CANVAS_H), Image.LANCZOS)
    if blur > 0:
        bg = bg.filter(ImageFilter.GaussianBlur(radius=blur))
    bg = ImageEnhance.Brightness(bg).enhance(0.38)
    vig = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0,0,0,0))
    vd  = ImageDraw.Draw(vig)
    for i in range(80):
        a = int(70 * (1 - i/80))
        vd.rectangle([i, i, CANVAS_W-i, CANVAS_H-i], outline=(0,0,0,a))
    return Image.alpha_composite(bg.convert("RGBA"), vig).convert("RGB")


def shadow(draw, xy, text, fnt, color, sh=3):
    x, y = xy
    draw.text((x+sh, y+sh), text, font=fnt, fill=(0,0,0))
    draw.text((x,    y   ), text, font=fnt, fill=color)


def shadow_centered(draw, text, fnt, color, cx, y, sh=3):
    """Рисует текст с центром по cx."""
    bb = draw.textbbox((0,0), text, font=fnt)
    w  = bb[2] - bb[0]
    shadow(draw, (cx - w//2, y), text, fnt, color, sh)


# ── Рендер текста трека — ЦЕНТРИРОВАН на слайде 2 ────────────────────────────
def render_lyrics_centered(draw, lyrics, size, color, slide2_cx):
    """
    Рендерит текст трека построчно, каждая строка — по центру слайда 2.
    Авто-уменьшение если не влезает по высоте.
    slide2_cx — центр слайда 2 по X на холсте = 1080 + 540 = 1620
    """
    raw_lines = [l.strip() for l in lyrics.split("\n")]
    max_w = SLIDE_W - LYRICS_PAD * 2   # 960px
    max_h = CANVAS_H - LYRICS_PAD * 2  # 960px

    for sz in range(size, 12, -2):
        fnt    = get_font(sz)
        line_h = int(sz * 1.6)

        # Wrap каждую строку
        display = []
        for raw in raw_lines:
            if not raw:
                display.append("")
                continue
            chars = max(4, int(max_w / (sz * 0.58)))
            parts = textwrap.wrap(raw, width=chars) or [raw]
            for attempt in range(30):
                if all(draw.textlength(p, font=fnt) <= max_w for p in parts):
                    break
                chars -= 1
                parts = textwrap.wrap(raw, width=max(3, chars)) or [raw[:chars]]
            display.extend(parts)

        total_h = len(display) * line_h
        if total_h > max_h:
            continue

        # Вертикально центрируем блок текста на слайде 2
        y = (CANVAS_H - total_h) // 2

        for line in display:
            if line:
                shadow_centered(draw, line, fnt, color, slide2_cx, y)
            y += line_h
        return sz

    # Fallback
    fnt = get_font(13)
    y   = LYRICS_PAD
    for raw in raw_lines:
        shadow_centered(draw, raw[:80], fnt, color, slide2_cx, y)
        y += 20
    return 13


# ── Главный класс ─────────────────────────────────────────────────────────────
class CarouselGenerator:
    def __init__(self, settings: dict):
        self.s = settings

    def make_carousel(self, photo_bytes: bytes, artist: str, track: str,
                      lyrics: str, original_filename: str = "image.jpg") -> tuple:
        """Возвращает (slide1_png, slide2_png, name1, name2)"""
        s     = self.s
        blur  = s.get("blur", 22)
        color = TEXT_COLORS.get(s.get("text_color", "white"), (255,255,255))
        sz1   = int(s.get("font_size_slide1", 78))
        sz2   = int(s.get("font_size_slide2", 44))

        stem  = Path(original_filename).stem
        name1 = f"{stem}_левая_часть.png"
        name2 = f"{stem}_правая_часть.png"

        photo = Image.open(io.BytesIO(photo_bytes)).convert("RGB")

        # 1. Размытый фон
        canvas = make_bg(photo, blur)

        # 2. Квадратное фото с скруглёнными углами
        sq      = crop_square(photo).resize((PHOTO_SZ, PHOTO_SZ), Image.LANCZOS)
        sq_rgba = sq.convert("RGBA")
        sq_rgba.putalpha(rounded_mask(PHOTO_SZ, CORNER_R))
        cv_rgba = canvas.convert("RGBA")
        cv_rgba.paste(sq_rgba, (PHOTO_X, PHOTO_Y), sq_rgba)
        canvas  = cv_rgba.convert("RGB")

        # 4. Тёмный overlay на слайд 2 чтобы текст читался поверх фото
        ov = Image.new("RGBA", (SLIDE_W, SLIDE_H), (0, 0, 0, 150))
        cv_rgba2 = canvas.convert("RGBA")
        cv_rgba2.paste(ov, (SLIDE_W, 0), ov)
        canvas = cv_rgba2.convert("RGB")

        draw = ImageDraw.Draw(canvas)

        # 5. Слайд 1: Артист + трек по центру левой зоны
        fnt_artist = get_font(sz1)
        fnt_track  = get_font(max(14, sz1 - 20))

        ab = draw.textbbox((0,0), artist, font=fnt_artist)
        tb = draw.textbbox((0,0), track,  font=fnt_track)
        a_h     = ab[3] - ab[1]
        t_h     = tb[3] - tb[1]
        gap     = 24
        block_h = a_h + gap + t_h
        by      = (CANVAS_H - block_h) // 2

        shadow_centered(draw, artist, fnt_artist, color, ARTIST_CX, by)
        shadow_centered(draw, track,  fnt_track,  color, ARTIST_CX, by + a_h + gap)

        # 6. Слайд 2: Текст трека — центр слайда 2 по X
        slide2_cx = SLIDE_W + SLIDE_W // 2   # 1080 + 540 = 1620

        render_lyrics_centered(
            draw       = draw,
            lyrics     = lyrics,
            size       = sz2,
            color      = color,
            slide2_cx  = slide2_cx,
        )

        # 7. Нарезаем
        def to_png(im):
            buf = io.BytesIO()
            im.save(buf, "PNG", compress_level=0)
            return buf.getvalue()

        s1 = to_png(canvas.crop((0,      0, SLIDE_W,   SLIDE_H)))
        s2 = to_png(canvas.crop((SLIDE_W, 0, CANVAS_W, SLIDE_H)))
        return s1, s2, name1, name2
