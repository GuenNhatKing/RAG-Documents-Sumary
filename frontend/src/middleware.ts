import { NextRequest, NextResponse } from "next/server";

/**
 * Next.js Middleware — Auth & role-based routing at the proxy level.
 * Runs BEFORE page renders. Redirects unauthenticated users to /login
 * and blocks unauthorized roles from protected routes.
 */

// ============================================================
// JWT helpers (Edge-safe, no external libs)
// ============================================================
function getTokenFromCookies(request: NextRequest): string | null {
  return request.cookies.get("token")?.value ?? null;
}

function decodePayload(token: string): { sub: string; role: string; exp: number } | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const payload = JSON.parse(atob(parts[1]));
    return payload;
  } catch {
    return null;
  }
}

// ============================================================
// Route config
// ============================================================

// Routes that require authentication
const PROTECTED_PREFIXES = ["/chat", "/upload", "/files", "/stats", "/documents"];

// Routes that require specific roles (prefix → allowed roles)
const ROLE_ROUTES: Record<string, string[]> = {
  "/upload": ["admin", "can_bo"],
  "/files": ["admin", "can_bo"],
  "/stats": ["admin", "quan_ly"],
};

// Routes accessible only by guests (redirect to / if already logged in)
const GUEST_ONLY = ["/login", "/register"];

// ============================================================
// Middleware
// ============================================================
export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const token = getTokenFromCookies(request);
  const payload = token ? decodePayload(token) : null;

  // Check token expiry
  const isExpired = payload ? Date.now() / 1000 > payload.exp : true;
  const isAuthenticated = !!payload && !isExpired;
  const role = payload?.role ?? "";

  // Guest-only pages: redirect to / if already logged in
  if (GUEST_ONLY.some((p) => pathname.startsWith(p))) {
    if (isAuthenticated) {
      return NextResponse.redirect(new URL("/", request.url));
    }
    return NextResponse.next();
  }

  // Protected routes: require authentication
  const isProtected = PROTECTED_PREFIXES.some((p) => pathname.startsWith(p));
  if (isProtected && !isAuthenticated) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("redirect", pathname);
    return NextResponse.redirect(loginUrl);
  }

  // Role-based access
  for (const [prefix, allowedRoles] of Object.entries(ROLE_ROUTES)) {
    if (pathname.startsWith(prefix) && !allowedRoles.includes(role)) {
      return NextResponse.redirect(new URL("/403", request.url));
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/",
    "/chat/:path*",
    "/upload/:path*",
    "/files/:path*",
    "/stats/:path*",
    "/documents/:path*",
    "/login",
    "/register",
  ],
};
