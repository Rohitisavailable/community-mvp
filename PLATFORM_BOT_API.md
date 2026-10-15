# Connect another platform bot

Community Desk exposes an authenticated, project-scoped HTTPS answer endpoint. It can be called by a bot adapter running on any platform that can make outbound HTTPS requests. The platform adapter still needs to receive that platform's events and send the returned answer back to its chat.

## Create a project API key

Generate a long random key (at least 32 random bytes) and configure Render's `COMMUNITY_BOT_API_KEYS` environment variable as a JSON object mapping each key to a project slug:

```json
{"YOUR_LONG_RANDOM_KEY":"community-axon"}
```

Keep the key in the adapter's server-side secret store. Never put it in browser JavaScript, a public repository, a chat message, or a client-side app. To revoke a key, remove its mapping in Render and redeploy. Multiple keys can map to different projects.

## Request

```http
POST https://community-desk.onrender.com/api/v1/ask
Authorization: Bearer YOUR_LONG_RANDOM_KEY
Content-Type: application/json
```

```json
{
  "question": "What does the project document say about delivery?",
  "integration_id": "my-platform",
  "conversation_id": "server-channel-user"
}
```

`question` is required (2–5,000 characters). `integration_id` and `conversation_id` are optional and keep answer context separate by platform/conversation. The response is JSON with `answer`, `sources`, and `backend` fields. The adapter should send the `answer` field to its platform chat and may show `sources` as citations.

## PowerShell example

```powershell
$headers = @{
  Authorization = "Bearer $env:COMMUNITY_BOT_API_KEY"
  "Content-Type" = "application/json"
}
$body = @{
  question = "What does the project document say about delivery?"
  integration_id = "my-platform"
  conversation_id = "server-channel-user"
} | ConvertTo-Json
Invoke-RestMethod -Method Post `
  -Uri "https://community-desk.onrender.com/api/v1/ask" `
  -Headers $headers -Body $body
```

The API key belongs in the calling bot's server-side environment, not in this dashboard's public frontend. Calls use only the project associated with that key. A platform-specific adapter is still needed to handle incoming messages, decide when to call `/api/v1/ask`, and deliver the response.
