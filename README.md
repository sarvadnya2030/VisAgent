# VisAgent: Telegram to GitHub uploader

Send a file, photo, video, audio or voice note to a Telegram bot and it commits it to a private GitHub repo (`sarvadnya2030/visuals`).

## Usage (in Telegram)

- `/folder <name>` sets the repo folder for uploads (required before uploading). `/folder` shows the current one.
- Send a file. Its caption becomes the commit message.
- Files land at `<folder>/<YYYYMMDD-HHMMSS>_<message_id>_<filename>`.
- Multiple uploads are processed one at a time, in order.

## Run

```bash
export TELEGRAM_TOKEN=...      # from @BotFather
export GITHUB_TOKEN=...        # fine-grained PAT, Contents read/write on sarvadnya2030/visuals
export ALLOWED_USER_ID=...     # your numeric Telegram id; everyone else is ignored
# optional: GITHUB_BRANCH (default main)
python3 bot.py
```

The bot refuses to start unless the target repo exists and is private. Folder and offset state are kept in `state.json`.

## Limits

- Telegram bot downloads cap at 20 MB. Send photos as files to keep originals.
- Executables and installers (`.exe`, `.sh`, `.dll`, ...) are refused.
- No retries: a failed upload is resent by hand.
