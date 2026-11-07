"use client";

import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { apiFetch, ApiError } from "@/lib/api";
import { BOOKING_TIME_SLOTS } from "@/lib/bookingSlots";
import { routeUsesGeocodedPinsBoth } from "@/lib/bookingRouteEstimate";
import { MIN_BOOKING_SITES, loadCustomerSites, subscribeSitesChanged } from "@/lib/customerSites";
import { customerBookingPaymentPath } from "@/lib/customerPaymentNavigation";
import { WorkflowApi } from "@/lib/workflowApi";
import BookingWizardStepper from "@/components/booking/BookingWizardStepper";
import RouteStep from "@/components/booking/RouteStep";
import ShipmentStep from "@/components/booking/ShipmentStep";
import ScheduleStep from "@/components/booking/ScheduleStep";
import DocumentsStep from "@/components/booking/DocumentsStep";
import ReviewStep from "@/components/booking/ReviewStep";
import { freightLinesFromPayload } from "@/components/booking/bookingQuoteUtils";
import { isWizardStepComplete, validateWizardStep } from "@/components/booking/bookingWizardValidation";
import {
  BOOKING_WIZARD_STEPS,
  type BookingWizardStep,
  type FormErrors,
  type LiveCostQuote,
  type QuotedCostBreakdown,
  type QuoteGeoMeta,
  type RouteOptionQuote,
  type RouteQuoteApiResponse,
  type TollEstimateMeta,
} from "@/components/booking/wizardTypes";

const DEFAULT_SERVICE_TYPE = "fixed";

const STEP_ORDER: BookingWizardStep[] = BOOKING_WIZARD_STEPS.map((s) => s.id);

