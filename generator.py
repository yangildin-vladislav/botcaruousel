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
PHOTO_X  = SLIDE_W - PHOTO_SZ // 2    # 648 (начало фото)
PHOTO_Y  = (CANVAS_H - PHOTO_SZ) // 2 # 108
CORNER_R = 50

# Левая зона (артист/трек): 0..PHOTO_X
ARTIST_CX = PHOTO_X // 2

# Правая зона (текст трека): 
# Фото заканчивается на 648 + 864 = 1512. Край холста = 2160.
# Центр пустой области: (1512 + 2160) // 2 = 1836
FREE_ZONE_CX = 1836
LYRICS_PAD = 40 

# ── Шрифты ───────────────────────────────────────────────────────────────────
_HERE = Path(__file__).parent

def get_font(size: int):
    custom = _HERE / "font.ttf"
    try:
        if custom.exists():
            return ImageFont.truetype(str(custom), size)
        return ImageFont.load_default()
    except:
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

# ── Вспомогательные функции ───────────────────────────────────────────────────
def shadow_centered(draw, text, fnt, color, cx, y):
    bb = draw.textbbox((0,0), text, font=fnt)
    w  = bb[2] - bb[0]
    tx = cx - w // 2
    # Тень
    draw.text((tx+2, y+2), text, font=fnt, fill=(0,0,0,120))
    # Текст
    draw.text((tx, y), text, font=fnt, fill=color)

class CarouselGenerator:
    def __init__(self, settings: dict):
        """Исправлено: теперь принимает настройки, как просит bot.py"""
        self.s = settings

    def make_carousel(self, photo_bytes, artist, track, lyrics, original_filename="image.jpg"):
        s     = self.s
        blur  = s.get("blur", 22)
        color = TEXT_COLORS.get(s.get("text_color", "white"), (255,255,255))
        sz1   = int(s.get("font_size_slide1", 78))
        sz2   = int(s.get("font_size_slide2", 44))

        photo = Image.open(io.BytesIO(photo_bytes)).convert("RGB")
        
        # 1. Квадратное фото
        w, h = photo.size
        side = min(w, h)
        sq = photo.crop(((w-side)//2, (h-side)//2, (w+side)//2, (h+side)//2))
        sq = sq.resize((PHOTO_SZ, PHOTO_SZ), Image.LANCZOS)

        # 2. Фон (Размытие и Яркость)
        bg = sq.resize((CANVAS_W, CANVAS_H), Image.LANCZOS)
        if blur > 0:
            bg = bg.filter(ImageFilter.GaussianBlur(radius=blur))
        
        # ИСПРАВЛЕНО: Увеличил яркость с 0.38 до 0.7, чтобы не было слишком темно
        bg = ImageEnhance.Brightness(bg).enhance(0.7)
        canvas = bg.convert("RGBA")

        # 3. Наложение фото со скруглением
        mask = Image.new("L", (PHOTO_SZ, PHOTO_SZ), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0,0,PHOTO_SZ,PHOTO_SZ], radius=CORNER_R, fill=255)
        
        sq_rgba = sq.convert("RGBA")
        sq_rgba.putalpha(mask)
        canvas.paste(sq_rgba, (PHOTO_X, PHOTO_Y), sq_rgba)
        
        # ИСПРАВЛЕНО: Удален черный оверлей Image.new("RGBA", ... 150), который затемнял 2-й слайд
        
        final_cv = canvas.convert("RGB")
        draw = ImageDraw.Draw(final_cv)

        # 4. Слайд 1: Текст (левая часть)
        fnt_a = get_font(sz1)
        fnt_t = get_font(max(14, sz1 - 20))
        
        total_h = sz1 + 24 + (sz1-20)
        y = (CANVAS_H - total_h) // 2
        shadow_centered(draw, artist, fnt_a, color, ARTIST_CX, y)
        shadow_centered(draw, track, fnt_t, color, ARTIST_CX, y + sz1 + 24)

        # 5. Слайд 2: Текст (правая пустая область)
        fnt_l = get_font(sz2)
        # Ограничиваем ширину текста для узкой зоны (ширина зоны ~600px)
        lines = []
        for line in lyrics.split('\n'):
            lines.extend(textwrap.wrap(line, width=22))
        
        line_h = sz2 + 15
        cur_y = (CANVAS_H - (len(lines) * line_h)) // 2
        
        for line in lines:
            # Центрируем внутри FREE_ZONE_CX (1836px)
            shadow_centered(draw, line, fnt_l, color, FREE_ZONE_CX, cur_y)
            cur_y += line_h

        # 6. Нарезка
        stem = Path(original_filename).stem
        s1 = final_cv.crop((0, 0, SLIDE_W, SLIDE_H))
        s2 = final_cv.crop((SLIDE_W, 0, CANVAS_W, SLIDE_H))
        
        def to_bytes(im):
            b = io.BytesIO()
            im.save(b, "PNG")
            return b.getvalue()

        return to_bytes(s1), to_bytes(s2), f"{stem}_1.png", f"{stem}_2.png"
