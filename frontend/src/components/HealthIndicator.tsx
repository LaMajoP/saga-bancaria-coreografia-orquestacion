import { useEffect, useState } from "react";
import { getDependenciesHealth } from "../api/gateway";
import type { DependenciesHealth } from "../types/transfer";

export default function HealthIndicator() {
  const [health, setHealth] = useState<DependenciesHealth | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let mounted = true;
    const check = async () => {
      try {
        const data = await getDependenciesHealth();
        if (mounted) { setHealth(data); setError(false); }
      } catch {
        if (mounted) setError(true);
      }
    };
    check();
    const interval = setInterval(check, 15_000);
    return () => { mounted = false; clearInterval(interval); };
  }, []);

  if (error) {
    return (
      <div className="flex items-center gap-2 rounded-lg bg-red-500/5 px-3 py-1.5 text-xs text-red-400/80">
        <span className="h-1.5 w-1.5 rounded-full bg-red-500" />
        Desconectado
      </div>
    );
  }

  if (!health) {
    return (
      <div className="flex items-center gap-2 rounded-lg bg-white/[0.03] px-3 py-1.5 text-xs text-gray-500">
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-gray-500" />
        Verificando
      </div>
    );
  }

  const allUp = health.status === "UP";
  return (
    <div className="flex items-center gap-2">
      {health.services.map((s) => (
        <div
          key={s.service}
          className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] font-medium ${
            s.status === "UP" ? "bg-emerald-500/5 text-emerald-400/70" : "bg-red-500/5 text-red-400/70"
          }`}
        >
          <span className={`h-1 w-1 rounded-full ${s.status === "UP" ? "bg-emerald-500" : "bg-red-500"}`} />
          {s.service.replace("-service", "")}
        </div>
      ))}
      <div className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] font-medium ${
        allUp ? "bg-emerald-500/5 text-emerald-400/70" : "bg-yellow-500/5 text-yellow-400/70"
      }`}>
        <span className={`h-1 w-1 rounded-full ${allUp ? "bg-emerald-500" : "bg-yellow-500"}`} />
        {allUp ? "Online" : "Degraded"}
      </div>
    </div>
  );
}
