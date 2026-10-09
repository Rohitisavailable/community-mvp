# Community Desk demo video

`community-desk-demo.webm` is a 38-second, silent, captioned walkthrough. It reads the current Project A and Project B matches from the prototype's local SQLite full-text search index, then records the walkthrough in the browser as WebM. The video is a designed walkthrough, not a raw desktop recording or proof that Hermes handled the responses; it labels the sample response as local-index retrieval.

To regenerate it from PowerShell in this directory:

```powershell
..\.venv\Scripts\python.exe .\demo_server.py
```

Open `http://127.0.0.1:8790/` and click **Record demo video**. The server binds to localhost only and saves the result to this directory. The main Community Desk app must be present at the usual `outputs/community-mvp/data` path because the recorder reads its project indexes directly.
