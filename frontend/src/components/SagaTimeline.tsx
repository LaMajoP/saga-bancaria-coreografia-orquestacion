import type { SagaStepInfo, StepState } from "../types/transfer";

const STEP_CONFIG: Record<string, { icon: string; gradient: string }> = {
  debit: {
    icon: "M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z",
    gradient: "from-blue-500 to-cyan-500",
  },
  risk: {
    icon: "M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z",
    gradient: "from-amber-500 to-orange-500",
  },
  clearing: {
    icon: "M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4",
    gradient: "from-purple-500 to-pink-500",
  },
  credit: {
    icon: "M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z",
    gradient: "from-emerald-500 to-teal-500",
  },
};

const STATE_CONFIG: Record<StepState, {
  ringClass: string;
  bgClass: string;
  labelColor: string;
  label: string;
  badgeIcon?: string;
  badgeBg?: string;
}> = {
  pending: {
    ringClass: "ring-1 ring-white/10",
    bgClass: "bg-white/[0.03]",
    labelColor: "text-gray-500",
    label: "Pendiente",
  },
  running: {
    ringClass: "ring-2 ring-indigo-500/50",
    bgClass: "bg-indigo-500/10",
    labelColor: "text-indigo-400",
    label: "Ejecutando...",
  },
  success: {
    ringClass: "ring-1 ring-emerald-500/40",
    bgClass: "bg-emerald-500/10",
    labelColor: "text-emerald-400",
    label: "Exitoso",
    badgeIcon: "M5 13l4 4L19 7",
    badgeBg: "bg-emerald-500",
  },
  failed: {
    ringClass: "ring-1 ring-red-500/40",
    bgClass: "bg-red-500/10",
    labelColor: "text-red-400",
    label: "Fallido",
    badgeIcon: "M6 18L18 6M6 6l12 12",
    badgeBg: "bg-red-500",
  },
  compensating: {
    ringClass: "ring-2 ring-purple-500/50",
    bgClass: "bg-purple-500/10",
    labelColor: "text-purple-400",
    label: "Compensando...",
  },
  compensated: {
    ringClass: "ring-1 ring-purple-500/40",
    bgClass: "bg-purple-500/10",
    labelColor: "text-purple-400",
    label: "Compensado",
    badgeIcon: "M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6",
    badgeBg: "bg-purple-500",
  },
  skipped: {
    ringClass: "ring-1 ring-white/5",
    bgClass: "bg-white/[0.01]",
    labelColor: "text-gray-600",
    label: "Omitido",
  },
};

function formatElapsed(ms: number): string {
  return `${(ms / 1000).toFixed(1)}s`;
}

function StepNode({ info }: { info: SagaStepInfo }) {
  const stepCfg = STEP_CONFIG[info.step];
  const stateCfg = STATE_CONFIG[info.state];
  const isActive = info.state === "running" || info.state === "compensating";

  return (
    <div className="flex flex-col items-center gap-3">
      {/* Node */}
      <div className="relative">
        {/* Pulse ring for active */}
        {isActive && (
          <div className="absolute inset-0 rounded-2xl bg-indigo-500/20 step-active" />
        )}

        <div className={`relative flex h-14 w-14 items-center justify-center rounded-2xl transition-all duration-700 ${stateCfg.ringClass} ${stateCfg.bgClass}`}>
          <svg
            className={`h-6 w-6 transition-colors duration-500 ${
              info.state === "pending" || info.state === "skipped" ? "text-gray-600" : stateCfg.labelColor
            }`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={1.5}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d={stepCfg.icon} />
          </svg>
        </div>

        {/* Status badge */}
        {stateCfg.badgeIcon && (
          <div className={`absolute -bottom-1 -right-1 flex h-5 w-5 items-center justify-center rounded-full ${stateCfg.badgeBg} ring-2 ring-[#050a18]`}>
            <svg className="h-2.5 w-2.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
              <path strokeLinecap="round" strokeLinejoin="round" d={stateCfg.badgeIcon} />
            </svg>
          </div>
        )}
      </div>

      {/* Label */}
      <div className="text-center">
        <div className="text-xs font-medium text-gray-300">{info.label}</div>
        <div className={`text-[10px] font-medium ${stateCfg.labelColor}`}>
          {stateCfg.label}
        </div>
        {isActive && info.elapsedMs != null && (
          <div className="mt-0.5 font-mono text-[10px] tabular-nums text-indigo-400/80">
            {formatElapsed(info.elapsedMs)}
          </div>
        )}
        {info.detail && (
          <div className="mt-0.5 max-w-[80px] text-[10px] text-gray-500">{info.detail}</div>
        )}
      </div>
    </div>
  );
}

function Connector({ fromState }: { fromState: StepState }) {
  const done = fromState === "success" || fromState === "compensated";
  const fail = fromState === "failed";
  const comp = fromState === "compensated" || fromState === "compensating";

  let bgColor = "bg-white/[0.06]";
  if (done && !comp) bgColor = "bg-emerald-500/30";
  if (comp) bgColor = "bg-purple-500/30";
  if (fail) bgColor = "bg-red-500/30";

  return (
    <div className="flex items-center px-1">
      <div className={`h-px w-6 transition-colors duration-700 sm:w-10 ${bgColor}`} />
    </div>
  );
}

interface Props {
  steps: SagaStepInfo[];
  elapsedTotal?: number;
  isPolling?: boolean;
}

export default function SagaTimeline({ steps, elapsedTotal, isPolling }: Props) {
  if (steps.length === 0) return null;

  return (
    <div className="glass rounded-2xl p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">Progreso de la Saga</h2>
          <p className="text-xs text-gray-500">Flujo de transaccion distribuida</p>
        </div>
        {elapsedTotal != null && elapsedTotal > 0 && (
          <div className="flex items-center gap-2 rounded-lg bg-white/[0.04] px-3 py-1.5">
            {isPolling && (
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-indigo-500" />
            )}
            <span className="font-mono text-xs tabular-nums text-gray-400">
              {formatElapsed(elapsedTotal)}
            </span>
          </div>
        )}
      </div>

      <div className="flex items-start justify-center overflow-x-auto pb-2">
        {steps.map((s, i) => (
          <div key={s.step} className="flex items-center">
            <StepNode info={s} />
            {i < steps.length - 1 && <Connector fromState={s.state} />}
          </div>
        ))}
      </div>
    </div>
  );
}
