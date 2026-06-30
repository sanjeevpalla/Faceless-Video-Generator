/**
 * Long-running POST helper that uses Tauri's native HTTP client (Rust/reqwest)
 * when running inside Tauri, falling back to fetch in browser dev mode.
 *
 * Why: Windows WebView2 imposes its own HTTP timeout (~60s) on XHR/fetch made
 * from the renderer. Tauri's @tauri-apps/api/http bypasses WebView2 entirely
 * and has no timeout unless you set one explicitly.
 */

const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

export async function tauriPost<T>(path: string, body?: unknown): Promise<T> {
  const url = `${BASE}/api/v1${path}`;
  const headers = { "Content-Type": "application/json" };

  // Tauri context: use native Rust HTTP (no WebView timeout)
  if (typeof window !== "undefined" && (window as any).__TAURI__) {
    const { fetch: tFetch, Body, ResponseType } = await import("@tauri-apps/api/http");
    const response = await tFetch<T>(url, {
      method: "POST",
      headers,
      body: body !== undefined ? Body.json(body) : undefined,
      responseType: ResponseType.JSON,
      timeout: { secs: 1800, nanos: 0 }, // 30-minute ceiling
    });
    if (!response.ok) {
      const detail = (response.data as any)?.detail || (response.data as any)?.error || "Server error";
      throw new Error(detail);
    }
    return response.data;
  }

  // Browser dev mode: plain fetch (no timeout limit in Node/browser)
  const res = await fetch(url, {
    method: "POST",
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data?.detail || data?.error || `HTTP ${res.status}`);
  }
  return res.json();
}
