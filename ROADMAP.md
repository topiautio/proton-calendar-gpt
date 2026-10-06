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

The owner-private hosted MCP plugin responds and the NAS connection is reachable.
The owner confirmed that Test 2 appeared in the selected calendar at 13:00–14:00
Europe/Helsinki. Its job later became `unknown`, so write verification still has a
defect or timeout to resolve. Read/search and mutation tools beyond creation were
not exposed by the original plugin. The v0.2 source now implements these tools,
including recurring series/occurrences and device reminders. Local validation
passes; the new deployment and live acceptance checks are in progress.

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
