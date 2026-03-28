import io
import os
import textwrap
from pathlib import Path
from PIL import Image, ImageFilter, ImageDraw, ImageFont, ImageEnhance

# ── Константы Карусели ────────────────────────────────────────────────────────
CANVAS_W = 2160
CANVAS_H = 1080
SLIDE_W  = 1080
PHOTO_SZ = 864
PHOTO_X  = SLIDE_W - PHOTO_SZ // 2
PHOTO_Y  = (CANVAS_H - PHOTO_SZ) // 2
ARTIST_CX    = PHOTO_X // 2
FREE_ZONE_CX = 1836

class CarouselGenerator:
    def __init__(self, settings):
        self.settings = settings
        self.base_path = Path(__file__).parent

    def get_font(self, font_type, size):
        # Выбор файла шрифта в зависимости от режима
        name = "Impact.ttf" if font_type == "impact" else "font.ttf"
        path = self.base_path / "fonts" / name
        if not path.exists():
            path = self.base_path / name # Проверка в корне
        try:
            return ImageFont.truetype(str(path), size)
        except:
            return ImageFont.load_default()

    def shadow_centered(self, draw, text, font, color, cx, y):
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        tx = cx - tw // 2
        draw.text((tx+2, y+2), text, font=font, fill=(0, 0, 0, 100))
        draw.text((tx, y), text, font=font, fill=color)

    def draw_impact_text(self, draw, text, font, w, h):
        lines = text.split('\n')
        total_h = sum(draw.textbbox((0,0), l, font=font)[3] for l in lines) + (len(lines)*10)
        y = (h - total_h) // 2
        for line in lines:
            bbox = draw.textbbox((0,0), line, font=font)
            x = (w - (bbox[2]-bbox[0])) // 2
            # Обводка
            for o in [(-2,-2),(2,-2),(-2,2),(2,2),(0,-2),(0,2),(-2,0),(2,0)]:
                draw.text((x+o[0], y+o[1]), line, font=font, fill="black")
            draw.text((x, y), line, font=font, fill="white")
            y += (bbox[3]-bbox[1]) + 10

    def make_carousel(self, image_bytes, artist, track, lyrics, original_name, mode="carousel"):
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        
        if mode == "impact":
            # РЕЖИМ IMPACT (МЕМ)
            width, height = img.size
            font_main = self.get_font("impact", self.settings.get("font_size_slide1", 80))
            font_lyr = self.get_font("impact", self.settings.get("font_size_slide2", 50))
            
            s1 = img.copy(); draw1 = ImageDraw.Draw(s1)
            self.draw_impact_text(draw1, f"{artist}\n{track}".upper(), font_main, width, height)
            
            s2 = img.copy(); draw2 = ImageDraw.Draw(s2)
            self.draw_impact_text(draw2, lyrics.upper(), font_lyr, width, height)
        else:
            # РЕЖИМ КАРУСЕЛЬ (СТАНДАРТ)
            canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), (30, 30, 30))
            blur_bg = img.resize((CANVAS_W, CANVAS_H), Image.Resampling.LANCZOS)
            blur_bg = blur_bg.filter(ImageFilter.GaussianBlur(self.settings.get("blur", 20)))
            canvas.paste(blur_bg, (0, 0))
            
            mask = Image.new("L", (PHOTO_SZ, PHOTO_SZ), 0)
            draw_m = ImageDraw.Draw(mask)
            draw_m.rounded_rectangle((0, 0, PHOTO_SZ, PHOTO_SZ), 50, fill=255)
            photo = img.resize((PHOTO_SZ, PHOTO_SZ), Image.Resampling.LANCZOS).convert("RGBA")
            photo.putalpha(mask)
            canvas.paste(photo, (PHOTO_X, PHOTO_Y), photo)
            
            final_cv = canvas.convert("RGB")
            draw = ImageDraw.Draw(final_cv)
            color = self.settings.get("text_color", "white")
            
            sz1, sz2 = self.settings.get("font_size_slide1", 78), self.settings.get("font_size_slide2", 44)
            fnt_a = self.get_font("normal", sz1)
            fnt_t = self.get_font("normal", max(14, sz1 - 20))
            self.shadow_centered(draw, artist, fnt_a, color, ARTIST_CX, (CANVAS_H - (sz1*2))//2)
            self.shadow_centered(draw, track, fnt_t, color, ARTIST_CX, (CANVAS_H // 2) + 20)
            
            fnt_l = self.get_font("normal", sz2)
            lyr_lines = []
            for line in lyrics.split('\n'): lyr_lines.extend(textwrap.wrap(line, width=22))
            y2 = (CANVAS_H - (len(lyr_lines)*(sz2+15))) // 2
            for line in lyr_lines:
                self.shadow_centered(draw, line, fnt_l, color, FREE_ZONE_CX, y2)
                y2 += sz2 + 15
            
            s1 = final_cv.crop((0, 0, SLIDE_W, CANVAS_H))
            s2 = final_cv.crop((SLIDE_W, 0, CANVAS_W, CANVAS_H))

        out1, out2 = io.BytesIO(), io.BytesIO()
        s1.save(out1, format="JPEG", quality=90); s2.save(out2, format="JPEG", quality=90)
        base = original_name.rsplit('.', 1)[0]
        return out1.getvalue(), out2.getvalue(), f"{base}_1.jpg", f"{base}_2.jpg"
