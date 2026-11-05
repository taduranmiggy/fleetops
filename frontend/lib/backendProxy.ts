import type { NextRequest } from "next/server";

const HOP_BY_HOP = new Set([
  "connection",
  "content-length",
  "host",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailers",
  "transfer-encoding",
  "upgrade",
]);

export function backendOrigin(): string {
  const configured = (process.env.BACKEND_ORIGIN || "").trim();
  if (configured) {
    let parsed: URL;
    try {
      parsed = new URL(configured);
    } catch {
      throw new Error("BACKEND_ORIGIN must be a complete URL.");
    }
    const host = parsed.hostname.toLowerCase();
    if (process.env.NODE_ENV === "production") {
      if (
        parsed.protocol !== "https:" ||
        host === "localhost" ||
        host.endsWith(".localhost") ||
        /^127(?:\.\d{1,3}){3}$/.test(host) ||
        host === "::1" ||
        host === "[::1]"
      ) {
        throw new Error("Production BACKEND_ORIGIN must be a non-local HTTPS URL.");
      }
      if (
        parsed.pathname !== "/" ||
        parsed.search ||
        parsed.hash ||
        parsed.username ||
        parsed.password
      ) {
        throw new Error(
          "Production BACKEND_ORIGIN must contain only the HTTPS origin, without a path or credentials.",
        );
      }
    }
    return parsed.origin;
  }
  if (process.env.NODE_ENV === "production") {
    throw new Error("BACKEND_ORIGIN is required in production.");
  }
  return "http://127.0.0.1:8000";
}

export async function proxyToBackend(req: NextRequest, backendPath: string): Promise<Response> {
  const incoming = new URL(req.url);
  const target = `${backendOrigin()}${backendPath.startsWith("/") ? backendPath : `/${backendPath}`}${incoming.search}`;
  const headers = new Headers();
  req.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) {
      headers.set(key, value);
    }
  });

  const init: RequestInit = {
    method: req.method,
    headers,
    redirect: "manual",
  };
  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = await req.arrayBuffer();
  }

  const upstream = await fetch(target, init);
  const outHeaders = new Headers();
  upstream.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) {
      outHeaders.set(key, value);
    }
  });
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: outHeaders,
  });
}
