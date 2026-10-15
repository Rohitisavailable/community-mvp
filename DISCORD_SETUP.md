# Add Community Desk to Discord

This integration uses Discord application commands. A server administrator connects a Discord server to a Community Desk project once with `/bind`; any member can then use `/ask question:...`.

## Configure the Discord application

1. Create an application in the [Discord Developer Portal](https://discord.com/developers/applications).
2. Under **General Information**, copy the **Application ID** and **Public Key**.
3. Under **Bot**, create/reset the bot token and copy it. Store it only in Render; never commit it or paste it into chat.
4. Under **Installation**, enable **Guild Install** and the `applications.commands` scope. Add the bot user with the `bot` scope if you want it to appear in the server member list. It does not need message-reading permissions; replies are sent through slash-command interactions.
5. Install the application to your Discord server using the Developer Portal's install link.

## Configure the deployed service

In Render, open the Community Desk service's **Environment** settings and add:

- `DISCORD_APPLICATION_ID` — Application ID
- `DISCORD_PUBLIC_KEY` — Public Key (hex string)
- `DISCORD_BOT_TOKEN` — bot token

Set the Discord **Interactions Endpoint URL** to:

```text
https://community-desk.onrender.com/discord/interactions
```

Save the Discord application settings and redeploy Community Desk after setting the Render variables. On startup, the app registers `/ask` and `/bind` with Discord. Discord verifies requests using the application's public key.

## Bind and try it

1. In your Discord server, a server administrator runs `/bind project:<project-slug>`. Use the slug shown in the Community Desk dashboard, such as `community-axon`.
2. Any member can run `/ask question:<your question>`.

The answer is scoped to that project's imported sources and includes source references when available. The binding is per Discord server. A server admin can switch its project by running `/bind` again.

## Troubleshooting

- If Discord says the endpoint is invalid, confirm the endpoint URL is HTTPS, the Render service is awake, and `DISCORD_PUBLIC_KEY` exactly matches the Developer Portal's Public Key.
- If `/ask` or `/bind` does not appear, check Render logs for command-registration errors and confirm `DISCORD_APPLICATION_ID` and `DISCORD_BOT_TOKEN` are set, then redeploy.
- If `/bind` says the project was not found, use the exact project slug displayed in Community Desk.
- If `/ask` reports no supported information, import the relevant file or website into that project first.
