package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"github.com/develonrails/carbonate/internal/calendar"
	"io"
)

// Machine-readable calendar data for the private adapter. No account/session
// credentials are included. Targeted UID reads decrypt only the requested event.
func cmdCalendarJSON(ctx context.Context, args []string, out io.Writer, events bool) error {
	fs := flag.NewFlagSet("calendar json", flag.ContinueOnError)
	fs.SetOutput(out)
	path := fs.String("session", "", "session file")
	calendarID := fs.String("calendar", "", "calendar ID")
	uid := fs.String("uid", "", "only this iCalendar UID")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if fs.NArg() != 0 {
		return errors.New("unexpected positional argument")
	}
	conn, err := connect(ctx, *path)
	if err != nil {
		return err
	}
	defer conn.Close()
	if !events {
		calendars, err := calendar.List(ctx, conn)
		if err != nil {
			return err
		}
		return json.NewEncoder(out).Encode(calendars)
	}
	if *calendarID == "" {
		return errors.New("calendar ID is required")
	}
	decoded, unreadable, err := calendar.EventsForUID(ctx, conn, *calendarID, *uid)
	if err != nil {
		return err
	}
	type item struct {
		UID        string `json:"uid"`
		ICS        string `json:"ics"`
		Modified   string `json:"modified"`
		Unverified bool   `json:"unverified"`
	}
	result := struct {
		CalendarID      string `json:"calendar_id"`
		Events          []item `json:"events"`
		UnreadableCount int    `json:"unreadable_count"`
	}{CalendarID: *calendarID, Events: []item{}, UnreadableCount: len(unreadable)}
	for _, event := range decoded {
		result.Events = append(result.Events, item{event.UID, event.ICS(), event.Modified.UTC().Format("2006-01-02T15:04:05Z"), event.Unverified})
	}
	return json.NewEncoder(out).Encode(result)
}
