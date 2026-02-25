"""
TikTok Carousel Bot v2
"""

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

# ── Conversation states ───────────────────────────────────────────────────────
(
    WAIT_PHOTO, WAIT_ARTIST, WAIT_TRACK, WAIT_LYRICS,
    WAIT_FONT_SIZE1, WAIT_FONT_SIZE2,
    BATCH_WAIT_ARTIST, BATCH_WAIT_TRACK, BATCH_WAIT_LYRICS,
) = range(9)

# ── Default settings ──────────────────────────────────────────────────────────
DEFAULT_SETTINGS = {
    "font": "bold",
    "text_color": "white",
    "blur": 18,
    "gradient": True,
    "font_size_slide1": 80,
    "font_size_slide2": 52,
}

user_settings: dict[int, dict] = {}
user_state: dict[int, dict] = {}


def get_settings(uid: int) -> dict:
    if uid not in user_settings:
        user_settings[uid] = DEFAULT_SETTINGS.copy()
    return user_settings[uid]


def settings_text(s: dict) -> str:
    return (
        f"⚙️ *Текущие настройки:*\n\n"
        f"Шрифт: `{s['font']}`\n"
        f"Цвет текста: `{s['text_color']}`\n"
        f"Размытие фона: `{s['blur']}`\n"
        f"Размер шрифта — слайд 1 (имя/трек): `{s['font_size_slide1']}`\n"
        f"Размер шрифта — слайд 2 (текст трека): `{s['font_size_slide2']}`\n"
        f"Градиент: `{'да' if s['gradient'] else 'нет'}`"
    )


def settings_keyboard(s: dict) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔤 Шрифт", callback_data="SET_font"),
            InlineKeyboardButton("🎨 Цвет", callback_data="SET_color"),
        ],
        [
            InlineKeyboardButton("📏 Размер шрифта слайд 1", callback_data="SET_size1"),
        ],
        [
            InlineKeyboardButton("📏 Размер шрифта слайд 2", callback_data="SET_size2"),
        ],
        [
            InlineKeyboardButton("💧 Размытие", callback_data="SET_blur"),
            InlineKeyboardButton(
                f"✨ Градиент: {'ON' if s['gradient'] else 'OFF'}",
                callback_data="SET_gradient"
            ),
        ],
        [InlineKeyboardButton("✅ Готово", callback_data="SET_done")],
    ])


# ── /start ────────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 *TikTok Carousel Bot*\n\n"
        "Отправь фото → бот сделает 2 слайда карусели для TikTok.\n\n"
        "Слайд 1: имя артиста + название трека\n"
        "Слайд 2: оригинальное фото + текст трека\n\n"
        "*Команды:*\n"
        "/start — начать\n"
        "/settings — настройки оформления\n"
        "/cancel — отменить",
        parse_mode="Markdown"
    )


# ── /settings ─────────────────────────────────────────────────────────────────
async def cmd_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    s = get_settings(uid)
    await update.message.reply_text(
        settings_text(s),
        parse_mode="Markdown",
        reply_markup=settings_keyboard(s)
    )


async def settings_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    s = get_settings(uid)
    data = query.data

    if data == "SET_font":
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("Bold", callback_data="FONT_bold"),
            InlineKeyboardButton("Medium", callback_data="FONT_medium"),
            InlineKeyboardButton("Light", callback_data="FONT_light"),
            InlineKeyboardButton("Italic", callback_data="FONT_italic"),
        ]])
        await query.edit_message_text("Выбери шрифт:", reply_markup=kb)

    elif data.startswith("FONT_"):
        s["font"] = data.split("_", 1)[1]
        await query.edit_message_text(settings_text(s), parse_mode="Markdown",
                                       reply_markup=settings_keyboard(s))

    elif data == "SET_color":
        colors = ["white", "yellow", "cyan", "pink", "orange", "red", "green"]
        rows = [[InlineKeyboardButton(c.capitalize(), callback_data=f"COLOR_{c}") for c in colors[:4]],
                [InlineKeyboardButton(c.capitalize(), callback_data=f"COLOR_{c}") for c in colors[4:]]]
        await query.edit_message_text("Выбери цвет текста:", reply_markup=InlineKeyboardMarkup(rows))

    elif data.startswith("COLOR_"):
        s["text_color"] = data.split("_", 1)[1]
        await query.edit_message_text(settings_text(s), parse_mode="Markdown",
                                       reply_markup=settings_keyboard(s))

    elif data == "SET_blur":
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("0 (нет)", callback_data="BLUR_0"),
            InlineKeyboardButton("10", callback_data="BLUR_10"),
            InlineKeyboardButton("18", callback_data="BLUR_18"),
            InlineKeyboardButton("28", callback_data="BLUR_28"),
        ]])
        await query.edit_message_text("Степень размытия фона:", reply_markup=kb)

    elif data.startswith("BLUR_"):
        s["blur"] = int(data.split("_")[1])
        await query.edit_message_text(settings_text(s), parse_mode="Markdown",
                                       reply_markup=settings_keyboard(s))

    elif data == "SET_size1":
        ctx.user_data["awaiting_size"] = "font_size_slide1"
        await query.edit_message_text(
            "Введи размер шрифта для *слайда 1* (имя артиста + трек).\n"
            "Рекомендую: 60–100. Например: `80`",
            parse_mode="Markdown"
        )

    elif data == "SET_size2":
        ctx.user_data["awaiting_size"] = "font_size_slide2"
        await query.edit_message_text(
            "Введи размер шрифта для *слайда 2* (текст трека).\n"
            "Рекомендую: 36–64. Например: `48`",
            parse_mode="Markdown"
        )

    elif data == "SET_gradient":
        s["gradient"] = not s["gradient"]
        await query.edit_message_text(settings_text(s), parse_mode="Markdown",
                                       reply_markup=settings_keyboard(s))

    elif data == "SET_done":
        await query.edit_message_text(
            "✅ Настройки сохранены!\n\nТеперь отправь фото для генерации карусели."
        )


