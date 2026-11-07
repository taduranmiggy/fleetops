from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, field_validator, model_validator

from app.constants.booking_time_slots import BOOKING_TIME_SLOTS
from app.models.entities import BookingStatus, CargoTypeCategory, CustomsClearanceStatus, ServiceType

CUSTOMS_CLEARANCE_STATUSES = {s.value for s in CustomsClearanceStatus}
CARGO_TYPE_CATEGORY_VALUES = frozenset(c.value for c in CargoTypeCategory)


class BookingCreate(BaseModel):
    pickup_location: str
    dropoff_location: str
    service_type: ServiceType
    scheduled_date: date
    scheduled_time_slot: str
    cargo_weight_tons: float
    cargo_description: str
    cargo_type_category: str
    toll_entry_point: str | None = None
    toll_exit_point: str | None = None
    vehicle_class: str | None = None
    distance_km_override: float | None = None

    @field_validator("cargo_weight_tons")
    @classmethod
    def validate_weight(cls, v: float) -> float:
        # Four trucks × 42 t = 168 t max per synchronized convoy.
        if v <= 0 or v > 168:
            raise ValueError("Cargo weight must be between 0.1 and 168 metric tons (fleet limit)")
        return v

    @field_validator("cargo_description")
    @classmethod
    def validate_cargo_description(cls, v: str) -> str:
        t = " ".join((v or "").split()).strip()
        if len(t) < 3:
            raise ValueError("Cargo description is required (at least 3 characters)")
        if len(t) > 500:
            raise ValueError("Cargo description must be at most 500 characters")
        return t

    @field_validator("cargo_type_category")
    @classmethod
    def validate_cargo_type_category(cls, v: str) -> str:
        key = (v or "").strip().lower()
        if key not in CARGO_TYPE_CATEGORY_VALUES:
            raise ValueError(
                f"Cargo type category must be one of: {', '.join(sorted(CARGO_TYPE_CATEGORY_VALUES))}"
            )
        return key

    @field_validator("pickup_location", "dropoff_location")
    @classmethod
    def validate_location(cls, v: str) -> str:
        if not v or len(v) < 3:
            raise ValueError("Location must be at least 3 characters")
        return v.strip()

    @field_validator("scheduled_time_slot")
    @classmethod
    def validate_time_slot(cls, v: str) -> str:
        t = (v or "").strip()
        if t not in BOOKING_TIME_SLOTS:
            raise ValueError(f"Time slot must be one of: {', '.join(BOOKING_TIME_SLOTS)}")
        return t

    @field_validator("scheduled_date")
    @classmethod
    def validate_scheduled_date(cls, v: date) -> date:
        if v < date.today():
            raise ValueError("Scheduled date cannot be in the past.")
        return v

    @field_validator("distance_km_override")
    @classmethod
    def validate_distance_override(cls, v: float | None) -> float | None:
        if v is None:
            return None
        if v <= 0 or v > 5000:
            raise ValueError("Distance override must be between 0.1 and 5000 km")
        return round(float(v), 2)

    @model_validator(mode="after")
    def validate_route_points(self):
        if self.pickup_location.strip().lower() == self.dropoff_location.strip().lower():
            raise ValueError("Pickup and delivery locations cannot be the same.")
        return self


class BookingScheduleAvailabilityRead(BaseModel):
    """scheduled_time_slot → True when four trucks can still serve this load (ETA overlap)."""

    scheduled_date: date
    slots: dict[str, bool]
    required_trucks: int = 1
    available_trucks_by_slot: dict[str, int] = {}
    availability_message: str | None = None


