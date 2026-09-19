# Evidencia de los casos de prueba

> Documento generado por `scripts/generar_evidencia.py`. Es la salida literal de
> `scripts/verificar_casos.py AMBAS` ejecutada contra el sistema en marcha, sin
> edicion manual.

**Generado:** 2026-09-18 21:41
**Modalidades verificadas:** Orquestacion y Coreografia
**Resultado:** 10/10 casos superados

## Que comprueba cada caso

| Caso | Escenario | Estado esperado | Compensaciones esperadas |
|---|---|---|---|
| CP-01 | Camino feliz | `CONFIRMADA` | ninguna |
| CP-02 | Fondos insuficientes | `RECHAZADA_FONDOS` | **ninguna** — el debito nunca ocurrio |
| CP-03 | Fallo de riesgo | `RECHAZADA_RIESGO` | `DEBIT` |
| CP-04 | Timeout de clearing | `RECHAZADA_RED` | `RISK` y despues `DEBIT` |
| CP-05 | Reintento con la misma clave | `CONFIRMADA` | ninguna, sin doble cobro |

En CP-02, CP-03 y CP-04 la comprobacion dura es que los saldos de origen y
destino queden **exactamente** como estaban antes de la transferencia.

## Salida de la verificacion

```text
##############################################################################
### MODALIDAD: ORCHESTRATION
##############################################################################
  preparación del escenario: ACC-001 recargada de 440,000 a 500,000 COP

==============================================================================
CP-01 — CAMINO FELIZ
==============================================================================
  transfer_id=7d2da906-1461-4bd3-b20b-c6e895950539
  Gateway: RECIBIDA → EN_PROCESO → CONFIRMADA
    → [  1] DEBIT     debit                EXECUTED             
    → [  2] RISK      risk_check           EXECUTED             
    → [  3] CLEARING  clearing_transfer    EXECUTED             
    → [  4] CREDIT    credit               EXECUTED             
  saldos antes:   {'ACC-001': 500000, 'ACC-002': 2170000, 'ACC-003': 600000}
  saldos después: {'ACC-001': 470000, 'ACC-002': 2200000, 'ACC-003': 600000}
  esperado=CONFIRMADA obtenido=CONFIRMADA   ✅ PASA

==============================================================================
CP-02 — FONDOS INSUFICIENTES (no debe compensar nada)
==============================================================================
  transfer_id=b16fb4c8-3e08-4558-8eb5-adb1de3bdc71
  Gateway: RECIBIDA → EN_PROCESO → RECHAZADA_FONDOS
    → [  1] DEBIT     debit                FAILED               INSUFFICIENT_FUNDS
    → [  2] RISK      risk_check           SKIPPED              
    → [  3] CLEARING  clearing_transfer    SKIPPED              
    → [  4] CREDIT    credit               SKIPPED              
  saldos antes:   {'ACC-001': 470000, 'ACC-002': 2200000, 'ACC-003': 600000}
  saldos después: {'ACC-001': 470000, 'ACC-002': 2200000, 'ACC-003': 600000}
  esperado=RECHAZADA_FONDOS obtenido=RECHAZADA_FONDOS   ✅ PASA

==============================================================================
CP-03 — FALLO DE RIESGO (revierte el débito)
==============================================================================
  transfer_id=2d797fe6-41f0-4fbf-99b8-b82f197ca16e
  Gateway: RECIBIDA → EN_PROCESO → COMPENSANDO → RECHAZADA_RIESGO
    → [  1] DEBIT     debit                EXECUTED             
    → [  2] RISK      risk_check           FAILED               RISK_REJECTED
    → [  3] CLEARING  clearing_transfer    SKIPPED              
    → [  4] CREDIT    credit               SKIPPED              
    ↩ [104] DEBIT     debit_compensate     COMPENSATED          
  saldos antes:   {'ACC-001': 470000, 'ACC-002': 2200000, 'ACC-003': 600000}
  saldos después: {'ACC-001': 470000, 'ACC-002': 2200000, 'ACC-003': 600000}
  esperado=RECHAZADA_RIESGO obtenido=RECHAZADA_RIESGO   ✅ PASA

==============================================================================
CP-04 — TIMEOUT DE CLEARING (compensa RISK y luego DEBIT)
==============================================================================
  transfer_id=aab82a44-be6b-482c-a3f6-a517e2452aef
  Gateway: RECIBIDA → EN_PROCESO → COMPENSANDO → RECHAZADA_RED
    → [  1] DEBIT     debit                EXECUTED             
    → [  2] RISK      risk_check           EXECUTED             
    → [  3] CLEARING  clearing_transfer    FAILED               CLEARING_TIMEOUT
    → [  4] CREDIT    credit               SKIPPED              
    ↩ [103] RISK      risk_compensate      COMPENSATED          
    ↩ [104] DEBIT     debit_compensate     COMPENSATED          
  saldos antes:   {'ACC-001': 470000, 'ACC-002': 2200000, 'ACC-003': 600000}
  saldos después: {'ACC-001': 470000, 'ACC-002': 2200000, 'ACC-003': 600000}
  esperado=RECHAZADA_RED obtenido=RECHAZADA_RED   ✅ PASA

==============================================================================
CP-05 — IDEMPOTENCIA ANTE REINTENTOS
==============================================================================
  1er POST -> HTTP 201, estado final CONFIRMADA
  2do POST -> HTTP 200, replayed=True, mismo transfer_id=True
  saldos: {'ACC-001': 470000, 'ACC-002': 2200000, 'ACC-003': 600000} → {'ACC-001': 440000, 'ACC-002': 2230000, 'ACC-003': 600000} → {'ACC-001': 440000, 'ACC-002': 2230000, 'ACC-003': 600000}
  ✅ PASA — un solo cobro

==============================================================================
RESUMEN ORCHESTRATION: 5/5 casos
==============================================================================


##############################################################################
### MODALIDAD: CHOREOGRAPHY
##############################################################################
  preparación del escenario: ACC-001 recargada de 440,000 a 500,000 COP

==============================================================================
CP-01 — CAMINO FELIZ
==============================================================================
  transfer_id=8fc043e1-fa00-454a-88bd-48056df21e16
  Gateway: RECIBIDA → EN_PROCESO → CONFIRMADA
    → [  1] DEBIT     debit                EXECUTED             
    → [  2] RISK      risk_check           EXECUTED             
    → [  3] CLEARING  clearing_transfer    EXECUTED             
    → [  4] CREDIT    credit               EXECUTED             
    eventos: TransferRequested → BalanceDebited → RiskApproved → ClearingRequested → ClearingCompleted → TransferCompleted
  saldos antes:   {'ACC-001': 500000, 'ACC-002': 2230000, 'ACC-003': 600000}
  saldos después: {'ACC-001': 470000, 'ACC-002': 2260000, 'ACC-003': 600000}
  esperado=CONFIRMADA obtenido=CONFIRMADA   ✅ PASA

==============================================================================
CP-02 — FONDOS INSUFICIENTES (no debe compensar nada)
==============================================================================
  transfer_id=362ece98-1c93-4bcc-bb51-240be44a71cb
  Gateway: RECIBIDA → EN_PROCESO → RECHAZADA_FONDOS
    → [  1] DEBIT     debit                FAILED               INSUFFICIENT_FUNDS
    eventos: TransferRequested → TransferFailed
  saldos antes:   {'ACC-001': 470000, 'ACC-002': 2260000, 'ACC-003': 600000}
  saldos después: {'ACC-001': 470000, 'ACC-002': 2260000, 'ACC-003': 600000}
  esperado=RECHAZADA_FONDOS obtenido=RECHAZADA_FONDOS   ✅ PASA

==============================================================================
CP-03 — FALLO DE RIESGO (revierte el débito)
==============================================================================
  transfer_id=b18f0bbd-077d-44ee-b050-129c45d7d35c
  Gateway: RECIBIDA → EN_PROCESO → COMPENSANDO → RECHAZADA_RIESGO
    → [  1] DEBIT     debit                EXECUTED             
    → [  2] RISK      risk_check           FAILED               RISK_REJECTED
    ↩ [104] DEBIT     debit_compensate     COMPENSATED          
    eventos: TransferRequested → BalanceDebited → RiskRejected → TransferFailed → DebitCompensationRequested → DebitCompensated → TransferCompensated
  saldos antes:   {'ACC-001': 470000, 'ACC-002': 2260000, 'ACC-003': 600000}
  saldos después: {'ACC-001': 470000, 'ACC-002': 2260000, 'ACC-003': 600000}
  esperado=RECHAZADA_RIESGO obtenido=RECHAZADA_RIESGO   ✅ PASA

==============================================================================
CP-04 — TIMEOUT DE CLEARING (compensa RISK y luego DEBIT)
==============================================================================
  transfer_id=9efb79ef-3bb8-47b8-97bd-66838f185025
  Gateway: RECIBIDA → EN_PROCESO → COMPENSANDO → RECHAZADA_RED
    → [  1] DEBIT     debit                EXECUTED             
    → [  2] RISK      risk_check           EXECUTED             
    → [  3] CLEARING  clearing_transfer    FAILED               CLEARING_TIMEOUT
    ↩ [103] RISK      risk_compensate      COMPENSATED          
    ↩ [104] DEBIT     debit_compensate     COMPENSATED          
    eventos: TransferRequested → BalanceDebited → RiskApproved → ClearingRequested → TransferFailed → RiskCompensationRequested → RiskCompensated → DebitCompensationRequested → DebitCompensated → TransferCompensated
  saldos antes:   {'ACC-001': 470000, 'ACC-002': 2260000, 'ACC-003': 600000}
  saldos después: {'ACC-001': 470000, 'ACC-002': 2260000, 'ACC-003': 600000}
  esperado=RECHAZADA_RED obtenido=RECHAZADA_RED   ✅ PASA

==============================================================================
CP-05 — IDEMPOTENCIA ANTE REINTENTOS
==============================================================================
  1er POST -> HTTP 201, estado final CONFIRMADA
  2do POST -> HTTP 200, replayed=True, mismo transfer_id=True
  saldos: {'ACC-001': 470000, 'ACC-002': 2260000, 'ACC-003': 600000} → {'ACC-001': 440000, 'ACC-002': 2290000, 'ACC-003': 600000} → {'ACC-001': 440000, 'ACC-002': 2290000, 'ACC-003': 600000}
  ✅ PASA — un solo cobro

==============================================================================
RESUMEN CHOREOGRAPHY: 5/5 casos
==============================================================================
```

## Como reproducirlo

```bash
docker compose up -d
python scripts/verificar_casos.py AMBAS
```
