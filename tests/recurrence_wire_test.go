package calendar

import (
	"testing"
	"time"
)

// Run inside the patched Carbonate bridge build, mounting this file into
// /src/internal/calendar. This exercises its real parser and row identity.
func TestAdapterRecurrenceTimezoneIdentity(t *testing.T) {
	for _, value := range []string{
		"RECURRENCE-ID:20261026T070000Z",
		"RECURRENCE-ID;TZID=Europe/Helsinki:20261026T090000",
	} {
		ics := "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:adapter-test\r\nDTSTART;TZID=Europe/Helsinki:20261026T140000\r\n" + value + "\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
		events, err := parseEvents(ics)
		if err != nil {
			t.Fatal(err)
		}
		want := time.Date(2026, 10, 26, 7, 0, 0, 0, time.UTC).Unix()
		if got := recurrenceIDOf(events[0]); got != want {
			t.Fatalf("%s: recurrence ID = %d, want %d", value, got, want)
		}
	}
}

func TestAdapterInvalidRecurrenceNeverSelectsMaster(t *testing.T) {
	ics := "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:adapter-test\r\nRECURRENCE-ID;TZID=Invalid/Zone:20261026T090000\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
	if _, err := parseEvents(ics); err == nil {
		t.Fatal("invalid recurrence ID could be treated as the master")
	}
}
