"""Runs the choreography participants.

Deliberately a separate process from the orchestrator: in choreography there is
no coordinator to host, only participants listening to a bus. Each one gets its
own thread and its own broker connection, because a pika BlockingConnection is
not thread-safe.
"""

import logging
import threading
import time

from app.choreography.broker import EventBus
from app.choreography.participants import PARTICIPANTS, Participant
from app.core.logging import configure_logging
from app.persistence.repository import SagaRepository

logger = logging.getLogger(__name__)
_stop = threading.Event()


def _run_participant(name: str, queue: str, handler, repository: SagaRepository) -> None:
    while not _stop.is_set():
        bus = EventBus()
        try:
            participant = Participant(
                name=name, queue=queue, handler=handler, bus=bus, repository=repository
            )
            bus.consume(queue, participant.dispatch)
        except Exception:  # noqa: BLE001 - a participant reconnects instead of dying
            logger.exception("participant=%s lost its connection, retrying in 5s", name)
            time.sleep(5)
        finally:
            try:
                bus.close()
            except Exception:  # noqa: BLE001
                pass


def main() -> None:
    configure_logging()
    repository = SagaRepository()
    repository.initialize()

    # Declare exchange, queues and bindings once before anyone consumes.
    setup = EventBus()
    setup.declare_topology(setup._open())
    setup.close()

    threads = [
        threading.Thread(
            target=_run_participant,
            args=(name, queue, handler, repository),
            name=name,
            daemon=True,
        )
        for name, queue, handler in PARTICIPANTS
    ]
    for thread in threads:
        thread.start()
    logger.info(
        "service=choreography operation=start status=ready participants=%s",
        ",".join(name for name, _, _ in PARTICIPANTS),
    )

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        _stop.set()
        logger.info("service=choreography operation=stop status=shutting_down")


if __name__ == "__main__":
    main()
