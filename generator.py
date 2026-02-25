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

# Центр текста на 1-м слайде
ARTIST_CX = PHOTO_X // 2

def shadow_centered(draw, text, font, color, cx, y):
    """Рисует текст с небольшой тенью для читаемости"""
    tw, th = draw.textbbox((0, 0), text, font=font)[2:]
    tx = cx - tw // 2
    # Тень
    draw.text((tx+2, y+2), text, font=font, fill=(0, 0, 0, 100))
    # Основной текст
    draw.text((tx, y), text, font=font, fill=color)

def get_font(size):
    try:
        return ImageFont.truetype("font.ttf", size)
    except:
        return ImageFont.load_default()

class CarouselGenerator:
    def generate(self, photo_bytes, artist, track, lyrics, settings):
        # 1. Загрузка и подготовка фото
        img = Image.open(io.BytesIO(photo_bytes)).convert("RGB")
        w, h = img.size
        side = min(w, h)
        img = img.crop(((w-side)//2, (h-side)//2, (w+side)//2, (h+side)//2))
        img = img.resize((PHOTO_SZ, PHOTO_SZ), Image.Resampling.LANCZOS)

        # Скругление углов
        mask = Image.new("L", (PHOTO_SZ, PHOTO_SZ), 0)
        draw_m = ImageDraw.Draw(mask)
        draw_m.rounded_rectangle((0, 0, PHOTO_SZ, PHOTO_SZ), CORNER_R, fill=255)
        img.putalpha(mask)

        # 2. Создание фона (размытие)
        bg = img.resize((CANVAS_W, CANVAS_H), Image.Resampling.LANCZOS)
        bg = bg.filter(ImageFilter.GaussianBlur(settings.get("blur", 20)))
        enhancer = ImageEnhance.Brightness(bg)
        bg = enhancer.enhance(0.7) # Немного приглушаем фон
        
        canvas = bg.convert("RGB")
        canvas.paste(img, (PHOTO_X, PHOTO_Y), img)

        # 3. Настройка текста
        draw = ImageDraw.Draw(canvas)
        color = settings.get("text_color", "white")
        sz1 = settings.get("font_size_slide1", 70)
        sz2 = settings.get("font_size_slide2", 40)

        # 4. Слайд 1: Артист и Трек
        fnt_a = get_font(sz1)
        fnt_t = get_font(max(14, sz1 - 20))
        
        # Центрируем блок текста по вертикали
        gap = 20
        total_h = sz1 + gap + (sz1-20)
        start_y = (CANVAS_H - total_h) // 2
        
        shadow_centered(draw, artist, fnt_a, color, ARTIST_CX, start_y)
        shadow_centered(draw, track, fnt_t, color, ARTIST_CX, start_y + sz1 + gap)

        # 5. Слайд 2: Текст в пустой области справа
        # Конец фото: 648 + 864 = 1512. Конец холста: 2160.
        # Свободное место: 2160 - 1512 = 648px.
        # Центр этой области: 1512 + (648 // 2) = 1836.
        FREE_ZONE_CX = 1836 
        
        fnt_l = get_font(sz2)
        # Ограничиваем ширину, чтобы текст не наезжал на фото
        lines = []
        for line in lyrics.split('\n'):
            lines.extend(textwrap.wrap(line, width=25))
            
        line_h = sz2 + 10
        current_y = (CANVAS_H - (len(lines) * line_h)) // 2
        
        for line in lines:
            shadow_centered(draw, line, fnt_l, color, FREE_ZONE_CX, current_y)
            current_y += line_h

        # Сохранение
        out = io.BytesIO()
        canvas.save(out, format="JPEG", quality=95)
        return out.getvalue()
