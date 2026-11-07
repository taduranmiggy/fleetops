/**
 * Typed wrapper around the booking → trip → payment lifecycle.
 */
import { apiGet, apiPatch, apiPost, apiPostMultipart } from "./api";
import { appendEvidenceToFormData } from "./evidenceFormData";
import type { EvidenceCaptureMetadata } from "./evidenceCapture";
import type { CargoTypeScreening, CargoTypeValidationAdminRow } from "./cargoTypeCategories";
import type { DispatcherAssignmentRow, DispatcherUserOption } from "./dispatcherAssignment";

export type BookingStatus =
  | "pending_payment"
  | "payment_verification"
  | "payment_verified"
  | "ready_for_assignment"
  | "pending_approval"
  | "approved"
  | "assigned"
  | "accepted"
  | "enroute"
  | "loading"
  | "out_for_delivery"
  | "completed"
  | "cancelled"
  | "rejected"
  | "payment_rejected"
  | "expired";

export type CustomerBookingAssignment = {
  trip_id: number;
  booking_id?: number;
  trip_status: string;
  helper_progress_status: string | null;
  truck: {
    id: number;
    code: string;
    plate_number?: string;
    model_name: string | null;
    capacity_tons: number;
  } | null;
  driver: { id: number; name: string } | null;
  helper: { id: number; name: string } | null;
  latest_location_name: string | null;
  location_updates: Array<{
    location_name: string;
    remarks: string | null;
    photo_url: string | null;
    created_at: string;
    booking_id?: number;
    trip_id?: number;
    helper_id?: number | null;
    helper_name?: string | null;
    driver_id?: number | null;
    driver_name?: string | null;
    delivery_status?: string;
    latitude?: number | null;
    longitude?: number | null;
  }>;
  status_timeline: Array<{
    status: string;
    location_name: string;
    remarks: string | null;
    photo_url: string | null;
    created_at: string;
    booking_id?: number;
    trip_id?: number;
    helper_id?: number | null;
    helper_name?: string | null;
    driver_id?: number | null;
    driver_name?: string | null;
    delivery_status?: string;
    latitude?: number | null;
    longitude?: number | null;
  }>;
  timeline_events?: CrewTimelineEvent[];
};

export type CustomerBookingRow = Booking & {
  display_status: string;
  display_status_label: string;
  can_cancel: boolean;
  assignments: CustomerBookingAssignment[];
};

export type CustomerBookingHistoryRow = CustomerBookingRow & {
  primary_trip_id: number | null;
  closed_at: string | null;
};

export type Booking = {
  id: number;
  customer_id: number;
  pickup_location: string;
  dropoff_location: string;
  service_type: "fixed" | "customized";
  scheduled_date: string;
  scheduled_time_slot: string;
  cargo_weight_tons: number;
  required_truck_count: number;
  cargo_description: string | null;
  estimated_cost: number;
  actual_cost: number | null;
  status: BookingStatus;
  approved_by_id: number | null;
  approved_at: string | null;
  rejection_reason: string | null;
  created_at: string;
  updated_at: string;
  latest_location?: string | null;
  cargo_declaration_original_filename?: string | null;
  cargo_declaration_uploaded_at?: string | null;
  cargo_declaration_file_url?: string | null;
  terms_agreement_original_filename?: string | null;
  terms_agreement_uploaded_at?: string | null;
  terms_agreement_file_url?: string | null;
  terms_agreed_at?: string | null;
  terms_signature_signer_name?: string | null;
  terms_agreement_version?: string | null;
  terms_e_signed?: boolean;
  customs_clearance_status?: string | null;
  customs_tariff_notes?: string | null;
  customs_additional_charges_php?: number | null;
  customs_customer_updated_at?: string | null;
  customs_admin_validated?: boolean;
  customs_validated_by_id?: number | null;
  customs_validated_at?: string | null;
  customs_admin_notes?: string | null;
  customs_validated_additional_charges_php?: number | null;
  goods_declaration_validated?: boolean;
  cargo_type_validated?: boolean;
  goods_declaration_review_status?: string | null;
  goods_declaration_review_status_label?: string | null;
  goods_declaration_review_remarks?: string | null;
  goods_declaration_review_remarks_history?: string | null;
  goods_declaration_revision_count?: number;
  goods_declaration_revision_limit?: number;
  goods_declaration_reviewed_at?: string | null;
  goods_declaration_reviewed_by_id?: number | null;
  booking_qr_payload?: string | null;
  booking_qr_code?: string | null;
  booking_qr_ready?: boolean;
  booking_qr_verified?: boolean;
  booking_qr_verified_at?: string | null;
  delivery_verification_ready?: boolean;
  delivery_verification_active?: boolean;
  delivery_verification_used?: boolean;
  delivery_verification_qr_payload?: string | null;
  delivery_verification_code?: string | null;
  delivery_verification_created_at?: string | null;
  delivery_verification_used_at?: string | null;
  delivery_verification_method?: "qr" | "code" | null;
  cargo_type_category?: string | null;
  cargo_type_admin_notes?: string | null;
  cargo_restricted_flag?: boolean;
  cargo_restricted_reasons?: string | null;
  cargo_type_validated_by_id?: number | null;
  cargo_type_validated_at?: string | null;
  estimated_toll_budget_php?: number | null;
  toll_matrix_matched?: boolean;
  toll_estimate_message?: string | null;
  vehicle_class_used?: string | null;
  toll_entry_point?: string | null;
  toll_exit_point?: string | null;
  toll_effective_date?: string | null;
};

export type GoodsDeclarationAdminRow = {
  booking_id: number;
  customer_id: number;
  status: string;
  pickup_location: string;
  dropoff_location: string;
  cargo_description: string | null;
  cargo_weight_tons: number;
  cargo_declaration_original_filename: string | null;
  cargo_declaration_uploaded_at: string | null;
  cargo_declaration_file_url?: string | null;
  goods_declaration_review_status: string | null;
  goods_declaration_review_status_label: string;
  goods_declaration_review_remarks: string | null;
  goods_declaration_review_remarks_history?: string | null;
  goods_declaration_revision_count?: number;
  goods_declaration_revision_limit?: number;
  goods_declaration_reviewed_at: string | null;
  goods_declaration_reviewed_by_id: number | null;
  review_history?: Array<{
    id: number;
    action: string;
    reason_code: string | null;
    remarks: string | null;
    document_original_filename: string | null;
    actor_id: number | null;
    actor_role: string | null;
    revision_number: number;
    created_at: string | null;
  }>;
};

