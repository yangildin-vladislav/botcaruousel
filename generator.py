import io
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw, ImageFont, ImageFilter

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
        """Обрезает изображение до квадрата 1:1 по центру"""
        width, height = img.size
        new_size = min(width, height)
        left = (width - new_size) / 2
        top = (height - new_size) / 2
        right = (width + new_size) / 2
        bottom = (height + new_size) / 2
        return img.crop((left, top, right, bottom))

    def draw_impact_text(self, draw, text, font, size_px):
        """Рисует текст в стиле Impact с обводкой"""
        w, h = size_px
        lines = text.split('\n')
        
        # Считаем общую высоту блока текста
        total_text_h = 0
        line_data = []
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_w, line_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            line_data.append((line, line_w, line_h))
            total_text_h += line_h + 15

        current_y = (h - total_text_h) // 2
        for line, lw, lh in line_data:
            x = (w - lw) // 2
            # Жирная черная обводка
            for off in [(-3,-3),(3,-3),(-3,3),(3,3),(0,-3),(0,3),(-3,0),(3,0)]:
                draw.text((x+off[0], current_y+off[1]), line, font=font, fill="black")
            draw.text((x, current_y), line, font=font, fill="white")
            current_y += lh + 15

    def make_carousel(self, image_bytes, artist, track, lyrics, original_name, mode="carousel"):
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        
        # КВАДРАТНАЯ ОБРЕЗКА 1:1
        img = self.center_crop_square(img)
        # Увеличиваем до стандартного хорошего разрешения, например 1080x1080
        img = img.resize((1080, 1080), Image.Resampling.LANCZOS)
        width, height = img.size

        if mode == "impact":
            # --- РЕЖИМ МЕМ (IMPACT) ---
            f_main = self.get_font("impact", self.settings.get("font_size_slide1", 80))
            f_lyr = self.get_font("impact", self.settings.get("font_size_slide2", 50))
            
            # Слайд 1 (Только Артист)
            s1 = img.copy()
            self.draw_impact_text(ImageDraw.Draw(s1), artist.upper(), f_main, (width, height))
            
            # Слайд 2 (Текст)
            s2 = img.copy()
            self.draw_impact_text(ImageDraw.Draw(s2), lyrics.upper(), f_lyr, (width, height))
        else:
            # --- РЕЖИМ КАРУСЕЛЬ ---
            # (Тут можно оставить логику из предыдущего шага, 
            # но так как вы просили 1:1, просто наложим текст поверх квадрата)
            f_main = self.get_font("normal", self.settings.get("font_size_slide1", 70))
            f_lyr = self.get_font("normal", self.settings.get("font_size_slide2", 40))
            
            s1 = img.copy()
            draw1 = ImageDraw.Draw(s1)
            # Тень и текст для карусели
            txt1 = f"{artist}\n{track}"
            self.draw_impact_text(draw1, txt1, f_main, (width, height)) # Используем ту же функцию обводки для читаемости
            
            s2 = img.copy()
            self.draw_impact_text(ImageDraw.Draw(s2), lyrics, f_lyr, (width, height))

        out1, out2 = io.BytesIO(), io.BytesIO()
        s1.save(out1, format="JPEG", quality=90)
        s2.save(out2, format="JPEG", quality=90)
        base = original_name.rsplit('.', 1)[0]
        return out1.getvalue(), out2.getvalue(), f"{base}_1.jpg", f"{base}_2.jpg"
