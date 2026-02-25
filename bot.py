import os
import io
import zipfile
import logging
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)
from generator import CarouselGenerator

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Токен
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# Состояния
WAIT_ARTIST, WAIT_TRACK, WAIT_LYRICS = range(3)

# Устанавливаем лимит чуть меньше 20 МБ для безопасности передачи
MAX_ZIP_SIZE = 19 * 1024 * 1024 

user_state = {}
DEFAULT_SETTINGS = {
    "text_color": "white",
    "blur": 22,
    "font_size_slide1": 78,
    "font_size_slide2": 44,
}

async def start_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        mode, name = "single", "image.jpg"
    elif update.message.document:
        doc = update.message.document
        file_id, name = doc.file_id, doc.file_name
        mode = "batch" if name.lower().endswith('.zip') else "single"
    else:
        return ConversationHandler.END

    user_state[uid] = {"file_id": file_id, "mode": mode, "name": name}
    await update.message.reply_text("👤 Введите имя артиста:")
    return WAIT_ARTIST

async def got_artist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_state[update.effective_user.id]["artist"] = update.message.text
    await update.message.reply_text("🎵 Название трека:")
    return WAIT_TRACK

async def got_track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_state[update.effective_user.id]["track"] = update.message.text
    await update.message.reply_text("📝 Текст песни:")
    return WAIT_LYRICS

async def got_lyrics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = user_state.get(uid)
    if not state: return ConversationHandler.END
    state["lyrics"] = update.message.text

    await update.message.reply_text("⏳ Обрабатываю пачку фото. Архивы придут частями по ~20МБ...")

    try:
        file = await context.bot.get_file(state["file_id"])
        f_bytes = await file.download_as_bytearray()
        gen = CarouselGenerator(DEFAULT_SETTINGS)

        if state["mode"] == "single":
            b1, b2, n1, n2 = gen.make_carousel(f_bytes, state["artist"], state["track"], state["lyrics"], state["name"])
            await update.message.reply_document(io.BytesIO(b1), filename=n1)
            await update.message.reply_document(io.BytesIO(b2), filename=n2)
        else:
            # ЛОГИКА АВТО-ДРОБЛЕНИЯ ZIP
            with zipfile.ZipFile(io.BytesIO(f_bytes)) as in_zip:
                files = [f for f in in_zip.namelist() if f.lower().endswith(('.png', '.jpg', '.jpeg')) and not f.startswith('__')]
                
                output_zip_io = io.BytesIO()
                current_zip = zipfile.ZipFile(output_zip_io, 'w')
                part_num = 1

                for i, f_name in enumerate(files, 1):
                    img_data = in_zip.read(f_name)
                    # Генерация слайдов
                    b1, b2, n1, n2 = gen.make_carousel(img_data, state["artist"], state["track"], state["lyrics"], f_name)
                    
                    # Добавляем в текущий архив
                    current_zip.writestr(n1, b1)
                    current_zip.writestr(n2, b2)

                    # Если размер архива в памяти превысил порог
                    if output_zip_io.tell() > MAX_ZIP_SIZE:
                        current_zip.close()
                        output_zip_io.seek(0)
                        await update.message.reply_document(
                            document=output_zip_io, 
                            filename=f"carousel_part_{part_num}.zip",
                            caption=f"📦 Часть {part_num} готова"
                        )
                        # Сбрасываем для новой части
                        output_zip_io = io.BytesIO()
                        current_zip = zipfile.ZipFile(output_zip_io, 'w')
                        part_num += 1

                # Закрываем последний архив
                current_zip.close()
                if output_zip_io.tell() > 50: # Если в нем что-то есть
                    output_zip_io.seek(0)
                    await update.message.reply_document(
                        document=output_zip_io, 
                        filename=f"carousel_part_{part_num}.zip",
                        caption=f"✅ Финальная часть {part_num}"
                    )

        await update.message.reply_text("✨ Все части отправлены!")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text(f"❌ Произошла ошибка: {e}")
    
    user_state.pop(uid, None)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_state.pop(update.effective_user.id, None)
    await update.message.reply_text("❌ Отменено.")
    return ConversationHandler.END

def main():
    if not BOT_TOKEN: return
    app = Application.builder().token(BOT_TOKEN).build()
    
    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.PHOTO | filters.Document.ALL, start_file)],
        states={
            WAIT_ARTIST: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_artist)],
            WAIT_TRACK:  [MessageHandler(filters.TEXT & ~filters.COMMAND, got_track)],
            WAIT_LYRICS: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_lyrics)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    app.add_handler(conv)
    app.add_handler(CommandHandler("start", start_file))
    
    print("🚀 Бот запущен. Архивы будут дробиться по 19 МБ.")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
