import type { SagaExecution } from "../types/saga";

/**
 * Traza de una saga. Devuelve null mientras el saga-service todavia no ha
 * registrado la ejecucion: el Gateway responde antes de que la Saga arranque,
 * asi que durante el primer instante la traza aun no existe.
 */
export async function getSagaTrace(transferId: string): Promise<SagaExecution | null> {
  const res = await fetch(`/api/v1/sagas/${transferId}`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`saga-service respondio ${res.status}`);
  return res.json();
}

export interface AccountBalance {
  account_id: string;
  balance: number;
  currency: string;
}

/** Saldo real de una cuenta, para poder demostrar que quedan intactos. */
export async function getAccountBalance(accountId: string): Promise<AccountBalance | null> {
  const res = await fetch(`/accounts/${accountId}`);
  if (!res.ok) return null;
  return res.json();
}
