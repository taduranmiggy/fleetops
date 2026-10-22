from datetime import date, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_roles
from app.db import get_db
from app.models.entities import (
    Booking,
    BookingStatus,
    GeneralOperationalReport,
    GoodsDeclarationReviewStatus,
    OperationalLog,
    Trip,
    User,
    UserRole,
)
from app.schemas.booking import (
    BookingCreate,
    BookingCustomsValidate,
    BookingRead,
    BookingScheduleAvailabilityRead,
    PreDeliveryChecklistValidate,
)
from app.schemas.cargo_type import BookingCargoTypeValidate, CargoTypeScreeningRead
from app.schemas.toll_plaza import AdminBookingTollOverride
from app.services.pre_delivery_verification import build_pre_delivery_checklist
from app.services.dispatcher_booking_assignment import assert_dispatcher_booking_access
from app.services.dispatcher_booking_assignment import filter_bookings_for_dispatcher
from app.services.cargo_type_classification import apply_cargo_type_validation, screen_cargo_type
from app.services.email_templates import EmailTemplate
from app.services.notifications import send_email_notification
from app.core.config import settings
from app.constants.booking_time_slots import BOOKING_TIME_SLOTS
from app.constants.fleet_capacity import cargo_exceeds_fleet
from app.services.booking_freight_knobs import resolve_booking_freight_knobs
from app.services.booking_capacity import get_available_truck_count
from app.services.booking_schedule import (
    availability_for_date,
    available_trucks_by_slot_for_date,
    crew_capacity_for_window,
)
from app.services.route_distance_resolution import resolve_quote_distance_km
from app.constants.fleet_capacity import trucks_required_for_cargo
from app.models.entities import TruckSlotHold, TruckSlotHoldStatus
from app.services.booking_road_distance import booking_pickup_dropoff_distance_km
from app.services.booking_tracking_payload import build_assignments_for_booking
from app.services.booking_status_aggregate import aggregate_customer_display_from_assignment_rows
from app.services.general_operational_reports import list_general_operational_reports
from app.constants.general_operational_report import GENERAL_OPS_CATEGORY_LABELS, GENERAL_OPS_TRIP_STATUS_LABELS
from app.constants.operational_log import REPORT_TYPE_LABELS
from app.services.booking_documents import resolve_booking_document_path, save_booking_document, save_terms_e_signature
from app.services.terms_agreement_pdf import (
    FLEETOPT_TERMS_VERSION,
    generate_signed_terms_pdf,
    signed_terms_pdf_abs_path,
    signed_terms_pdf_relative_path,
)
from app.services.upload_urls import media_type_for_path
from app.services.dispatch_resource_availability import release_booking_trips
from app.services.goods_declaration_review import (
    effective_goods_declaration_review_status,
    goods_declaration_review_customer_fields,
    mark_goods_declaration_pending,
    mark_goods_declaration_resubmitted,
)
from app.services.goods_declaration_notifications import notify_reviewers_documents_resubmitted
from app.services.booking_qr import booking_qr_public_fields


router = APIRouter(prefix="/bookings", tags=["bookings"])


def _booking_read_payload(booking: Booking) -> dict:
    payload = BookingRead.model_validate(booking).model_dump(mode="json")
    payload.update(goods_declaration_review_customer_fields(booking))
    payload.update(booking_qr_public_fields(booking))
    return payload


def _sync_bookings_approved_from_verified_payments(db: Session, customer_id: int | None) -> None:
    """Set booking to approved when payment is already verified (fixes rows missed by ORM / legacy DB).

    Uses raw SQL so we never load Booking ORM rows while status text is still a legacy ENUM name
    (e.g. PENDING_APPROVAL) — that would raise LookupError before startup normalization runs.
    """
    try:
        extra = ""
        params: dict = {}
        if customer_id is not None:
            extra = " AND b.customer_id = :cid"
            params["cid"] = customer_id
        # Accept both normalized and legacy pending labels in WHERE
        stmt = text(
            """
            UPDATE bookings b
            INNER JOIN (
                SELECT booking_id, MAX(id) AS mid
                FROM payments
                WHERE status = 'verified'
                GROUP BY booking_id
            ) v ON v.booking_id = b.id
            INNER JOIN payments p ON p.id = v.mid
            SET
                b.status = 'payment_verified',
                b.approved_at = COALESCE(b.approved_at, p.reviewed_at, p.paid_at),
                b.approved_by_id = COALESCE(b.approved_by_id, p.reviewed_by_id)
            WHERE b.status IN ('pending_approval', 'PENDING_APPROVAL', 'payment_verification')
            """
            + extra
        )
        r = db.execute(stmt, params)
        rc = getattr(r, "rowcount", None)
        if rc is not None and rc > 0:
            db.commit()
    except Exception:
        db.rollback()


