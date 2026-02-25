import os
import io
import zipfile
import asyncio
import json
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, filters, ContextTypes
)
from generator import CarouselGenerator

# ── States ──────────────────────────────────────────────────────────────────
WAIT_PHOTO, WAIT_ARTIST, WAIT_TRACK, WAIT_LYRICS, CONFIRM = range(5)

# ── Settings keys ─────────────────────────────────────────────────────────
DEFAULT_SETTINGS = {
    "font": "bold",          # bold | light | italic
    "text_color": "white",   # white | yellow | cyan | pink | orange
    "blur": 18,              # 0-30
    "gradient": True,        # bool
    "font_size": 52,         # 40-80
}

user_settings: dict[int, dict] = {}
user_state: dict[int, dict] = {}


def get_settings(uid: int) -> dict:
    if uid not in user_settings:
        user_settings[uid] = DEFAULT_SETTINGS.copy()
    return user_settings[uid]


# ── /start ───────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 *TikTok Carousel Bot*\n\n"
        "Отправь мне фото обложки — и я сделаю карусель для TikTok.\n\n"
        "Команды:\n"
        "• /start — начать\n"
        "• /settings — настройки шрифта и цвета\n"
        "• /zip — отправить ZIP с фотками (пакетная обработка)\n"
        "• /help — помощь",
        parse_mode="Markdown"
    )


