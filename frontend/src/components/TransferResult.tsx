import type { TransferResponse } from "../types/transfer";
import StatusBadge from "./StatusBadge";

interface Props {
  transfer: TransferResponse;
  isPolling: boolean;
}

export default function TransferResult({ transfer, isPolling }: Props) {
  const formatDate = (iso: string) =>
    new Date(iso).toLocaleString("es-CO", { dateStyle: "short", timeStyle: "medium" });
  const formatAmount = (val: string) =>
    `$${parseInt(val).toLocaleString("es-CO")}`;

  return (
    <div className="glass rounded-2xl p-6">
      <div className="mb-5 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">Detalle</h2>
        <div className="flex items-center gap-2">
          {isPolling && (
            <span className="flex items-center gap-1.5 text-[10px] text-indigo-400">
              <span className="h-1 w-1 animate-pulse rounded-full bg-indigo-500" />
              Live
            </span>
          )}
          <StatusBadge status={transfer.status} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <Field label="Transfer ID" value={transfer.transfer_id.slice(0, 8) + "..."} mono />
        <Field label="Origen" value={transfer.source_account_id} />
        <Field label="Destino" value={transfer.destination_account_id} />
        <Field label="Monto" value={formatAmount(transfer.amount)} highlight />
        <Field label="Moneda" value={transfer.currency} />
        <Field label="Creado" value={formatDate(transfer.created_at)} />
        <Field label="Actualizado" value={formatDate(transfer.updated_at)} />
        <Field label="Idempotency Key" value={transfer.idempotency_key.slice(0, 8) + "..."} mono />
        {transfer.replayed && (
          <div className="col-span-2 sm:col-span-3">
            <div className="flex items-center gap-2 rounded-xl bg-emerald-500/5 px-3 py-2 text-xs text-emerald-400">
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              Idempotente — sin doble cobro
            </div>
          </div>
        )}
      </div>

      {(transfer.chaos.force_risk_failure || transfer.chaos.force_clearing_timeout) && (
        <div className="mt-4 flex flex-wrap gap-2">
          {transfer.chaos.force_risk_failure && (
            <span className="rounded-lg bg-red-500/5 px-2.5 py-1 text-[11px] font-medium text-red-400/80">
              Fallo riesgo forzado
            </span>
          )}
          {transfer.chaos.force_clearing_timeout && (
            <span className="rounded-lg bg-orange-500/5 px-2.5 py-1 text-[11px] font-medium text-orange-400/80">
              Timeout clearing forzado
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function Field({ label, value, mono, highlight }: {
  label: string; value: string; mono?: boolean; highlight?: boolean;
}) {
  return (
    <div>
      <div className="text-[10px] font-medium uppercase tracking-wider text-gray-500">{label}</div>
      <div className={`mt-0.5 text-sm ${mono ? "font-mono text-xs text-gray-400" : ""} ${highlight ? "font-semibold text-white" : "text-gray-300"}`}>
        {value}
      </div>
    </div>
  );
}
