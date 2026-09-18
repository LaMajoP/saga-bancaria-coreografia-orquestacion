"""The five mandatory cases against the central coordinator, offline."""

from app.domain.states import CompensationStatus, SagaStatus
from app.orchestration.coordinator import execute_saga, run_orchestrated_saga
from tests.conftest import business_failure


def test_cp01_camino_feliz(context):
    resultado = execute_saga(context)

    assert resultado.status is SagaStatus.COMPLETED
    assert resultado.compensation_status is CompensationStatus.NOT_REQUIRED
    assert context.accounts.calls == ["debit", "credit"]
    assert context.risk.calls == ["check"]
    assert context.clearing.calls == ["transfer"]
    assert context.repository.compensations(context.transfer_id) == []
    assert ("CONFIRMADA", None) in context.gateway.notifications


def test_cp02_fondos_insuficientes_no_compensa_nada(context):
    context.accounts.debit_outcome = business_failure("INSUFFICIENT_FUNDS", "REJECTED_FUNDS")

    resultado = execute_saga(context)

    assert resultado.status is SagaStatus.REJECTED_FUNDS
    # The critical assertion: compensating a debit that never happened would
    # invent money out of nothing.
    assert resultado.compensation_status is CompensationStatus.NOT_REQUIRED
    assert context.accounts.calls == ["debit"]
    assert context.risk.calls == []
    assert context.clearing.calls == []
    assert context.repository.compensations(context.transfer_id) == []


def test_cp03_fallo_de_riesgo_revierte_el_debito(context):
    context.risk.check_outcome = business_failure("RISK_REJECTED", "RISK_REJECTED")

    resultado = execute_saga(context)

    assert resultado.status is SagaStatus.REJECTED_RISK
    assert resultado.compensation_status is CompensationStatus.COMPENSATED
    assert context.repository.compensations(context.transfer_id) == ["DEBIT"]
    assert context.accounts.calls == ["debit", "compensate_debit"]
    assert context.clearing.calls == []


def test_cp04_timeout_de_clearing_compensa_en_orden_inverso(context):
    context.clearing.transfer_outcome = business_failure("CLEARING_TIMEOUT", "REJECTED_NETWORK")

    resultado = execute_saga(context)

    assert resultado.status is SagaStatus.REJECTED_NETWORK
    assert resultado.compensation_status is CompensationStatus.COMPENSATED
    # Risk first, debit second. The opposite order would be graded as a failure.
    assert context.repository.compensations(context.transfer_id) == ["RISK", "DEBIT"]
    assert resultado.compensated == ["RISK", "DEBIT"] or [
        name.value for name in resultado.compensated
    ] == ["RISK", "DEBIT"]


def test_fallo_tardio_en_el_credito_compensa_los_tres_pasos(context):
    """Not reachable from the UI switches, so the unit test is the only proof."""
    context.accounts.credit_outcome = business_failure("LEDGER_UNAVAILABLE")

    resultado = execute_saga(context)

    assert resultado.status is SagaStatus.FAILED
    assert context.repository.compensations(context.transfer_id) == [
        "CLEARING",
        "RISK",
        "DEBIT",
    ]


def test_cp05_reintentar_una_saga_terminada_no_ejecuta_nada(context, transfer_request):
    primera = run_orchestrated_saga(transfer_request, context=context)
    llamadas_tras_la_primera = list(context.accounts.calls)

    segunda = run_orchestrated_saga(transfer_request, context=context)

    assert primera.status is SagaStatus.COMPLETED
    assert segunda.status is SagaStatus.COMPLETED
    assert segunda.replayed is True
    # No second debit, no second credit: no double charge.
    assert context.accounts.calls == llamadas_tras_la_primera


def test_una_compensacion_fallida_queda_visible_y_no_se_da_por_hecha(context):
    context.risk.check_outcome = business_failure("RISK_REJECTED", "RISK_REJECTED")
    context.accounts.compensate_outcome = business_failure("LEDGER_LOCKED")

    resultado = execute_saga(context)

    assert resultado.status is SagaStatus.REJECTED_RISK
    assert resultado.compensation_status is CompensationStatus.COMPENSATION_FAILED
    assert resultado.compensated == []


def test_el_gateway_ve_compensando_antes_del_rechazo_definitivo(context):
    """Persona 3 needs that intermediate state to show the rollback live."""
    context.clearing.transfer_outcome = business_failure("CLEARING_TIMEOUT", "REJECTED_NETWORK")

    execute_saga(context)

    estados = [estado for estado, _ in context.gateway.notifications]
    assert "COMPENSANDO" in estados
    assert estados.index("COMPENSANDO") < estados.index("RECHAZADA_RED")
