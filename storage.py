"""SQLite for local mode and private-schema PostgreSQL for hosted mode."""
from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Any


class Store:
    def __init__(self, data_dir: Path, database_url: str = "") -> None:
        self.data_dir = data_dir
        self.database_url = database_url.strip()
        self.backend = "postgres" if self.database_url else "sqlite"
        if self.backend == "postgres":
            try:
                import psycopg
                from psycopg.rows import dict_row
            except ImportError as exc:
                raise RuntimeError("Install psycopg to use DATABASE_URL") from exc
            self._psycopg = psycopg
            self._dict_row = dict_row

    def connect(self, project: str = ""):
        if self.backend == "postgres":
            return self._psycopg.connect(self.database_url, row_factory=self._dict_row, connect_timeout=10, sslmode="require")
        if project == "dashboard":
            path = self.data_dir / "dashboard.sqlite3"
        else:
            path = self.data_dir / "projects" / project / "knowledge.sqlite3"
        path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def ping(self) -> None:
        """Check storage availability without running schema migrations."""
        if self.backend == "postgres":
            with self._psycopg.connect(self.database_url, connect_timeout=3, sslmode="require") as db:
                db.execute("SELECT 1")
            return
        with self.connect("dashboard") as db:
            db.execute("SELECT 1")

    def is_integrity_error(self, error: Exception) -> bool:
        if self.backend == "postgres":
            return isinstance(error, self._psycopg.IntegrityError)
        return isinstance(error, sqlite3.IntegrityError)

    def ensure_schema(self) -> None:
        if self.backend == "postgres":
            with self.connect() as db:
                db.execute("CREATE SCHEMA IF NOT EXISTS community_desk")
                db.execute("REVOKE ALL ON SCHEMA community_desk FROM PUBLIC")
                db.execute("CREATE TABLE IF NOT EXISTS community_desk.admins (email TEXT PRIMARY KEY, password_hash TEXT NOT NULL)")
                db.execute("CREATE TABLE IF NOT EXISTS community_desk.projects (slug TEXT PRIMARY KEY, name TEXT NOT NULL, hermes_profile TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now())")
                db.execute("CREATE TABLE IF NOT EXISTS community_desk.documents (id BIGSERIAL PRIMARY KEY, project_slug TEXT NOT NULL REFERENCES community_desk.projects(slug) ON DELETE CASCADE, filename TEXT NOT NULL, body TEXT NOT NULL, source_type TEXT NOT NULL DEFAULT 'file', source_url TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now())")
                db.execute("ALTER TABLE community_desk.documents ADD COLUMN IF NOT EXISTS source_type TEXT NOT NULL DEFAULT 'file'")
                db.execute("ALTER TABLE community_desk.documents ADD COLUMN IF NOT EXISTS source_url TEXT")
                db.execute("CREATE INDEX IF NOT EXISTS documents_project_idx ON community_desk.documents(project_slug, id DESC)")
                db.execute("CREATE INDEX IF NOT EXISTS documents_search_idx ON community_desk.documents USING GIN (to_tsvector('simple', body))")
                db.execute("CREATE TABLE IF NOT EXISTS community_desk.messages (id BIGSERIAL PRIMARY KEY, project_slug TEXT NOT NULL REFERENCES community_desk.projects(slug) ON DELETE CASCADE, session_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now())")
                db.execute("CREATE INDEX IF NOT EXISTS messages_session_idx ON community_desk.messages(project_slug, session_id, id)")
                db.execute("CREATE TABLE IF NOT EXISTS community_desk.backboard_threads (project_slug TEXT NOT NULL REFERENCES community_desk.projects(slug) ON DELETE CASCADE, session_id TEXT NOT NULL, thread_id TEXT NOT NULL, PRIMARY KEY(project_slug, session_id))")
                db.execute("CREATE TABLE IF NOT EXISTS community_desk.telegram_chats (chat_id TEXT PRIMARY KEY, project_slug TEXT NOT NULL REFERENCES community_desk.projects(slug) ON DELETE CASCADE, chat_type TEXT NOT NULL, chat_title TEXT NOT NULL DEFAULT '', bound_by TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now())")
                db.execute("CREATE TABLE IF NOT EXISTS community_desk.discord_guilds (guild_id TEXT PRIMARY KEY, project_slug TEXT NOT NULL REFERENCES community_desk.projects(slug) ON DELETE CASCADE, bound_by TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now())")
                db.execute("CREATE TABLE IF NOT EXISTS community_desk.rss_feeds (id BIGSERIAL PRIMARY KEY, project_slug TEXT NOT NULL REFERENCES community_desk.projects(slug) ON DELETE CASCADE, feed_url TEXT NOT NULL, channel_id TEXT NOT NULL, keywords TEXT NOT NULL DEFAULT '', initialized BOOLEAN NOT NULL DEFAULT FALSE, last_checked_at TIMESTAMPTZ, last_error TEXT NOT NULL DEFAULT '', created_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(project_slug,feed_url,channel_id))")
                db.execute("CREATE TABLE IF NOT EXISTS community_desk.rss_deliveries (feed_id BIGINT NOT NULL REFERENCES community_desk.rss_feeds(id) ON DELETE CASCADE, item_key TEXT NOT NULL, status TEXT NOT NULL, claimed_at TIMESTAMPTZ NOT NULL DEFAULT now(), published_at TIMESTAMPTZ, PRIMARY KEY(feed_id,item_key))")
            return
        with self.connect("dashboard") as db:
            db.execute("CREATE TABLE IF NOT EXISTS admins (email TEXT PRIMARY KEY, password_hash TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS projects (slug TEXT PRIMARY KEY, name TEXT NOT NULL, hermes_profile TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
            db.execute("CREATE TABLE IF NOT EXISTS telegram_chats (chat_id TEXT PRIMARY KEY, project_slug TEXT NOT NULL REFERENCES projects(slug) ON DELETE CASCADE, chat_type TEXT NOT NULL, chat_title TEXT NOT NULL DEFAULT '', bound_by TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
            db.execute("CREATE TABLE IF NOT EXISTS discord_guilds (guild_id TEXT PRIMARY KEY, project_slug TEXT NOT NULL REFERENCES projects(slug) ON DELETE CASCADE, bound_by TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
            db.execute("CREATE TABLE IF NOT EXISTS rss_feeds (id INTEGER PRIMARY KEY, project_slug TEXT NOT NULL REFERENCES projects(slug) ON DELETE CASCADE, feed_url TEXT NOT NULL, channel_id TEXT NOT NULL, keywords TEXT NOT NULL DEFAULT '', initialized INTEGER NOT NULL DEFAULT 0, last_checked_at TEXT, last_error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(project_slug,feed_url,channel_id))")
            db.execute("CREATE TABLE IF NOT EXISTS rss_deliveries (feed_id INTEGER NOT NULL REFERENCES rss_feeds(id) ON DELETE CASCADE, item_key TEXT NOT NULL, status TEXT NOT NULL, claimed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, published_at TEXT, PRIMARY KEY(feed_id,item_key))")
            existing_projects = db.execute("SELECT slug FROM projects").fetchall()
        # Add tables introduced by newer app versions to existing local project
        # databases too. Older projects do not pass through ensure_project() at
        # startup when demo seeding is disabled.
        for row in existing_projects:
            with self.connect(row["slug"]) as db:
                db.execute("CREATE TABLE IF NOT EXISTS documents (id INTEGER PRIMARY KEY, filename TEXT NOT NULL, body TEXT NOT NULL, source_type TEXT NOT NULL DEFAULT 'file', source_url TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
                columns = {column["name"] for column in db.execute("PRAGMA table_info(documents)").fetchall()}
                if "source_type" not in columns:
                    db.execute("ALTER TABLE documents ADD COLUMN source_type TEXT NOT NULL DEFAULT 'file'")
                if "source_url" not in columns:
                    db.execute("ALTER TABLE documents ADD COLUMN source_url TEXT")
                db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS document_search USING fts5(filename UNINDEXED, body, tokenize='unicode61')")
                db.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
                db.execute("CREATE TABLE IF NOT EXISTS backboard_threads (session_id TEXT PRIMARY KEY, thread_id TEXT NOT NULL)")

    def create_initial_admin(self, email: str, password_hash: str) -> None:
        with self.connect("dashboard") as db:
            table = "community_desk.admins" if self.backend == "postgres" else "admins"
            count = db.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
            if not count:
                if self.backend == "postgres":
                    db.execute("INSERT INTO community_desk.admins(email,password_hash) VALUES(%s,%s)", (email, password_hash))
                else:
                    db.execute("INSERT INTO admins(email,password_hash) VALUES(?,?)", (email, password_hash))

    def admin_hash(self, email: str):
        with self.connect("dashboard") as db:
            table = "community_desk.admins" if self.backend == "postgres" else "admins"
            marker = "%s" if self.backend == "postgres" else "?"
            return db.execute(f"SELECT password_hash FROM {table} WHERE email={marker}", (email,)).fetchone()

    def list_projects(self):
        table = "community_desk.projects" if self.backend == "postgres" else "projects"
        with self.connect("dashboard") as db:
            return [dict(row) for row in db.execute(f"SELECT slug,name,hermes_profile,created_at FROM {table} ORDER BY created_at,name")]

    def project_record(self, slug: str):
        if self.backend == "postgres":
            with self.connect("dashboard") as db:
                row = db.execute("SELECT slug,name,hermes_profile,created_at FROM community_desk.projects WHERE slug=%s", (slug,)).fetchone()
        else:
            with self.connect("dashboard") as db:
                row = db.execute("SELECT slug,name,hermes_profile,created_at FROM projects WHERE slug=?", (slug,)).fetchone()
        return dict(row) if row else None

    def bind_telegram_chat(self, chat_id: str, slug: str, chat_type: str, chat_title: str, bound_by: str) -> None:
        if self.backend == "postgres":
            with self.connect("dashboard") as db:
                db.execute("INSERT INTO community_desk.telegram_chats(chat_id,project_slug,chat_type,chat_title,bound_by) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(chat_id) DO UPDATE SET project_slug=EXCLUDED.project_slug, chat_type=EXCLUDED.chat_type, chat_title=EXCLUDED.chat_title, bound_by=EXCLUDED.bound_by", (chat_id, slug, chat_type, chat_title, bound_by))
            return
        with self.connect("dashboard") as db:
            db.execute("INSERT INTO telegram_chats(chat_id,project_slug,chat_type,chat_title,bound_by) VALUES(?,?,?,?,?) ON CONFLICT(chat_id) DO UPDATE SET project_slug=excluded.project_slug, chat_type=excluded.chat_type, chat_title=excluded.chat_title, bound_by=excluded.bound_by", (chat_id, slug, chat_type, chat_title, bound_by))

    def telegram_project(self, chat_id: str):
        table = "community_desk.telegram_chats" if self.backend == "postgres" else "telegram_chats"
        with self.connect("dashboard") as db:
            row = db.execute(f"SELECT project_slug,chat_type,chat_title FROM {table} WHERE chat_id={('%s' if self.backend == 'postgres' else '?')}", (chat_id,)).fetchone()
        return dict(row) if row else None

    def unbind_telegram_chat(self, chat_id: str) -> None:
        table = "community_desk.telegram_chats" if self.backend == "postgres" else "telegram_chats"
        marker = "%s" if self.backend == "postgres" else "?"
        with self.connect("dashboard") as db:
            db.execute(f"DELETE FROM {table} WHERE chat_id={marker}", (chat_id,))

    def bind_discord_guild(self, guild_id: str, slug: str, bound_by: str) -> None:
        if self.backend == "postgres":
            with self.connect("dashboard") as db:
                db.execute("INSERT INTO community_desk.discord_guilds(guild_id,project_slug,bound_by) VALUES(%s,%s,%s) ON CONFLICT(guild_id) DO UPDATE SET project_slug=EXCLUDED.project_slug,bound_by=EXCLUDED.bound_by", (guild_id, slug, bound_by))
            return
        with self.connect("dashboard") as db:
            db.execute("INSERT INTO discord_guilds(guild_id,project_slug,bound_by) VALUES(?,?,?) ON CONFLICT(guild_id) DO UPDATE SET project_slug=excluded.project_slug,bound_by=excluded.bound_by", (guild_id, slug, bound_by))

    def discord_project(self, guild_id: str):
        table = "community_desk.discord_guilds" if self.backend == "postgres" else "discord_guilds"
        marker = "%s" if self.backend == "postgres" else "?"
        with self.connect("dashboard") as db:
            row = db.execute(f"SELECT project_slug FROM {table} WHERE guild_id={marker}", (guild_id,)).fetchone()
        return dict(row) if row else None

    def list_rss_feeds(self, slug: str):
        table = "community_desk.rss_feeds" if self.backend == "postgres" else "rss_feeds"
        marker = "%s" if self.backend == "postgres" else "?"
        with self.connect("dashboard") as db:
            rows = db.execute(f"SELECT id,project_slug,feed_url,channel_id,keywords,initialized,last_checked_at,last_error,created_at FROM {table} WHERE project_slug={marker} ORDER BY id DESC", (slug,)).fetchall()
        return [dict(row) for row in rows]

    def add_rss_feed(self, slug: str, feed_url: str, channel_id: str, keywords: str) -> int:
        if self.backend == "postgres":
            with self.connect("dashboard") as db:
                row = db.execute("INSERT INTO community_desk.rss_feeds(project_slug,feed_url,channel_id,keywords) VALUES(%s,%s,%s,%s) RETURNING id", (slug, feed_url, channel_id, keywords)).fetchone()
                return int(row["id"])
        with self.connect("dashboard") as db:
            cursor = db.execute("INSERT INTO rss_feeds(project_slug,feed_url,channel_id,keywords) VALUES(?,?,?,?)", (slug, feed_url, channel_id, keywords))
            return int(cursor.lastrowid)

    def delete_rss_feed(self, slug: str, feed_id: int) -> bool:
        table = "community_desk.rss_feeds" if self.backend == "postgres" else "rss_feeds"
        marker = "%s" if self.backend == "postgres" else "?"
        with self.connect("dashboard") as db:
            cursor = db.execute(f"DELETE FROM {table} WHERE project_slug={marker} AND id={marker}", (slug, feed_id))
            return cursor.rowcount > 0

    def enabled_rss_feeds(self):
        table = "community_desk.rss_feeds" if self.backend == "postgres" else "rss_feeds"
        with self.connect("dashboard") as db:
            return [dict(row) for row in db.execute(f"SELECT id,project_slug,feed_url,channel_id,keywords,initialized FROM {table} ORDER BY id")]

    def set_rss_feed_status(self, feed_id: int, error: str = "") -> None:
        table = "community_desk.rss_feeds"
        marker = "%s"
        if self.backend == "sqlite":
            table, marker = "rss_feeds", "?"
        with self.connect("dashboard") as db:
            if self.backend == "postgres":
                db.execute(f"UPDATE {table} SET last_checked_at=now(),last_error={marker} WHERE id={marker}", (error[:500], feed_id))
            else:
                db.execute(f"UPDATE {table} SET last_checked_at=CURRENT_TIMESTAMP,last_error={marker} WHERE id={marker}", (error[:500], feed_id))

    def initialize_rss_feed(self, feed_id: int, item_keys: list[str]) -> None:
        table = "community_desk.rss_deliveries" if self.backend == "postgres" else "rss_deliveries"
        marker = "%s" if self.backend == "postgres" else "?"
        with self.connect("dashboard") as db:
            for item_key in item_keys:
                db.execute(f"INSERT INTO {table}(feed_id,item_key,status) VALUES({marker},{marker},'skipped') ON CONFLICT(feed_id,item_key) DO NOTHING", (feed_id, item_key))
            feeds = "community_desk.rss_feeds" if self.backend == "postgres" else "rss_feeds"
            db.execute(f"UPDATE {feeds} SET initialized=TRUE WHERE id={marker}" if self.backend == "postgres" else f"UPDATE {feeds} SET initialized=1 WHERE id={marker}", (feed_id,))

    def claim_rss_item(self, feed_id: int, item_key: str) -> bool:
        table = "community_desk.rss_deliveries" if self.backend == "postgres" else "rss_deliveries"
        marker = "%s" if self.backend == "postgres" else "?"
        with self.connect("dashboard") as db:
            if self.backend == "postgres":
                row = db.execute(f"INSERT INTO {table} AS current_item(feed_id,item_key,status) VALUES({marker},{marker},'sending') ON CONFLICT(feed_id,item_key) DO UPDATE SET status='sending',claimed_at=now() WHERE current_item.status NOT IN ('sent','skipped') AND (current_item.status!='sending' OR current_item.claimed_at < now()-interval '15 minutes') RETURNING feed_id", (feed_id, item_key)).fetchone()
                return row is not None
            row = db.execute(f"INSERT INTO {table}(feed_id,item_key,status) VALUES({marker},{marker},'sending') ON CONFLICT(feed_id,item_key) DO UPDATE SET status='sending',claimed_at=CURRENT_TIMESTAMP WHERE {table}.status NOT IN ('sent','skipped') AND ({table}.status!='sending' OR {table}.claimed_at < datetime('now','-15 minutes')) RETURNING feed_id", (feed_id, item_key)).fetchone()
            return row is not None

    def finish_rss_item(self, feed_id: int, item_key: str, sent: bool, skipped: bool = False) -> None:
        table = "community_desk.rss_deliveries" if self.backend == "postgres" else "rss_deliveries"
        marker = "%s" if self.backend == "postgres" else "?"
        with self.connect("dashboard") as db:
            status = "sent" if sent else ("skipped" if skipped else "failed")
            if sent and self.backend == "postgres":
                db.execute(f"UPDATE {table} SET status={marker},published_at=now() WHERE feed_id={marker} AND item_key={marker}", (status, feed_id, item_key))
            elif sent:
                db.execute(f"UPDATE {table} SET status={marker},published_at=CURRENT_TIMESTAMP WHERE feed_id={marker} AND item_key={marker}", (status, feed_id, item_key))
            else:
                db.execute(f"UPDATE {table} SET status={marker} WHERE feed_id={marker} AND item_key={marker}", (status, feed_id, item_key))

    def ensure_project(self, slug: str, name: str, profile: str) -> None:
        if self.backend == "postgres":
            with self.connect("dashboard") as db:
                db.execute("INSERT INTO community_desk.projects(slug,name,hermes_profile) VALUES(%s,%s,%s) ON CONFLICT(slug) DO NOTHING", (slug, name, profile))
            return
        project_dir = self.data_dir / "projects" / slug
        project_dir.mkdir(parents=True, exist_ok=True)
        with self.connect("dashboard") as db:
            db.execute("INSERT OR IGNORE INTO projects(slug,name,hermes_profile) VALUES(?,?,?)", (slug, name, profile))
        with self.connect(slug) as db:
            db.execute("CREATE TABLE IF NOT EXISTS documents (id INTEGER PRIMARY KEY, filename TEXT NOT NULL, body TEXT NOT NULL, source_type TEXT NOT NULL DEFAULT 'file', source_url TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
            columns = {column["name"] for column in db.execute("PRAGMA table_info(documents)").fetchall()}
            if "source_type" not in columns:
                db.execute("ALTER TABLE documents ADD COLUMN source_type TEXT NOT NULL DEFAULT 'file'")
            if "source_url" not in columns:
                db.execute("ALTER TABLE documents ADD COLUMN source_url TEXT")
            db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS document_search USING fts5(filename UNINDEXED, body, tokenize='unicode61')")
            db.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
            db.execute("CREATE TABLE IF NOT EXISTS backboard_threads (session_id TEXT PRIMARY KEY, thread_id TEXT NOT NULL)")

    def backboard_thread(self, slug: str, session_id: str) -> str | None:
        if self.backend == "postgres":
            with self.connect("dashboard") as db:
                row = db.execute("SELECT thread_id FROM community_desk.backboard_threads WHERE project_slug=%s AND session_id=%s", (slug, session_id)).fetchone()
        else:
            with self.connect(slug) as db:
                row = db.execute("SELECT thread_id FROM backboard_threads WHERE session_id=?", (session_id,)).fetchone()
        return row["thread_id"] if row else None

    def save_backboard_thread(self, slug: str, session_id: str, thread_id: str) -> None:
        if self.backend == "postgres":
            with self.connect("dashboard") as db:
                db.execute("INSERT INTO community_desk.backboard_threads(project_slug,session_id,thread_id) VALUES(%s,%s,%s) ON CONFLICT(project_slug,session_id) DO UPDATE SET thread_id=EXCLUDED.thread_id", (slug, session_id, thread_id))
            return
        with self.connect(slug) as db:
            db.execute("INSERT INTO backboard_threads(session_id,thread_id) VALUES(?,?) ON CONFLICT(session_id) DO UPDATE SET thread_id=excluded.thread_id", (session_id, thread_id))

    def seed_document_if_empty(self, slug: str, filename: str, body: str) -> None:
        if self.backend == "postgres":
            with self.connect("dashboard") as db:
                exists = db.execute("SELECT 1 FROM community_desk.documents WHERE project_slug=%s LIMIT 1", (slug,)).fetchone()
                if not exists:
                    db.execute("INSERT INTO community_desk.documents(project_slug,filename,body) VALUES(%s,%s,%s)", (slug, filename, body))
            return
        with self.connect(slug) as db:
            # Keep the search index in step with the authoritative documents
            # table. A deleted document can otherwise leave an FTS row behind;
            # SQLite may then reuse that document id on the next insert.
            db.execute("DELETE FROM document_search WHERE rowid NOT IN (SELECT id FROM documents)")
            if not db.execute("SELECT 1 FROM documents LIMIT 1").fetchone():
                cursor = db.execute("INSERT INTO documents(filename,body) VALUES(?,?)", (filename, body))
                db.execute("INSERT INTO document_search(rowid,filename,body) VALUES(?,?,?)", (cursor.lastrowid, filename, body))

    def documents(self, slug: str):
        if self.backend == "postgres":
            with self.connect("dashboard") as db:
                rows = db.execute("SELECT id,filename,source_type,source_url,created_at FROM community_desk.documents WHERE project_slug=%s ORDER BY id DESC", (slug,)).fetchall()
        else:
            with self.connect(slug) as db:
                rows = db.execute("SELECT id,filename,source_type,source_url,created_at FROM documents ORDER BY id DESC").fetchall()
        return [dict(row) for row in rows]

    def add_document(self, slug: str, filename: str, body: str, source_type: str = "file", source_url: str | None = None) -> None:
        if self.backend == "postgres":
            with self.connect("dashboard") as db:
                db.execute("INSERT INTO community_desk.documents(project_slug,filename,body,source_type,source_url) VALUES(%s,%s,%s,%s,%s)", (slug, filename, body, source_type, source_url))
            return
        with self.connect(slug) as db:
            # Remove orphaned FTS rows before SQLite assigns an id. Without
            # this, a previously deleted document can collide with the reused
            # id and fail the upload with an FTS constraint error.
            db.execute("DELETE FROM document_search WHERE rowid NOT IN (SELECT id FROM documents)")
            cursor = db.execute("INSERT INTO documents(filename,body,source_type,source_url) VALUES(?,?,?,?)", (filename, body, source_type, source_url))
            db.execute("INSERT INTO document_search(rowid,filename,body) VALUES(?,?,?)", (cursor.lastrowid, filename, body))

    def delete_document(self, slug: str, document_id: int) -> bool:
        if self.backend == "postgres":
            with self.connect("dashboard") as db:
                cursor = db.execute("DELETE FROM community_desk.documents WHERE project_slug=%s AND id=%s", (slug, document_id))
                return cursor.rowcount > 0
        with self.connect(slug) as db:
            exists = db.execute("SELECT 1 FROM documents WHERE id=?", (document_id,)).fetchone()
            if not exists:
                return False
            # The FTS rowid is the corresponding documents.id, so removal also
            # removes this file from search and the project-bound Hermes tool.
            db.execute("DELETE FROM document_search WHERE rowid=?", (document_id,))
            db.execute("DELETE FROM documents WHERE id=?", (document_id,))
            return True

    def search(self, slug: str, terms: list[str], limit: int):
        if not terms:
            return []
        if self.backend == "postgres":
            query = " OR ".join(terms[:16])
            with self.connect("dashboard") as db:
                return db.execute("""SELECT filename, source_type, source_url, ts_headline('simple', body, websearch_to_tsquery('simple', %s), 'MaxFragments=2,MaxWords=30,MinWords=8') AS excerpt
                    FROM community_desk.documents
                    WHERE project_slug=%s AND to_tsvector('simple', body) @@ websearch_to_tsquery('simple', %s)
                    ORDER BY ts_rank(to_tsvector('simple', body), websearch_to_tsquery('simple', %s)) DESC LIMIT %s""", (query, slug, query, query, limit)).fetchall()
        match = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms[:16])
        try:
            with self.connect(slug) as db:
                return db.execute("SELECT d.filename,d.source_type,d.source_url,snippet(document_search,1,'[',']',' … ',24) AS excerpt,bm25(document_search) AS rank FROM document_search JOIN documents AS d ON d.id=document_search.rowid WHERE document_search MATCH ? ORDER BY bm25(document_search) LIMIT ?", (match, limit)).fetchall()
        except sqlite3.OperationalError:
            return []

    def add_message(self, slug: str, session_id: str, role: str, content: str) -> None:
        if self.backend == "postgres":
            with self.connect("dashboard") as db:
                db.execute("INSERT INTO community_desk.messages(project_slug,session_id,role,content) VALUES(%s,%s,%s,%s)", (slug, session_id, role, content))
            return
        with self.connect(slug) as db:
            db.execute("INSERT INTO messages(session_id,role,content) VALUES(?,?,?)", (session_id, role, content))

    def history(self, slug: str, session_id: str, limit: int):
        if self.backend == "postgres":
            with self.connect("dashboard") as db:
                return db.execute("SELECT role,content FROM community_desk.messages WHERE project_slug=%s AND session_id=%s ORDER BY id DESC LIMIT %s", (slug, session_id, limit)).fetchall()
        with self.connect(slug) as db:
            return db.execute("SELECT role,content FROM messages WHERE session_id=? ORDER BY id DESC LIMIT ?", (session_id, limit)).fetchall()

    def add_project(self, slug: str, name: str, profile: str) -> None:
        if self.backend == "postgres":
            with self.connect("dashboard") as db:
                db.execute("INSERT INTO community_desk.projects(slug,name,hermes_profile) VALUES(%s,%s,%s)", (slug, name, profile))
        else:
            with self.connect("dashboard") as db:
                db.execute("INSERT INTO projects(slug,name,hermes_profile) VALUES(?,?,?)", (slug, name, profile))
            self.ensure_project(slug, name, profile)

    def delete_project(self, slug: str) -> None:
        if self.backend == "postgres":
            with self.connect("dashboard") as db:
                db.execute("DELETE FROM community_desk.projects WHERE slug=%s", (slug,))
            return
        with self.connect("dashboard") as db:
            db.execute("DELETE FROM projects WHERE slug=?", (slug,))
        target = (self.data_dir / "projects" / slug).resolve()
        if target.is_relative_to((self.data_dir / "projects").resolve()):
            import shutil
            shutil.rmtree(target, ignore_errors=True)
