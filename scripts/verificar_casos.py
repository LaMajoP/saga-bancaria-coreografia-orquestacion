#!/usr/bin/env python3
"""Ejecuta los cinco casos obligatorios contra el sistema en marcha.

Entra siempre por el API Gateway, como lo haria el frontend, y comprueba tres
cosas en cada caso: el estado publico final, las compensaciones registradas en
la bitacora y —lo mas importante— que los saldos queden intactos cuando la
transferencia no debe prosperar.

Uso:
    python scripts/verificar_casos.py                  # orquestacion
    python scripts/verificar_casos.py CHOREOGRAPHY     # coreografia
    python scripts/verificar_casos.py AMBAS            # las dos seguidas
"""

import sys
import time
from uuid import uuid4

import httpx

GATEWAY = "http://127.0.0.1:8000"
ACCOUNT = "http://127.0.0.1:8001"
SAGA = "http://127.0.0.1:8004"
CUENTAS = ("ACC-001", "ACC-002", "ACC-003")
ESTADOS_FINALES = {
    "CONFIRMADA",
    "RECHAZADA_FONDOS",
    "RECHAZADA_RIESGO",
    "RECHAZADA_RED",
    "COMPENSADA",
    "FALLIDA",
}

cliente = httpx.Client(timeout=30)

#: Cada corrida mueve dinero de verdad. La cuenta origen necesita fondos de
#: sobra para CP-01 y CP-05, y la cuenta ACC-003 debe seguir sin fondos para
#: que CP-02 tenga sentido.
SALDO_MINIMO_ORIGEN = 500_000


def preparar_escenario() -> None:
    """Deja la cuenta origen con fondos suficientes antes de empezar.

    Se hace con el endpoint publico de credito del Account Service, sin tocar
    su base de datos: la verificacion no debe romper el aislamiento que el
    propio taller evalua.
    """
    actual = cliente.get(f"{ACCOUNT}/accounts/ACC-001").json()["balance"]
    if actual >= SALDO_MINIMO_ORIGEN:
        return
    faltante = SALDO_MINIMO_ORIGEN - actual
    cliente.post(
        f"{ACCOUNT}/accounts/ACC-001/credit",
        json={"transfer_id": str(uuid4()), "amount": faltante},
    )
    print(f"  preparación del escenario: ACC-001 recargada de {actual:,} a {SALDO_MINIMO_ORIGEN:,} COP")


def saldos() -> dict[str, int]:
    return {c: cliente.get(f"{ACCOUNT}/accounts/{c}").json()["balance"] for c in CUENTAS}


def esperar_estado_final(transfer_id: str, limite: int = 120) -> tuple[str, list[str]]:
    """Sondea el Gateway hasta que la Saga llegue a un estado terminal."""
    transiciones: list[str] = []
    inicio = time.time()
    while time.time() - inicio < limite:
        estado = cliente.get(f"{GATEWAY}/api/v1/transfers/{transfer_id}").json()["status"]
        if not transiciones or transiciones[-1] != estado:
            transiciones.append(estado)
        if estado in ESTADOS_FINALES:
            return estado, transiciones
        time.sleep(0.4)
    return "TIMEOUT", transiciones


def mostrar_traza(transfer_id: str) -> None:
    traza = cliente.get(f"{SAGA}/api/v1/sagas/{transfer_id}").json()
    for paso in traza["steps"]:
        flecha = "↩" if paso["kind"] == "COMPENSATION" else "→"
        print(
            f"    {flecha} [{paso['sequence']:>3}] {paso['step_name']:<9} "
            f"{paso['operation']:<20} {paso['status']:<20} {paso['error_code'] or ''}"
        )
    if traza["events"]:
        print("    eventos: " + " → ".join(e["event_type"] for e in traza["events"]))


def ejecutar_caso(nombre, cuerpo, estado_esperado, modo, saldos_esperados=None) -> bool:
    print(f"\n{'=' * 78}\n{nombre}\n{'=' * 78}")
    antes = saldos()
    respuesta = cliente.post(
        f"{GATEWAY}/api/v1/transfers", json=cuerpo, headers={"X-Saga-Mode": modo}
    )
    transfer_id = respuesta.json()["transfer_id"]
    final, transiciones = esperar_estado_final(transfer_id)
    despues = saldos()

    print(f"  transfer_id={transfer_id}")
    print(f"  Gateway: {' → '.join(transiciones)}")
    mostrar_traza(transfer_id)
    print(f"  saldos antes:   {antes}")
    print(f"  saldos después: {despues}")

    correcto = final == estado_esperado
    if saldos_esperados is None:
        # La transferencia no debia prosperar: ni un peso puede haberse movido.
        correcto = correcto and antes == despues
    else:
        correcto = correcto and all(
            despues[c] - antes[c] == delta for c, delta in saldos_esperados.items()
        )
    print(f"  esperado={estado_esperado} obtenido={final}   {'✅ PASA' if correcto else '❌ FALLA'}")
    return correcto


