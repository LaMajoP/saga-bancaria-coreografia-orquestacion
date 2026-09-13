# Account & Ledger Service

Servicio propietario de cuentas, saldos y movimientos. Usa una base SQLite
aislada en `ACCOUNT_DB_PATH`; Docker Compose la persiste en el volumen
`account_service_data`.

Para la demostración local se inicializan las cuentas `ACC-001` (1.500.000
COP), `ACC-002` (1.000.000 COP) y `ACC-003` (100.000 COP).

| Método | Endpoint | Resultado |
| --- | --- | --- |
| GET | `/accounts/{account_id}` | Consulta saldo |
| POST | `/accounts/{account_id}/debit` | Débito idempotente (`DEBITED`) |
| POST | `/accounts/{account_id}/credit` | Crédito idempotente (`COMPLETED`) |
| POST | `/accounts/{account_id}/debit/compensate` | Revierte un débito (`COMPENSATED`) |
| POST | `/accounts/{account_id}/credit/compensate` | Revierte un crédito (`COMPENSATED`) |

Los `POST` reciben:

```json
{"transfer_id": "UUID", "amount": 500000}
```

Cada combinación de `transfer_id`, cuenta y operación solo se aplica una vez.
Una compensación falla con `ORIGINAL_OPERATION_NOT_FOUND` si su operación
original no ocurrió.

## Pruebas

```bash
pip install -r requirements-dev.txt
PYTHONPATH=. pytest
```
