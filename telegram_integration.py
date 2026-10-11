"""Optional Telegram webhook for project-scoped Community Desk support."""
from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor
import hmac
import json
import logging
import os
from pathlib import Path
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from flask import Blueprint, jsonify, request

MAX_TELEGRAM_SOURCE_BYTES = 1_000_000
MAX_TELEGRAM_TEXT = 4000
_LOG = logging.getLogger("community_desk.telegram")


def create_telegram_blueprint(store, project_record, answer_question, fetch_website_source):
    """Create a webhook blueprint with dependencies injected from app.py."""
    blueprint = Blueprint("telegram", __name__)
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    webhook_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
    admin_ids = {item.strip() for item in os.getenv("TELEGRAM_ADMIN_USER_IDS", "").split(",") if item.strip().isdigit()}
    pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="telegram-update")
    seen_lock = threading.Lock()
    seen_updates: set[int] = set()
    seen_order: deque[int] = deque()
    capacity = threading.BoundedSemaphore(24)

    def api(method: str, payload: dict | None = None) -> dict:
        if not token:
            raise RuntimeError("Telegram is not configured")
        data = json.dumps(payload or {}).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/{method}",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read(1_000_000))
        if not result.get("ok"):
            raise RuntimeError(f"Telegram API rejected {method}")
        return result.get("result", {})

    def send_text(chat_id: int | str, text: str, reply_to: int | None = None) -> None:
        # Telegram text messages are limited to 4096 characters. Use plain text
        # so source excerpts cannot inject Telegram HTML/Markdown formatting.
        chunks = [text[i:i + MAX_TELEGRAM_TEXT] for i in range(0, len(text), MAX_TELEGRAM_TEXT)] or ["I couldn't prepare a reply."]
        for index, chunk in enumerate(chunks):
            payload = {"chat_id": chat_id, "text": chunk}
            if index == 0 and reply_to is not None:
                payload["reply_parameters"] = {"message_id": reply_to, "allow_sending_without_reply": True}
            api("sendMessage", payload)

    def send_typing(chat_id: int | str) -> None:
        try:
            api("sendChatAction", {"chat_id": chat_id, "action": "typing"})
        except Exception:
            # The indicator is a UX hint; it must not break answering.
            pass

    def download_document(file_id: str, original_filename: str) -> tuple[str, str]:
        metadata = api("getFile", {"file_id": file_id})
        file_path = str(metadata.get("file_path", ""))
        file_size = int(metadata.get("file_size", 0) or 0)
        if not file_path or file_size > MAX_TELEGRAM_SOURCE_BYTES:
            raise ValueError("Please send a .txt or .md file smaller than 1 MB.")
        quoted_path = urllib.parse.quote(file_path, safe="/")
        req = urllib.request.Request(f"https://api.telegram.org/file/bot{token}/{quoted_path}")
        with urllib.request.urlopen(req, timeout=15) as response:
            raw = response.read(MAX_TELEGRAM_SOURCE_BYTES + 1)
        if len(raw) > MAX_TELEGRAM_SOURCE_BYTES:
            raise ValueError("Please send a .txt or .md file smaller than 1 MB.")
        filename = Path(original_filename or str(metadata.get("file_path", "source.txt"))).name
        if Path(filename).suffix.lower() not in {".txt", ".md"}:
            raise ValueError("Only .txt and .md documents are supported right now.")
        try:
            content = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ValueError("The file must be UTF-8 text.") from None
        if not content.strip():
            raise ValueError("That file is empty.")
        return filename, content

    def is_authorized(user: dict) -> bool:
        return str(user.get("id", "")) in admin_ids

    def help_text() -> str:
        return (
            "Hi! I can answer questions from the sources connected to this chat.\n\n"
            "Admin setup: send /myid to get your Telegram user ID.\n"
            "Admin setup: /bind project-slug\n"
            "Ask: /ask your question (in a group), or send a message here in private chat.\n"
            "Add a source: /source https://example.com/page\n"
            "Add a .txt or .md file: send it as a document.\n"
            "Disconnect: /unbind\n\n"
            "Replies prioritize this project's imported sources. If they don't contain the answer, configured web search may be used. I'm the project's bot; I won't pretend to be a human."
        )

    def process_update(update: dict) -> None:
        # Channel posts are broadcast content, not a customer question. For
        # interactive support, attach the bot to the channel's discussion group.
        message = update.get("message") or update.get("edited_message")
        if not isinstance(message, dict):
            return
        chat = message.get("chat") or {}
        sender = message.get("from") or {}
        chat_id = chat.get("id")
        if chat_id is None or not sender or sender.get("is_bot"):
            return
        chat_key = str(chat_id)
        user_key = str(sender.get("id", "unknown"))
        text = str(message.get("text", "")).strip()
        command_match = re.match(r"^/(\w+)(?:@[A-Za-z0-9_]+)?(?:\s+([\s\S]*))?$", text)
        command = command_match.group(1).lower() if command_match else ""
        argument = (command_match.group(2) or "").strip() if command_match else ""
        reply_to = message.get("message_id")

        try:
            if command in {"start", "help"}:
                send_text(chat_id, help_text(), reply_to)
                return
            if command == "myid":
                send_text(chat_id, f"Your Telegram user ID is {user_key}. Add this number to TELEGRAM_ADMIN_USER_IDS in the server environment to allow you to bind chats and upload sources.", reply_to)
                return
            if command == "bind":
                if not is_authorized(sender):
                    send_text(chat_id, "Only a configured Telegram admin can connect this chat.", reply_to)
                    return
                slug = argument.split()[0] if argument else ""
                project = project_record(slug) if slug else None
                if not project:
                    send_text(chat_id, "Project not found. Use the project slug shown in the dashboard, for example /bind project-a.", reply_to)
                    return
                store.bind_telegram_chat(chat_key, slug, str(chat.get("type", "unknown")), str(chat.get("title") or chat.get("username") or "Private chat")[:200], user_key)
                send_text(chat_id, f"Connected to {project['name']}. This chat can access only that project's sources.", reply_to)
                return
            if command == "unbind":
                if not is_authorized(sender):
                    send_text(chat_id, "Only a configured Telegram admin can disconnect this chat.", reply_to)
                    return
                store.unbind_telegram_chat(chat_key)
                send_text(chat_id, "This chat is disconnected from project knowledge.", reply_to)
                return

            binding = store.telegram_project(chat_key)
            if not binding:
                if text or message.get("document"):
                    send_text(chat_id, "This chat is not connected yet. A configured admin can connect it with /bind project-slug.", reply_to)
                return
            slug = binding["project_slug"]
            project = project_record(slug)
            if not project:
                store.unbind_telegram_chat(chat_key)
                send_text(chat_id, "The connected project is no longer available. Ask an admin to reconnect this chat.", reply_to)
                return

            document = message.get("document")
            if document:
                if not is_authorized(sender):
                    send_text(chat_id, "Only a configured Telegram admin can add project sources.", reply_to)
                    return
                filename, content = download_document(str(document.get("file_id", "")), str(document.get("file_name", "source.txt")))
                store.add_document(slug, filename, content)
                send_text(chat_id, f"Added {filename} to {project['name']} only.", reply_to)
                return

            if command == "source" or (text.lower().startswith("https://") and is_authorized(sender)):
                if not is_authorized(sender):
                    send_text(chat_id, "Only a configured Telegram admin can add website sources.", reply_to)
                    return
                url = argument if command == "source" else text
                if not url:
                    send_text(chat_id, "Use /source https://example.com/page. I import only that page, not linked pages.", reply_to)
                    return
                final_url, content = fetch_website_source(url)
                store.add_document(slug, final_url, content, source_type="website", source_url=final_url)
                send_text(chat_id, f"Added that page to {project['name']} only: {final_url}", reply_to)
                return

            if command == "ask":
                question = argument
            elif command:
                send_text(chat_id, "I don't know that command. Send /help for options.", reply_to)
                return
            elif chat.get("type") == "private":
                question = text
            else:
                # Keep group traffic quiet and avoid collecting messages that
                # were not directed to the bot. /ask always works in groups.
                return
            if len(question) < 2:
                send_text(chat_id, "Please include a question after /ask.", reply_to)
                return
            if len(question) > 5000:
                send_text(chat_id, "That question is too long; please keep it under 5,000 characters.", reply_to)
                return

            stop_typing = threading.Event()
            send_typing(chat_id)

            def keep_typing() -> None:
                while not stop_typing.wait(4):
                    send_typing(chat_id)

            typing_thread = threading.Thread(target=keep_typing, daemon=True)
            typing_thread.start()
            try:
                session = f"telegram:{chat_key}:{user_key}"
                result = answer_question(slug, question, session)
                answer = str(result.get("answer", "")).strip()
                sources = str(result.get("sources", "")).strip()
                if sources and sources not in answer:
                    answer += f"\n\nSource: {sources}"
                send_text(chat_id, answer or "I couldn't find that in this project's available sources.", reply_to)
            finally:
                stop_typing.set()
        except ValueError as error:
            send_text(chat_id, str(error), reply_to)
        except (urllib.error.URLError, TimeoutError):
            _LOG.warning("Telegram network request failed for chat %s", chat_key)
            try:
                send_text(chat_id, "I couldn't reach the source or answer service just now. Please try again shortly.", reply_to)
            except Exception:
                pass
        except Exception:
            _LOG.exception("Telegram update processing failed for chat %s", chat_key)
            try:
                send_text(chat_id, "I couldn't complete that request just now. Please try again shortly.", reply_to)
            except Exception:
                pass

    @blueprint.post("/telegram/webhook")
    def telegram_webhook():
        if not token or not webhook_secret:
            return jsonify({"error": "Telegram webhook is not configured"}), 503
        supplied = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not hmac.compare_digest(supplied, webhook_secret):
            return jsonify({"error": "Unauthorized"}), 401
        update = request.get_json(silent=True)
        if not isinstance(update, dict) or not isinstance(update.get("update_id"), int):
            return jsonify({"error": "Invalid Telegram update"}), 400
        update_id = update["update_id"]
        with seen_lock:
            if update_id in seen_updates:
                return jsonify({"ok": True, "duplicate": True})
            if not capacity.acquire(blocking=False):
                return jsonify({"error": "Busy"}), 503
            seen_updates.add(update_id)
            seen_order.append(update_id)
            while len(seen_order) > 2048:
                seen_updates.discard(seen_order.popleft())
        try:
            future = pool.submit(process_update, update)
            future.add_done_callback(lambda _future: capacity.release())
        except RuntimeError:
            with seen_lock:
                seen_updates.discard(update_id)
            capacity.release()
            return jsonify({"error": "Busy"}), 503
        return jsonify({"ok": True})

    @blueprint.get("/telegram/status")
    def telegram_status():
        # Diagnostics expose configuration state, never the bot token or secret.
        return jsonify({"configured": bool(token and webhook_secret), "admin_ids_configured": bool(admin_ids)})

    return blueprint
