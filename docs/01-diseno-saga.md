# Diseño de la Saga — Persona 2

> Documento de diseño previo a la implementación. Fija la máquina de estados, el
> catálogo de eventos y los contratos de integración de las dos modalidades del
> Patrón Saga. **Ninguna decisión aquí modifica los endpoints, campos ni estados
> ya publicados por Persona 1**; sólo añade lo que el contrato dejó abierto.

Fuentes normativas, en orden de precedencia:

1. `Taller Avanzado de Arquitectura: Patrón Saga Bancario...` (enunciado oficial).
2. `contrato-integracion.txt` (contrato interno del equipo).
3. `contexto-proyecto.txt` (distribución de trabajo).

---

## 1. Decisiones de arquitectura

| # | Decisión | Justificación |
|---|---|---|
| D-01 | La saga vive en un servicio nuevo, `saga-service`, en el puerto **8004**. | El enunciado §2.4 exige una capa lógica de saga separable. Aísla mi trabajo del de Persona 1. |
| D-02 | Las **dos** modalidades comparten `domain/` y `clients/`; sólo cambia la capa de coordinación. | Hace la comparativa del criterio 2 (20%) demostrable en código: mismos pasos, dos estilos de control. |
| D-03 | El orquestador se implementa como **flujo de Prefect** (`@flow` + `@task` por paso). | El enunciado §3 admite explícitamente "coordinador **o flujo de Prefect**", y §2.5 pide un motor de flujos con delays. Cubre criterios 1 y 3 a la vez. |
| D-04 | Se usa **Prefect 3.8.6**, no Prefect 2. | Prefect 2 está descontinuado y no instala en Python 3.14. La API `@flow`/`@task` que pide el enunciado es idéntica en ambas versiones. Queda documentado por transparencia. |
| D-05 | El broker de la coreografía es **RabbitMQ** con un exchange `topic`. | El enunciado §3 pide "un bus o canal de mensajería". La consola de RabbitMQ sirve de evidencia visual en el video. |
| D-06 | Los participantes coreografiados son **adaptadores propios** que reaccionan a eventos y llaman a los endpoints HTTP de Persona 1. | `contexto-proyecto.txt` §FASE 2: "Persona 2 NO debería modificar la lógica interna de los microservicios". |
| D-07 | El estado público se actualiza por **endpoint interno del Gateway**, no por evento, en ambas modalidades. | El contrato §6.1 obliga a escoger **una sola** opción. Un mecanismo único evita divergencias entre orquestación y coreografía. |
| D-08 | Los delays de 2–4 s los inyecta la **capa de saga**, no los microservicios. | Persona 1 ya cerró sus servicios. Poner el delay en la saga permite apagarlo en las pruebas automatizadas y encenderlo en la demo, sin tocar código ajeno. |

---

## 2. Los cuatro pasos y sus compensaciones

La saga es una secuencia de cuatro transacciones locales. Cada una tiene una
compensación explícita, salvo la última (nada posterior puede fallar).

| # | Paso | Servicio | Operación normal | Compensación |
|---|---|---|---|---|
| 1 | `DEBIT` | Account `:8001` | `POST /accounts/{origen}/debit` | `POST /accounts/{origen}/debit/compensate` |
| 2 | `RISK` | Risk `:8002` | `POST /risk/check` | `POST /risk/compensate` |
| 3 | `CLEARING` | Clearing `:8003` | `POST /clearing/transfer` | `POST /clearing/compensate` |
| 4 | `CREDIT` | Account `:8001` | `POST /accounts/{destino}/credit` | `POST /accounts/{destino}/credit/compensate` |

**Regla de reversa (criterio 1 de la rúbrica):** ante un fallo en el paso *n*, se
compensan los pasos `n-1, n-2, ..., 1` **en ese orden estricto**, y únicamente
los que quedaron registrados como `EXECUTED`. Un paso `SKIPPED` o `FAILED` nunca
se compensa.

