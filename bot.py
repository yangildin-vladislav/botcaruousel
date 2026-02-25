import os
import io
import zipfile
import logging
import threading
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)
# Убедитесь, что в generator.py функция называется make_carousel
from generator import CarouselGenerator

# --- КОНФИГУРАЦИЯ ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
# Лимит 19 МБ, так как Render/Telegram могут обрывать соединение на 20 МБ
MAX_ZIP_SIZE = 19 * 1024 * 1024 

WAIT_ARTIST, WAIT_TRACK, WAIT_LYRICS = range(3)

user_state = {}
DEFAULT_SETTINGS = {
    "text_color": "white",
    "blur": 22,
    "font_size_slide1": 78,
    "font_size_slide2": 44,
}

# --- МИНИ-СЕРВЕР ДЛЯ RENDER.COM ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        return # Отключаем лишние логи сервера в консоль

def run_health_check_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    logger.info(f"✅ Health check server started on port {port}")
    server.serve_forever()

# --- ЛОГИКА ОБРАБОТКИ ---
async def start_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if update.message.photo:
        file_id, mode, name = update.message.photo[-1].file_id, "single", "image.jpg"
    elif update.message.document:
        doc = update.message.document
        file_id, name = doc.file_id, doc.file_name
        mode = "batch" if name.lower().endswith('.zip') else "single"
    else:
        return ConversationHandler.END

    user_state[uid] = {"file_id": file_id, "mode": mode, "name": name}
    await update.message.reply_text("👤 Введите имя артиста:")
    return WAIT_ARTIST

async def got_artist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_state[update.effective_user.id]["artist"] = update.message.text
    await update.message.reply_text("🎵 Название трека:")
    return WAIT_TRACK

async def got_track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_state[update.effective_user.id]["track"] = update.message.text
    await update.message.reply_text("📝 Текст песни:")
    return WAIT_LYRICS

async def got_lyrics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    state = user_state.get(uid)
    if not state: return ConversationHandler.END
    state["lyrics"] = update.message.text
    
    await update.message.reply_text("⏳ Начинаю обработку. При больших пачках архивы придут частями...")

    try:
        file = await context.bot.get_file(state["file_id"])
        f_bytes = await file.download_as_bytearray()
        gen = CarouselGenerator(DEFAULT_SETTINGS)

        if state["mode"] == "single":
            b1, b2, n1, n2 = gen.make_carousel(f_bytes, state["artist"], state["track"], state["lyrics"], state["name"])
            await update.message.reply_document(io.BytesIO(b1), filename=n1)
            await update.message.reply_document(io.BytesIO(b2), filename=n2)
        else:
            with zipfile.ZipFile(io.BytesIO(f_bytes)) as in_zip:
                files = [f for f in in_zip.namelist() if f.lower().endswith(('.png', '.jpg', '.jpeg')) and not f.startswith('__')]
                
                output_zip_io = io.BytesIO()
                current_zip = zipfile.ZipFile(output_zip_io, 'w')
                part_num = 1

                for f_name in files:
                    img_data = in_zip.read(f_name)
                    b1, b2, n1, n2 = gen.make_carousel(img_data, state["artist"], state["track"], state["lyrics"], f_name)
                    
                    current_zip.writestr(n1, b1)
                    current_zip.writestr(n2, b2)

                    # Если размер архива в памяти превысил лимит
                    if output_zip_io.tell() > MAX_ZIP_SIZE:
                        current_zip.close()
                        output_zip_io.seek(0)
                        await update.message.reply_document(output_zip_io, filename=f"part_{part_num}.zip", caption=f"📦 Часть {part_num}")
                        output_zip_io = io.BytesIO()
                        current_zip = zipfile.ZipFile(output_zip_io, 'w')
                        part_num += 1

                current_zip.close()
                if output_zip_io.tell() > 100:
                    output_zip_io.seek(0)
                    await update.message.reply_document(output_zip_io, filename=f"part_{part_num}.zip", caption="✅ Финальная часть")
        
        await update.message.reply_text("✨ Обработка завершена!")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Произошла ошибка: {e}")
    
    user_state.pop(uid, None)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_state.pop(update.effective_user.id, None)
    await update.message.reply_text("❌ Отменено.")
    return ConversationHandler.END

# --- ЗАПУСК ---
def main():
    # 1. Запуск Health Check сервера для Render
    threading.Thread(target=run_health_check_server, daemon=True).start()

    if not BOT_TOKEN:
        logger.error("❌ Переменная BOT_TOKEN не установлена!")
        return

    # 2. Инициализация бота
    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.PHOTO | filters.Document.ALL, start_file)],
        states={
            WAIT_ARTIST: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_artist)],
            WAIT_TRACK:  [MessageHandler(filters.TEXT & ~filters.COMMAND, got_track)],
            WAIT_LYRICS: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_lyrics)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", lambda u, c: u.message.reply_text("📸 Пришли фото или ZIP-архив")))
    app.add_handler(conv_handler)

    logger.info("🚀 Бот запущен...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