async def handle_size_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Обработка ручного ввода размера шрифта."""
    uid = update.effective_user.id
    key = ctx.user_data.get("awaiting_size")
    if not key:
        return  # не ждём ввод — пропускаем

    text = update.message.text.strip()
    try:
        size = int(text)
        if not (10 <= size <= 200):
            raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ Введи число от 10 до 200")
        return

    s = get_settings(uid)
    s[key] = size
    ctx.user_data.pop("awaiting_size", None)

    label = "слайд 1" if key == "font_size_slide1" else "слайд 2"
    await update.message.reply_text(
        f"✅ Размер шрифта для *{label}* установлен: `{size}`\n\n"
        f"Используй /settings чтобы изменить другие параметры\n"
        f"или просто отправь фото для генерации.",
        parse_mode="Markdown"
    )


# ── Single photo flow ─────────────────────────────────────────────────────────
async def photo_received(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    # Не реагируем если ждём ввод размера
    if ctx.user_data.get("awaiting_size"):
        await update.message.reply_text("Сначала введи число для размера шрифта 👆")
        return ConversationHandler.END

    uid = update.effective_user.id
    photo = update.message.photo[-1]
    file = await ctx.bot.get_file(photo.file_id)
    buf = io.BytesIO()
    await file.download_to_memory(buf)
    # Telegram не сохраняет оригинальное имя для фото — используем file_id
    user_state[uid] = {"photo": buf.getvalue(), "original_filename": photo.file_unique_id}
    await update.message.reply_text("✅ Фото получено!\n\nНапиши *имя артиста*:", parse_mode="Markdown")
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
        "📝 Напиши *текст трека* (слова для второго слайда).\n"
        "Можно несколько строк:",
        parse_mode="Markdown"
    )
    return WAIT_LYRICS


async def got_lyrics(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_state[uid]["lyrics"] = update.message.text.strip()
    st = user_state[uid]

    msg = await update.message.reply_text("⏳ Генерирую...")
    await _generate_and_send(update, ctx, uid, st)
    await msg.delete()
    user_state.pop(uid, None)
    return ConversationHandler.END


async def _generate_and_send(update, ctx, uid, st):
    settings = get_settings(uid)
    gen = CarouselGenerator(settings)

    original_fn = st.get("original_filename", f"{st['artist']}_{st['track']}")
    slide1, slide2, name1, name2 = gen.make_carousel(
        photo_bytes=st["photo"],
        artist=st["artist"],
        track=st["track"],
        lyrics=st["lyrics"],
        original_filename=original_fn,
    )

    from telegram import InputMediaDocument
    await ctx.bot.send_media_group(
        chat_id=update.effective_chat.id,
        media=[
            InputMediaDocument(
                media=io.BytesIO(slide1),
                filename=name1,
                caption=f"🎵 {st['artist']} — {st['track']}"
            ),
            InputMediaDocument(
                media=io.BytesIO(slide2),
                filename=name2,
            ),
        ]
    )
    await update.message.reply_text("✅ Готово! Загружай в TikTok 🔥")


# ── ZIP batch flow ─────────────────────────────────────────────────────────────
async def document_received(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    doc = update.message.document

    if not doc.file_name.lower().endswith(".zip"):
        # Может быть одиночный PNG/JPG — обрабатываем как фото
        if doc.file_name.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            file = await ctx.bot.get_file(doc.file_id)
            buf = io.BytesIO()
            await file.download_to_memory(buf)
            user_state[uid] = {"photo": buf.getvalue(), "original_filename": doc.file_name}
            await update.message.reply_text("✅ Фото получено!\n\nНапиши *имя артиста*:", parse_mode="Markdown")
            return WAIT_ARTIST
        await update.message.reply_text("⚠️ Пришли ZIP-архив (.zip) или фото (.jpg/.png)")
        return ConversationHandler.END

    await update.message.reply_text("⏳ Получаю архив...")
    file = await ctx.bot.get_file(doc.file_id)
    buf = io.BytesIO()
    await file.download_to_memory(buf)
    user_state[uid] = {"zip_buf": buf.getvalue(), "mode": "batch"}

    await update.message.reply_text(
        "✅ Архив получен!\n\nНапиши *имя артиста* (применится ко всем фоткам):",
        parse_mode="Markdown"
    )
    return BATCH_WAIT_ARTIST


async def batch_got_artist(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_state[uid]["artist"] = update.message.text.strip()
    await update.message.reply_text("🎵 Название трека:", parse_mode="Markdown")
    return BATCH_WAIT_TRACK


async def batch_got_track(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_state[uid]["track"] = update.message.text.strip()
    await update.message.reply_text("📝 Текст трека:", parse_mode="Markdown")
    return BATCH_WAIT_LYRICS


async def batch_got_lyrics(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_state[uid]["lyrics"] = update.message.text.strip()
    st = user_state[uid]

    settings = get_settings(uid)
    gen = CarouselGenerator(settings)

    buf = io.BytesIO(st["zip_buf"])
    buf.seek(0)
    with zipfile.ZipFile(buf) as zf:
        image_names = [
            n for n in zf.namelist()
            if n.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
            and not n.startswith("__MACOSX")
            and not Path(n).name.startswith(".")
        ]

    if not image_names:
        await update.message.reply_text("❌ В архиве нет изображений (.jpg/.png/.webp)")
        user_state.pop(uid, None)
        return ConversationHandler.END

    await update.message.reply_text(
        f"🎨 Генерирую {len(image_names)} каруселей...\n"
        f"~{len(image_names) * 3} секунд"
    )

    results_zip = io.BytesIO()
    with zipfile.ZipFile(results_zip, "w", zipfile.ZIP_STORED) as out_zf:  # ZIP_STORED = без сжатия
        buf.seek(0)
        with zipfile.ZipFile(buf) as zf:
            for i, name in enumerate(image_names, 1):
                photo_bytes = zf.read(name)
                slide1, slide2, n1, n2 = gen.make_carousel(
                    photo_bytes=photo_bytes,
                    artist=st["artist"],
                    track=st["track"],
                    lyrics=st["lyrics"],
                    original_filename=name,
                )
                out_zf.writestr(n1, slide1)
                out_zf.writestr(n2, slide2)

                if i % 5 == 0:
                    await update.message.reply_text(f"⏳ {i}/{len(image_names)} готово...")

    results_zip.seek(0)
    await ctx.bot.send_document(
        chat_id=update.effective_chat.id,
        document=results_zip,
        filename=f"carousels_{st['artist']}.zip",
        caption=f"✅ Готово! {len(image_names)} каруселей 🔥\nВсе PNG без сжатия."
    )

    user_state.pop(uid, None)
    return ConversationHandler.END


async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_state.pop(uid, None)
    ctx.user_data.pop("awaiting_size", None)
    await update.message.reply_text("❌ Отменено.")
    return ConversationHandler.END


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    token = os.environ["BOT_TOKEN"]
    app = Application.builder().token(token).build()

    # Single photo / document flow (включая одиночные image-документы)
    single_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.PHOTO, photo_received),
            MessageHandler(filters.Document.ALL, document_received),
        ],
        states={
            WAIT_ARTIST:       [MessageHandler(filters.TEXT & ~filters.COMMAND, got_artist)],
            WAIT_TRACK:        [MessageHandler(filters.TEXT & ~filters.COMMAND, got_track)],
            WAIT_LYRICS:       [MessageHandler(filters.TEXT & ~filters.COMMAND, got_lyrics)],
            BATCH_WAIT_ARTIST: [MessageHandler(filters.TEXT & ~filters.COMMAND, batch_got_artist)],
            BATCH_WAIT_TRACK:  [MessageHandler(filters.TEXT & ~filters.COMMAND, batch_got_track)],
            BATCH_WAIT_LYRICS: [MessageHandler(filters.TEXT & ~filters.COMMAND, batch_got_lyrics)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CallbackQueryHandler(settings_cb))
    # Ввод размера шрифта вручную (текстовые сообщения вне конверсации)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_size_input))
    app.add_handler(single_conv)

    print("🤖 Bot started!")
    app.run_polling()


if __name__ == "__main__":
    main()
