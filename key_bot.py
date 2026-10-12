"""Private Telegram bot for issuing keys for a service you administer."""

from __future__ import annotations

import hashlib
import getpass
import json
import logging
import os
import re
import secrets
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from key_api import start_validation_api

LOGGER = logging.getLogger("key_bot")
# Keep credentials in environment variables, never in source control.
BOT_TOKEN = ""
ADMIN_ID = 0
ALLOWED_VALIDITY_DAYS = (7, 15, 30)
KEY_GENERATION_ATTEMPTS = 20
KEY_PREFIX_BY_DAYS = {7: "DRT-WEEK ", 15: "DRT-2WEEK ", 30: "DRT-MONTH "}
KEY_PATTERN = re.compile(r"^DRT-(?:WEEK|2WEEK|MONTH|XIT) [0-9A-F]{4}$")
KEY_FORMAT_LABEL = "DRT-WEEK / DRT-2WEEK / DRT-MONTH 0000"


def generate_key(days: int) -> str:
    """Return a short key whose prefix identifies its validity period."""
    try:
        prefix = KEY_PREFIX_BY_DAYS[days]
    except KeyError as error:
        raise ValueError("Unsupported key validity duration.") from error
    key = f"{prefix}{secrets.randbelow(0x10000):04X}"
    if not KEY_PATTERN.fullmatch(key):
        raise RuntimeError("Generated key did not match the configured format.")
    return key


class TelegramAPIError(RuntimeError):
    """Raised when Telegram returns an unsuccessful Bot API response."""


