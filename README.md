# telegram-github-bot

Send a file, photo, video, audio or voice note to a Telegram bot; it commits it to a GitHub repo.

## Run

```bash
export TELEGRAM_TOKEN=...      # from @BotFather
export GITHUB_TOKEN=...        # fine-grained PAT, Contents: read/write on the target repo
export GITHUB_REPO=owner/name  # target repo
export ALLOWED_USER_ID=...     # your numeric Telegram id (others are ignored)
# optional: GITHUB_BRANCH (default main), UPLOAD_DIR (default uploads)
python3 bot.py
```

Files land at `uploads/<timestamp>_<filename>`. A caption becomes the commit message.

Limits: Telegram Bot API downloads cap at 20 MB; one file per commit; no retries.