export default function CostCalculator({
  onQuotedBreakdown,
}: {
  onQuotedBreakdown?: (breakdown: QuotedCostBreakdown) => void;
}) {
  const router = useRouter();
  const [currentStep, setCurrentStep] = useState<BookingWizardStep>("route");
  const [pickupId, setPickupId] = useState("");
  const [dropoffId, setDropoffId] = useState("");
  const [sites, setSites] = useState<Awaited<ReturnType<typeof loadCustomerSites>>>([]);
  const [weight, setWeight] = useState("1");
  const [cost, setCost] = useState<LiveCostQuote | null>(null);
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<FormErrors>({});
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState<"success" | "error" | "">("");
  const [date, setDate] = useState("");
  const [pickedSlot, setPickedSlot] = useState<string>("");
  const [slotAvailability, setSlotAvailability] = useState<Record<string, boolean>>({});
  const [slotAvailableTrucks, setSlotAvailableTrucks] = useState<Record<string, number>>({});
  const [requiredTrucksFromApi, setRequiredTrucksFromApi] = useState<number>(1);
  const [slotsLoading, setSlotsLoading] = useState(false);
  const [slotsFetchError, setSlotsFetchError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [routeQuoteMeta, setRouteQuoteMeta] = useState<QuoteGeoMeta | null>(null);
  const [tollEstimateMeta, setTollEstimateMeta] = useState<TollEstimateMeta | null>(null);
  const [manualDistanceKm, setManualDistanceKm] = useState("");
  const [distanceConfirmed, setDistanceConfirmed] = useState(true);
  const [distanceWarning, setDistanceWarning] = useState<string | null>(null);
  const [quoteStatus, setQuoteStatus] = useState<string | null>(null);
  const [routeOptions, setRouteOptions] = useState<RouteOptionQuote[]>([]);
  const [selectedRouteOptionId, setSelectedRouteOptionId] = useState<string | null>(null);
  const [recommendedRouteOptionId, setRecommendedRouteOptionId] = useState<string | null>(null);
  const [travelTimeLabel, setTravelTimeLabel] = useState<string | null>(null);
  const [freightLines, setFreightLines] = useState<Awaited<ReturnType<typeof freightLinesFromPayload>> | null>(null);
  const [cargoDeclaration, setCargoDeclaration] = useState<File | null>(null);
  const [termsSignature, setTermsSignature] = useState<File | null>(null);
  const [termsScrolled, setTermsScrolled] = useState(false);
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [cargoDescription, setCargoDescription] = useState("");
  const [cargoTypeCategory, setCargoTypeCategory] = useState("");
  const [quoteRefreshNonce, setQuoteRefreshNonce] = useState(0);
  const prevStepRef = useRef<BookingWizardStep>("route");
  const today = new Date().toISOString().split("T")[0];

  const hasEnoughSites = sites.length >= MIN_BOOKING_SITES;

  const pickup = useMemo(() => sites.find((s) => s.id === pickupId)?.address ?? "", [sites, pickupId]);
  const dropoff = useMemo(() => sites.find((s) => s.id === dropoffId)?.address ?? "", [sites, dropoffId]);

  const showApproximateRoutingWarning = useMemo(() => {
    if (routeQuoteMeta) {
      const { pickup_resolution: pr, dropoff_resolution: dr, pricing_tier: t, routing_method: rm } = routeQuoteMeta;
      if (pr === "none" || dr === "none") return true;
      if (t !== "geocoded") return true;
      if (rm === "haversine_road_factor") return true;
      return false;
    }
    return !routeUsesGeocodedPinsBoth(pickup, dropoff);
  }, [routeQuoteMeta, pickup, dropoff]);

  const validationContext = useMemo(
    () => ({
      sitesCount: sites.length,
      pickupId,
      dropoffId,
      pickup,
      dropoff,
      weight,
      cargoDescription,
      cargoTypeCategory,
      date,
      today,
      pickedSlot,
      slotsLoading,
      slotAvailability,
      slotAvailableTrucks,
      requiredTrucksFromApi,
      cargoDeclaration,
      termsSignature,
      termsAccepted,
      termsScrolled,
    }),
    [
      sites.length,
      pickupId,
      dropoffId,
      pickup,
      dropoff,
      weight,
      cargoDescription,
      cargoTypeCategory,
      date,
      today,
      pickedSlot,
      slotsLoading,
      slotAvailability,
      slotAvailableTrucks,
      requiredTrucksFromApi,
      cargoDeclaration,
      termsSignature,
      termsAccepted,
      termsScrolled,
    ],
  );

  useEffect(() => {
    let cancelled = false;
    const refresh = () => {
      loadCustomerSites()
        .then((list) => {
          if (!cancelled) setSites(list);
        })
        .catch(() => undefined);
    };
    refresh();
    return subscribeSitesChanged(refresh);
  }, []);

  useEffect(() => {
    const ids = new Set(sites.map((s) => s.id));
    setPickupId((id) => (id && ids.has(id) ? id : ""));
    setDropoffId((id) => (id && ids.has(id) ? id : ""));
  }, [sites]);

  useEffect(() => {
    if (!hasEnoughSites) {
      setSlotAvailability({});
      setSlotAvailableTrucks({});
      setRequiredTrucksFromApi(1);
      setPickedSlot("");
      setSlotsFetchError(null);
      setSlotsLoading(false);
      return;
    }
    if (!date) {
      setSlotAvailability({});
      setSlotAvailableTrucks({});
      setRequiredTrucksFromApi(1);
      setPickedSlot("");
      setSlotsFetchError(null);
      setSlotsLoading(false);
      return;
    }

    let cancelled = false;
    setSlotsLoading(true);
    setSlotsFetchError(null);
    setPickedSlot("");

    void WorkflowApi.bookingPickupSlotAvailability(date, {
      cargo_weight_tons: Number.isFinite(parseFloat(weight)) ? parseFloat(weight) : 1,
      pickup_location: pickup,
      dropoff_location: dropoff,
    })
      .then((res) => {
        if (cancelled) return;
        setSlotsFetchError(res.availability_message ?? null);
        const next: Record<string, boolean> = {};
        for (const s of BOOKING_TIME_SLOTS) {
          next[s] = res.slots?.[s] !== false;
        }
        setSlotAvailability(next);
        setSlotAvailableTrucks(res.available_trucks_by_slot ?? {});
        setRequiredTrucksFromApi(
          typeof res.required_trucks === "number" && Number.isFinite(res.required_trucks)
            ? Math.max(1, Math.floor(res.required_trucks))
            : 1,
        );
      })
      .catch((e) => {
        if (!cancelled) {
          const next: Record<string, boolean> = {};
          for (const s of BOOKING_TIME_SLOTS) next[s] = true;
          setSlotAvailability(next);
          setSlotAvailableTrucks({});
          setRequiredTrucksFromApi(Math.max(1, Math.ceil((Number.parseFloat(weight) || 1) / 42)));
          setSlotsFetchError(e instanceof Error ? e.message : "Could not load pickup windows.");
        }
      })
      .finally(() => {
        if (!cancelled) setSlotsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [date, hasEnoughSites, pickup, dropoff, weight]);

  const parsedWeight = parseFloat(weight);
  const effectiveWeightTons = Number.isFinite(parsedWeight) && parsedWeight > 0 ? Math.min(168, parsedWeight) : 1;

  const quoteMatchesWeight = useMemo(() => {
    if (!freightLines || !Number.isFinite(parsedWeight) || parsedWeight <= 0) return false;
    return Math.abs(freightLines.booking_weight_tons - parsedWeight) < 0.001;
  }, [freightLines, parsedWeight]);

  const quoteReady = Boolean(cost && quoteMatchesWeight && !loading && distanceConfirmed);

  const applyRouteQuoteResponse = useCallback(
    (data: RouteQuoteApiResponse) => {
      setMessage("");
      setMessageType("");
      const live: LiveCostQuote = {
        distance_km: data.distance_km,
        total_trucks: data.total_trucks,
        cargo_gross_php: data.cargo_gross_php,
        diesel_cost_php: data.diesel_cost_php,
        driver_share_php: data.driver_share_php,
        helper_share_php: data.helper_share_php,
        toll_fees_php: data.toll_fees_php,
        additives_total_php: data.additives_total_php,
        net_profit_total_php: data.net_profit_total_php,
        quoted_total: data.quoted_total,
        truck_loads: data.truck_loads,
      };
      setCost(live);
      setRouteQuoteMeta({
        pickup_resolution: data.pickup_resolution,
        dropoff_resolution: data.dropoff_resolution,
        pricing_tier: data.pricing_tier,
        routing_method: data.routing_method,
      });
      setTollEstimateMeta({
        matched: Boolean(data.toll_matrix_matched),
        message: data.toll_estimate_message ?? null,
        entryPoint: data.toll_entry_point ?? null,
        exitPoint: data.toll_exit_point ?? null,
        effectiveDate: data.toll_effective_date ?? null,
        budgetPerTruck: data.estimated_toll_budget_per_truck ?? null,
        budgetTotal: data.estimated_toll_budget_total ?? null,
        plazaOptions: data.toll_plaza_options ?? [],
        suggestedEntry: data.suggested_toll_entry_point ?? null,
        suggestedExit: data.suggested_toll_exit_point ?? null,
        tollSource: data.toll_source ?? null,
        segments: data.toll_segments ?? [],
        isEstimated: Boolean(data.toll_is_estimated),
        matchMethod: data.toll_match_method ?? null,
      });
      setDistanceConfirmed(data.distance_confirmed !== false);
      setDistanceWarning(data.distance_warning ?? null);
      setQuoteStatus(data.quote_status ?? null);
      if (data.route_options?.length) {
        setRouteOptions(data.route_options);
        const recommended =
          data.recommended_route_option_id ?? data.route_options.find((o) => o.is_recommended)?.id ?? null;
        setRecommendedRouteOptionId(recommended);
        setSelectedRouteOptionId((prev) => {
          if (prev && data.route_options!.some((o) => o.id === prev)) return prev;
          return data.selected_route_option_id ?? recommended ?? data.route_options![0]?.id ?? null;
        });
      }
      setTravelTimeLabel(data.travel_time_label ?? null);
      setFreightLines(freightLinesFromPayload(data));
      onQuotedBreakdown?.({
        cargo_gross_php: live.cargo_gross_php,
        toll_fees_php: live.toll_fees_php,
        labor_freight_php: live.driver_share_php + live.helper_share_php,
        quoted_total_php: live.quoted_total,
      });
    },
    [onQuotedBreakdown],
  );

  const fetchRouteQuote = useCallback(
    async (signal?: AbortSignal) => {
      const data = await apiFetch<RouteQuoteApiResponse>("/customer/route-quote", {
        method: "POST",
        body: JSON.stringify({
          pickup_location: pickup,
          dropoff_location: dropoff,
          weight_tons: effectiveWeightTons,
          vehicle_class: "Class 3",
          distance_km_override: manualDistanceKm.trim() ? Number(manualDistanceKm) : undefined,
          selected_route_option_id: selectedRouteOptionId || undefined,
        }),
        signal,
      });
      applyRouteQuoteResponse(data);
    },
    [
      pickup,
      dropoff,
      effectiveWeightTons,
      manualDistanceKm,
      selectedRouteOptionId,
      applyRouteQuoteResponse,
    ],
  );

  useEffect(() => {
    if (!hasEnoughSites) {
      setCost(null);
      setRouteQuoteMeta(null);
      setTollEstimateMeta(null);
      setFreightLines(null);
      setRouteOptions([]);
      setSelectedRouteOptionId(null);
      setRecommendedRouteOptionId(null);
      setTravelTimeLabel(null);
      setLoading(false);
      return;
    }

    const p = pickup.trim();
    const d = dropoff.trim();

    if (!pickupId || !dropoffId || pickupId === dropoffId || p.length < 3 || d.length < 3 || p.toLowerCase() === d.toLowerCase()) {
      setCost(null);
      setRouteQuoteMeta(null);
      setTollEstimateMeta(null);
      setFreightLines(null);
      setRouteOptions([]);
      setSelectedRouteOptionId(null);
      setRecommendedRouteOptionId(null);
      setTravelTimeLabel(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    const ac = new AbortController();
    setLoading(true);

    const quoteStepVisible = currentStep === "pricing" || currentStep === "payment";
    const immediate = quoteStepVisible || quoteRefreshNonce > 0;
    const timer = window.setTimeout(
      () => {
        void (async () => {
          try {
            await fetchRouteQuote(ac.signal);
          } catch (e: unknown) {
            if (cancelled) return;
            if (e instanceof DOMException && e.name === "AbortError") return;
            setCost(null);
            setRouteQuoteMeta(null);
            setTollEstimateMeta(null);
            setFreightLines(null);
            setRouteOptions([]);
            setTravelTimeLabel(null);
            if (e instanceof ApiError) {
              setMessage(e.message);
              setMessageType("error");
              return;
            }
            setMessage("Could not compute road distance. Check your connection and that the API is running.");
            setMessageType("error");
          } finally {
            if (!cancelled) setLoading(false);
          }
        })();
      },
      immediate ? 0 : 220,
    );

    return () => {
      cancelled = true;
      ac.abort();
      window.clearTimeout(timer);
    };
  }, [
    pickup,
    dropoff,
    weight,
    hasEnoughSites,
    pickupId,
    dropoffId,
    manualDistanceKm,
    selectedRouteOptionId,
    fetchRouteQuote,
    currentStep,
    quoteRefreshNonce,
  ]);

  useEffect(() => {
    if (prevStepRef.current !== "pricing" && currentStep === "pricing") {
      setQuoteRefreshNonce((n) => n + 1);
    }
    prevStepRef.current = currentStep;
  }, [currentStep]);

  const bookingPricingHint = !hasEnoughSites
    ? `Save at least ${MIN_BOOKING_SITES} sites on your dashboard — booking is disabled until then.`
    : "Select pickup and dropoff — server geocoding runs when you save (needs backend online).";

  const requiredTrucks = Math.max(1, requiredTrucksFromApi || Math.ceil((parseFloat(weight) || 1) / 42));
  const selectedAvailableTrucks = pickedSlot ? (slotAvailableTrucks[pickedSlot] ?? 0) : 0;

  const canSubmit =
    hasEnoughSites &&
    quoteReady &&
    !isSubmitting &&
    !!pickedSlot &&
    slotAvailability[pickedSlot] !== false &&
    (slotAvailableTrucks[pickedSlot] ?? 0) >= requiredTrucksFromApi &&
    !slotsLoading &&
    !!cargoDeclaration &&
    !!termsSignature &&
    termsScrolled &&
    termsAccepted &&
    distanceConfirmed;

  const canGoNext = useMemo(() => {
    if (!isWizardStepComplete(currentStep, validationContext)) return false;
    if (currentStep === "route") {
      return !loading && distanceConfirmed && !!cost?.distance_km;
    }
    if (currentStep === "pricing") {
      return quoteReady;
    }
    return true;
  }, [currentStep, validationContext, loading, distanceConfirmed, cost?.distance_km, quoteReady]);

  const currentStepIndex = STEP_ORDER.indexOf(currentStep);
  const isFirstStep = currentStepIndex === 0;
  const isLastStep = currentStepIndex === STEP_ORDER.length - 1;

  const clearError = useCallback((key: string) => {
    setErrors((er) => (er[key] ? { ...er, [key]: "" } : er));
  }, []);

  const clearErrors = useCallback((keys: string[]) => {
    setErrors((er) => {
      const next = { ...er };
      let changed = false;
      for (const key of keys) {
        if (next[key]) {
          next[key] = "";
          changed = true;
        }
      }
      return changed ? next : er;
    });
  }, []);

  const handleNext = () => {
    const stepErrors = validateWizardStep(currentStep, validationContext);
    setErrors(stepErrors);
    if (Object.keys(stepErrors).length > 0) return;
    if (currentStep === "route" && (loading || !distanceConfirmed || !cost?.distance_km)) return;
    if (!isLastStep) {
      setCurrentStep(STEP_ORDER[currentStepIndex + 1]);
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  };

  const handlePrev = () => {
    if (!isFirstStep) {
      setCurrentStep(STEP_ORDER[currentStepIndex - 1]);
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (sites.length < MIN_BOOKING_SITES) return;

    const allErrors = validateWizardStep("review", validationContext);
    setErrors(allErrors);
    if (Object.keys(allErrors).length > 0) return;
    if (!canSubmit) return;
    if (
      !window.confirm(
        "Create this booking and proceed to payment? FleetOps will save the request, then open the payment page for verification.",
      )
    ) {
      return;
    }

    setIsSubmitting(true);
    setMessage("");

    try {
      let termsSignerName = "";
      if (typeof window !== "undefined") {
        try {
          const cached = window.localStorage.getItem("customer_current_user");
          if (cached) {
            const parsed = JSON.parse(cached) as { full_name?: string };
            termsSignerName = parsed.full_name?.trim() ?? "";
          }
        } catch {
          termsSignerName = "";
        }
      }

      const data = await WorkflowApi.createBookingWithDocuments({
        pickup_location: pickup,
        dropoff_location: dropoff,
        service_type: DEFAULT_SERVICE_TYPE,
        scheduled_date: date,
        scheduled_time_slot: pickedSlot,
        cargo_weight_tons: parseFloat(weight),
        cargo_description: cargoDescription.replace(/\s+/g, " ").trim(),
        cargo_type_category: cargoTypeCategory.trim(),
        terms_agreed: termsAccepted,
        terms_signer_name: termsSignerName || undefined,
        cargo_declaration: cargoDeclaration!,
        terms_e_signature: termsSignature!,
        vehicle_class: "Class 3",
        distance_km_override: manualDistanceKm.trim()
          ? Number(manualDistanceKm)
          : cost?.distance_km && cost.distance_km > 0
            ? cost.distance_km
            : undefined,
      });

      router.push(customerBookingPaymentPath(data.id));
    } catch (error) {
      const err = error as Error;
      setMessage(` Error: ${err.message}`);
      setMessageType("error");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div style={{ display: "grid", gap: "1.5rem" }}>
      {!hasEnoughSites && (
        <div
          role="alert"
          style={{
            padding: "1rem",
            borderRadius: "10px",
            background: "rgba(239, 68, 68, 0.1)",
            border: "1px solid rgba(220, 38, 38, 0.45)",
            color: "#b91c1c",
            fontSize: "0.95rem",
          }}
        >
          <strong>Booking not available yet.</strong> Add at least {MIN_BOOKING_SITES} site addresses under{" "}
          <Link href="/dashboard/customer" style={{ fontWeight: 700, color: "inherit" }}>
            Customer dashboard → Sites
          </Link>{" "}
          before you can place a booking.
        </div>
      )}

      <BookingWizardStepper currentStep={currentStep} />

      <form onSubmit={handleSubmit} style={{ display: "grid", gap: "1.25rem" }}>
        {errors.sites_min && (
          <p role="alert" style={{ margin: 0, color: "#b91c1c", fontSize: "0.9rem" }}>
            {errors.sites_min}
          </p>
        )}

        {currentStep === "route" && (
          <RouteStep
            sites={sites}
            hasEnoughSites={hasEnoughSites}
            pickupId={pickupId}
            dropoffId={dropoffId}
            pickup={pickup}
            dropoff={dropoff}
            errors={errors}
            cost={cost}
            loading={loading}
            bookingPricingHint={bookingPricingHint}
            routeQuoteMeta={routeQuoteMeta}
            distanceWarning={distanceWarning}
            distanceConfirmed={distanceConfirmed}
            manualDistanceKm={manualDistanceKm}
            quoteStatus={quoteStatus}
            showApproximateRoutingWarning={showApproximateRoutingWarning}
            onPickupIdChange={(id) => {
              setPickupId(id);
              setSelectedRouteOptionId(null);
              setManualDistanceKm("");
            }}
            onDropoffIdChange={(id) => {
              setDropoffId(id);
              setSelectedRouteOptionId(null);
              setManualDistanceKm("");
            }}
            onClearError={clearError}
            onManualDistanceKmChange={setManualDistanceKm}
            routeOptions={routeOptions}
            selectedRouteOptionId={selectedRouteOptionId}
            recommendedRouteOptionId={recommendedRouteOptionId}
            travelTimeLabel={travelTimeLabel}
            onSelectRouteOption={(optionId) => {
              if (optionId === selectedRouteOptionId) return;
              setSelectedRouteOptionId(optionId);
              setManualDistanceKm("");
            }}
          />
        )}

        {currentStep === "shipment" && (
          <ShipmentStep
            hasEnoughSites={hasEnoughSites}
            weight={weight}
            cargoDescription={cargoDescription}
            cargoTypeCategory={cargoTypeCategory}
            errors={errors}
            onWeightChange={setWeight}
            onCargoDescriptionChange={(value) => {
              setCargoDescription(value);
              clearError("cargo_description");
            }}
            onCargoTypeCategoryChange={(value) => {
              setCargoTypeCategory(value);
              clearError("cargo_type_category");
            }}
          />
        )}

        {currentStep === "schedule" && (
          <ScheduleStep
            hasEnoughSites={hasEnoughSites}
            date={date}
            today={today}
            pickedSlot={pickedSlot}
            slotsLoading={slotsLoading}
            slotsFetchError={slotsFetchError}
            slotAvailability={slotAvailability}
            requiredTrucks={requiredTrucks}
            selectedAvailableTrucks={selectedAvailableTrucks}
            onDateChange={setDate}
            onPickedSlotChange={setPickedSlot}
            errors={errors}
            onClearErrors={clearErrors}
          />
        )}

        {currentStep === "documents" && (
          <DocumentsStep
            cargoDeclaration={cargoDeclaration}
            termsSignature={termsSignature}
            termsAccepted={termsAccepted}
            termsScrolled={termsScrolled}
            disabled={!hasEnoughSites}
            errors={errors}
            onCargoDeclarationChange={setCargoDeclaration}
            onTermsSignatureChange={setTermsSignature}
            onTermsAcceptedChange={setTermsAccepted}
            onTermsScrolledChange={setTermsScrolled}
            onClearError={clearError}
          />
        )}

        {(currentStep === "review" || currentStep === "pricing" || currentStep === "payment") && (
          <ReviewStep
            mode={currentStep}
            pickup={pickup}
            dropoff={dropoff}
            weight={weight}
            cargoDescription={cargoDescription}
            cargoTypeCategory={cargoTypeCategory}
            date={date}
            pickedSlot={pickedSlot}
            cargoDeclaration={cargoDeclaration}
            termsSignature={termsSignature}
            termsAccepted={termsAccepted}
            termsScrolled={termsScrolled}
            cost={cost}
            freightLines={freightLines}
            routeQuoteMeta={routeQuoteMeta}
            tollEstimateMeta={tollEstimateMeta}
            distanceWarning={distanceWarning}
            distanceConfirmed={distanceConfirmed}
            manualDistanceKm={manualDistanceKm}
            manualTollEntry=""
            manualTollExit=""
            manualVehicleClass="Class 3"
            quoteStatus={quoteStatus}
            showApproximateRoutingWarning={showApproximateRoutingWarning}
            quoteLoading={loading}
            quoteReady={quoteReady}
            canSubmit={canSubmit}
            isSubmitting={isSubmitting}
            errors={errors}
            hasEnoughSites={hasEnoughSites}
            bookingPricingHint={bookingPricingHint}
            onManualDistanceKmChange={setManualDistanceKm}
            onManualTollEntryChange={() => {}}
            onManualTollExitChange={() => {}}
            onManualVehicleClassChange={() => {}}
          />
        )}

        {!isLastStep && (
          <div className="booking-wizard-nav">
            <button
              type="button"
              className="button button--secondary booking-wizard-nav__prev"
              onClick={handlePrev}
              disabled={isFirstStep}
            >
              Previous
            </button>
            <button
              type="button"
              className="button booking-wizard-nav__next"
              onClick={handleNext}
              disabled={!canGoNext}
            >
              Next
            </button>
          </div>
        )}

        {isLastStep && !isFirstStep && (
          <div className="booking-wizard-nav booking-wizard-nav--review">
            <button type="button" className="button button--secondary booking-wizard-nav__prev" onClick={handlePrev}>
              Previous
            </button>
          </div>
        )}

        {pickedSlot && selectedAvailableTrucks < requiredTrucks && currentStep === "review" && (
          <p role="alert" style={{ margin: 0, color: "#b91c1c", fontSize: "0.9rem" }}>
            Not enough free trucks, drivers, and helpers for this schedule. Please choose another date/time.
          </p>
        )}

        {message && (
          <div
            style={{
              padding: "1rem",
              borderRadius: "8px",
              background: messageType === "success" ? "rgba(76, 175, 80, 0.1)" : "rgba(244, 67, 54, 0.1)",
              border: `1px solid ${messageType === "success" ? "#4CAF50" : "#F44336"}`,
              color: messageType === "success" ? "#4CAF50" : "#F44336",
              fontSize: "0.95rem",
            }}
          >
            {message}
          </div>
        )}
      </form>
    </div>
  );
}
