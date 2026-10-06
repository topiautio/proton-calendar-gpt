# Install entirely through TrueNAS Apps YAML

**No SSH or NAS host shell is required for the normal setup.** Paste one of these self-contained files into **Apps → Discover Apps → ⋮ → Install via YAML**, name the App `proton-calendar`, and set its environment values. TrueNAS builds the embedded source, initializes its Docker volumes and starts the service. No source upload, prebuilt local image, `.env` file or manually created secret files are needed.

The checked NAS runs TrueNAS 25.10.7 and Docker Compose 2.38.1. Inline Dockerfiles require Compose 2.17 or newer. The initial build needs internet access and takes longer than downloading a ready-made image.

| File | Connection |
| --- | --- |
| `funnel.yaml` | Tailscale Funnel; no router forwarding |
| `ddns.yaml` | DDNS and Caddy; forward external TCP 80 to NAS 10080 and TCP 443 to NAS 10443 |
| `existing-proxy.yaml` | Your existing reverse proxy; adapter bound to NAS loopback port 8787 |

## Set values in the YAML

Leave the long `build/dockerfile_inline` source block intact. Edit the `calendar` service's `environment` block:

| Setting | Value |
| --- | --- |
| `PUBLIC_URL` | Your NAS adapter's public HTTPS origin, for example `https://calendar.your-domain.example` |
| `ACTION_API_KEY` | A private random key of at least 32 characters; create one with your password manager |
| `PROTON_USERNAME` | Your Proton username |
| `PROTON_PASSWORD` | Your Proton login password, needed only for initial login |
| `PROTON_TWO_FACTOR_CODE` | Leave empty initially; if required, enter a fresh 2FA code after the image build finishes |
| `PROTON_MAILBOX_PASSWORD` | Leave empty unless the Proton account uses a separate mailbox password |
| `PROTON_LOGIN_ATTEMPT` | `1` initially; increase it each time you deliberately request another login attempt |
| `PROTON_CALENDAR_ID` | Empty for a single-calendar account; otherwise your intended calendar ID |
| `CALENDAR_TIMEZONE` | `Europe/Helsinki` by default |
| `DEFAULT_DURATION_MINUTES` | `60` by default |

Quote environment values containing YAML punctuation. Compose treats `$` specially even in quoted values: write `$$` for each literal dollar sign in passwords/keys. Do not send passwords or keys in chat. Environment credentials remain visible to administrators through the saved App configuration; remove the Proton password, code and mailbox password from the YAML after login succeeds. Keep the adapter API key configured for ongoing requests.

For **DDNS**, also set the Caddy service's `CALENDAR_DOMAIN` to that hostname without `https://` and configure DNS/port forwarding. For **Funnel**, set `TS_AUTHKEY` in the `tailscale` service's environment. Use a dedicated non-ephemeral Tailscale auth key and enable MagicDNS, HTTPS and Funnel permission. This App creates its own node, separate from your existing TrueNAS Tailscale App. The routing configuration is embedded in the YAML.

If you do not yet know the assigned Funnel hostname, save with the placeholder `PUBLIC_URL`, then find the node in the Tailscale admin console and edit `PUBLIC_URL` to its actual `https://HOSTNAME`. The App's tailscale container Shell can also show it with `tailscale status`; SSH is not needed.

### Verify public Funnel access

The `.ts.net` hostname and a valid TLS certificate alone do not prove public access. A device connected to Tailscale can reach the private address even when the hosted ChatGPT plugin cannot.

Open the App's **tailscale container Shell** in the TrueNAS web UI and run this read-only check:

```sh
tailscale funnel status
```

If Funnel permission is missing, open **Tailscale admin console → Access controls → Funnel → Add Funnel to policy**. Ensure the policy permits this App's node; a tagged node needs a matching policy target. Preserve the rest of your existing policy. The YAML configures the forwarding route, but cannot grant permission in your Tailscale account.

If the route is not enabled, run the following in that same container Shell and complete any Tailscale approval link it displays:

```sh
tailscale funnel --bg http://127.0.0.1:8000
```

Allow up to 10 minutes for public DNS publication, then check `https://YOUR_PUBLIC_HOST/healthz` on a phone using mobile data **with Tailscale disconnected on that phone**. It should return `{"status":"ok"}`. Home-network access or a successful check over Tailscale does not verify the hosted plugin's access. See [Tailscale Funnel requirements and troubleshooting](https://tailscale.com/docs/features/tailscale-funnel).

## Proton login and 2FA

Startup generates a private bridge password inside the persistent calendar volume, then uses Carbonate's supported stdin login mode. The Proton session is retained across restarts. An existing session is reused; passwords are not used for every calendar write.

Each `PROTON_LOGIN_ATTEMPT` value permits at most one automatic attempt. A failed attempt does not create a restart/login loop; the adapter remains available and reports `login_configured: false` until login succeeds. Logs show a generic result without passwords, session tokens or raw Proton login output.

For 2FA, wait until the first build is finished, edit the YAML with a fresh code and increment `PROTON_LOGIN_ATTEMPT`, then save again. Remove the login credentials/code once the logs report `Proton session configured.`

Proton may require a browser human-verification challenge that cannot be completed by a static YAML value. For this case, open the **calendar container's Shell in the TrueNAS web UI** and run:

```sh
python /app/bootstrap.py --interactive-login
```

Complete Proton's prompts there. This helper refuses to replace an existing session. It reuses the generated bridge password, so there is no password-file copying step. If the account has multiple calendars, use that same browser container Shell to run `carbonate calendars -session /data/auth.json` and set the intended ID in the YAML.

## Connect the ChatGPT plugin

1. Check the App logs and verify `https://YOUR_PUBLIC_HOST/healthz` from outside your home network with Tailscale disconnected on the testing device. This health check verifies the adapter, not Proton login.
2. Set `PROTON_ADAPTER_URL` in the private hosted plugin's runtime settings to your NAS adapter's HTTPS origin. Set `PROTON_ACTION_API_KEY` as a secret to the same key used in the App YAML. Redeploy the plugin's saved version to apply the settings.
3. Install/connect the private My Proton Calendar plugin in ChatGPT and run `getIntegrationStatus` and `getCalendarContext`.
4. Create a disposable appointment and confirm the job reaches `verified` and the event appears in the official Proton Calendar app. Delete it manually.

Keep this App as the only adapter for the Proton session. Use TrueNAS Apps for its lifecycle; do not also start the earlier shell Compose stack. The calendar session, generated bridge secret and event queue are stored in the App's `calendar_data` Docker volume; preserve it during upgrades and plan its backup. Removing it loses this state and duplicate prevention history. Do not clear it merely to retry an uncertain write.

## Developer notes

`generate-yaml.py` embeds the backend source and configuration into all three files. Regenerate after changing `app.py`, `bootstrap.py`, requirements, the Dockerfile, CLI patch or routing configuration:

```sh
python3 truenas/generate-yaml.py
```

The YAML configurations and bootstrap behavior are verified locally. No App was installed or modified on the NAS through the read-only SSH access. Live Proton login and event creation still require account testing. The separate shell Compose files remain an optional developer installation route.

References: [TrueNAS custom Apps](https://www.truenas.com/docs/scale/apps/installcustomappscreens/), [Docker inline build support](https://docs.docker.com/reference/compose-file/build/#dockerfile_inline).
