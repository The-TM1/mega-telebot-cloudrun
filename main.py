import os, re, tempfile, shutil, mimetypes
from pathlib import Path
from fastapi import FastAPI, Request, Header, HTTPException
import httpx
from mega import Mega

BOT_TOKEN   = os.getenv("BOT_TOKEN")
TASK_SECRET = os.getenv("TASK_SECRET", "")
# Use local Bot API server instead of api.telegram.org
BASE_URL    = os.getenv("TELEGRAM_API_BASE", "http://127.0.0.1:8081")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN env var is required")
MEGA_URL_REGEX = re.compile(r"https?://mega\\.nz/\\S+", re.I)

app = FastAPI()

async def tg(method: str, data=None, files=None):
    url = f"{BASE_URL}/bot{BOT_TOKEN}/{method}"
    async with httpx.AsyncClient(timeout=600) as client:
        r = await client.post(url, data=data, files=files)
        r.raise_for_status()
        return r.json()

@app.get("/")
async def health():
    return {"ok": True}

@app.post("/webhook/{token}")
async def webhook(token: str, request: Request):
    if token != BOT_TOKEN:
        raise HTTPException(status_code=403, detail="bad token")
    payload = await request.json()
    message = payload.get("message") or payload.get("edited_message")
    if not message:
        return {"ok": True}

    chat_id = message["chat"]["id"]
    text    = (message.get("text") or "").strip()
    m = MEGA_URL_REGEX.search(text)
    if not m:
        return {"ok": True}

    mega_url = m.group(0)
    # Respond quickly to Telegram to avoid webhook timeouts
    await tg("sendMessage", data={"chat_id": chat_id, "text": "⏬ Got it — downloading…"})
    # Kick off long-running task
    base_host = request.headers.get('host')
    async with httpx.AsyncClient(timeout=1800) as client:
        await client.post(f"http://{base_host}/task/process",
                          json={"chat_id": chat_id, "mega_url": mega_url},
                          headers={"X-Task-Key": TASK_SECRET})
    return {"ok": True}

@app.post("/task/process")
async def process_task(payload: dict, x_task_key: str = Header(default="")):
    if TASK_SECRET == "" or x_task_key != TASK_SECRET:
        raise HTTPException(status_code=403, detail="unauthorized task caller")
    chat_id = int(payload["chat_id"])
    url     = payload["mega_url"]

    tmpdir = Path(tempfile.mkdtemp(prefix="mega_"))
    file_path = None
    try:
        mega = Mega()
        m = mega.login_anonymous()
        local_path = m.download_url(url, dest_path=str(tmpdir))
        file_path  = Path(local_path)
        if not file_path.exists():
            await tg("sendMessage", data={"chat_id": chat_id, "text": "❌ Download failed."})
            return {"ok": False}
        size = file_path.stat().st_size
        # 2 GB limit enforced by local API. Warn if the file is too big.
        if size > 2 * 1024 * 1024 * 1024:
            mb = f"{size/1024/1024/1024:.1f} GB"
            await tg("sendMessage",
                     data={"chat_id": chat_id,
                           "text": f"⚠️ File is {mb}, which exceeds the 2 GB upload limit."})
            return {"ok": True}
        mime, _ = mimetypes.guess_type(str(file_path))
        method = "sendVideo" if (mime or "").startswith("video/") else "sendDocument"
        field  = "video" if method == "sendVideo" else "document"

        data  = {"chat_id": str(chat_id), "caption": file_path.name}
        files = {field: (file_path.name, open(file_path, "rb"))}
        await tg(method, data=data, files=files)
        await tg("sendMessage", data={"chat_id": chat_id, "text": "✅ Done."})
        return {"ok": True}
    except Exception as e:
        await tg("sendMessage", data={"chat_id": chat_id, "text": f"❌ Failed: {e}"})
        return {"ok": False}
    finally:
        try:
            if file_path and file_path.exists():
                file_path.unlink()
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass
