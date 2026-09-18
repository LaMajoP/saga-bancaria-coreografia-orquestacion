import { useCallback, useEffect, useRef, useState } from "react";
import { getTransfer } from "../api/gateway";
import { getSagaTrace } from "../api/saga";
import type { SagaExecution, SagaStepName, SagaStepRow } from "../types/saga";
import { STEP_LABELS } from "../types/saga";
import type { SagaStep, SagaStepInfo, StepState, TransferResponse, TransferStatus } from "../types/transfer";

const TERMINAL_STATUSES: TransferStatus[] = [
  "CONFIRMADA",
  "RECHAZADA_FONDOS",
  "RECHAZADA_RIESGO",
  "RECHAZADA_RED",
  "COMPENSADA",
  "FALLIDA",
];

const ORDEN: SagaStepName[] = ["DEBIT", "RISK", "CLEARING", "CREDIT"];

const UI_STEP: Record<SagaStepName, SagaStep> = {
  DEBIT: "debit",
  RISK: "risk",
  CLEARING: "clearing",
  CREDIT: "credit",
};

function pasosVacios(): SagaStepInfo[] {
  return ORDEN.map((nombre) => ({
    step: UI_STEP[nombre],
    label: STEP_LABELS[nombre],
    state: "pending" as StepState,
  }));
}

/**
 * Traduce la bitacora real del saga-service al modelo que pinta la interfaz.
 *
 * Nada se infiere del estado publico: cada estado que se muestra viene de una
 * fila realmente escrita por la Saga, con su servicio, su operacion, su codigo
 * de error y su duracion. Esa es la diferencia entre una bitacora de auditoria
 * y una reconstruccion verosimil.
 */
export function derivarPasos(saga: SagaExecution | null): SagaStepInfo[] {
  if (!saga) return pasosVacios();

  const acciones = new Map<SagaStepName, SagaStepRow>();
  const compensaciones = new Map<SagaStepName, SagaStepRow>();
  const ordenDeReversa = saga.steps
    .filter((s) => s.kind === "COMPENSATION")
    .sort((a, b) => a.sequence - b.sequence);

  for (const fila of saga.steps) {
    if (fila.kind === "ACTION") acciones.set(fila.step_name, fila);
    else compensaciones.set(fila.step_name, fila);
  }
  const rango = new Map(ordenDeReversa.map((s, i) => [s.step_name, i + 1]));

  const terminada = saga.finished_at !== null;
  const revirtiendo = saga.compensation_status === "COMPENSATING";

  return ORDEN.map((nombre) => {
    const accion = acciones.get(nombre);
    const compensacion = compensaciones.get(nombre);

    let state: StepState = "pending";
    let detail: string | undefined;
    let elapsedMs: number | undefined = accion?.duration_ms ?? undefined;

    if (compensacion) {
      const fallo = compensacion.status === "COMPENSATION_FAILED";
      state = fallo ? "failed" : "compensated";
      detail = fallo ? (compensacion.error_code ?? "Compensacion fallida") : "Revertido";
      elapsedMs = compensacion.duration_ms ?? elapsedMs;
    } else if (accion?.status === "EXECUTED") {
      // Ejecutado pero la saga esta dando marcha atras: aun le toca revertirse.
      state = revirtiendo ? "compensating" : "success";
    } else if (accion?.status === "FAILED") {
      state = "failed";
      detail = accion.error_code ?? accion.message ?? undefined;
    } else if (accion?.status === "SKIPPED") {
      state = "skipped";
      detail = "No se intento";
    } else if (saga.current_step === nombre) {
      state = "running";
    } else if (terminada) {
      // En coreografia no existen filas SKIPPED: si la saga termino y el paso
      // no dejo rastro, es que ningun evento llego a dispararlo.
      state = "skipped";
      detail = "No se intento";
    }

    return {
      step: UI_STEP[nombre],
      label: STEP_LABELS[nombre],
      state,
      detail,
      elapsedMs,
      service: accion?.service ?? compensacion?.service,
      operation: accion?.operation,
      attempt: accion?.attempt,
      compensationRank: rango.get(nombre),
    };
  });
}

interface PollingResult {
  transfer: TransferResponse | null;
  saga: SagaExecution | null;
  steps: SagaStepInfo[];
  isPolling: boolean;
  elapsedTotal: number;
  startPolling: (transferId: string) => void;
  reset: () => void;
}

export function useTransferPolling(intervalMs = 1500): PollingResult {
  const [transfer, setTransfer] = useState<TransferResponse | null>(null);
  const [saga, setSaga] = useState<SagaExecution | null>(null);
  const [steps, setSteps] = useState<SagaStepInfo[]>([]);
  const [isPolling, setIsPolling] = useState(false);
  const [elapsedTotal, setElapsedTotal] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval>>();
  const tickRef = useRef<ReturnType<typeof setInterval>>();
  const startTimeRef = useRef<number>(0);

  const stop = useCallback(() => {
    clearInterval(timerRef.current);
    clearInterval(tickRef.current);
    setIsPolling(false);
  }, []);

  const poll = useCallback(
    async (id: string) => {
      try {
        // El estado publico y la traza se leen a la vez: la interfaz necesita
        // los dos, y pedirlos en serie duplicaria la latencia percibida.
        const [publico, traza] = await Promise.all([
          getTransfer(id),
          getSagaTrace(id).catch(() => null),
        ]);

        setTransfer(publico);
        setSaga(traza);
        setSteps(derivarPasos(traza));
        setElapsedTotal(Date.now() - startTimeRef.current);

        if (TERMINAL_STATUSES.includes(publico.status)) {
          // Una ultima lectura: la traza puede cerrarse un instante despues de
          // que el Gateway ya publico el estado final.
          const finalTrace = await getSagaTrace(id).catch(() => traza);
          setSaga(finalTrace);
          setSteps(derivarPasos(finalTrace));
          setElapsedTotal(Date.now() - startTimeRef.current);
          stop();
        }
      } catch {
        // Errores transitorios de red no deben cortar el sondeo.
      }
    },
    [stop],
  );

  const startPolling = useCallback(
    (transferId: string) => {
      stop();
      startTimeRef.current = Date.now();
      setElapsedTotal(0);
      setIsPolling(true);
      setSteps(pasosVacios());

      poll(transferId);
      timerRef.current = setInterval(() => poll(transferId), intervalMs);
      tickRef.current = setInterval(() => {
        setElapsedTotal(Date.now() - startTimeRef.current);
      }, 100);
    },
    [intervalMs, poll, stop],
  );

  const reset = useCallback(() => {
    stop();
    setTransfer(null);
    setSaga(null);
    setSteps([]);
    setElapsedTotal(0);
  }, [stop]);

  useEffect(
    () => () => {
      clearInterval(timerRef.current);
      clearInterval(tickRef.current);
    },
    [],
  );

  return { transfer, saga, steps, isPolling, elapsedTotal, startPolling, reset };
}
