import { jwtDecode } from "jwt-decode";

export const API = "http://localhost:8000";

export interface TokenPayload {
  sub: string; // username
  role: string; // admin | can_bo | lanh_dao | nguoi_dung
  exp: number;
}

// Detect if we are running in the browser (client side)
const isBrowser = typeof window !== "undefined";

// Store token in a cookie (client‑only) using a tiny helper.
// We avoid a heavy dependency; simple document.cookie manipulation works.
export const setToken = (token: string) => {
  if (!isBrowser) return;
  document.cookie = `token=${encodeURIComponent(token)}; path=/; SameSite=Lax`;
};

export const getToken = (): string | null => {
  if (!isBrowser) return null;
  const match = document.cookie.match(/(?:^|; )token=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : null;
};

export const clearToken = () => {
  if (!isBrowser) return;
  // Delete cookie by setting expiration in the past
  document.cookie = `token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT`;
};

export const getPayload = (): TokenPayload | null => {
  const token = getToken();
  if (!token) return null;
  try {
    return jwtDecode<TokenPayload>(token);
  } catch {
    return null;
  }
};

export const isAuthenticated = () => !!getPayload();
export const hasRole = (role: string) => getPayload()?.role === role;
