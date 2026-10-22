"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { CSSProperties, ReactNode } from "react";

import CustomerBookingAssignmentsList from "@/components/CustomerBookingAssignmentsList";
import ContactSupportButton from "@/components/ContactSupportButton";
import CustomerBookingQrCard from "@/components/CustomerBookingQrCard";
import CustomerDeliveryVerificationCard from "@/components/CustomerDeliveryVerificationCard";
import CustomerDocumentReviewSection from "@/components/CustomerDocumentReviewSection";
import CustomerNotificationsPanel from "@/components/CustomerNotificationsPanel";
import KpiCard from "@/components/KpiCard";
import SectionJumpLink from "@/components/ui/SectionJumpLink";
import AsyncDataView from "@/components/ui/AsyncDataView";
import LoadingMessage from "@/components/ui/LoadingMessage";
import { EMPTY_BOOKINGS, EMPTY_SHIPMENTS, ERROR_LOAD_DATA, LOADING_AUTH_RESTORE } from "@/lib/loadingMessages";
import { APP_LOCALE, APP_TIMEZONE, formatNumber, formatPhpWhole } from "@/lib/appLocale";
import { customerWorkflowCurrentLabel } from "@/lib/customerBookingWorkflow";
import {
  MIN_BOOKING_SITES,
  addCustomerSite,
  loadCustomerSites,
  removeCustomerSite,
  subscribeSitesChanged,
  type CustomerSite,
} from "@/lib/customerSites";
import { WorkflowApi, type CustomerBookingHistoryRow, type CustomerBookingRow, type Payment } from "@/lib/workflowApi";
import { useHashScrollWhenReady } from "@/lib/useHashScrollWhenReady";
import { useRoleGuard } from "@/lib/useRoleGuard";


