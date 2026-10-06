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

The original connection is reachable and the owner has confirmed Test 2 in Proton.
Its old verification job is unknown. The v0.2 backend passes 34 automated tests;
the plugin passes 10 tests and TypeScript checking, and the Docker image builds.
The new TrueNAS deployment and live acceptance results remain pending. Record
actual verified results here after testing; do not infer success from local tests.
