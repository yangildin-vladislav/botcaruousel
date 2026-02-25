"""
CarouselGenerator v3
════════════════════
Холст: 2160×1080 (2 слайда по 1080×1080)

Логика фото:
  - Фото обрезается в квадрат 1:1 (crop по центру)
  - Холст делится на 5 равных колонок по 432px каждая
  - Квадратная фотка занимает колонки 1–4 на слайде 1 (x: 0..1728)
    т.е. начинается с x=0 и заканчивается на x=1728 (переходит на слайд 2 на 648px)
  - При листании фото "перетекает": на слайде 2 видна правая часть (колонки 4–5, x: 1296..1728 относительно слайда 2)
  
Координаты:
  Колонка 1: 0–432
  Колонка 2: 432–864
  Колонка 3: 864–1296
  Колонка 4: 1296–1728
  Колонка 5: 1728–2160

  Фото (1728×1080 растянутое из квадрата) вставляется от x=0 до x=1728
  → На слайде 1 (0..1080): видна левая часть фото (0..1080px из 1728px)
  → На слайде 2 (1080..2160): видна правая часть фото (648..1728px), т.е. 2/5

Слайд 1: фоновое размытое фото + неразмытая фотка (4/5 ширины) + артист + трек
Слайд 2: фоновое размытое фото + продолжение фотки (2/5 ширины) + текст трека

Текст:
  - justify выравнивание
  - авто-уменьшение если не влезает
  - гарантированный перенос строк
"""

import io
from PIL import Image, ImageFilter, ImageDraw, ImageFont, ImageEnhance
import textwrap

# ── Размеры ──────────────────────────────────────────────────────────────────
SLIDE_W  = 1080
SLIDE_H  = 1080
CANVAS_W = 2160   # 2 слайда
CANVAS_H = 1080

COL = CANVAS_W // 5   # 432px — одна колонка
# Фото занимает колонки 0–3 = 4 колонки = 1728px
PHOTO_START_X = 0
PHOTO_END_X   = COL * 4   # 1728

PADDING = 60

FONT_PATHS = {
    "bold":   "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf",
    "medium": "/usr/share/fonts/truetype/google-fonts/Poppins-Medium.ttf",
    "light":  "/usr/share/fonts/truetype/google-fonts/Poppins-Light.ttf",
    "italic": "/usr/share/fonts/truetype/google-fonts/Poppins-BoldItalic.ttf",
}
FALLBACK_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

TEXT_COLORS = {
    "white":  (255, 255, 255),
    "yellow": (255, 225, 60),
    "cyan":   (60, 220, 255),
    "pink":   (255, 80, 190),
    "orange": (255, 150, 40),
    "red":    (255, 60, 60),
    "green":  (60, 220, 120),
}


# ── Утилиты шрифтов ───────────────────────────────────────────────────────────
def get_font(style: str, size: int) -> ImageFont.FreeTypeFont:
    path = FONT_PATHS.get(style, FONT_PATHS["bold"])
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        try:
            return ImageFont.truetype(FALLBACK_FONT, size)
        except Exception:
            return ImageFont.load_default()


# ── Фон ──────────────────────────────────────────────────────────────────────
def make_bg(photo: Image.Image, blur: int) -> Image.Image:
    """Размытый фон на весь холст 2160×1080."""
    bg = photo.resize((CANVAS_W, CANVAS_H), Image.LANCZOS)
    if blur > 0:
        bg = bg.filter(ImageFilter.GaussianBlur(radius=blur))
    bg = ImageEnhance.Brightness(bg).enhance(0.35)
    return bg.convert("RGB")


def crop_square(photo: Image.Image) -> Image.Image:
    """Обрезает фото по центру в квадрат 1:1."""
    w, h = photo.size
    side = min(w, h)
    left = (w - side) // 2
    top  = (h - side) // 2
    return photo.crop((left, top, left + side, top + side))


# ── Текст с тенью ─────────────────────────────────────────────────────────────
def draw_shadow_text(draw, xy, text, font, color, shadow=3):
    x, y = xy
    draw.text((x + shadow, y + shadow), text, font=font, fill=(0, 0, 0))
    draw.text((x, y), text, font=font, fill=color)


