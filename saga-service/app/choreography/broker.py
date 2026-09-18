"""RabbitMQ event bus for the choreographed saga.

There is no central coordinator here: the bus only carries events, and every
participant decides on its own what to do with the ones it subscribed to.
"""

from collections.abc import Callable
import logging
import time

import pika
from pika.exceptions import AMQPError

from app.choreography.events import TOPOLOGY, DomainEvent
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class EventBus:
    """A connection to the broker. Not thread-safe: use one per thread."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.exchange = self.settings.exchange
        self._connection: pika.BlockingConnection | None = None
        self._channel: pika.adapters.blocking_connection.BlockingChannel | None = None

    # ------------------------------------------------------------------ plumbing

    def _open(self):
        if self._channel is not None and self._channel.is_open:
            return self._channel
        parameters = pika.URLParameters(self.settings.broker_url)
        parameters.heartbeat = 60
        parameters.blocked_connection_timeout = 30
        self._connection = pika.BlockingConnection(parameters)
        self._channel = self._connection.channel()
        self.declare_topology(self._channel)
        return self._channel

    def declare_topology(self, channel) -> None:
        """Declare the exchange, the queues and their bindings. Idempotent."""
        channel.exchange_declare(
            exchange=self.exchange, exchange_type="topic", durable=True
        )
        for queue, routing_keys in TOPOLOGY.items():
            channel.queue_declare(queue=queue, durable=True)
            for routing_key in routing_keys:
                channel.queue_bind(
                    queue=queue, exchange=self.exchange, routing_key=routing_key
                )

    def close(self) -> None:
        if self._connection is not None and self._connection.is_open:
            self._connection.close()
        self._connection = None
        self._channel = None

    # ------------------------------------------------------------------ publish

    def publish(self, event: DomainEvent) -> None:
        """Publish an event persistently, retrying once on a dropped connection."""
        for attempt in (1, 2):
            try:
                channel = self._open()
                channel.basic_publish(
                    exchange=self.exchange,
                    routing_key=event.event_type.value,
                    body=event.to_json(),
                    properties=pika.BasicProperties(
                        delivery_mode=2,  # persist the event across broker restarts
                        content_type="application/json",
                        message_id=event.event_id,
                        correlation_id=event.transfer_id,
                    ),
                )
                logger.info(
                    "transfer_id=%s service=event-bus operation=publish status=success event=%s",
                    event.transfer_id,
                    event.event_type.value,
                )
                return
            except AMQPError as error:
                self.close()
                if attempt == 2:
                    logger.error(
                        "transfer_id=%s service=event-bus operation=publish status=failed event=%s error=%s",
                        event.transfer_id,
                        event.event_type.value,
                        error,
                    )
                    raise
                time.sleep(0.5)

    # ------------------------------------------------------------------ consume

    def consume(self, queue: str, handler: Callable[[DomainEvent], None]) -> None:
        """Consume forever. Acknowledges only after the handler returns."""
        channel = self._open()
        channel.basic_qos(prefetch_count=1)

        def _on_message(ch, method, properties, body) -> None:
            try:
                event = DomainEvent.from_json(body)
            except (ValueError, KeyError) as error:
                logger.error("queue=%s discarding malformed event: %s", queue, error)
                ch.basic_nack(method.delivery_tag, requeue=False)
                return
            try:
                handler(event)
            except Exception:  # noqa: BLE001 - a participant must not kill the bus
                logger.exception(
                    "transfer_id=%s queue=%s event=%s handler failed",
                    event.transfer_id,
                    queue,
                    event.event_type.value,
                )
                # Do not requeue: a poisoned event would loop forever. The saga
                # stays visible as unfinished in saga.executions instead.
                ch.basic_nack(method.delivery_tag, requeue=False)
                return
            ch.basic_ack(method.delivery_tag)

        channel.basic_consume(queue=queue, on_message_callback=_on_message)
        logger.info("service=event-bus operation=consume status=started queue=%s", queue)
        channel.start_consuming()
