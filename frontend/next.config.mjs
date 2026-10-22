import path from "node:path";
import { fileURLToPath } from "node:url";
import nextEnv from "@next/env";

const { loadEnvConfig } = nextEnv;
loadEnvConfig(process.cwd(), process.env.NODE_ENV !== "production");

const configDir = path.dirname(fileURLToPath(import.meta.url));
const monorepoRoot = path.resolve(configDir, "..");

const isProd = process.env.NODE_ENV === "production";
const requiredProdVars = ["NEXT_PUBLIC_API_URL", "BACKEND_ORIGIN"];
if (isProd) {
  const missing = requiredProdVars.filter((key) => !(process.env[key] || "").trim());
  if (missing.length) {
    throw new Error(
      `Missing required production environment variables: ${missing.join(", ")}. ` +
        "Set these before running `next build`.",
    );
  }
  const publicApi = process.env.NEXT_PUBLIC_API_URL?.trim() || "";
  if (!(publicApi.startsWith("https://") || publicApi.startsWith("/api-proxy"))) {
    throw new Error(
      "NEXT_PUBLIC_API_URL must be an HTTPS URL or `/api-proxy` in production.",
    );
  }
}

const backendOrigin = process.env.BACKEND_ORIGIN || "http://127.0.0.1:8000";
const isNetlify = process.env.NETLIFY === "true";
/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  outputFileTracingRoot: monorepoRoot,
  turbopack: {
    root: monorepoRoot,
  },
  async rewrites() {
    // Netlify uses the server route at /api-proxy; Next rewrites are for local development.
    if (isNetlify) return [];
    const origin = backendOrigin.replace(/\/+$/, "");
    return [
      {
        source: "/api-proxy/:path*",
        destination: `${origin}/api/:path*`,
      },
      {
        source: "/uploads/:path*",
        destination: `${origin}/uploads/:path*`,
      },
    ];
  },
};

export default nextConfig;
