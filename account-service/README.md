# Account & Ledger Service

Servicio propietario de cuentas, saldos y movimientos. Usa el schema aislado
`account` en Supabase PostgreSQL mediante `ACCOUNT_DATABASE_URL`.

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

Las operaciones que modifican saldo responden con `new_balance`, el saldo
resultante de esa operación. Si el mismo `transfer_id` se reintenta, se
devuelve el mismo resultado sin volver a modificar la cuenta. Los montos de
COP se reciben como enteros en pesos.

## Pruebas

```bash
pip install -r requirements-dev.txt
PYTHONPATH=. pytest
```

## Migración desde SQLite

Si existen movimientos en el volumen SQLite anterior, impórtalos una única vez
antes de eliminarlo. Con `ACCOUNT_DATABASE_URL` configurada, ejecuta desde la
raíz del repositorio:

```bash
python scripts/migrate_sqlite_to_supabase.py --sqlite-path /ruta/a/accounts.db
```
