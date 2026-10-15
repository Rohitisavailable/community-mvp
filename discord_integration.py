"""Discord slash-command adapter for project-scoped Community Desk answers."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import logging
import os
import urllib.error
import urllib.request

from flask import Blueprint, jsonify, request
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

_LOG = logging.getLogger("community_desk.discord")
DISCORD_API = "https://discord.com/api/v10"
MAX_ANSWER_LENGTH = 1900


def create_discord_blueprint(store, project_record, answer_question):
    blueprint = Blueprint("discord", __name__)
    application_id = os.getenv("DISCORD_APPLICATION_ID", "").strip()
    bot_token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    public_key_hex = os.getenv("DISCORD_PUBLIC_KEY", "").strip()
    pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="discord-ask")

    def discord_request(method: str, url: str, payload: dict) -> dict:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bot {bot_token}",
                "Content-Type": "application/json",
                "User-Agent": "CommunityDesk (https://community-desk.onrender.com, 1.0)",
            },
            method=method,
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            raw = response.read(1_000_000)
        return json.loads(raw) if raw else {}

    def register_commands() -> None:
        if not application_id or not bot_token:
            return
        commands = [
            {
                "name": "ask",
                "description": "Ask this server's connected project sources",
                "type": 1,
                "options": [{
                    "type": 3,
                    "name": "question",
                    "description": "What would you like to know?",
                    "required": True,
                    "max_length": 1800,
                }],
            },
            {
                "name": "bind",
                "description": "Connect this Discord server to a Community Desk project",
                "type": 1,
                "options": [{
                    "type": 3,
                    "name": "project",
                    "description": "Project slug shown in Community Desk",
                    "required": True,
                    "max_length": 61,
                }],
            },
        ]
        try:
            discord_request("PUT", f"{DISCORD_API}/applications/{application_id}/commands", commands)
            _LOG.info("Registered Discord /ask and /bind commands")
        except Exception as error:
            _LOG.warning("Could not register Discord commands (%s)", type(error).__name__)

    import threading
    threading.Thread(target=register_commands, name="discord-commands", daemon=True).start()

    def verify_request(raw: bytes) -> bool:
        signature = request.headers.get("X-Signature-Ed25519", "")
        timestamp = request.headers.get("X-Signature-Timestamp", "")
        try:
            key = VerifyKey(bytes.fromhex(public_key_hex))
            key.verify(timestamp.encode("utf-8") + raw, bytes.fromhex(signature))
            return True
        except (ValueError, BadSignatureError):
            return False

    def follow_up(interaction_token: str, content: str) -> None:
        url = f"{DISCORD_API}/webhooks/{application_id}/{interaction_token}"
        req = urllib.request.Request(
            url,
            data=json.dumps({
                "content": content[:MAX_ANSWER_LENGTH],
                "allowed_mentions": {"parse": []},
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            response.read(1024)

    def answer_in_background(interaction: dict, slug: str, question: str) -> None:
        guild_id = str(interaction.get("guild_id", ""))
        channel_id = str(interaction.get("channel_id", ""))
        user = interaction.get("member", {}).get("user", {})
        user_id = str(user.get("id", "unknown"))
        try:
            result = answer_question(slug, question, f"discord:{guild_id}:{channel_id}:{user_id}", channel="discord")
            answer = str(result.get("answer", "")).strip()
            sources = str(result.get("sources", "")).strip()
            if sources and sources not in answer:
                answer += f"\n\nSources: {sources}"
            follow_up(str(interaction.get("token", "")), answer or "I couldn't find that in this project's available sources.")
        except Exception as error:
            _LOG.warning("Discord answer failed (%s)", type(error).__name__)
            try:
                follow_up(str(interaction.get("token", "")), "I couldn't complete that request just now. Please try again shortly.")
            except Exception:
                _LOG.warning("Discord error reply could not be delivered")

    @blueprint.post("/discord/interactions")
    def discord_interactions():
        if not public_key_hex:
            return jsonify({"error": "Discord interactions are not configured"}), 503
        raw = request.get_data(cache=True)
        if not verify_request(raw):
            return jsonify({"error": "Invalid Discord request signature"}), 401
        try:
            interaction = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return jsonify({"error": "Invalid interaction payload"}), 400

        if interaction.get("type") == 1:
            return jsonify({"type": 1})
        if interaction.get("type") != 2:
            return jsonify({"type": 4, "data": {"content": "Unsupported interaction.", "flags": 64}})

        data = interaction.get("data") or {}
        name = data.get("name")
        guild_id = str(interaction.get("guild_id", ""))
        if not guild_id:
            return jsonify({"type": 4, "data": {"content": "Use this command in a connected Discord server.", "flags": 64}})

        if name == "bind":
            try:
                permissions = int((interaction.get("member") or {}).get("permissions", "0"))
            except (ValueError, TypeError):
                permissions = 0
            if not permissions & (0x8 | 0x20):
                return jsonify({"type": 4, "data": {"content": "Only a server administrator or member with Manage Server permission can bind this server.", "flags": 64}})
            options = data.get("options") or []
            slug = str(options[0].get("value", "")).strip() if options else ""
            project = project_record(slug) if slug else None
            if not project:
                return jsonify({"type": 4, "data": {"content": "Project not found. Use the project slug shown in Community Desk.", "flags": 64}})
            user = (interaction.get("member") or {}).get("user", {})
            store.bind_discord_guild(guild_id, slug, str(user.get("id", "unknown")))
            return jsonify({"type": 4, "data": {"content": f"Connected this server to {project['name']}. Members can now use /ask.", "allowed_mentions": {"parse": []}}})

        if name != "ask":
            return jsonify({"type": 4, "data": {"content": "Unknown command.", "flags": 64}})
        binding = store.discord_project(guild_id)
        if not binding:
            return jsonify({"type": 4, "data": {"content": "This server is not connected yet. A server admin can use /bind project:<project-slug>.", "flags": 64}})
        project = project_record(binding["project_slug"])
        if not project:
            return jsonify({"type": 4, "data": {"content": "The connected project is unavailable. Ask a server admin to bind it again.", "flags": 64}})
        options = data.get("options") or []
        question = str(options[0].get("value", "")).strip() if options else ""
        if len(question) < 2 or len(question) > 1800:
            return jsonify({"type": 4, "data": {"content": "Please enter a question between 2 and 1,800 characters.", "flags": 64}})

        try:
            pool.submit(answer_in_background, interaction, binding["project_slug"], question)
        except RuntimeError:
            return jsonify({"type": 4, "data": {"content": "The bot is busy. Please try again shortly.", "flags": 64}})
        # Defer immediately: model/source search can take longer than Discord's
        # three-second initial-response deadline.
        return jsonify({"type": 5})

    return blueprint
