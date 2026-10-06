# Completion target

This project remains a private development project. Creating one appointment is
not the completion criterion. The target is a practical Proton Calendar assistant
in an ordinary ChatGPT chat, with these operations:

- List calendars and select the intended calendar explicitly.
- Read event details, search text and list occurrences within a date range.
- Create, edit/reschedule and delete individual events.
- Create and manage recurring series and individual occurrences.
- Set, preserve and read device reminders.
- Handle timezone offsets, daylight-saving changes and all-day events.
- Verify each mutation against Proton, without duplicate writes or false success.

Invitations and sending email are outside this first completion target. Do not
silently send guest invitations. Keep the existing Test 2 appointment unchanged.

## Live checkpoint — 6 October 2026

The private hosted MCP plugin and NAS adapter are reachable. Reconnecting exposed
the upgraded tools, and regular ChatGPT successfully listed calendars, searched
and read Test 2. Its original job is now verified through read-only reconciliation.
Live adapter checks passed timed and all-day creation/rescheduling, reminders,
weekly creation across DST, and individual/series deletion. All disposable test
events were removed and Test 2 remains unchanged.

Single-occurrence editing remains unverified; fresh reads showed no exception and
the original master unchanged. Adapter 0.2.2 adds an exception sequence correction
and safe diagnostics, with 38 Python tests passing and a successful Docker build.
It still needs a NAS rebuild and live occurrence edit/cancel tests. Whole-series
reminder changes and ChatGPT mutation flows also need live acceptance. See
ACCEPTANCE.md for the precise checkpoint.

Local tests do not establish live Proton compatibility. Completion requires live
read-back plus explicit edit, recurrence and reminder tests on disposable events.
Do not delete Test 2 as part of testing.

## Before public release

Choose a project license compatible with the components we distribute, document
upstream attribution and licensing, and finish the reproducible YAML setup and
live acceptance checklist. Every user must deploy their own adapter, Proton
session and private plugin; sharing a plugin connected to one owner's account is
not a multi-user product. Keep credentials, personal calendar IDs, session files,
job databases and hosted project identities outside the public source. There is
no planned public release in this task.