function formatShortDate(iso: string): string {
  try {
    return new Intl.DateTimeFormat(APP_LOCALE, {
      timeZone: APP_TIMEZONE,
      month: "short",
      day: "numeric",
      year: "numeric",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

const TRACKING_PAGE_SIZE = 3;
const SECTION_PAGE_SIZE = 4;

const PENDING_PAYMENT_STATUSES = new Set([
  "pending_payment",
  "payment_verification",
  "payment_rejected",
]);

const ONGOING_STATUSES = new Set([
  "assigned",
  "approved",
  "payment_verified",
  "ready_for_assignment",
  "for_pickup",
  "picked_up",
  "en_route",
  "out_for_delivery",
  "dropped_off",
  "accepted",
  "loading",
]);

export default function CustomerPortalDashboard() {
  const { ready, allowed } = useRoleGuard(["customer"]);
  const [activeShipments, setActiveShipments] = useState<CustomerBookingRow[]>([]);
  const [historyRows, setHistoryRows] = useState<CustomerBookingHistoryRow[]>([]);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notificationUnread, setNotificationUnread] = useState(0);
  const [sites, setSites] = useState<CustomerSite[]>([]);
  const [trackingPage, setTrackingPage] = useState(0);
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({
    pending: true,
    ongoing: true,
    completed: false,
    cancelled: false,
  });
  const [showDeliveryVerification, setShowDeliveryVerification] = useState(false);
  const [sectionPages, setSectionPages] = useState<Record<string, number>>({
    pending: 0,
    ongoing: 0,
    completed: 0,
    cancelled: 0,
  });
  const [newSiteLabel, setNewSiteLabel] = useState("");
  const [newSiteStreet, setNewSiteStreet] = useState("");
  const [newSiteBrgy, setNewSiteBrgy] = useState("");
  const [newSiteCity, setNewSiteCity] = useState("");
  const [newSiteProvince, setNewSiteProvince] = useState("");
  const [newSitePostal, setNewSitePostal] = useState("");
  const [siteFormError, setSiteFormError] = useState<string | null>(null);
  useEffect(() => {
    if (!ready || !allowed) return;
    let cancelled = false;
    (async () => {
      try {
        const [shipRes, hist, p] = await Promise.all([
          WorkflowApi.customerShipmentTracking(),
          WorkflowApi.customerBookingHistory(),
          WorkflowApi.listPayments(),
        ]);
        if (!cancelled) {
          setActiveShipments(shipRes.shipments);
          setHistoryRows(hist);
          setPayments(p);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : ERROR_LOAD_DATA);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [ready, allowed]);

  useEffect(() => {
    if (!ready || !allowed) return;
    let cancelled = false;
    const refresh = () => {
      loadCustomerSites()
        .then((list) => {
          if (!cancelled) setSites(list);
        })
        .catch((e) => {
          console.error(e);
        });
    };
    refresh();
    return subscribeSitesChanged(refresh);
  }, [ready, allowed]);

  const paymentByBooking = useMemo(() => {
    const m = new Map<number, Payment>();
    for (const p of payments) {
      const cur = m.get(p.booking_id);
      if (!cur || p.id > cur.id) m.set(p.booking_id, p);
    }
    return m;
  }, [payments]);

  const refreshShipments = useCallback(async () => {
    try {
      const shipRes = await WorkflowApi.customerShipmentTracking();
      setActiveShipments(shipRes.shipments);
    } catch (e) {
      console.error(e);
    }
  }, []);

  useEffect(() => {
    if (!ready || !allowed) return;
    const onVis = () => {
      if (document.visibilityState === "visible") void refreshShipments();
    };
    const onFocus = () => void refreshShipments();
    document.addEventListener("visibilitychange", onVis);
    window.addEventListener("focus", onFocus);
    const poll = window.setInterval(() => {
      if (document.visibilityState === "visible") void refreshShipments();
    }, 15000);
    return () => {
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("focus", onFocus);
      window.clearInterval(poll);
    };
  }, [ready, allowed, refreshShipments]);

  const historyCount = historyRows.length;
  const completedCount = useMemo(
    () => historyRows.filter((x) => x.display_status === "completed").length,
    [historyRows],
  );

  // Red mark tracks unread notifications only — clears after the user views them.
  const alertBadgeCount = notificationUnread;

  const bookingBuckets = useMemo(() => {
    const pendingPayments = activeShipments.filter((b) => PENDING_PAYMENT_STATUSES.has(b.display_status));
    const ongoing = activeShipments.filter((b) => ONGOING_STATUSES.has(b.display_status));
    const completed = historyRows.filter((b) => b.display_status === "completed");
    const cancelled = historyRows.filter((b) =>
      ["cancelled", "rejected", "expired", "payment_rejected"].includes(b.display_status),
    );
    return { pendingPayments, ongoing, completed, cancelled };
  }, [activeShipments, historyRows]);

  const kpis = useMemo(() => {
    const totalOrders = activeShipments.length + historyCount;
    const paid = payments.filter((p) => p.status === "verified");
    const spent = paid.reduce((s, p) => s + p.amount, 0);
    const done = completedCount;
    const rate = totalOrders ? Math.round((done / totalOrders) * 1000) / 10 : 0;
    const inTransit = activeShipments.filter((b) =>
      ["en_route", "out_for_delivery", "picked_up", "dropped_off", "for_pickup"].includes(b.display_status),
    ).length;
    const pendingPickup = activeShipments.filter((b) =>
      ["assigned", "approved", "payment_verified", "ready_for_assignment", "for_pickup"].includes(b.display_status),
    ).length;
    return {
      activeCount: activeShipments.length,
      inTransit,
      pendingPickup,
      totalOrders,
      spent,
      spentLabel: spent >= 1000 ? `₱${formatNumber(spent / 1000, { maximumFractionDigits: 1 })}K` : formatPhpWhole(Math.round(spent)),
      rate,
      thisMonth: activeShipments.filter((b) => {
        const t = new Date(b.created_at).getTime();
        const now = new Date();
        return t > now.getTime() - 31 * 86400000;
      }).length,
    };
  }, [activeShipments, historyCount, completedCount, payments]);

  const activeShow = useMemo(() => {
    const prioritized = [...activeShipments].sort((a, b) => {
      const rank = (s: string) =>
        [
          "dropped_off",
          "en_route",
          "out_for_delivery",
          "picked_up",
          "for_pickup",
          "assigned",
          "approved",
          "payment_verified",
          "ready_for_assignment",
          "payment_verification",
          "pending_payment",
        ].indexOf(s);
      return rank(a.display_status) - rank(b.display_status);
    });
    return prioritized;
  }, [activeShipments]);

  const trackingPageCount = Math.max(1, Math.ceil(activeShow.length / TRACKING_PAGE_SIZE));
  const trackingPageSafe = Math.min(trackingPage, trackingPageCount - 1);
  const trackingPageItems = useMemo(() => {
    const start = trackingPageSafe * TRACKING_PAGE_SIZE;
    return activeShow.slice(start, start + TRACKING_PAGE_SIZE);
  }, [activeShow, trackingPageSafe]);

  useEffect(() => {
    if (trackingPage !== trackingPageSafe) setTrackingPage(trackingPageSafe);
  }, [trackingPage, trackingPageSafe]);

  useEffect(() => {
    setTrackingPage(0);
  }, [activeShipments.length]);

  const txRows = useMemo(
    () =>
      payments
        .filter((p) => p.status === "verified")
        .slice(0, 5)
        .map((p) => ({
          id: p.id,
          when: formatShortDate(p.paid_at || p.created_at),
          amt: formatPhpWhole(p.amount),
          state: "Paid" as const,
        })),
    [payments],
  );

  useHashScrollWhenReady(ready && allowed && !loading && !error);

  if (!ready) {
    return (
      <main className="dashboard-standard-main">
        <LoadingMessage label={LOADING_AUTH_RESTORE} />
      </main>
    );
  }

  if (!allowed) return null;

  return (
    <main className="dashboard-standard-main">
      <div className="dashboard-standard-inner" style={{ maxWidth: 1280 }}>
        <AsyncDataView
          loading={loading}
          error={error}
          loadingLabel="Loading your data…"
          variant="dashboard"
          onRetry={() => window.location.reload()}
        >
        {!loading && !error && (
          <>
            <nav className="tab-pills" aria-label="Jump to portal section">
              <SectionJumpLink targetId="customer-kpis">Overview</SectionJumpLink>
              {alertBadgeCount > 0 ? (
                <SectionJumpLink targetId="customer-notifications">
                  Alerts
                  <span
                    style={{
                      marginLeft: 6,
                      display: "inline-flex",
                      alignItems: "center",
                      justifyContent: "center",
                      minWidth: 20,
                      height: 20,
                      padding: "0 6px",
                      borderRadius: 999,
                      background: "#DC2626",
                      color: "#fff",
                      fontSize: "0.72rem",
                      fontWeight: 800,
                    }}
                  >
                    {alertBadgeCount}
                  </span>
                </SectionJumpLink>
              ) : null}
              <SectionJumpLink targetId="customer-delivery-verification">Delivery Verification</SectionJumpLink>
              <SectionJumpLink targetId="customer-tracking">
                Tracking
                {alertBadgeCount > 0 ? (
                  <span
                    aria-hidden
                    style={{
                      marginLeft: 6,
                      width: 8,
                      height: 8,
                      borderRadius: 999,
                      background: "#DC2626",
                      display: "inline-block",
                    }}
                  />
                ) : null}
              </SectionJumpLink>
              <SectionJumpLink targetId="customer-booking-sections">Bookings</SectionJumpLink>
              <SectionJumpLink targetId="customer-sites">Sites</SectionJumpLink>
            </nav>

            <div id="customer-notifications" className="scroll-section" style={{ display: "grid", gap: "0.85rem" }}>
              <CustomerNotificationsPanel onUnreadChange={setNotificationUnread} />
            </div>

            <section
              id="customer-kpis"
              className="scroll-section safe-auto-grid-200"
            >
              <KpiCard label="Active bookings" value={kpis.activeCount} delta={`${kpis.inTransit} in motion · ${kpis.pendingPickup} pre-dispatch`} tone="neutral" scrollTargetId="customer-tracking" />
              <KpiCard label="Total orders" value={kpis.totalOrders} delta={`${kpis.thisMonth} in last ~31 days`} tone="neutral" />
              <KpiCard
                label="Total paid"
                value={kpis.totalOrders ? kpis.spentLabel : "—"}
                delta={payments.length ? `${payments.length} payment row(s)` : "No payments yet"}
                tone="neutral"
              />
              <KpiCard label="Fulfillment snapshot" value={`${kpis.rate}%`} delta="Completed vs all bookings" trend={kpis.rate >= 90 ? "up" : "flat"} tone={kpis.rate >= 90 ? "success" : "neutral"} />
            </section>

            <section id="customer-delivery-verification" className="card scroll-section" style={{ display: "grid", gap: showDeliveryVerification ? "1rem" : "0.5rem" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap" }}>
                <div>
                  <h2 style={{ margin: 0 }}>Delivery Verification</h2>
                  <p style={{ margin: "0.35rem 0 0", color: "var(--text-secondary)", fontSize: "0.9rem" }}>
                    {activeShow.some((order) => order.delivery_verification_active)
                      ? "Your QR codes and backup codes are ready when your shipment arrives."
                      : "QR codes and backup codes appear here after payment is verified."}
                  </p>
                </div>
                {activeShow.some((order) => order.delivery_verification_active) ? (
                  <button
                    type="button"
                    className="button"
                    aria-expanded={showDeliveryVerification}
                    aria-controls="customer-delivery-verification-cards"
                    onClick={() => setShowDeliveryVerification((open) => !open)}
                    style={{ minHeight: 0, padding: "0.55rem 0.8rem", whiteSpace: "nowrap" }}
                  >
                    {showDeliveryVerification ? "Hide codes" : `Show codes (${activeShow.filter((order) => order.delivery_verification_active).length})`}
                  </button>
                ) : null}
              </div>
              {showDeliveryVerification && activeShow.some((order) => order.delivery_verification_active) ? (
                <div id="customer-delivery-verification-cards" className="safe-auto-grid-300">
                  {activeShow
                    .filter((order) => order.delivery_verification_active)
                    .map((order) => (
                      <CustomerDeliveryVerificationCard
                        key={order.id}
                        bookingId={order.id}
                        payload={order.delivery_verification_qr_payload}
                        verificationCode={order.delivery_verification_code}
                        active={order.delivery_verification_active}
                        used={order.delivery_verification_used}
                        usedAt={order.delivery_verification_used_at}
                      />
                    ))}
                </div>
              ) : null}
            </section>

            <section className="dashboard-standard-grid">
              <div
                id="customer-tracking"
                className="card scroll-section"
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "1rem",
                  minWidth: 0,
                }}
              >
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    flexWrap: "wrap",
                    gap: "0.5rem",
                    flexShrink: 0,
                  }}
                >
                  <h2 style={{ margin: 0 }}>Shipment tracking</h2>
                  <a href="/modules/operations/trips" style={{ color: "var(--brand-text-strong)", textDecoration: "none", fontSize: "0.9rem", fontWeight: 600 }}>
                    Trips overview
                  </a>
                </div>

                {activeShow.length === 0 ? (
                  <p style={{ margin: 0, color: "var(--text-secondary)" }} role="status">
                    {EMPTY_SHIPMENTS}
                  </p>
                ) : (
                  <>
                    <div
                      className="customer-tracking-booking-list"
                      style={{
                        display: "grid",
                        gap: "1rem",
                        maxHeight: 750,
                        overflowY: "auto",
                        overflowX: "hidden",
                        paddingRight: "0.25rem",
                        WebkitOverflowScrolling: "touch",
                      }}
                    >
                      {trackingPageItems.map((order) => {
                        return (
                          <div
                            key={order.id}
                            className="customer-tracking-booking-card"
                            style={{
                              border: "1px solid var(--border)",
                              borderRadius: "12px",
                              padding: "1rem",
                              display: "grid",
                              gap: "0.75rem",
                              background: "#FAFAFA",
                              minWidth: 0,
                              maxWidth: "100%",
                              height: "auto",
                            }}
                          >
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start", gap: "0.75rem", flexWrap: "wrap" }}>
                              <div>
                                <div style={{ fontWeight: "700", marginBottom: "0.25rem" }}>Booking #{order.id}</div>
                                <div style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>Pickup {formatShortDate(`${order.scheduled_date}`)}</div>
                              </div>
                              <ShipmentBadge status={customerWorkflowCurrentLabel(order, paymentByBooking.get(order.id) ?? null)} />
                            </div>
                            <div style={{ fontSize: "0.9rem", display: "grid", gap: "0.35rem" }}>
                              <div><span style={{ color: "var(--text-secondary)" }}>From:</span> {order.pickup_location}</div>
                              <div><span style={{ color: "var(--text-secondary)" }}>To:</span> {order.dropoff_location}</div>
                              <CustomerBookingQrCard
                                bookingId={order.id}
                                payload={order.booking_qr_payload}
                                verificationCode={order.booking_qr_code ?? null}
                                verified={Boolean(order.booking_qr_verified)}
                                verifiedAt={order.booking_qr_verified_at ?? null}
                                compact
                              />
                              <div style={{ marginTop: "0.25rem" }}>
                                <CustomerBookingAssignmentsList
                                  assignments={order.assignments}
                                  dropoffAddress={order.dropoff_location}
                                  showDeliveryTimeline
                                />
                              </div>
                            </div>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "0.88rem", flexWrap: "wrap", gap: "0.35rem" }}>
                              <span style={{ color: "var(--text-secondary)" }}>
                                Payment total <strong>{formatPhpWhole(Number(order.estimated_cost))}</strong>
                              </span>
                              <div style={{ display: "flex", gap: "0.65rem", alignItems: "center", flexWrap: "wrap" }}>
                                <ContactSupportButton
                                  bookingId={order.id}
                                  style={{
                                    fontSize: "0.82rem",
                                    padding: "0.35rem 0.75rem",
                                    minHeight: 0,
                                  }}
                                />
                                <Link href={`/modules/operations/trips?booking=${order.id}`} style={{ color: "var(--brand-text-strong)", textDecoration: "none", fontWeight: 600 }}>
                                  Track booking
                                </Link>
                              </div>
                            </div>
                            <CustomerDocumentReviewSection
                              booking={order}
                              payment={paymentByBooking.get(order.id) ?? null}
                              compact
                              onUpdated={() => void refreshShipments()}
                            />
                          </div>
                        );
                      })}
                    </div>
                    {activeShow.length > TRACKING_PAGE_SIZE ? (
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          gap: "0.75rem",
                          flexWrap: "wrap",
                          flexShrink: 0,
                        }}
                      >
                        <span style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
                          Page {trackingPageSafe + 1} of {trackingPageCount} · {activeShow.length} bookings
                        </span>
                        <div style={{ display: "flex", gap: "0.5rem" }}>
                          <button
                            type="button"
                            className="quick-action-btn"
                            disabled={trackingPageSafe <= 0}
                            onClick={() => setTrackingPage((p) => Math.max(0, p - 1))}
                          >
                            Previous
                          </button>
                          <button
                            type="button"
                            className="quick-action-btn"
                            disabled={trackingPageSafe >= trackingPageCount - 1}
                            onClick={() => setTrackingPage((p) => Math.min(trackingPageCount - 1, p + 1))}
                          >
                            Next
                          </button>
                        </div>
                      </div>
                    ) : null}
                  </>
                )}
              </div>

              <div style={{ display: "grid", gap: "1.25rem", minWidth: 0, alignContent: "start" }}>
                <div
                  id="customer-sites"
                  className="card scroll-section"
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "0.85rem",
                    minWidth: 0,
                    maxHeight: "min(70vh, 560px)",
                    overflow: "hidden",
                  }}
                >
                  <h2 style={{ margin: 0, flexShrink: 0 }}>Sites</h2>
                  <div
                    style={{
                      display: "grid",
                      gap: "0.85rem",
                      minHeight: 0,
                      flex: 1,
                      overflowY: "auto",
                      overflowX: "hidden",
                      paddingRight: "0.25rem",
                      WebkitOverflowScrolling: "touch",
                    }}
                  >
                  <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--text-secondary)" }}>
                    Use separate fields: street, district or village, city or municipality, province, and zip code —
                    the full line is built automatically for bookings and pricing. You need at least {MIN_BOOKING_SITES} sites
                    before you can book.
                  </p>
                  <p style={{ margin: 0, fontSize: "0.9rem", fontWeight: 700 }}>
                    {sites.length} saved · minimum {MIN_BOOKING_SITES} to book
                  </p>
                  {sites.length === 0 ? (
                    <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--text-secondary)" }}>No sites yet — add your first address below.</p>
                  ) : (
                    <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "grid", gap: "0.5rem" }}>
                      {sites.map((s) => (
                        <li
                          key={s.id}
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            gap: "0.5rem",
                            alignItems: "start",
                            fontSize: "0.85rem",
                            padding: "0.5rem 0",
                            borderBottom: "1px solid var(--border)",
                          }}
                        >
                          <span>
                            {s.label ? (
                              <>
                                <strong>{s.label}</strong>
                                <br />
                              </>
                            ) : null}
                            {s.street ? (
                              <span style={{ color: "var(--text-secondary)", lineHeight: 1.55, display: "block" }}>
                                <span>
                                  <strong>Street:</strong> {s.street}
                                </span>
                                <br />
                                <span>
                                  <strong>District / village:</strong> {s.barangay ?? "—"}
                                </span>
                                <br />
                                <span>
                                  <strong>City / municipality:</strong> {s.cityMunicipality ?? "—"}
                                </span>
                                <br />
                                <span>
                                  <strong>Province:</strong> {s.province ?? "—"} ·{" "}
                                  <strong>Zip:</strong> {s.postalCode ?? "—"}
                                </span>
                              </span>
                            ) : (
                              <span style={{ color: "var(--text-secondary)" }}>{s.address}</span>
                            )}
                          </span>
                          <button
                            type="button"
                            onClick={() => {
                              const summary =
                                s.label?.trim() ||
                                (s.street ? [s.street, s.cityMunicipality].filter(Boolean).join(", ") : s.address.trim()) ||
                                "this site";
                              const ok = window.confirm(
                                `Are you sure you want to delete this saved site?\n\n${summary}`,
                              );
                              if (!ok) return;
                              void removeCustomerSite(s.id).catch(() => undefined);
                            }}
                            style={{
                              border: "1px solid var(--border)",
                              background: "#fff",
                              borderRadius: 6,
                              fontSize: "0.72rem",
                              fontWeight: 600,
                              cursor: "pointer",
                              padding: "0.25rem 0.45rem",
                              color: "#b91c1c",
                              flexShrink: 0,
                            }}
                          >
                            Remove
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                  <div style={{ display: "grid", gap: "0.45rem" }}>
                    <label style={{ fontSize: "0.78rem", fontWeight: 600, color: "var(--text-secondary)" }}>
                      Site name (optional)
                    </label>
                    <input
                      className="input"
                      value={newSiteLabel}
                      onChange={(e) => {
                        setNewSiteLabel(e.target.value);
                        if (siteFormError) setSiteFormError(null);
                      }}
                      placeholder="e.g. Main warehouse"
                    />

                    <div className="safe-auto-grid-140">
                      <label style={{ display: "grid", gap: "0.25rem", fontSize: "0.78rem", fontWeight: 600, color: "var(--text-secondary)", marginTop: "0.2rem", gridColumn: "1 / -1" }}>
                        Street
                        <input
                          className="input"
                          value={newSiteStreet}
                          onChange={(e) => {
                            setNewSiteStreet(e.target.value);
                            if (siteFormError) setSiteFormError(null);
                          }}
                          placeholder="Building / house no., street name"
                          autoComplete="street-address"
                        />
                      </label>
                      <label style={{ display: "grid", gap: "0.25rem", fontSize: "0.78rem", fontWeight: 600, color: "var(--text-secondary)" }}>
                        District / village
                        <input
                          className="input"
                          value={newSiteBrgy}
                          onChange={(e) => {
                            setNewSiteBrgy(e.target.value);
                            if (siteFormError) setSiteFormError(null);
                          }}
                          placeholder="e.g. Bagong Nayon"
                        />
                      </label>
                      <label style={{ display: "grid", gap: "0.25rem", fontSize: "0.78rem", fontWeight: 600, color: "var(--text-secondary)" }}>
                        City / municipality
                        <input
                          className="input"
                          value={newSiteCity}
                          onChange={(e) => {
                            setNewSiteCity(e.target.value);
                            if (siteFormError) setSiteFormError(null);
                          }}
                          placeholder="e.g. Rodriguez"
                        />
                      </label>
                      <label style={{ display: "grid", gap: "0.25rem", fontSize: "0.78rem", fontWeight: 600, color: "var(--text-secondary)" }}>
                        Province
                        <input
                          className="input"
                          value={newSiteProvince}
                          onChange={(e) => {
                            setNewSiteProvince(e.target.value);
                            if (siteFormError) setSiteFormError(null);
                          }}
                          placeholder="e.g. Rizal"
                        />
                      </label>
                      <label style={{ display: "grid", gap: "0.25rem", fontSize: "0.78rem", fontWeight: 600, color: "var(--text-secondary)" }}>
                        Zip code
                        <input
                          className="input"
                          value={newSitePostal}
                          onChange={(e) => {
                            setNewSitePostal(e.target.value);
                            if (siteFormError) setSiteFormError(null);
                          }}
                          placeholder="e.g. 1860"
                          inputMode="numeric"
                          autoComplete="postal-code"
                        />
                      </label>
                    </div>
                    {siteFormError && (
                      <p role="alert" style={{ margin: 0, fontSize: "0.8rem", color: "var(--text-error, #DC2626)" }}>
                        {siteFormError}
                      </p>
                    )}
                    <button
                      type="button"
                      className="button"
                      style={{ marginTop: "0.25rem" }}
                      onClick={() => {
                        void (async () => {
                          const res = await addCustomerSite(
                            {
                              street: newSiteStreet,
                              barangay: newSiteBrgy,
                              cityMunicipality: newSiteCity,
                              province: newSiteProvince,
                              postalCode: newSitePostal,
                            },
                            newSiteLabel,
                          );
                          if (!res.ok) {
                            setSiteFormError(res.message);
                            return;
                          }
                          setNewSiteStreet("");
                          setNewSiteBrgy("");
                          setNewSiteCity("");
                          setNewSiteProvince("");
                          setNewSitePostal("");
                          setNewSiteLabel("");
                          setSiteFormError(null);
                        })();
                      }}
                    >
                      Add site
                    </button>
                  </div>
                  <div id="customer-bookings" className="scroll-section">
                  {sites.length >= MIN_BOOKING_SITES ? (
                      <CustomerCtaPrimary href="/booking">+ New booking</CustomerCtaPrimary>
                  ) : (
                    <div
                      style={{
                        padding: "0.85rem",
                        borderRadius: 10,
                        textAlign: "center",
                        fontWeight: 700,
                        background: "#E5E7EB",
                        color: "#6B7280",
                        fontSize: "0.9rem",
                      }}
                    >
                      Add {MIN_BOOKING_SITES - sites.length} more site{MIN_BOOKING_SITES - sites.length === 1 ? "" : "s"} to enable booking
                    </div>
                  )}
                  </div>
                  </div>
                </div>

                <div className="card" style={{ display: "grid", gap: "1rem" }}>
                  <h2 style={{ margin: 0 }}>Account</h2>
                  <RowKv label="Member reference" value={`Customer ID (session)`} />
                  <RowKv
                    label="Feedback"
                    value={
                      <Link href="/modules/customer/support" style={{ color: "var(--brand-text-strong)", fontWeight: 600 }}>
                        Send feedback
                      </Link>
                    }
                  />
                  <CustomerCtaGhost href="/modules/customer/profile">View profile</CustomerCtaGhost>
                </div>

                <div className="card" style={{ display: "grid", gap: "0.75rem" }}>
                  <h2 style={{ margin: 0 }}>Recent payments</h2>
                  {txRows.length === 0 ? (
                    <p style={{ margin: 0, fontSize: "0.88rem", color: "var(--text-secondary)" }}>No paid transactions yet.</p>
                  ) : (
                    txRows.map((tx) => (
                      <div key={tx.id} style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem", fontSize: "0.88rem", borderBottom: "1px solid var(--border)", paddingBottom: "0.55rem" }}>
                        <div>
                          <div style={{ fontWeight: 600 }}>{tx.amt}</div>
                          <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>{tx.when}</div>
                        </div>
                        <span style={{ fontWeight: 700, color: "var(--text-success)", fontSize: "0.8rem", alignSelf: "center" }}>{tx.state}</span>
                      </div>
                    ))
                  )}
                  <Link href="/modules/customer/payment" style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--brand-text-strong)" }}>
                    Payments &amp; receipts
                  </Link>
                </div>
              </div>
            </section>

            <section
              id="customer-booking-sections"
              className="card scroll-section"
              style={{ display: "grid", gap: "0.85rem" }}
            >
              <div>
                <h2 style={{ margin: 0 }}>Bookings by status</h2>
                <p style={{ margin: "0.35rem 0 0", color: "var(--text-secondary)", fontSize: "0.9rem" }}>
                  Pending payments, ongoing deliveries, and closed bookings are grouped below. Shipment tracking above
                  stays focused on active movement.
                </p>
              </div>
              {(
                [
                  {
                    key: "pending",
                    title: "Pending payments",
                    rows: bookingBuckets.pendingPayments,
                    empty: "No bookings awaiting payment.",
                    tone: "#92400E",
                    bg: "#FFFBEB",
                  },
                  {
                    key: "ongoing",
                    title: "Ongoing deliveries",
                    rows: bookingBuckets.ongoing,
                    empty: "No deliveries in progress.",
                    tone: "#1E40AF",
                    bg: "#EFF6FF",
                  },
                  {
                    key: "completed",
                    title: "Completed deliveries",
                    rows: bookingBuckets.completed,
                    empty: "No completed deliveries yet.",
                    tone: "#166534",
                    bg: "#ECFDF5",
                  },
                  {
                    key: "cancelled",
                    title: "Cancelled / Rejected",
                    rows: bookingBuckets.cancelled,
                    empty: "No cancelled or rejected bookings.",
                    tone: "#991B1B",
                    bg: "#FEF2F2",
                  },
                ] as const
              ).map((section) => {
                const open = openSections[section.key] ?? false;
                const page = sectionPages[section.key] ?? 0;
                const pageCount = Math.max(1, Math.ceil(section.rows.length / SECTION_PAGE_SIZE));
                const pageSafe = Math.min(page, pageCount - 1);
                const pageRows = section.rows.slice(
                  pageSafe * SECTION_PAGE_SIZE,
                  pageSafe * SECTION_PAGE_SIZE + SECTION_PAGE_SIZE,
                );
                return (
                  <div
                    key={section.key}
                    style={{
                      border: "1px solid var(--border)",
                      borderRadius: 10,
                      overflow: "hidden",
                      background: "#fff",
                    }}
                  >
                    <button
                      type="button"
                      aria-expanded={open}
                      onClick={() =>
                        setOpenSections((prev) => ({ ...prev, [section.key]: !open }))
                      }
                      style={{
                        width: "100%",
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        gap: "0.75rem",
                        padding: "0.85rem 1rem",
                        border: "none",
                        background: section.bg,
                        color: section.tone,
                        cursor: "pointer",
                        textAlign: "left",
                        minHeight: 48,
                      }}
                    >
                      <span style={{ fontWeight: 800, fontSize: "0.95rem" }}>{section.title}</span>
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 8, fontWeight: 700 }}>
                        <span
                          style={{
                            minWidth: 24,
                            height: 24,
                            padding: "0 7px",
                            borderRadius: 999,
                            background: "#fff",
                            color: section.tone,
                            display: "inline-flex",
                            alignItems: "center",
                            justifyContent: "center",
                            fontSize: "0.8rem",
                          }}
                        >
                          {section.rows.length}
                        </span>
                        <span aria-hidden>{open ? "▾" : "▸"}</span>
                      </span>
                    </button>
                    {open ? (
                      <div style={{ padding: "0.85rem 1rem", display: "grid", gap: "0.65rem" }}>
                        {section.rows.length === 0 ? (
                          <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "0.88rem" }}>{section.empty}</p>
                        ) : (
                          <>
                            {pageRows.map((row) => (
                              <div
                                key={`${section.key}-${row.id}`}
                                style={{
                                  display: "flex",
                                  justifyContent: "space-between",
                                  gap: "0.75rem",
                                  flexWrap: "wrap",
                                  alignItems: "center",
                                  padding: "0.65rem 0.75rem",
                                  borderRadius: 8,
                                  border: "1px solid #E5E7EB",
                                  background: "#FAFAFA",
                                }}
                              >
                                <div style={{ minWidth: 0 }}>
                                  <div style={{ fontWeight: 700 }}>Booking #{row.id}</div>
                                  <div style={{ fontSize: "0.82rem", color: "var(--text-secondary)", marginTop: 2 }}>
                                    {row.pickup_location} → {row.dropoff_location}
                                  </div>
                                  <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)", marginTop: 2 }}>
                                    {formatShortDate(`${row.scheduled_date}`)} ·{" "}
                                    {customerWorkflowCurrentLabel(row, paymentByBooking.get(row.id) ?? null)}
                                  </div>
                                </div>
                                <Link
                                  href={`/modules/operations/trips?booking=${row.id}`}
                                  style={{
                                    color: "var(--brand-text-strong)",
                                    fontWeight: 700,
                                    fontSize: "0.85rem",
                                    textDecoration: "none",
                                    minHeight: 40,
                                    display: "inline-flex",
                                    alignItems: "center",
                                  }}
                                >
                                  View
                                </Link>
                              </div>
                            ))}
                            {section.rows.length > SECTION_PAGE_SIZE ? (
                              <div
                                style={{
                                  display: "flex",
                                  justifyContent: "space-between",
                                  alignItems: "center",
                                  gap: "0.5rem",
                                  flexWrap: "wrap",
                                }}
                              >
                                <span style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                                  Page {pageSafe + 1} of {pageCount}
                                </span>
                                <div style={{ display: "flex", gap: 8 }}>
                                  <button
                                    type="button"
                                    className="quick-action-btn"
                                    disabled={pageSafe <= 0}
                                    onClick={() =>
                                      setSectionPages((prev) => ({
                                        ...prev,
                                        [section.key]: Math.max(0, pageSafe - 1),
                                      }))
                                    }
                                  >
                                    Previous
                                  </button>
                                  <button
                                    type="button"
                                    className="quick-action-btn"
                                    disabled={pageSafe >= pageCount - 1}
                                    onClick={() =>
                                      setSectionPages((prev) => ({
                                        ...prev,
                                        [section.key]: Math.min(pageCount - 1, pageSafe + 1),
                                      }))
                                    }
                                  >
                                    Next
                                  </button>
                                </div>
                              </div>
                            ) : null}
                          </>
                        )}
                      </div>
                    ) : null}
                  </div>
                );
              })}
              <Link
                href="/modules/customer/booking-history"
                style={{ fontSize: "0.88rem", fontWeight: 700, color: "var(--brand-text-strong)" }}
              >
                Open full booking history →
              </Link>
            </section>
          </>
        )}
        </AsyncDataView>
      </div>
    </main>
  );
}

