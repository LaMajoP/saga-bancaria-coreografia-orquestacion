/**
 * Contratos de la capa de Saga (saga-service :8004).
 *
 * A diferencia del estado publico del Gateway, que solo dice en que punto esta
 * la transferencia, estos datos son la bitacora real: que paso se ejecuto, cual
 * fallo, cuales se compensaron y en que orden. Es lo que permite que la interfaz
 * muestre evidencia en lugar de una reconstruccion aproximada.
 */

export type SagaMode = "ORCHESTRATION" | "CHOREOGRAPHY";

export type SagaStepName = "DEBIT" | "RISK" | "CLEARING" | "CREDIT";

export type SagaStepKind = "ACTION" | "COMPENSATION";

export type SagaStepStatus =
  | "EXECUTED"
  | "FAILED"
  | "SKIPPED"
  | "COMPENSATED"
  | "COMPENSATION_FAILED";

export type CompensationStatus =
  | "NOT_REQUIRED"
  | "COMPENSATING"
  | "COMPENSATED"
  | "COMPENSATION_FAILED";

export interface SagaStepRow {
  sequence: number;
  step_name: SagaStepName;
  kind: SagaStepKind;
  service: string;
  operation: string;
  status: SagaStepStatus;
  attempt: number;
  error_code: string | null;
  message: string | null;
  duration_ms: number | null;
  created_at: string;
  updated_at: string;
}

export interface SagaEventRow {
  event_id: string;
  event_type: string;
  transfer_id: string;
  payload: Record<string, unknown>;
  occurred_at: string;
}

export interface SagaExecution {
  transfer_id: string;
  implementation: SagaMode;
  status: string;
  compensation_status: CompensationStatus;
  gateway_status: string;
  current_step: SagaStepName | null;
  source_account_id: string;
  destination_account_id: string;
  amount: number;
  currency: string;
  chaos: { force_risk_failure: boolean; force_clearing_timeout: boolean };
  error_code: string | null;
  message: string | null;
  started_at: string;
  finished_at: string | null;
  steps: SagaStepRow[];
  events: SagaEventRow[];
}

export const MODE_LABELS: Record<SagaMode, string> = {
  ORCHESTRATION: "Orquestacion",
  CHOREOGRAPHY: "Coreografia",
};

export const STEP_LABELS: Record<SagaStepName, string> = {
  DEBIT: "Debitar Cuenta",
  RISK: "Validar Riesgo",
  CLEARING: "Clearing Interbancario",
  CREDIT: "Acreditar Destino",
};
