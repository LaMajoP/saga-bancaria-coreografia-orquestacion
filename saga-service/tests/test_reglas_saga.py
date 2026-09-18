"""The rules the workshop grades hardest: reverse order and no phantom rollbacks."""

import pytest

from app.domain.errors import FailureKind, classify, outcome_for
from app.domain.states import GatewayStatus, SagaStatus, StepName, to_gateway_status
from app.domain.steps import STEPS, compensation_order, compensation_sequence


def nombres(steps):
    return [step.name.value for step in steps]


def test_el_flujo_normal_tiene_los_cuatro_pasos_en_orden():
    assert nombres(STEPS) == ["DEBIT", "RISK", "CLEARING", "CREDIT"]


def test_sin_pasos_ejecutados_no_se_compensa_nada():
    """CP-02: the debit never happened, so nothing may be reversed."""
    assert compensation_order([]) == []


def test_un_solo_paso_ejecutado_compensa_solo_ese():
    """CP-03: only the debit ran."""
    assert nombres(compensation_order([StepName.DEBIT])) == ["DEBIT"]


def test_dos_pasos_ejecutados_compensan_en_orden_inverso():
    """CP-04: risk is undone before the debit, never the other way round."""
    assert nombres(compensation_order([StepName.DEBIT, StepName.RISK])) == ["RISK", "DEBIT"]


def test_fallo_tardio_compensa_los_tres_en_orden_inverso():
    ejecutados = [StepName.DEBIT, StepName.RISK, StepName.CLEARING]
    assert nombres(compensation_order(ejecutados)) == ["CLEARING", "RISK", "DEBIT"]


def test_nunca_se_compensa_un_paso_que_no_se_ejecuto():
    """Even if clearing is claimed as executed, an absent risk is not reversed."""
    resultado = nombres(compensation_order([StepName.DEBIT, StepName.CLEARING]))
    assert "RISK" not in resultado
    assert resultado == ["CLEARING", "DEBIT"]


def test_la_numeracion_de_compensaciones_crece_en_orden_inverso():
    """Sorting the audit trail by sequence must show the rollback backwards."""
    por_nombre = {step.name: step for step in STEPS}
    secuencias = [
        compensation_sequence(por_nombre[nombre])
        for nombre in (StepName.CLEARING, StepName.RISK, StepName.DEBIT)
    ]
    assert secuencias == sorted(secuencias)


@pytest.mark.parametrize(
    "error_code, esperado",
    [
        ("INSUFFICIENT_FUNDS", SagaStatus.REJECTED_FUNDS),
        ("RISK_REJECTED", SagaStatus.REJECTED_RISK),
        ("RISK_LIMIT_EXCEEDED", SagaStatus.REJECTED_RISK),
        ("CLEARING_TIMEOUT", SagaStatus.REJECTED_NETWORK),
        ("SOMETHING_ELSE", SagaStatus.FAILED),
    ],
)
def test_cada_causa_de_fallo_tiene_su_estado_final(error_code, esperado):
    assert outcome_for(error_code) is esperado


def test_un_rechazo_de_negocio_no_se_reintenta():
    """Risk answers HTTP 200 with success=false: it is a decision, not a glitch."""
    assert classify(200, "RISK_REJECTED") is FailureKind.BUSINESS


def test_un_error_de_servidor_si_se_reintenta():
    assert classify(503, None) is FailureKind.TRANSIENT


def test_un_conflicto_de_integracion_no_se_reintenta():
    assert classify(409, "IDEMPOTENCY_CONFLICT") is FailureKind.INTEGRATION


@pytest.mark.parametrize(
    "interno, publico",
    [
        (SagaStatus.PENDING, GatewayStatus.IN_PROGRESS),
        (SagaStatus.DEBITED, GatewayStatus.IN_PROGRESS),
        (SagaStatus.COMPLETED, GatewayStatus.CONFIRMED),
        (SagaStatus.REJECTED_FUNDS, GatewayStatus.REJECTED_FUNDS),
        (SagaStatus.REJECTED_RISK, GatewayStatus.REJECTED_RISK),
        (SagaStatus.REJECTED_NETWORK, GatewayStatus.REJECTED_NETWORK),
        (SagaStatus.COMPENSATING, GatewayStatus.COMPENSATING),
        (SagaStatus.FAILED, GatewayStatus.FAILED),
    ],
)
def test_cada_estado_interno_se_traduce_al_vocabulario_del_gateway(interno, publico):
    assert to_gateway_status(interno) is publico


def test_todos_los_estados_internos_tienen_traduccion():
    for estado in SagaStatus:
        assert to_gateway_status(estado) in GatewayStatus