export type PreDeliveryChecklistItem = {
  key: string;
  label: string;
  passed: boolean;
  detail: string;
};

export type PreDeliveryChecklist = {
  booking_id: number;
  all_passed: boolean;
  ready_for_delivery: boolean;
  items: PreDeliveryChecklistItem[];
};

export type TripBookingSummary = {
  id: number;
  customer_id?: number;
  customer_name?: string | null;
  customer_company_name?: string | null;
  paid_amount_verified?: number | null;
  pickup_location: string;
  dropoff_location: string;
  scheduled_date: string;
  scheduled_time_slot: string;
  cargo_weight_tons: number;
  cargo_description: string | null;
  estimated_cost: number;
  status: string;
};

export type TripTruckSummary = {
  id: number;
  code: string;
  capacity_tons: number;
  model_name?: string | null;
  plate_number?: string | null;
  /** Fleet DB status (e.g. available, maintenance). */
  status?: string | null;
  availability_status?: string | null;
};

/** Shared driver/helper assigned-leg row from GET /driver/bookings and GET /helper/bookings. */
export type CrewTimelineEvent = {
  at: string;
  kind: "milestone" | "location";
  code: string;
  title: string;
  detail: string;
  remarks: string | null;
  photo_url: string | null;
  submitted_by: string | null;
  update_index?: number;
  booking_id?: number;
  trip_id?: number;
  helper_id?: number | null;
  driver_id?: number | null;
  driver_name?: string | null;
  delivery_status?: string | null;
  evidence_verification_label?: string | null;
  evidence_review_required?: boolean;
  evidence_latitude?: number | null;
  evidence_longitude?: number | null;
  evidence_device_captured_at?: string | null;
};

export type DriverTripNotificationRow = {
  id: number;
  trip_id: number | null;
  booking_id: number;
  kind: "assigned" | "updated" | string;
  schedule_summary: string;
  route_summary: string;
  required_action: string;
  read: boolean;
  read_at: string | null;
  created_at: string | null;
};

export type CustomerNotificationRow = {
  id: number;
  booking_id: number | null;
  kind: "document_revision" | "document_rejected" | "support_received" | string;
  title: string;
  message: string;
  required_action: string;
  link_path: string;
  read: boolean;
  read_at: string | null;
  dismissed: boolean;
  dismissed_at: string | null;
  created_at: string | null;
};

export type CrewSchedulingPlot = {
  assigned_at: string | null;
  pickup_date: string | null;
  pickup_time_slot: string | null;
  pickup_location: string;
  delivery_at: string | null;
  delivery_location: string;
  route_waypoints: string[];
  route_distance_km: number;
  duration_hours: number;
  truck_code: string | null;
  truck_model: string | null;
  driver_name: string | null;
  helper_name: string | null;
  status: string;
  trip_status: string;
};

export type DeliveryReceivingStatus = {
  trip_id: number;
  receiving_document_uploaded: boolean;
  receiving_document_path: string | null;
  receiving_document_uploaded_at: string | null;
  qr_verified: boolean;
  qr_verified_at: string | null;
  qr_payload: string | null;
  digital_signature_uploaded: boolean;
  digital_signature_path: string | null;
  digital_signature_uploaded_at: string | null;
  ready_for_completion: boolean;
};

export type DeliveryVerificationResult = {
  booking_id: number;
  trip_ids: number[];
  status: "completed";
  completed_at: string;
  helper_id: number;
  verification_method: "qr" | "code";
  message: string;
};

export type CrewAssignedBookingRow = {
  trip_id: number;
  booking_id: number;
  trip_status: string;
  helper_progress_status: string | null;
  operational_status: string;
  location_updates_submitted: number;
  required_location_updates: number;
  location_update_count: number;
  distance_km: number;
  road_distance_km: number | null;
  assigned_at?: string | null;
  estimated_delivery_time?: string | null;
  duration_hours?: number;
  route_path?: string;
  route_waypoints?: string[];
  scheduling_plot?: CrewSchedulingPlot;
  driver_name: string | null;
  helper_name: string | null;
  driver_profile: { rating: number; compliance_status: string } | null;
  helper_profile: { rating: number } | null;
  latest_location: string | null;
  latest_location_name: string | null;
  payment_status: string;
  payment_latest_amount_php: number | null;
  booking_status: string | null;
  truck_assignment_status: string | null;
  completed_at: string | null;
  pod_notes: string | null;
  delivery_receiving?: DeliveryReceivingStatus;
  pre_delivery_checklist?: PreDeliveryChecklist;
  pre_delivery_ready?: boolean;
  pre_delivery_block_message?: string | null;
  booking_qr_verified?: boolean;
  booking_qr_verified_at?: string | null;
  booking_qr_ready?: boolean;
  timeline_events: CrewTimelineEvent[];
  location_updates: Array<{
    id: number;
    location_name: string;
    remarks: string | null;
    photo_url: string | null;
    created_at: string;
    helper_id: number;
    submitted_by: string | null;
  }>;
  status_updates: Array<{
    id: number;
    status: string;
    location_name: string;
    remarks: string | null;
    photo_url: string | null;
    created_at: string;
    helper_id: number;
    submitted_by: string | null;
  }>;
  proof_photo_urls: string[];
  general_operational_reports: Array<{
    id: number;
    category: string;
    status: string | null;
    report_date: string;
    description: string;
    notes: string | null;
    attachment_url: string | null;
    created_at: string;
  }>;
  vehicle_issue_reports: Array<{
    id: number;
    issue_type: string;
    priority: string;
    description: string;
    attachment_url: string | null;
    status: string;
    created_at: string;
  }>;
  recent_locations: Array<{
    location_name: string;
    remarks: string | null;
    photo_url: string | null;
    created_at: string;
  }>;
  booking: TripBookingSummary | null;
  truck: TripTruckSummary | null;
};

