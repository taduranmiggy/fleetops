"""Pickup-window capacity: four trucks × 42 t, with overlap by planned trip duration on the route."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.constants.booking_time_slots import (
    BOOKING_SLOT_TERMINAL_STATUSES,
    BOOKING_TIME_SLOTS,
    normalize_time_slot,
)
from app.constants.fleet_capacity import (
    DEFAULT_ROAD_SPEED_KMH_FOR_ETA,
    FLEET_TRUCK_COUNT,
    MIN_TRIP_DURATION_HOURS,
    trucks_required_for_cargo,
)
from app.core.config import Settings, settings as app_settings
from app.models.entities import Booking, Trip, TripStatus
from app.services.route_estimate import (
    PreciseDistanceUnavailable,
    estimate_road_distance_km_with_fallback,
)
from app.services.booking_capacity import fleet_operational_pool_size
from app.services.demo_booking_filter import is_demo_placeholder_booking

_TERMINAL_TRIP: frozenset[TripStatus] = frozenset({TripStatus.COMPLETED, TripStatus.CANCELLED})


def _slot_start_on_date(booking_date: date, time_slot: str) -> datetime:
    t = datetime.strptime(time_slot.strip(), "%H:%M").time()
    return datetime.combine(booking_date, t)


def duration_hours_for_route(pickup_location: str, dropoff_location: str, cfg: Settings | None = None) -> float:
    cfg = cfg or app_settings
    km, _, _ = estimate_road_distance_km_with_fallback(pickup_location, dropoff_location, cfg)
    return max(MIN_TRIP_DURATION_HOURS, float(km) / DEFAULT_ROAD_SPEED_KMH_FOR_ETA)


def duration_hours_for_booking(booking: Booking, cfg: Settings | None = None) -> float:
    return duration_hours_for_route(booking.pickup_location, booking.dropoff_location, cfg)


def interval_for_pickup_window(
    scheduled_date: date,
    time_slot: str,
    pickup_location: str,
    dropoff_location: str,
    cfg: Settings | None = None,
) -> tuple[datetime, datetime]:
    start = _slot_start_on_date(scheduled_date, time_slot)
    end = start + timedelta(hours=duration_hours_for_route(pickup_location, dropoff_location, cfg))
    return start, end


def booking_interval_resolved(
    db: Session,
    booking: Booking,
    cfg: Settings | None = None,
) -> tuple[datetime, datetime]:
    """Uses dispatcher-selected route duration when a route option is saved."""
    from app.services.dispatch_route_selection import _parse_path_payload, get_selected_route_option

    cfg = cfg or app_settings
    if booking.scheduled_date is None or not (booking.scheduled_time_slot or "").strip():
        now = datetime.utcnow()
        return now, now + timedelta(hours=MIN_TRIP_DURATION_HOURS)
    start = _slot_start_on_date(booking.scheduled_date, booking.scheduled_time_slot)
    selected = get_selected_route_option(db, booking.id)
    dur: float | None = None
    if selected is not None:
        _, meta = _parse_path_payload(selected.path_json)
        raw_dur = meta.get("duration_hours")
        if raw_dur is not None:
            dur = float(raw_dur)
        if dur is None or dur <= 0:
            dist = float(selected.distance_km or 0)
            if dist > 0:
                dur = max(MIN_TRIP_DURATION_HOURS, dist / DEFAULT_ROAD_SPEED_KMH_FOR_ETA)
    if dur is None or dur <= 0:
        dur = duration_hours_for_booking(booking, cfg)
    return start, start + timedelta(hours=dur)


def booking_interval(
    booking: Booking,
    cfg: Settings | None = None,
) -> tuple[datetime, datetime]:
    return interval_for_pickup_window(
        booking.scheduled_date,
        booking.scheduled_time_slot,
        booking.pickup_location,
        booking.dropoff_location,
        cfg,
    )


def booking_interval_best_effort(
    booking: Booking,
    cfg: Settings | None = None,
) -> tuple[datetime, datetime]:
    """Like ``booking_interval`` but falls back to slot start + MIN_TRIP_DURATION when route km is unavailable."""
    try:
        return booking_interval(booking, cfg)
    except PreciseDistanceUnavailable:
        if booking.scheduled_date is None or not (booking.scheduled_time_slot or "").strip():
            now = datetime.utcnow()
            return now, now + timedelta(hours=MIN_TRIP_DURATION_HOURS)
        start = _slot_start_on_date(booking.scheduled_date, booking.scheduled_time_slot)
        return start, start + timedelta(hours=MIN_TRIP_DURATION_HOURS)


def booking_pickup_window_end_approx(booking: Booking) -> datetime | None:
    """Fast pickup-window end for dashboards — no geocoding or external routing."""
    if booking.scheduled_date is None or not (booking.scheduled_time_slot or "").strip():
        return None
    if normalize_time_slot(booking.scheduled_time_slot) not in BOOKING_TIME_SLOTS:
        return None
    start = _slot_start_on_date(booking.scheduled_date, booking.scheduled_time_slot)
    return start + timedelta(hours=MIN_TRIP_DURATION_HOURS)


def trip_interval(db: Session, trip: Trip, cfg: Settings | None = None) -> tuple[datetime, datetime]:
    booking = trip.booking or db.query(Booking).filter(Booking.id == trip.booking_id).first()
    if booking is None:
        now = datetime.utcnow()
        return now, now + timedelta(hours=MIN_TRIP_DURATION_HOURS)
    start = _slot_start_on_date(booking.scheduled_date, booking.scheduled_time_slot)
    dur = float(trip.duration_hours) if trip.duration_hours and trip.duration_hours > 0 else 0.0
    if dur <= 0:
        dur = duration_hours_for_booking(booking, cfg)
    end = start + timedelta(hours=dur)
    return start, end


def intervals_overlap(a0: datetime, a1: datetime, b0: datetime, b1: datetime) -> bool:
    return a0 < b1 and b0 < a1


def trucks_committed_for_window(
    db: Session,
    scheduled_date: date,
    time_slot: str,
    pickup_location: str,
    dropoff_location: str,
    cfg: Settings | None = None,
    exclude_booking_id: int | None = None,
) -> int:
    """Sum required trucks for non-terminal bookings whose planned interval overlaps this window."""
    if not pickup_location.strip() or not dropoff_location.strip():
        return 0
    cfg = cfg or app_settings
    ns, ne = interval_for_pickup_window(
        scheduled_date, time_slot, pickup_location, dropoff_location, cfg
    )
    total = 0
    rows = (
        db.query(Booking)
        .filter(
            Booking.scheduled_date == scheduled_date,
            ~Booking.status.in_(BOOKING_SLOT_TERMINAL_STATUSES),
        )
        .all()
    )
    for b in rows:
        if exclude_booking_id is not None and b.id == exclude_booking_id:
            continue
        if is_demo_placeholder_booking(b.pickup_location, b.dropoff_location):
            continue
        s, e = booking_interval(b, cfg)
        if intervals_overlap(ns, ne, s, e):
            total += trucks_required_for_cargo(b.cargo_weight_tons)
    return total


def available_trucks_for_window(
    db: Session,
    scheduled_date: date,
    time_slot: str,
    pickup_location: str,
    dropoff_location: str,
    cfg: Settings | None = None,
    exclude_booking_id: int | None = None,
) -> int:
    pool = fleet_operational_pool_size(db)
    if pool <= 0:
        return 0
    committed = trucks_committed_for_window(
        db,
        scheduled_date,
        time_slot,
        pickup_location,
        dropoff_location,
        cfg,
        exclude_booking_id,
    )
    return max(0, pool - committed)


def slot_has_capacity(
    db: Session,
    scheduled_date: date,
    time_slot: str,
    cargo_weight_tons: float,
    pickup_location: str,
    dropoff_location: str,
    cfg: Settings | None = None,
    exclude_booking_id: int | None = None,
) -> bool:
    if not pickup_location.strip() or not dropoff_location.strip():
        return False
    cfg = cfg or app_settings
    need = trucks_required_for_cargo(cargo_weight_tons)
    ns, ne = interval_for_pickup_window(
        scheduled_date, time_slot, pickup_location, dropoff_location, cfg
    )

    total = 0
    rows = (
        db.query(Booking)
        .filter(
            Booking.scheduled_date == scheduled_date,
            ~Booking.status.in_(BOOKING_SLOT_TERMINAL_STATUSES),
        )
        .all()
    )
    for b in rows:
        if exclude_booking_id is not None and b.id == exclude_booking_id:
            continue
        if is_demo_placeholder_booking(b.pickup_location, b.dropoff_location):
            continue
        s, e = booking_interval(b, cfg)
        if intervals_overlap(ns, ne, s, e):
            total += trucks_required_for_cargo(b.cargo_weight_tons)
    pool = fleet_operational_pool_size(db)
    if pool <= 0:
        return False
    return total + need <= pool


def slot_available(
    db: Session,
    scheduled_date: date,
    time_slot: str,
    cargo_weight_tons: float,
    pickup_location: str,
    dropoff_location: str,
    cfg: Settings | None = None,
    exclude_booking_id: int | None = None,
) -> bool:
    return slot_has_capacity(
        db,
        scheduled_date,
        time_slot,
        cargo_weight_tons,
        pickup_location,
        dropoff_location,
        cfg,
        exclude_booking_id,
    )


def availability_for_date(
    db: Session,
    scheduled_date: date,
    cargo_weight_tons: float,
    pickup_location: str,
    dropoff_location: str,
    cfg: Settings | None = None,
) -> dict[str, bool]:
    """Map each canonical slot → True when a new booking may start then (fleet trucks + overlap)."""
    need = trucks_required_for_cargo(cargo_weight_tons)
    return {
        slot: available_trucks_for_window(
            db, scheduled_date, slot, pickup_location, dropoff_location, cfg
        )
        >= need
        for slot in BOOKING_TIME_SLOTS
    }


def available_trucks_by_slot_for_date(
    db: Session,
    scheduled_date: date,
    pickup_location: str,
    dropoff_location: str,
    cfg: Settings | None = None,
) -> dict[str, int]:
    return {
        slot: available_trucks_for_window(
            db, scheduled_date, slot, pickup_location, dropoff_location, cfg
        )
        for slot in BOOKING_TIME_SLOTS
    }


def truck_free_for_booking(
    db: Session,
    truck_id: int,
    booking: Booking,
    cfg: Settings | None = None,
    exclude_trip_id: int | None = None,
) -> bool:
    cfg = cfg or app_settings
    ns, ne = booking_interval_resolved(db, booking, cfg)
    trips = db.query(Trip).filter(Trip.truck_id == truck_id, ~Trip.status.in_(_TERMINAL_TRIP)).all()
    for tr in trips:
        if exclude_trip_id is not None and tr.id == exclude_trip_id:
            continue
        s, e = trip_interval(db, tr, cfg)
        if intervals_overlap(ns, ne, s, e):
            return False
    return True


def driver_free_for_booking(
    db: Session,
    driver_id: int,
    booking: Booking,
    cfg: Settings | None = None,
    exclude_trip_id: int | None = None,
) -> bool:
    cfg = cfg or app_settings
    ns, ne = booking_interval_resolved(db, booking, cfg)
    trips = db.query(Trip).filter(Trip.driver_id == driver_id, ~Trip.status.in_(_TERMINAL_TRIP)).all()
    for tr in trips:
        if exclude_trip_id is not None and tr.id == exclude_trip_id:
            continue
        s, e = trip_interval(db, tr, cfg)
        if intervals_overlap(ns, ne, s, e):
            return False
    return True


def helper_free_for_booking(
    db: Session,
    helper_id: int,
    booking: Booking,
    cfg: Settings | None = None,
    exclude_trip_id: int | None = None,
) -> bool:
    cfg = cfg or app_settings
    ns, ne = booking_interval_resolved(db, booking, cfg)
    trips = db.query(Trip).filter(Trip.helper_id == helper_id, ~Trip.status.in_(_TERMINAL_TRIP)).all()
    for tr in trips:
        if exclude_trip_id is not None and tr.id == exclude_trip_id:
            continue
        s, e = trip_interval(db, tr, cfg)
        if intervals_overlap(ns, ne, s, e):
            return False
    return True


@dataclass(frozen=True)
class CrewWindowCapacity:
    trucks: int
    drivers: int
    helpers: int
    required: int
    can_book: bool

    @property
    def message(self) -> str | None:
        if self.can_book:
            return None
        missing: list[str] = []
        if self.trucks < self.required:
            missing.append(f"trucks ({self.trucks} free, need {self.required})")
        if self.drivers < self.required:
            missing.append(f"drivers ({self.drivers} free, need {self.required})")
        if self.helpers < self.required:
            missing.append(f"helpers ({self.helpers} free, need {self.required})")
        detail = ", ".join(missing) if missing else "crew"
        return (
            f"Not enough free trucks, drivers, and helpers for this date/time ({detail}). "
            "Please choose another schedule."
        )


_OFF_DUTY = frozenset({"off_duty", "off-duty", "on_break", "break", "unavailable"})
_NON_OP_TRUCK = frozenset({"maintenance", "inactive", "under_maintenance", "in_maintenance"})


def _crew_norm(value: str | None) -> str:
    raw = (value or "").strip().lower()
    return raw.rsplit(".", 1)[-1]


_TERMINAL_BOOKING_VALUES = frozenset(status.value for status in BOOKING_SLOT_TERMINAL_STATUSES)


def _booking_status_value(value: object | None) -> str:
    """Normalize enum/string booking statuses returned by different DB dialects."""
    if value is None:
        return ""
    if hasattr(value, "value"):
        return str(getattr(value, "value")).strip().lower()
    raw = str(value).strip().lower()
    if "." in raw:
        raw = raw.rsplit(".", 1)[-1]
    return raw


def _resource_free_for_interval(
    db: Session,
    *,
    kind: str,
    resource_id: int,
    window_start: datetime,
    window_end: datetime,
    cfg: Settings,
    exclude_booking_id: int | None = None,
) -> bool:
    """True when no non-terminal trip/assignment for this resource overlaps the window."""
    from app.models.entities import (
        TruckAssignment,
        TruckAssignmentStatus,
    )

    non_terminal_assignment = frozenset(
        {
            TruckAssignmentStatus.ASSIGNED,
            TruckAssignmentStatus.FOR_PICKUP,
            TruckAssignmentStatus.PICKED_UP,
            TruckAssignmentStatus.EN_ROUTE,
            TruckAssignmentStatus.DROPPED_OFF,
            TruckAssignmentStatus.IN_PROGRESS,
        }
    )

    # A stale non-terminal trip attached to a terminal booking must not reserve
    # crew capacity. This mirrors dispatch_resource_availability._active_trips,
    # which is the source of truth used by the dispatcher dashboard.
    trip_q = (
        db.query(Trip, Booking)
        .join(Booking, Booking.id == Trip.booking_id)
        .filter(
            ~Trip.status.in_(_TERMINAL_TRIP),
            ~Booking.status.in_(BOOKING_SLOT_TERMINAL_STATUSES),
        )
    )
    if kind == "truck":
        trip_q = trip_q.filter(Trip.truck_id == resource_id)
    elif kind == "driver":
        trip_q = trip_q.filter(Trip.driver_id == resource_id)
    else:
        trip_q = trip_q.filter(Trip.helper_id == resource_id)
    for tr, bk in trip_q.all():
        # Keep the Python guard for legacy rows/dialects that return raw status
        # strings and can bypass an enum-based SQL predicate.
        if _booking_status_value(bk.status) in _TERMINAL_BOOKING_VALUES:
            continue
        if exclude_booking_id is not None and tr.booking_id == exclude_booking_id:
            continue
        s, e = trip_interval(db, tr, cfg)
        if intervals_overlap(window_start, window_end, s, e):
            return False

    assign_q = (
        db.query(TruckAssignment, Booking)
        .join(Booking, Booking.id == TruckAssignment.booking_id)
        .filter(
            TruckAssignment.assignment_status.in_(non_terminal_assignment),
            ~Booking.status.in_(BOOKING_SLOT_TERMINAL_STATUSES),
        )
    )
    if kind == "truck":
        assign_q = assign_q.filter(TruckAssignment.truck_id == resource_id)
    elif kind == "driver":
        assign_q = assign_q.filter(TruckAssignment.driver_id == resource_id)
    else:
        assign_q = assign_q.filter(TruckAssignment.helper_id == resource_id)
    for ta, bk in assign_q.all():
        if _booking_status_value(bk.status) in _TERMINAL_BOOKING_VALUES:
            continue
        if exclude_booking_id is not None and bk.id == exclude_booking_id:
            continue
        s, e = booking_interval_resolved(db, bk, cfg)
        if intervals_overlap(window_start, window_end, s, e):
            return False
    return True


def crew_capacity_for_window(
    db: Session,
    scheduled_date: date,
    time_slot: str,
    pickup_location: str,
    dropoff_location: str,
    *,
    required_trucks: int,
    cfg: Settings | None = None,
    exclude_booking_id: int | None = None,
) -> CrewWindowCapacity:
    """Count free trucks/drivers/helpers for a pickup window (calendar overlap only)."""
    from app.models.entities import Truck, User, UserRole

    cfg = cfg or app_settings
    need = max(1, int(required_trucks))
    pickup = (pickup_location or "").strip() or "Unknown pickup"
    dropoff = (dropoff_location or "").strip() or "Unknown dropoff"
    try:
        window_start, window_end = interval_for_pickup_window(
            scheduled_date, time_slot, pickup, dropoff, cfg
        )
    except PreciseDistanceUnavailable:
        start = _slot_start_on_date(scheduled_date, time_slot)
        window_start, window_end = start, start + timedelta(hours=MIN_TRIP_DURATION_HOURS)

    trucks = [
        t
        for t in db.query(Truck).order_by(Truck.id).all()
        if _crew_norm(t.status) not in _NON_OP_TRUCK
    ]
    crew_users = db.query(User).order_by(User.id).all()
    drivers = [
        u
        for u in crew_users
        if _crew_norm(getattr(u.role, "value", u.role)) == UserRole.DRIVER.value
        and _crew_norm(u.availability_status) not in _OFF_DUTY
    ]
    helpers = [
        u
        for u in crew_users
        if _crew_norm(getattr(u.role, "value", u.role)) == UserRole.HELPER.value
        and _crew_norm(u.availability_status) not in _OFF_DUTY
    ]

    free_trucks = sum(
        1
        for t in trucks
        if _resource_free_for_interval(
            db,
            kind="truck",
            resource_id=t.id,
            window_start=window_start,
            window_end=window_end,
            cfg=cfg,
            exclude_booking_id=exclude_booking_id,
        )
    )
    free_drivers = sum(
        1
        for u in drivers
        if _resource_free_for_interval(
            db,
            kind="driver",
            resource_id=u.id,
            window_start=window_start,
            window_end=window_end,
            cfg=cfg,
            exclude_booking_id=exclude_booking_id,
        )
    )
    free_helpers = sum(
        1
        for u in helpers
        if _resource_free_for_interval(
            db,
            kind="helper",
            resource_id=u.id,
            window_start=window_start,
            window_end=window_end,
            cfg=cfg,
            exclude_booking_id=exclude_booking_id,
        )
    )

    # Cap truck free count by the booking fleet pool (same abstraction as slot holds).
    free_trucks = min(free_trucks, fleet_operational_pool_size(db))

    can_book = free_trucks >= need and free_drivers >= need and free_helpers >= need
    return CrewWindowCapacity(
        trucks=free_trucks,
        drivers=free_drivers,
        helpers=free_helpers,
        required=need,
        can_book=can_book,
    )
