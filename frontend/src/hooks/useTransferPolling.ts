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
  const timeoutRef = useRef<ReturnType<typeof setTimeout>>();
  const tickRef = useRef<ReturnType<typeof setInterval>>();
  const startTimeRef = useRef<number>(0);
  const activeRef = useRef(false);

  const stop = useCallback(() => {
    activeRef.current = false;
    clearTimeout(timeoutRef.current);
    clearInterval(tickRef.current);
    setIsPolling(false);
  }, []);

  /**
   * Duracion real de la saga segun el servidor.
   *
   * El cronometro del navegador mide desde que se pulsa el boton e incluye la
   * latencia del sondeo, asi que exagera. Cuando la traza trae sus dos marcas
   * de tiempo, se usa la diferencia entre ellas: es el numero que coincide con
   * la bitacora de auditoria.
   */
  const duracionReal = (traza: SagaExecution | null): number | null => {
    if (!traza?.finished_at) return null;
    return new Date(traza.finished_at).getTime() - new Date(traza.started_at).getTime();
  };

  /**
   * Sondeo secuencial: cada consulta espera a la anterior.
   *
   * Con setInterval las peticiones se solapaban —cada vuelta tarda entre dos y
   * cuatro segundos y el intervalo era de uno y medio—, se acumulaban en la
   * cola del navegador y la respuesta que traia el estado final llegaba con
   * decenas de segundos de retraso. El resultado era una saga ya terminada en
   * el servidor que en pantalla seguia "Procesando".
   */
  const poll = useCallback(
    async (id: string) => {
      if (!activeRef.current) return;
      try {
        const [publico, traza] = await Promise.all([
          getTransfer(id),
          getSagaTrace(id).catch(() => null),
        ]);
        if (!activeRef.current) return;

        // La Saga es la fuente de verdad de su propio final. El estado del
        // Gateway es una proyeccion que puede llegar unos segundos despues,
        // porque las notificaciones salen en cola para no frenar la saga.
        // Esperar a esa proyeccion dejaba la pantalla en "Procesando" con los
        // cuatro pasos ya en verde.
        const terminada = traza?.finished_at != null;
        const estado = (
          terminada && traza ? traza.gateway_status : publico.status
        ) as TransferStatus;

        setTransfer({ ...publico, status: estado });
        setSaga(traza);
        setSteps(derivarPasos(traza));

        if (terminada || TERMINAL_STATUSES.includes(estado)) {
          setElapsedTotal(duracionReal(traza) ?? Date.now() - startTimeRef.current);
          stop();
          return;
        }
        setElapsedTotal(Date.now() - startTimeRef.current);
      } catch {
        // Un fallo puntual de red no debe cortar el sondeo.
      }
      if (activeRef.current) {
        timeoutRef.current = setTimeout(() => poll(id), intervalMs);
      }
    },
    [intervalMs, stop],
  );

  const startPolling = useCallback(
    (transferId: string) => {
      stop();
      startTimeRef.current = Date.now();
      setElapsedTotal(0);
      setIsPolling(true);
      setSteps(pasosVacios());
      activeRef.current = true;

      void poll(transferId);
      tickRef.current = setInterval(() => {
        if (activeRef.current) setElapsedTotal(Date.now() - startTimeRef.current);
      }, 100);
    },
    [poll, stop],
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
      activeRef.current = false;
      clearTimeout(timeoutRef.current);
      clearInterval(tickRef.current);
    },
    [],
  );

  return { transfer, saga, steps, isPolling, elapsedTotal, startPolling, reset };
}
