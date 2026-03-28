"""
TikTok Carousel Bot v6
Исправлено:
  - Размер шрифта меняется корректно (убран конфликт хендлеров)
  - Шрифт берётся из font.ttf рядом со скриптом
  - Текст трека центрирован на слайде 2
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

# ── States ────────────────────────────────────────────────────────────────────
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


def settings_text(s: dict) -> str:
    return (
        "⚙️ *Настройки оформления:*\n\n"
        f"Цвет текста: `{s['text_color']}`\n"
        f"Размытие фона: `{s['blur']}`\n"
        f"📏 Шрифт слайд 1 (артист/трек): `{s['font_size_slide1']}`\n"
        f"📏 Шрифт слайд 2 (текст трека): `{s['font_size_slide2']}`\n\n"
        "_Чтобы изменить размер шрифта — нажми кнопку и напиши число_"
    )


def settings_kb(s: dict) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎨 Цвет текста", callback_data="S_color")],
        [InlineKeyboardButton(f"📏 Размер слайд 1: {s['font_size_slide1']}", callback_data="S_sz1")],
        [InlineKeyboardButton(f"📏 Размер слайд 2: {s['font_size_slide2']}", callback_data="S_sz2")],
        [InlineKeyboardButton("💧 Размытие", callback_data="S_blur")],
        [InlineKeyboardButton("✅ Закрыть", callback_data="S_close")],
    ])


# ── /start ────────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 *TikTok Carousel Bot*\n\n"
        "Отправь фото (как документ для лучшего качества) → введи артиста, трек, текст.\n\n"
        "/settings — настройки оформления\n"
        "/cancel — отмена",
        parse_mode="Markdown"
    )


# ── /settings ─────────────────────────────────────────────────────────────────
async def cmd_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    s   = get_s(uid)
    # Сбрасываем ожидание ввода если было
    ctx.user_data.pop("size_key", None)
    ctx.user_data.pop("size_msg_id", None)
    await update.message.reply_text(
        settings_text(s), parse_mode="Markdown", reply_markup=settings_kb(s)
    )


async def settings_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id
    s   = get_s(uid)
    d   = q.data

    if d == "S_color":
        colors = ["white","yellow","cyan","pink","orange","red","green"]
        await q.edit_message_text("🎨 Выбери цвет текста:", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(c.capitalize(), callback_data=f"C_{c}") for c in colors[:4]],
            [InlineKeyboardButton(c.capitalize(), callback_data=f"C_{c}") for c in colors[4:]],
        ]))

    elif d.startswith("C_"):
        s["text_color"] = d[2:]
        await q.edit_message_text(settings_text(s), parse_mode="Markdown", reply_markup=settings_kb(s))

    elif d == "S_blur":
        await q.edit_message_text("💧 Степень размытия:", reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("0", callback_data="B_0"),
            InlineKeyboardButton("10", callback_data="B_10"),
            InlineKeyboardButton("22", callback_data="B_22"),
            InlineKeyboardButton("30", callback_data="B_30"),
        ]]))

    elif d.startswith("B_"):
        s["blur"] = int(d[2:])
        await q.edit_message_text(settings_text(s), parse_mode="Markdown", reply_markup=settings_kb(s))

    elif d == "S_sz1":
        ctx.user_data["size_key"] = "font_size_slide1"
        await q.edit_message_text(
            "📏 Введи размер шрифта для *слайда 1* (имя артиста + трек).\n"
            "Рекомендую: `60`–`100`\n\n"
            "Напиши число и отправь:",
            parse_mode="Markdown"
        )

    elif d == "S_sz2":
        ctx.user_data["size_key"] = "font_size_slide2"
        await q.edit_message_text(
            "📏 Введи размер шрифта для *слайда 2* (текст трека).\n"
            "Рекомендую: `36`–`60`\n\n"
            "Напиши число и отправь:",
            parse_mode="Markdown"
        )

    elif d == "S_close":
        await q.edit_message_text("✅ Настройки сохранены! Отправь фото для генерации.")


# ── Обработка текста ВНЕ диалога (ввод размера шрифта) ───────────────────────
async def text_outside_conv(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    key = ctx.user_data.get("size_key")

    if not key:
        await update.message.reply_text(
            "Отправь фото чтобы начать 📸\nИли /settings для настроек."
        )
        return

    text = update.message.text.strip()
    try:
        size = int(text)
        if not (10 <= size <= 200):
            raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ Введи число от 10 до 200:")
        return

    get_s(uid)[key] = size
    ctx.user_data.pop("size_key", None)

    label = "слайд 1 (артист/трек)" if key == "font_size_slide1" else "слайд 2 (текст трека)"
    s = get_s(uid)
    await update.message.reply_text(
        f"✅ Размер шрифта ({label}): `{size}`\n\n"
        f"Текущие размеры:\n"
        f"Слайд 1: `{s['font_size_slide1']}` | Слайд 2: `{s['font_size_slide2']}`\n\n"
        "Отправь фото для генерации или /settings для дальнейших настроек.",
        parse_mode="Markdown"
    )


# ── Photo / document — начало диалога ─────────────────────────────────────────
async def photo_received(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid   = update.effective_user.id
    # Сбрасываем ожидание ввода размера если было
    ctx.user_data.pop("size_key", None)

    photo = update.message.photo[-1]
    file  = await ctx.bot.get_file(photo.file_id)
    buf   = io.BytesIO()
    await file.download_to_memory(buf)
    user_state[uid] = {
        "photo": buf.getvalue(),
        "original_filename": photo.file_unique_id + ".jpg"
    }
    await update.message.reply_text(
        "✅ Фото получено!\n\n"
        "💡 *Совет:* для оригинального качества отправляй как *файл* (скрепка → файл).\n\n"
        "✏️ Напиши *имя артиста*:",
        parse_mode="Markdown"
    )
    return WAIT_ARTIST


async def document_received(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ctx.user_data.pop("size_key", None)
    doc = update.message.document

    if doc.file_name.lower().endswith((".jpg",".jpeg",".png",".webp")):
        file = await ctx.bot.get_file(doc.file_id)
        buf  = io.BytesIO()
        await file.download_to_memory(buf)
        user_state[uid] = {"photo": buf.getvalue(), "original_filename": doc.file_name}
        await update.message.reply_text(
            "✅ Фото получено!\n\n✏️ Напиши *имя артиста*:",
            parse_mode="Markdown"
        )
        return WAIT_ARTIST

    if doc.file_name.lower().endswith(".zip"):
        await update.message.reply_text("⏳ Получаю архив...")
        file = await ctx.bot.get_file(doc.file_id)
        buf  = io.BytesIO()
        await file.download_to_memory(buf)
        user_state[uid] = {"zip_buf": buf.getvalue(), "mode": "batch"}
        await update.message.reply_text(
            "✅ Архив получен!\n\n✏️ Напиши *имя артиста* (для всех фото):",
            parse_mode="Markdown"
        )
        return WAIT_ARTIST

    await update.message.reply_text("⚠️ Отправь фото (.jpg/.png) или архив (.zip)")
    return ConversationHandler.END


async def got_artist(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_state[uid]["artist"] = update.message.text.strip()
    await update.message.reply_text("🎵 Напиши *название трека*:", parse_mode="Markdown")
    return WAIT_TRACK


async def got_track(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_state[uid]["track"] = update.message.text.strip()
    await update.message.reply_text(
        "📝 Напиши *текст трека* (слова для 2-го слайда):\n\n"
        "_Каждая строка будет на отдельной строке слайда_",
        parse_mode="Markdown"
    )
    return WAIT_LYRICS


async def got_lyrics(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_state[uid]["lyrics"] = update.message.text.strip()
    st  = user_state[uid]
    msg = await update.message.reply_text("⏳ Генерирую...")

    try:
        if st.get("mode") == "batch":
            await _do_batch(update, ctx, uid, st)
        else:
            await _do_single(update, ctx, uid, st)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

    try:
        await msg.delete()
    except Exception:
        pass

    user_state.pop(uid, None)
    return ConversationHandler.END


async def _do_single(update, ctx, uid, st):
    gen = CarouselGenerator(get_s(uid))
    s1, s2, n1, n2 = gen.make_carousel(
        photo_bytes=st["photo"],
        artist=st["artist"],
        track=st["track"],
        lyrics=st["lyrics"],
        original_filename=st.get("original_filename", "image.jpg"),
    )
    from telegram import InputMediaDocument
    await ctx.bot.send_media_group(
        chat_id=update.effective_chat.id,
        media=[
            InputMediaDocument(io.BytesIO(s1), filename=n1,
                               caption=f"🎵 {st['artist']} — {st['track']}"),
            InputMediaDocument(io.BytesIO(s2), filename=n2),
        ]
    )
    await update.message.reply_text("✅ Готово! Загружай в TikTok 🔥")


async def _do_batch(update, ctx, uid, st):
    gen = CarouselGenerator(get_s(uid))
    buf = io.BytesIO(st["zip_buf"])

    with zipfile.ZipFile(buf) as zf:
        images = [n for n in zf.namelist()
                  if n.lower().endswith((".jpg",".jpeg",".png",".webp"))
                  and not n.startswith("__MACOSX")
                  and not Path(n).name.startswith(".")]

    if not images:
        await update.message.reply_text("❌ В архиве нет изображений")
        return

    await update.message.reply_text(f"🎨 {len(images)} фото — генерирую...")

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as ozf:
        buf.seek(0)
        with zipfile.ZipFile(buf) as zf:
            for i, name in enumerate(images, 1):
                s1, s2, n1, n2 = gen.make_carousel(
                    photo_bytes=zf.read(name),
                    artist=st["artist"],
                    track=st["track"],
                    lyrics=st["lyrics"],
                    original_filename=name,
                )
                ozf.writestr(n1, s1)
                ozf.writestr(n2, s2)
                if i % 5 == 0:
                    await update.message.reply_text(f"⏳ {i}/{len(images)}...")

    out.seek(0)
    await ctx.bot.send_document(
        chat_id=update.effective_chat.id,
        document=out,
        filename=f"carousels_{st['artist']}.zip",
        caption=f"✅ {len(images)} каруселей готово! 🔥"
    )


async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_state.pop(uid, None)
    ctx.user_data.pop("size_key", None)
    await update.message.reply_text("❌ Отменено. Отправь фото чтобы начать заново.")
    return ConversationHandler.END


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    token = os.environ["BOT_TOKEN"]
    app   = Application.builder().token(token).build()

    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.PHOTO, photo_received),
            MessageHandler(filters.Document.ALL, document_received),
        ],
        states={
            WAIT_ARTIST: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_artist)],
            WAIT_TRACK:  [MessageHandler(filters.TEXT & ~filters.COMMAND, got_track)],
            WAIT_LYRICS: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_lyrics)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("help",     cmd_start))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CommandHandler("cancel",   cancel))
    app.add_handler(CallbackQueryHandler(settings_cb))
    app.add_handler(conv)
    # Текст вне диалога — только для ввода размера шрифта
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_outside_conv))

    print("🤖 Bot v6 started!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
