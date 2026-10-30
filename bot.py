#!/usr/bin/env python3
"""Telegram -> GitHub uploader for ONE private repo (sarvadnya2030/visuals).

In Telegram:
  /folder <name>   set the repo folder for uploads (required before uploading)
  /folder          show the current folder
  send a file, photo, video, audio or voice note
      -> committed to <folder>/; its caption (if any) is the commit message

Albums and multiple uploads are handled one at a time, in the order sent.

Env vars: TELEGRAM_TOKEN, GITHUB_TOKEN, ALLOWED_USER_ID, GITHUB_BRANCH (default main)
"""
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

REPO = "sarvadnya2030/visuals"  # the only repo this bot ever writes to
BRANCH = os.environ.get("GITHUB_BRANCH", "main")
TOKEN = os.environ["TELEGRAM_TOKEN"]
TG = f"https://api.telegram.org/bot{TOKEN}"
TG_FILE = f"https://api.telegram.org/file/bot{TOKEN}"
GH = "https://api.github.com"
GH_HEADERS = {
    "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
    "Accept": "application/vnd.github+json",
    "User-Agent": "tg-github-bot",
}
ALLOWED = int(os.environ["ALLOWED_USER_ID"])
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
MAX_BYTES = 20 * 1024 * 1024  # Bot API download cap
# Executables/installers never go into the repo: a clone could run them.
BLOCKED_EXT = (".exe", ".msi", ".bat", ".cmd", ".ps1", ".sh", ".dll", ".so", ".jar")
# Folder: "/"-separated segments, none starting with "." (so no "..", no hidden dirs).
FOLDER_RE = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9._-]*(/[A-Za-z0-9_-][A-Za-z0-9._-]*)*$")
HELP = (
    "Send a file, photo, video, audio or voice note. Its caption becomes the commit message.\n"
    "/folder <name> sets the repo folder (required first).\n"
    "/folder shows the current folder."
)
group_captions = {}  # album caption, sent only on the first item of a media group


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


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_state(state):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f)
    os.replace(tmp, STATE_FILE)  # atomic: a crash never leaves a half-written state


def pick_file(msg):
    """Return (file_id, filename, size) for the one attachment in a message, or Nones."""
    if "document" in msg:
        d = msg["document"]
        return d["file_id"], d.get("file_name") or f"doc_{d['file_unique_id']}", d.get("file_size", 0)
    if "photo" in msg:
        p = msg["photo"][-1]  # largest size
        return p["file_id"], f"photo_{p['file_unique_id']}.jpg", p.get("file_size", 0)
    for kind, ext in (("video", "mp4"), ("audio", "mp3"), ("voice", "ogg")):
        if kind in msg:
            m = msg[kind]
            name = m.get("file_name") or f"{kind}_{m['file_unique_id']}.{ext}"
            return m["file_id"], name, m.get("file_size", 0)
    return None, None, 0


def caption_for(msg):
    cap = msg.get("caption")
    gid = msg.get("media_group_id")
    if gid:
        if cap:
            if len(group_captions) > 200:
                group_captions.clear()
            group_captions[gid] = cap
        else:
            cap = group_captions.get(gid)
    return cap


def safe(name):
    return re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(name)).lstrip(".") or "file"


def commit(path, data, message):
    url = f"{GH}/repos/{REPO}/contents/{urllib.parse.quote(path)}"
    payload = {"message": message, "content": base64.b64encode(data).decode(), "branch": BRANCH}
    return call(url, payload, headers=GH_HEADERS, method="PUT")


