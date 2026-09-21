"""El recuerdo es opcional, aislado y nunca recurre a un archivo legible."""
import sys
import uuid

import pytest

from gestor.servicios import claves_locales as claves


def test_ambito_aisla_cuentas_y_carpetas(tmp_path, monkeypatch):
    monkeypatch.setattr(claves.rutas, 'RAIZ_DATOS', tmp_path / 'uno')
    uno = claves._destino('admin')
    assert uno != claves._destino('usuario')
    monkeypatch.setattr(claves.rutas, 'RAIZ_DATOS', tmp_path / 'dos')
    assert uno != claves._destino('admin')


def test_error_del_almacen_no_impide_entrar(tmp_path, monkeypatch):
    monkeypatch.setattr(claves.rutas, 'RAIZ_DATOS', tmp_path)

    def inaccesible():
        raise OSError('El almacén no está disponible.')

    monkeypatch.setattr(claves, '_sistema', inaccesible)
    assert claves.guardar('admin', 'privada')['ok'] is False
    assert claves.leer('admin')['ok'] is False
    assert claves.olvidar('admin')['ok'] is False
    assert not list(tmp_path.iterdir())


@pytest.mark.skipif(sys.platform != 'win32', reason='Necesita el almacén real de Windows')
def test_guardar_leer_y_borrar_en_windows(tmp_path, monkeypatch):
    monkeypatch.setattr(claves.rutas, 'RAIZ_DATOS', tmp_path)
    cuenta = 'qa-' + uuid.uuid4().hex
    try:
        assert claves.guardar(cuenta, 'Prueba-á-934!')['ok']
        assert claves.leer(cuenta)['password'] == 'Prueba-á-934!'
        assert claves.olvidar(cuenta)['ok']
        assert claves.leer(cuenta) == {'ok': True, 'recordada': False}
    finally:
        claves.olvidar(cuenta)
