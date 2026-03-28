import io
import textwrap
from pathlib import Path
from PIL import Image, ImageFilter, ImageDraw, ImageFont

# Константы для оригинальной карусели
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
        name = "Impact.ttf" if font_type == "impact" else "font.ttf"
        path = self.base_path / "fonts" / name
        if not path.exists(): path = self.base_path / name
        try:
            return ImageFont.truetype(str(path), size)
        except:
            return ImageFont.load_default()

    def center_crop_square(self, img):
        """Обрезает любое фото до квадрата 1:1"""
        width, height = img.size
        new_size = min(width, height)
        left = (width - new_size) / 2
        top = (height - new_size) / 2
        right = (width + new_size) / 2
        bottom = (height + new_size) / 2
        return img.crop((left, top, right, bottom))

    def shadow_centered(self, draw, text, font, color, cx, y):
        """Рисование текста с тенью по центру (для Карусели)"""
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        tx = cx - tw // 2
        draw.text((tx+2, y+2), text, font=font, fill=(0, 0, 0, 120))
        draw.text((tx, y), text, font=font, fill=color)

    def draw_impact_text(self, draw, text, font, size_px):
        """Рисование текста с обводкой (для Impact)"""
        w, h = size_px
        lines = text.split('\n')
        total_h = sum(draw.textbbox((0,0), l, font=font)[3] for l in lines) + (len(lines)*15)
        curr_y = (h - total_h) // 2
        for line in lines:
            bbox = draw.textbbox((0,0), line, font=font)
            line_w = bbox[2] - bbox[0]
            line_h = bbox[3] - bbox[1]
            x = (w - line_w) // 2
            for o in [(-3,-3),(3,-3),(-3,3),(3,3),(0,-3),(0,3),(-3,0),(2,0)]:
                draw.text((x+o[0], curr_y+o[1]), line, font=font, fill="black")
            draw.text((x, curr_y), line, font=font, fill="white")
            curr_y += line_h + 15

    def make_carousel(self, image_bytes, artist, track, lyrics, original_name, mode="carousel"):
        raw_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        # Всегда сначала делаем квадрат
        square_img = self.center_crop_square(raw_img)

        if mode == "impact":
            # --- РЕЖИМ IMPACT (МЕМ) ---
            img = square_img.resize((1080, 1080), Image.Resampling.LANCZOS)
            f_main = self.get_font("impact", self.settings.get("font_size_slide1", 85))
            f_lyr = self.get_font("impact", self.settings.get("font_size_slide2", 50))
            
            s1 = img.copy(); self.draw_impact_text(ImageDraw.Draw(s1), artist.upper(), f_main, (1080,1080))
            s2 = img.copy(); self.draw_impact_text(ImageDraw.Draw(s2), lyrics.upper(), f_lyr, (1080,1080))
        else:
            # --- ВАШ ОСНОВНОЙ РЕЖИМ КАРУСЕЛИ ---
            canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), (30, 30, 30))
            # Размытый фон
            blur_bg = square_img.resize((CANVAS_W, CANVAS_H), Image.Resampling.LANCZOS)
            blur_bg = blur_bg.filter(ImageFilter.GaussianBlur(self.settings.get("blur", 22)))
            canvas.paste(blur_bg, (0, 0))

            # Скругленное фото по центру
            mask = Image.new("L", (PHOTO_SZ, PHOTO_SZ), 0)
            draw_m = ImageDraw.Draw(mask)
            draw_m.rounded_rectangle((0, 0, PHOTO_SZ, PHOTO_SZ), 50, fill=255)
            photo = square_img.resize((PHOTO_SZ, PHOTO_SZ), Image.Resampling.LANCZOS).convert("RGBA")
            photo.putalpha(mask)
            canvas.paste(photo, (PHOTO_X, PHOTO_Y), photo)

            final_cv = canvas.convert("RGB")
            draw = ImageDraw.Draw(final_cv)
            color = self.settings.get("text_color", "white")
            
            # Текст Слайд 1 (Артист и Трек слева)
            sz1 = self.settings.get("font_size_slide1", 78)
            fnt_a = self.get_font("normal", sz1)
            fnt_t = self.get_font("normal", max(14, sz1 - 20))
            y1 = (CANVAS_H - (sz1 * 2 + 20)) // 2
            self.shadow_centered(draw, artist, fnt_a, color, ARTIST_CX, y1)
            self.shadow_centered(draw, track, fnt_t, color, ARTIST_CX, y1 + sz1 + 20)

            # Текст Слайд 2 (Лирика справа)
            sz2 = self.settings.get("font_size_slide2", 44)
            fnt_l = self.get_font("normal", sz2)
            lines = []
            for line in lyrics.split('\n'): lines.extend(textwrap.wrap(line, width=22))
            y2 = (CANVAS_H - (len(lines)*(sz2+15))) // 2
            for line in lines:
                self.shadow_centered(draw, line, fnt_l, color, FREE_ZONE_CX, y2)
                y2 += sz2 + 15

            s1 = final_cv.crop((0, 0, SLIDE_W, CANVAS_H))
            s2 = final_cv.crop((SLIDE_W, 0, CANVAS_W, CANVAS_H))

        out1, out2 = io.BytesIO(), io.BytesIO()
        s1.save(out1, format="JPEG", quality=90)
        s2.save(out2, format="JPEG", quality=90)
        return out1.getvalue(), out2.getvalue(), f"{original_name}_1.jpg", f"{original_name}_2.jpg"
