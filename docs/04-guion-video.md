# Guion del video demostrativo — 6 minutos

> El enunciado pide un video **de máximo 6 minutos** que exhiba los fallos y las
> compensaciones. Este guion reparte el tiempo según el peso real de la rúbrica:
> la lógica de Saga y las compensaciones valen el 40%, así que se llevan casi la
> mitad del video.

---

## Antes de grabar

**1. Baja el delay a 2 segundos.** El enunciado admite de 2 a 4 s; con 3 s los
casos no caben en seis minutos.

```bash
SAGA_STEP_DELAY_SECONDS=2 docker compose up -d
```

**2. Cuánto tarda realmente cada caso.** Medido sobre este sistema con delay de
2 s, contra Supabase remoto. Planifica con estos números, no con estimaciones:

| Caso | Orquestación | Coreografía |
|---|---|---|
| CP-01 camino feliz | **36 s** | 26 s |
| CP-02 fondos insuficientes | **13 s** | — |
| CP-03 fallo de riesgo | **28 s** | — |
| CP-04 timeout de clearing | **40 s** | **34 s** |
| CP-05 idempotencia | instantáneo* | — |

\* Si reutilizas la clave de la transferencia de CP-01, el reintento es inmediato.

La suma de las ejecuciones es de unos **2:30**. Eso no es tiempo perdido: es
justo mientras corren cuando narras. Lo que no cabe es detenerse a explicar
código o alargar la introducción.

**3. Prepara el escenario.** El ensayo recarga ACC-001, que si no se queda sin
fondos y CP-03 y CP-04 saldrían como `RECHAZADA_FONDOS`:

```bash
python scripts/verificar_casos.py ORCHESTRATION
```

**4. Abre cuatro pestañas:**

| # | URL | Para qué |
|---|---|---|
| 1 | `http://localhost:3000` | La demo principal |
| 2 | `http://localhost:4200` | Consola de Prefect |
| 3 | `http://localhost:15672` | Consola de RabbitMQ (`guest`/`guest`) |
| 4 | Terminal | Saldos |

**5. Ensaya una vez entera.** El cronómetro es lo que más falla.

---

## Reparto del tiempo

El orden no es el numérico: **CP-05 va justo después de CP-01** para reutilizar
su clave de idempotencia, lo que ahorra media transferencia entera.

| Bloque | Duración | Criterio |
|---|---|---|
| Contexto y arquitectura | 0:30 | — |
| CP-01 camino feliz | 0:45 | Saga (40%) |
| CP-05 idempotencia | 0:20 | Microservicios (10%) |
| CP-02 fondos insuficientes | 0:25 | Saga (40%) |
| CP-03 fallo de riesgo | 0:45 | Saga (40%) |
| CP-04 timeout + Prefect | 1:10 | Saga (40%) + Observabilidad (15%) |
| Coreografía + RabbitMQ | 1:10 | Comparativa (20%) |
| Cierre | 0:25 | Documentación (5%) |
| **Total** | **5:30** | deja 30 s de margen |

---

## 0:00 – 0:30 · Contexto y arquitectura

**Muestra:** el `README.md` con el diagrama a la vista.

> "NovaBank procesa transferencias interbancarias y necesita abandonar los
> bloqueos globales de 2PC. Implementamos el Patrón Saga bajo el modelo BASE, en
> sus dos modalidades. Son ocho servicios: el Gateway, tres microservicios de
> dominio con datos aislados, la capa de Saga con sus dos implementaciones,
> RabbitMQ como bus de eventos y Prefect como motor de flujos."

No leas la lista de servicios: señálala en el diagrama.

---

## 0:30 – 1:15 · CP-01 · Camino feliz

**Muestra:** pestaña 1. Modalidad **Orquestación**, sin switches. Señala los
saldos del formulario antes de lanzar.

> "Transferencia normal: 50.000 pesos de ACC-001 a ACC-002."

Lanza y **narra mientras corre** (36 s):

> "El Gateway registró la transferencia y se la entregó a la Saga. El orquestador
> va paso a paso: debita origen, valida riesgo, ejecuta el clearing interbancario
> y acredita destino. Cada paso es una transacción local que se confirma de
> inmediato; no existe ninguna transacción global."

Al terminar: estado `CONFIRMADA` y saldos actualizados.

---

## 1:15 – 1:35 · CP-05 · Idempotencia

**No lances nada nuevo.** Usa el panel **Test Idempotencia** que acaba de
aparecer con la clave de CP-01.

> "Un cliente que reintenta enviaría la misma operación con la misma
> Idempotency-Key."

Pulsa **Reintentar con misma clave**.

> "Responde 200 con `replayed: true` y el mismo `transfer_id`. Ni segundo débito
> ni segundo cobro. Hay tres barreras: la clave en el Gateway, la deduplicación
> de eventos en la Saga y el `transfer_id` en cada microservicio."

