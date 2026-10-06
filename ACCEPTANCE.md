# Live acceptance for v0.2

The release is complete only after these checks pass through the installed private
ChatGPT plugin and the official Proton Calendar application. Local tests exercise
a fake bridge and cannot establish live compatibility or delivered notifications.

## Before testing

- Preserve the owner's existing Test 2 (6 October 2026, 13:00–14:00 Helsinki).
- Confirm connection status, Proton login and `getCalendarContext.api_version: 2`.
- List calendars and confirm the configured default is Kalenteri. Do not change
  calendar configuration or modify existing real appointments while testing.
- Use uniquely named disposable acceptance events. Read the target before every
  edit/delete, supplying its current revision. Avoid attendees/invitations.

## Checks

1. Reconcile Test 2's old unknown creation job using `verifyEventWrite`. Poll the
   operation, then confirm its original job is verified. This is read-only.
2. List today's events and search for Test 2. Read its full details and confirm
   its existing title/times without altering it.
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
   and fresh reads showing absence. Leave Test 2 unchanged.
10. Repeat an identical creation request or mutation input/revision: it returns
    the original job/operation instead of creating a duplicate. A stale revision
    must fail without writing. Restarting the App preserves the session and queue.

## Checkpoint: 6 October 2026

TrueNAS runs adapter 0.2.4. The private hosted plugin uses source
`1405c5c5b05200060e1c4c401ca8e329b32a8aa8` and deployed successfully.
Reconnecting previously resolved the stale tool catalog.

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
  deleted with verified status. Test 2 was retained unchanged.
- Repeating the exact notification-test creation request reuses its original
  verified job; it does not create another event.
- The owner's phone received the five-minute notification for the 17:20
  Helsinki test on 6 October, as confirmed at 17:15.

Verified through regular ChatGPT's installed plugin:

- Listing Vanha, Holidays in Finland and Kalenteri; searching and reading Test 2.
- Creating/reading a disposable weekly series with reminders. Its whole-series
  title/reminder edit eventually verified on the adapter; a fresh read confirmed
  both occurrences changed. Its cleanup through the adapter verified.
- Reading the phone test's correct title, times and reminder with verified
  signatures. Operation `0be93f6b92554882bec096973814f3c7` reached ready after one
  status poll under the improved hosted polling behavior.

Hosted status tools now wait up to 24 seconds per call using only read-only GETs
against the original job. They return terminal states promptly, remain bounded,
and never repeat mutations or unknown jobs. Eleven Node tests, TypeScript and
production build pass. Forty Python tests, patched Go calendar/CLI tests, and the
exact compressed inline Docker build pass.

The TrueNAS Save/logout cause was its 65,536-character authenticated WebSocket
message limit. Expanded YAML exceeded it and the connection closed before a job
started. Compressed embedded source reduced private YAML to about 27 KB. Both
updates subsequently saved, rebuilt and returned to RUNNING with the session
intact. Generated templates enforce a size budget with headroom for settings.
The editor must finish loading its existing YAML before pasting an update.

Earlier occurrence edits were uncertain and were not retried. Timezone-aware
recurrence identity fixed editing. The first cancellation saved, but comparison
of EXDATE wire strings returned unknown; fresh reads confirmed the occurrence
absent and other dates retained. Normalizing exclusions as sets of actual dates
fixed verification, including duplicate signed cards and equivalent timezones.

Remaining final host check: ChatGPT was sent an explicit description-edit and
cleanup request for only the completed phone test
`46fe94ae607cf7c5994a2dcc5b1f730aac05090ffc0cc0570636c3f2500ecd4b@private-proton-gpt`.
It returned no assistant result for those messages. A fresh adapter read confirms
that event still exists with its original description/revision. The owner saw no action approval or error. A shorter request with the app
explicitly attached also returned no assistant result. The chat was opened for
the owner to continue directly. No further mutation
was submitted from the adapter, avoiding a race with a pending host approval.
The phone test is retained until this is resolved; Test 2 remains unchanged.

Notification delivery and the adapter capabilities have passed. The release is
not marked complete until the remaining ChatGPT mutation/cleanup check resolves.
Attendee invitations are intentionally outside this agreed first-version scope.
