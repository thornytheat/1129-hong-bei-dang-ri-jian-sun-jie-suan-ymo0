from collections import defaultdict
from .contracts import OvenTicket


def close_candidates(tickets: tuple[OvenTicket, ...], *, day: int, minute: int):
    observed = defaultdict(list)
    for ticket in tickets:
        if ticket.day != day or ticket.display_min > minute:
            continue
        observed[ticket.lot].append(ticket)
    usable, refusals = [], []
    for lot, changes in sorted(observed.items()):
        revision = max(item.revision for item in changes)
        current = set(item for item in changes if item.revision == revision)
        if len(current) > 1:
            refusals.append({"lot": lot, "reason": "REVISION_CONFLICT"})
            continue
        ticket = current.pop()
        if ticket.station != changes[0].station or any(i.station != ticket.station for i in changes):
            refusals.append({"lot": lot, "reason": "STATION_CONFLICT"})
            continue
        if not ticket.arrival_min <= minute < ticket.arrival_min + ticket.shelf_minutes:
            refusals.append({"lot": lot, "reason": "OUTSIDE_SHELF_WINDOW"})
            continue
        usable.append(ticket)
    return usable, refusals


def lot_clock(ticket: OvenTicket, minute: int) -> dict:
    expiry = ticket.arrival_min + ticket.shelf_minutes
    display = max(ticket.arrival_min, ticket.display_min)
    return {
        "lot": ticket.lot,
        "station": ticket.station,
        "sku": ticket.sku,
        "display": display,
        "expiry": expiry,
        "minutes_left": max(0, expiry - max(display, minute)),
        "reference_price_cents": ticket.price_cents,
    }


def carryable(ticket: OvenTicket, inspection_minute: int) -> bool:
    return max(ticket.arrival_min, ticket.display_min) <= inspection_minute < ticket.arrival_min + ticket.shelf_minutes