def _parse_iso_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _create_booking_record(db: Session, user: User, payload: BookingCreate) -> Booking:
    """Shared booking creation logic (JSON or multipart customer submit)."""
    has_manual_toll = bool(payload.toll_entry_point and payload.toll_exit_point)
    dist = resolve_quote_distance_km(
        payload.pickup_location,
        payload.dropoff_location,
        settings,
        distance_km_override=payload.distance_km_override,
        allow_unverified_with_manual_toll=has_manual_toll,
        allow_unverified=True,
    )
    km = dist.distance_km
    knobs = resolve_booking_freight_knobs(db, settings)
    from app.services.booking_pricing import pricing_with_toll_matrix
    from app.services.toll_matrix import DEFAULT_VEHICLE_CLASS

    pricing, toll_meta = pricing_with_toll_matrix(
        db,
        pickup_location=payload.pickup_location,
        dropoff_location=payload.dropoff_location,
        cargo_weight_tons=payload.cargo_weight_tons,
        distance_km=km,
        settings=settings,
        as_of_date=payload.scheduled_date,
        vehicle_class=(payload.vehicle_class or DEFAULT_VEHICLE_CLASS),
        manual_entry=payload.toll_entry_point,
        manual_exit=payload.toll_exit_point,
    )

    if cargo_exceeds_fleet(payload.cargo_weight_tons):
        raise HTTPException(
            status_code=400,
            detail="Cargo exceeds simultaneous fleet capacity (four trucks × 42 t). Split into multiple bookings.",
        )

    required_trucks = trucks_required_for_cargo(payload.cargo_weight_tons)
    availability = get_available_truck_count(
        db,
        payload.scheduled_date,
        payload.scheduled_time_slot,
        required_trucks=required_trucks,
        lock_rows=False,
    )
    if not availability.can_book:
        raise HTTPException(
            status_code=409,
            detail="Not enough trucks available for this schedule. Please choose another date/time.",
        )

    recheck = get_available_truck_count(
        db,
        payload.scheduled_date,
        payload.scheduled_time_slot,
        required_trucks=required_trucks,
        lock_rows=True,
    )
    if not recheck.can_book:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Not enough trucks available for this schedule. Please choose another date/time.",
        )

    crew = crew_capacity_for_window(
        db,
        payload.scheduled_date,
        payload.scheduled_time_slot,
        payload.pickup_location,
        payload.dropoff_location,
        required_trucks=required_trucks,
    )
    if not crew.can_book:
        raise HTTPException(
            status_code=409,
            detail=crew.message
            or "Not enough free trucks, drivers, and helpers for this date/time. Please choose another schedule.",
        )

    booking = Booking(
        customer_id=user.id,
        pickup_location=payload.pickup_location,
        dropoff_location=payload.dropoff_location,
        service_type=payload.service_type,
        scheduled_date=payload.scheduled_date,
        scheduled_time_slot=payload.scheduled_time_slot,
        cargo_weight_tons=payload.cargo_weight_tons,
        required_truck_count=required_trucks,
        cargo_description=payload.cargo_description,
        cargo_type_category=payload.cargo_type_category,
        estimated_cost=pricing["quoted_total"],
        estimated_toll_budget_php=toll_meta.get("toll_budget_per_truck"),
        toll_matrix_matched=bool(toll_meta.get("matched")),
        toll_estimate_message=toll_meta.get("message"),
        vehicle_class_used=toll_meta.get("vehicle_class"),
        toll_entry_point=toll_meta.get("entry_point"),
        toll_exit_point=toll_meta.get("exit_point"),
        toll_effective_date=_parse_iso_date(toll_meta.get("effective_date")) if toll_meta.get("matched") else None,
        status=BookingStatus.PAYMENT_VERIFICATION,
    )
    db.add(booking)
    db.flush()

    hold = TruckSlotHold(
        booking_id=booking.id,
        schedule_date=payload.scheduled_date,
        time_slot=payload.scheduled_time_slot,
        required_truck_count=required_trucks,
        hold_status=TruckSlotHoldStatus.ON_HOLD,
    )
    db.add(hold)
    return booking


