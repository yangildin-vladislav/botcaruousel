# 4. (ОПЦИОНАЛЬНО) Убираем или уменьшаем затемнение
        # Если хотите совсем убрать темный фон, удалите этот блок:
        # ov = Image.new("RGBA", (SLIDE_W, SLIDE_H), (0, 0, 0, 80)) # Уменьшил прозрачность со 150 до 80
        # cv_rgba2 = canvas.convert("RGBA")
        # cv_rgba2.paste(ov, (SLIDE_W, 0), ov)
        # canvas = cv_rgba2.convert("RGB")

        draw = ImageDraw.Draw(canvas)

        # ... (пропускаем Слайд 1) ...

        # 6. Слайд 2: Текст трека в ПРАВОЙ свободной части
        # Конец фото на холсте: PHOTO_X + PHOTO_SZ = 648 + 864 = 1512
        # Правый край холста: 2160
        # Свободная зона: от 1512 до 2160 (ширина 648px)
        
        photo_end_x = PHOTO_X + PHOTO_SZ 
        free_zone_center = photo_end_x + (CANVAS_W - photo_end_x) // 2 # Это ~1836px
        
        fnt_lyrics = get_font(sz2)
        # Ограничиваем ширину текста, чтобы он не залезал на фото (ширина зоны 600px с отступами)
        lines = textwrap.wrap(lyrics, width=20) 
        
        current_y = (CANVAS_H - (len(lines) * (sz2 + 10))) // 2
        for line in lines:
            # Рисуем текст с центром в free_zone_center
            shadow_centered(draw, line, fnt_lyrics, color, free_zone_center, current_y)
            current_y += sz2 + 10
