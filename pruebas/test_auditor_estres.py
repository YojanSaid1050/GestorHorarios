"""El auditor no debe dar por histórico cualquier ajuste bloqueado."""
from pruebas.auditor import _es_heredado


def test_bloqueado_no_significa_historico():
    assert not _es_heredado({'bloqueado': True, 'origen': 'ajuste_manual'})
    assert _es_heredado({'origen': 'base_septiembre_2026'})
    assert _es_heredado({'heredado': True, 'origen': 'turno_base'})
    assert not _es_heredado({'origen': 'base_septiembre_2026'}, {'origen': 'turno_base'})
