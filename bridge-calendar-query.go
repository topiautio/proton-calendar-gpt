package calendar

import (
	"context"
	"github.com/develonrails/carbonate/internal/proton"
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
