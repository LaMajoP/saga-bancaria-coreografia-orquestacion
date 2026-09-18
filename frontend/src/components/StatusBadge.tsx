import type { TransferStatus } from "../types/transfer";
import { STATUS_LABELS } from "../types/transfer";

const STYLES: Record<TransferStatus, { bg: string; text: string; dot: string }> = {
  RECIBIDA: { bg: "bg-blue-500/10", text: "text-blue-400", dot: "bg-blue-400" },
  EN_PROCESO: { bg: "bg-indigo-500/10", text: "text-indigo-400", dot: "bg-indigo-400" },
  CONFIRMADA: { bg: "bg-emerald-500/10", text: "text-emerald-400", dot: "bg-emerald-400" },
  RECHAZADA_FONDOS: { bg: "bg-red-500/10", text: "text-red-400", dot: "bg-red-400" },
  RECHAZADA_RIESGO: { bg: "bg-red-500/10", text: "text-red-400", dot: "bg-red-400" },
  RECHAZADA_RED: { bg: "bg-orange-500/10", text: "text-orange-400", dot: "bg-orange-400" },
  COMPENSANDO: { bg: "bg-purple-500/10", text: "text-purple-400", dot: "bg-purple-400" },
  COMPENSADA: { bg: "bg-purple-500/10", text: "text-purple-400", dot: "bg-purple-400" },
  FALLIDA: { bg: "bg-red-500/10", text: "text-red-400", dot: "bg-red-400" },
};

export default function StatusBadge({ status }: { status: TransferStatus }) {
  const s = STYLES[status];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium ${s.bg} ${s.text}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} />
      {STATUS_LABELS[status]}
    </span>
  );
}
