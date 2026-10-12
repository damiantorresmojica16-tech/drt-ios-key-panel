# Telegram key bot

This bot issues access keys only for a service you administer. It does not
generate or validate keys for DRT IO or another third-party service.

## Requirements

- Python 3.10 or later
- A Telegram bot token created through Telegram's BotFather
- Your own Telegram numeric user ID

The bot and validation API use only Python's standard library.

## Configure and run

Optionally set these environment variables in the terminal where you will run
the bot:

- `TELEGRAM_BOT_TOKEN`: keep the token private; do not add it to source control.
- `TELEGRAM_ADMIN_ID`: your numeric Telegram user ID. Only this account can
  issue, inspect, or revoke keys, and commands are accepted only in a private
  chat.
- `KEYBOT_DB_PATH` (optional): SQLite database path. Defaults to `keys.sqlite3`
  in the current directory.

Keep `BOT_TOKEN` empty in `key_bot.py` and use the environment variable or
hidden startup prompt. Never save the token in source code. If a token was
previously entered into the source or shared, revoke it with BotFather and
create a replacement.

Use the token currently shown by BotFather and your own numeric Telegram user
ID (not the bot's ID). Start the script and send `/start` to the bot in a
private chat. On startup it verifies the token with Telegram and removes a
configured webhook, preserving pending updates, because this bot uses long
polling.

Then run:

```text
python key_bot.py
```

When you send `/start` or `/help`, the bot shows a persistent **GENERAR**
button. Tap it to open inline duration choices labeled **7 DAYS**, **15 DAYS**,
and **30 DAYS**. Tapping a duration issues one key in the chat.

The bot also supports:

- `GENERAR` — same action as the persistent button.
- `/list [count]` — show the status and suffix of up to 30 recent keys.
- `/revoke <key>` — revoke a key immediately.
- `/help` — show command help.

New keys use four random hexadecimal characters with a duration prefix:
`DRT-WEEK 0000` for 7 days,
`DRT-2WEEK 0000` for 15 days, or `DRT-MONTH 0000` for 30 days. Existing
`DRT-XIT` keys remain recognizable until they expire. Only the SHA-256 hash
and the suffix are stored in SQLite; the full key is shown in Telegram once
when issued. If Telegram cannot deliver the new key, the bot revokes it.

## Deploy the validation service on Render

The repository includes `render.yaml` for a paid Render web service with a
1 GB persistent disk. Persistent disks are required because the bot's SQLite
database contains the issued-key hashes and expiry times; Render's ordinary
filesystem is ephemeral. Check Render's current pricing before creating the
service.

1. Push this project, including `render.yaml`, to a private GitHub repository.
2. Sign in to Render, create a **Blueprint**, and connect that repository.
3. During Blueprint setup, enter `TELEGRAM_BOT_TOKEN` and
   `TELEGRAM_ADMIN_ID` as secret environment-variable values in Render. Never
   commit either value or send the token in chat.
4. Wait for the service health check at `/healthz` to pass. The service uses
   Render's `PORT`, binds to `0.0.0.0`, and stores SQLite under `/var/data`.
5. In the Render service settings, copy its HTTPS hostname. Replace the
   placeholder endpoint with
   `https://<your-service>.onrender.com/api/validate` in both the iOS app and
   the preview, then rebuild and distribute the app.

The Render account must be authorized by its owner. Do not use the local
preview to submit real buyer keys until the deployment is live and its HTTPS
endpoint has been configured.

## How validation and countdown work

`key_bot.py` also starts the `/api/validate` HTTP endpoint from `key_api.py`.
It checks the submitted key against the same SQLite database, rejects expired
or revoked keys, and returns its actual expiry and remaining seconds. The iOS
app and `preview.html` use that response to show the validity period and a
live DAYS/HRS/MINS/SECS countdown. The expiry clock begins when the bot issues
the key, not when the buyer first enters it.

Locally, the API listens on `127.0.0.1:8765`. On Render, the Blueprint sets
the public bind address, uses Render's `PORT`, and sets `KEY_API_TRUST_PROXY`
for the platform proxy. Keep the bot and API pointed at the same database
using `KEYBOT_DB_PATH`.

The app fails closed while the placeholder URL is configured or if the API
cannot be reached; it does not display a locally invented validity period.
The API applies a basic per-IP request limit, but a four-hex-character suffix
still has only 65,536 possibilities. That is too short for a public service:
use longer random keys and stronger production rate limiting before selling
access. Never put the Telegram bot token or database credentials in the iOS
app or browser page.

**Security warning:** a four-hex-character key has only 65,536 possible values
(16 bits) and is easy to guess or brute-force. Do not use this format to
protect valuable data, accounts, or a public service. The API's basic
per-IP limit is not sufficient production protection; longer random keys and
stronger rate limiting are strongly recommended.

If the bot does not reply, keep the terminal open and check its startup output:
`401` means the bot token is invalid or revoked, `409` can indicate another
running bot process is polling at the same time, and a private-chat notice
about `TELEGRAM_ADMIN_ID` means the configured account ID does not match yours.
Do not share the token or any log line containing it.

Use only with a service you administer. Keep the host, API, database, and TLS
reverse proxy maintained and monitored; this minimal standard-library API is
not a substitute for a hardened production authentication service.
