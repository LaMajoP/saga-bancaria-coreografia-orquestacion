export type TransferStatus =
  | "RECIBIDA"
  | "EN_PROCESO"
  | "CONFIRMADA"
  | "RECHAZADA_FONDOS"
  | "RECHAZADA_RIESGO"
  | "RECHAZADA_RED"
  | "COMPENSANDO"
  | "COMPENSADA"
  | "FALLIDA";

export interface ChaosOptions {
  force_risk_failure: boolean;
  force_clearing_timeout: boolean;
}

export interface TransferRequest {
  source_account_id: string;
  destination_account_id: string;
  amount: string;
  currency: string;
  chaos: ChaosOptions;
}

export interface TransferResponse {
  transfer_id: string;
  idempotency_key: string;
  status: TransferStatus;
  source_account_id: string;
  destination_account_id: string;
  amount: string;
  currency: string;
  chaos: ChaosOptions;
  created_at: string;
  updated_at: string;
  replayed: boolean;
}

export interface ServiceHealth {
  service: string;
  status: "UP" | "DOWN";
  http_status?: number;
  detail?: string;
}

export interface DependenciesHealth {
  status: "UP" | "DEGRADED";
  services: ServiceHealth[];
}

export type SagaStep = "debit" | "risk" | "clearing" | "credit";

export type StepState = "pending" | "running" | "success" | "failed" | "compensating" | "compensated" | "skipped";

export interface SagaStepInfo {
  step: SagaStep;
  label: string;
  state: StepState;
  detail?: string;
  elapsedMs?: number;
  /** Datos tomados de la bitacora real del saga-service, no inferidos. */
  service?: string;
  operation?: string;
  attempt?: number;
  /** 1 = primera compensacion ejecutada. Evidencia el orden inverso. */
  compensationRank?: number;
}

export const STATUS_LABELS: Record<TransferStatus, string> = {
  RECIBIDA: "Recibida",
  EN_PROCESO: "En Proceso",
  CONFIRMADA: "Confirmada",
  RECHAZADA_FONDOS: "Rechazada (Fondos)",
  RECHAZADA_RIESGO: "Rechazada (Riesgo)",
  RECHAZADA_RED: "Rechazada (Red)",
  COMPENSANDO: "Compensando",
  COMPENSADA: "Compensada",
  FALLIDA: "Fallida",
};

/** Cuentas sembradas por la migracion. El saldo se consulta en vivo. */
export const DEMO_ACCOUNTS = [
  { id: "ACC-001", label: "ACC-001 — Cuenta Principal" },
  { id: "ACC-002", label: "ACC-002 — Cuenta Secundaria" },
  { id: "ACC-003", label: "ACC-003 — Cuenta Ahorro" },
];
