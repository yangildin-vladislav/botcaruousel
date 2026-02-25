"""
CarouselGenerator v5  —  точное совпадение с референсом
═════════════════════════════════════════════════════════

Холст: 2160 × 1080px (два слайда по 1080×1080)

Разметка (все координаты на общем холсте):
  ┌──────────────┬──────────────────┬──────────────┐
  │  Слайд 1     │   Фото (864×864) │  Слайд 2     │
  │  0..1080     │   648..1512      │  1080..2160  │
  │              │   top: 108       │              │
  │  [ARTIST]    │                  │  [LYRICS]    │
  │  [TRACK]     │                  │              │
  └──────────────┴──────────────────┴──────────────┘

Фото:
  - Обрезается в квадрат 1:1 по центру
  - Вставляется X=648, Y=108, размер 864×864
  - Скруглённые углы ~50px
  - Центр фото X=1080 = граница слайдов → при листании перетекает

Слайд 1 (левая половина, 0..1080):
  - Фон: размытое фото
  - Ник артиста по центру левой зоны (0..648), вертикально по центру
  - Название трека ниже ника

Слайд 2 (правая половина, 1080..2160):
  - Фон: размытое фото (продолжение)
  - Правая половина чёткого фото (1080..1512)
  - Текст трека: справа от фото (1562..2110), каждая строка оригинала — отдельная строка

Вывод: PNG compress_level=0 (без сжатия)
Имена: {stem}_левая_часть.png / {stem}_правая_часть.png
"""

import io
import textwrap
from pathlib import Path
from PIL import Image, ImageFilter, ImageDraw, ImageFont, ImageEnhance

# ── Размеры ──────────────────────────────────────────────────────────────────
CANVAS_W  = 2160
CANVAS_H  = 1080
SLIDE_W   = 1080
SLIDE_H   = 1080

PHOTO_SZ  = 864                          # квадрат
PHOTO_X   = SLIDE_W - PHOTO_SZ // 2     # 1080 - 432 = 648
PHOTO_Y   = (CANVAS_H - PHOTO_SZ) // 2  # (1080-864)//2 = 108
CORNER_R  = 50

# Зоны текста
ARTIST_X0 = 50                           # от этого x
ARTIST_X1 = PHOTO_X - 30                # до левого края фото = 618
ARTIST_CX = (ARTIST_X0 + ARTIST_X1) // 2  # центр зоны артиста = 334

TEXT_X0   = PHOTO_X + PHOTO_SZ + 50     # правее фото: 648+864+50 = 1562
TEXT_X1   = CANVAS_W - 50              # 2110
TEXT_W    = TEXT_X1 - TEXT_X0          # 548

# ── Шрифты (Carlito — кириллица + латиница) ──────────────────────────────────
FONTS = {
    "bold":   "/usr/share/fonts/truetype/crosextra/Carlito-Bold.ttf",
    "medium": "/usr/share/fonts/truetype/crosextra/Carlito-Regular.ttf",
    "light":  "/usr/share/fonts/truetype/crosextra/Carlito-Regular.ttf",
    "italic": "/usr/share/fonts/truetype/crosextra/Carlito-BoldItalic.ttf",
}
FALLBACK = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

TEXT_COLORS = {
    "white":  (255, 255, 255),
    "yellow": (255, 225, 60),
    "cyan":   (60, 220, 255),
    "pink":   (255, 80, 190),
    "orange": (255, 150, 40),
    "red":    (255, 60, 60),
    "green":  (60, 220, 120),
}