def draw_centered_text(draw, text, font, color, slide_offset_x, y, slide_width=SLIDE_W):
    """Рисует текст по центру слайда."""
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    x = slide_offset_x + (slide_width - w) // 2
    draw_shadow_text(draw, (x, y), text, font, color)


# ── Justify текст ─────────────────────────────────────────────────────────────
def draw_justify_line(draw, line, font, x_start, y, max_w, color, is_last=False):
    words = line.split()
    if not words:
        return
    if is_last or len(words) == 1:
        draw_shadow_text(draw, (x_start, y), line, font, color)
        return
    total_word_w = sum(draw.textlength(w, font=font) for w in words)
    gap_total = max_w - total_word_w
    gap = gap_total / (len(words) - 1)
    cx = float(x_start)
    for i, word in enumerate(words):
        draw_shadow_text(draw, (int(cx), y), word, font, color)
        cx += draw.textlength(word, font=font) + gap


def render_lyrics(draw, lyrics, font_style, font_size, max_w, max_h, color, x0, y0):
    """
    Рендерит текст трека с justify и авто-уменьшением размера.
    Гарантирует что весь текст влезает в max_h.
    """
    raw_lines = [l.rstrip() for l in lyrics.split("\n")]

    for size in range(font_size, 13, -2):
        font = get_font(font_style, size)
        line_h = int(size * 1.55)

        # Wrap каждую строку
        wrapped = []
        for raw in raw_lines:
            if not raw.strip():
                wrapped.append("")
                continue
            # Подбираем ширину обёртки по пикселям
            chars = max(4, int(max_w / (size * 0.54)))
            parts = textwrap.wrap(raw, width=chars) or [""]
            # Проверяем каждую часть на ширину
            for part in parts:
                # Если часть шире — уменьшаем chars
                attempts = 0
                while draw.textlength(part, font=font) > max_w and attempts < 20:
                    chars = max(3, chars - 1)
                    parts = textwrap.wrap(raw, width=chars) or [""]
                    attempts += 1
                wrapped.extend(parts)
                break

        total_h = len(wrapped) * line_h
        if total_h <= max_h:
            # Рендерим
            y = y0
            for i, line in enumerate(wrapped):
                if not line:
                    y += line_h
                    continue
                is_last = (i == len(wrapped) - 1)
                draw_justify_line(draw, line, font, x0, y, max_w, color, is_last)
                y += line_h
            return size

    # Крайний случай — рисуем минимальным
    font = get_font(font_style, 14)
    y = y0
    for raw in raw_lines:
        draw_shadow_text(draw, (x0, y), raw[:90], font, color)
        y += 22
    return 14


