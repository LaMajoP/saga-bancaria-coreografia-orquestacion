import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, createTransfer } from "./api/gateway";
import AuditLog from "./components/AuditLog";
import HealthIndicator from "./components/HealthIndicator";
import IdempotencyPanel from "./components/IdempotencyPanel";
import SagaTimeline from "./components/SagaTimeline";
import TracePanel from "./components/TracePanel";
import TransferForm from "./components/TransferForm";
import TransferHistory from "./components/TransferHistory";
import TransferResult from "./components/TransferResult";
import { useTransferPolling } from "./hooks/useTransferPolling";
import type { SagaMode } from "./types/saga";
import type { TransferRequest } from "./types/transfer";

export default function App() {
  const { transfer, saga, steps, isPolling, elapsedTotal, startPolling, reset } = useTransferPolling(1500);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const lastRequestRef = useRef<TransferRequest | null>(null);
  const lastKeyRef = useRef<string | null>(null);
  const lastModeRef = useRef<SagaMode>("ORCHESTRATION");
  const [idempotencyResult, setIdempotencyResult] = useState<{
    replayed: boolean; key: string; message: string;
  } | null>(null);

  const handleSubmit = useCallback(async (req: TransferRequest, mode: SagaMode) => {
    reset();
    setError(null);
    setIdempotencyResult(null);
    setSubmitting(true);
    try {
      const result = await createTransfer(req, undefined, mode);
      lastRequestRef.current = req;
      lastKeyRef.current = result.idempotency_key;
      lastModeRef.current = mode;
      startPolling(result.transfer_id);
      setRefreshTrigger((n) => n + 1);
    } catch (err) {
      if (err instanceof ApiError) setError(`Error ${err.status}: ${err.message}`);
      else setError("Error de conexion con el servidor");
    } finally {
      setSubmitting(false);
    }
  }, [reset, startPolling]);

  const handleIdempotencyRetry = useCallback(async () => {
    if (!lastRequestRef.current || !lastKeyRef.current) return;
    setSubmitting(true);
    setIdempotencyResult(null);
    try {
      const result = await createTransfer(lastRequestRef.current, lastKeyRef.current, lastModeRef.current);
      setIdempotencyResult({
        replayed: result.replayed,
        key: lastKeyRef.current,
        message: result.replayed
          ? "Idempotencia verificada: resultado original sin doble operacion."
          : "Se creo una nueva operacion (idempotencia no detectada).",
      });
      setRefreshTrigger((n) => n + 1);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setIdempotencyResult({
          replayed: false,
          key: lastKeyRef.current,
          message: "Conflicto 409: clave reutilizada con datos distintos.",
        });
      } else {
        setError("Error al reintentar");
      }
    } finally {
      setSubmitting(false);
    }
  }, []);

  // Al terminar una saga los saldos cambiaron (o volvieron a su sitio tras una
  // compensacion): conviene releerlos para que la evidencia sea la actual.
  useEffect(() => {
    if (!isPolling && transfer) setRefreshTrigger((n) => n + 1);
  }, [isPolling]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleNewTransfer = () => {
    reset();
    setError(null);
    setIdempotencyResult(null);
    lastRequestRef.current = null;
    lastKeyRef.current = null;
    setRefreshTrigger((n) => n + 1);
  };

  return (
    <div className="relative min-h-screen">
      <div className="mesh-bg" />

      {/* Header */}
      <header className="sticky top-0 z-50 border-b border-white/[0.04] bg-[#050a18]/80 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600">
              <svg className="h-4 w-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <div>
              <h1 className="text-sm font-bold text-white tracking-tight">NovaBank</h1>
              <p className="text-[10px] text-gray-500">Saga Bancaria</p>
            </div>
          </div>
          <HealthIndicator />
        </div>
      </header>

      {/* Main */}
      <main className="mx-auto max-w-7xl px-6 py-8">
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          {/* Left Column */}
          <div className="space-y-4 lg:col-span-4">
            <TransferForm
              onSubmit={handleSubmit}
              disabled={submitting || isPolling}
              refreshBalances={refreshTrigger}
            />

            {error && (
              <div className="rounded-xl bg-red-500/5 px-4 py-3 text-xs text-red-400">
                {error}
              </div>
            )}

            {transfer && !isPolling && (
              <div className="space-y-3">
                <IdempotencyPanel
                  idempotencyKey={lastKeyRef.current}
                  onRetry={handleIdempotencyRetry}
                  result={idempotencyResult}
                  disabled={submitting}
                />
                <button onClick={handleNewTransfer} className="btn-ghost w-full text-sm">
                  Nueva Transferencia
                </button>
              </div>
            )}
          </div>

          {/* Right Column */}
          <div className="space-y-4 lg:col-span-8">
            {steps.length > 0 && (
              <SagaTimeline steps={steps} elapsedTotal={elapsedTotal} isPolling={isPolling} />
            )}

            {transfer && (
              <>
                <TransferResult transfer={transfer} isPolling={isPolling} />
                <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                  <AuditLog saga={saga} />
                  <TracePanel saga={saga} />
                </div>
              </>
            )}

            {!transfer && (
              <div className="glass flex flex-col items-center justify-center rounded-2xl py-20 text-center">
                <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-white/[0.03]">
                  <svg className="h-8 w-8 text-gray-700" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
                  </svg>
                </div>
                <h3 className="text-sm font-medium text-gray-400">Sin transferencia activa</h3>
                <p className="mt-1 max-w-xs text-xs text-gray-600">
                  Completa el formulario para iniciar una transferencia y visualizar la Saga en tiempo real.
                </p>
              </div>
            )}
          </div>
        </div>

        {/* History */}
        <div className="mt-8">
          <TransferHistory refreshTrigger={refreshTrigger} />
        </div>
      </main>

      <footer className="border-t border-white/[0.03] py-6 text-center text-[11px] text-gray-700">
        NovaBank International — Patron Saga Bancario
      </footer>
    </div>
  );
}