def _finalize_new_booking(db: Session, user: User, booking: Booking) -> Booking:
    db.commit()
    db.refresh(booking)
    subject, html_body = EmailTemplate.booking_confirmation(
        booking_id=booking.id,
        quoted_amount_php=float(booking.estimated_cost or 0),
        scheduled_date=str(booking.scheduled_date),
    )
    send_email_notification(to_email=user.email, subject=subject, html_body=html_body)
    return booking


def _user_assigned_to_booking(db: Session, booking_id: int, user: User) -> bool:
    if user.role == UserRole.DRIVER:
        return (
            db.query(Trip.id)
            .filter(Trip.booking_id == booking_id, Trip.driver_id == user.id)
            .first()
            is not None
        )
    if user.role == UserRole.HELPER:
        return (
            db.query(Trip.id)
            .filter(Trip.booking_id == booking_id, Trip.helper_id == user.id)
            .first()
            is not None
        )
    return False


def _assert_booking_access(db: Session, booking: Booking, user: User) -> None:
    if user.role in {UserRole.ADMIN, UserRole.MANAGER}:
        return
    if user.role == UserRole.CUSTOMER:
        if booking.customer_id != user.id:
            raise HTTPException(status_code=403, detail="Not allowed")
        return
    if user.role == UserRole.DISPATCHER:
        assert_dispatcher_booking_access(db, user, booking.id)
        return
    if _user_assigned_to_booking(db, booking.id, user):
        return
    raise HTTPException(status_code=403, detail="Not allowed")


@router.post("", response_model=BookingRead)
def create_booking(
    payload: BookingCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.CUSTOMER, UserRole.MANAGER, UserRole.ADMIN)),
):
    """Create a new booking with routed road distance and cargo-based customer quote."""
    try:
        booking = _create_booking_record(db, user, payload)
        return _finalize_new_booking(db, user, booking)
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise


