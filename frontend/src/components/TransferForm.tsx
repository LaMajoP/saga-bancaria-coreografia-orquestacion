import { useEffect, useState } from "react";
import { getAccountBalance } from "../api/saga";
import type { SagaMode } from "../types/saga";
import { MODE_LABELS } from "../types/saga";
import type { TransferRequest } from "../types/transfer";
import { DEMO_ACCOUNTS } from "../types/transfer";

interface Props {
  onSubmit: (req: TransferRequest, mode: SagaMode) => void;
  disabled: boolean;
  /** Cambia cuando termina una transferencia, para releer los saldos. */
  refreshBalances: number;
}

function Toggle({ checked, onChange, label, description, color }: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  description: string;
  color: "red" | "orange";
}) {
  return (
    <label className="flex cursor-pointer items-center justify-between gap-4 rounded-xl px-4 py-3 transition-colors hover:bg-white/[0.02]">
      <div className="min-w-0">
        <div className="text-sm font-medium text-gray-200">{label}</div>
        <div className="text-xs text-gray-500">{description}</div>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`toggle-track flex-shrink-0 ${checked ? "active" : ""}`}
        style={checked ? { background: color === "red" ? "linear-gradient(135deg, #ef4444, #dc2626)" : "linear-gradient(135deg, #f97316, #ea580c)" } : {}}
      >
        <div className="toggle-thumb" />
      </button>
    </label>
  );
}

export default function TransferForm({ onSubmit, disabled, refreshBalances }: Props) {
  const [source, setSource] = useState("ACC-001");
  const [destination, setDestination] = useState("ACC-002");
  const [amount, setAmount] = useState("50000");
  const [forceRisk, setForceRisk] = useState(false);
  const [forceClearing, setForceClearing] = useState(false);
  const [mode, setMode] = useState<SagaMode>("ORCHESTRATION");
  const [balances, setBalances] = useState<Record<string, number>>({});

  // Los saldos se leen del Account Service: son la evidencia de que una
  // transferencia compensada no mueve un solo peso.
  useEffect(() => {
    let vigente = true;
    Promise.all(DEMO_ACCOUNTS.map((a) => getAccountBalance(a.id))).then((resultados) => {
      if (!vigente) return;
      const mapa: Record<string, number> = {};
      for (const r of resultados) {
        if (r) mapa[r.account_id] = r.balance;
      }
      setBalances(mapa);
    });
    return () => {
      vigente = false;
    };
  }, [refreshBalances]);

  const etiqueta = (id: string) =>
    balances[id] != null ? `${id} — $${balances[id].toLocaleString("es-CO")} COP` : id;

  const destinationOptions = DEMO_ACCOUNTS.filter((a) => a.id !== source);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit(
      {
        source_account_id: source,
        destination_account_id: destination,
        amount: `${parseInt(amount)}.00`,
        currency: "COP",
        chaos: {
          force_risk_failure: forceRisk,
          force_clearing_timeout: forceClearing,
        },
      },
      mode,
    );
  };

  const formatCOP = (val: string) => {
    const num = parseInt(val.replace(/\D/g, "") || "0");
    return num.toLocaleString("es-CO");
  };

  return (
    <form onSubmit={handleSubmit} className="glass-strong glow-border rounded-2xl p-6">
      <div className="mb-6">
        <h2 className="text-xl font-bold text-white">Nueva Transferencia</h2>
        <p className="mt-1 text-sm text-gray-500">Ingresa los datos de la operacion bancaria</p>
      </div>

      <div className="space-y-4">
        <div>
          <label className="mb-2 block text-xs font-medium uppercase tracking-wider text-gray-400">
            Cuenta Origen
          </label>
          <select
            className="select-modern"
            value={source}
            onChange={(e) => {
              setSource(e.target.value);
              if (e.target.value === destination) {
                const other = DEMO_ACCOUNTS.find((a) => a.id !== e.target.value);
                if (other) setDestination(other.id);
              }
            }}
          >
            {DEMO_ACCOUNTS.map((a) => (
              <option key={a.id} value={a.id}>
                {etiqueta(a.id)}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="mb-2 block text-xs font-medium uppercase tracking-wider text-gray-400">
            Cuenta Destino
          </label>
          <select
            className="select-modern"
            value={destination}
            onChange={(e) => setDestination(e.target.value)}
          >
            {destinationOptions.map((a) => (
              <option key={a.id} value={a.id}>
                {etiqueta(a.id)}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="mb-2 block text-xs font-medium uppercase tracking-wider text-gray-400">
            Importe
          </label>
          <div className="relative">
            <span className="absolute left-4 top-1/2 -translate-y-1/2 text-sm font-medium text-gray-500">COP</span>
            <input
              type="text"
              className="input-modern pl-14 text-lg font-semibold"
              value={formatCOP(amount)}
              onChange={(e) => {
                const raw = e.target.value.replace(/\D/g, "");
                setAmount(raw || "0");
              }}
              placeholder="500,000"
            />
          </div>
        </div>
      </div>

      {/* Modalidad de la Saga */}
      <div className="mt-6">
        <label className="mb-2 block text-xs font-medium uppercase tracking-wider text-gray-400">
          Modalidad de la Saga
        </label>
        <div className="grid grid-cols-2 gap-2">
          {(["ORCHESTRATION", "CHOREOGRAPHY"] as SagaMode[]).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMode(m)}
              className={`rounded-xl px-3 py-2.5 text-xs font-medium transition-all ${
                mode === m
                  ? "bg-indigo-500/15 text-indigo-300 ring-1 ring-indigo-500/40"
                  : "bg-white/[0.03] text-gray-500 hover:bg-white/[0.05]"
              }`}
            >
              {MODE_LABELS[m]}
              <span className="mt-0.5 block text-[10px] font-normal text-gray-600">
                {m === "ORCHESTRATION" ? "Coordinador central" : "Eventos autonomos"}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Chaos Section */}
      <div className="mt-6 rounded-xl border border-amber-500/10 bg-amber-500/[0.03] p-1">
        <div className="mb-1 flex items-center gap-2 px-4 pt-3">
          <div className="flex h-6 w-6 items-center justify-center rounded-md bg-amber-500/10">
            <svg className="h-3.5 w-3.5 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <span className="text-xs font-semibold uppercase tracking-wider text-amber-500/80">Chaos Engineering</span>
        </div>

        <Toggle
          checked={forceRisk}
          onChange={setForceRisk}
          label="Forzar fallo de riesgo"
          description="Rechaza en validacion antifraude (CP-03)"
          color="red"
        />
        <Toggle
          checked={forceClearing}
          onChange={setForceClearing}
          label="Forzar timeout de clearing"
          description="Timeout en red interbancaria (CP-04)"
          color="orange"
        />
      </div>

      <button type="submit" className="btn-primary mt-6 w-full" disabled={disabled || parseInt(amount) <= 0}>
        {disabled ? (
          <span className="flex items-center justify-center gap-2">
            <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" className="opacity-20" />
              <path d="M12 2a10 10 0 019.95 9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
            </svg>
            Procesando
          </span>
        ) : (
          "Iniciar Transferencia"
        )}
      </button>
    </form>
  );
}