def command(chat, text, state):
    cmd, _, arg = text.partition(" ")
    cmd = cmd.split("@")[0].lower()  # "/folder@visgitbot" works too
    arg = arg.strip()
    if cmd == "/folder":
        if not arg:
            return reply(chat, f"Current folder: {state.get('folder') or 'not set'}")
        if len(arg) > 100 or ".." in arg or not FOLDER_RE.match(arg):
            return reply(chat, "Invalid folder. Use letters, digits, _ - . and / "
                               "(no spaces, no leading dot, no ..). Example: /folder photos/2026")
        state["folder"] = arg
        save_state(state)
        return reply(chat, f"Folder set to {arg}. Uploads go to {REPO}/{arg}/")
    reply(chat, HELP)  # /start, /help and anything unknown


RETRIES = 3
RETRY_DELAY = 5  # seconds, multiplied by attempt number


def handle(msg, state):
    chat = msg["chat"]["id"]
    if msg.get("from", {}).get("id") != ALLOWED or msg["chat"]["type"] != "private":
        return  # ignore strangers and group chats silently
    text = (msg.get("text") or "").strip()
    if text.startswith("/"):
        return command(chat, text, state)
    if "photo" in msg:
        # Telegram re-encodes photos on upload; only the file upload keeps full quality.
        return reply(chat, "Telegram compressed this photo. Resend it as a File (attach > File) to keep full quality.")
    file_id, name, size = pick_file(msg)
    if not file_id:
        return reply(chat, HELP)
    folder = state.get("folder")
    if not folder:
        return reply(chat, "No folder set. Send /folder <name> first.")
    if size > MAX_BYTES:
        return reply(chat, "Too big: the Telegram bot API only lets bots download files up to 20 MB.")
    if name.lower().endswith(BLOCKED_EXT):
        return reply(chat, "Refused: executables and installers are not committed.")
    path = f"{folder}/{time.strftime('%Y%m%d-%H%M%S')}_{msg['message_id']}_{safe(name)}"
    message = caption_for(msg) or f"Add {safe(name)} to {folder} via Telegram"
    for attempt in range(1, RETRIES + 1):  # transient network/GitHub errors: retry, then move on to the next upload
        try:
            info = call(f"{TG}/getFile", {"file_id": file_id})["result"]
            with urllib.request.urlopen(f"{TG_FILE}/{info['file_path']}", timeout=120) as r:
                data = r.read()
            commit(path, data, message)
            return reply(chat, f"Committed {path} ({len(data)} bytes) to {REPO}@{BRANCH}\nMessage: {message}")
        except Exception as e:
            print(f"upload error (attempt {attempt}/{RETRIES}):", type(e).__name__, e)  # details stay in the local log
            if attempt < RETRIES:
                time.sleep(RETRY_DELAY * attempt)
    state.setdefault("failed", []).append(path)  # kept in state.json for a manual resend
    reply(chat, f"Upload failed after {RETRIES} tries: {safe(name)}. Resend it later; the next uploads continue.")


def check_repo():
    r = call(f"{GH}/repos/{REPO}", headers=GH_HEADERS)
    if r.get("full_name") != REPO or not r.get("private"):
        sys.exit(f"refusing to run: {REPO} must exist and be private")


def main():
    check_repo()
    state = load_state()
    state.setdefault("offset", 0)
    state.setdefault("folder", None)
    print(f"bot running -> {REPO}@{BRANCH}, folder={state['folder']}")
    while True:
        try:
            updates = call(f"{TG}/getUpdates", {"offset": state["offset"], "timeout": 30})["result"]
        except urllib.error.HTTPError as e:
            if e.code in (401, 409):
                sys.exit(f"Telegram rejected polling ({e.code}): bad token, or another bot instance is running")
            print("poll error:", e.code)
            time.sleep(5)
            continue
        except Exception as e:
            print("poll error:", type(e).__name__, e)
            time.sleep(5)
            continue
        for u in updates:
            # Offset saved BEFORE handling: a crash loses that upload (user resends) instead of committing it twice.
            state["offset"] = u["update_id"] + 1
            save_state(state)
            if "message" in u:
                try:
                    handle(u["message"], state)
                except Exception as e:
                    print("handler error:", type(e).__name__, e)


if __name__ == "__main__":
    main()
