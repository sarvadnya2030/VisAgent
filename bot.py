#!/usr/bin/env python3
"""Telegram -> GitHub uploader. Send a file/photo to the bot, it commits it to a repo.

Env vars:
  TELEGRAM_TOKEN   bot token from @BotFather
  GITHUB_TOKEN     fine-grained PAT, Contents: read/write on the target repo
  GITHUB_REPO      owner/name, e.g. shripad/my-uploads
  ALLOWED_USER_ID  your numeric Telegram user id (only this user can commit)
  GITHUB_BRANCH    optional, default main
  UPLOAD_DIR       optional, folder inside the repo, default uploads
"""
import base64
import json
import os
import re
import time
import urllib.parse
import urllib.request

TOKEN = os.environ["TELEGRAM_TOKEN"]
TG = f"https://api.telegram.org/bot{TOKEN}"
TG_FILE = f"https://api.telegram.org/file/bot{TOKEN}"
GH = "https://api.github.com"
GH_HEADERS = {
    "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
    "Accept": "application/vnd.github+json",
    "User-Agent": "tg-github-bot",
}
REPO = os.environ["GITHUB_REPO"]
BRANCH = os.environ.get("GITHUB_BRANCH", "main")
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "uploads").strip("/")
ALLOWED = int(os.environ["ALLOWED_USER_ID"])


def call(url, data=None, headers=None, method=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(
        url, data=body, method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def reply(chat, text):
    call(f"{TG}/sendMessage", {"chat_id": chat, "text": text})


def pick_file(msg):
    # ponytail: one attachment per message; Telegram albums arrive as separate messages anyway
    if "document" in msg:
        d = msg["document"]
        return d["file_id"], d.get("file_name", f"doc_{d['file_unique_id']}")
    if "photo" in msg:
        p = msg["photo"][-1]  # largest size
        return p["file_id"], f"photo_{p['file_unique_id']}.jpg"
    for kind, ext in (("video", "mp4"), ("audio", "mp3"), ("voice", "ogg")):
        if kind in msg:
            m = msg[kind]
            return m["file_id"], m.get("file_name", f"{kind}_{m['file_unique_id']}.{ext}")
    return None, None


def safe(name):
    return re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(name))


def commit(path, data, message):
    url = f"{GH}/repos/{REPO}/contents/{urllib.parse.quote(path)}"
    payload = {"message": message, "content": base64.b64encode(data).decode(), "branch": BRANCH}
    return call(url, payload, headers=GH_HEADERS, method="PUT")


def handle(msg):
    chat = msg["chat"]["id"]
    if msg["from"]["id"] != ALLOWED:
        return  # ignore strangers silently
    file_id, name = pick_file(msg)
    if not file_id:
        reply(chat, "Send me a file, photo, video, audio or voice note. Caption = commit message.")
        return
    try:
        info = call(f"{TG}/getFile", {"file_id": file_id})["result"]  # Bot API caps downloads at 20 MB
        with urllib.request.urlopen(f"{TG_FILE}/{info['file_path']}", timeout=120) as r:
            data = r.read()
        path = f"{UPLOAD_DIR}/{time.strftime('%Y%m%d-%H%M%S')}_{safe(name)}"
        message = msg.get("caption") or f"Add {path} via Telegram"
        commit(path, data, message)
        reply(chat, f"Committed {path} ({len(data)} bytes) to {REPO}@{BRANCH}")
    except Exception as e:  # ponytail: no retries; user just resends
        reply(chat, f"Failed: {e}")


def main():
    offset = 0
    print(f"bot running -> {REPO}@{BRANCH}/{UPLOAD_DIR}")
    while True:
        try:
            updates = call(f"{TG}/getUpdates", {"offset": offset, "timeout": 30})["result"]
        except Exception as e:
            print("poll error:", e)
            time.sleep(5)
            continue
        for u in updates:
            offset = u["update_id"] + 1
            if "message" in u:
                try:
                    handle(u["message"])
                except Exception as e:
                    print("handler error:", e)


if __name__ == "__main__":
    main()
