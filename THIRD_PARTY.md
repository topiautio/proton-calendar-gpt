# Third-party components

The original source in this repository is licensed under the [MIT License](LICENSE).
The components below keep their own licences. This project is unofficial and is
not affiliated with or endorsed by Proton.

## Adapter image

- **[Carbonate](https://github.com/develonrails/carbonate)**, MIT. The image builds
  it from pinned commit `baa9818402e980208ac0041ea6544f3d4683d29d`. This project
  adds `carbonate-cli.patch`, `bridge-calendar-api.go` and
  `bridge-calendar-query.go` for machine-readable calendar reads. The upstream
  licence stays in the build-stage checkout; keep Carbonate's notice if you
  distribute a built image.
- **Python packages**, installed from PyPI at build time and not included in this
  repository: FastAPI (MIT), Uvicorn (BSD-3-Clause), icalendar (BSD-2-Clause) and
  [recurring-ical-events](https://pypi.org/project/recurring-ical-events/) 3.8.2
  (LGPL-3.0-or-later), used as an unmodified, separately installed library.
- **Container images** (Python, Go, Caddy, Tailscale) have their own licences and
  notices.

## `calendar-plugin/`

The ChatGPT plugin is a ChatGPT Sites project. Its files come from several sources:

| Files | Source | Licence |
| --- | --- | --- |
| App shell, auth helper, database setup, configuration and most of `components/ui/` | OpenAI's [`create-sites`](https://github.com/openai/sites/tree/main/packages/create-sites) vinext template, partly modified | MIT, © 2026 OpenAI (same text as `build/sites-vite-plugin.LICENSE`) |
| `build/sites-vite-plugin.ts` | Vendored from `@openai/sites-vite-plugin` 0.2.0 | MIT, © 2026 OpenAI; see `build/sites-vite-plugin.LICENSE` |
| `components/ui/`, `vendor/shadcn-tailwind-4.13.0.css` | [shadcn/ui](https://ui.shadcn.com) | MIT, © 2023 shadcn; see `vendor/shadcn-tailwind-4.13.0.LICENSE.md` |
| `lib/calendar-mcp.ts`, `tests/calendar-mcp.test.mjs`, `README.md` | This project | MIT |

### ChatGPT Sites tooling without a published licence

The ChatGPT Sites environment generated the build, preview and install tooling
below. These files are not part of the public MIT template and carry no licence
notice, so **this project's MIT licence does not cover them**. They are included
only so the plugin builds on ChatGPT Sites.

- `build/connector-preview-plugin.mjs`, `build/connector-preview-worker.mjs`,
  `build/sites-worker.ts`
- `scripts/` (all files)
- `lib/connector-context.ts`, `lib/connector-contract.mts`,
  `lib/connector-errors.mts`, `lib/connector-preview.d.ts`, `lib/connectors.ts`
- `components/connector-error.tsx`
- `examples/d1/`
- Generated or boilerplate configuration: `.npmrc`, `cloudflare-env.d.ts`,
  `eslint.config.mjs`, `postcss.config.mjs`, `drizzle/meta/_journal.json`,
  `public/file.svg`, `public/globe.svg`, `public/window.svg`
