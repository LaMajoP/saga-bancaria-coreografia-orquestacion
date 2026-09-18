import type { DependenciesHealth, TransferRequest, TransferResponse } from "../types/transfer";
import type { SagaMode } from "../types/saga";

const BASE = "/api/v1";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.detail ?? res.statusText, body);
  }
  return res.json();
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public body?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function createTransfer(
  payload: TransferRequest,
  idempotencyKey?: string,
  mode?: SagaMode,
): Promise<TransferResponse> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (idempotencyKey) {
    headers["Idempotency-Key"] = idempotencyKey;
  }
  // La modalidad viaja como cabecera para no alterar el contrato JSON acordado.
  if (mode) {
    headers["X-Saga-Mode"] = mode;
  }
  return request<TransferResponse>(`${BASE}/transfers`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
}

export async function getTransfer(transferId: string): Promise<TransferResponse> {
  return request<TransferResponse>(`${BASE}/transfers/${transferId}`);
}

export async function listTransfers(): Promise<{ transfers: TransferResponse[] }> {
  return request<{ transfers: TransferResponse[] }>(`${BASE}/transfers`);
}

export async function getDependenciesHealth(): Promise<DependenciesHealth> {
  return request<DependenciesHealth>(`${BASE}/dependencies/health`);
}

export async function getGatewayHealth(): Promise<{ status: string }> {
  return request<{ status: string }>("/health");
}
