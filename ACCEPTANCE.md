# Live acceptance for v0.2

The release is complete only after these checks pass through the installed
ChatGPT plugin and the official Proton Calendar application. Local tests exercise
a fake bridge and cannot establish live compatibility or delivered notifications.

## Before testing

- Leave existing real appointments untouched. Keep one pre-existing reference
  event to read during the checks, and do not edit or delete it.
- Confirm connection status, Proton login and `getCalendarContext.api_version: 2`.
- List calendars and confirm the configured default is the intended calendar.
  Do not change calendar configuration while testing.
- Use uniquely named disposable acceptance events. Read the target before every
  edit/delete, supplying its current revision. Avoid attendees/invitations.

## Checks

1. If an earlier creation job ended `unknown`, reconcile it using
   `verifyEventWrite`. Poll the operation, then confirm the original job is
   verified. This is read-only.
2. List today's events and search for the reference event. Read its full details
   and confirm its title and times without altering it.
3. Create a disposable timed event with a 15-minute device reminder. Poll until
   verified and independently read the event/reminder back through the plugin.
4. Reschedule that disposable event and edit its title. Confirm verified status,
   the revised time/title and preserved reminder in a fresh read and Proton UI.
5. Create a three-occurrence weekly series spanning the October DST transition,
   with Europe/Helsinki recurrence timezone. Confirm each occurrence retains its
   local start time while the UTC offset changes. Read the rule and reminders.
6. Edit the second occurrence's time/title, read it back by its original recurrence
   ID, then cancel that occurrence. Confirm the other two occurrences remain.
7. Change the disposable series' reminder and confirm the master and any exception
   retain the requested reminder. Confirm series and occurrence scope behave as
   explicitly requested; ambiguous requests should trigger clarification.
8. Create/read/edit a disposable all-day event and confirm its exclusive end date.
9. Delete only the disposable acceptance events/series. Confirm verified deletion
   and fresh reads showing absence. Leave the reference event unchanged.
10. Repeat an identical creation request or mutation input/revision: it returns
    the original job/operation instead of creating a duplicate. A stale revision
    must fail without writing. Restarting the App preserves the session and queue.

## Checkpoint: 6 October 2026

TrueNAS runs adapter 0.2.4 and the hosted plugin is deployed. Reconnecting the
plugin resolved a stale tool catalog.

Verified live through the authenticated adapter:

- Timed creation, title edits and rescheduling with preserved device reminders.
- All-day creation/rescheduling with correct exclusive end dates.
- Weekly recurrence across the October Helsinki DST transition, preserving
  local start times while offsets change.
- Moving one occurrence while retaining its original recurrence identity and
  leaving its master unchanged.
- Changing reminders on both a recurring master and its saved exception.
- Cancelling one occurrence with EXDATE plus targeted exception removal;
  adapter 0.2.4 reports ready/verified.
- Individual and whole-series deletion. All recurrence acceptance events were
  deleted with verified status. The reference event was left unchanged.
- Repeating the exact creation request for a notification test reuses its
  original verified job; it does not create another event.
- A five-minute device reminder was delivered to an Android phone at the
  expected time.

Verified through regular ChatGPT's installed plugin:

- Listing calendars; searching for and reading the reference event.
- Creating/reading a disposable weekly series with reminders. Its whole-series
  title/reminder edit eventually verified on the adapter; a fresh read confirmed
  both occurrences changed. Its cleanup through the adapter verified.
- Reading the notification test's title, times and reminder with verified
  signatures. The operation reached ready after one status poll under the
  improved hosted polling behavior.

Hosted status tools now wait up to 24 seconds per call using only read-only GETs
against the original job. They return terminal states promptly, remain bounded,
and never repeat mutations or unknown jobs. Eleven Node tests, TypeScript and
production build pass. Forty Python tests, patched Go calendar/CLI tests, and the
exact compressed inline Docker build pass.

The TrueNAS Save/logout cause was its 65,536-character authenticated WebSocket
message limit. Expanded YAML exceeded it and the connection closed before a job
started. Compressed embedded source reduced the App YAML to about 27 KB. Both
updates subsequently saved, rebuilt and returned to RUNNING with the session
intact. Generated templates enforce a size budget with headroom for settings.
The editor must finish loading its existing YAML before pasting an update.

Earlier occurrence edits were uncertain and were not retried. Timezone-aware
recurrence identity fixed editing. The first cancellation saved, but comparison
of EXDATE wire strings returned unknown; fresh reads confirmed the occurrence
absent and other dates retained. Normalizing exclusions as sets of actual dates
fixed verification, including duplicate signed cards and equivalent timezones.

Remaining final host check: ChatGPT was sent an explicit description-edit and
cleanup request for the completed notification test event. It returned no
assistant result, and no action approval or error was shown. A shorter request
with the app explicitly attached also returned no assistant result. A fresh
adapter read confirms the event still exists with its original description and
revision. No further mutation was submitted from the adapter, to avoid racing a
possibly pending host approval. The test event is kept until this is resolved.

Notification delivery and the adapter capabilities have passed. The release is
not marked complete until the remaining ChatGPT mutation/cleanup check resolves.
Attendee invitations are intentionally outside the first-version scope.

## Checkpoint: 10 October 2026 — Claude connector

TrueNAS runs adapter 0.3.0, deployed by replacing only the embedded build block
in the existing App YAML (about 40 KB; environment settings unchanged). The
adapter now serves a remote MCP endpoint at `/mcp` with single-owner OAuth
(dynamic client registration, PKCE S256, approval with `ACTION_API_KEY`).

Verified live through claude.ai with a custom connector:

- claude.ai detected OAuth and dynamic registration automatically; approval on
  the adapter's page succeeded and all eleven tools were listed.
- Creating a disposable timed event progressed pending → writing → verified.
- The same chat found it with listCalendarEvents, read its revision and deleted
  it with scope `event`; the deletion reached ready with `verified: true`. No
  other events were touched.

Forty-nine Python tests pass, including the OAuth and MCP flow. The official MCP
Python SDK client completed discovery, registration, PKCE and tool calls locally.

## Later use

The ChatGPT check left open on 6 October is closed: the ChatGPT plugin works in
everyday use. Requests through both ChatGPT and Claude can take tens of seconds
before the assistant answers.