```
DEBIT  ──►  RISK  ──►  CLEARING  ──►  CREDIT
                          ✗ falla
                          │
  ◄── compensar RISK ◄────┘
  │
  └──► compensar DEBIT ──► estado consistente
```

### 2.1 Comportamiento real de los servicios (verificado, no asumido)

Smoke test ejecutado contra los cuatro servicios el 2026-09-18. Tres hallazgos
que condicionan la implementación:

| Servicio | Al rechazar devuelve | Consecuencia |
|---|---|---|
| Account (fondos insuficientes) | **HTTP 409** + `error_code: INSUFFICIENT_FUNDS` | Se ramifica por código HTTP. |
| Risk (rechazo) | **HTTP 200** + `success: false` + `status: RISK_REJECTED` | **No se puede usar `raise_for_status()`**: un rechazo de riesgo parece un éxito a nivel HTTP. |
| Clearing (timeout) | **HTTP 200** + `success: false` + `status: REJECTED_NETWORK` | Igual que Risk. |

> Por eso todo resultado de paso se evalúa leyendo el **cuerpo** de la respuesta
> (`success` y `status`), y el código HTTP se usa sólo para distinguir fallo de
> negocio (4xx) de fallo técnico reintentable (5xx, timeout, conexión).

---

## 3. Máquina de estados

### 3.1 Estados internos de la saga

El contrato §4 define once estados. Para poder reportar a la vez *por qué* falló
y *que ya se compensó*, la ejecución guarda **dos campos ortogonales**:

`status` — desenlace de la saga:

```
PENDING → DEBITED → RISK_APPROVED → CLEARING_PENDING → COMPLETED
                                                      
   └─► REJECTED_FUNDS | REJECTED_RISK | REJECTED_NETWORK | FAILED
```

`compensation_status` — evidencia de la marcha atrás:

```
NOT_REQUIRED | COMPENSATING | COMPENSATED | COMPENSATION_FAILED
```

Esto resuelve una ambigüedad de los documentos: CP-03 exige estado final
`RECHAZADO_RIESGO`, pero los diagramas del contrato §23 terminan en
`COMPENSATED`. Con dos campos ambas afirmaciones son ciertas al mismo tiempo:
`status = REJECTED_RISK` y `compensation_status = COMPENSATED`.

### 3.2 Transiciones válidas

| Desde | Evento | Hacia |
|---|---|---|
| `PENDING` | débito exitoso | `DEBITED` |
| `PENDING` | fondos insuficientes | `REJECTED_FUNDS` *(terminal, sin compensación)* |
| `DEBITED` | riesgo aprueba | `RISK_APPROVED` |
| `DEBITED` | riesgo rechaza | `REJECTED_RISK` vía `COMPENSATING` |
| `RISK_APPROVED` | clearing acepta | `CLEARING_PENDING` |
| `RISK_APPROVED` | clearing expira | `REJECTED_NETWORK` vía `COMPENSATING` |
| `CLEARING_PENDING` | crédito exitoso | `COMPLETED` *(terminal)* |
| `CLEARING_PENDING` | crédito falla | `FAILED` vía `COMPENSATING` |

`REJECTED_FUNDS` es el único fallo que **no** dispara compensación: el débito
nunca ocurrió, y compensar algo no ejecutado violaría la regla principal del
contrato §27.

### 3.3 Mapeo hacia el estado público del Gateway

El Gateway habla en español y con su propio vocabulario (`gateway.transfers.status`).
La saga traduce antes de notificar:

| Saga (interno) | Gateway (público) | Caso |
|---|---|---|
| `PENDING`, `DEBITED`, `RISK_APPROVED`, `CLEARING_PENDING` | `EN_PROCESO` | — |
| `COMPLETED` | `CONFIRMADA` | CP-01 |
| `REJECTED_FUNDS` | `RECHAZADA_FONDOS` | CP-02 |
| `COMPENSATING` (transitorio) | `COMPENSANDO` | CP-03 / CP-04 |
| `REJECTED_RISK` | `RECHAZADA_RIESGO` | CP-03 |
| `REJECTED_NETWORK` | `RECHAZADA_RED` | CP-04 |
| `FAILED` | `FALLIDA` | fallo tardío |