@router.post("/with-documents", response_model=BookingRead)
async def create_booking_with_documents(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.CUSTOMER, UserRole.MANAGER, UserRole.ADMIN)),
    pickup_location: str = Form(...),
    dropoff_location: str = Form(...),
    service_type: str = Form("fixed"),
    scheduled_date: date = Form(...),
    scheduled_time_slot: str = Form(...),
    cargo_weight_tons: float = Form(...),
    cargo_description: str = Form(...),
    cargo_type_category: str = Form(...),
    toll_entry_point: str | None = Form(default=None),
    toll_exit_point: str | None = Form(default=None),
    vehicle_class: str | None = Form(default=None),
    distance_km_override: float | None = Form(default=None),
    terms_agreed: str = Form(...),
    terms_signer_name: str | None = Form(default=None),
    cargo_declaration: UploadFile = File(...),
    terms_e_signature: UploadFile = File(...),
):
    """Customer booking submit with cargo declaration upload and electronic terms acceptance."""
    if (terms_agreed or "").strip().lower() not in {"true", "1", "yes", "on"}:
        raise HTTPException(status_code=400, detail="You must accept the Terms & Agreement.")

    try:
        payload = BookingCreate(
            pickup_location=pickup_location,
            dropoff_location=dropoff_location,
            service_type=service_type,
            scheduled_date=scheduled_date,
            scheduled_time_slot=scheduled_time_slot,
            cargo_weight_tons=cargo_weight_tons,
            cargo_description=cargo_description,
            cargo_type_category=cargo_type_category,
            toll_entry_point=(toll_entry_point or None),
            toll_exit_point=(toll_exit_point or None),
            vehicle_class=(vehicle_class or None),
            distance_km_override=distance_km_override,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        booking = _create_booking_record(db, user, payload)
        decl_name, decl_path, decl_at = await save_booking_document(
            booking.id, cargo_declaration, prefix="declaration"
        )
        sig_name, sig_path, _sig_at = await save_terms_e_signature(booking.id, terms_e_signature)
        signed_at = datetime.utcnow()
        signer_name = (terms_signer_name or user.full_name or "").strip() or user.full_name
        client_ip = request.client.host if request.client else None

        booking.cargo_declaration_original_filename = decl_name
        booking.cargo_declaration_storage_path = decl_path
        booking.cargo_declaration_uploaded_at = decl_at
        mark_goods_declaration_pending(booking)

        booking.terms_e_signature_storage_path = sig_path
        booking.terms_signature_signer_name = signer_name
        booking.terms_signature_ip = client_ip
        booking.terms_agreement_version = FLEETOPT_TERMS_VERSION
        booking.terms_agreed_at = signed_at

        abs_sig = resolve_booking_document_path(sig_path)
        pdf_abs = signed_terms_pdf_abs_path(booking.id)
        try:
            generate_signed_terms_pdf(
                booking_id=booking.id,
                customer_name=signer_name,
                user_account_id=user.id,
                signed_at=signed_at,
                ip_address=client_ip,
                signature_png_path=abs_sig,
                output_path=pdf_abs,
            )
        except Exception as exc:
            import logging

            logging.getLogger(__name__).exception(
                "Signed terms PDF generation failed for booking %s", booking.id
            )
            raise HTTPException(
                status_code=500,
                detail="Unable to generate the signed terms agreement PDF. Please try again.",
            ) from exc
        booking.terms_agreement_original_filename = f"FleetOpt-Signed-Terms-Booking-{booking.id}.pdf"
        booking.terms_agreement_storage_path = signed_terms_pdf_relative_path(booking.id)
        booking.terms_agreement_uploaded_at = signed_at
        return _finalize_new_booking(db, user, booking)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Booking could not be saved. Please try again.",
        ) from exc


@router.get("/{booking_id}/documents/cargo-declaration", response_class=FileResponse)
def download_cargo_declaration(
    booking_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    _assert_booking_access(db, booking, user)
    path = resolve_booking_document_path(booking.cargo_declaration_storage_path)
    fname = booking.cargo_declaration_original_filename or path.name
    return FileResponse(path, filename=fname, media_type=media_type_for_path(path))


@router.get("/{booking_id}/documents/terms-agreement", response_class=FileResponse)
def download_terms_agreement(
    booking_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    _assert_booking_access(db, booking, user)
    path = resolve_booking_document_path(booking.terms_agreement_storage_path)
    fname = booking.terms_agreement_original_filename or path.name
    return FileResponse(path, filename=fname, media_type=media_type_for_path(path))


@router.post("/{booking_id}/documents/resubmit", response_model=BookingRead)
async def resubmit_booking_documents(
    booking_id: int,
    cargo_declaration: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.CUSTOMER, UserRole.ADMIN, UserRole.MANAGER)),
):
    """Customer re-uploads revised cargo declaration after admin requested revision."""
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if user.role == UserRole.CUSTOMER and booking.customer_id != user.id:
        raise HTTPException(status_code=403, detail="Not allowed")

    current = effective_goods_declaration_review_status(booking)
    if current != GoodsDeclarationReviewStatus.REVISION_REQUESTED.value:
        raise HTTPException(
            status_code=400,
            detail="Document resubmission is only allowed when a revision has been requested.",
        )

    has_decl = cargo_declaration is not None and bool(cargo_declaration.filename)
    if not has_decl:
        raise HTTPException(status_code=400, detail="Upload a revised cargo declaration.")

    if has_decl and cargo_declaration is not None:
        # Preserve prior version in audit history before replacing the active file pointer.
        prior_path = booking.cargo_declaration_storage_path
        prior_name = booking.cargo_declaration_original_filename
        if prior_path or prior_name:
            from app.models.entities import GoodsDeclarationReviewEvent

            db.add(
                GoodsDeclarationReviewEvent(
                    booking_id=booking.id,
                    action="resubmitted",
                    reason_code=None,
                    remarks="Customer uploaded a revised goods declaration (previous version retained).",
                    document_storage_path=prior_path,
                    document_original_filename=prior_name,
                    actor_id=user.id,
                    actor_role=user.role.value if hasattr(user.role, "value") else str(user.role),
                    revision_number=int(getattr(booking, "goods_declaration_revision_count", 0) or 0),
                )
            )
        decl_name, decl_path, decl_at = await save_booking_document(
            booking.id, cargo_declaration, prefix="declaration"
        )
        booking.cargo_declaration_original_filename = decl_name
        booking.cargo_declaration_storage_path = decl_path
        booking.cargo_declaration_uploaded_at = decl_at

    mark_goods_declaration_resubmitted(booking)
    db.commit()
    db.refresh(booking)
    notify_reviewers_documents_resubmitted(db, booking)
    return _booking_read_payload(booking)


