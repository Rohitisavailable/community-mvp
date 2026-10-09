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
                db.execute("CREATE TABLE IF NOT EXISTS community_desk.documents (id BIGSERIAL PRIMARY KEY, project_slug TEXT NOT NULL REFERENCES community_desk.projects(slug) ON DELETE CASCADE, filename TEXT NOT NULL, body TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now())")
                db.execute("CREATE INDEX IF NOT EXISTS documents_project_idx ON community_desk.documents(project_slug, id DESC)")
                db.execute("CREATE INDEX IF NOT EXISTS documents_search_idx ON community_desk.documents USING GIN (to_tsvector('simple', body))")
                db.execute("CREATE TABLE IF NOT EXISTS community_desk.messages (id BIGSERIAL PRIMARY KEY, project_slug TEXT NOT NULL REFERENCES community_desk.projects(slug) ON DELETE CASCADE, session_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now())")
                db.execute("CREATE INDEX IF NOT EXISTS messages_session_idx ON community_desk.messages(project_slug, session_id, id)")
                db.execute("CREATE TABLE IF NOT EXISTS community_desk.backboard_threads (project_slug TEXT NOT NULL REFERENCES community_desk.projects(slug) ON DELETE CASCADE, session_id TEXT NOT NULL, thread_id TEXT NOT NULL, PRIMARY KEY(project_slug, session_id))")
            return
        with self.connect("dashboard") as db:
            db.execute("CREATE TABLE IF NOT EXISTS admins (email TEXT PRIMARY KEY, password_hash TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS projects (slug TEXT PRIMARY KEY, name TEXT NOT NULL, hermes_profile TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
            existing_projects = db.execute("SELECT slug FROM projects").fetchall()
        # Add tables introduced by newer app versions to existing local project
        # databases too. Older projects do not pass through ensure_project() at
        # startup when demo seeding is disabled.
        for row in existing_projects:
            with self.connect(row["slug"]) as db:
                db.execute("CREATE TABLE IF NOT EXISTS backboard_threads (session_id TEXT PRIMARY KEY, thread_id TEXT NOT NULL)")

    def create_initial_admin(self, email: str, password_hash: str) -> None:
        with self.connect("dashboard") as db:
            count = db.execute("SELECT COUNT(*) AS n FROM admins").fetchone()["n"]
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
            db.execute("CREATE TABLE IF NOT EXISTS documents (id INTEGER PRIMARY KEY, filename TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
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
                rows = db.execute("SELECT id,filename,created_at FROM community_desk.documents WHERE project_slug=%s ORDER BY id DESC", (slug,)).fetchall()
        else:
            with self.connect(slug) as db:
                rows = db.execute("SELECT id,filename,created_at FROM documents ORDER BY id DESC").fetchall()
        return [dict(row) for row in rows]

    def add_document(self, slug: str, filename: str, body: str) -> None:
        if self.backend == "postgres":
            with self.connect("dashboard") as db:
                db.execute("INSERT INTO community_desk.documents(project_slug,filename,body) VALUES(%s,%s,%s)", (slug, filename, body))
            return
        with self.connect(slug) as db:
            # Remove orphaned FTS rows before SQLite assigns an id. Without
            # this, a previously deleted document can collide with the reused
            # id and fail the upload with an FTS constraint error.
            db.execute("DELETE FROM document_search WHERE rowid NOT IN (SELECT id FROM documents)")
            cursor = db.execute("INSERT INTO documents(filename,body) VALUES(?,?)", (filename, body))
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
                return db.execute("""SELECT filename, ts_headline('simple', body, websearch_to_tsquery('simple', %s), 'MaxFragments=2,MaxWords=30,MinWords=8') AS excerpt
                    FROM community_desk.documents
                    WHERE project_slug=%s AND to_tsvector('simple', body) @@ websearch_to_tsquery('simple', %s)
                    ORDER BY ts_rank(to_tsvector('simple', body), websearch_to_tsquery('simple', %s)) DESC LIMIT %s""", (query, slug, query, query, limit)).fetchall()
        match = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms[:16])
        try:
            with self.connect(slug) as db:
                return db.execute("SELECT filename,snippet(document_search,1,'[',']',' … ',24) AS excerpt,bm25(document_search) AS rank FROM document_search WHERE document_search MATCH ? ORDER BY bm25(document_search) LIMIT ?", (match, limit)).fetchall()
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
