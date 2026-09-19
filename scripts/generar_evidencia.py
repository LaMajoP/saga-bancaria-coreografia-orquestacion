#!/usr/bin/env python3
"""Genera el documento de evidencia de los casos de prueba.

Ejecuta la verificacion completa contra el sistema en marcha y guarda la salida
literal en docs/03-evidencia-casos-de-prueba.md. La evidencia se regenera, no se
escribe a mano: si el comportamiento cambiara, el documento lo reflejaria.

Uso:
    docker compose up -d
    python scripts/generar_evidencia.py
"""

from datetime import datetime
from pathlib import Path
import subprocess
import sys

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "docs" / "03-evidencia-casos-de-prueba.md"

CABECERA = """# Evidencia de los casos de prueba

> Documento generado por `scripts/generar_evidencia.py`. Es la salida literal de
> `scripts/verificar_casos.py AMBAS` ejecutada contra el sistema en marcha, sin
> edicion manual.

**Generado:** {fecha}
**Modalidades verificadas:** Orquestacion y Coreografia
**Resultado:** {resultado}

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
{salida}
```

## Como reproducirlo

```bash
docker compose up -d
python scripts/verificar_casos.py AMBAS
```
"""


def main() -> int:
    print("Ejecutando la verificacion completa (puede tardar varios minutos)...")
    proceso = subprocess.run(
        [sys.executable, str(RAIZ / "scripts" / "verificar_casos.py"), "AMBAS"],
        capture_output=True,
        text=True,
        cwd=RAIZ,
    )
    salida = (proceso.stdout + proceso.stderr).strip()
    resultado = "10/10 casos superados" if proceso.returncode == 0 else "HAY CASOS FALLIDOS"

    SALIDA.parent.mkdir(exist_ok=True)
    SALIDA.write_text(
        CABECERA.format(
            fecha=datetime.now().strftime("%Y-%m-%d %H:%M"),
            resultado=resultado,
            salida=salida,
        )
    )
    print(f"\n{resultado}")
    print(f"Escrito: {SALIDA.relative_to(RAIZ)}")
    return proceso.returncode


if __name__ == "__main__":
    raise SystemExit(main())
