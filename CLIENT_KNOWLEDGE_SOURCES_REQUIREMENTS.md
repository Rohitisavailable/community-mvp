# Client Requirements: Knowledge Sources and Grounded Answers

**Status:** Point 1 implementation is in the working tree; runtime and acceptance checks have not been run.
**Reference product:** [Bonfires](https://www.bonfires.ai/) as inspiration for a unified knowledge-source experience. This is a focused MVP requirement, not a request to clone Bonfires.

## Business objective

Automate customer-care responses across the web dashboard and connected Telegram/Discord bots so the client does not need to retain a dedicated customer-care employee for routine questions. Answers must remain grounded in the client's configured sources. When those sources do not support an answer, the bot should clearly say it cannot answer from the available information instead of guessing or searching Google. Define separately what should happen for exceptional cases that still need a person or an operational action.

## Conversation style

The AI should chat naturally and warmly, like a helpful customer-care representative: understand follow-up questions, use the conversation context, and respond clearly without sounding like a rigid template. Do not add unsolicited AI disclaimers to ordinary replies. A natural tone must not weaken the source-only rule; unsupported details still require an honest “I couldn't find that in the available information” response. If a customer directly asks whether they are speaking to AI or a person, answer truthfully and do not impersonate a human employee.

## 1. Add knowledge sources to a project

Provide an admin-facing source area within each project. It should let the admin:

- Add a website link for the project’s knowledge base.
- Select and upload multiple files in one action.
- See the added sources with their filename or URL, source type, and processing status.
- Remove a source from the project.

Imported content must be indexed and stored within the selected project’s namespace. A source added to Project A must never appear in Project B’s retrieval results.

For the initial MVP, fetch the website URL explicitly provided by the admin. Whole-site crawling, private GitHub access, continuous sync, and other connectors are outside this requirement until separately approved. Confirm required file formats before promising anything beyond the existing `.txt` and `.md` support.

## 2. Answer only from the project’s sources

The AI must ground answers exclusively in successfully processed files and website pages added to the currently selected project.

- Do not use Google, general web search, or other unconfigured external search as an answer fallback.
- Do not fill gaps with unsupported model knowledge or guesses.
- Cite the source used: the filename for an uploaded file, or the imported URL for a website page.
- If the project’s sources do not contain the answer, say so plainly and invite the user to add the relevant source.
- Keep every retrieval scoped to the active project.

### Source filter between knowledge and results

Add a source-selection/filter step between the project's stored sources and the answer. The filter should choose only relevant, imported project sources before any AI provider receives context. If the question clearly names a source—for example, a Zomato page—and that source is available, restrict retrieval to that source. The answer must come from that Zomato page's imported content, not Google or general knowledge about Zomato. Show the source used on the result page. If the named source has no supporting information, abstain rather than switching to another website or external search.

For questions without a clear named source, search relevant sources within the active project only and show which sources supported the answer. An explicit source selector in the UI (for example, “All project sources” or one selected source) can make this behavior inspectable; the client has not specified whether that selector must be user-controlled or can be automatic.

## 3. Multiple AI providers working together

The client also wants multiple AI providers—such as Claude, Gemini, and GPT—to work together on answers, rather than offering only one model at a time.

- Add provider adapters so enabled providers can be called through a common interface.
- For each question, retrieve evidence once from the active project's sources, then give the same evidence and question to each enabled provider.
- Combine the providers' responses into one final answer. The combined answer must remain grounded only in the supplied project evidence and cite its source filenames/URLs.
- Do not allow a provider to use Google/general web search or unsupported outside knowledge as a fallback.
- Keep provider API keys server-side in environment variables or an equivalent secrets manager; never return or log their values in the dashboard.
- Show which providers are enabled and report provider failures clearly. Do not silently present one provider's output as a complete multi-provider result.

**Cost constraint:** The original MVP asks for a 100% free stack. Claude, Gemini, and GPT API access may have different pricing or free quotas, which can change. Confirm the allowed budget and provider credentials before enabling hosted providers; keep provider calls disabled until configured.

## 4. API for Telegram, Discord, and other bots

Provide a documented HTTPS API that lets an external bot use the same project knowledge Q&A as the web dashboard. A suitable initial shape is `POST /api/v1/projects/{project_id}/ask`; treat this as a proposed route name until the API contract is finalized.

- The caller sends a question and receives the grounded answer plus source citations in a predictable JSON response.
- The API uses the same per-project source filter, source-only answer rules, and multi-provider behavior as the web dashboard.
- Authenticate bot callers with revocable, project-scoped API credentials. A bot credential must not query another project by changing the project ID.
- Keep bot credentials server-side in the bot's secret configuration; never put them in a public web page, repository, or chat message.
- Document the base URL, authentication header, request/response schema, errors, and a Telegram/Discord integration example.
- Expose the API over HTTPS in a deployed environment. Localhost URLs are only for development and cannot be reached by hosted bots.

## 5. Acceptance checks

1. Upload at least two files together; verify each appears as its own source and is retrievable.
2. Add an admin-provided website URL; verify its imported content is retrievable and the answer cites that URL.
3. Ask about a fact in an uploaded file; verify the answer cites the filename.
4. Ask a question whose answer is absent from all project sources; verify the AI abstains instead of guessing or searching Google.
5. Verify answering does not issue Google or general external-search requests.
6. Add a source to Project A and ask about its unique content from Project B; verify Project B does not reveal it.
7. Remove a source and verify it is no longer used in subsequent answers.
8. Enable at least two providers and verify they receive the same question and project-scoped evidence, then contribute to one cited final answer.
9. Make one provider unavailable and verify the UI clearly reports degraded/partial operation rather than claiming every provider contributed.
10. Import a Zomato page containing a known order fact; ask about that fact with “Zomato” in the question and verify only the Zomato source is passed to providers and cited in the result.
11. Ask about a fact absent from the imported Zomato page but available from general web search; verify the app abstains and does not use Google or another source as a fallback.
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

This note captures the clarified requirements: multi-source project knowledge ingestion, source-only answers, natural customer-care conversation, multiple AI providers contributing together, and a secure API for external bots. It does not authorize implementation of broader Bonfires capabilities such as knowledge graphs, background group-chat ingestion, or automatic site crawling.
