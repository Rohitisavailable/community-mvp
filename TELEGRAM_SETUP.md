# Telegram support bot setup

Community Desk can serve Telegram questions through a webhook. Each Telegram chat is bound to exactly one project. The bot prefers that project's imported files and pages, then may use Backboard web search when configured and the sources do not answer. It shows Telegram's `typing` indicator while the model works and uses the same natural response path as the dashboard.

## Configure the hosted bot

1. Create a bot with Telegram's [BotFather](https://t.me/BotFather). Keep its token private. **Use a separate bot token from the one running your Hermes gateway.** This integration uses a webhook; Telegram does not let the same bot token use webhook delivery and Hermes' long polling at the same time.
2. In Render, add these environment variables to the `community-desk` web service:
   - `TELEGRAM_BOT_TOKEN`: the BotFather token.
   - `TELEGRAM_WEBHOOK_SECRET`: a random 32+ character value using letters, numbers, `_` or `-`.
   - `TELEGRAM_ADMIN_USER_IDS`: initially leave blank; fill this in after the bot can answer `/myid`.
   - `WEB_SEARCH_ENABLED=true`: enables Backboard web search when the bound project's sources don't contain the answer. The app still prioritizes the project's imported sources and should label/cite web results. This requires `AI_PROVIDER=backboard` and valid Backboard credentials/model settings; local Ollama/Hermes modes do not have web search.
3. Deploy the current app version. The public webhook endpoint is `https://community-desk.onrender.com/telegram/webhook`.
4. Set the webhook from PowerShell. These prompts keep the token and secret out of the command text:

   ```powershell
   $botToken = Read-Host "BotFather token"
   $webhookSecret = Read-Host "TELEGRAM_WEBHOOK_SECRET value from Render"
   $body = @{
     url = "https://community-desk.onrender.com/telegram/webhook"
     secret_token = $webhookSecret
     allowed_updates = @("message", "edited_message")
   } | ConvertTo-Json -Compress
   Invoke-RestMethod -Method Post -Uri "https://api.telegram.org/bot$botToken/setWebhook" -ContentType "application/json" -Body $body
   Remove-Variable botToken, webhookSecret, body
   ```

   A successful response contains `"ok": true`. You can inspect webhook health with Telegram's `getWebhookInfo` method; never paste its URL/token into a public issue or chat.
5. Open a private chat with the bot and send `/start`, then `/myid`. Add the numeric ID it returns to Render's `TELEGRAM_ADMIN_USER_IDS`. For multiple admins, separate IDs with commas. Redeploy after changing the value.
6. Add the bot to a Telegram group (public or private). In the group, connect it to a project by sending `/bind@YourBotUsername project-slug` as a configured admin. Use the slug shown in the dashboard. One group can be bound to one project; another group can be bound to another project.
7. Any member can ask in the bound group by sending a normal text message; `/ask` remains available too. In a private chat, send the question normally. For current news, a short topic by itself (for example, `AxonDAO`) is treated as a request for recent public updates. Answers prioritize the bound project's sources; if they do not answer, configured web search may look for dated official website and publicly accessible social updates, with citations. Private or login-restricted social posts are not accessible through this search path.

## Auto-post RSS updates to a Telegram channel

1. In Telegram, add this bot to the target channel as an administrator and grant it permission to post messages. For a public channel, you can use its `@username`; for a private channel, use its numeric channel ID (usually starts with `-100`).
2. In the Community Desk dashboard, select the project, then use **RSS auto-posting** to enter the public HTTPS RSS/Atom feed URL and channel. Optionally add comma-separated keywords; an item is sent if any keyword appears in its title, summary, or category.
3. The app validates the feed before saving. It records the current entries as already seen, then posts later entries at most once, oldest first, with a title, short excerpt, and link. Failed posts are retried. Remove the feed from the same panel to stop monitoring it.

The app checks feeds about every five minutes while its web process is running. Render's free web service can sleep when idle, so polling and posts can be delayed until the service wakes. Use an always-on paid service or a scheduled worker for dependable publishing; this setup does not create paid Render resources automatically.

## Add and manage sources in Telegram

- A configured admin can send a `.txt` or `.md` document into a bound group or private chat. Files must be UTF-8 text and under 1 MB. The bot confirms which project received the source.
- A configured admin can add one public page with `/source https://example.com/page`. Only the exact HTTPS page is imported; the importer does not crawl linked pages.
- Remove sources from the project's dashboard, which keeps source removal behavior consistent across web and Telegram.
- `/unbind` disconnects a chat; only a configured Telegram admin can bind or unbind it.

## Groups, channels, and identity

In bound groups, every ordinary text message is treated as a question; this can make the bot answer regular conversation too. `/ask` is also available to all members. Only `/bind`, `/unbind`, and source management require a configured admin. To receive ordinary group messages, make the bot an administrator or disable its Group Privacy Mode with `/setprivacy` in @BotFather, then remove and re-add it to the group for the setting to take effect. Telegram enables privacy mode by default for bots that are not group admins. The bot must be invited to private groups by a member with permission to add it.

A channel is a broadcast surface and does not provide ordinary member-to-bot conversations. To support questions for a channel audience, link a discussion group, add the bot to that group, and bind the discussion group to the project. For RSS publishing, the bot can be made a channel administrator with permission to post; see the auto-post setup above.

The bot uses Telegram's visible typing indicator and a natural support tone. It does not impersonate a human and will identify itself truthfully if asked. Response speed depends on the configured model/provider and its availability; web search adds latency. The webhook acknowledges Telegram promptly and continues processing in the background, but Render restarts can interrupt an in-flight reply.

## Local development

Set the three Telegram variables in the ignored `.env` file and configure a public HTTPS tunnel URL as the webhook. Telegram cannot deliver webhooks to `localhost`. Telegram allows one active webhook URL per bot token, and webhook delivery cannot run alongside `getUpdates` long polling.
