# Private Proton Calendar assistant

Private ChatGPT plugin for reading and managing Proton Calendar from natural language. The Docker adapter runs as a TrueNAS App while your computer is off. It does not call OpenAI’s paid API; no OpenAI API key is needed.

The current flow is: **ChatGPT on your Pixel → private Site-hosted MCP plugin → authenticated public HTTPS endpoint on your NAS → Docker adapter → experimental Carbonate bridge → Proton Calendar**. Use the installed plugin from an ordinary ChatGPT chat. You do not need to create a custom GPT.

For your intended TrueNAS installation, start with [Install via YAML](truenas/README.md). The YAML embeds the image build, storage initialization and login setup, so normal installation needs no SSH or manually prepared files. Set the environment values in TrueNAS Apps; Proton challenges may need the browser-based container Shell. Sections 1–3 below document the optional shell Compose installation and networking details; do not run that stack alongside the TrueNAS App.

**Status:** private development release; the completion target is not yet met. ChatGPT now lists calendars, searches events and reads event details after reconnecting the plugin. Live adapter checks verified timed/all-day creation and rescheduling, device-reminder read-back, weekly recurrence across DST, and deletion of individual events and whole series. Editing a single recurring occurrence remains unverified. Adapter 0.2.2 advances exception sequences and adds safe failure diagnostics; deployment and live occurrence checks are pending. See [ACCEPTANCE.md](ACCEPTANCE.md). Carbonate uses an unsupported private Proton API and may break. Its pinned commit is `baa9818402e980208ac0041ea6544f3d4683d29d`.

## 1. Optional shell Compose installation: prepare on TrueNAS

Copy this folder into a dedicated dataset, for example `/mnt/POOL/apps/proton-calendar-gpt`. Replace `POOL` with your pool name in all commands. Use the TrueNAS shell or SSH; don't install Python packages on the NAS host. `setup.py` uses only Python's standard library.

```sh
cd /mnt/POOL/apps/proton-calendar-gpt
sudo python3 setup.py
sudo docker compose build
```

The adapter runs as UID/GID 10001. If dataset ACLs block it, grant that identity access to this dedicated dataset. Preserve the permissions set by setup. Never use a shared world-readable dataset for the session or secrets. Nothing here needs the Docker socket mounted into a container.

Builds use pinned Carbonate source and Python package versions. Container base tags follow their maintenance lines. Production operators can pin image digests after validating an update. Run exactly one adapter instance/worker for this session.

## 2. Log into Proton on the NAS

Do this before starting the web adapter:

```sh
sudo docker compose run --rm --no-deps calendar carbonate auth YOUR_PROTON_USERNAME -session /data/auth.json
```

Enter your Proton password and second factor interactively **in this terminal**, never in ChatGPT. Human verification, if requested by Proton, may require additional manual steps. The bridge prints a new bridge password once. Store it in your password manager and use a local editor to replace the empty `secrets/bridge_password` file with that password. Keep ownership 10001:10001 and mode 600. This is different from your Proton password and the Action API key.

The default works when your account has exactly one calendar. With multiple calendars run the command below and set `PROTON_CALENDAR_ID` in `.env` to the intended calendar's printed ID. Our image adds machine-readable calendar and targeted event reads to the pinned bridge. It preserves the upstream Proton authentication and event-write implementation. Without an ID, the bridge refuses writes to accounts with multiple calendars. For an isolated trial, you can use a separate Proton account with disposable test events.

```sh
sudo docker compose run --rm --no-deps calendar carbonate calendars -session /data/auth.json
```

Your session and locally queued event details are retained in `data/`. NAS administrators and software with access to the bridge secrets can access decrypted calendar information. Backups of this dataset also contain sensitive data. The adapter does not expose email or contacts through the plugin, but the underlying Proton session is broader than a narrowly scoped official calendar token.

## 3. Choose one HTTPS connection

The hosted plugin calls your NAS from the cloud, not from your phone’s Tailscale connection. A private `100.x` address or private Tailscale Serve URL will not work for this connection. The endpoint needs public HTTPS on port 443 with a valid certificate.

### A. DDNS with a reverse proxy

Edit `.env`:

```dotenv
PUBLIC_URL=https://your-ddns-host.example
CALENDAR_DOMAIN=your-ddns-host.example
```

The hostname must resolve to your reachable public IP. Check that your ISP permits inbound connections and you are not behind carrier-grade NAT. If an AAAA record exists, IPv6 routing must work too. Forward router TCP **80 → NAS port 10080** and **443 → NAS port 10443**. Caddy obtains and renews a free publicly trusted certificate automatically; there is no certificate purchase or manual installation step. The hosted plugin uses the normal external HTTPS port 443.

**If you already run a reverse proxy, use it instead:** proxy this hostname to the calendar container's port 8000 over its Docker network, or to `127.0.0.1:8787` from a host-based proxy. A proxy in another container cannot reach the host using its own `127.0.0.1`; join its network or configure an explicit reachable host address. Keep the TrueNAS management interface on a separate route/port. The bundled Caddy configuration maps only this calendar service.

