import os, threading, secrets, sqlite3, time
from flask import Flask, abort, render_template_string, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

TOKEN = os.environ["BOT_TOKEN"]
BASE_URL = os.environ["BASE_URL"].rstrip("/")
DB = os.environ.get("DB_PATH", "/tmp/carousels.db")
app = Flask(__name__)

def db():
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS albums
        (id TEXT PRIMARY KEY, owner INTEGER, photos TEXT, created INTEGER)""")
    return con

sessions = {}
def session_for(uid):
    return sessions.setdefault(uid, [])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "سلام! به Seven of Spades خوش اومدی ♠️\n\n"
        "عکس‌هات رو یکی‌یکی یا چندتایی بفرست. ترتیب ارسال، ترتیب اسلایدهاست.\n"
        "وقتی تموم شد /done رو بزن.\n"
        "برای شروع دوباره /cancel رو بزن."
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sessions.pop(update.effective_user.id, None)
    await update.message.reply_text("آلبوم پاک شد. برای ساخت آلبوم جدید عکس بفرست.")

async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    photos = session_for(uid)
    photos.append(update.message.photo[-1].file_id)
    await update.message.reply_text(f"عکس {len(photos)} دریافت شد. عکس بعدی رو بفرست یا /done رو بزن.")

async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    photos = sessions.get(uid, [])
    if len(photos) < 2:
        await update.message.reply_text("برای اسلایدشو حداقل دو عکس بفرست.")
        return
    album_id = secrets.token_urlsafe(7)
    con = db()
    con.execute("INSERT INTO albums VALUES (?, ?, ?, ?)",
                (album_id, uid, "|".join(photos), int(time.time())))
    con.commit()
    con.close()
    sessions.pop(uid, None)
    url = f"{BASE_URL}/s/{album_id}"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("👀 پیش‌نمایش اسلایدشو", url=url)],
        [InlineKeyboardButton("📢 اشتراک‌گذاری در کانال", url=f"https://t.me/share/url?url={url}&text=اسلایدشو%20جدید%20♠️")]
    ])
    await update.message.reply_text(
        f"آماده شد! ♠️\n{len(photos)} اسلاید ساخته شد.\n"
        "برای انتشار در کانال، لینک اشتراک‌گذاری رو بزن و کانالت رو انتخاب کن.",
        reply_markup=keyboard
    )

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لطفاً عکس بفرست یا /done رو برای ساخت اسلایدشو بزن.")

@app.get("/")
def home():
    return "Seven of Spades carousel service is running."

@app.get("/s/<album_id>")
def show_album(album_id):
    con = db()
    row = con.execute("SELECT photos FROM albums WHERE id=?", (album_id,)).fetchone()
    con.close()
    if not row: abort(404)
    ids = row[0].split("|")
    # Telegram file IDs are passed to the browser endpoint; the server resolves them.
    return render_template_string(PAGE, album_id=album_id, count=len(ids))

@app.get("/api/photos/<album_id>")
def photo_data(album_id):
    con = db()
    row = con.execute("SELECT photos FROM albums WHERE id=?", (album_id,)).fetchone()
    con.close()
    if not row: abort(404)
    return {"photos": row[0].split("|")}

@app.get("/img/<path:file_id>")
def image_proxy(file_id):
    import requests
    r = requests.get(f"https://api.telegram.org/bot{TOKEN}/getFile",
                     params={"file_id": file_id}, timeout=20)
    r.raise_for_status()
    path = r.json()["result"]["file_path"]
    img = requests.get(f"https://api.telegram.org/file/bot{TOKEN}/{path}", timeout=30)
    img.raise_for_status()
    from flask import Response
    return Response(img.content, content_type=img.headers.get("Content-Type", "image/jpeg"))

PAGE = r"""
<!doctype html><html lang="fa" dir="rtl"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>Seven of Spades</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#090909;color:white;font-family:system-ui;display:flex;min-height:100vh;align-items:center;justify-content:center}
main{width:min(100vw,520px);padding:16px}.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;color:#ddd;font-size:14px}
.stage{position:relative;width:100%;aspect-ratio:4/5;background:#191919;border-radius:18px;overflow:hidden;display:flex;align-items:center;justify-content:center}
img{width:100%;height:100%;object-fit:contain}.nav{position:absolute;inset:0;display:flex;justify-content:space-between;align-items:center;padding:8px}
button{border:0;border-radius:50%;width:42px;height:42px;background:#0009;color:white;font-size:24px}
.dots{display:flex;gap:6px;justify-content:center;margin:14px 0}.dot{height:5px;width:18px;border-radius:8px;background:#555}.dot.active{background:white}
.hint{text-align:center;color:#aaa;font-size:12px}.brand{text-align:center;color:#aaa;font-size:12px;margin-top:18px;letter-spacing:2px}
</style><main><div class="top"><span>♠ SEVEN OF SPADES</span><span id="counter">1 / {{count}}</span></div>
<div class="stage" id="stage"><img id="photo" alt="اسلاید"><div class="nav"><button id="prev">‹</button><button id="next">›</button></div></div>
<div class="dots" id="dots"></div><div class="hint">برای دیدن عکس بعدی، صفحه را به چپ یا راست بکشید</div><div class="brand">SEVEN OF SPADES</div></main>
<script>
const id={{ album_id|tojson }}, img=document.getElementById('photo'), counter=document.getElementById('counter'), dots=document.getElementById('dots');
let photos=[], index=0, startX=0;
fetch('/api/photos/'+id).then(r=>r.json()).then(data=>{photos=data.photos; dots.innerHTML=photos.map((_,i)=>'<span class="dot"></span>').join(''); render();});
function render(){if(!photos.length)return;img.src='/img/'+encodeURIComponent(photos[index]);counter.textContent=(index+1)+' / '+photos.length;[...dots.children].forEach((d,i)=>d.classList.toggle('active',i===index));}
function move(n){index=(index+n+photos.length)%photos.length;render()}
document.getElementById('prev').onclick=()=>move(-1);document.getElementById('next').onclick=()=>move(1);
document.getElementById('stage').addEventListener('touchstart',e=>startX=e.touches[0].clientX,{passive:true});
document.getElementById('stage').addEventListener('touchend',e=>{let dx=e.changedTouches[0].clientX-startX;if(Math.abs(dx)>35)move(dx<0?1:-1)},{passive:true});
document.addEventListener('keydown',e=>{if(e.key==='ArrowRight')move(-1);if(e.key==='ArrowLeft')move(1)});
</script></html>
"""

def run_bot():
    import asyncio
    async def main():
        application = Application.builder().token(TOKEN).build()
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("cancel", cancel))
        application.add_handler(CommandHandler("done", done))
        application.add_handler(MessageHandler(filters.PHOTO, photo))
        application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, unknown))
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        while True:
            await asyncio.sleep(3600)
    asyncio.run(main())

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