export type Trip = {
  id: number;
  booking_id: number;
  truck_id: number;
  driver_id: number;
  dispatcher_id: number | null;
  route_path: string;
  distance_km: number;
  toll_cost: number;
  fuel_cost: number;
  labor_cost: number;
  driver_allowance_php?: number;
  helper_allowance_php?: number;
  duration_hours: number;
  status: string;
  assigned_at: string | null;
  accepted_at: string | null;
  departure_time: string | null;
  arrival_pickup_time: string | null;
  loading_start_time: string | null;
  loading_end_time: string | null;
  departure_delivery_time: string | null;
  arrival_delivery_time: string | null;
  completed_at: string | null;
  proof_of_delivery: string | null;
  pod_notes: string | null;
  latest_location: string | null;
  estimated_delivery_time: string | null;
  helper_id?: number | null;
  helper_name?: string | null;
  helper_progress_status?: string | null;
  helper_last_proof_path?: string | null;
  /** Helper workflow slug (assigned, for_pickup, picked_up, …). */
  operational_status?: string;
  operational_status_label?: string;
  /** Routed pickup→dropoff km when available. */
  road_distance_km?: number | null;
  driver_name?: string | null;
  location_updates?: Array<{
    location_name: string;
    remarks: string | null;
    photo_url: string | null;
    created_at: string;
  }>;
  status_timeline?: Array<{
    status: string;
    location_name: string;
    remarks: string | null;
    photo_url: string | null;
    created_at: string;
  }>;
  booking?: TripBookingSummary | null;
  truck?: TripTruckSummary | null;
};

export type DriverDashboardSummary = {
  generated_at: string;
  crew_role?: "driver" | "helper";
  attendance: {
    has_open_shift: boolean;
    check_in_at: string | null;
    can_check_in: boolean;
  };
  assignments_today: {
    total_assigned_today: number;
    active_trips: number;
    completed_today: number;
    completed_legs_total: number;
  };
  distance_loaded_km: {
    total_km: number;
    average_km: number;
    trip_count: number;
  };
  fuel_completed_php: number;
  trip_labor_completed_php: number;
  completion_rate_percent: number;
  completion_counts: {
    completed_assigned_legs: number;
    assigned_legs_excluded_cancelled: number;
  };
  driver_profile: {
    base_salary_php: number;
    deductions_php: number;
    net_salary_php: number;
    compliance_status: string;
    rating: number;
  } | null;
  helper_profile?: {
    base_salary_php: number;
    rating: number;
  } | null;
};

export type DriverPayHistoryRow = {
  trip_id: number;
  booking_id: number;
  completed_at: string | null;
  period_label: string;
  route_label: string;
  cargo_weight_tons: number;
  distance_km: number;
  driver_pay: number;
  bonus: number;
  deduction: number;
  total_pay: number;
  status: string;
};

export type DriverPaySummary = {
  period_start: string;
  period_end: string;
  period_label: string;
  trips_completed: number;
  total_distance_km: number;
  base_earnings: number;
  bonus: number;
  deductions: number;
  current_total: number;
  driver_share_formula: {
    description: string;
    cargo_gross_php_per_ton: number;
    driver_share_rate: number;
  };
  payroll_note: string;
  payment_history: DriverPayHistoryRow[];
};

export type DriverVehicleIssueSelectableTrip = {
  trip_id: number;
  booking_id: number;
  truck_plate: string;
  truck_model: string | null;
  route_label: string;
  pickup_location: string;
  dropoff_location: string;
  helper_id: number | null;
  helper_name: string | null;
  trip_status: string;
  operational_status: string;
  scheduled_date: string | null;
};

export type DriverVehicleIssueReportResponse = {
  id: number;
  booking_id: number;
  trip_id: number;
  truck_id: number;
  driver_id: number;
  helper_id: number | null;
  issue_type: string;
  priority: string;
  description: string;
  attachment_url: string | null;
  status: string;
  created_at: string;
  updated_at: string;
};

export type DispatchVehicleIssueReportRow = {
  id: number;
  booking_id: number;
  trip_id: number;
  truck_id: number;
  truck_plate: string;
  truck_model: string | null;
  route: string;
  driver_id: number;
  driver_name: string | null;
  helper_id: number | null;
  helper_name: string | null;
  issue_type: string;
  issue_type_label: string;
  priority: string;
  description: string;
  attachment_url: string | null;
  status: string;
  created_at: string | null;
  updated_at: string | null;
};

export type GeneralOperationalReportRow = {
  id: number;
  booking_id: number;
  trip_id: number;
  driver_id: number;
  driver_name: string | null;
  category: string;
  category_label: string;
  trip_status: string | null;
  trip_status_label: string | null;
  report_date: string;
  starting_odometer_km: number | null;
  ending_odometer_km: number | null;
  fuel_consumed: number | null;
  description: string;
  notes: string | null;
  attachment_url: string | null;
  created_at: string | null;
  route: string;
  truck_plate: string;
};

export type DriverGeneralOperationalReportResponse = {
  id: number;
  booking_id: number;
  trip_id: number;
  driver_id: number;
  helper_id: number | null;
  category: string;
  trip_status: string | null;
  report_date: string;
  starting_odometer_km: number | null;
  ending_odometer_km: number | null;
  fuel_consumed: number | null;
  description: string;
  notes: string | null;
  attachment_url: string | null;
  created_at: string;
};

export type Payment = {
  id: number;
  booking_id: number;
  customer_id: number;
  method: string;
  amount: number;
  status: "for_verification" | "verified" | "rejected" | "refunded";
  reference: string;
  paid_at: string | null;
  refunded_at: string | null;
  proof_original_filename?: string | null;
  proof_uploaded_at?: string | null;
  proof_file_url?: string | null;
  reviewed_at?: string | null;
  xendit_qr_id?: string | null;
  xendit_payment_id?: string | null;
  xendit_invoice_id?: string | null;
  xendit_invoice_url?: string | null;
  xendit_external_id?: string | null;
  xendit_status?: "PENDING" | "PAID" | "EXPIRED" | "FAILED" | string | null;
  xendit_qr_string?: string | null;
  xendit_expires_at?: string | null;
  xendit_paid_at?: string | null;
  created_at: string;
  verification_mode?: "xendit_auto" | "manual" | "cash_offline" | string | null;
  display_status?: string | null;
  webhook_verified?: boolean | null;
  webhook_status?: string | null;
  verified_by_name?: string | null;
};

