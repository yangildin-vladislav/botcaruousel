import os, io, zipfile, logging, threading, asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler
from generator import CarouselGenerator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
MAX_ZIP_SIZE = 19 * 1024 * 1024
CHOOSE_MODE, WAIT_FILE, WAIT_ARTIST, WAIT_TRACK, WAIT_LYRICS = range(5)

# Сервер для Render
class HealthCheck(BaseHTTPRequestHandler):
    def do_GET(self): self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
    def do_HEAD(self): self.send_response(200); self.end_headers()
    def log_message(self, *args): pass

def run_server():
    HTTPServer(('0.0.0.0', int(os.environ.get("PORT", 8080))), HealthCheck).serve_forever()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎨 Карусель (TikTok)", callback_data='carousel')],
        [InlineKeyboardButton("😎 Impact (Мемный стиль)", callback_data='impact')]
    ]
    await update.message.reply_text("Выберите режим работы:", reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSE_MODE

async def mode_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['mode'] = query.data
    await query.edit_message_text(f"Выбран режим: {query.data.upper()}\nПришлите фото или ZIP-архив:")
    return WAIT_FILE

async def receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.photo:
        fid, name, is_zip = msg.photo[-1].file_id, "image.jpg", False
    elif msg.document:
        fid, name = msg.document.file_id, msg.document.file_name
        is_zip = name.lower().endswith('.zip')
    else: return WAIT_FILE
    
    context.user_data.update({"fid": fid, "is_zip": is_zip, "name": name})
    await msg.reply_text("👤 Имя артиста:")
    return WAIT_ARTIST

async def process_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ud = context.user_data
    ud['lyrics'] = update.message.text
    await update.message.reply_text("⏳ Обработка... Подождите.")

    try:
        file = await context.bot.get_file(ud["fid"])
        f_bytes = await file.download_as_bytearray()
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
        await update.message.reply_text("✨ Готово! /start для нового заказа.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
    return ConversationHandler.END

# Промежуточные шаги
async def g_art(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['artist'] = update.message.text
    await update.message.reply_text("🎵 Название трека:"); return WAIT_TRACK
async def g_tr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['track'] = update.message.text
    await update.message.reply_text("📝 Текст песни:"); return WAIT_LYRICS

def main():
    threading.Thread(target=run_server, daemon=True).start()
    app = Application.builder().token(BOT_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSE_MODE: [CallbackQueryHandler(mode_chosen)],
            WAIT_FILE:   [MessageHandler(filters.PHOTO | filters.Document.ALL, receive_file)],
            WAIT_ARTIST: [MessageHandler(filters.TEXT & ~filters.COMMAND, g_art)],
            WAIT_TRACK:  [MessageHandler(filters.TEXT & ~filters.COMMAND, g_tr)],
            WAIT_LYRICS: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_all)],
        },
        fallbacks=[CommandHandler("cancel", lambda u,c: ConversationHandler.END)]
    )
    app.add_handler(conv)
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
