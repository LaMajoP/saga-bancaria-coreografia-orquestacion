"""The five cases against the choreographed saga, with an in-memory bus.

RabbitMQ is replaced by a list, which is enough: what matters is which event
each participant publishes when, because that causal chain is what enforces
reverse order when no coordinator exists.
"""

import pytest

import app.choreography.participants as participantes
from app.choreography.events import TOPOLOGY, DomainEvent, EventType
from app.choreography.participants import PARTICIPANTS, Participant, context_payload
from app.domain.states import CompensationStatus, Implementation, SagaStatus
from app.orchestration.context import SagaContext
from tests.conftest import FakeAccounts, FakeClearing, FakeGateway, FakeRisk, business_failure


class BusEnMemoria:
    """Collects published events instead of sending them to a broker."""

    def __init__(self) -> None:
        self.publicados: list[DomainEvent] = []

    def publish(self, event: DomainEvent) -> None:
        self.publicados.append(event)


def _suscrita(cola: str, tipo: EventType) -> bool:
    claves = TOPOLOGY[cola]
    return "#" in claves or tipo.value in claves


@pytest.fixture
def coreografia(settings, repository, transfer_request, monkeypatch):
    """Returns a runner that drives the whole choreography and reports the chain."""
    clientes = {
        "accounts": FakeAccounts(),
        "risk": FakeRisk(),
        "clearing": FakeClearing(),
        "gateway": FakeGateway(),
    }

    def fabrica_de_contexto(request, repository=None):
        return SagaContext(request=request, repository=repository, settings=settings, **clientes)

    monkeypatch.setattr(participantes, "SagaContext", fabrica_de_contexto)

    def correr() -> list[str]:
        bus = BusEnMemoria()
        equipo = [
            Participant(name=n, queue=q, handler=h, bus=bus, repository=repository)
            for n, q, h in PARTICIPANTS
        ]
        repository.start_execution(
            transfer_id=transfer_request.transfer_id,
            implementation=Implementation.CHOREOGRAPHY,
            source_account_id=transfer_request.source_account_id,
            destination_account_id=transfer_request.destination_account_id,
            amount=transfer_request.amount,
        )
        pendientes = [
            DomainEvent(
                event_type=EventType.TRANSFER_REQUESTED,
                transfer_id=transfer_request.transfer_id,
                payload=context_payload(transfer_request),
            )
        ]
        cadena: list[str] = []
        while pendientes and len(cadena) < 40:
            evento = pendientes.pop(0)
            cadena.append(evento.event_type.value)
            ya_publicados = len(bus.publicados)
            for participante in equipo:
                if _suscrita(participante.queue, evento.event_type):
                    participante.dispatch(evento)
            pendientes.extend(bus.publicados[ya_publicados:])
        return cadena

    correr.clientes = clientes
    correr.bus_equipo = None
    return correr


def test_cp01_la_cadena_de_eventos_del_camino_feliz(coreografia, repository, transfer_request):
    cadena = coreografia()

    assert cadena == [
        "TransferRequested",
        "BalanceDebited",
        "RiskApproved",
        "ClearingRequested",
        "ClearingCompleted",
        "TransferCompleted",
    ]
    ejecucion = repository.get_execution(transfer_request.transfer_id)
    assert ejecucion.status is SagaStatus.COMPLETED
    assert ejecucion.compensation_status is CompensationStatus.NOT_REQUIRED
    assert repository.compensations(transfer_request.transfer_id) == []


def test_cp02_fondos_insuficientes_termina_sin_compensar(coreografia, repository, transfer_request):
    coreografia.clientes["accounts"].debit_outcome = business_failure(
        "INSUFFICIENT_FUNDS", "REJECTED_FUNDS"
    )

    cadena = coreografia()

    assert cadena == ["TransferRequested", "TransferFailed"]
    ejecucion = repository.get_execution(transfer_request.transfer_id)
    assert ejecucion.status is SagaStatus.REJECTED_FUNDS
    assert ejecucion.compensation_status is CompensationStatus.NOT_REQUIRED
    assert repository.compensations(transfer_request.transfer_id) == []
    assert coreografia.clientes["risk"].calls == []
    assert coreografia.clientes["clearing"].calls == []


