# Risk Service

Servicio de evaluación de riesgo persistido en el schema `risk` de Supabase.

| Método | Endpoint | Resultado |
| --- | --- | --- |
| POST | `/risk/check` | Aprueba o rechaza una transferencia de forma idempotente. |
| POST | `/risk/compensate` | Compensa una aprobación previa. |
| GET | `/health` | Estado del servicio. |

`force_risk_failure` fuerza un rechazo. Se acepta también `force_failure`
para compatibilidad con el contrato inicial. `RISK_MAX_AMOUNT` define el
límite máximo permitido y tiene `1000000` como valor predeterminado.

Las evaluaciones usan `transfer_id` como clave de idempotencia. Reutilizarlo
con un cuerpo diferente devuelve `IDEMPOTENCY_CONFLICT`.
