import { createHmac, timingSafeEqual } from "node:crypto";

export const PORTFOLIO_COOKIE_NAME = "portfolio_session";
const SESSION_TTL_SECONDS = 60 * 60 * 24 * 7;

function sessionSecret() {
  const secret = process.env.PORTFOLIO_SESSION_SECRET;
  if (!secret) throw new Error("PORTFOLIO_SESSION_SECRET is not configured");
  return secret;
}

function signature(expiresAt: string) {
  return createHmac("sha256", sessionSecret()).update(`portfolio:${expiresAt}`).digest("hex");
}

export function createPortfolioSession() {
  const expiresAt = String(Date.now() + SESSION_TTL_SECONDS * 1000);
  return { token: `${expiresAt}.${signature(expiresAt)}`, maxAge: SESSION_TTL_SECONDS };
}

export function isValidPortfolioSession(token: string | undefined) {
  if (!token) return false;
  const [expiresAt, suppliedSignature, ...rest] = token.split(".");
  if (rest.length || !/^\d+$/.test(expiresAt || "") || !/^[a-f0-9]{64}$/i.test(suppliedSignature || "")) return false;
  if (Number(expiresAt) <= Date.now()) return false;

  try {
    const expected = Buffer.from(signature(expiresAt), "hex");
    const supplied = Buffer.from(suppliedSignature, "hex");
    return expected.length === supplied.length && timingSafeEqual(expected, supplied);
  } catch {
    return false;
  }
}

export function isValidPortfolioPassword(candidate: unknown) {
  const expectedValue = process.env.PORTFOLIO_ACCESS_PASSWORD;
  if (!expectedValue || typeof candidate !== "string") return false;
  const expected = Buffer.from(expectedValue, "utf8");
  const supplied = Buffer.from(candidate, "utf8");
  return expected.length === supplied.length && timingSafeEqual(expected, supplied);
}

export function portfolioAuthConfigured() {
  return Boolean(process.env.PORTFOLIO_ACCESS_PASSWORD && process.env.PORTFOLIO_SESSION_SECRET);
}
