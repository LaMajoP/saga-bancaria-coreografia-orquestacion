import type { SagaExecution } from "../types/saga";
import { MODE_LABELS } from "../types/saga";

/**
 * Trazabilidad por servicio, leida de saga.saga_steps.
 *
 * Las filas de compensacion se numeran por encima de las de accion, asi que
 * ordenarlas por 'sequence' deja a la vista que la reversa ocurrio en orden
 * inverso al flujo normal.
 */

const SVC_COLORS: Record<string, string> = {
  "account-service": "text-emerald-400/70 bg-emerald-500/8",
  "risk-service": "text-amber-400/70 bg-amber-500/8",
  "clearing-service": "text-orange-400/70 bg-orange-500/8",
  "api-gateway": "text-blue-400/70 bg-blue-500/8",
  saga: "text-purple-400/70 bg-purple-500/8",
};

const STATUS_COLORS: Record<string, string> = {
  EXECUTED: "text-emerald-500",
  FAILED: "text-red-500",
  COMPENSATED: "text-purple-500",
  COMPENSATION_FAILED: "text-red-500",
  SKIPPED: "text-gray-600",
};

const COMPENSATION_LABELS: Record<string, string> = {
  NOT_REQUIRED: "Sin compensaciones",
  COMPENSATING: "Compensando",
  COMPENSATED: "Compensada",
  COMPENSATION_FAILED: "Compensacion fallida",
};

export default function TracePanel({ saga }: { saga: SagaExecution | null }) {
  if (!saga) return null;

  const compensaciones = saga.steps.filter((s) => s.kind === "COMPENSATION");

  return (
    <div className="glass rounded-2xl p-6">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-white">Trazabilidad</h2>
          <p className="text-xs text-gray-500">
            {MODE_LABELS[saga.implementation]} · {COMPENSATION_LABELS[saga.compensation_status]}
          </p>
        </div>
        <span className="flex-shrink-0 rounded-lg bg-white/[0.03] px-2.5 py-1 font-mono text-[10px] text-gray-500">
          tid:{saga.transfer_id.slice(0, 8)}
        </span>
      </div>

      <div className="space-y-1">
        {saga.steps.map((fila) => (
          <div
            key={`${fila.step_name}-${fila.kind}`}
            className="flex flex-wrap items-center gap-2 rounded-lg bg-black/20 px-3 py-2 font-mono text-[11px]"
          >
            <span className="w-8 flex-shrink-0 tabular-nums text-gray-700">{fila.sequence}</span>
            <span className="w-4 flex-shrink-0 text-gray-600">
              {fila.kind === "COMPENSATION" ? "↩" : "→"}
            </span>
            <span
              className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                SVC_COLORS[fila.service] ?? "text-gray-400 bg-white/5"
              }`}
            >
              {fila.service.replace("-service", "")}
            </span>
            <span className="text-gray-400">{fila.operation}</span>
            <span className={`font-semibold ${STATUS_COLORS[fila.status] ?? "text-gray-400"}`}>
              {fila.status.toLowerCase()}
            </span>
            {fila.error_code && <span className="text-red-500/60">{fila.error_code}</span>}
            {fila.duration_ms != null && (
              <span className="ml-auto tabular-nums text-gray-700">{fila.duration_ms} ms</span>
            )}
          </div>
        ))}
      </div>

      {compensaciones.length > 0 && (
        <div className="mt-4 rounded-xl bg-purple-500/[0.04] px-4 py-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-purple-400/80">
            Orden de reversa
          </p>
          <p className="mt-1 font-mono text-xs text-gray-400">
            {compensaciones
              .sort((a, b) => a.sequence - b.sequence)
              .map((c) => c.step_name)
              .join(" → ")}
          </p>
          <p className="mt-1 text-[10px] text-gray-600">
            Inverso al flujo normal DEBIT → RISK → CLEARING → CREDIT
          </p>
        </div>
      )}
    </div>
  );
}
