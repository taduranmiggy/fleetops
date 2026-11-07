"""Unit tests: dispatcher resource availability / assignability."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.models.entities import BookingStatus, TripStatus, TruckAssignmentStatus, UserRole
from app.services.booking_schedule import (
    CrewWindowCapacity,
    _resource_free_for_interval,
    crew_capacity_for_window,
)
from app.services.dispatch_resource_availability import (
    _BUSY_ASSIGNMENT,
    _NON_TERMINAL_ASSIGNMENT,
    _TERMINAL_BOOKING,
    _conflicts_for_resource,
    _global_resource_status,
    evaluate_driver_for_booking,
    evaluate_helper_for_booking,
    evaluate_truck_for_booking,
    heal_stale_resource_availability,
)


def test_terminal_filters_exclude_completed():
    assert BookingStatus.COMPLETED in _TERMINAL_BOOKING
    assert BookingStatus.PAYMENT_REJECTED in _TERMINAL_BOOKING
    assert BookingStatus.REJECTED in _TERMINAL_BOOKING
    assert TruckAssignmentStatus.COMPLETED not in _NON_TERMINAL_ASSIGNMENT
    assert TruckAssignmentStatus.CANCELLED not in _NON_TERMINAL_ASSIGNMENT
    # Arrived Destination / proof pending still occupies the resource.
    assert TruckAssignmentStatus.DROPPED_OFF in _BUSY_ASSIGNMENT


def test_crew_capacity_message_lists_shortages():
    crew = CrewWindowCapacity(trucks=0, drivers=1, helpers=0, required=1, can_book=False)
    assert crew.message is not None
    assert "trucks" in crew.message
    assert "helpers" in crew.message
    assert CrewWindowCapacity(2, 2, 2, 1, True).message is None


def test_crew_window_ignores_stale_trip_on_completed_booking():
    """A terminal parent booking releases capacity even if its trip row was not closed."""
    completed_booking = SimpleNamespace(id=50, status=BookingStatus.COMPLETED)
    stale_trip = SimpleNamespace(
        id=7,
        booking_id=50,
        truck_id=1,
        driver_id=10,
        helper_id=11,
        status=TripStatus.ASSIGNED,
    )
    trip_query = MagicMock()
    trip_query.join.return_value = trip_query
    trip_query.filter.return_value = trip_query
    trip_query.all.return_value = [(stale_trip, completed_booking)]
    assignment_query = MagicMock()
    assignment_query.join.return_value = assignment_query
    assignment_query.filter.return_value = assignment_query
    assignment_query.all.return_value = []
    db = MagicMock()
    db.query.side_effect = [trip_query, assignment_query]

    with (
        patch("app.services.booking_schedule.trip_interval") as trip_interval,
        patch("app.services.booking_schedule.booking_interval_resolved") as booking_interval,
    ):
        free = _resource_free_for_interval(
            db,
            kind="truck",
            resource_id=1,
            window_start=datetime(2026, 11, 18, 8, 0),
            window_end=datetime(2026, 11, 18, 10, 0),
            cfg=SimpleNamespace(),
        )

    assert free is True
    trip_query.join.assert_called_once()
    trip_interval.assert_not_called()
    booking_interval.assert_not_called()


def test_crew_window_ignores_assignment_on_payment_rejected_booking():
    """Rejected-payment assignments cannot make every customer slot unavailable."""
    rejected_booking = SimpleNamespace(id=51, status=BookingStatus.PAYMENT_REJECTED)
    stale_assignment = SimpleNamespace(
        id=8,
        booking_id=51,
        truck_id=1,
        driver_id=10,
        helper_id=11,
        assignment_status=TruckAssignmentStatus.ASSIGNED,
    )
    trip_query = MagicMock()
    trip_query.join.return_value = trip_query
    trip_query.filter.return_value = trip_query
    trip_query.all.return_value = []
    assignment_query = MagicMock()
    assignment_query.join.return_value = assignment_query
    assignment_query.filter.return_value = assignment_query
    assignment_query.all.return_value = [(stale_assignment, rejected_booking)]
    db = MagicMock()
    db.query.side_effect = [trip_query, assignment_query]

    with patch("app.services.booking_schedule.booking_interval_resolved") as booking_interval:
        free = _resource_free_for_interval(
            db,
            kind="helper",
            resource_id=11,
            window_start=datetime(2026, 11, 18, 8, 0),
            window_end=datetime(2026, 11, 18, 10, 0),
            cfg=SimpleNamespace(),
        )

    assert free is True
    booking_interval.assert_not_called()


def test_crew_window_treats_non_maintenance_truck_status_as_operational():
    """A stale dispatch status must not hide a truck from customer capacity."""
    truck = SimpleNamespace(id=1, status="assigned")
    driver = SimpleNamespace(id=10, role="driver", availability_status="available")
    helper = SimpleNamespace(id=11, role="helper", availability_status="available")
    db = MagicMock()
    truck_query = MagicMock()
    truck_query.order_by.return_value.all.return_value = [truck]
    crew_query = MagicMock()
    crew_query.order_by.return_value.all.return_value = [
        driver,
        helper,
        SimpleNamespace(id=12, role="DRIVER", availability_status="available"),
        SimpleNamespace(id=13, role="HELPER", availability_status="available"),
    ]
    db.query.side_effect = [truck_query, crew_query]

    with (
        patch("app.services.booking_schedule._resource_free_for_interval", return_value=True),
        patch("app.services.booking_schedule.fleet_operational_pool_size", return_value=1),
        patch("app.services.booking_schedule.interval_for_pickup_window", return_value=(
            datetime(2026, 11, 18, 8, 0),
            datetime(2026, 11, 18, 10, 0),
        )),
    ):
        result = crew_capacity_for_window(
            db,
            date(2026, 11, 18),
            "08:00",
            "Pickup",
            "Dropoff",
            required_trucks=1,
            cfg=SimpleNamespace(),
        )

    assert result.can_book is True
    assert result.trucks == 1


def test_active_commitment_blocks_even_when_windows_do_not_overlap():
    """Resource on an active Jul 14 booking cannot be selected for a Jul 23 booking."""
    cfg = SimpleNamespace()
    target = SimpleNamespace(
        id=233,
        scheduled_date=date(2026, 7, 23),
        scheduled_time_slot="14:00",
        pickup_location="A",
        dropoff_location="B",
    )
    live_booking = SimpleNamespace(
        id=100,
        scheduled_date=date(2026, 7, 14),
        scheduled_time_slot="08:00",
        status=BookingStatus.OUT_FOR_DELIVERY,
    )
    live_trip = SimpleNamespace(
        id=9,
        booking_id=100,
        truck_id=1,
        driver_id=2,
        helper_id=3,
        status=TripStatus.IN_DELIVERY,
        duration_hours=4.0,
        booking=live_booking,
    )

    db = MagicMock()

    with (
        patch(
            "app.services.dispatch_resource_availability.booking_interval_resolved",
            side_effect=[
                (datetime(2026, 7, 23, 14, 0), datetime(2026, 7, 23, 20, 0)),
            ],
        ),
        patch(
            "app.services.dispatch_resource_availability._active_trips",
            return_value=[(live_trip, live_booking)],
        ),
        patch(
            "app.services.dispatch_resource_availability._active_assignments",
            return_value=[],
        ),
        patch(
            "app.services.dispatch_resource_availability.trip_interval",
            return_value=(datetime(2026, 7, 14, 8, 0), datetime(2026, 7, 14, 12, 0)),
        ),
    ):
        conflicts = _conflicts_for_resource(
            db, kind="truck", resource_id=1, booking=target, cfg=cfg
        )
    assert len(conflicts) == 1
    assert conflicts[0]["booking_id"] == 100
    assert conflicts[0]["live_busy"] is True
    assert conflicts[0]["calendar_overlap"] is False


def test_conflicts_detected_when_windows_overlap():
    cfg = SimpleNamespace()
    target = SimpleNamespace(id=233)
    other = SimpleNamespace(id=100, scheduled_date=date(2026, 7, 23), scheduled_time_slot="14:00")
    trip = SimpleNamespace(
        id=9,
        booking_id=100,
        truck_id=1,
        status=TripStatus.ASSIGNED,
    )
    db = MagicMock()
    start = datetime(2026, 7, 23, 14, 0)
    end = datetime(2026, 7, 23, 18, 0)
    with (
        patch(
            "app.services.dispatch_resource_availability.booking_interval_resolved",
            return_value=(start, end),
        ),
        patch(
            "app.services.dispatch_resource_availability._active_trips",
            return_value=[(trip, other)],
        ),
        patch(
            "app.services.dispatch_resource_availability._active_assignments",
            return_value=[],
        ),
        patch(
            "app.services.dispatch_resource_availability.trip_interval",
            return_value=(start + timedelta(hours=1), end + timedelta(hours=1)),
        ),
        patch(
            "app.services.dispatch_resource_availability._trip_on_resource",
            return_value=True,
        ),
    ):
        conflicts = _conflicts_for_resource(
            db, kind="truck", resource_id=1, booking=target, cfg=cfg
        )
    assert len(conflicts) == 1
    assert conflicts[0]["booking_id"] == 100


def test_evaluate_truck_not_assignable_when_on_trip():
    """Live On Trip blocks assignment even when the calendar window is free."""
    truck = SimpleNamespace(id=1, code="TRK-001", status="available", capacity_tons=30, availability_status="assigned")
    booking = SimpleNamespace(id=233)
    db = MagicMock()

    with (
        patch(
            "app.services.dispatch_resource_availability._active_trips",
            return_value=[],
        ),
        patch(
            "app.services.dispatch_resource_availability._active_assignments",
            return_value=[],
        ),
        patch(
            "app.services.dispatch_resource_availability._global_resource_status",
            return_value="on_trip",
        ),
        patch(
            "app.services.dispatch_resource_availability._conflicts_for_resource",
            return_value=[],
        ),
    ):
        row = evaluate_truck_for_booking(db, truck, booking)

    assert row["status"] == "on_trip"
    assert row["assignable"] is False
    assert "active trip" in (row["conflict_reason"] or "").lower()


def test_evaluate_driver_and_helper_not_assignable_when_assigned():
    """Assigned badge means another active booking — cannot double-assign."""
    driver = SimpleNamespace(id=10, full_name="Driver A", availability_status="available", role="driver")
    helper = SimpleNamespace(id=11, full_name="Helper A", availability_status="available", role="helper")
    booking = SimpleNamespace(id=233)
    db = MagicMock()

    with (
        patch("app.services.dispatch_resource_availability._active_trips", return_value=[]),
        patch("app.services.dispatch_resource_availability._active_assignments", return_value=[]),
        patch("app.services.dispatch_resource_availability._global_resource_status", return_value="assigned"),
        patch(
            "app.services.dispatch_resource_availability._conflicts_for_resource",
            return_value=[
                {
                    "booking_id": 99,
                    "scheduled_date": "2026-07-14",
                    "scheduled_time_slot": "08:00",
                    "live_busy": True,
                    "calendar_overlap": False,
                }
            ],
        ),
    ):
        d = evaluate_driver_for_booking(db, driver, booking)
        h = evaluate_helper_for_booking(db, helper, booking)

    assert d["assignable"] is False
    assert h["assignable"] is False
    assert d["status"] == "assigned"
    assert h["status"] == "assigned"


def test_global_status_ignores_stale_availability_flag():
    truck = SimpleNamespace(id=1, status="available", availability_status="assigned")
    status = _global_resource_status(
        MagicMock(),
        kind="truck",
        resource_id=1,
        trip_rows=[],
        assignment_rows=[],
        truck=truck,
    )
    assert status == "available"


def test_global_status_on_trip_from_live_leg():
    trip = SimpleNamespace(id=9, truck_id=1, driver_id=None, helper_id=None, status=TripStatus.IN_DELIVERY)
    booking = SimpleNamespace(id=50, status=BookingStatus.OUT_FOR_DELIVERY)
    status = _global_resource_status(
        MagicMock(),
        kind="truck",
        resource_id=1,
        trip_rows=[(trip, booking)],
        assignment_rows=[],
        truck=SimpleNamespace(id=1, status="available", availability_status="assigned"),
    )
    assert status == "on_trip"


def test_global_status_assigned_from_pending_trip():
    trip = SimpleNamespace(id=9, truck_id=1, driver_id=None, helper_id=None, status=TripStatus.ASSIGNED)
    booking = SimpleNamespace(id=50, status=BookingStatus.ASSIGNED)
    status = _global_resource_status(
        MagicMock(),
        kind="truck",
        resource_id=1,
        trip_rows=[(trip, booking)],
        assignment_rows=[],
        truck=SimpleNamespace(id=1, status="available", availability_status="assigned"),
    )
    assert status == "assigned"


def test_global_status_on_trip_from_dropped_off_assignment():
    ta = SimpleNamespace(
        id=3,
        truck_id=1,
        driver_id=10,
        helper_id=11,
        assignment_status=TruckAssignmentStatus.DROPPED_OFF,
    )
    booking = SimpleNamespace(id=50, status=BookingStatus.OUT_FOR_DELIVERY)
    status = _global_resource_status(
        MagicMock(),
        kind="helper",
        resource_id=11,
        trip_rows=[],
        assignment_rows=[(ta, booking)],
        user=SimpleNamespace(id=11, availability_status="available"),
    )
    assert status == "on_trip"


def test_heal_clears_stale_assigned_flags():
    truck = SimpleNamespace(id=1, status="available", availability_status="assigned")
    driver = SimpleNamespace(id=10, availability_status="assigned", role=UserRole.DRIVER)
    helper = SimpleNamespace(id=11, availability_status="assigned", role=UserRole.HELPER)
    healed = heal_stale_resource_availability(
        MagicMock(),
        trucks=[truck],
        drivers=[driver],
        helpers=[helper],
        trip_rows=[],
        assignment_rows=[],
    )
    assert healed == 3
    assert truck.availability_status == "available"
    assert driver.availability_status == "available"
    assert helper.availability_status == "available"
