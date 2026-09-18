import { useEffect, useState } from "react";
import { listTransfers } from "../api/gateway";
import type { TransferResponse } from "../types/transfer";
import StatusBadge from "./StatusBadge";

export default function TransferHistory({ refreshTrigger }: { refreshTrigger: number }) {
  const [transfers, setTransfers] = useState<TransferResponse[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    listTransfers()
      .then((data) => { if (mounted) setTransfers(data.transfers.reverse()); })
      .catch(() => {})
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, [refreshTrigger]);

  return (
    <div className="glass rounded-2xl p-6">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">Historial</h2>
          <p className="text-xs text-gray-500">Transferencias registradas</p>
        </div>
        <span className="rounded-lg bg-white/[0.03] px-2.5 py-1 text-[11px] tabular-nums text-gray-500">
          {transfers.length} registros
        </span>
      </div>

      {loading && transfers.length === 0 ? (
        <div className="py-8 text-center text-sm text-gray-600">Cargando...</div>
      ) : transfers.length === 0 ? (
        <div className="py-8 text-center text-sm text-gray-600">Sin transferencias registradas</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="text-[10px] font-medium uppercase tracking-wider text-gray-500">
                <th className="pb-3 pr-3">ID</th>
                <th className="pb-3 pr-3">Origen</th>
                <th className="pb-3 pr-3">Destino</th>
                <th className="pb-3 pr-3 text-right">Monto</th>
                <th className="pb-3 pr-3">Estado</th>
                <th className="pb-3">Fecha</th>
              </tr>
            </thead>
            <tbody>
              {transfers.map((t) => (
                <tr key={t.transfer_id} className="border-t border-white/[0.03] transition-colors hover:bg-white/[0.02]">
                  <td className="py-3 pr-3 font-mono text-xs text-gray-500">{t.transfer_id.slice(0, 8)}</td>
                  <td className="py-3 pr-3 text-xs text-gray-400">{t.source_account_id}</td>
                  <td className="py-3 pr-3 text-xs text-gray-400">{t.destination_account_id}</td>
                  <td className="py-3 pr-3 text-right text-xs font-medium text-gray-300">
                    ${parseInt(t.amount).toLocaleString("es-CO")}
                  </td>
                  <td className="py-3 pr-3"><StatusBadge status={t.status} /></td>
                  <td className="py-3 text-[11px] tabular-nums text-gray-600">
                    {new Date(t.created_at).toLocaleString("es-CO", { dateStyle: "short", timeStyle: "short" })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
