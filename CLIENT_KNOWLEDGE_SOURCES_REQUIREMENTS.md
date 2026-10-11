# Client Requirements: Knowledge Sources and Grounded Answers

**Status:** Project-scoped file and website ingestion, project-first answers with optional Backboard web-search fallback, and an optional Telegram webhook are implemented in the working tree. This behavior has not been runtime-tested or deployed. Web fallback requires `WEB_SEARCH_ENABLED=true`, the Backboard provider, and valid provider credentials/model settings. Telegram requires its own webhook bot token; do not reuse a token currently polling through Hermes.
**Reference product:** [Bonfires](https://www.bonfires.ai/) as inspiration for a unified knowledge-source experience. This is a focused MVP requirement, not a request to clone Bonfires.

## Business objective

Automate customer-care responses across the web dashboard and connected Telegram/Discord bots so the client does not need to retain a dedicated customer-care employee for routine questions. Prefer the client's configured project sources. If they do not answer, the bot may use general internet search when enabled, clearly label those facts as web results, and cite the URLs. Never use uncited model memory as a substitute. Define separately what should happen for exceptional cases that still need a person or an operational action.

## Conversation style

The AI should chat naturally and warmly, like a helpful customer-care representative: understand follow-up questions, use the conversation context, and respond clearly without sounding like a rigid template. Do not add unsolicited AI disclaimers to ordinary replies. A natural tone must not weaken the evidence rule: use uploaded sources first, then cite internet URLs when web fallback is used; if neither supports an answer, say so. If a customer directly asks whether they are speaking to AI or a person, answer truthfully and do not impersonate a human employee.

## 1. Add knowledge sources to a project

Provide an admin-facing source area within each project. It should let the admin:

- Add a website link for the project’s knowledge base.
- Select and upload multiple files in one action.
- See the added sources with their filename or URL, source type, and processing status.
- Remove a source from the project.

Imported content must be indexed and stored within the selected project’s namespace. A source added to Project A must never appear in Project B’s retrieval results.

For the initial MVP, fetch the website URL explicitly provided by the admin. Whole-site crawling, private GitHub access, continuous sync, and other connectors are outside this requirement until separately approved. Confirm required file formats before promising anything beyond the existing `.txt` and `.md` support.

## 2. Prefer project sources, with cited internet fallback

The AI must first search successfully processed files and website pages added to the currently selected project. If those sources do not contain enough information, the configured web-search provider may answer from public internet pages.

- Do not fill gaps with unsupported model knowledge or guesses.
- Clearly distinguish project-source facts from web-search facts. Cite filenames/imported URLs for project material and direct page URLs for web results.
- If web search is disabled or neither project sources nor cited web results contain the answer, say so plainly and invite the user to add the relevant source.
- Keep every retrieval scoped to the active project.

### Source filter between knowledge and results

Add a source-selection/filter step between the project's stored sources and the answer. The filter should choose relevant, imported project sources before any AI provider receives context. If the question clearly names a source—for example, a Zomato page—and that source is available, prioritize that imported content and show its citation. If it does not contain the answer, web fallback is allowed under the latest client clarification but must be labeled as web material and cite its direct URLs.

For questions without a clear named source, search relevant sources within the active project first, then use web search only when enabled and needed. Show whether each cited source is project content or a web result. An explicit source selector in the UI (for example, “All project sources” or one selected source) can make this behavior inspectable; the client has not specified whether that selector must be user-controlled or can be automatic.

## 3. Multiple AI providers working together

The client also wants multiple AI providers—such as Claude, Gemini, and GPT—to work together on answers, rather than offering only one model at a time.

- Add provider adapters so enabled providers can be called through a common interface.
- For each question, retrieve evidence once from the active project's sources, then give the same evidence and question to each enabled provider.
- Combine the providers' responses into one final answer. Use supplied project evidence first; if a provider uses web search as fallback, label those claims and cite their direct URLs.
- Do not allow a provider to answer from unsupported outside knowledge without citations.
- Keep provider API keys server-side in environment variables or an equivalent secrets manager; never return or log their values in the dashboard.
- Show which providers are enabled and report provider failures clearly. Do not silently present one provider's output as a complete multi-provider result.

**Cost constraint:** The original MVP asks for a 100% free stack. Claude, Gemini, and GPT API access may have different pricing or free quotas, which can change. Confirm the allowed budget and provider credentials before enabling hosted providers; keep provider calls disabled until configured.

## 4. API for Telegram, Discord, and other bots

Provide a documented HTTPS API that lets an external bot use the same project knowledge Q&A as the web dashboard. A suitable initial shape is `POST /api/v1/projects/{project_id}/ask`; treat this as a proposed route name until the API contract is finalized.

- The caller sends a question and receives the grounded answer plus source citations in a predictable JSON response.
- The API uses the same per-project source filter, evidence-first/web-fallback rules, and multi-provider behavior as the web dashboard.
- Authenticate bot callers with revocable, project-scoped API credentials. A bot credential must not query another project by changing the project ID.
- Keep bot credentials server-side in the bot's secret configuration; never put them in a public web page, repository, or chat message.
- Document the base URL, authentication header, request/response schema, errors, and a Telegram/Discord integration example.
- Expose the API over HTTPS in a deployed environment. Localhost URLs are only for development and cannot be reached by hosted bots.

## 5. Acceptance checks

1. Upload at least two files together; verify each appears as its own source and is retrievable.
2. Add an admin-provided website URL; verify its imported content is retrievable and the answer cites that URL.
3. Ask about a fact in an uploaded file; verify the answer cites the filename.
4. Ask a question whose answer is absent from all project sources; with web fallback enabled, verify the answer cites web URLs; with it disabled, verify the AI abstains.
5. Verify web search is used only when enabled and that the answer identifies/cites web results rather than presenting them as uploaded sources.
6. Add a source to Project A and ask about its unique content from Project B; verify Project B does not reveal it.
7. Remove a source and verify it is no longer used in subsequent answers.
8. Enable at least two providers and verify they receive the same question and project-scoped evidence, then contribute to one cited final answer.
9. Make one provider unavailable and verify the UI clearly reports degraded/partial operation rather than claiming every provider contributed.
10. Import a Zomato page containing a known order fact; ask about that fact with “Zomato” in the question and verify only the Zomato source is passed to providers and cited in the result.
11. Ask about a fact absent from the imported Zomato page but available from general web search; verify the result is clearly labeled as web fallback and includes direct web citations.
12. Call the documented API using a credential scoped to Project A; verify it returns a source-cited answer from Project A.
13. Try that Project A credential against Project B; verify access is denied and no Project B data is returned.
14. Use the API from a Telegram or Discord bot and verify it produces the same project-scoped, cited behavior as the dashboard.
15. Ask a follow-up question in the same conversation and verify the bot responds naturally using the prior turn's context while staying grounded in the project's sources.

## 6. Open details to confirm

- Which file formats are required beyond `.txt` and `.md`?
- Should adding a website fetch only the entered page, or also follow links? The MVP default is only the explicitly entered URL.
- Is GitHub a required source type? If yes, does it need private repository support?
- What exact message and next action should appear when no source contains an answer?
- Which provider accounts/keys and model names should be supported first, and what API usage budget is allowed?
- When one provider fails, should the app deliver a clearly labeled partial answer or wait/error until all enabled providers respond?
- Should the final answer be synthesized by one designated provider, by deterministic code, or by another agreed method?
- Should the source filter automatically select a named source, or should the user also be able to choose a source before asking?
- What caller-authentication method and per-project credential management should the API provide (create, rotate, revoke)?
- Which bot platform should be the first live integration: Telegram or Discord?
- For cases the bot cannot resolve from the sources, should it simply explain that limitation, create a ticket, or notify an owner/on-call contact? The routine-support automation goal does not itself define exception handling.

## 7. Scope boundary

This note captures the latest clarified requirements: multi-source project knowledge ingestion, project-first answers with cited general web fallback, natural customer-care conversation, multiple AI providers contributing together, and a secure API for external bots. It does not authorize implementation of broader Bonfires capabilities such as knowledge graphs, background group-chat ingestion, or automatic site crawling.
