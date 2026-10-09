"""Local helper for rendering a short, captioned Community Desk demo video."""
from __future__ import annotations

import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import app  # noqa: E402 - use the prototype's real local search index

DEMO_DIR = Path(__file__).resolve().parent
VIDEO_PATH = DEMO_DIR / "community-desk-demo.webm"
PAGE_PATH = DEMO_DIR / "index.html"
MAX_VIDEO_BYTES = 100 * 1024 * 1024


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/":
            payload = PAGE_PATH.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if path == "/data.json":
            a = app.search_project("project-a", "What is the test code ABCSDE-DADFE?")
            b = app.search_project("project-b", "What is the test code ABCSDE-DADFE?")
            uploaded = next((item for item in a if item["filename"] != "welcome.txt"), None)
            excerpt = uploaded["excerpt"] if uploaded else "No matching excerpt was found in Project A."
            codes = re.findall(r"[A-Za-z0-9]+-[A-Za-z0-9]+", excerpt)
            payload = json.dumps({
                "filename": uploaded["filename"] if uploaded else "Uploaded text file",
                "excerpt": excerpt,
                "code": codes[0] if codes else "",
                "project_a_matches": len(a),
                "project_b_matches": len(b),
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if path == "/video" and VIDEO_PATH.exists():
            payload = VIDEO_PATH.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "video/webm")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self.send_error(404)

    def do_POST(self) -> None:
        if urlsplit(self.path).path != "/save":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_VIDEO_BYTES:
            self.send_error(413, "Video must be between 1 byte and 100 MB")
            return
        payload = self.rfile.read(length)
        if not payload.startswith(b"\x1a\x45\xdf\xa3"):
            self.send_error(415, "Expected a WebM video")
            return
        VIDEO_PATH.write_bytes(payload)
        reply = json.dumps({"saved": True, "bytes": len(payload), "path": str(VIDEO_PATH)}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(reply)))
        self.end_headers()
        self.wfile.write(reply)

    def log_message(self, fmt: str, *args: object) -> None:
        print("demo-server:", fmt % args)


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 8790), Handler)
    print("Demo recorder ready at http://127.0.0.1:8790/")
    print("Localhost only; video saves inside the demo folder.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