@router.get("/schedule-availability", response_model=BookingScheduleAvailabilityRead)
def booking_schedule_availability(
    scheduled_date: date,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
    cargo_weight_tons: float = Query(default=1.0, ge=0.1, le=168.0),
    pickup_location: str = Query(default=""),
    dropoff_location: str = Query(default=""),
):
    """Open slots require truck-count capacity plus free trucks, drivers, and helpers for the window."""
    from app.models.entities import BookingStatus, User, UserRole
    from app.services.booking_capacity import fleet_operational_pool_size
    from app.services.demo_booking_filter import demo_booking_orm_filter

    required_trucks = trucks_required_for_cargo(cargo_weight_tons)
    has_route = len(pickup_location.strip()) >= 3 and len(dropoff_location.strip()) >= 3
    pickup = pickup_location.strip() if has_route else ""
    dropoff = dropoff_location.strip() if has_route else ""

    active_booking_exists = db.query(Booking.id).filter(
        Booking.status.notin_(
            {
                BookingStatus.CANCELLED,
                BookingStatus.REJECTED,
                BookingStatus.PAYMENT_REJECTED,
                BookingStatus.COMPLETED,
                BookingStatus.EXPIRED,
            }
        ),
        ~demo_booking_orm_filter(Booking.pickup_location, Booking.dropoff_location),
    ).first() is not None

    # With no active workflow rows, route distance cannot affect capacity. Avoid
    # external geocoding/routing calls so a fresh demo database remains usable
    # even when map providers are slow or unavailable.
    if not active_booking_exists:
        off_duty = {"off_duty", "off-duty", "on_break", "break", "unavailable"}
        truck_count = fleet_operational_pool_size(db)
        driver_count = int(
            db.query(User.id)
            .filter(
                User.role == UserRole.DRIVER,
                ~func.lower(func.coalesce(User.availability_status, "")).in_(off_duty),
            )
            .count()
        )
        helper_count = int(
            db.query(User.id)
            .filter(
                User.role == UserRole.HELPER,
                ~func.lower(func.coalesce(User.availability_status, "")).in_(off_duty),
            )
            .count()
        )
        free_capacity = min(truck_count, driver_count, helper_count)
        slots = {slot: free_capacity >= required_trucks for slot in BOOKING_TIME_SLOTS}
        available_by_slot = {slot: free_capacity for slot in BOOKING_TIME_SLOTS}
        return BookingScheduleAvailabilityRead(
            scheduled_date=scheduled_date,
            slots=slots,
            required_trucks=required_trucks,
            available_trucks_by_slot=available_by_slot,
        )

    if has_route:
        slots = availability_for_date(
            db,
            scheduled_date,
            cargo_weight_tons,
            pickup,
            dropoff,
        )
        available_by_slot = available_trucks_by_slot_for_date(
            db,
            scheduled_date,
            pickup,
            dropoff,
        )
    else:
        slots = {}
        available_by_slot = {}
        for slot in BOOKING_TIME_SLOTS:
            cap = get_available_truck_count(
                db,
                scheduled_date,
                slot,
                required_trucks=required_trucks,
                lock_rows=False,
            )
            slots[slot] = cap.can_book
            available_by_slot[slot] = cap.available_trucks

    for slot in BOOKING_TIME_SLOTS:
        if not slots.get(slot):
            continue
        crew = crew_capacity_for_window(
            db,
            scheduled_date,
            slot,
            pickup or "TBD pickup",
            dropoff or "TBD dropoff",
            required_trucks=required_trucks,
        )
        if not crew.can_book:
            slots[slot] = False
        # Expose the limiting free-crew count alongside truck capacity for UI hints.
        available_by_slot[slot] = min(
            available_by_slot.get(slot, 0),
            crew.trucks,
            crew.drivers,
            crew.helpers,
        )

    return BookingScheduleAvailabilityRead(
        scheduled_date=scheduled_date,
        slots=slots,
        required_trucks=required_trucks,
        available_trucks_by_slot=available_by_slot,
    )


