interface Props {
  idempotencyKey: string | null;
  onRetry: () => void;
  result: { replayed: boolean; key: string; message: string } | null;
  disabled: boolean;
}

export default function IdempotencyPanel({ idempotencyKey, onRetry, result, disabled }: Props) {
  if (!idempotencyKey) return null;

  return (
    <div className="glass rounded-2xl border-cyan-500/10 p-4">
      <div className="mb-3 flex items-center gap-2">
        <div className="flex h-5 w-5 items-center justify-center rounded-md bg-cyan-500/10">
          <svg className="h-3 w-3 text-cyan-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
        </div>
        <span className="text-xs font-semibold text-cyan-400/80">Test Idempotencia (CP-05)</span>
      </div>

      <div className="mb-3 overflow-hidden rounded-lg bg-black/20 px-3 py-2">
        <span className="text-[10px] text-gray-500">Key: </span>
        <code className="font-mono text-[11px] text-cyan-400/70">{idempotencyKey}</code>
      </div>

      <button
        onClick={onRetry}
        disabled={disabled}
        className="w-full rounded-xl bg-cyan-500/10 px-4 py-2.5 text-xs font-medium text-cyan-400 transition-all hover:bg-cyan-500/15 disabled:opacity-40"
      >
        {disabled ? "Reintentando..." : "Reintentar con misma clave"}
      </button>

      {result && (
        <div className={`mt-3 rounded-xl px-3 py-2.5 text-xs ${
          result.replayed
            ? "bg-emerald-500/5 text-emerald-400"
            : "bg-amber-500/5 text-amber-400"
        }`}>
          <div className="flex items-start gap-2">
            <svg className="mt-0.5 h-3 w-3 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d={
                result.replayed
                  ? "M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                  : "M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"
              } />
            </svg>
            <span>{result.message}</span>
          </div>
        </div>
      )}
    </div>
  );
}
