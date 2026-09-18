import type { SagaEventRow, SagaExecution, SagaStepRow } from "../types/saga";

/**
 * Bitacora de auditoria construida con datos reales.
 *
 * En coreografia se muestran los eventos de dominio tal y como quedaron en el
 * event store; en orquestacion, las filas de la bitacora de pasos. En ningun
 * caso se inventan entradas ni marcas de tiempo.
 */

type EntryType = "info" | "success" | "error" | "compensation" | "muted";

interface AuditEntry {
  timestamp: string;
  event: string;
  detail: string;
  type: EntryType;
}

const EVENTOS_DE_EXITO = new Set([
  "BalanceDebited",
  "RiskApproved",
  "ClearingCompleted",
  "TransferCompleted",
]);

const EVENTOS_DE_ERROR = new Set(["RiskRejected", "TransferFailed"]);

function tipoDeEvento(eventType: string): EntryType {
  if (EVENTOS_DE_EXITO.has(eventType)) return "success";
  if (EVENTOS_DE_ERROR.has(eventType)) return "error";
  if (eventType.includes("Compensat")) return "compensation";
  return "info";
}

function detalleDeEvento(evento: SagaEventRow): string {
  const p = evento.payload ?? {};
  const cuenta = p.account_id as string | undefined;
  const importe = p.amount as number | undefined;
  const motivo = (p.error_code as string | undefined) ?? (p.reason as string | undefined);

  if (motivo) return `motivo: ${motivo}`;
  if (cuenta && importe != null) {
    return `${cuenta} por $${importe.toLocaleString("es-CO")} COP`;
  }
  const origen = p.source_account_id as string | undefined;
  const destino = p.destination_account_id as string | undefined;
  if (origen && destino) return `${origen} → ${destino}`;
  return "—";
}

function desdeEventos(eventos: SagaEventRow[]): AuditEntry[] {
  return eventos.map((evento) => ({
    timestamp: evento.occurred_at,
    event: evento.event_type,
    detail: detalleDeEvento(evento),
    type: tipoDeEvento(evento.event_type),
  }));
}

function desdePasos(pasos: SagaStepRow[]): AuditEntry[] {
  return pasos.map((paso) => {
    const esCompensacion = paso.kind === "COMPENSATION";
    let type: EntryType = "info";
    if (esCompensacion) type = paso.status === "COMPENSATED" ? "compensation" : "error";
    else if (paso.status === "EXECUTED") type = "success";
    else if (paso.status === "FAILED") type = "error";
    else if (paso.status === "SKIPPED") type = "muted";

    const partes = [paso.service, paso.status.toLowerCase()];
    if (paso.error_code) partes.push(paso.error_code);
    if (paso.duration_ms != null) partes.push(`${paso.duration_ms} ms`);

    return {
      timestamp: esCompensacion ? paso.updated_at : paso.created_at,
      event: paso.operation,
      detail: partes.join(" · "),
      type,
    };
  });
}

const DOT_COLORS: Record<EntryType, string> = {
  info: "bg-blue-500",
  success: "bg-emerald-500",
  error: "bg-red-500",
  compensation: "bg-purple-500",
  muted: "bg-gray-700",
};

const LINE_COLORS: Record<EntryType, string> = {
  info: "border-l-blue-500/20",
  success: "border-l-emerald-500/20",
  error: "border-l-red-500/20",
  compensation: "border-l-purple-500/20",
  muted: "border-l-white/5",
};

export default function AuditLog({ saga }: { saga: SagaExecution | null }) {
  if (!saga) return null;

  const usaEventos = saga.events.length > 0;
  const entries = usaEventos ? desdeEventos(saga.events) : desdePasos(saga.steps);

  return (
    <div className="glass rounded-2xl p-6">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-white">Bitacora de Auditoria</h2>
          <p className="text-xs text-gray-500">
            {usaEventos
              ? `${entries.length} eventos de dominio registrados`
              : `${entries.length} operaciones registradas`}
          </p>
        </div>
        <span className="flex-shrink-0 rounded-lg bg-white/[0.03] px-2.5 py-1 text-[10px] text-gray-500">
          {usaEventos ? "event store" : "saga.saga_steps"}
        </span>
      </div>

      {entries.length === 0 ? (
        <p className="text-xs text-gray-600">Todavia no hay registros para esta transferencia.</p>
      ) : (
        <div className="relative ml-2 max-h-80 overflow-y-auto">
          {entries.map((entry, i) => (
            <div key={i} className={`relative border-l-2 pb-4 pl-5 last:pb-0 ${LINE_COLORS[entry.type]}`}>
              <div
                className={`absolute -left-[5px] top-1 h-2 w-2 rounded-full ${DOT_COLORS[entry.type]} ring-2 ring-[#050a18]`}
              />
              <div className="flex flex-wrap items-baseline gap-2">
                <span className="text-xs font-medium text-gray-200">{entry.event}</span>
                <span className="text-[10px] tabular-nums text-gray-600">
                  {new Date(entry.timestamp).toLocaleTimeString("es-CO", { hour12: false })}
                </span>
              </div>
              <p className="mt-0.5 text-xs text-gray-500">{entry.detail}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