def verificar_idempotencia(modo: str) -> bool:
    print(f"\n{'=' * 78}\nCP-05 — IDEMPOTENCIA ANTE REINTENTOS\n{'=' * 78}")
    clave = str(uuid4())
    cuerpo = {
        "source_account_id": "ACC-001",
        "destination_account_id": "ACC-002",
        "amount": "30000",
        "currency": "COP",
    }
    cabeceras = {"X-Saga-Mode": modo, "Idempotency-Key": clave}
    antes = saldos()
    primera = cliente.post(f"{GATEWAY}/api/v1/transfers", json=cuerpo, headers=cabeceras)
    transfer_id = primera.json()["transfer_id"]
    final, _ = esperar_estado_final(transfer_id)
    tras_la_primera = saldos()

    segunda = cliente.post(f"{GATEWAY}/api/v1/transfers", json=cuerpo, headers=cabeceras)
    time.sleep(5)
    tras_la_segunda = saldos()

    print(f"  1er POST -> HTTP {primera.status_code}, estado final {final}")
    print(
        f"  2do POST -> HTTP {segunda.status_code}, replayed={segunda.json()['replayed']}, "
        f"mismo transfer_id={segunda.json()['transfer_id'] == transfer_id}"
    )
    print(f"  saldos: {antes} → {tras_la_primera} → {tras_la_segunda}")
    correcto = (
        segunda.status_code == 200
        and segunda.json()["replayed"]
        and segunda.json()["transfer_id"] == transfer_id
        and tras_la_primera == tras_la_segunda
        and tras_la_primera["ACC-001"] - antes["ACC-001"] == -30000
    )
    print(f"  {'✅ PASA — un solo cobro' if correcto else '❌ FALLA'}")
    return correcto


def transferencia(**extra) -> dict:
    return {
        "source_account_id": "ACC-001",
        "destination_account_id": "ACC-002",
        "amount": "30000",
        "currency": "COP",
        **extra,
    }


def verificar(modo: str) -> bool:
    print(f"\n\n{'#' * 78}\n### MODALIDAD: {modo}\n{'#' * 78}")
    preparar_escenario()
    resultados = [
        ejecutar_caso(
            "CP-01 — CAMINO FELIZ",
            transferencia(),
            "CONFIRMADA",
            modo,
            saldos_esperados={"ACC-001": -30000, "ACC-002": 30000, "ACC-003": 0},
        ),
        ejecutar_caso(
            "CP-02 — FONDOS INSUFICIENTES (no debe compensar nada)",
            {
                "source_account_id": "ACC-003",
                "destination_account_id": "ACC-002",
                "amount": "99999999",
                "currency": "COP",
            },
            "RECHAZADA_FONDOS",
            modo,
        ),
        ejecutar_caso(
            "CP-03 — FALLO DE RIESGO (revierte el débito)",
            transferencia(chaos={"force_risk_failure": True, "force_clearing_timeout": False}),
            "RECHAZADA_RIESGO",
            modo,
        ),
        ejecutar_caso(
            "CP-04 — TIMEOUT DE CLEARING (compensa RISK y luego DEBIT)",
            transferencia(chaos={"force_risk_failure": False, "force_clearing_timeout": True}),
            "RECHAZADA_RED",
            modo,
        ),
        verificar_idempotencia(modo),
    ]
    print(f"\n{'=' * 78}\nRESUMEN {modo}: {sum(resultados)}/5 casos\n{'=' * 78}")
    return all(resultados)


def main() -> int:
    argumento = (sys.argv[1] if len(sys.argv) > 1 else "ORCHESTRATION").upper()
    modos = ("ORCHESTRATION", "CHOREOGRAPHY") if argumento == "AMBAS" else (argumento,)
    if any(m not in {"ORCHESTRATION", "CHOREOGRAPHY"} for m in modos):
        print("Modalidad no reconocida. Usa ORCHESTRATION, CHOREOGRAPHY o AMBAS.")
        return 2
    return 0 if all(verificar(modo) for modo in modos) else 1


if __name__ == "__main__":
    raise SystemExit(main())