The included Caddy container binds host ports 10080/10443 to avoid conflicting with TrueNAS's usual management ports. Confirm those two ports are free. Configure port forwarding specifically to these proxy ports, not to the management interface.

```sh
sudo docker compose -f compose.yaml -f compose.ddns.yaml up -d
```

If using an existing proxy, run `sudo docker compose up -d` instead and configure that proxy separately.

### B. Tailscale Funnel, no router port forwarding

Use `compose.funnel.yaml` instead of the files above. This creates a separate Tailscale node named `proton-calendar`, not a public route to the NAS's existing Tailscale node.

Create a non-ephemeral Tailscale auth key for this node and save `TS_AUTHKEY=YOUR_KEY` in `secrets/tailscale.env` (root-owned mode 600). Enable MagicDNS, HTTPS certificates and Funnel permission for this node in your tailnet policy using Tailscale's documented setup. The container uses userspace networking, with no privileged mode or host network.

```sh
sudo docker compose -f compose.funnel.yaml up -d tailscale
sudo docker compose -f compose.funnel.yaml exec tailscale tailscale status
```

Use the node's actual assigned `proton-calendar.YOUR_TAILNET.ts.net` hostname. Set `PUBLIC_URL=https://THAT_HOSTNAME` in `.env`, then:

```sh
sudo docker compose -f compose.funnel.yaml up -d calendar
sudo docker compose -f compose.funnel.yaml exec tailscale tailscale funnel status
```

The Funnel configuration is under `tailscale/serve.json`. It publishes the calendar service only. The adapter API key (stored in `secrets/action_api_key`) protects all calendar operations; `/healthz` and the API schema are public and contain no secrets or events. Test from a phone with Tailscale disabled to confirm public reachability. Node expiry and reauthentication still need attention: keep Tailscale state persistent and review the node's key-expiry setting.

### TrueNAS Apps: Install via YAML

For a TrueNAS-managed App, follow [the Apps YAML guide](truenas/README.md). Paste one standalone configuration into **Apps → Discover Apps → ⋮ → Install via YAML**:

- [Tailscale Funnel](truenas/funnel.yaml)
- [DDNS with Caddy](truenas/ddns.yaml)
- [Existing reverse proxy](truenas/existing-proxy.yaml)

These files contain the source build and routing configuration, use persistent Docker volumes, and accept environment settings directly in YAML. No prebuilt image or dataset-path replacement is needed. Set the public hostname, private adapter key and login settings, then manage the service through TrueNAS Apps. Run one instance of the adapter, managed by either TrueNAS Apps or shell Compose.

## 4. Connect the private ChatGPT plugin

A custom GPT is not required. Install **My Proton Calendar** from the Plugins directory and connect it when prompted. Start a new ordinary ChatGPT chat and invoke the plugin by name or with `@` where available. For example: “Use My Proton Calendar to add school tomorrow at 9:45.” Supported plugins can be used on mobile; the complete flow still needs testing on your Pixel with your account.

The published plugin uses the Site-hosted MCP endpoint; do not paste the NAS OpenAPI schema into the GPT editor for this route. After deploying the NAS App:

1. Set `PROTON_ADAPTER_URL` in the private Site’s runtime settings to the NAS adapter’s public HTTPS origin.
2. Set `PROTON_ACTION_API_KEY` as a **secret**, using `ACTION_API_KEY` from the App YAML (or `secrets/action_api_key` for shell Compose). Enter it directly in secure settings, never chat or source.
3. Redeploy the Site’s existing saved version to activate the runtime settings.
4. Install/connect the generated private plugin in ChatGPT, and ask it to check the calendar connection.

Sites handles OAuth between ChatGPT and the hosted plugin. The hosted plugin calls the NAS adapter using its secret API key. The Proton session and bridge password stay on the NAS. Keep both the Site and its plugin owner-private because this service uses one Proton account. See [plugin setup](calendar-plugin/README.md) for the complete connection instructions.

The [original custom GPT Action setup](custom-gpt-alternative.md) remains an optional alternative. Its confirmation flags apply only to that route; plugin actions follow the host’s permission controls.

## 5. Verify before everyday use

1. Ask the connected plugin to run `getIntegrationStatus`, then `getCalendarContext`. It should report a reachable connection, configured Proton login, Europe/Helsinki and the correct current local time.
2. Ask for a disposable test event with an explicit date, start and end time.
3. Confirm its status reaches `verified` and inspect it in the official Proton Calendar Android app. Delete the test manually.
4. Ask "I have school tomorrow at 9:45". The default duration is 60 minutes, so the proposed event ends at 10:45. Change `DEFAULT_DURATION_MINUTES` to your preference.
5. Test repeating the exact request: it should reuse the same job rather than create a duplicate. Test a winter date and a daylight-saving transition; ChatGPT should use the event date’s timezone offset and clarify ambiguous times.

