# Client Call: Implementation Notes

**Source:** `Desktop 2026.10.09 - 15.14.16.01.mp4` (about 8 minutes)
**Status:** Audio reviewed with local speech recognition; confirm the uncertain details with the client before expanding scope.

## Client clarification (direct instruction in chat)

The client wants the first feature to let an admin add knowledge sources to a project, including **website links and multiple files in one upload flow**, similar in spirit to [Bonfires](https://www.bonfires.ai/). Use Bonfires as product inspiration for a shared knowledge-source experience; this does not mean cloning its full knowledge graph, chat connectors, or background conversation ingestion. Bonfires describes a shared knowledge environment fed by connected sources and conversations in its [product overview](https://www.bonfires.ai/) and [documentation](https://docs.bonfires.ai/).

## Updated feature scope

Build a simple **Project Knowledge Sources** area:

- Add one or more website URLs to the selected project.
- Select and upload multiple supported files in a single action.
- Keep source records, extracted text, and indexing scoped to that project.
- Show each source's name/URL, type, processing status, and an option to remove it.
- Ground the project's Q&A **only in successfully processed sources explicitly added to that project**. Do not use Google, general web search, or unrelated model knowledge as a fallback.
- Cite the exact filename or imported website URL used to answer.
- If the project's sources do not contain the answer, say that no answer was found in those sources and ask the user to add the needed source. Do not guess or silently search elsewhere.
- Handle failed/unreachable URLs or unsupported files with a visible per-source error and allow retry/removal.

For MVP, website ingestion should fetch the entered page(s) only. A site-wide crawl, private GitHub authentication, continuous syncing, graph visualization, and background chat ingestion are **out of scope unless the client explicitly asks for them**. Confirm PDF/Office support before promising it; the current MVP accepts `.txt` and `.md`.

## Requirements heard in the call

The clearest product discussion is around 04:04–05:00. The speaker describes three ways to provide project knowledge:

1. **Website link:** paste a website URL and have the app read/import its online content. GitHub is mentioned as an example or source, but the exact scope is unclear.
2. **File upload:** add local files to the project. The recording suggests files as an input method; the later chat clarification specifies multiple files in one flow. The file formats are not stated in the call.
3. **Paste text:** copy and paste content directly into the project.

The speaker then discusses filtering/using the collected data and an offline-data option. The exact meaning is uncertain. The whiteboard visually groups three numbered inputs, points them toward a central step, and shows a separate right-side box, which is consistent with a source-ingestion flow but does not label the processing or output.

## Suggested implementation checklist

- [ ] Add a project-scoped **Website URL** input that fetches and extracts readable page content from the entered URL(s) only.
- [ ] Support adding multiple files in one selection/upload action.
- [ ] Keep website ingestion limited to the entered page(s) for the MVP; expand to linked-page/site crawling only if approved.
- [ ] Confirm whether GitHub repositories are a required source type or merely an example website. If required, define supported public/private repository access and credential handling.
- [ ] Keep the existing **file upload** flow and confirm which formats to support (current MVP accepts `.txt` and `.md`).
- [ ] Add a **paste text** flow with a title/source name so the content can be identified in answers.
- [ ] Send content from all approved sources through the same project-isolated storage and retrieval path; never retrieve another project's material.
- [ ] Clarify what “filter” means: filtering sources before saving, selecting relevant passages at question time, or filtering what the user sees.
- [ ] Clarify whether “offline” means local-only storage, the ability to query already-imported data without internet, or simply manually pasted content.
- [ ] Show source name/type and ingestion status so admins can tell what material was imported and where an answer came from.

## Acceptance checks to propose

- Select at least two files together and verify both appear as separate sources after processing.
- Add a website URL and verify its readable content is indexed for the selected project.
- Add one known fact through each supported input method and ask the same project a question that retrieves it.
- Ask a question whose answer is in an uploaded file and verify the answer cites that filename.
- Ask a question whose answer is in an imported website page and verify the answer cites that URL.
- Ask an unrelated question absent from all project sources; verify the assistant abstains and does not return general web-search results.
- Verify the answer path makes no Google or external-search request.
- Ask the question from a different project and verify that none of those facts appear.
- For website ingestion, show the source URL in the answer or source list and verify behavior for an unreachable page.
- For uploaded and pasted content, show the source title/filename in the answer.
- If offline use is required, disconnect the app from the internet after ingestion and confirm the agreed offline behavior.

## Questions to confirm with the client

1. Should a website source fetch only the entered URL or also crawl linked pages?
2. Is GitHub a required source type? If so, should private repositories be supported?
3. Which file formats are required beyond `.txt` and `.md`?
4. Should pasted text be saved as a named knowledge source?
5. What does the “filter” step do, and who controls it?
6. What does “offline” mean in this product, and which sources must remain usable offline?
7. What does the final right-hand box on the whiteboard represent: the indexed knowledge, the AI answer, or another output?

The client has already clarified that answers must come from the uploaded file or imported website source only, with no Google results. The remaining question is limited to how the UI should explain an unanswered question; the safe behavior is to say the source material does not contain the answer.

## Transcript confidence

The local multilingual speech-to-text pass identifies Marathi/Hinglish with English technical terms. It is imperfect, especially after about 05:00, so the checklist preserves the clear source types and marks interpretation-dependent details for confirmation. The notes are a summary, not a verbatim transcript or a claim that every phrase was decoded correctly.