const badgeBase: CSSProperties = {
  padding: "0.3rem 0.65rem",
  borderRadius: 6,
  fontSize: "0.78rem",
  fontWeight: 700,
  whiteSpace: "nowrap",
};

function ShipmentBadge({ status }: { status: string }) {
  const s = status.toLowerCase();
  if (s.includes("complet")) return <span style={{ ...badgeBase, background: "rgba(5,150,105,0.12)", color: "#047857" }}>{status}</span>;
  if (s.includes("route") || s.includes("arrived") || s.includes("pickup") || s.includes("destination") || s.includes("driver"))
    return <span style={{ ...badgeBase, background: "rgba(37,99,235,0.12)", color: "var(--brand-text-strong)" }}>{status}</span>;
  if (s.includes("payment") || s.includes("goods") || s.includes("dispatch") || s.includes("submitted"))
    return <span style={{ ...badgeBase, background: "rgba(251,191,36,0.35)", color: "#92400e" }}>{status}</span>;
  return <span style={{ ...badgeBase, background: "#F3F4F6", color: "#475569" }}>{status}</span>;
}

function RowKv({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="row-kv">
      <span className="row-kv__label">{label}</span>
      <span className="row-kv__value">{value}</span>
    </div>
  );
}

function CustomerCtaPrimary({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link
      href={href}
      style={{
        padding: "0.85rem",
        borderRadius: 10,
        textAlign: "center",
        fontWeight: 700,
        textDecoration: "none",
        background: "linear-gradient(135deg, #F57C00, #FF9800)",
        color: "#fff",
        display: "block",
      }}
    >
      {children}
    </Link>
  );
}

function CustomerCtaGhost({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link
      href={href}
      style={{
        padding: "0.65rem",
        borderRadius: 8,
        textAlign: "center",
        border: "1px solid var(--border)",
        fontWeight: 600,
        textDecoration: "none",
        color: "var(--brand-text-strong)",
        background: "#fff",
        display: "block",
      }}
    >
      {children}
    </Link>
  );
}
