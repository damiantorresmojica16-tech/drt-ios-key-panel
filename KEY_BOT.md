# Telegram key bot

This bot issues access keys only for a service you administer. It does not
generate or validate keys for DRT IO or another third-party service.

## Requirements and secrets

- Python 3.10 or later
- A Telegram bot token created through Telegram's BotFather
- Your own numeric Telegram user ID
- A Supabase PostgreSQL connection string

Keep `BOT_TOKEN` empty in `key_bot.py`. Configure `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_ADMIN_ID`, `DATABASE_URL`, and (for webhook hosting)
`TELEGRAM_WEBHOOK_SECRET` as environment variables. Never commit secrets or
put them in the iOS app/browser page. If a token was published in a public
repository, revoke it in BotFather and create a replacement; deleting the
current file does not erase earlier Git commits.

## Local run

Install dependencies and set the environment variables above, then run:

```text
pip install -r requirements.txt
python key_bot.py
```

Without `RENDER_EXTERNAL_URL`, local development uses Telegram long polling.
The bot and validation API use the same PostgreSQL database, so test with a
database you control. Local API defaults to `127.0.0.1:8765`.

Send `/start` to the bot in a private chat. Tap **GENERAR** and choose **7
DAYS**, **15 DAYS**, or **30 DAYS**. The bot also supports `/list [count]`,
`/revoke <key>`, and `/help`. A generated key is displayed once and only its
SHA-256 hash and suffix are stored.

New keys use four random hexadecimal characters with a duration prefix:
`DRT-WEEK 0000` for 7 days, `DRT-2WEEK 0000` for 15 days, or `DRT-MONTH 0000`
for 30 days. That suffix has only 16 bits, which is not suitable for a public
service protecting valuable access; increase key entropy before commercial
use.

## Free hosting with Supabase and Render

This Blueprint configures a Render **Free** web service without a persistent
disk. Supabase PostgreSQL is the shared durable store for keys; Telegram
delivers bot updates to the service through an authenticated webhook.

1. Create a Supabase project and copy its PostgreSQL connection string from
   the database connection settings. Use the direct connection string unless
   Supabase's networking guidance for your project says otherwise.
2. Push this project, including `render.yaml` and `requirements.txt`, to the
   GitHub repository connected to the new Render Blueprint. Do not modify any
   unrelated Render service or repository.
3. In the Render Blueprint setup, enter `DATABASE_URL`,
   `TELEGRAM_BOT_TOKEN`, and `TELEGRAM_ADMIN_ID` as secret values. Render
   generates `TELEGRAM_WEBHOOK_SECRET` automatically.
4. Deploy and wait for `/healthz` to pass. The service uses Render's `PORT`,
   binds to `0.0.0.0`, and registers
   `https://<service>.onrender.com/telegram/webhook` with Telegram.
5. Copy the service's HTTPS hostname and configure
   `https://<service>.onrender.com/api/validate` in the iOS app and
   `preview.html`, then rebuild/distribute the app.

Free-tier availability has limits: Render may spin down an inactive service,
causing a cold start on the next request; Supabase Free may pause an inactive
project. Validation and bot updates will be unavailable during those
interruptions. Do not use uptime tricks to evade provider limits.

The Render account owner must authorize the deployment and create/configure
their own Supabase project. Never send database credentials or bot tokens in
chat or embed them in client code.

## Validation and countdown

`/api/validate` checks the submitted key against PostgreSQL, rejects expired
or revoked keys, and returns its actual expiry and remaining seconds. The iOS
app and `preview.html` use that response for the DAYS/HRS/MINS/SECS countdown.
The expiry clock begins when the bot issues the key, not when the buyer first
enters it. The server remains authoritative.

The API applies a basic per-IP request limit, but it is not a substitute for
production-grade rate limiting and authentication. Use only with a service
you administer and maintain the host, database, TLS, and keys securely.
