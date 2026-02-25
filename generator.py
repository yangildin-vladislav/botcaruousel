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

# Центр текста на 1-м слайде (левая часть)
ARTIST_CX = PHOTO_X // 2

def shadow_centered(draw, text, font, color, cx, y):
    """Рисует текст с небольшой тенью для читаемости"""
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    tx = cx - tw // 2
    # Мягкая тень
    draw.text((tx+2, y+2), text, font=font, fill=(0, 0, 0, 80))
    # Основной текст
    draw.text((tx, y), text, font=font, fill=color)

def get_font(size):
    # Пытаемся загрузить font.ttf из корня проекта
    font_path = "font.ttf"
    try:
        if os.path.exists(font_path):
            return ImageFont.truetype(font_path, size)
        return ImageFont.load_default()
    except:
        return ImageFont.load_default()

class CarouselGenerator:
    def __init__(self):
        pass

    def generate(self, photo_bytes, artist, track, lyrics, settings):
        # 1. Загрузка фото
        img = Image.open(io.BytesIO(photo_bytes)).convert("RGBA")
        
        # Обрезка в квадрат
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
        # Делаем фон из исходного фото
        bg = img.copy().resize((CANVAS_W, CANVAS_H), Image.Resampling.LANCZOS)
        bg = bg.filter(ImageFilter.GaussianBlur(settings.get("blur", 20)))
        
        # Затемняем фон чуть-чуть, чтобы текст читался, но фото оставалось ярким
        enhancer = ImageEnhance.Brightness(bg.convert("RGB"))
        bg = enhancer.enhance(0.8).convert("RGBA")
        
        # Основной холст
        canvas = bg
        # Накладываем само фото в центр (на стык)
        canvas.paste(img, (PHOTO_X, PHOTO_Y), img)
        canvas = canvas.convert("RGB")

        # 3. Настройка рисования
        draw = ImageDraw.Draw(canvas)
        color = settings.get("text_color", "white")
        sz1 = settings.get("font_size_slide1", 70)
        sz2 = settings.get("font_size_slide2", 40)

        # 4. Текст на Слайде 1 (Артист и Трек)
        fnt_a = get_font(sz1)
        fnt_t = get_font(max(14, sz1 - 20))
        
        gap = 20
        total_h = sz1 + gap + (sz1-20)
        start_y = (CANVAS_H - total_h) // 2
        
        shadow_centered(draw, artist, fnt_a, color, ARTIST_CX, start_y)
        shadow_centered(draw, track, fnt_t, color, ARTIST_CX, start_y + sz1 + gap)

        # 5. Текст на Слайде 2 (в пустой области справа)
        # Конец фото: 648 (PHOTO_X) + 864 (PHOTO_SZ) = 1512
        # Правый край: 2160
        # Центр пустой зоны: 1512 + (2160 - 1512) // 2 = 1836
        FREE_ZONE_CX = 1836 
        
        fnt_l = get_font(sz2)
        
        # Разбиваем текст на строки
        all_lines = []
        for block in lyrics.split('\n'):
            if not block.strip():
                all_lines.append("")
                continue
            all_lines.extend(textwrap.wrap(block, width=22)) # Ограничение ширины

        line_h = sz2 + 12
        # Ограничиваем количество строк, чтобы не вышли за экран
        max_lines = CANVAS_H // line_h - 2
        display_lines = all_lines[:max_lines]
        
        current_y = (CANVAS_H - (len(display_lines) * line_h)) // 2
        
        for line in display_lines:
            if line.strip():
                shadow_centered(draw, line, fnt_l, color, FREE_ZONE_CX, current_y)
            current_y += line_h

        # 6. Сохранение
        out = io.BytesIO()
        canvas.save(out, format="JPEG", quality=95)
        return out.getvalue()
