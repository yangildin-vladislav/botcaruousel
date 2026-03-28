import os, io, zipfile, logging, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler, CallbackQueryHandler
)
from generator import CarouselGenerator

logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MAX_ZIP_SIZE = 19 * 1024 * 1024

# +2 новых состояния: REPEAT_OR_NEW, WAIT_REPEAT_FILE
CHOOSE_MODE, WAIT_FILE, WAIT_ARTIST, WAIT_TRACK, WAIT_LYRICS, CHOOSE_SIZE, REPEAT_OR_NEW, WAIT_REPEAT_FILE = range(8)

def get_cancel_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data='cancel_conv')]])

# Сервер для Render
class HealthCheck(BaseHTTPRequestHandler):
    def do_GET(self): self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
    def do_HEAD(self): self.send_response(200); self.end_headers()
    def log_message(self, *args): pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    kb = [[InlineKeyboardButton("🎨 Карусель (TikTok Style)", callback_data='m_carousel')],
          [InlineKeyboardButton("😎 Impact (Мемный стиль)", callback_data='m_impact')]]
    text = "Выберите режим:"
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
    return CHOOSE_MODE

async def mode_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    mode = query.data.replace('m_', '')
    context.user_data['mode'] = mode
    await query.edit_message_text(f"✅ Режим: {mode.upper()}\nПришлите фото или ZIP.", reply_markup=get_cancel_kb())
    return WAIT_FILE

async def receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.photo:
        fid, name, is_zip = msg.photo[-1].file_id, "img.jpg", False
    elif msg.document:
        fid, name = msg.document.file_id, msg.document.file_name
        is_zip = name.lower().endswith('.zip')
    else:
        return WAIT_FILE
    context.user_data.update({"fid": fid, "is_zip": is_zip, "name": name})
    await msg.reply_text("👤 Имя артиста:", reply_markup=get_cancel_kb())
    return WAIT_ARTIST

async def got_artist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['artist'] = update.message.text
    if context.user_data.get('mode') == 'impact':
        context.user_data['track'] = ""
        await update.message.reply_text("📝 Введите текст:", reply_markup=get_cancel_kb())
        return WAIT_LYRICS
    await update.message.reply_text("🎵 Название трека:", reply_markup=get_cancel_kb())
    return WAIT_TRACK

async def got_track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['track'] = update.message.text
    await update.message.reply_text("📝 Текст лирики:", reply_markup=get_cancel_kb())
    return WAIT_LYRICS

async def got_lyrics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['lyrics'] = update.message.text
    kb = [[InlineKeyboardButton("S (Мелкий)", callback_data='s_45_30')],
          [InlineKeyboardButton("M (Средний)", callback_data='s_80_50')],
          [InlineKeyboardButton("L (Крупный)", callback_data='s_115_85')],
          [InlineKeyboardButton("❌ Отмена", callback_data='cancel_conv')]]
    await update.message.reply_text("Выберите размер текста:", reply_markup=InlineKeyboardMarkup(kb))
    return CHOOSE_SIZE

async def size_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, s1, s2 = query.data.split('_')
    context.user_data['sizes'] = {'s1': int(s1), 's2': int(s2)}
    await query.edit_message_text("⏳ Обработка начата...")

    ud = context.user_data
    chat_id = update.effective_chat.id
    ok = await _process(context.bot, chat_id, ud)

    if ok:
        # Сохраняем шаблон
        context.user_data['template'] = {
            'mode':   ud['mode'],
            'artist': ud['artist'],
            'track':  ud['track'],
            'lyrics': ud['lyrics'],
            'sizes':  ud['sizes'],
        }
        kb = [
            [InlineKeyboardButton("🔁 Новое фото (тот же шаблон)", callback_data='repeat_template')],
            [InlineKeyboardButton("🆕 Начать заново", callback_data='start_new')],
        ]
        await context.bot.send_message(chat_id, "✅ Готово! Что дальше?", reply_markup=InlineKeyboardMarkup(kb))
        return REPEAT_OR_NEW
    else:
        return ConversationHandler.END

# ── Обработка выбора после рендера ──────────────────────────────────────────

async def repeat_or_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'start_new':
        # Очищаем всё и идём к старту
        context.user_data.clear()
        return await start(update, context)

    # repeat_template — показываем шаблон и ждём новый файл
    tpl = context.user_data.get('template', {})
    mode   = tpl.get('mode', '?').upper()
    artist = tpl.get('artist', '?')
    track  = tpl.get('track') or '—'
    s      = tpl.get('sizes', {})
    size_label = f"s1={s.get('s1','?')}, s2={s.get('s2','?')}"

    await query.edit_message_text(
        f"📋 Активный шаблон:\n"
        f"🎨 Режим: {mode}\n"
        f"👤 Артист: {artist}\n"
        f"🎵 Трек: {track}\n"
        f"🔡 Размер: {size_label}\n\n"
        f"Пришлите новое фото или ZIP — остальное применится автоматически.",
        reply_markup=get_cancel_kb()
    )
    return WAIT_REPEAT_FILE