The API queues writes and returns promptly. A single background worker continues after the chat turn. The plugin exposes job status so ChatGPT can check the same job without resubmitting the event. `verified` means the bridge wrote an event and then read back matching UID, title, dates, location and description from Proton, including recurrence and device reminders when present. `pending`/`writing` mean it hasn't finished. `unknown` means it could already be saved: use `verifyEventWrite` for read-only reconciliation or inspect Proton manually; the adapter deliberately doesn't blindly repeat uncertain writes.

Identical normalized requests reuse a durable job forever, including after restart. If you manually delete a verified event, repeating that identical request reports its original verified job; it does not recreate it or prove it still exists. This version has no job reset/retry UI. Never delete the database just to retry an uncertain write without checking the calendar first.

## Calendar operations in v0.2

The updated adapter and plugin support:

- List calendars, read event/series details, search title/description/location, and list occurrences within up to 366 days. Read one calendar per request and use pagination for large results.
- Create timed or all-day events; all-day end dates are exclusive. Timed dates require explicit UTC offsets.
- Edit/reschedule or delete an individual event after reading its current revision. Unspecified fields, existing reminders and provider properties are preserved.
- Daily, weekly, monthly and yearly recurrence with interval, optional count or end time, and optional weekdays. Timed series require an IANA timezone such as `Europe/Helsinki`, retaining local time across DST. All-day series use count rather than until.
- Edit a series or one occurrence, and cancel a selected occurrence without deleting the series. Occurrence changes use the original recurrence ID even after rescheduling. Rescheduling a series that already has exceptions requires manual review in Proton.
- Add, replace, remove and read up to five device reminders, expressed as minutes before start (0–10080). An empty list removes reminders. Existing email reminders are preserved during unrelated edits; this version creates device reminders only. Device notification delivery depends on Proton and the device and is not proven by a saved alarm.

Read and mutation requests use a durable background queue so the chat connection does not time out while the bridge decrypts a calendar. Poll `getCalendarOperationStatus`: `ready` contains the result, `failed` is a pre-write failure, and `unknown` requires inspection before further mutations. Only `result.verified: true` confirms an edit/delete read-back. Mutations with the same input and revision reuse the original operation. New reads always obtain fresh data.

Before editing, use `getCalendarEvent` to obtain the UID, calendar ID and current revision. A stale revision rejects the mutation. Specify `event`, `series` or `occurrence` explicitly; the assistant should clarify ambiguous scope. Attendee events and events with unverifiable signatures remain read-only. This is not an official Proton integration or a claim of complete Google Calendar feature parity. Invitations and calendar sharing are outside this release.

See [the live acceptance checklist](ACCEPTANCE.md) and [completion target](ROADMAP.md). Keep Test 2 unchanged during testing.

## Maintenance and removal

Before logging in again, stop the adapter. Use `carbonate auth ... -keep-bridge-password` with the same session path to retain your bridge password. Start the adapter again afterwards. Its entrypoint loads that password from the secret file for CLI commands too.

Inspect container startup logs for configuration errors. To troubleshoot a Proton login locally, stop the adapter and run `sudo docker compose run --rm --no-deps calendar carbonate calendars -session /data/auth.json`. This command displays private calendar names. The web adapter returns generic upstream errors rather than exposing Proton error output or credentials.

To remove, stop the TrueNAS App or chosen Compose stack, disconnect/uninstall the plugin (or remove the optional custom GPT/Action), revoke the bridge's Proton session, and disable Funnel or remove the reverse-proxy route. Keep or securely remove `data/` and `secrets/` according to your backup policy. Deleting containers alone does not delete bind-mounted credentials.

## Local developer tests

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

Tests cover authorization, input validation, UTC normalization, iCalendar escaping, duplicate prevention, queue limits, uncertain writes and read-back verification using a fake bridge. They do not prove Carbonate can log in or save events to your real account.

## References

- [ChatGPT plugins and mobile support](https://learn.chatgpt.com/docs/plugins)
- [MCP plugin authentication](https://developers.openai.com/plugins/build/auth)

- [GPT Actions](https://developers.openai.com/api/docs/actions/introduction)
- [Action authentication](https://developers.openai.com/api/docs/actions/authentication)
- [HTTPS, timeouts and confirmation controls](https://developers.openai.com/api/docs/actions/production)
- [Carbonate source and limitations](https://github.com/develonrails/carbonate)
- [Tailscale Funnel](https://tailscale.com/docs/features/tailscale-funnel)
- [Tailscale Docker configuration](https://tailscale.com/docs/features/containers/docker/docker-params)
- [TrueNAS custom Apps](https://www.truenas.com/docs/scale/apps/installcustomappscreens/)
- [Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https)
- [Let's Encrypt](https://letsencrypt.org/getting-started/)