class KeyBot:
    def __init__(self, token: str, admin_id: int, database_url: str) -> None:
        import psycopg

        self.admin_id = admin_id
        self.api_url = f"https://api.telegram.org/bot{token}/"
        self.database_url = database_url
        with psycopg.connect(self.database_url) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS access_keys (
                    id BIGSERIAL PRIMARY KEY,
                    key_hash TEXT NOT NULL UNIQUE,
                    key_hint TEXT NOT NULL,
                    created_at BIGINT NOT NULL,
                    expires_at BIGINT NOT NULL,
                    revoked_at BIGINT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_state (
                    name TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )

    def connect_database(self) -> Any:
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(self.database_url, row_factory=dict_row)

    def api_call(self, method: str, payload: dict[str, Any]) -> Any:
        request = Request(
            self.api_url + method,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=35) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            try:
                details = json.loads(body).get("description", body)
            except json.JSONDecodeError:
                details = body or error.reason
            raise TelegramAPIError(
                f"Telegram {method} returned HTTP {error.code}: {details}"
            ) from error
        if not result.get("ok"):
            raise TelegramAPIError(f"Telegram {method} failed: {result!r}")
        return result["result"]

    def send_message(self, chat_id: int, text: str) -> None:
        self.api_call("sendMessage", {"chat_id": chat_id, "text": text})

    def send_admin_menu(self, chat_id: int, text: str) -> None:
        self.api_call(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text,
                "reply_markup": {
                    "keyboard": [[{"text": "GENERAR"}]],
                    "resize_keyboard": True,
                    "is_persistent": True,
                },
            },
        )

    def current_offset(self) -> int | None:
        with self.connect_database() as connection:
            row = connection.execute(
                "SELECT value FROM bot_state WHERE name = 'update_offset'"
            ).fetchone()
        return int(row["value"]) if row else None

    def save_offset(self, offset: int) -> None:
        with self.connect_database() as connection:
            connection.execute(
                """
                INSERT INTO bot_state (name, value) VALUES ('update_offset', %s)
                ON CONFLICT(name) DO UPDATE SET value = excluded.value
                """,
                (str(offset),),
            )

    def issue_keys(self, days: int, count: int) -> list[tuple[str, int]]:
        now = int(time.time())
        expires_at = now + days * 24 * 60 * 60
        issued: list[tuple[str, int]] = []
        with self.connect_database() as connection:
            for _ in range(count):
                for _ in range(KEY_GENERATION_ATTEMPTS):
                    key = generate_key(days)
                    digest = hashlib.sha256(key.encode("ascii")).hexdigest()
                    row = connection.execute(
                        """
                        INSERT INTO access_keys
                            (key_hash, key_hint, created_at, expires_at)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT(key_hash) DO NOTHING
                        RETURNING id
                        """,
                        (digest, key[-4:], now, expires_at),
                    ).fetchone()
                    if row:
                        issued.append((key, int(row["id"])))
                        break
                else:
                    raise RuntimeError(
                        "Could not create a unique short key after repeated collisions."
                    )
        return issued

    def revoke_key(self, key: str) -> bool:
        digest = hashlib.sha256(key.upper().encode("utf-8")).hexdigest()
        now = int(time.time())
        with self.connect_database() as connection:
            cursor = connection.execute(
                """
                UPDATE access_keys
                SET revoked_at = %s
                WHERE key_hash = %s AND revoked_at IS NULL
                """,
                (now, digest),
            )
        return cursor.rowcount == 1

    def list_keys(self, limit: int) -> str:
        with self.connect_database() as connection:
            rows = connection.execute(
                """
                SELECT key_hint, created_at, expires_at, revoked_at
                FROM access_keys ORDER BY id DESC LIMIT %s
                """,
                (limit,),
            ).fetchall()
        if not rows:
            return "Todavía no hay keys emitidas."

        now = int(time.time())
        lines = ["Últimas keys emitidas (solo se muestra el sufijo):"]
        for row in rows:
            if row["revoked_at"] is not None:
                status = "revocada"
            elif row["expires_at"] <= now:
                status = "expirada"
            else:
                status = "activa"
            expires = time.strftime(
                "%Y-%m-%d UTC", time.gmtime(row["expires_at"])
            )
            lines.append(f"…{row['key_hint']} · {status} · vence {expires}")
        return "\n".join(lines)

    def handle_update(self, update: dict[str, Any]) -> None:
        callback = update.get("callback_query")
        if callback:
            self.handle_callback(callback)
            return

        message = update.get("message")
        if not message or not message.get("text"):
            return

        sender = message.get("from", {})
        chat = message.get("chat", {})
        if sender.get("id") != self.admin_id or chat.get("type") != "private":
            LOGGER.warning("Ignored Telegram update from an unauthorized chat")
            if chat.get("type") == "private" and chat.get("id") is not None:
                self.send_message(
                    chat["id"],
                    "Este bot es privado. Configura TELEGRAM_ADMIN_ID con el ID "
                    "numérico de tu cuenta de Telegram.",
                )
            return

        chat_id = chat["id"]
        parts = message["text"].strip().split()
        if not parts:
            return
        command = parts[0].split("@", 1)[0].lower()

        if command in {"/start", "/help"}:
            self.send_admin_menu(
                chat_id,
                "Panel privado para generar keys.\n"
                "Pulsa GENERAR para elegir la duración: 7, 15 o 30 DAYS.\n"
                "/version — comprobar el formato activo de keys\n"
                "/list [cantidad] — ver estado y sufijo de keys recientes\n"
                "/revoke <key> — revocar una key\n"
                "La key completa se muestra una sola vez al emitirla.\n"
                "Formato generado: DRT-WEEK, DRT-2WEEK o DRT-MONTH seguido "
                "de cuatro caracteres hexadecimales.\n"
                "Aviso: el sufijo de cuatro caracteres tiene solo 16 bits y no es "
                "adecuado para proteger servicios sensibles.",
            )
        elif command == "/version":
            self.send_message(chat_id, f"Formato activo: {KEY_FORMAT_LABEL}")
        elif command in {"/new", "generar"}:
            if len(parts) != 1:
                self.send_message(chat_id, "Pulsa GENERAR sin añadir texto.")
                return
            self.send_duration_choices(chat_id)
        elif command == "/list":
            self.handle_list(chat_id, parts[1:])
        elif command == "/revoke":
            self.handle_revoke(chat_id, parts[1:])
        else:
            self.send_message(chat_id, "Comando desconocido. Usa /help.")

    def send_duration_choices(self, chat_id: int) -> None:
        keyboard = {
            "inline_keyboard": [[
                {"text": f"{days} DAYS", "callback_data": f"issue:{days}"}
                for days in ALLOWED_VALIDITY_DAYS
            ]]
        }
        self.api_call(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": "Selecciona la duración de la key:",
                "reply_markup": keyboard,
            },
        )

    def handle_callback(self, callback: dict[str, Any]) -> None:
        sender = callback.get("from", {})
        message = callback.get("message", {})
        chat = message.get("chat", {})
        data = callback.get("data", "")
        if (
            sender.get("id") != self.admin_id
            or chat.get("type") != "private"
            or not data.startswith("issue:")
        ):
            self.api_call(
                "answerCallbackQuery",
                {"callback_query_id": callback["id"], "text": "Acción no autorizada."},
            )
            return

        try:
            days = int(data.partition(":")[2])
        except ValueError:
            days = 0
        if days not in ALLOWED_VALIDITY_DAYS:
            self.api_call(
                "answerCallbackQuery",
                {"callback_query_id": callback["id"], "text": "Duración inválida."},
            )
            return

        self.api_call("answerCallbackQuery", {"callback_query_id": callback["id"]})
        self.issue_and_send_key(chat["id"], days)

    def issue_and_send_key(self, chat_id: int, days: int) -> None:
        issued = self.issue_keys(days, 1)
        validity_names = {7: "WEEK", 15: "2 WEEKS", 30: "1 MONTH"}
        expiry = time.strftime(
            "%Y-%m-%d %H:%M:%S UTC", time.gmtime(int(time.time()) + days * 86400)
        )
        lines = [
            f"Key issued · validity: {validity_names[days]} ({days} days) · expires {expiry}",
            "Guárdalas ahora; no se almacenan en texto plano:",
            *(key for key, _ in issued),
        ]
        try:
            self.send_message(chat_id, "\n".join(lines))
        except (TelegramAPIError, URLError, TimeoutError):
            for _, row_id in issued:
                self.revoke_issued_row(row_id)
            raise

    def revoke_issued_row(self, row_id: int) -> None:
        with self.connect_database() as connection:
            connection.execute(
                "UPDATE access_keys SET revoked_at = %s WHERE id = %s",
                (int(time.time()), row_id),
            )

    def handle_list(self, chat_id: int, args: list[str]) -> None:
        try:
            if len(args) > 1:
                raise ValueError
            limit = int(args[0]) if args else 10
            if not 1 <= limit <= 30:
                raise ValueError
        except ValueError:
            self.send_message(chat_id, "Uso: /list [cantidad: 1-30]")
            return
        self.send_message(chat_id, self.list_keys(limit))

    def handle_revoke(self, chat_id: int, args: list[str]) -> None:
        if len(args) != 1:
            self.send_message(chat_id, "Uso: /revoke <key>")
            return
        if self.revoke_key(args[0]):
            self.send_message(chat_id, "Key revocada.")
        else:
            self.send_message(chat_id, "No se encontró una key activa con ese valor.")

    def configure_webhook(self, webhook_url: str, secret: str) -> None:
        bot = self.api_call("getMe", {})
        LOGGER.info("Connected to Telegram as @%s (id %s)", bot.get("username"), bot.get("id"))
        self.api_call(
            "setWebhook",
            {
                "url": webhook_url,
                "secret_token": secret,
                "allowed_updates": ["message", "callback_query"],
            },
        )
        LOGGER.info(
            "Private key bot webhook configured; key format: %s",
            KEY_FORMAT_LABEL,
        )

    def run_polling(self) -> None:
        offset = self.current_offset()
        bot = self.api_call("getMe", {})
        LOGGER.info("Connected to Telegram as @%s (id %s)", bot.get("username"), bot.get("id"))
        webhook = self.api_call("getWebhookInfo", {})
        if webhook.get("url"):
            LOGGER.warning("Removing configured webhook so local polling can receive updates")
            self.api_call("deleteWebhook", {"drop_pending_updates": False})
        LOGGER.info("Private key bot started in local polling mode")
        while True:
            try:
                payload: dict[str, Any] = {
                    "timeout": 25,
                    "allowed_updates": ["message", "callback_query"],
                }
                if offset is not None:
                    payload["offset"] = offset
                updates = self.api_call("getUpdates", payload)
                for update in updates:
                    update_id = int(update["update_id"])
                    self.handle_update(update)
                    offset = update_id + 1
                    self.save_offset(offset)
            except (TelegramAPIError, URLError, TimeoutError, json.JSONDecodeError) as error:
                LOGGER.error("Telegram polling failed: %s", error)
                time.sleep(3)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    token = BOT_TOKEN.strip() or os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        token = getpass.getpass("Telegram bot token (input hidden): ").strip()
    if not token:
        raise SystemExit(
            "Set BOT_TOKEN in key_bot.py, TELEGRAM_BOT_TOKEN, or enter it when prompted."
        )

    admin_id_raw = str(ADMIN_ID) if ADMIN_ID > 0 else os.environ.get("TELEGRAM_ADMIN_ID", "").strip()
    if not admin_id_raw:
        admin_id_raw = input("Your numeric Telegram user ID: ").strip()
    try:
        admin_id = int(admin_id_raw)
        if admin_id <= 0:
            raise ValueError
    except ValueError as error:
        raise SystemExit("Set TELEGRAM_ADMIN_ID to your positive Telegram user ID.") from error

    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("Set DATABASE_URL to the Supabase PostgreSQL connection string.")
    api_host = os.environ.get("KEY_API_HOST", "127.0.0.1")
    try:
        api_port = int(
            os.environ.get("KEY_API_PORT")
            or os.environ.get("PORT", "8765")
        )
        if not 1 <= api_port <= 65535:
            raise ValueError
    except ValueError as error:
        raise SystemExit("KEY_API_PORT must be an integer from 1 to 65535.") from error
    trust_proxy = os.environ.get("KEY_API_TRUST_PROXY", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }

    webhook_secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip()
    render_url = os.environ.get("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
    bot = KeyBot(token, admin_id, database_url)
    api_server = start_validation_api(
        database_url, api_host, api_port, trust_proxy, bot, webhook_secret
    )
    LOGGER.info("Validation API listening on %s:%s", api_host, api_port)
    try:
        if render_url:
            if not webhook_secret:
                raise SystemExit("Set TELEGRAM_WEBHOOK_SECRET for Telegram webhook delivery.")
            bot.configure_webhook(f"{render_url}/telegram/webhook", webhook_secret)
            api_server.wait_for_shutdown()
        else:
            bot.run_polling()
    finally:
        api_server.shutdown()
        api_server.server_close()


if __name__ == "__main__":
    main()
