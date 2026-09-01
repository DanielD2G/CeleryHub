async function _errorFrom(res: Response, method: string, url: string): Promise<Error> {
  // Prefer the server's own message ({"detail": ...} from FastAPI) over a
  // generic "422 Unprocessable Entity".
  const body = await res.json().catch(() => null);
  const detail =
    body && typeof body === "object" && "detail" in body
      ? typeof body.detail === "string"
        ? body.detail
        : JSON.stringify(body.detail)
      : null;
  return new Error(detail ?? `${method} ${url} failed: ${res.status} ${res.statusText}`);
}

export async function apiGet<T>(url: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(url, { signal });
  if (!res.ok) throw await _errorFrom(res, "GET", url);
  return res.json();
}

export async function apiPost<T>(
  url: string,
  body?: unknown,
  signal?: AbortSignal
): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: body != null ? { "Content-Type": "application/json" } : undefined,
    body: body != null ? JSON.stringify(body) : undefined,
    signal,
  });
  if (!res.ok) throw await _errorFrom(res, "POST", url);
  return res.json();
}

export async function apiPut<T>(
  url: string,
  body?: unknown,
  signal?: AbortSignal
): Promise<T> {
  const res = await fetch(url, {
    method: "PUT",
    headers: body != null ? { "Content-Type": "application/json" } : undefined,
    body: body != null ? JSON.stringify(body) : undefined,
    signal,
  });
  if (!res.ok) throw await _errorFrom(res, "PUT", url);
  return res.json();
}

export async function apiDelete(url: string, signal?: AbortSignal): Promise<void> {
  const res = await fetch(url, { method: "DELETE", signal });
  if (!res.ok) throw await _errorFrom(res, "DELETE", url);
}