export type XenditConfig = {
  enabled: boolean;
  public_key: string | null;
};

export type XenditPaymentSession = {
  payment: Payment;
  qr_string: string | null;
  xendit_status: string | null;
  checkout_url?: string | null;
};

export type ScheduleTimelineResource = {
  id: number;
  label: string;
  sub: string;
  availability: "available" | "maintenance" | "lane" | "assigned" | "unavailable" | "on_trip";
};

export type ScheduleTimelineEvent = {
  id: string;
  type: string;
  trip_id: number | null;
  booking_id: number | null;
  resource_kind: string;
  resource_id: number;
  start: string;
  end: string;
  state: string;
  title: string;
  subtitle: string;
  pickup?: string;
  dropoff?: string;
  truck_code?: string;
  driver_name?: string;
  helper_name?: string;
  trip_status?: string;
  helper_progress?: string | null;
  customer_name?: string;
  cargo_tons?: number;
  conflict?: boolean;
  conflict_reasons?: string[];
};

export type ScheduleTimelineResponse = {
  window_start: string;
  window_end: string;
  mode: string;
  resource: string;
  total_hours: number;
  start_date: string;
  resources: ScheduleTimelineResource[];
  events: ScheduleTimelineEvent[];
  conflicts: Array<{
    event_id: string;
    trip_id: number | null;
    booking_id: number | null;
    reasons: string[];
    label?: string;
  }>;
};

export type ScheduleTimelineTripDetail = {
  trip_id: number;
  booking_id: number;
  customer: string;
  customer_email: string | null;
  cargo_tons: number;
  pickup: string;
  dropoff: string;
  scheduled_date: string;
  scheduled_time_slot: string;
  booking_status: string;
  trip_status: string;
  helper_progress: string | null;
  truck: { id: number; code: string | null } | null;
  driver: { id: number; name: string | null } | null;
  helper: { id: number; name: string | null } | null;
  eta: string | null;
  payment: { status: string | null; amount: number | null };
  window_start: string;
  window_end: string;
  latest_location: { text: string; at: string } | null;
  status_history: Array<{ status: string; location: string; at: string }>;
};

export type DispatchTripMonitoringAssignment = {
  trip_id: number;
  trip_status: string;
  operational_status: string;
  booking_id: number;
  customer_id: number;
  customer_name: string | null;
  customer_company_name: string | null;
  pickup_location: string;
  dropoff_location: string;
  scheduled_date: string;
  scheduled_time_slot: string;
  cargo_weight_tons: number;
  estimated_cost: number;
  booking_status: string;
  booking_db_status: string;
  paid_amount_verified?: number | null;
  truck_id: number | null;
  truck_code: string;
  driver_id: number | null;
  driver_name: string | null;
  helper_id: number | null;
  helper_name: string | null;
  helper_progress_status: string | null;
  distance_km: number;
  latest_location: string | null;
  last_updated: string | null;
};

export type DispatchTripMonitoringBoardResponse = {
  generated_at: string;
  summary: {
    active_legs: number;
    in_transit_legs: number;
    loading_unloading_legs: number;
    completed_trip_legs_today: number;
    completed_trip_legs_total: number;
    bookings_all_legs_completed: number;
  };
  active_assignments: DispatchTripMonitoringAssignment[];
};

export type DispatchResourceAvailabilityRow = {
  id: number;
  name: string;
  code?: string;
  capacity_tons?: number;
  status: "available" | "assigned" | "on_trip" | "unavailable";
  status_label: string;
  assignable: boolean;
  conflict_reason?: string | null;
  next_available_at?: string | null;
};

