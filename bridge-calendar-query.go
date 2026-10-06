package calendar

import (
	"context"
	"errors"
	"github.com/develonrails/carbonate/internal/proton"
	_ "time/tzdata" // Resolve recurrence TZIDs even in the slim runtime image.
)

// EventsForUID avoids decrypting an entire account to verify one appointment.
// An empty UID deliberately requests the whole selected calendar.
func EventsForUID(ctx context.Context, conn *proton.Conn, calendarID, uid string) ([]Event, []string, error) {
	keys, err := conn.CalendarKeys(ctx, calendarID)
	if err != nil {
		return nil, nil, err
	}
	raw, err := fetchAll(ctx, conn, calendarID)
	if err != nil {
		return nil, nil, err
	}
	if uid != "" {
		selected := raw[:0]
		for _, event := range raw {
			if event.UID == uid {
				selected = append(selected, event)
			}
		}
		raw = selected
	}
	events, unreadable := decodeAll(raw, keys.CalKR, keys.AddrKR)
	return events, unreadable, nil
}

// DeleteOccurrence removes only a matching exception row, never its master.
func DeleteOccurrence(ctx context.Context, conn *proton.Conn, calendarID, uid string, recurrenceID int64) (bool, error) {
	if recurrenceID == 0 {
		return false, errors.New("refusing to delete a master as an occurrence")
	}
	keys, err := conn.CalendarKeys(ctx, calendarID)
	if err != nil {
		return false, err
	}
	event, err := findEvent(ctx, conn, calendarID, uid, recurrenceID)
	if err != nil || event == nil {
		return false, err
	}
	_, err = sync(ctx, conn, calendarID, keys.MemberID, deleteEntry{ID: event.ID}, false)
	return err == nil, err
}
