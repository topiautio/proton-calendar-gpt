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

TrueNAS runs adapter 0.2.4. Reconnecting the ChatGPT plugin resolved its stale
tool catalog. A read-only check in regular ChatGPT successfully used
`listCalendars`, `listCalendarEvents`, `getCalendarEvent` and
`getCalendarOperationStatus`: all three calendars were returned, Kalenteri was
the default, and Test 2 was found/read at its original 13:00–14:00 Helsinki time.
Its old creation job was reconciled to `verified` without rewriting it.

Authenticated adapter acceptance checks passed:

- Timed creation with a 15-minute device reminder, title edit and rescheduling;
  the reminder survived a fresh read.
- Three-occurrence weekly creation with a 30-minute reminder, retaining 09:00
  Helsinki across the October DST transition.
- All-day creation with a 60-minute reminder and rescheduling; the exclusive
  end date remained correct.
- Verified deletion of all disposable acceptance events, including both whole
  recurring series. Test 2 was preserved.

Regular ChatGPT also created and read a disposable two-occurrence weekly series
with a 15-minute reminder. Its whole-series title/reminder edit reached verified
status on the adapter and a fresh read showed 45-minute reminders on both dates.
ChatGPT stopped polling after its six-check limit; the adapter continued the
operation. The disposable series was subsequently deleted with verified status
through the adapter. This polling limit needs further workflow testing.

Single-occurrence editing returned `unknown` on three disposable series. Fresh
reads confirmed their masters unchanged, with no saved exception. No uncertain
write was automatically retried. Occurrence cancellation and reminder edits
across existing exceptions have not passed live acceptance. Adapter 0.2.2 exposed
Proton rejection code 2001 on the third attempt. No uncertain edit was retried.
All disposable events were removed; Test 2 remains unchanged.

The source for adapter 0.2.3 advances new exception sequences, preserves the
parent's recurrence timezone, patches Carbonate to resolve timezone IDs and
reject invalid recurrence IDs before they can select the master, and uses a
parent EXDATE plus targeted exception deletion for cancellation. Diagnostics
contain only fixed labels/numeric codes/categories, never raw upstream text.
Its 39 Python tests, patched Go calendar/CLI tests (including real recurrence
identity regression tests), and Docker build pass. It is deployed and live recurrence acceptance is in progress. Actual notification delivery also needs confirmation.

The owner authorized editing the YAML in their signed-in TrueNAS browser. The
Save/logout failure was traced to the installed middleware's 65,536-character
authenticated WebSocket message limit: the expanded private YAML exceeded it,
and the connection closed before a job started. Compressed embedded source
reduced the private YAML to about 27 KB. The exact generated Docker build passed,
then Save completed successfully in TrueNAS with the session intact. The App
returned to RUNNING and the public API reported adapter 0.2.3. Generated templates
now enforce a request-size budget with headroom for private settings.

Adapter 0.2.3 then verified a moved single occurrence and preservation of its
master. Cancellation saved successfully: a fresh list returned only October 19
and November 2 and no exception remained. Its operation stayed unknown because
the exclusion comparison used wire strings. Adapter 0.2.4 compares EXDATE/RDATE
as sets of actual instants, independent of UTC spelling, grouping and duplicate
signed cards. Its new regression test checks equivalent dates and detects extra
exclusions; all 40 Python tests and the exact inline Docker build pass. The small
YAML saved again without logout and the deployed API reports 0.2.4. A different
occurrence is being tested; the uncertain cancellation is never replayed.