export const WorkflowApi = {
  // Bookings
  listBookings: () => apiGet<Booking[]>("/bookings"),
  bookingPickupSlotAvailability: (
    scheduled_date: string,
    opts?: { cargo_weight_tons?: number; pickup_location?: string; dropoff_location?: string },
  ) => {
    const q = new URLSearchParams({ scheduled_date });
    if (opts?.cargo_weight_tons != null && Number.isFinite(opts.cargo_weight_tons)) {
      q.set("cargo_weight_tons", String(opts.cargo_weight_tons));
    }
    if (opts?.pickup_location && opts.pickup_location.trim().length >= 3) {
      q.set("pickup_location", opts.pickup_location.trim());
    }
    if (opts?.dropoff_location && opts.dropoff_location.trim().length >= 3) {
      q.set("dropoff_location", opts.dropoff_location.trim());
    }
    return apiGet<{
      scheduled_date: string;
      slots: Record<string, boolean>;
      required_trucks: number;
      available_trucks_by_slot: Record<string, number>;
      availability_message?: string | null;
    }>(
      `/bookings/schedule-availability?${q.toString()}`,
    );
  },
  createBooking: (payload: {
    pickup_location: string;
    dropoff_location: string;
    service_type: "fixed" | "customized";
    scheduled_date: string;
    scheduled_time_slot: string;
    cargo_weight_tons: number;
    cargo_description: string;
    cargo_type_category: string;
  }) => apiPost<Booking>("/bookings", payload),
  createBookingWithDocuments: (payload: {
    pickup_location: string;
    dropoff_location: string;
    service_type: "fixed" | "customized";
    scheduled_date: string;
    scheduled_time_slot: string;
    cargo_weight_tons: number;
    cargo_description?: string | null;
    cargo_type_category?: string | null;
    terms_agreed: boolean;
    terms_signer_name?: string;
    cargo_declaration: File;
    terms_e_signature: File;
    toll_entry_point?: string;
    toll_exit_point?: string;
    vehicle_class?: string;
    distance_km_override?: number;
  }) => {
    const fd = new FormData();
    fd.append("pickup_location", payload.pickup_location);
    fd.append("dropoff_location", payload.dropoff_location);
    fd.append("service_type", payload.service_type);
    fd.append("scheduled_date", payload.scheduled_date);
    fd.append("scheduled_time_slot", payload.scheduled_time_slot);
    fd.append("cargo_weight_tons", String(payload.cargo_weight_tons));
    if (payload.cargo_description) fd.append("cargo_description", payload.cargo_description);
    if (payload.cargo_type_category) fd.append("cargo_type_category", payload.cargo_type_category);
    if (payload.toll_entry_point) fd.append("toll_entry_point", payload.toll_entry_point);
    if (payload.toll_exit_point) fd.append("toll_exit_point", payload.toll_exit_point);
    if (payload.vehicle_class) fd.append("vehicle_class", payload.vehicle_class);
    if (payload.distance_km_override != null && payload.distance_km_override > 0) {
      fd.append("distance_km_override", String(payload.distance_km_override));
    }
    fd.append("terms_agreed", payload.terms_agreed ? "true" : "false");
    if (payload.terms_signer_name) fd.append("terms_signer_name", payload.terms_signer_name);
    fd.append("cargo_declaration", payload.cargo_declaration);
    fd.append("terms_e_signature", payload.terms_e_signature);
    return apiPostMultipart<Booking>("/bookings/with-documents", fd);
  },
  getBooking: (id: number) => apiGet<Booking>(`/bookings/${id}`),
  bookingTrackingDetails: (id: number) =>
    apiGet<{
      booking: {
        id: number;
        status: string;
        pickup_location: string;
        dropoff_location: string;
        cargo_weight_tons: number;
        scheduled_date: string;
        scheduled_time_slot: string;
        required_truck_count: number;
        /** Routed pickup→dropoff km (same engine as booking pricing); null if unavailable. */
        road_distance_km?: number | null;
      };
      assignments: Array<{
        trip_id: number;
        booking_id?: number;
        trip_status: string;
        helper_progress_status: string | null;
        truck: { id: number; code: string; model_name: string | null; capacity_tons: number } | null;
        driver: { id: number; name: string } | null;
        helper: { id: number; name: string } | null;
        latest_location_name: string | null;
        location_updates: Array<{
          location_name: string;
          remarks: string | null;
          photo_url: string | null;
          created_at: string;
          latitude?: number | null;
          longitude?: number | null;
        }>;
        status_timeline: Array<{
          status: string;
          location_name: string;
          remarks: string | null;
          photo_url: string | null;
          created_at: string;
          latitude?: number | null;
          longitude?: number | null;
        }>;
        timeline_events?: CrewTimelineEvent[];
      }>;
      /** Dispatcher operational logs (staff only; omitted for customers). */
      operational_logs?: Array<{
        id: number;
        trip_id: number;
        booking_id: number;
        dispatcher_id: number;
        dispatcher_name: string | null | undefined;
        report_type: string;
        report_type_label: string;
        priority_level: string;
        operational_details: string;
        attachment_url: string | null;
        created_at: string | null;
      }>;
      general_operational_reports?: Array<{
        id: number;
        trip_id: number;
        booking_id: number;
        driver_id: number;
        driver_name: string | null | undefined;
        category: string;
        category_label: string;
        trip_status: string | null;
        trip_status_label: string | null;
        report_date: string;
        starting_odometer_km: number | null;
        ending_odometer_km: number | null;
        fuel_consumed: number | null;
        description: string;
        notes: string | null;
        attachment_url: string | null;
        created_at: string | null;
      }>;
    }>(`/bookings/${id}/tracking-details`),
  cancelBooking: (id: number) => apiPost<{ status: string }>(`/bookings/${id}/cancel`),

  customerCurrentBookings: () => apiGet<CustomerBookingRow[]>("/customer/current-bookings"),
  customerBookingHistory: () => apiGet<CustomerBookingHistoryRow[]>("/customer/booking-history"),
  customerShipmentTracking: () => apiGet<{ shipments: CustomerBookingRow[] }>("/customer/shipment-tracking"),
  customerCancelBooking: (id: number) => apiPatch<{ status: string }>(`/customer/bookings/${id}/cancel`, {}),
  customerNotifications: (params?: { unread_only?: boolean; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.unread_only) q.set("unread_only", "true");
    if (params?.limit != null) q.set("limit", String(params.limit));
    const qs = q.toString();
    return apiGet<{ notifications: CustomerNotificationRow[]; unread_count: number }>(
      `/customer/notifications${qs ? `?${qs}` : ""}`,
    );
  },
  customerMarkNotificationRead: (notification_id: number) =>
    apiPatch<CustomerNotificationRow>(`/customer/notifications/${notification_id}/read`, {}),
  customerMarkAllNotificationsRead: () =>
    apiPost<{ marked_read: number }>("/customer/notifications/mark-all-read", {}),
  customerDismissNotification: (notification_id: number) =>
    apiPost<CustomerNotificationRow>(`/customer/notifications/${notification_id}/dismiss`, {}),
  customerUpdateBookingCustoms: (
    id: number,
    payload: {
      customs_clearance_status?: string | null;
      customs_tariff_notes?: string | null;
      customs_additional_charges_php?: number | null;
    },
  ) => apiPatch<Booking>(`/customer/bookings/${id}/customs`, payload),
  validateBookingCustoms: (
    id: number,
    payload: {
      validated: boolean;
      customs_admin_notes?: string | null;
      customs_validated_additional_charges_php?: number | null;
    },
  ) => apiPatch<Booking>(`/bookings/${id}/customs/validate`, payload),
  preDeliveryChecklist: (id: number) => apiGet<PreDeliveryChecklist>(`/bookings/${id}/pre-delivery-checklist`),
  updatePreDeliveryChecklist: (
    id: number,
    payload: { goods_declaration_validated?: boolean; cargo_type_validated?: boolean },
  ) => apiPatch<PreDeliveryChecklist>(`/bookings/${id}/pre-delivery-checklist`, payload),

  listGoodsDeclarations: () => apiGet<GoodsDeclarationAdminRow[]>("/admin/goods-declarations"),
  goodsDeclarationReasonCatalog: () =>
    apiGet<{ revision: Array<{ code: string; label: string }>; rejection: Array<{ code: string; label: string }> }>(
      "/admin/goods-declarations/reason-catalog",
    ),
  reviewGoodsDeclaration: (
    bookingId: number,
    payload: {
      status: "approved" | "rejected" | "revision_requested";
      remarks?: string | null;
      reason_code?: string | null;
    },
  ) => apiPatch<GoodsDeclarationAdminRow>(`/admin/goods-declarations/${bookingId}`, payload),
  helperVerifyBookingQr: (
    bookingId: number,
    payload: string,
    method: "camera" | "manual" | "scan" = "scan",
    tripId?: number,
  ) =>
    apiPost<{
      ok: boolean;
      already_verified: boolean;
      booking_id: number;
      trip_ids?: number[];
      verified_at: string;
      verification_method?: string | null;
      completed?: boolean;
      message: string;
    }>(`/helper/bookings/${bookingId}/verify-qr`, {
      payload,
      method,
      ...(tripId != null ? { trip_id: tripId } : {}),
    }),

  resubmitBookingDocuments: (
    bookingId: number,
    payload: { cargo_declaration?: File },
  ) => {
    const fd = new FormData();
    if (payload.cargo_declaration) fd.append("cargo_declaration", payload.cargo_declaration);
    return apiPostMultipart<Booking>(`/bookings/${bookingId}/documents/resubmit`, fd);
  },

  listCargoTypeValidations: () => apiGet<CargoTypeValidationAdminRow[]>("/admin/cargo-type-validations"),
  previewCargoTypeScreening: (bookingId: number, category: string) =>
    apiGet<CargoTypeScreening>(
      `/bookings/${bookingId}/cargo-type/screening?category=${encodeURIComponent(category)}`,
    ),
  validateBookingCargoType: (
    bookingId: number,
    payload: {
      validated: boolean;
      cargo_type_category?: string | null;
      cargo_type_admin_notes?: string | null;
      cargo_description?: string | null;
    },
  ) => apiPatch<Booking>(`/bookings/${bookingId}/cargo-type/validate`, payload),

  listDispatchers: () => apiGet<DispatcherUserOption[]>("/admin/dispatchers"),
  listDispatcherAssignments: () => apiGet<DispatcherAssignmentRow[]>("/admin/dispatcher-assignments"),
  assignBookingDispatcher: (bookingId: number, dispatcherId: number | null) =>
    apiPatch<DispatcherAssignmentRow>(`/admin/dispatcher-assignments/${bookingId}`, {
      dispatcher_id: dispatcherId,
    }),

  // Workflow API
  workflowCreateBooking: (payload: Record<string, unknown>) =>
    apiPost<Booking>("/workflow/booking/create", payload),
  pendingApprovals: () => apiGet<Booking[]>("/workflow/booking/pending-approval"),
  /** Approved bookings ready for dispatcher assignment (empty until managers approve). */
  assignableBookings: () => apiGet<Booking[]>("/workflow/booking/assignable"),
  approveBooking: (id: number, approved: boolean, reason?: string) =>
    apiPost<Booking>(`/workflow/booking/${id}/approve`, { approved, rejection_reason: reason }),
  createJobFromBooking: (id: number) => apiPost<Trip>(`/workflow/job/create-from-booking/${id}`),

  // Trip
  getTrip: (trip_id: number) => apiGet<Trip>(`/workflow/job/${trip_id}`),

  // Driver
  myTrips: (opts?: { includeTimeline?: boolean }) => {
    const qs = opts?.includeTimeline ? "?include_timeline=true" : "";
    return apiGet<Trip[]>(`/driver/trips${qs}`);
  },
  driverDashboardSummary: () => apiGet<DriverDashboardSummary>("/driver/dashboard-summary"),
  driverPaySummary: () => apiGet<DriverPaySummary>("/driver/pay-summary"),
  driverVehicleIssueSelectableTrips: () =>
    apiGet<{ trips: DriverVehicleIssueSelectableTrip[] }>("/driver/vehicle-issue/trips"),
  driverSubmitVehicleIssueReport: (formData: FormData) =>
    apiPostMultipart<DriverVehicleIssueReportResponse>("/driver/vehicle-issue-reports", formData),
  driverGeneralOperationalFormTrips: () =>
    apiGet<{ trips: DriverVehicleIssueSelectableTrip[] }>("/driver/general-operational-form/trips"),
  driverSubmitGeneralOperationalReport: (formData: FormData) =>
    apiPostMultipart<DriverGeneralOperationalReportResponse>("/driver/general-operational-reports", formData),
  driverSalary: () => apiGet<Record<string, unknown>>("/driver/salary"),
  driverCheckIn: () =>
    apiPost<{ checked_in: boolean; timestamp: string }>("/driver/attendance/check-in", {}),
  driverCheckOut: () =>
    apiPost<{ checked_out: boolean; timestamp: string }>("/driver/attendance/check-out", {}),
  acceptJob: (trip_id: number) => apiPost<Trip>(`/workflow/job/${trip_id}/accept`),
  depart: (trip_id: number, opts?: { location_name?: string; notes?: string }) =>
    apiPost<Trip>(`/workflow/job/${trip_id}/depart`, {
      status: "departed",
      location_name: opts?.location_name,
      notes: opts?.notes,
    }),
  arrivedPickup: (trip_id: number) =>
    apiPost<Trip>(`/workflow/job/${trip_id}/arrived-pickup`, { status: "loading" }),
  loadingComplete: (trip_id: number) =>
    apiPost<Trip>(`/workflow/job/${trip_id}/loading-complete`),
  deliveryReceivingStatus: (trip_id: number) =>
    apiGet<DeliveryReceivingStatus>(`/workflow/job/${trip_id}/delivery-receiving-status`),
  uploadReceivingDocument: (trip_id: number, file: File, evidence?: EvidenceCaptureMetadata | null) => {
    const fd = new FormData();
    fd.append("file", file);
    if (evidence) appendEvidenceToFormData(fd, evidence);
    return apiPostMultipart<DeliveryReceivingStatus>(`/workflow/job/${trip_id}/receiving-document`, fd);
  },
  verifyReceivingQr: (trip_id: number, scanned_payload: string) =>
    apiPost<DeliveryReceivingStatus>(`/workflow/job/${trip_id}/verify-receiving-qr`, { scanned_payload }),
  verifyDelivery: (trip_id: number, method: "qr" | "code", credential: string) =>
    apiPost<DeliveryVerificationResult>(`/helper/trips/${trip_id}/verify-delivery`, { method, credential }),
  uploadDigitalSignature: (trip_id: number, file: File, evidence?: EvidenceCaptureMetadata | null) => {
    const fd = new FormData();
    fd.append("file", file);
    if (evidence) appendEvidenceToFormData(fd, evidence);
    return apiPostMultipart<DeliveryReceivingStatus>(`/workflow/job/${trip_id}/digital-signature`, fd);
  },
  completeTrip: (trip_id: number, proof_url?: string, notes?: string) =>
    apiPost<Trip>(`/workflow/job/${trip_id}/complete`, { proof_url, notes }),
  reportIssue: (trip_id: number, issue_type: string, description: string, severity = "medium") =>
    apiPost(`/workflow/job/${trip_id}/report-issue`, { issue_type, description, severity }),

  // Fuel & toll
  addFuelLog: (
    trip_id: number,
    payload: { liters: number; cost: number; odometer_km?: number; receipt_url?: string }
  ) => apiPost(`/trips/${trip_id}/fuel-log`, payload),
  addTollLog: (trip_id: number, payload: { location: string; amount: number; receipt_url?: string }) =>
    apiPost(`/trips/${trip_id}/toll-log`, payload),
  addAdditionalToll: (trip_id: number, payload: { amount: number; reason: string; receipt_url?: string }) =>
    apiPost(`/trips/${trip_id}/additional-toll`, payload),
  additionalTolls: (trip_id: number) => apiGet(`/trips/${trip_id}/additional-tolls`),
  fuelLogs: (trip_id: number) => apiGet(`/trips/${trip_id}/fuel-logs`),
  tollLogs: (trip_id: number) => apiGet(`/trips/${trip_id}/toll-logs`),
  generateReport: (trip_id: number) => apiPost(`/trips/${trip_id}/generate-report`),
  getCompletionReport: (trip_id: number) => apiGet(`/trips/${trip_id}/report`),
  confirmCompletionReport: (trip_id: number) => apiPost(`/trips/${trip_id}/report/confirm`),

  // Payments
  listPayments: () => apiGet<Payment[]>("/payments"),
  submitPaymentProof: (booking_id: number, method: string, file?: File | null) => {
    const fd = new FormData();
    fd.append("booking_id", String(booking_id));
    fd.append("method", method);
    if (file) fd.append("file", file);
    return apiPostMultipart<Payment>("/payments/submit-proof", fd);
  },
  verifyPayment: (payment_id: number) => apiPost<Payment>(`/payments/${payment_id}/verify`, {}),
  markCashReceived: (payment_id: number) => apiPost<Payment>(`/payments/${payment_id}/cash-received`, {}),
  rejectPayment: (payment_id: number) => apiPost<Payment>(`/payments/${payment_id}/reject`, {}),
  payBooking: (booking_id: number, method: string, amount: number) =>
    apiPost<Payment>("/payments", { booking_id, method, amount }),
  refundPayment: (payment_id: number, reason?: string) =>
    apiPost<Payment>(`/payments/${payment_id}/refund`, { reason }),
  bookingPayments: (booking_id: number) => apiGet<Payment[]>(`/payments/booking/${booking_id}`),
  xenditConfig: () => apiGet<XenditConfig>("/payments/xendit/config"),
  createXenditSession: (booking_id: number, method: string = "gcash") =>
    apiPost<XenditPaymentSession>(`/payments/xendit/session/${booking_id}`, { method }),
  createCashSession: (booking_id: number) => apiPost<Payment>(`/payments/cash/session/${booking_id}`, {}),
  getXenditSession: (booking_id: number) => apiGet<XenditPaymentSession>(`/payments/xendit/session/${booking_id}`),

  // Feedback
  submitFeedback: (payload: {
    booking_id?: number | null;
    rating: number;
    message?: string;
    category?: string;
    screenshot?: File | null;
  }) => {
    const fd = new FormData();
    if (payload.booking_id != null) fd.append("booking_id", String(payload.booking_id));
    else fd.append("booking_id", "general");
    fd.append("rating", String(payload.rating));
    fd.append("category", payload.category || "support");
    if (payload.message) fd.append("message", payload.message);
    if (payload.screenshot) fd.append("screenshot", payload.screenshot);
    return apiPostMultipart("/feedback/with-attachment", fd);
  },
  listFeedback: () => apiGet("/feedback"),

  // Manager
  managerFinance: () => apiGet("/manager/finance"),
  issueJobOrder: (booking_id: number, instructions?: string) =>
    apiPost(`/manager/job-orders/${booking_id}${instructions ? `?instructions=${encodeURIComponent(instructions)}` : ""}`),

  // Schedule
  scheduleTrucks: (week?: string) =>
    apiGet(`/schedule/trucks${week ? `?week=${encodeURIComponent(week)}` : ""}`),
  scheduleDrivers: (week?: string) =>
    apiGet(`/schedule/drivers${week ? `?week=${encodeURIComponent(week)}` : ""}`),
  /** Gantt-style timeline (trips, maintenance, holds, conflicts). */
  scheduleTimeline: (params?: {
    start?: string;
    mode?: "day" | "week";
    resource?: "truck" | "driver";
    status?: string;
    q?: string;
  }) => {
    const q = new URLSearchParams();
    if (params?.start) q.set("start", params.start);
    if (params?.mode) q.set("mode", params.mode);
    if (params?.resource) q.set("resource", params.resource);
    if (params?.status) q.set("status", params.status);
    if (params?.q) q.set("q", params.q);
    const qs = q.toString();
    return apiGet<ScheduleTimelineResponse>(`/schedule/timeline${qs ? `?${qs}` : ""}`);
  },
  scheduleTimelineTripDetail: (tripId: number) =>
    apiGet<ScheduleTimelineTripDetail>(`/schedule/timeline/trip/${tripId}`),
  availability: (scheduled_date: string) =>
    apiGet(`/schedule/availability?scheduled_date=${encodeURIComponent(scheduled_date)}`),

  // Dispatch
  dispatchBookingAvailability: (booking_id: number) =>
    apiGet<{
      booking_id: number;
      required_truck_count: number;
      cargo_weight_tons: number;
      weight_splits: number[];
      schedule_window_start?: string;
      schedule_window_end?: string;
      trucks: { id: number; code: string; capacity_tons: number; status?: string; status_label?: string }[];
      drivers: { id: number; name: string; status?: string; status_label?: string }[];
      helpers: { id: number; name: string; status?: string; status_label?: string }[];
      truck_roster: DispatchResourceAvailabilityRow[];
      driver_roster: DispatchResourceAvailabilityRow[];
      helper_roster: DispatchResourceAvailabilityRow[];
    }>(`/dispatch/booking/${booking_id}/availability`),
  dispatchAssignBatch: (
    booking_id: number,
    assignments: Array<{ truck_id: number; driver_id: number; helper_id: number; assigned_weight: number }>,
  ) =>
    apiPost<{ booking_id: number; trip_ids: number[]; assigned_count: number }>(`/dispatch/${booking_id}/assign-batch`, {
      assignments,
    }),
  manualAssign: (
    booking_id: number,
    payload: {
      truck_id?: number;
      driver_id?: number;
      helper_id?: number;
      route_path?: string[];
      distance_km?: number;
      duration_hours?: number;
      fuel_cost?: number;
      toll_cost?: number;
      labor_cost?: number;
      predicted_total_cost?: number;
    }
  ) => apiPost(`/dispatch/${booking_id}/assign`, payload),

  dispatchRoster: () =>
    apiGet<{
      trucks: { id: number; code: string; capacity_tons: number }[];
      drivers: { id: number; name: string }[];
      helpers: { id: number; name: string }[];
    }>("/dispatch/roster"),

  dispatchAssignmentsBoard: () =>
    apiGet<{
      assignments: Array<{
        trip_id: number;
        trip_status: string;
        booking_id: number;
        customer_id: number;
        customer_name: string | null;
        customer_company_name: string | null;
        pickup_location: string;
        dropoff_location: string;
        scheduled_date: string;
        scheduled_time_slot: string;
        cargo_weight_tons: number;
        estimated_cost: number;
        booking_status: string;
        paid_amount_verified?: number | null;
        truck_id: number | null;
        truck_code: string;
        driver_id: number | null;
        driver_name: string | null;
        helper_id: number | null;
        helper_name: string | null;
        helper_progress_status: string | null;
        operational_status?: string | null;
        distance_km: number;
        latest_location: string | null;
        last_updated: string | null;
      }>;
    }>("/dispatch/assignments-board"),

  dispatchTripMonitoringBoard: () => apiGet<DispatchTripMonitoringBoardResponse>("/dispatch/trip-monitoring-board"),

  dispatchVehicleIssueReports: () =>
    apiGet<{ reports: DispatchVehicleIssueReportRow[] }>("/dispatch/vehicle-issue-reports"),
  dispatchVehicleIssueReportUpdate: (report_id: number, status: "reviewed" | "resolved") =>
    apiPatch<{ id: number; status: string }>(`/dispatch/vehicle-issue-reports/${report_id}`, { status }),

  dispatchGeneralOperationalReports: (params?: { booking_id?: number }) => {
    const q = new URLSearchParams();
    if (params?.booking_id != null) q.set("booking_id", String(params.booking_id));
    const qs = q.toString();
    return apiGet<{ reports: GeneralOperationalReportRow[] }>(
      `/dispatch/general-operational-reports${qs ? `?${qs}` : ""}`,
    );
  },

  dispatchFleetAssets: () =>
    apiGet<{
      drivers: Array<{
        id: number;
        name: string;
        phone: string;
        rating: number;
        completed_trips: number;
        status: "on_trip" | "available";
        assigned_truck_code?: string;
      }>;
      trucks: Array<{
        id: number;
        plate: string;
        model_name: string;
        capacity_tons: number;
        status: string;
        db_status: string;
        odometer_km: number;
        age_years: number;
        assigned_driver_name: string | null;
        assigned_driver_id: number | null;
      }>;
    }>("/dispatch/fleet-assets"),

  driverAssignedBookings: () => apiGet<{ bookings: CrewAssignedBookingRow[] }>("/driver/bookings"),

  driverTripNotifications: (params?: { unread_only?: boolean; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.unread_only) q.set("unread_only", "true");
    if (params?.limit != null) q.set("limit", String(params.limit));
    const qs = q.toString();
    return apiGet<{ notifications: DriverTripNotificationRow[]; unread_count: number }>(
      `/driver/notifications${qs ? `?${qs}` : ""}`,
    );
  },
  driverMarkNotificationRead: (notification_id: number) =>
    apiPatch<DriverTripNotificationRow>(`/driver/notifications/${notification_id}/read`, {}),
  driverMarkAllNotificationsRead: () =>
    apiPost<{ marked_read: number }>("/driver/notifications/mark-all-read", {}),

  helperListBookings: () => apiGet<{ bookings: CrewAssignedBookingRow[] }>("/helper/bookings"),

  helperSubmitProgress: (trip_id: number, fd: FormData) =>
    apiPostMultipart<{
      trip_id: number;
      status: string;
      trip_status: string;
      photo_path: string | null;
      location_updates_submitted: number;
      required_location_updates: number;
    }>(`/helper/trips/${trip_id}/status`, fd),
  helperSubmitLocation: (trip_id: number, fd: FormData) =>
    apiPostMultipart<{
      trip_id: number;
      location_updates_submitted: number;
      required_location_updates: number;
    }>(`/helper/trips/${trip_id}/location`, fd),
};
