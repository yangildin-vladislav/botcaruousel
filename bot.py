import os, io, zipfile, logging, threading, asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    filters, ContextTypes, ConversationHandler, CallbackQueryHandler
)
from generator import CarouselGenerator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
MAX_ZIP_SIZE = 19 * 1024 * 1024
CHOOSE_MODE, WAIT_FILE, WAIT_ARTIST, WAIT_TRACK, WAIT_LYRICS = range(5)

# --- КНОПКА ОТМЕНЫ ---
def get_cancel_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена / Выйти в меню", callback_data='cancel_conv')]])

# Сервер для Render
class HealthCheck(BaseHTTPRequestHandler):
    def do_GET(self): self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
    def do_HEAD(self): self.send_response(200); self.end_headers()
    def log_message(self, *args): pass

def run_server():
    HTTPServer(('0.0.0.0', int(os.environ.get("PORT", 8080))), HealthCheck).serve_forever()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Очищаем старые данные пользователя при каждом старте
    context.user_data.clear()
    keyboard = [
        [InlineKeyboardButton("🎨 Карусель (TikTok)", callback_data='carousel')],
        [InlineKeyboardButton("😎 Impact (Мемный стиль)", callback_data='impact')]
    ]
    text = "Привет! Выбери режим работы бота:"
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSE_MODE

async def mode_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'cancel_conv':
        return await start(update, context)

    context.user_data['mode'] = query.data
    await query.edit_message_text(
        f"✅ Выбран режим: {query.data.upper()}\nТеперь пришли мне ФОТО или ZIP-АРХИВ.",
        reply_markup=get_cancel_kb()
    )
    return WAIT_FILE

async def receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.photo:
        fid, name, is_zip = msg.photo[-1].file_id, "image.jpg", False
    elif msg.document:
        fid, name = msg.document.file_id, msg.document.file_name
        is_zip = name.lower().endswith('.zip')
    else:
        await msg.reply_text("Это не фото и не ZIP. Попробуй еще раз или нажми Отмена.", reply_markup=get_cancel_kb())
        return WAIT_FILE
    
    context.user_data.update({"fid": fid, "is_zip": is_zip, "name": name})
    await msg.reply_text("👤 Введи имя артиста:", reply_markup=get_cancel_kb())
    return WAIT_ARTIST

async def g_art(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['artist'] = update.message.text
    await update.message.reply_text("🎵 Введи название трека:", reply_markup=get_cancel_kb())
    return WAIT_TRACK

async def g_tr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['track'] = update.message.text
    await update.message.reply_text("📝 Введи текст песни:", reply_markup=get_cancel_kb())
    return WAIT_LYRICS

async def process_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud = context.user_data
    ud['lyrics'] = update.message.text
    await update.message.reply_text("⏳ Начинаю магию... Подожди немного.")

    try:
        file = await context.bot.get_file(ud["fid"])
        f_bytes = await file.download_as_bytearray()
        # Настройки по умолчанию
        gen = CarouselGenerator({"text_color": "white", "blur": 22, "font_size_slide1": 80, "font_size_slide2": 45})
        mode = ud.get('mode', 'carousel')

        if not ud["is_zip"]:
            b1, b2, n1, n2 = gen.make_carousel(f_bytes, ud["artist"], ud["track"], ud["lyrics"], ud["name"], mode)
            await update.message.reply_document(io.BytesIO(b1), filename=n1)
            await update.message.reply_document(io.BytesIO(b2), filename=n2)
        else:
            out_io = io.BytesIO(); cur_zip = zipfile.ZipFile(out_io, 'w'); p = 1
            with zipfile.ZipFile(io.BytesIO(f_bytes)) as in_z:
                imgs = [f for f in in_z.namelist() if f.lower().endswith(('.png', '.jpg', '.jpeg')) and not f.startswith('__')]
                for f in imgs:
                    b1, b2, n1, n2 = gen.make_carousel(in_z.read(f), ud["artist"], ud["track"], ud["lyrics"], f, mode)
                    cur_zip.writestr(n1, b1); cur_zip.writestr(n2, b2)
                    if out_io.tell() > MAX_ZIP_SIZE:
                        cur_zip.close(); out_io.seek(0)
                        await update.message.reply_document(out_io, filename=f"part_{p}.zip")
                        out_io = io.BytesIO(); cur_zip = zipfile.ZipFile(out_io, 'w'); p += 1
            cur_zip.close()
            if out_io.tell() > 100:
                out_io.seek(0); await update.message.reply_document(out_io, filename=f"part_{p}.zip")
        
        await update.message.reply_text("✨ Готово! Нажми /start, чтобы сделать еще.")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Произошла ошибка. Попробуй заново через /start")
    
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Хендлер для кнопки Отмена"""
    query = update.callback_query
    await query.answer("Возвращаемся в меню...")
    context.user_data.clear()
    # Возвращаем пользователя к самому началу (выбор режима)
    return await start(update, context)

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Хендлер для команды /cancel"""
    context.user_data.clear()
    await update.message.reply_text("❌ Действие отменено. Напиши /start для выбора режима.")
    return ConversationHandler.END

def main():
    threading.Thread(target=run_server, daemon=True).start()
    app = Application.builder().token(BOT_TOKEN).build()
    
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSE_MODE: [CallbackQueryHandler(mode_chosen)],
            WAIT_FILE:   [
                MessageHandler(filters.PHOTO | filters.Document.ALL, receive_file),
                CallbackQueryHandler(cancel_callback, pattern='^cancel_conv$')
            ],
            WAIT_ARTIST: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, g_art),
                CallbackQueryHandler(cancel_callback, pattern='^cancel_conv$')
            ],
            WAIT_TRACK:  [
                MessageHandler(filters.TEXT & ~filters.COMMAND, g_tr),
                CallbackQueryHandler(cancel_callback, pattern='^cancel_conv$')
            ],
            WAIT_LYRICS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_all),
                CallbackQueryHandler(cancel_callback, pattern='^cancel_conv$')
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)]
    )
    
    app.add_handler(conv)
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
