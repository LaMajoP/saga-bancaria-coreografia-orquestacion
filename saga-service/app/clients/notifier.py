"""Publicacion del estado publico hacia el Gateway, fuera del camino critico.

El Gateway mantiene una *proyeccion* del estado de la transferencia: no decide
nada y no participa en la saga. Esperar su respuesta antes de seguir al paso
siguiente anadia entre uno y dos segundos por notificacion, y con cinco o seis
notificaciones por saga eso era casi un tercio del tiempo total.

Se envian desde un unico hilo: salen del camino critico pero conservan el orden,
de modo que el Gateway nunca ve un estado retroceder.
"""

from concurrent.futures import ThreadPoolExecutor
import logging

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gateway-notify")


def _enviar(gateway, transfer_id: str, status: str, error_code, message) -> None:
    try:
        gateway.notify_status(transfer_id, status, error_code, message)
    except Exception:  # noqa: BLE001 - perder una proyeccion no altera la saga
        logger.exception(
            "transfer_id=%s service=saga operation=status_notify status=failed", transfer_id
        )


def notify_async(
    gateway,
    transfer_id: str,
    status: str,
    error_code: str | None = None,
    message: str | None = None,
) -> None:
    _executor.submit(_enviar, gateway, transfer_id, status, error_code, message)


def flush(timeout: float = 15.0) -> None:
    """Espera a que se envien las notificaciones encoladas.

    El hilo unico garantiza orden FIFO, asi que basta con encolar un centinela
    y esperarlo: cuando le llega el turno, todo lo anterior ya salio. Se usa al
    cerrar una saga, para que el estado terminal llegue al Gateway antes de dar
    la ejecucion por terminada. Los estados intermedios siguen sin bloquear.
    """
    try:
        _executor.submit(lambda: None).result(timeout=timeout)
    except Exception:  # noqa: BLE001
        logger.warning("service=saga operation=status_flush status=timeout")