@router.get("", response_model=list[BookingRead])
def list_bookings(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    cid = user.id if user.role == UserRole.CUSTOMER else None
    _sync_bookings_approved_from_verified_payments(db, cid)
    query = db.query(Booking)
    if user.role == UserRole.CUSTOMER:
        query = query.filter(Booking.customer_id == user.id)
    rows = query.order_by(Booking.created_at.desc()).all()
    if user.role == UserRole.DISPATCHER:
        rows = filter_bookings_for_dispatcher(db, user, rows)
    if user.role in {UserRole.DRIVER, UserRole.HELPER}:
        assigned_booking_ids = {
            int(row[0])
            for row in (
                db.query(Trip.booking_id)
                .filter(
                    Trip.booking_id.isnot(None),
                    Trip.driver_id == user.id if user.role == UserRole.DRIVER else Trip.helper_id == user.id,
                )
                .all()
            )
            if row[0] is not None
        }
        rows = [row for row in rows if int(row.id) in assigned_booking_ids]
    return [_booking_read_payload(b) for b in rows]


@router.get("/{booking_id}", response_model=BookingRead)
def get_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    cid = user.id if user.role == UserRole.CUSTOMER else None
    _sync_bookings_approved_from_verified_payments(db, cid)
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    _assert_booking_access(db, booking, user)
    return _booking_read_payload(booking)


@router.post("/{booking_id}/cancel")
def cancel_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    _assert_booking_access(db, booking, user)

    if user.role == UserRole.CUSTOMER:
        if booking.status not in (BookingStatus.PENDING_PAYMENT, BookingStatus.PAYMENT_VERIFICATION):
            raise HTTPException(
                status_code=400,
                detail="Cancellation is only allowed before payment is verified.",
            )
    else:
        if booking.status in (BookingStatus.COMPLETED, BookingStatus.CANCELLED):
            raise HTTPException(
                status_code=400,
                detail="Completed or cancelled bookings can no longer be cancelled.",
            )

    booking.status = BookingStatus.CANCELLED
    release_booking_trips(db, booking.id)
    db.query(TruckSlotHold).filter(TruckSlotHold.booking_id == booking.id).update(
        {"hold_status": TruckSlotHoldStatus.RELEASED}
    )
    db.commit()
    return {"status": "cancelled"}


@router.patch("/{booking_id}/customs/validate")
def validate_booking_customs(
    booking_id: int,
    payload: BookingCustomsValidate,
    db: Session = Depends(get_db),
    reviewer: User = Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER)),
):
    """Admin validates customer customs info. Does not alter estimated_cost or dispatch status."""
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if payload.validated:
        booking.customs_admin_validated = True
        booking.customs_validated_by_id = reviewer.id
        booking.customs_validated_at = datetime.utcnow()
        if payload.customs_admin_notes is not None:
            booking.customs_admin_notes = payload.customs_admin_notes
        if payload.customs_validated_additional_charges_php is not None:
            booking.customs_validated_additional_charges_php = payload.customs_validated_additional_charges_php
        elif booking.customs_additional_charges_php is not None:
            booking.customs_validated_additional_charges_php = booking.customs_additional_charges_php
    else:
        booking.customs_admin_validated = False
        booking.customs_validated_by_id = None
        booking.customs_validated_at = None
        if payload.customs_admin_notes is not None:
            booking.customs_admin_notes = payload.customs_admin_notes

    db.commit()
    db.refresh(booking)
    return BookingRead.model_validate(booking).model_dump(mode="json")


