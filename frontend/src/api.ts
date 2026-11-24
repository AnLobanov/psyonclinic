import type { Report } from "./types";

export async function fetchReport(refresh: boolean, signal: AbortSignal): Promise<Report> {
  let response: Response;
  try {
    response = await fetch(refresh ? "/api/comparison/refresh" : "/api/comparison", {
      method: refresh ? "POST" : "GET",
      headers: { Accept: "application/json" },
      signal,
    });
  } catch {
    throw new Error("Не удалось подключиться к серверу приложения.");
  }
  if (!response.ok) {
    const error: { detail?: unknown } | null = await response.json().catch(() => null);
    throw new Error(
      typeof error?.detail === "string" ? error.detail : `Сервер вернул HTTP ${response.status}.`,
    );
  }
  return response.json() as Promise<Report>;
}
