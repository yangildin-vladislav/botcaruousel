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
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
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

# ── Загрузка файла ────────────────────────────────────────────────────────────
async def start_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_state.pop(uid, None) # Сброс старого состояния

    try:
        if update.message.photo:
            tg_file = await update.message.photo[-1].get_file()
            orig_name = "photo.png"
            mode = "single"
        elif update.message.document:
            doc = update.message.document
            tg_file = await doc.get_file()
            orig_name = doc.file_name
            mode = "batch" if orig_name.lower().endswith('.zip') else "single"
        else:
            return ConversationHandler.END

        # Используем метод скачивания в память для обхода проблем с размером
        file_out = io.BytesIO()
        await tg_file.download_to_memory(file_out)
        data = file_out.getvalue()

        user_state[uid] = {
            "mode": mode,
            "data": data,
            "orig_name": orig_name
        }

        await update.message.reply_text("👤 Введи имя артиста:")
        return WAIT_ARTIST

    except Exception as e:
        logger.error(f"Ошибка загрузки: {e}")
        await update.message.reply_text("❌ Ошибка при получении файла. Попробуй еще раз.")
        return ConversationHandler.END

# ── Сбор данных ─────────────────────────────────────────────────────────────
async def got_artist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in user_state:
        await update.message.reply_text("❌ Сессия истекла. Пришли фото заново.")
        return ConversationHandler.END
    user_state[uid]["artist"] = update.message.text
    await update.message.reply_text("🎵 Введи название трека:")
    return WAIT_TRACK

async def got_track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in user_state:
        return ConversationHandler.END
    user_state[uid]["track"] = update.message.text
    await update.message.reply_text("📝 Введи текст песни:")
    return WAIT_LYRICS

async def got_lyrics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in user_state:
        return ConversationHandler.END
    
    user_state[uid]["lyrics"] = update.message.text
    state = user_state[uid]
    gen = CarouselGenerator(get_s(uid))
    
    await update.message.reply_text("⏳ Генерирую...")

    try:
        if state["mode"] == "single":
            b1, b2, n1, n2 = gen.make_carousel(state["data"], state["artist"], state["track"], state["lyrics"], state["orig_name"])
            await update.message.reply_document(io.BytesIO(b1), filename=n1)
            await update.message.reply_document(io.BytesIO(b2), filename=n2)
        else:
            out_zip_io = io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(state["data"])) as in_zip:
                with zipfile.ZipFile(out_zip_io, 'w') as out_zip:
                    valid_files = [f for f in in_zip.namelist() if f.lower().endswith(('.png', '.jpg', '.jpeg')) and not f.startswith('__MACOSX')]
                    for fname in valid_files:
                        p_bytes = in_zip.read(fname)
                        b1, b2, n1, n2 = gen.make_carousel(p_bytes, state["artist"], state["track"], state["lyrics"], fname)
                        out_zip.writestr(n1, b1)
                        out_zip.writestr(n2, b2)
            out_zip_io.seek(0)
            await update.message.reply_document(out_zip_io, filename=f"карусель_{uid}.zip")

        await update.message.reply_text("✅ Готово!")
    except Exception as e:
        logger.error(f"Ошибка генерации: {e}")
        await update.message.reply_text(f"❌ Ошибка: {e}")
    
    user_state.pop(uid, None)
    return ConversationHandler.END

# ── Настройки и запуск ────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Пришли фото или ZIP-архив.", reply_markup=get_keyboard())

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_state.pop(update.effective_user.id, None)
    await update.message.reply_text("❌ Отменено.")
    return ConversationHandler.END

def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        print("❌ BOT_TOKEN NOT FOUND")
        return

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

    print("🚀 Бот запущен через Polling...")
    # Использование drop_pending_updates помогает избежать зависших сообщений после перезапуска
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