@router.get("/{booking_id}/cargo-type/screening")
def cargo_type_screening_preview(
    booking_id: int,
    category: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER)),
):
    """Preview restricted/contraband warning flags — informational only."""
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    chosen = (category or booking.cargo_type_category or "").strip().lower() or None
    result = screen_cargo_type(category=chosen, cargo_description=booking.cargo_description)
    return CargoTypeScreeningRead.model_validate(result).model_dump(mode="json")


@router.patch("/{booking_id}/cargo-type/validate")
def validate_booking_cargo_type(
    booking_id: int,
    payload: BookingCargoTypeValidate,
    db: Session = Depends(get_db),
    reviewer: User = Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER)),
):
    """Admin classifies cargo type and verifies booking cargo. Warning flags do not block validation."""
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    try:
        apply_cargo_type_validation(
            booking,
            validated=payload.validated,
            category=payload.cargo_type_category if payload.cargo_type_category is not None else booking.cargo_type_category,
            reviewer=reviewer,
            admin_notes=payload.cargo_type_admin_notes,
            cargo_description=payload.cargo_description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    db.commit()
    db.refresh(booking)
    return BookingRead.model_validate(booking).model_dump(mode="json")


@router.get("/{booking_id}/pre-delivery-checklist")
def booking_pre_delivery_checklist(
    booking_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    _assert_booking_access(db, booking, user)
    return build_pre_delivery_checklist(db, booking)


@router.patch("/{booking_id}/pre-delivery-checklist")
def update_pre_delivery_checklist(
    booking_id: int,
    payload: PreDeliveryChecklistValidate,
    db: Session = Depends(get_db),
    reviewer: User = Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER, UserRole.DISPATCHER)),
):
    """Mark declaration / cargo type checks after review — does not alter dispatch assignment flow."""
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if reviewer.role == UserRole.DISPATCHER:
        assert_dispatcher_booking_access(db, reviewer, booking.id)

    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="No checklist fields to update.")

    if "goods_declaration_validated" in data:
        if data["goods_declaration_validated"] and not (
            booking.cargo_declaration_storage_path or booking.cargo_declaration_original_filename
        ):
            raise HTTPException(status_code=400, detail="Cargo declaration document must be on file before validation.")
        booking.goods_declaration_validated = bool(data["goods_declaration_validated"])
        if data["goods_declaration_validated"]:
            booking.goods_declaration_review_status = "approved"
        elif booking.goods_declaration_review_status == "approved":
            booking.goods_declaration_review_status = "pending"

    if "cargo_type_validated" in data:
        desc = (booking.cargo_description or "").strip()
        if data["cargo_type_validated"] and len(desc) < 3:
            raise HTTPException(status_code=400, detail="Cargo description is required before cargo type validation.")
        booking.cargo_type_validated = bool(data["cargo_type_validated"])

    db.commit()
    db.refresh(booking)
    return build_pre_delivery_checklist(db, booking)