def font(style: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(FONTS.get(style, FONTS["bold"]), size)
    except Exception:
        try:
            return ImageFont.truetype(FALLBACK, size)
        except Exception:
            return ImageFont.load_default()


# ── Вспомогательные ───────────────────────────────────────────────────────────
def crop_square(img: Image.Image) -> Image.Image:
    w, h = img.size
    s = min(w, h)
    return img.crop(((w-s)//2, (h-s)//2, (w+s)//2, (h+s)//2))


def rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([(0,0),(size,size)], radius=radius, fill=255)
    return mask


def blurred_bg(photo: Image.Image, blur: int) -> Image.Image:
    bg = photo.resize((CANVAS_W, CANVAS_H), Image.LANCZOS)
    if blur > 0:
        bg = bg.filter(ImageFilter.GaussianBlur(radius=blur))
    bg = ImageEnhance.Brightness(bg).enhance(0.38)
    # Лёгкая виньетка
    vig = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0,0,0,0))
    vd  = ImageDraw.Draw(vig)
    for i in range(80):
        a = int(70 * (1 - i/80))
        vd.rectangle([i, i, CANVAS_W-i, CANVAS_H-i], outline=(0,0,0,a))
    return Image.alpha_composite(bg.convert("RGBA"), vig).convert("RGB")


def txt_shadow(draw, xy, text, fnt, color, sh=3):
    x, y = xy
    draw.text((x+sh, y+sh), text, font=fnt, fill=(0,0,0))
    draw.text((x,    y   ), text, font=fnt, fill=color)


# ── Рендер текста трека (построчно, каждая строка оригинала отдельно) ─────────
def render_lyrics(draw, lyrics, style, size, x0, y0, max_w, max_h, color):
    """
    Каждая строка оригинального текста рендерится отдельно.
    Если строка не влезает по ширине — переносится.
    Если весь текст не влезает по высоте — уменьшаем размер шрифта.
    """
    raw_lines = lyrics.split("\n")

    for sz in range(size, 12, -2):
        fnt    = font(style, sz)
        line_h = int(sz * 1.55)

        # Строим список отображаемых строк
        display = []
        for raw in raw_lines:
            raw = raw.strip()
            if not raw:
                display.append("")
                continue
            # Подбираем chars чтобы строка влезала по пикселям
            chars = max(4, int(max_w / (sz * 0.58)))
            parts = textwrap.wrap(raw, width=chars) or [raw]
            # Проверяем и сужаем пока не влезет
            for attempt in range(30):
                if all(draw.textlength(p, font=fnt) <= max_w for p in parts):
                    break
                chars -= 1
                parts = textwrap.wrap(raw, width=max(3, chars)) or [raw[:chars]]
            display.extend(parts)

        total_h = len(display) * line_h
        if total_h > max_h:
            continue  # Не влезает — уменьшаем шрифт

        # Рендерим
        y = y0
        for i, line in enumerate(display):
            if line:
                txt_shadow(draw, (x0, y), line, fnt, color)
            y += line_h
        return sz

    # Крайний случай: рисуем мелко
    fnt = font(style, 13)
    y   = y0
    for raw in raw_lines:
        txt_shadow(draw, (x0, y), raw[:80], fnt, color)
        y += 20
    return 13


# ── Главный класс ─────────────────────────────────────────────────────────────
class CarouselGenerator:
    def __init__(self, settings: dict):
        self.s = settings

    def make_carousel(self, photo_bytes: bytes, artist: str, track: str,
                      lyrics: str, original_filename: str = "image") -> tuple:
        """Возвращает (slide1_png, slide2_png, name1, name2)"""
        s       = self.s
        blur    = s.get("blur", 20)
        color   = TEXT_COLORS.get(s.get("text_color", "white"), (255,255,255))
        style   = s.get("font", "bold")
        sz1     = int(s.get("font_size_slide1", 78))
        sz2     = int(s.get("font_size_slide2", 44))

        stem  = Path(original_filename).stem
        name1 = f"{stem}_левая_часть.png"
        name2 = f"{stem}_правая_часть.png"

        photo = Image.open(io.BytesIO(photo_bytes)).convert("RGB")

        # ── 1. Размытый фон ─────────────────────────────────────────────────
        canvas = blurred_bg(photo, blur)

        # ── 2. Чёткое квадратное фото по центру холста ──────────────────────
        sq = crop_square(photo).resize((PHOTO_SZ, PHOTO_SZ), Image.LANCZOS)
        sq_rgba = sq.convert("RGBA")
        sq_rgba.putalpha(rounded_mask(PHOTO_SZ, CORNER_R))

        canvas_rgba = canvas.convert("RGBA")
        canvas_rgba.paste(sq_rgba, (PHOTO_X, PHOTO_Y), sq_rgba)
        canvas = canvas_rgba.convert("RGB")

        draw = ImageDraw.Draw(canvas)

        # ── 3. Слайд 1: Артист + трек (левая зона 0..648) ───────────────────
        # Рисуем ПОСЛЕ вставки фото → текст поверх фона, не поверх фото
        fnt_artist = font(style, sz1)
        fnt_track  = font(style, max(14, sz1 - 20))

        ab = draw.textbbox((0,0), artist, font=fnt_artist)
        tb = draw.textbbox((0,0), track,  font=fnt_track)
        a_h = ab[3] - ab[1]
        t_h = tb[3] - tb[1]
        gap = 22
        block_h = a_h + gap + t_h
        by = (CANVAS_H - block_h) // 2

        # Убеждаемся что текст не заезжает на фото — клипаем к ARTIST_X1
        a_w = ab[2] - ab[0]
        ax = max(ARTIST_X0, min(ARTIST_CX - a_w//2, ARTIST_X1 - a_w))
        txt_shadow(draw, (ax, by), artist, fnt_artist, color)

        t_w = tb[2] - tb[0]
        tx = max(ARTIST_X0, min(ARTIST_CX - t_w//2, ARTIST_X1 - t_w))
        txt_shadow(draw, (tx, by + a_h + gap), track, fnt_track, color)

        # ── 4. Слайд 2: Текст трека (правее фото, 1562..2110) ───────────────
        render_lyrics(
            draw   = draw,
            lyrics = lyrics,
            style  = style,
            size   = sz2,
            x0     = TEXT_X0,
            y0     = PHOTO_Y + 10,
            max_w  = TEXT_W,
            max_h  = PHOTO_SZ - 20,
            color  = color,
        )

        # ── 5. Нарезаем и возвращаем ─────────────────────────────────────────
        def to_png(im):
            buf = io.BytesIO()
            im.save(buf, "PNG", compress_level=0)
            return buf.getvalue()

        s1 = to_png(canvas.crop((0,      0, SLIDE_W,   SLIDE_H)))
        s2 = to_png(canvas.crop((SLIDE_W, 0, CANVAS_W, SLIDE_H)))
        return s1, s2, name1, name2
