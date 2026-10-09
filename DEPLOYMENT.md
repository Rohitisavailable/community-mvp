# Public prototype deployment

This guide deploys the Admin-only Community Desk dashboard to Render and stores its data in Supabase Postgres. The app serves the page over HTTPS through Render. Admin login is required for all project data, uploads, and chat routes.

## What runs where

- **Render Free web service:** Flask + Waitress app. Its local filesystem is temporary, so the app must not store hosted data there.
- **Supabase Postgres:** project records, uploaded text, chat history, and Admin password hash. The app creates a private `community_desk` schema on first startup.
- **Hermes and Ollama:** remain local to your Windows computer. A cloud Render process cannot call your PC's `127.0.0.1` services. Hosted mode therefore defaults to `AI_ENABLED=false` and answers with project-scoped matching excerpts. The app now also supports Backboard for hosted inference. To enable it, configure the Backboard environment variables below; do not expose the PC's Ollama or Hermes listener directly to the public internet.

Render Free services have an ephemeral filesystem and can spin down when idle; Supabase Free is suitable for a prototype but has plan limits and may pause inactive projects. Check each provider's current terms before relying on it for a live service: [Render free services](https://render.com/docs/free), [Supabase pricing](https://supabase.com/pricing).

## 1. Put this app in a Git repository

Create a private GitHub repository and add the contents of this `community-mvp` folder. Do not include `.env`, `.venv`, `data/`, Hermes profile files, or bot tokens. The included `.gitignore` excludes the local environment and data folders. Keep repository history free of secrets.

## 2. Create the Supabase database

1. Create a Supabase project on the free plan.
2. Open **Connect** in the Supabase dashboard and copy the **Session pooler** connection string for the `postgres` user. Use the session pooler because Render's free service may not have IPv6 connectivity for Supabase's direct endpoint. Do not use the transaction pooler for this prototype.
3. Keep that string private. It is supplied as `DATABASE_URL` in Render, never committed to the repository or placed in browser code.

See [Supabase connection options](https://supabase.com/docs/guides/database/connecting-to-postgres) for the current connection-string instructions.

## 3. Create the Render service

1. In Render, choose **New → Blueprint** and connect the GitHub repository.
2. Select the repository branch containing `render.yaml`. The Blueprint creates a free web service named `community-desk` and prompts for the `sync: false` values.
3. Enter:
   - `ADMIN_EMAIL`: the Admin email to use for this deployment.
   - `ADMIN_PASSWORD`: a unique password with at least 14 characters.
   - `DATABASE_URL`: the Supabase Session pooler string from step 2.
   - `COMMUNITY_BACKBOARD_API_KEY`: your Backboard API key. Render stores this as a private environment value.
   - `BACKBOARD_LLM_PROVIDER` and `BACKBOARD_MODEL_NAME`: the provider name and exact model ID selected in Backboard. Both are required so the app won't silently use Backboard's default model.
4. Render generates `APP_SECRET_KEY`; keep the generated value private. Confirm the remaining Blueprint values and deploy.
5. Wait for `/healthz` to pass, then open the service's `onrender.com` URL and sign in.

After the first deploy, open the Render service's **Environment** settings and change `AI_ENABLED` to `true`, then redeploy. `AI_PROVIDER` is set to `backboard` in the Blueprint. The key, provider, and model name are read only by the server; never put them in browser code or commit them to `.env`.

When Backboard is selected, Community Desk first retrieves excerpts from the active project's database and sends only those excerpts, the question, and that project's scoped prompt to Backboard. A separate Backboard thread ID is stored for each project and chat session; Backboard memory and web search are disabled on each request. This still means the question and matched document excerpts leave your hosting provider and are processed by Backboard and its selected model provider. Check the provider's current pricing and data policy before using private content.

On first boot, the app creates its tables and inserts the initial Admin if the database has none. It does not seed demo projects in hosted mode. Create projects and upload only text that is appropriate to store in the connected Supabase project.

## 4. Verify the deployed prototype

- Open `/healthz`; it should return `{"ok":true,"storage":"postgres"}`.
- Sign in with the Render Admin credentials.
- Create Project A and Project B, upload a different uniquely named `.txt` file to each, and ask a question whose answer exists only in each file.
- Switch projects and ask for the other project's unique fact. The app scopes database search by project slug and should not return that fact.
- Sign out and confirm the project API requires login.

The app protects admin routes and uploaded knowledge behind the Admin login. This is not yet a public visitor-facing Q&A site. Public visitors cannot ask project questions until a deliberate public-project/access model is designed.

## Local mode

For Windows localhost use, omit `DATABASE_URL` and the app uses its existing per-project SQLite files. Follow the local setup in [README.md](README.md). Do not set `APP_ENV=production` when testing over plain `http://127.0.0.1`; production cookies are marked Secure and require HTTPS.

## Prototype limits

- One Admin login; no invitations, password reset, roles, audit trail, or billing.
- Hosted inference is off by default. Local Windows Hermes/Ollama is not automatically reachable from Render.
- Uploaded documents are plain text only (`.txt` and `.md`, up to 1 MB each).
- No automatic migration of existing local SQLite data to Supabase; existing local data remains on the PC unless separately migrated.
- Free hosting can sleep, pause, or change its limits. This configuration is for evaluation, not a high-availability production service.
