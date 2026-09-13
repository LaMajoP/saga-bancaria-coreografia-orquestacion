# Saga bancaria

Esqueleto inicial de una arquitectura de microservicios para una saga bancaria.
Los servicios se ejecutan localmente, mientras que la persistencia se realiza
en Supabase PostgreSQL mediante variables de entorno incluidas en `.env`.

## Servicios

- `api-gateway`: punto de entrada público.
- `account-service`: gestión de cuentas.
- `risk-service`: evaluación de riesgo.
- `clearing-service`: compensación y liquidación.

## Inicio rápido

```bash
docker compose up --build
```

Cada servicio expone `GET /health` y su documentación interactiva en `/docs`.

## API Gateway

El Gateway expone `POST /api/v1/transfers` y utiliza el header opcional
`Idempotency-Key` (UUID) para impedir dobles solicitudes. El contrato de
los endpoints y los estados está documentado en `contrato-integracion.txt`.

Para ejecutar sus pruebas localmente:

```bash
cd api-gateway
pip install -r requirements-dev.txt
PYTHONPATH=. pytest
```