# ── Основной класс ────────────────────────────────────────────────────────────
class CarouselGenerator:
    def __init__(self, settings: dict):
        self.s = settings

    def make_carousel(self, photo_bytes: bytes, artist: str, track: str, lyrics: str,
                      original_filename: str = "image") -> tuple[bytes, bytes, str, str]:
        """
        Возвращает (slide1_png, slide2_png, name1, name2).
        name1 = "filename_левая_часть.png"
        name2 = "filename_правая_часть.png"
        """
        s = self.s
        blur      = s.get("blur", 18)
        color     = TEXT_COLORS.get(s.get("text_color", "white"), (255, 255, 255))
        font_st   = s.get("font", "bold")
        size1     = int(s.get("font_size_slide1", 80))
        size2     = int(s.get("font_size_slide2", 48))
        use_grad  = s.get("gradient", True)

        # Имена файлов
        stem = Path_stem(original_filename)
        name1 = f"{stem}_левая_часть.png"
        name2 = f"{stem}_правая_часть.png"

        photo = Image.open(io.BytesIO(photo_bytes)).convert("RGB")

        # 1. Размытый фон 2160×1080
        canvas = make_bg(photo, blur)

        # 2. Градиент поверх фона
        if use_grad:
            grad = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
            gd = ImageDraw.Draw(grad)
            for y in range(CANVAS_H):
                a = int(160 * (y / CANVAS_H) ** 1.3)
                gd.line([(0, y), (CANVAS_W, y)], fill=(0, 0, 0, a))
            canvas = Image.alpha_composite(canvas.convert("RGBA"), grad).convert("RGB")

        # 3. Квадратная обрезка фото, масштаб до 1728×1080 (4 колонки × CANVAS_H)
        sq = crop_square(photo)
        photo_w = PHOTO_END_X  # 1728
        photo_h = CANVAS_H     # 1080
        sq_resized = sq.resize((photo_w, photo_h), Image.LANCZOS)

        # Вставляем фото начиная с x=0 на весь холст (перекрывает обе слайды частично)
        canvas.paste(sq_resized, (PHOTO_START_X, 0))

        # 4. Тёмные полосы поверх фото для текстовых зон
        draw = ImageDraw.Draw(canvas)

        # ── СЛАЙД 1: Артист + Трек ────────────────────────────────────────────
        # Текстовая зона — нижняя часть слайда 1 (не на фото-зоне, а левее)
        # Фото занимает x: 0..1728, слайд 1 это x: 0..1080
        # Значит на слайде 1 фото полностью перекрывает слайд (0..1080 < 1728)
        # Рисуем тёмный блок под текст в нижней части слайда 1

        text1_h = 220
        ov1 = Image.new("RGBA", (SLIDE_W, text1_h), (0, 0, 0, 160))
        canvas_rgba = canvas.convert("RGBA")
        canvas_rgba.paste(ov1, (0, SLIDE_H - text1_h), ov1)
        canvas = canvas_rgba.convert("RGB")
        draw = ImageDraw.Draw(canvas)

        font_artist = get_font(font_st, size1)
        font_track  = get_font(font_st, max(14, size1 - 22))

        # Артист по центру слайда 1
        ab = draw.textbbox((0, 0), artist, font=font_artist)
        a_h = ab[3] - ab[1]
        center_y = SLIDE_H - text1_h + (text1_h // 2) - a_h - 10
        draw_centered_text(draw, artist, font_artist, color, 0, center_y)

        # Трек ниже
        tb = draw.textbbox((0, 0), track, font=font_track)
        t_y = center_y + a_h + 12
        draw_centered_text(draw, track, font_track, color, 0, t_y)

        # ── СЛАЙД 2: Текст трека ──────────────────────────────────────────────
        # На слайде 2 (x: 1080..2160) фото видно от x=1080 до x=1728 → это 648px = 1.5 колонки
        # Текст располагается в правой части слайда 2, где нет фото (x: 1728..2160 = 432px)
        # + немного заходим на фото с тёмным overlay

        # Тёмный overlay на правые 2 колонки слайда 2 (x: 1728..2160 = вся 5-я колонка + часть 4-й)
        text2_x_start = SLIDE_W + COL  # 1080+432 = 1512 (от 2-й колонки слайда 2)
        text2_w = CANVAS_W - text2_x_start  # 2160-1512 = 648

        ov2 = Image.new("RGBA", (text2_w, CANVAS_H), (0, 0, 0, 190))
        canvas_rgba = canvas.convert("RGBA")
        canvas_rgba.paste(ov2, (text2_x_start, 0), ov2)
        canvas = canvas_rgba.convert("RGB")
        draw = ImageDraw.Draw(canvas)

        # Рендерим текст трека
        txt_pad = 40
        render_lyrics(
            draw=draw,
            lyrics=lyrics,
            font_style=font_st,
            font_size=size2,
            max_w=text2_w - txt_pad * 2,
            max_h=CANVAS_H - txt_pad * 2,
            color=color,
            x0=text2_x_start + txt_pad,
            y0=txt_pad,
        )

        # 5. Тонкая линия стыка слайдов
        draw.rectangle([SLIDE_W - 1, 0, SLIDE_W + 1, SLIDE_H], fill=(255, 255, 255, 25))

        # 6. Нарезаем
        slide1 = canvas.crop((0, 0, SLIDE_W, SLIDE_H))
        slide2 = canvas.crop((SLIDE_W, 0, CANVAS_W, SLIDE_H))

        def to_png(im: Image.Image) -> bytes:
            buf = io.BytesIO()
            im.save(buf, format="PNG", compress_level=0)
            return buf.getvalue()

        return to_png(slide1), to_png(slide2), name1, name2


def Path_stem(filename: str) -> str:
    """Возвращает имя файла без расширения."""
    from pathlib import Path
    return Path(filename).stem