async def receive_repeat_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.photo:
        fid, name, is_zip = msg.photo[-1].file_id, "img.jpg", False
    elif msg.document:
        fid, name = msg.document.file_id, msg.document.file_name
        is_zip = name.lower().endswith('.zip')
    else:
        return WAIT_REPEAT_FILE

    tpl = context.user_data.get('template', {})
    context.user_data.update({
        'fid':    fid,
        'is_zip': is_zip,
        'name':   name,
        'mode':   tpl['mode'],
        'artist': tpl['artist'],
        'track':  tpl['track'],
        'lyrics': tpl['lyrics'],
        'sizes':  tpl['sizes'],
    })

    await msg.reply_text("⏳ Обработка с шаблоном...")
    chat_id = update.effective_chat.id
    ok = await _process(context.bot, chat_id, context.user_data)

    if ok:
        kb = [
            [InlineKeyboardButton("🔁 Ещё одно фото (тот же шаблон)", callback_data='repeat_template')],
            [InlineKeyboardButton("🆕 Начать заново", callback_data='start_new')],
        ]
        await context.bot.send_message(chat_id, "✅ Готово! Что дальше?", reply_markup=InlineKeyboardMarkup(kb))
        return REPEAT_OR_NEW
    else:
        return ConversationHandler.END

# ── Общий хелпер генерации (используется в обоих местах) ────────────────────

async def _process(bot, chat_id: int, ud: dict) -> bool:
    """Генерирует карусель/impact и шлёт файлы. Возвращает True при успехе."""
    try:
        file = await bot.get_file(ud["fid"])
        f_bytes = await file.download_as_bytearray()
        gen = CarouselGenerator({
            "font_size_slide1": ud['sizes']['s1'],
            "font_size_slide2": ud['sizes']['s2'],
            "blur": 22,
            "text_color": "white",
        })

        if not ud["is_zip"]:
            b1, b2, n1, n2 = gen.make_carousel(f_bytes, ud["artist"], ud["track"], ud["lyrics"], ud["name"], ud['mode'])
            await bot.send_document(chat_id, io.BytesIO(b1), filename=n1)
            await bot.send_document(chat_id, io.BytesIO(b2), filename=n2)
        else:
            out_io = io.BytesIO()
            cur_zip = zipfile.ZipFile(out_io, 'w')
            p = 1
            with zipfile.ZipFile(io.BytesIO(f_bytes)) as in_z:
                imgs = [f for f in in_z.namelist()
                        if f.lower().endswith(('.png', '.jpg', '.jpeg')) and not f.startswith('__')]
                for f in imgs:
                    b1, b2, n1, n2 = gen.make_carousel(in_z.read(f), ud["artist"], ud["track"], ud["lyrics"], f, ud['mode'])
                    cur_zip.writestr(n1, b1)
                    cur_zip.writestr(n2, b2)
                    if out_io.tell() > MAX_ZIP_SIZE:
                        cur_zip.close()
                        out_io.seek(0)
                        await bot.send_document(chat_id, out_io, filename=f"part_{p}.zip")
                        out_io = io.BytesIO()
                        cur_zip = zipfile.ZipFile(out_io, 'w')
                        p += 1
            cur_zip.close()
            if out_io.tell() > 100:
                out_io.seek(0)
                await bot.send_document(chat_id, out_io, filename=f"part_{p}.zip")
        return True
    except Exception as e:
        await bot.send_message(chat_id, f"❌ Ошибка: {e}")
        return False

# ── Отмена ───────────────────────────────────────────────────────────────────

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
    target = update.callback_query.message if update.callback_query else update.message
    await target.reply_text("❌ Отменено. Напишите /start")
    context.user_data.clear()
    return ConversationHandler.END

# ── Запуск ───────────────────────────────────────────────────────────────────

def main():
    threading.Thread(
        target=lambda: HTTPServer(('0.0.0.0', int(os.environ.get("PORT", 8080))), HealthCheck).serve_forever(),
        daemon=True
    ).start()

    app = Application.builder().token(BOT_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSE_MODE:       [CallbackQueryHandler(mode_chosen, pattern='^m_')],
            WAIT_FILE:         [MessageHandler(filters.PHOTO | filters.Document.ALL, receive_file)],
            WAIT_ARTIST:       [MessageHandler(filters.TEXT & ~filters.COMMAND, got_artist)],
            WAIT_TRACK:        [MessageHandler(filters.TEXT & ~filters.COMMAND, got_track)],
            WAIT_LYRICS:       [MessageHandler(filters.TEXT & ~filters.COMMAND, got_lyrics)],
            CHOOSE_SIZE:       [CallbackQueryHandler(size_chosen, pattern='^s_')],
            # ── новые состояния ──
            REPEAT_OR_NEW:     [CallbackQueryHandler(repeat_or_new, pattern='^(repeat_template|start_new)$')],
            WAIT_REPEAT_FILE:  [MessageHandler(filters.PHOTO | filters.Document.ALL, receive_repeat_file)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(cancel, pattern='cancel_conv'),
        ]
    )
    app.add_handler(conv)
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