# ── /settings ────────────────────────────────────────────────────────────────
async def cmd_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    s = get_settings(uid)

    keyboard = [
        [InlineKeyboardButton("🔤 Шрифт", callback_data="SET_font"),
         InlineKeyboardButton("🎨 Цвет текста", callback_data="SET_color")],
        [InlineKeyboardButton("💧 Размытие фона", callback_data="SET_blur"),
         InlineKeyboardButton("📏 Размер шрифта", callback_data="SET_size")],
        [InlineKeyboardButton(
            f"✨ Градиент: {'ON' if s['gradient'] else 'OFF'}",
            callback_data="SET_gradient"
        )],
    ]
    text = (
        f"⚙️ *Текущие настройки:*\n\n"
        f"Шрифт: `{s['font']}`\n"
        f"Цвет текста: `{s['text_color']}`\n"
        f"Размытие: `{s['blur']}`\n"
        f"Размер шрифта: `{s['font_size']}`\n"
        f"Градиент: `{'да' if s['gradient'] else 'нет'}`"
    )
    await update.message.reply_text(
        text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def settings_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    s = get_settings(uid)
    data = query.data

    if data == "SET_font":
        kb = [[
            InlineKeyboardButton("Bold", callback_data="FONT_bold"),
            InlineKeyboardButton("Light", callback_data="FONT_light"),
            InlineKeyboardButton("Italic", callback_data="FONT_italic"),
        ]]
        await query.edit_message_text("Выбери шрифт:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("FONT_"):
        s["font"] = data.split("_")[1]
        await query.edit_message_text(f"✅ Шрифт установлен: `{s['font']}`", parse_mode="Markdown")

    elif data == "SET_color":
        colors = ["white", "yellow", "cyan", "pink", "orange"]
        kb = [[InlineKeyboardButton(c.capitalize(), callback_data=f"COLOR_{c}") for c in colors]]
        await query.edit_message_text("Выбери цвет текста:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("COLOR_"):
        s["text_color"] = data.split("_")[1]
        await query.edit_message_text(f"✅ Цвет текста: `{s['text_color']}`", parse_mode="Markdown")

    elif data == "SET_blur":
        kb = [[
            InlineKeyboardButton("0 (нет)", callback_data="BLUR_0"),
            InlineKeyboardButton("10", callback_data="BLUR_10"),
            InlineKeyboardButton("18", callback_data="BLUR_18"),
            InlineKeyboardButton("28", callback_data="BLUR_28"),
        ]]
        await query.edit_message_text("Выбери степень размытия:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("BLUR_"):
        s["blur"] = int(data.split("_")[1])
        await query.edit_message_text(f"✅ Размытие: `{s['blur']}`", parse_mode="Markdown")

    elif data == "SET_size":
        kb = [[
            InlineKeyboardButton("40 (мелкий)", callback_data="SIZE_40"),
            InlineKeyboardButton("52 (средний)", callback_data="SIZE_52"),
            InlineKeyboardButton("64 (крупный)", callback_data="SIZE_64"),
            InlineKeyboardButton("76 (огромный)", callback_data="SIZE_76"),
        ]]
        await query.edit_message_text("Выбери размер шрифта:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("SIZE_"):
        s["font_size"] = int(data.split("_")[1])
        await query.edit_message_text(f"✅ Размер шрифта: `{s['font_size']}`", parse_mode="Markdown")

    elif data == "SET_gradient":
        s["gradient"] = not s["gradient"]
        kb = [[InlineKeyboardButton(
            f"✨ Градиент: {'ON' if s['gradient'] else 'OFF'}",
            callback_data="SET_gradient"
        )]]
        await query.edit_message_text(
            f"✅ Градиент: `{'включён' if s['gradient'] else 'выключен'}`",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb)
        )


# ── Single photo flow ────────────────────────────────────────────────────────
async def photo_received(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    photo = update.message.photo[-1]  # best quality
    file = await ctx.bot.get_file(photo.file_id)
    buf = io.BytesIO()
    await file.download_to_memory(buf)
    user_state[uid] = {"photo": buf.getvalue(), "mode": "single"}
    await update.message.reply_text("✅ Фото получено!\n\nТеперь напиши *имя артиста*:", parse_mode="Markdown")
    return WAIT_ARTIST


async def got_artist(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_state[uid]["artist"] = update.message.text.strip()
    await update.message.reply_text("🎵 Напиши *название трека*:", parse_mode="Markdown")
    return WAIT_TRACK


async def got_track(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_state[uid]["track"] = update.message.text.strip()
    await update.message.reply_text(
        "📝 Отправь *текст трека* (слова для второго слайда).\n\n"
        "Можно несколько строк — просто пиши как есть:",
        parse_mode="Markdown"
    )
    return WAIT_LYRICS


async def got_lyrics(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_state[uid]["lyrics"] = update.message.text.strip()
    st = user_state[uid]

    await update.message.reply_text(
        f"🎨 Генерирую карусель...\n\n"
        f"👤 {st['artist']}\n"
        f"🎵 {st['track']}\n"
        f"📝 {st['lyrics'][:60]}{'...' if len(st['lyrics']) > 60 else ''}",
    )

    await generate_and_send(update, ctx, uid, st)
    user_state.pop(uid, None)
    return ConversationHandler.END


async def generate_and_send(update, ctx, uid, st):
    settings = get_settings(uid)
    gen = CarouselGenerator(settings)

    slide1, slide2 = gen.make_carousel(
        photo_bytes=st["photo"],
        artist=st["artist"],
        track=st["track"],
        lyrics=st["lyrics"],
    )

    media = []
    from telegram import InputMediaPhoto
    media.append(InputMediaPhoto(media=io.BytesIO(slide1), caption=f"🎵 {st['artist']} — {st['track']}"))
    media.append(InputMediaPhoto(media=io.BytesIO(slide2)))

    await ctx.bot.send_media_group(chat_id=update.effective_chat.id, media=media)
    await update.message.reply_text("✅ Готово! Загружай в TikTok 🔥")


# ── ZIP batch flow ───────────────────────────────────────────────────────────
async def cmd_zip(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📦 Отправь ZIP-архив с фотками.\n\n"
        "Формат названия файлов внутри архива:\n"
        "`АртистНазваниеТрека.jpg`\n\n"
        "Или просто отправь архив — я спрошу данные для каждой фотки.",
        parse_mode="Markdown"
    )


async def document_received(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    doc = update.message.document

    if not doc.file_name.endswith(".zip"):
        await update.message.reply_text("⚠️ Пришли ZIP-архив (.zip)")
        return

    await update.message.reply_text("⏳ Получаю архив...")
    file = await ctx.bot.get_file(doc.file_id)
    buf = io.BytesIO()
    await file.download_to_memory(buf)
    buf.seek(0)

    settings = get_settings(uid)
    gen = CarouselGenerator(settings)

    # Ask for artist + track name + lyrics that apply to ALL photos in batch
    user_state[uid] = {"zip_buf": buf.getvalue(), "mode": "batch"}
    await update.message.reply_text(
        "✅ Архив получен!\n\n"
        "Напиши *имя артиста* (применится ко всем фоткам):",
        parse_mode="Markdown"
    )
    return WAIT_ARTIST


async def got_lyrics_batch(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_state[uid]["lyrics"] = update.message.text.strip()
    st = user_state[uid]

    settings = get_settings(uid)
    gen = CarouselGenerator(settings)

    buf = io.BytesIO(st["zip_buf"])
    buf.seek(0)

    with zipfile.ZipFile(buf) as zf:
        image_names = [n for n in zf.namelist()
                       if n.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
                       and not n.startswith("__MACOSX")]

    if not image_names:
        await update.message.reply_text("❌ В архиве нет изображений (.jpg/.png/.webp)")
        user_state.pop(uid, None)
        return ConversationHandler.END

    await update.message.reply_text(
        f"🎨 Генерирую карусели для {len(image_names)} фото...\n"
        f"Это займёт ~{len(image_names) * 2} секунд."
    )

    results_zip = io.BytesIO()
    with zipfile.ZipFile(results_zip, "w", zipfile.ZIP_DEFLATED) as out_zf:
        buf.seek(0)
        with zipfile.ZipFile(buf) as zf:
            for i, name in enumerate(image_names, 1):
                photo_bytes = zf.read(name)
                base = Path(name).stem
                slide1, slide2 = gen.make_carousel(
                    photo_bytes=photo_bytes,
                    artist=st["artist"],
                    track=st["track"],
                    lyrics=st["lyrics"],
                )
                out_zf.writestr(f"{base}_slide1.jpg", slide1)
                out_zf.writestr(f"{base}_slide2.jpg", slide2)

                if i % 10 == 0:
                    await update.message.reply_text(f"⏳ Обработано {i}/{len(image_names)}...")

    results_zip.seek(0)
    await ctx.bot.send_document(
        chat_id=update.effective_chat.id,
        document=results_zip,
        filename=f"carousels_{st['artist']}.zip",
        caption=f"✅ Готово! {len(image_names)} каруселей для TikTok 🔥"
    )

    user_state.pop(uid, None)
    return ConversationHandler.END


async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_state.pop(uid, None)
    await update.message.reply_text("❌ Отменено. Начни заново — отправь фото.")
    return ConversationHandler.END


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    token = os.environ["BOT_TOKEN"]
    app = Application.builder().token(token).build()

    # Single photo conversation
    single_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.PHOTO, photo_received)],
        states={
            WAIT_ARTIST: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_artist)],
            WAIT_TRACK:  [MessageHandler(filters.TEXT & ~filters.COMMAND, got_track)],
            WAIT_LYRICS: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_lyrics)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Batch ZIP conversation
    batch_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Document.ALL, document_received)],
        states={
            WAIT_ARTIST: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_artist)],
            WAIT_TRACK:  [MessageHandler(filters.TEXT & ~filters.COMMAND, got_track)],
            WAIT_LYRICS: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_lyrics_batch)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CommandHandler("zip", cmd_zip))
    app.add_handler(CallbackQueryHandler(settings_callback))
    app.add_handler(single_conv)
    app.add_handler(batch_conv)

    print("🤖 Bot started!")
    app.run_polling()


if __name__ == "__main__":
    main()
