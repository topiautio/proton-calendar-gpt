# My Proton Calendar plugin

Private Site-hosted MCP tools for the sibling TrueNAS adapter. Sites supplies OAuth and restricts access to the owner; keep both this Site and its generated plugin private because every tool uses one Proton account.

## Finish connecting the NAS

1. Deploy the original project on TrueNAS, following `../README.md`. Complete Proton authentication in the NAS terminal and expose only the adapter through public HTTPS (DDNS/Caddy or Tailscale Funnel).
2. In this Site's runtime environment settings, set `PROTON_ADAPTER_URL` to the adapter's HTTPS origin (no path, query, embedded credentials or fragment). It is a different URL from this Site.
3. Set `PROTON_ACTION_API_KEY` as a **secret**, using the value of the NAS's `secrets/action_api_key`. Enter it directly in the secure settings, never chat or source. Proton and bridge passwords remain on the NAS.
4. Redeploy this Site's existing saved version to apply the runtime environment revision. Updating variables alone does not activate them.
5. Install/connect the Site's generated private plugin in ChatGPT. Run `getIntegrationStatus`, then `getCalendarContext`. Create one disposable test event and confirm its job reaches `verified` and appears in the official Proton Calendar app. Delete it manually.

The server exposes `getIntegrationStatus`, `getCalendarContext`, `createCalendarEvent` and `getEventStatus` at `/mcp`. Calls require a Sites-authenticated user. It sends the NAS key only to the configured HTTPS origin, follows no redirects, limits request size and never returns raw upstream errors. It does not call the OpenAI API.

An omitted end time uses the NAS's default duration. Writes reuse the existing durable queue and read-back verification. `pending` and `writing` mean queued; `unknown` requires manual checking. A verified job proves the original write, not that a later-deleted event still exists. The unsupported Carbonate bridge still requires a live account test.

## Development

```sh
npm install
node --test tests/calendar-mcp.test.mjs
npx tsc --noEmit
npm run build
```

Publish updates using the Sites workflow, keeping `.openai/hosting.json`'s existing project ID and generated plugin identity. Do not upload a second standalone plugin for this Site.