En CP-03 y CP-04 el Gateway recibe **dos** notificaciones: primero `COMPENSANDO`
y luego el rechazo definitivo. Eso es deliberado: permite que el frontend de
Persona 3 muestre la marcha atrás en vivo, que es justo lo que pide el criterio 3
de la rúbrica ("los delays no permiten apreciar la marcha atrás" = nivel insuficiente).

---

## 4. Clasificación de fallos, reintentos y timeouts

| Clase | Ejemplos | Política |
|---|---|---|
| **Fallo de negocio** (terminal) | `INSUFFICIENT_FUNDS`, `RISK_REJECTED`, `RISK_LIMIT_EXCEEDED`, `CLEARING_TIMEOUT` | No se reintenta. Dispara compensación en reversa (salvo fondos). |
| **Fallo técnico transitorio** | timeout HTTP, error de conexión, 502/503/504 | Hasta **3 intentos** con backoff exponencial (0.5 s, 1 s, 2 s). Es seguro porque todos los endpoints de Persona 1 son idempotentes por `transfer_id`. Agotados los intentos, se trata como fallo y se compensa. |
| **Fallo de integración** (no reintentable) | `409 IDEMPOTENCY_CONFLICT`, `422`, `404 ACCOUNT_NOT_FOUND` | No se reintenta. `status = FAILED`, se compensa lo ejecutado. |

**Timeouts HTTP.** `connect = 5 s`; `read = CLEARING_LATENCY_SECONDS + 10 s`. El
margen es obligatorio: Clearing duerme deliberadamente para simular latencia
interbancaria, y un read-timeout corto convertiría CP-01 en un falso CP-04.

**Compensación fallida.** Si una compensación no logra completarse tras sus
reintentos, la saga queda en `compensation_status = COMPENSATION_FAILED` y se
registra en la bitácora. Nunca se marca como compensada una reversa que no
ocurrió: preferimos un estado visible y auditable a un limbo silencioso.

---

## 5. Catálogo de eventos de la coreografía

Formato obligatorio (contrato §12):

```json
{
  "event_id": "uuid",
  "event_type": "BalanceDebited",
  "transfer_id": "uuid",
  "timestamp": "2026-09-18T15:30:00Z",
  "payload": { "account_id": "ACC-001", "amount": 500000 }
}
```

### 5.1 Eventos del contrato

| Evento | Publica | Consume | Efecto |
|---|---|---|---|
| `TransferRequested` | Gateway | Account | Inicia la saga: intenta débito. |
| `BalanceDebited` | Account | Risk | Débito hecho: evaluar riesgo. |
| `RiskApproved` | Risk | Clearing | Riesgo ok: solicitar liquidación. |
| `RiskRejected` | Risk | Account | Riesgo rechaza: revertir débito. |
| `ClearingRequested` | Clearing | *(auditoría)* | Intención de liquidar, antes de ejecutarla. |
| `TransferCompleted` | Account | Proyector | CP-01 terminado. |
| `TransferFailed` | cualquiera | Proyector | Fallo terminal, con `error_code`. |
| `DebitCompensationRequested` | Risk / Account | Account | Pide revertir el débito. |
| `RiskCompensationRequested` | Clearing | Risk | Pide anular la aprobación de riesgo. |
| `DebitCompensated` | Account | Proyector | Débito revertido. |
| `RiskCompensated` | Risk | Account | Riesgo anulado → **encadena** la reversa del débito. |

### 5.2 Eventos añadidos

El contrato §11 los llama "eventos **principales**", no una lista cerrada. Estos
cuatro son necesarios y se informan al equipo según el procedimiento de §24:

| Evento | Por qué es necesario |
|---|---|
| `ClearingCompleted` | Sin él no hay forma de disparar el paso 4 (crédito). La lista original salta de `ClearingRequested` a `TransferCompleted` y omite el crédito. |
| `ClearingCompensationRequested` | Necesario para el fallo tardío (crédito falla con clearing ya ejecutado). |
| `ClearingCompensated` | Cierra la cadena de reversa del paso 3. |
| `TransferCompensated` | Marca el fin de la marcha atrás; es lo que el frontend espera para pintar `COMPENSADA`. |

### 5.3 Cadenas de eventos por caso

**CP-01 — camino feliz**

```
TransferRequested → BalanceDebited → RiskApproved → ClearingRequested
                 → ClearingCompleted → TransferCompleted
```

**CP-02 — fondos insuficientes** (sin compensación alguna)

```
TransferRequested → TransferFailed(INSUFFICIENT_FUNDS)
```

**CP-03 — riesgo rechaza** (un solo paso que revertir)

```
TransferRequested → BalanceDebited → RiskRejected
                 → DebitCompensationRequested → DebitCompensated
                 → TransferCompensated + TransferFailed(RISK_REJECTED)
```

**CP-04 — timeout de clearing** (dos pasos, en reversa estricta)

```
TransferRequested → BalanceDebited → RiskApproved → ClearingRequested
                 → TransferFailed(CLEARING_TIMEOUT)
                 → RiskCompensationRequested → RiskCompensated
                 → DebitCompensationRequested → DebitCompensated
                 → TransferCompensated
```

> **El orden inverso se logra por encadenamiento causal, no por un coordinador.**
> `RiskCompensated` es lo que dispara `DebitCompensationRequested`. Si en cambio
> el fallo emitiera ambas peticiones de compensación a la vez, se ejecutarían en
> paralelo y la rúbrica lo penaliza ("carece de control estricto de reversa").
> Esta es la diferencia técnica central frente a la orquestación, y es lo que se
> argumentará en el documento comparativo.

---

## 6. Topología de RabbitMQ

- **Exchange:** `saga.events`, tipo `topic`, durable.
- **Routing key:** el `event_type` literal.
- **Colas** (durables, una por participante):

| Cola | Bindings |
|---|---|
| `saga.account` | `TransferRequested`, `RiskRejected`, `ClearingCompleted`, `DebitCompensationRequested`, `RiskCompensated` |
| `saga.risk` | `BalanceDebited`, `RiskCompensationRequested` |
| `saga.clearing` | `RiskApproved`, `ClearingCompensationRequested` |
| `saga.projector` | `#` (todos: proyecta el estado público hacia el Gateway) |
| `saga.audit` | `#` (todos: persiste el event store en `saga.saga_events`) |

Publicación persistente (`delivery_mode=2`) y consumo con `ack` manual: se
confirma **después** de procesar, de modo que una caída del participante no
pierde el evento.

---

## 7. Idempotencia y consistencia eventual

Tres barreras superpuestas, de fuera hacia dentro:

1. **Gateway** — `Idempotency-Key` → un solo `transfer_id` por clave (ya implementado por Persona 1).
2. **Saga** — tabla `saga.processed_events` con único `(consumer, event_id)`. Un evento reentregado por RabbitMQ se descarta sin efecto.
3. **Microservicios** — cada operación es idempotente por `transfer_id`; un reintento devuelve el resultado original sin mover saldo (verificado en el smoke test).

Esta redundancia es la que permite reintentar sin miedo (§4) y es la evidencia
directa de CP-05.

**Consistencia eventual / BASE.** No existe transacción global. Cada servicio
confirma su transacción local de inmediato (*Basically Available*), el sistema
atraviesa estados intermedios visibles como `DEBITED` o `COMPENSANDO`
(*Soft state*), y la saga garantiza que toda ejecución termina en un estado
terminal consistente (*Eventual consistency*). La prueba dura: en CP-03 y CP-04
los saldos de origen y destino deben volver **exactamente** a su valor previo.

