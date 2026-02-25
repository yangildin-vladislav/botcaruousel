import io
import os
import textwrap
from pathlib import Path
from PIL import Image, ImageFilter, ImageDraw, ImageFont, ImageEnhance

# ── Константы ─────────────────────────────────────────────────────────────────
CANVAS_W = 2160
CANVAS_H = 1080
SLIDE_W  = 1080
SLIDE_H  = 1080

PHOTO_SZ = 864
PHOTO_X  = SLIDE_W - PHOTO_SZ // 2    # 648
PHOTO_Y  = (CANVAS_H - PHOTO_SZ) // 2 # 108
CORNER_R = 50

# Координаты текста
ARTIST_CX    = PHOTO_X // 2           # Центр левой пустой области
FREE_ZONE_CX = 1836                   # Центр правой пустой области (1512 + 324)

def shadow_centered(draw, text, font, color, cx, y):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    tx = cx - tw // 2
    draw.text((tx+2, y+2), text, font=font, fill=(0, 0, 0, 100))
    draw.text((tx, y), text, font=font, fill=color)

def get_font(size):
    font_path = Path(__file__).parent / "font.ttf"
    try:
        if font_path.exists():
            return ImageFont.truetype(str(font_path), size)
        return ImageFont.load_default()
    except:
        return ImageFont.load_default()

class CarouselGenerator:
    def __init__(self, settings: dict):
        """Теперь принимает настройки корректно"""
        self.s = settings

    def make_carousel(self, photo_bytes, artist, track, lyrics, original_filename="image.png"):
        s = self.s
        blur_val = s.get("blur", 22)
        color = s.get("text_color", "white")
        sz1 = int(s.get("font_size_slide1", 78))
        sz2 = int(s.get("font_size_slide2", 44))

        # 1. Обработка фото
        img = Image.open(io.BytesIO(photo_bytes)).convert("RGB")
        w, h = img.size
        side = min(w, h)
        img = img.crop(((w-side)//2, (h-side)//2, (w+side)//2, (h+side)//2))
        img = img.resize((PHOTO_SZ, PHOTO_SZ), Image.Resampling.LANCZOS)

        # 2. Фон
        bg = img.resize((CANVAS_W, CANVAS_H), Image.Resampling.LANCZOS)
        if blur_val > 0:
            bg = bg.filter(ImageFilter.GaussianBlur(blur_val))
        
        # Яркость (0.7 - сочно, но текст видно)
        bg = ImageEnhance.Brightness(bg).enhance(0.7)
        canvas = bg.convert("RGBA")

        # 3. Наложение фото со скруглением
        mask = Image.new("L", (PHOTO_SZ, PHOTO_SZ), 0)
        draw_m = ImageDraw.Draw(mask)
        draw_m.rounded_rectangle((0, 0, PHOTO_SZ, PHOTO_SZ), CORNER_R, fill=255)
        
        photo_rgba = img.convert("RGBA")
        photo_rgba.putalpha(mask)
        canvas.paste(photo_rgba, (PHOTO_X, PHOTO_Y), photo_rgba)
        
        # Переводим в RGB для рисования текста
        final_cv = canvas.convert("RGB")
        draw = ImageDraw.Draw(final_cv)

        # 4. Слайд 1: Артист и Трек
        fnt_a = get_font(sz1)
        fnt_t = get_font(max(14, sz1 - 20))
        h_block = sz1 + 20 + (sz1-20)
        y1 = (CANVAS_H - h_block) // 2
        shadow_centered(draw, artist, fnt_a, color, ARTIST_CX, y1)
        shadow_centered(draw, track, fnt_t, color, ARTIST_CX, y1 + sz1 + 20)

        # 5. Слайд 2: Текст в пустой области справа
        fnt_l = get_font(sz2)
        lines = []
        for line in lyrics.split('\n'):
            lines.extend(textwrap.wrap(line, width=22))
        
        line_h = sz2 + 15
        y2 = (CANVAS_H - (len(lines) * line_h)) // 2
        for line in lines:
            shadow_centered(draw, line, fnt_l, color, FREE_ZONE_CX, y2)
            y2 += line_h

        # 6. Нарезка и именование
        stem = Path(original_filename).stem
        name1 = f"{stem}_левая_часть.png"
        name2 = f"{stem}_правая_часть.png"

        def to_b(im):
            out = io.BytesIO()
            im.save(out, format="PNG")
            return out.getvalue()

        s1 = final_cv.crop((0, 0, SLIDE_W, SLIDE_H))
        s2 = final_cv.crop((SLIDE_W, 0, CANVAS_W, SLIDE_H))

        return to_b(s1), to_b(s2), name1, name2