class BookingRead(BaseModel):
    id: int
    customer_id: int
    pickup_location: str
    dropoff_location: str
    service_type: ServiceType
    scheduled_date: date
    scheduled_time_slot: str
    cargo_weight_tons: float
    required_truck_count: int
    cargo_description: str | None
    estimated_cost: float
    actual_cost: float | None
    status: BookingStatus
    approved_by_id: int | None
    approved_at: datetime | None
    rejection_reason: str | None
    created_at: datetime
    updated_at: datetime
    latest_location: str | None = None
    cargo_declaration_original_filename: str | None = None
    cargo_declaration_uploaded_at: datetime | None = None
    cargo_declaration_file_url: str | None = None
    terms_agreement_original_filename: str | None = None
    terms_agreement_uploaded_at: datetime | None = None
    terms_agreement_file_url: str | None = None
    terms_agreed_at: datetime | None = None
    terms_signature_signer_name: str | None = None
    terms_signature_ip: str | None = None
    terms_agreement_version: str | None = None
    terms_e_signed: bool = False
    customs_clearance_status: str | None = None
    customs_tariff_notes: str | None = None
    customs_additional_charges_php: float | None = None
    customs_customer_updated_at: datetime | None = None
    customs_admin_validated: bool = False
    customs_validated_by_id: int | None = None
    customs_validated_at: datetime | None = None
    customs_admin_notes: str | None = None
    customs_validated_additional_charges_php: float | None = None
    goods_declaration_validated: bool = False
    cargo_type_validated: bool = False
    goods_declaration_review_status: str | None = None
    goods_declaration_review_status_label: str | None = None
    goods_declaration_review_remarks: str | None = None
    goods_declaration_review_remarks_history: str | None = None
    goods_declaration_revision_count: int = 0
    goods_declaration_revision_limit: int = 3
    goods_declaration_reviewed_at: datetime | None = None
    goods_declaration_reviewed_by_id: int | None = None
    booking_qr_payload: str | None = None
    booking_qr_code: str | None = None
    booking_qr_ready: bool = False
    booking_qr_verified: bool = False
    booking_qr_verified_at: datetime | None = None
    booking_qr_verified_method: str | None = None
    cargo_type_category: str | None = None
    cargo_type_admin_notes: str | None = None
    cargo_restricted_flag: bool = False
    cargo_restricted_reasons: str | None = None
    cargo_type_validated_by_id: int | None = None
    cargo_type_validated_at: datetime | None = None
    estimated_toll_budget_php: float | None = None
    toll_matrix_matched: bool = False
    toll_estimate_message: str | None = None
    vehicle_class_used: str | None = None
    toll_entry_point: str | None = None
    toll_exit_point: str | None = None
    toll_effective_date: Optional[date] = None

    class Config:
        from_attributes = True


class PreDeliveryChecklistValidate(BaseModel):
    goods_declaration_validated: bool | None = None
    cargo_type_validated: bool | None = None


class BookingCustomsUpdate(BaseModel):
    customs_clearance_status: str | None = None
    customs_tariff_notes: str | None = None
    customs_additional_charges_php: float | None = None

    @field_validator("customs_clearance_status")
    @classmethod
    def validate_customs_status(cls, v: str | None) -> str | None:
        if v is None:
            return None
        t = v.strip()
        if t not in CUSTOMS_CLEARANCE_STATUSES:
            raise ValueError(f"Clearance status must be one of: {', '.join(sorted(CUSTOMS_CLEARANCE_STATUSES))}")
        return t

    @field_validator("customs_tariff_notes")
    @classmethod
    def validate_tariff_notes(cls, v: str | None) -> str | None:
        if v is None:
            return None
        t = v.strip()
        if len(t) > 2000:
            raise ValueError("Tariff notes must be at most 2000 characters")
        return t or None

    @field_validator("customs_additional_charges_php")
    @classmethod
    def validate_additional_charges(cls, v: float | None) -> float | None:
        if v is None:
            return None
        if v < 0 or v > 50_000_000:
            raise ValueError("Additional charges must be between 0 and 50,000,000 PHP")
        return round(v, 2)


class BookingCustomsValidate(BaseModel):
    validated: bool = True
    customs_admin_notes: str | None = None
    customs_validated_additional_charges_php: float | None = None

    @field_validator("customs_admin_notes")
    @classmethod
    def validate_admin_notes(cls, v: str | None) -> str | None:
        if v is None:
            return None
        t = v.strip()
        if len(t) > 2000:
            raise ValueError("Admin notes must be at most 2000 characters")
        return t or None

    @field_validator("customs_validated_additional_charges_php")
    @classmethod
    def validate_validated_charges(cls, v: float | None) -> float | None:
        if v is None:
            return None
        if v < 0 or v > 50_000_000:
            raise ValueError("Validated additional charges must be between 0 and 50,000,000 PHP")
        return round(v, 2)


class BookingApprovalRequest(BaseModel):
    approved: bool
    rejection_reason: str | None = None


class BookingStatusUpdate(BaseModel):
    status: BookingStatus
