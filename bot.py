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

# Настройка логирования (чтобы видеть ошибки в консоли Railway)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Состояния ────────────────────────────────────────────────────────────────
WAIT_ARTIST, WAIT_TRACK, WAIT_LYRICS = range(3)

# Глобальные хранилища (очищаются при перезагрузке бота)
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

# ── Обработка фото и архивов ──────────────────────────────────────────────────
async def start_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    # Если это фото
    if update.message.photo:
        file = await update.message.photo[-1].get_file()
        mode = "single"
    # Если это документ (ZIP)
    elif update.message.document:
        doc = update.message.document
        if not doc.file_name.lower().endswith('.zip'):
            await update.message.reply_text("❌ Пришли фото или ZIP-архив.")
            return ConversationHandler.END
        file = await doc.get_file()
        mode = "batch"
    else:
        return ConversationHandler.END

    try:
        data = await file.download_as_bytearray()
        user_state[uid] = {"mode": mode, "data": data, "filename": "image.png"}
        await update.message.reply_text("👤 Введи имя артиста:")
        return WAIT_ARTIST
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка загрузки: {e}")
        return ConversationHandler.END

# ── Сбор данных ─────────────────────────────────────────────────────────────
async def got_artist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in user_state:
        await update.message.reply_text("⏳ Сессия истекла. Пришли фото заново.")
        return ConversationHandler.END
    
    user_state[uid]["artist"] = update.message.text
    await update.message.reply_text("🎵 Введи название трека:")
    return WAIT_TRACK

async def got_track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in user_state:
        await update.message.reply_text("⏳ Сессия истекла. Пришли фото заново.")
        return ConversationHandler.END

    user_state[uid]["track"] = update.message.text
    await update.message.reply_text("📝 Введи текст песни:")
    return WAIT_LYRICS

async def got_lyrics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in user_state:
        await update.message.reply_text("⏳ Сессия истекла. Пришли фото заново.")
        return ConversationHandler.END

    user_state[uid]["lyrics"] = update.message.text
    state = user_state[uid]
    
    gen = CarouselGenerator(get_s(uid))
    await update.message.reply_text("⏳ Начинаю генерацию...")

    try:
        if state["mode"] == "single":
            b1, b2, n1, n2 = gen.make_carousel(state["data"], state["artist"], state["track"], state["lyrics"])
            await update.message.reply_document(io.BytesIO(b1), filename=n1)
            await update.message.reply_document(io.BytesIO(b2), filename=n2)
        else:
            # Batch mode (ZIP)
            out_zip_io = io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(state["data"])) as in_zip:
                with zipfile.ZipFile(out_zip_io, 'w') as out_zip:
                    imgs = [f for f in in_zip.namelist() if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
                    for fname in imgs:
                        p_bytes = in_zip.read(fname)
                        b1, b2, n1, n2 = gen.make_carousel(p_bytes, state["artist"], state["track"], state["lyrics"], fname)
                        out_zip.writestr(n1, b1)
                        out_zip.writestr(n2, b2)
            
            out_zip_io.seek(0)
            await update.message.reply_document(out_zip_io, filename="result_carousel.zip")

        await update.message.reply_text("✅ Готово!")
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text(f"❌ Ошибка: {e}")
    
    # Очистка памяти после работы
    user_state.pop(uid, None)
    return ConversationHandler.END

# ── Остальное ──────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Пришли фото или ZIP-архив, чтобы начать.", reply_markup=get_keyboard())

async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = get_s(update.effective_user.id)
    await update.message.reply_text(f"⚙️ Цвет: {s['text_color']}, Размытие: {s['blur']}", reply_markup=get_keyboard())

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_state.pop(update.effective_user.id, None)
    await update.message.reply_text("❌ Отменено.")
    return ConversationHandler.END

def main():
    token = os.environ.get("BOT_TOKEN")
    app = Application.builder().token(token).build()

    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.PHOTO | filters.Document.ZIP | filters.Document.FileExtension("zip"), start_process)
        ],
        states={
            WAIT_ARTIST: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_artist)],
            WAIT_TRACK:  [MessageHandler(filters.TEXT & ~filters.COMMAND, got_track)],
            WAIT_LYRICS: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_lyrics)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(conv)

    print("🚀 Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