---

## 1:35 – 2:00 · CP-02 · Fondos insuficientes

**Muestra:** cuenta origen **ACC-003**, importe muy superior al saldo. (13 s)

> "Un rechazo inicial: el débito falla por fondos insuficientes."

Al terminar, señala la línea de tiempo:

> "Esto es lo importante: los tres pasos siguientes quedan **omitidos** y no se
> ejecuta **ninguna compensación**. Compensar un débito que nunca ocurrió sería
> inventar dinero. Los saldos están intactos."

---

## 2:00 – 2:45 · CP-03 · Fallo de riesgo

**Muestra:** switch **"Forzar fallo de riesgo"**. Apunta los saldos antes. (28 s)

> "Aquí el débito sí ocurre, y después riesgo rechaza. El sistema queda
> temporalmente inconsistente: el dinero salió de origen y no llegó a ninguna
> parte. Ese es el *soft state* del modelo BASE."

Cuando pase a `COMPENSANDO`, detente ahí un segundo. Al terminar, baja al panel
de **Trazabilidad**:

> "El débito ejecutado, el riesgo fallido con su código `RISK_REJECTED`, los dos
> pasos omitidos y la compensación del débito. El saldo de origen volvió exacto."

---

## 2:45 – 3:55 · CP-04 · Timeout de clearing · **el bloque clave**

**Muestra:** switch **"Forzar timeout de clearing"**. (40 s)

> "El caso más exigente: falla el tercer paso después de haber ejecutado dos.
> Hay que revertir dos operaciones, y el orden importa."

Cuando empiece la compensación:

> "Se compensa primero el riesgo y **después** el débito: orden estrictamente
> inverso al flujo normal."

Baja a **Trazabilidad** y señala la caja **Orden de reversa**:

> "Secuencia 103 para la compensación de riesgo, 104 para la del débito.
> Ordenar por secuencia demuestra la reversa."

**Pestaña 2 (Prefect)** → *Runs* → último flow run → pestaña *Task Runs*:

> "El mismo flujo como tasks con nombre propio: DEBIT, RISK, CLEARING, y después
> compensate-RISK y compensate-DEBIT."

**Pestaña 4 (terminal):**

```bash
for a in ACC-001 ACC-002; do curl -s localhost:8001/accounts/$a; echo; done
```

> "Saldos íntegros. Consistencia eventual alcanzada."

---

## 3:55 – 5:05 · Coreografía

**Muestra:** pestaña 1, selector en **Coreografía**, switch de clearing. El mismo
CP-04. (34 s)

> "Ahora el mismo caso sin coordinador: cada servicio reacciona a eventos por su
> cuenta."

Mientras corre, salta a la **pestaña 3 (RabbitMQ)**:

> "Cinco colas, una por participante, sobre un exchange de tipo topic."

Vuelve y abre la **Bitácora de Auditoría**:

> "La cadena real de eventos: TransferRequested, BalanceDebited, RiskApproved,
> ClearingRequested, TransferFailed, y después RiskCompensationRequested,
> RiskCompensated, DebitCompensationRequested, DebitCompensated."

**Este es el punto técnico del video. Dilo despacio:**

> "Fíjate en el encadenamiento: la compensación del débito se pide **solo
> después** de que la del riesgo confirma. Sin coordinador, el orden inverso lo
> garantiza la causalidad entre eventos. Si el fallo emitiera las dos peticiones
> a la vez, se ejecutarían en paralelo y la reversa no estaría controlada."

---

## 5:05 – 5:30 · Cierre

**Muestra:** `docs/02-orquestacion-vs-coreografia.md`.

> "Las dos modalidades resuelven el mismo problema con los mismos cuatro pasos.
> En orquestación el flujo vive en un archivo y se lee de arriba abajo; en
> coreografía emerge de las suscripciones: sin punto único de fallo, pero más
> difícil de seguir. La comparación completa está en el repositorio, junto con la
> evidencia de los diez casos y las instrucciones de despliegue."

---

## Errores que arruinan la toma

| Error | Cómo evitarlo |
|---|---|
| ACC-001 sin fondos: CP-03 y CP-04 salen `RECHAZADA_FONDOS` | Ejecuta el ensayo previo, que la recarga |
| Delay en 3 s: no caben los casos | Graba con `SAGA_STEP_DELAY_SECONDS=2` |
| Lanzar CP-05 como transferencia nueva | Reutiliza la clave de CP-01: es instantáneo |
| Varios workers de coreografía levantados | `docker compose ps` — debe haber uno solo |
| Leer código en pantalla | Muestra comportamiento; el código ya está en el repositorio |
| Alargar la arquitectura más de 30 s | El 40% de la nota son las compensaciones, no el diagrama |
| Callarte mientras corre una saga | Los 2:30 de ejecución son tu tiempo de narración |
