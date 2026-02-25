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

# Настройка логирования для отладки
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

# ── Вход в процесс (Фото или ZIP) ─────────────────────────────────────────────
async def start_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    
    # 1. Если прислали фото как картинку
    if update.message.photo:
        file = await update.message.photo[-1].get_file()
        data = await file.download_as_bytearray()
        user_state[uid] = {"mode": "single", "data": data, "orig_name": "photo.png"}
    
    # 2. Если прислали документ (ZIP или фото как файл)
    elif update.message.document:
        doc = update.message.document
        file = await doc.get_file()
        data = await file.download_as_bytearray()
        
        # Проверяем, ZIP это или просто одиночная картинка
        if doc.file_name.lower().endswith('.zip'):
            user_state[uid] = {"mode": "batch", "data": data, "orig_name": doc.file_name}
        elif doc.file_name.lower().endswith(('.png', '.jpg', '.jpeg')):
            user_state[uid] = {"mode": "single", "data": data, "orig_name": doc.file_name}
        else:
            await update.message.reply_text("❌ Ошибка: Я принимаю только .zip архивы или фото (.jpg, .png)")
            return ConversationHandler.END
    else:
        return ConversationHandler.END

    await update.message.reply_text("👤 Введи имя артиста:")
    return WAIT_ARTIST

# ── Сбор текстовых данных ─────────────────────────────────────────────────────
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
        await update.message.reply_text("❌ Сессия истекла. Пришли фото заново.")
        return ConversationHandler.END

    user_state[uid]["track"] = update.message.text
    await update.message.reply_text("📝 Введи текст песни:")
    return WAIT_LYRICS

async def got_lyrics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in user_state:
        await update.message.reply_text("❌ Сессия истекла. Пришли фото заново.")
        return ConversationHandler.END

    user_state[uid]["lyrics"] = update.message.text
    state = user_state[uid]
    
    # Инициализируем генератор с текущими настройками
    gen = CarouselGenerator(get_s(uid))
    await update.message.reply_text("⏳ Обрабатываю... Пожалуйста, подождите.")

    try:
        if state["mode"] == "single":
            # Одиночное фото
            b1, b2, n1, n2 = gen.make_carousel(state["data"], state["artist"], state["track"], state["lyrics"], state["orig_name"])
            await update.message.reply_document(io.BytesIO(b1), filename=n1)
            await update.message.reply_document(io.BytesIO(b2), filename=n2)
        
        else:
            # Массовая обработка ZIP
            output_zip_io = io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(state["data"])) as in_zip:
                with zipfile.ZipFile(output_zip_io, 'w') as out_zip:
                    # Список файлов в архиве (исключаем системные пачки Mac)
                    valid_files = [f for f in in_zip.namelist() if f.lower().endswith(('.png', '.jpg', '.jpeg')) and not f.startswith('__MACOSX')]
                    
                    if not valid_files:
                        await update.message.reply_text("❌ В архиве не найдено картинок (.jpg, .png)")
                        return ConversationHandler.END

                    for fname in valid_files:
                        p_bytes = in_zip.read(fname)
                        # Генерируем два слайда
                        b1, b2, n1, n2 = gen.make_carousel(p_bytes, state["artist"], state["track"], state["lyrics"], fname)
                        # Сохраняем в новый архив
                        out_zip.writestr(n1, b1)
                        out_zip.writestr(n2, b2)
            
            output_zip_io.seek(0)
            await update.message.reply_document(output_zip_io, filename=f"готовая_карусель_{uid}.zip", caption="✅ Все фото обработаны!")

    except zipfile.BadZipFile:
        await update.message.reply_text("❌ Ошибка: Файл поврежден или это не .zip архив. Попробуйте создать ZIP заново.")
    except Exception as e:
        logger.error(f"Глобальная ошибка: {e}")
        await update.message.reply_text(f"❌ Произошла ошибка: {e}")
    
    # Очищаем состояние
    user_state.pop(uid, None)
    return ConversationHandler.END

# ── Дополнительные функции ────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Пришлите фото или ZIP-архив с фото, чтобы начать.", reply_markup=get_keyboard())

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_state.pop(update.effective_user.id, None)
    await update.message.reply_text("❌ Действие отменено.")
    return ConversationHandler.END

def main():
    token = os.environ.get("BOT_TOKEN")
    app = Application.builder().token(token).build()

    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.PHOTO | filters.Document.ALL, start_process)
        ],
        states={
            WAIT_ARTIST: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_artist)],
            WAIT_TRACK:  [MessageHandler(filters.TEXT & ~filters.COMMAND, got_track)],
            WAIT_LYRICS: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_lyrics)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(conv)

    print("🚀 Бот запущен и готов к работе!")
    app.run_polling()

if __name__ == "__main__":
    main()
