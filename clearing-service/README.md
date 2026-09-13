# Clearing Service

Servicio de compensación interbancaria simulado y persistido en el schema
`clearing` de Supabase.

| Método | Endpoint | Resultado |
| --- | --- | --- |
| POST | `/clearing/transfer` | Completa o rechaza una operación de clearing. |
| POST | `/clearing/compensate` | Compensa un clearing completado previamente. |
| GET | `/health` | Estado del servicio. |

Variables de entorno:

- `CLEARING_LATENCY_SECONDS`: latencia simulada; por defecto `0`.
- `CLEARING_TIMEOUT_SECONDS`: umbral de timeout; por defecto `3`.

`force_clearing_timeout` fuerza `REJECTED_NETWORK` con
`CLEARING_TIMEOUT`. Se acepta `force_timeout` para compatibilidad. Cada
`transfer_id` se procesa una sola vez y conserva el resultado original.
