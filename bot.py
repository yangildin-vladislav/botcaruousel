import os
import io
import zipfile
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, filters, ContextTypes
)
from generator import CarouselGenerator

# ── Состояния диалога ────────────────────────────────────────────────────────
WAIT_ARTIST, WAIT_TRACK, WAIT_LYRICS = range(3)

# Хранилище настроек и текущих данных
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

# ── Команды ──────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я создаю карусели для TikTok.\n\n"
        "📸 **Как работать:**\n"
        "1. Отправь мне одно фото или ZIP-архив (до 20Мб).\n"
        "2. Напиши Артиста, Трек и Текст.\n"
        "3. Я пришлю готовые слайды или архив.\n\n"
        "Настройки оформления: /settings",
        reply_markup=get_keyboard()
    )

async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = get_s(update.effective_user.id)
    text = (f"⚙️ **Текущие настройки:**\n"
            f"• Цвет: `{s['text_color']}`\n• Размытие: `{s['blur']}`\n"
            f"• Шрифт 1: `{s['font_size_slide1']}`\n• Шрифт 2: `{s['font_size_slide2']}`")
    await update.message.reply_text(text, reply_markup=get_keyboard(), parse_mode="Markdown")

# ── Обработка фото и архивов ──────────────────────────────────────────────────
async def photo_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    photo = await update.message.photo[-1].get_file()
    user_state[uid] = {"mode": "single", "data": await photo.download_as_bytearray()}
    await update.message.reply_text("👤 Введи имя артиста:")
    return WAIT_ARTIST

async def document_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    doc = update.message.document
    if doc.mime_type == 'application/zip' or doc.file_name.endswith('.zip'):
        file = await doc.get_file()
        user_state[uid] = {"mode": "batch", "data": await file.download_as_bytearray()}
        await update.message.reply_text("📦 Обнаружен ZIP-архив.\n👤 Введи имя артиста для всей пачки:")
        return WAIT_ARTIST
    else:
        await update.message.reply_text("❌ Пожалуйста, отправь фото или .zip архив.")

# ── Сбор данных ─────────────────────────────────────────────────────────────
async def got_artist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_state[update.effective_user.id]["artist"] = update.message.text
    await update.message.reply_text("🎵 Введи название трека:")
    return WAIT_TRACK

async def got_track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_state[update.effective_user.id]["track"] = update.message.text
    await update.message.reply_text("📝 Введи текст песни (каждая строка — новый блок):")
    return WAIT_LYRICS

async def got_lyrics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_state[uid]["lyrics"] = update.message.text
    
    state = user_state[uid]
    if state["mode"] == "single":
        await _do_single(update, context, state)
    else:
        await _do_batch(update, context, state)
    
    return ConversationHandler.END

# ── Генерация ───────────────────────────────────────────────────────────────
async def _do_single(update: Update, context: ContextTypes.DEFAULT_TYPE, state: dict):
    uid = update.effective_user.id
    gen = CarouselGenerator(get_s(uid))
    await update.message.reply_text("⏳ Генерирую слайды...")
    
    try:
        b1, b2, n1, n2 = gen.make_carousel(
            state["data"], state["artist"], state["track"], state["lyrics"], "photo.png"
        )
        await update.message.reply_document(document=io.BytesIO(b1), filename=n1)
        await update.message.reply_document(document=io.BytesIO(b2), filename=n2)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def _do_batch(update: Update, context: ContextTypes.DEFAULT_TYPE, state: dict):
    uid = update.effective_user.id
    gen = CarouselGenerator(get_s(uid))
    await update.message.reply_text("⏳ Обрабатываю архив (это может занять время)...")
    
    output_zip_io = io.BytesIO()
    count = 0
    
    try:
        with zipfile.ZipFile(io.BytesIO(state["data"])) as in_zip:
            with zipfile.ZipFile(output_zip_io, 'w') as out_zip:
                for file_name in in_zip.namelist():
                    if file_name.lower().endswith(('.png', '.jpg', '.jpeg')):
                        photo_bytes = in_zip.read(file_name)
                        # Генерация
                        b1, b2, n1, n2 = gen.make_carousel(
                            photo_bytes, state["artist"], state["track"], state["lyrics"], file_name
                        )
                        # Добавление в выходной архив
                        out_zip.writestr(n1, b1)
                        out_zip.writestr(n2, b2)
                        count += 1
        
        output_zip_io.seek(0)
        await update.message.reply_document(
            document=output_zip_io,
            filename="готовая_карусель.zip",
            caption=f"✅ Готово! Обработано изображений: {count}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при обработке архива: {e}")

# ── Настройки (Callback) ────────────────────────────────────────────────────
async def settings_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    s = get_s(uid)
    data = query.data

    if data == "set_color":
        colors = ["white", "yellow", "cyan", "pink", "orange"]
        idx = (colors.index(s["text_color"]) + 1) % len(colors)
        s["text_color"] = colors[idx]
    elif data == "set_blur":
        blurs = [0, 10, 22, 40]
        idx = (blurs.index(s["blur"]) + 1) % len(blurs)
        s["blur"] = blurs[idx]
    elif data in ["size_1", "size_2"]:
        context.user_data["edit_size"] = data
        await query.answer()
        await query.message.reply_text("📏 Введи число для размера шрифта (например, 60):")
        return

    await query.answer()
    await cmd_settings(update, context)

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Хендлер для ручного ввода размера шрифта
    mode = context.user_data.get("edit_size")
    if mode and update.message.text.isdigit():
        val = int(update.message.text)
        s = get_s(update.effective_user.id)
        if mode == "size_1": s["font_size_slide1"] = val
        else: s["font_size_slide2"] = val
        context.user_data.pop("edit_size")
        await update.message.reply_text("✅ Сохранено!")
        await cmd_settings(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Отменено.")
    return ConversationHandler.END

# ── Запуск ───────────────────────────────────────────────────────────────────
def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        print("❌ Ошибка: BOT_TOKEN не найден в переменных окружения!")
        return

    app = Application.builder().token(token).build()

    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.PHOTO, photo_received),
            MessageHandler(filters.Document.ZIP | filters.Document.FileExtension("zip"), document_received),
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
    app.add_handler(CallbackQueryHandler(settings_cb))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(conv)

    print("🤖 Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