def test_cp03_el_rechazo_de_riesgo_desencadena_la_reversa_del_debito(
    coreografia, repository, transfer_request
):
    coreografia.clientes["risk"].check_outcome = business_failure("RISK_REJECTED", "RISK_REJECTED")

    cadena = coreografia()

    assert "RiskRejected" in cadena
    assert "DebitCompensationRequested" in cadena
    assert cadena.index("RiskRejected") < cadena.index("DebitCompensationRequested")
    assert cadena[-1] == "TransferCompensated" or "TransferCompensated" in cadena
    assert repository.compensations(transfer_request.transfer_id) == ["DEBIT"]

    ejecucion = repository.get_execution(transfer_request.transfer_id)
    assert ejecucion.status is SagaStatus.REJECTED_RISK
    assert ejecucion.compensation_status is CompensationStatus.COMPENSATED


def test_cp04_la_reversa_se_encadena_y_respeta_el_orden_inverso(
    coreografia, repository, transfer_request
):
    coreografia.clientes["clearing"].transfer_outcome = business_failure(
        "CLEARING_TIMEOUT", "REJECTED_NETWORK"
    )

    cadena = coreografia()

    # Without a coordinator, the order is guaranteed by causality: the debit
    # rollback is only requested *after* the risk rollback confirms.
    assert cadena.index("RiskCompensationRequested") < cadena.index("RiskCompensated")
    assert cadena.index("RiskCompensated") < cadena.index("DebitCompensationRequested")
    assert cadena.index("DebitCompensationRequested") < cadena.index("DebitCompensated")
    assert repository.compensations(transfer_request.transfer_id) == ["RISK", "DEBIT"]

    ejecucion = repository.get_execution(transfer_request.transfer_id)
    assert ejecucion.status is SagaStatus.REJECTED_NETWORK
    assert ejecucion.compensation_status is CompensationStatus.COMPENSATED


def test_fallo_tardio_del_credito_revierte_desde_el_clearing(
    coreografia, repository, transfer_request
):
    coreografia.clientes["accounts"].credit_outcome = business_failure("LEDGER_UNAVAILABLE")

    cadena = coreografia()

    assert "ClearingCompensationRequested" in cadena
    assert repository.compensations(transfer_request.transfer_id) == ["CLEARING", "RISK", "DEBIT"]


def test_cp05_un_evento_reentregado_no_produce_un_segundo_efecto(
    settings, repository, transfer_request, monkeypatch
):
    """RabbitMQ delivers at least once; the effect must happen exactly once."""
    clientes = {
        "accounts": FakeAccounts(),
        "risk": FakeRisk(),
        "clearing": FakeClearing(),
        "gateway": FakeGateway(),
    }
    monkeypatch.setattr(
        participantes,
        "SagaContext",
        lambda request, repository=None: SagaContext(
            request=request, repository=repository, settings=settings, **clientes
        ),
    )
    bus = BusEnMemoria()
    cuenta = Participant(
        name="account-participant",
        queue="saga.account",
        handler=participantes.account_handler,
        bus=bus,
        repository=repository,
    )
    repository.start_execution(
        transfer_id=transfer_request.transfer_id,
        implementation=Implementation.CHOREOGRAPHY,
        source_account_id=transfer_request.source_account_id,
        destination_account_id=transfer_request.destination_account_id,
        amount=transfer_request.amount,
    )
    evento = DomainEvent(
        event_type=EventType.TRANSFER_REQUESTED,
        transfer_id=transfer_request.transfer_id,
        payload=context_payload(transfer_request),
    )

    cuenta.dispatch(evento)
    cuenta.dispatch(evento)  # exact redelivery, same event_id

    assert clientes["accounts"].calls == ["debit"]
    assert len(bus.publicados) == 1


def test_cada_participante_procesa_el_evento_por_su_cuenta(
    settings, repository, transfer_request, monkeypatch
):
    """Deduplication is per consumer: risk must still see what account saw."""
    monkeypatch.setattr(
        participantes,
        "SagaContext",
        lambda request, repository=None: SagaContext(
            request=request,
            repository=repository,
            settings=settings,
            accounts=FakeAccounts(),
            risk=FakeRisk(),
            clearing=FakeClearing(),
            gateway=FakeGateway(),
        ),
    )
    evento = DomainEvent(
        event_type=EventType.TRANSFER_REQUESTED,
        transfer_id=transfer_request.transfer_id,
        payload=context_payload(transfer_request),
    )

    assert repository.claim_event("account-participant", evento.event_id, evento.transfer_id)
    assert repository.claim_event("event-audit", evento.event_id, evento.transfer_id)
    assert not repository.claim_event("account-participant", evento.event_id, evento.transfer_id)
