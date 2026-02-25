import os
import io
import zipfile
import logging
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, filters, ContextTypes
)
from generator import CarouselGenerator

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Состояния ────────────────────────────────────────────────────────────────
WAIT_ARTIST, WAIT_TRACK, WAIT_LYRICS = range(3)

user_settings: dict[int, dict] = {}
user_state:    dict[int, dict] = {}

DEFAULT_SETTINGS = {
    "text_color":       "white",
    "blur":             22,
    "font_size_slide1": 78,
    "font_size_slide2": 44,
}

def get_s(uid: int) -> dict:
    if uid not in user_settings:
        user_settings[uid] = DEFAULT_SETTINGS.copy()
    return user_settings[uid]

def get_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎨 Цвет текста", callback_data="set_color"),
         InlineKeyboardButton("🌫 Размытие", callback_data="set_blur")],
        [InlineKeyboardButton("📏 Размер (Слайд 1)", callback_data="size_1"),
         InlineKeyboardButton("📏 Размер (Слайд 2)", callback_data="size_2")]
    ])

# ── Обработка входящих файлов ─────────────────────────────────────────────────
async def start_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    
    # Определяем, что пришло
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        mode = "single"
        orig_name = "image.jpg"
    elif update.message.document:
        doc = update.message.document
        file_id = doc.file_id
        orig_name = doc.file_name
        mode = "batch" if orig_name.lower().endswith('.zip') else "single"
    else:
        return ConversationHandler.END

    # Сохраняем только ID файла, чтобы не держать тяжелые байты в памяти раньше времени
    user_state[uid] = {
        "mode": mode,
        "file_id": file_id,
        "orig_name": orig_name
    }

    await update.message.reply_text("👤 Введи имя артиста (или /cancel):")
    return WAIT_ARTIST

async def got_artist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in user_state:
        await update.message.reply_text("❌ Ошибка: отправь файл заново.")
        return ConversationHandler.END
    user_state[uid]["artist"] = update.message.text
    await update.message.reply_text("🎵 Введи название трека:")
    return WAIT_TRACK

async def got_track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in user_state: return ConversationHandler.END
    user_state[uid]["track"] = update.message.text
    await update.message.reply_text("📝 Введи текст песни:")
    return WAIT_LYRICS

async def got_lyrics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in user_state: return ConversationHandler.END
    
    user_state[uid]["lyrics"] = update.message.text
    state = user_state[uid]
    
    await update.message.reply_text("⏳ Начинаю обработку. Это может занять время...")

    try:
        # Скачиваем файл только сейчас
        new_file = await context.bot.get_file(state["file_id"])
        file_bytearray = await new_file.download_as_bytearray()
        
        gen = CarouselGenerator(get_s(uid))

        if state["mode"] == "single":
            # Обработка одного фото
            b1, b2, n1, n2 = gen.make_carousel(
                file_bytearray, state["artist"], state["track"], state["lyrics"], state["orig_name"]
            )
            await update.message.reply_document(io.BytesIO(b1), filename=n1)
            await update.message.reply_document(io.BytesIO(b2), filename=n2)
        
        else:
            # Обработка ZIP (как во втором боте)
            zip_io = io.BytesIO(file_bytearray)
            output_zip_io = io.BytesIO()
            
            with zipfile.ZipFile(zip_io, 'r') as in_zip:
                with zipfile.ZipFile(output_zip_io, 'w') as out_zip:
                    # Фильтруем файлы
                    valid_files = [f for f in in_zip.namelist() if f.lower().endswith(('.png', '.jpg', '.jpeg')) and not f.startswith('__MACOSX')]
                    
                    for fname in valid_files:
                        img_data = in_zip.read(fname)
                        # Вызываем генератор (он вернет кортеж из 4 элементов)
                        b1, b2, n1, n2 = gen.make_carousel(
                            img_data, state["artist"], state["track"], state["lyrics"], fname
                        )
                        # Добавляем обе части в архив с нужными именами
                        out_zip.writestr(n1, b1)
                        out_zip.writestr(n2, b2)

            output_zip_io.seek(0)
            await update.message.reply_document(
                document=output_zip_io, 
                filename=f"carousel_ready_{uid}.zip",
                caption=f"✅ Готово! Обработано файлов: {len(valid_files)}"
            )

    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text(f"❌ Произошла ошибка: {e}")
    
    user_state.pop(uid, None)
    return ConversationHandler.END

# ── Доп. команды ─────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Пришли фото или ZIP-архив с фото.", reply_markup=get_keyboard())

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_state.pop(update.effective_user.id, None)
    await update.message.reply_text("❌ Отменено.")
    return ConversationHandler.END

def main():
    token = os.environ.get("BOT_TOKEN")
    app = Application.builder().token(token).build()

    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.PHOTO | filters.Document.ALL, start_process)],
        states={
            WAIT_ARTIST: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_artist)],
            WAIT_TRACK:  [MessageHandler(filters.TEXT & ~filters.COMMAND, got_track)],
            WAIT_LYRICS: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_lyrics)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(conv)

    print("🚀 Бот запущен (используется логика из стабильного примера)")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
