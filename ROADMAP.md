# Completion target

Creating one appointment is not the completion criterion. The target is a
practical Proton Calendar assistant in an ordinary ChatGPT or Claude chat, with
these operations:

- List calendars and select the intended calendar explicitly.
- Read event details, search text and list occurrences within a date range.
- Create, edit/reschedule and delete individual events.
- Create and manage recurring series and individual occurrences.
- Set, preserve and read device reminders.
- Handle timezone offsets, daylight-saving changes and all-day events.
- Verify each mutation against Proton, without duplicate writes or false success.

Invitations and sending email are outside this first completion target. Never
silently send guest invitations. Leave existing real appointments unchanged
during testing.

## Live checkpoint — 6 October 2026

The hosted MCP plugin and NAS adapter are reachable. Reconnecting exposed the
upgraded tools, and regular ChatGPT successfully listed calendars and searched
for and read an existing event. An earlier `unknown` creation job is now verified
through read-only reconciliation. Live adapter checks passed timed and all-day
creation/rescheduling, reminders, weekly creation across DST, and
individual/series deletion. All disposable test events were removed.

Adapter 0.2.4 verified occurrence editing and cancellation, plus reminder edits
on the master and exception. Phone notification delivery is confirmed. The
TrueNAS Save/logout cause was its 64 KiB request limit; compressed YAML now saves
and deploys successfully. Forty Python tests, patched Go tests, eleven hosted
Node tests, TypeScript, and both Docker/Site production builds pass. Hosted status
calls now wait with bounded read-only polls; a regular ChatGPT event read reached
ready in one status call. The final ChatGPT description edit and cleanup returned
no assistant result, and the cause is not yet known. That notification test event
is kept, while all recurrence acceptance events are deleted. See ACCEPTANCE.md.

Adapter 0.3.0 (10 October 2026) adds a Claude connector, verified live on
claude.ai.

Local tests do not establish live Proton compatibility. Completion requires live
read-back plus explicit edit, recurrence and reminder tests on disposable events.

## Public release

The original source is MIT licensed, and upstream attribution is documented in
THIRD_PARTY.md. Every user deploys their own adapter, Proton session and private
plugin; sharing a plugin connected to one person's account is not a multi-user
product. Keep credentials, personal calendar IDs, session files, job databases
and hosted project identities outside the public source.