---

## 8. Observabilidad: Prefect y delays

- El orquestador es un `@flow` de Prefect; cada paso y cada compensación es un `@task` con nombre explícito (`debit`, `risk`, `clearing`, `credit`, `compensate_risk`, `compensate_debit`).
- `SAGA_STEP_DELAY_SECONDS` (por defecto **3 s**, rango sugerido 2–4) se aplica antes de cada paso y de cada compensación. Se pone en `0` para las pruebas automatizadas.
- Cada paso escribe una fila en `saga.saga_steps` con `transfer_id`, servicio, operación, estado, `error_code`, duración y timestamp. Esa tabla **es** la bitácora de auditoría que exige CP-04, y es la fuente que consumirá el frontend de Persona 3.
- La coreografía no usa Prefect (no tiene coordinador que instrumentar): su trazabilidad sale del event store `saga.saga_events` y de la consola de RabbitMQ.

---

## 9. Integración con el API Gateway

El contrato §6.1 dejó dos huecos abiertos. Se cierran así (decisión D-07):

**Entrega hacia la saga.** El Gateway, tras crear la transferencia, la despacha
según `SAGA_MODE`:

- `ORCHESTRATION` → `POST {SAGA_ORCHESTRATOR_URL}/api/v1/sagas/transfers` → responde `202 Accepted`.
- `CHOREOGRAPHY` → publica `TransferRequested` en el exchange `saga.events`.

**Retorno del estado.** La saga notifica al Gateway:

```
PATCH /internal/v1/transfers/{transfer_id}/status
X-Internal-Token: <SAGA_INTERNAL_TOKEN>

{ "status": "COMPENSANDO", "error_code": null, "message": null,
  "updated_at": "2026-09-18T15:30:00Z" }
```

Ambos son los puntos de extensión que el propio contrato §6.1 anticipa, así que
no constituyen un cambio unilateral. La ruta pública, los nombres de campos y el
`transfer_id` quedan intactos.

---

## 10. Modelo de datos del schema `saga`

`saga.executions` ya existe; se le añaden columnas. Las otras tres tablas son
nuevas. **Sin llaves foráneas hacia otros schemas**, para no romper el
aislamiento entre microservicios que evalúa el criterio 5.

| Tabla | Propósito |
|---|---|
| `saga.executions` | Una fila por saga: modalidad, `status`, `compensation_status`, paso actual. |
| `saga.saga_steps` | Bitácora de auditoría: una fila por paso y por compensación. |
| `saga.saga_events` | Event store de la coreografía, en el formato del §12. |
| `saga.processed_events` | Deduplicación `(consumer, event_id)`. |

---

## 11. Matriz de verificación

Cada caso debe pasar en **las dos** modalidades.

| Caso | Disparador | Pasos ejecutados | Compensaciones esperadas | Estado final |
|---|---|---|---|---|
| CP-01 | — | DEBIT, RISK, CLEARING, CREDIT | ninguna | `CONFIRMADA` |
| CP-02 | monto > saldo | ninguno | **ninguna** | `RECHAZADA_FONDOS` |
| CP-03 | `force_risk_failure` | DEBIT | `compensate_debit` | `RECHAZADA_RIESGO` |
| CP-04 | `force_clearing_timeout` | DEBIT, RISK | `compensate_risk` **→ luego** `compensate_debit` | `RECHAZADA_RED` |
| CP-05 | misma `Idempotency-Key` | DEBIT, RISK, CLEARING, CREDIT (una sola vez) | ninguna | `CONFIRMADA`, saldos sin doble movimiento |

Invariante verificable en CP-02, CP-03 y CP-04: `saldo_origen_final == saldo_origen_inicial`
y `saldo_destino_final == saldo_destino_inicial`.