@router.get("/{booking_id}/tracking-details")
def booking_tracking_details(
    booking_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    _assert_booking_access(db, booking, user)

    assignment_rows = build_assignments_for_booking(db, booking)
    road_km = booking_pickup_dropoff_distance_km(booking)

    booking_effective_status = (
        aggregate_customer_display_from_assignment_rows(assignment_rows)
        if assignment_rows
        else (booking.status.value if hasattr(booking.status, "value") else str(booking.status))
    )

    payload: dict = {
        "booking": {
            "id": booking.id,
            "status": booking_effective_status,
            "pickup_location": booking.pickup_location,
            "dropoff_location": booking.dropoff_location,
            "cargo_weight_tons": float(booking.cargo_weight_tons),
            "scheduled_date": booking.scheduled_date.isoformat(),
            "scheduled_time_slot": booking.scheduled_time_slot,
            "required_truck_count": int(booking.required_truck_count or 1),
            "road_distance_km": float(road_km) if road_km is not None else None,
        },
        "assignments": assignment_rows,
    }

    if user.role != UserRole.CUSTOMER:
        logs = (
            db.query(OperationalLog)
            .filter(OperationalLog.booking_id == booking_id)
            .order_by(OperationalLog.created_at.desc())
            .all()
        )
        disp_ids = list({lg.dispatcher_id for lg in logs})
        dispatchers = db.query(User).filter(User.id.in_(disp_ids)).all() if disp_ids else []
        dmap = {u.id: (u.full_name or f"User #{u.id}") for u in dispatchers}
        payload["operational_logs"] = [
            {
                "id": lg.id,
                "trip_id": lg.trip_id,
                "booking_id": lg.booking_id,
                "dispatcher_id": lg.dispatcher_id,
                "dispatcher_name": dmap.get(lg.dispatcher_id),
                "report_type": lg.report_type,
                "report_type_label": REPORT_TYPE_LABELS.get(lg.report_type, lg.report_type),
                "priority_level": lg.priority_level,
                "operational_details": lg.operational_details,
                "attachment_url": lg.attachment_url,
                "created_at": lg.created_at.isoformat() if lg.created_at else None,
            }
            for lg in logs
        ]

        g_rows = list_general_operational_reports(db, booking_id=booking_id, limit=80)
        g_driver_ids = list({r.driver_id for r in g_rows})
        g_drivers = db.query(User).filter(User.id.in_(g_driver_ids)).all() if g_driver_ids else []
        g_dmap = {u.id: (u.full_name or f"User #{u.id}") for u in g_drivers}
        payload["general_operational_reports"] = [
            {
                "id": gr.id,
                "trip_id": gr.trip_id,
                "booking_id": gr.booking_id,
                "driver_id": gr.driver_id,
                "driver_name": g_dmap.get(gr.driver_id),
                "category": gr.category,
                "category_label": GENERAL_OPS_CATEGORY_LABELS.get(
                    gr.category, gr.category.replace("_", " ").title()
                ),
                "trip_status": gr.status,
                "trip_status_label": GENERAL_OPS_TRIP_STATUS_LABELS.get(gr.status, gr.status.replace("_", " ").title())
                if gr.status
                else None,
                "report_date": gr.report_date.isoformat(),
                "starting_odometer_km": gr.starting_odometer_km,
                "ending_odometer_km": gr.ending_odometer_km,
                "fuel_consumed": gr.fuel_consumed,
                "description": gr.description,
                "notes": gr.notes,
                "attachment_url": gr.attachment_url,
                "created_at": gr.created_at.isoformat() if gr.created_at else None,
            }
            for gr in g_rows
        ]

    return payload


@router.put("/{booking_id}/admin/toll-estimate", response_model=BookingRead)
def admin_override_booking_toll(
    booking_id: int,
    payload: AdminBookingTollOverride,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER, UserRole.DISPATCHER)),
):
    """Manual toll plaza + optional distance override — toll fee from Toll Matrix only."""
    from app.services.booking_pricing import pricing_with_toll_matrix
    from app.services.toll_matrix import DEFAULT_VEHICLE_CLASS

    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found.")

    has_manual_toll = bool(payload.toll_entry_point and payload.toll_exit_point)
    dist = resolve_quote_distance_km(
        booking.pickup_location,
        booking.dropoff_location,
        settings,
        distance_km_override=payload.distance_km_override,
        allow_unverified_with_manual_toll=has_manual_toll,
    )
    pricing, toll_meta = pricing_with_toll_matrix(
        db,
        pickup_location=booking.pickup_location,
        dropoff_location=booking.dropoff_location,
        cargo_weight_tons=float(booking.cargo_weight_tons or 0),
        distance_km=dist.distance_km,
        settings=settings,
        as_of_date=booking.scheduled_date,
        vehicle_class=payload.vehicle_class or DEFAULT_VEHICLE_CLASS,
        manual_entry=payload.toll_entry_point,
        manual_exit=payload.toll_exit_point,
    )

    booking.estimated_cost = pricing["quoted_total"]
    booking.estimated_toll_budget_php = toll_meta.get("toll_budget_per_truck")
    booking.toll_matrix_matched = bool(toll_meta.get("matched"))
    booking.toll_estimate_message = toll_meta.get("message")
    booking.vehicle_class_used = toll_meta.get("vehicle_class")
    booking.toll_entry_point = toll_meta.get("entry_point") or payload.toll_entry_point
    booking.toll_exit_point = toll_meta.get("exit_point") or payload.toll_exit_point
    booking.toll_effective_date = _parse_iso_date(toll_meta.get("effective_date")) if toll_meta.get("matched") else None

    db.commit()
    db.refresh(booking)
    return booking
