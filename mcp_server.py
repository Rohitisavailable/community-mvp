"""Project-bound read-only knowledge search tool for one Hermes profile."""
from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

from mcp.server.fastmcp import FastMCP

PROJECT_DB = Path(os.environ.get("PROJECT_KB_DB", "")).expanduser()
PROJECT_NAME = os.environ.get("PROJECT_KB_NAME", "this project").strip()
OTHER_PROJECT_NAMES = [name.strip().lower() for name in os.environ.get("OTHER_PROJECT_NAMES", "").split("|") if name.strip()]
STOP_WORDS = {"the", "and", "for", "with", "what", "when", "where", "who", "how", "does", "did", "are", "was", "were", "from", "this", "that", "project", "please", "tell", "about", "can", "you", "its", "their", "our", "into", "only", "according", "file", "files", "private", "test", "code", "exact", "information", "details", "data", "answer"}
mcp = FastMCP("project-knowledge")


@mcp.tool()
def search_project_knowledge(question: str) -> str:
    """Search only this Hermes profile's assigned project's imported sources."""
    question_lower = question.lower()
    if any(name in question_lower for name in OTHER_PROJECT_NAMES):
        return f"This Hermes profile is scoped to {PROJECT_NAME}; I can't access another project's files."
    if not PROJECT_DB.is_file():
        return "This profile's project knowledge database is not set up."
    terms = [t for t in re.findall(r"[A-Za-z0-9_-]+", question_lower) if len(t) > 2]
    if not terms:
        return "Ask a question containing terms found in this project's files."
    match = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms[:16])
    try:
        with sqlite3.connect(PROJECT_DB, timeout=5) as db:
            rows = db.execute(
                "SELECT d.filename, d.source_type, d.source_url, "
                "snippet(document_search,1,'[',']',' … ',28) "
                "FROM document_search JOIN documents AS d ON d.id=document_search.rowid "
                "WHERE document_search MATCH ? ORDER BY bm25(document_search) LIMIT 5",
                (match,),
            ).fetchall()
    except (sqlite3.Error, OSError) as exc:
        return f"Project knowledge search failed: {exc}"
    if not rows:
        return "No matching information was found in this project's sources. Do not answer from outside knowledge."
    meaningful = {term for term in terms if term not in STOP_WORDS}
    if meaningful and not any(meaningful & set(re.findall(r"[A-Za-z0-9_-]+", excerpt.lower())) for _, _, _, excerpt in rows):
        return "No matching information was found in this project's sources. Do not answer from outside knowledge."
    return "\n\n".join(
        f"Source website: {source_url or filename}\nExcerpt: {excerpt}"
        if source_type == "website"
        else f"Source file: {filename}\nExcerpt: {excerpt}"
        for filename, source_type, source_url, excerpt in rows
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
