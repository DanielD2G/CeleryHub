export async function apiGet<T>(url: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(url, { signal });
  if (!res.ok) {
    throw new Error(`GET ${url} failed: ${res.status} ${res.statusText}`);
  }
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
  if (!res.ok) {
    throw new Error(`POST ${url} failed: ${res.status} ${res.statusText}`);
  }
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
  if (!res.ok) {
    throw new Error(`PUT ${url} failed: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export async function apiDelete(url: string, signal?: AbortSignal): Promise<void> {
  const res = await fetch(url, { method: "DELETE", signal });
  if (!res.ok) {
    throw new Error(`DELETE ${url} failed: ${res.status} ${res.statusText}`);
  }
}
