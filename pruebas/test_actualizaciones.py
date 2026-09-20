# -*- coding: utf-8 -*-
"""Actualizarse por internet sin que la red sea un requisito para trabajar.

Ninguna prueba de aquí llama a GitHub. Depender de la red haría que la batería
fallara los días que la conexión va mal, y una prueba que falla por motivos que
no son el código deja de servir para nada: lo que se le pone delante es un
Velopack de mentira que contesta lo que cada caso necesita.
"""
from __future__ import annotations

from datetime import date

import pytest

from gestor import credenciales
from gestor.servicios import actualizaciones
from gestor.servicios.actualizaciones import MEMORIA_SEGUNDOS, Actualizaciones
from gestor.version import VERSION


class PaqueteFalso:
    def __init__(self, version):
        self.version = version


class InfoFalsa:
    def __init__(self, version, notas=''):
        self.target_full_release = PaqueteFalso(version)
        self.release_notes = notas


class GestorFalso:
    """Un Velopack de mentira: contesta lo que la prueba le diga."""

    def __init__(self, version_actual='4.0.0', novedad=None, revienta_al_comprobar=None):
        self.version_actual = version_actual
        self.novedad = novedad
        self.revienta_al_comprobar = revienta_al_comprobar
        self.descargas = []
        self.aplicadas = []

    def get_current_version(self):
        return self.version_actual

    def check_for_updates(self):
        if self.revienta_al_comprobar:
            raise self.revienta_al_comprobar
        return self.novedad

    def download_updates(self, info, al_avanzar=None):
        self.descargas.append(info)

    def apply_updates_and_restart(self, info):
        self.aplicadas.append(info)


class Reloj:
    def __init__(self):
        self.ahora = 0.0

    def __call__(self):
        return self.ahora

    def avanzar(self, segundos):
        self.ahora += segundos


def _permiso_bueno():
    """El de una instalación normal: permiso puesto y con un año por delante."""
    return credenciales.Permiso('ghp_de_mentira', credenciales.caducidad_por_defecto())


def _con(gestor, reloj=None, permiso=None):
    """Un servicio de actualizaciones con ese Velopack de mentira dentro.

    El permiso se le da hecho en vez de dejar que lo lea del disco: leyéndolo, la
    batería contestaría una cosa en la máquina de quien la ejecuta y otra en una
    instalación de verdad, que es lo mismo que no comprobar nada.
    """
    servicio = Actualizaciones(reloj=reloj,
                               permiso=permiso if permiso is not None else _permiso_bueno())
    servicio._gestor = gestor
    servicio._gestor_probado = True
    return servicio


# ------------------------------------------------- fuera de una instalación

def test_sin_instalador_se_dice_y_no_se_inventa_nada():
    """Correr el código a pelo, las pruebas, o el ejecutable suelto.

    Aquí Velopack no gobierna nada. Lo honesto es decirlo, no fingir que se
    puede actualizar ni tampoco callar.
    """
    servicio = _con(None)
    novedad = servicio.consultar()
    assert novedad.sin_instalador is True
    assert novedad.hay_novedad is False
    assert 'instalador' in novedad.motivo
    assert novedad.version_instalada == VERSION


def test_sin_instalador_descargar_e_instalar_se_niegan_con_motivo():
    servicio = _con(None)
    for accion in (servicio.descargar, servicio.instalar):
        with pytest.raises(RuntimeError) as fallo:
            accion()
        assert 'no puede actualizarse sola' in str(fallo.value)


# --------------------------------------------------------------- comprobar

def test_cuando_hay_version_nueva_se_ofrece_con_sus_notas():
    gestor = GestorFalso(novedad=InfoFalsa('4.1.0', 'Correcciones varias.'))
    novedad = _con(gestor).consultar()
    assert novedad.hay_novedad is True
    assert novedad.version_publicada == '4.1.0'
    assert novedad.notas == 'Correcciones varias.'
    assert novedad.sin_instalador is False


def test_cuando_no_hay_nada_nuevo_se_dice_sin_alarmar():
    novedad = _con(GestorFalso(novedad=None)).consultar()
    assert novedad.hay_novedad is False
    assert 'última versión' in novedad.motivo


def test_sin_internet_la_aplicacion_no_se_entera():
    """Lo más importante de todo el módulo.

    Un PC de oficina sin internet, detrás de un proxy o con GitHub caído tiene
    que abrir y trabajar exactamente igual. Comprobar si hay versión nueva es
    una comodidad, no un requisito.
    """
    gestor = GestorFalso(revienta_al_comprobar=OSError('la red no responde'))
    novedad = _con(gestor).consultar()
    assert novedad.hay_novedad is False
    assert 'No se pudo comprobar' in novedad.motivo
    assert novedad.version_instalada, 'aun sin red se sabe qué versión hay puesta'


def test_la_version_instalada_la_dice_el_instalador_y_no_el_codigo():
    """Después de actualizar, el código nuevo y la carpeta activa coinciden.

    Preguntárselo a Velopack y no a la constante del módulo es lo que evita el
    caso más confuso: que la aplicación anuncie una versión distinta de la que
    de verdad está corriendo.
    """
    servicio = _con(GestorFalso(version_actual='4.2.0'))
    assert servicio.version_en_uso() == '4.2.0'


# ---------------------------------------------------------------- la cuota

def test_no_se_le_pregunta_a_github_en_cada_arranque():
    """La API sin credenciales tiene cuota y gastarla no aporta nada."""
    reloj = Reloj()
    gestor = GestorFalso(novedad=InfoFalsa('4.1.0'))
    consultas = []
    original = gestor.check_for_updates

    def contar():
        consultas.append(1)
        return original()

    gestor.check_for_updates = contar
    servicio = _con(gestor, reloj)

    servicio.consultar()
    servicio.consultar()
    servicio.consultar()
    assert len(consultas) == 1, 'se preguntó más de una vez en la misma sesión'

    servicio.consultar(forzar=True)
    assert len(consultas) == 2, 'al forzar sí tiene que volver a preguntar'

    reloj.avanzar(MEMORIA_SEGUNDOS + 1)
    servicio.consultar()
    assert len(consultas) == 3, 'pasadas las horas de memoria, vuelve a preguntar'


# ------------------------------------------------- descargar e instalar

def test_descargar_deja_la_version_lista_pero_no_la_instala():
    """Los pasos no se encadenan solos: instalar lo pide una persona."""
    gestor = GestorFalso(novedad=InfoFalsa('4.1.0'))
    servicio = _con(gestor)
    resultado = servicio.descargar()

    assert resultado['ok'] and resultado['version'] == '4.1.0'
    assert len(gestor.descargas) == 1
    assert gestor.aplicadas == [], 'descargar no puede instalar por su cuenta'


def test_descargar_sin_novedad_se_explica_en_vez_de_fallar_seco():
    with pytest.raises(RuntimeError) as fallo:
        _con(GestorFalso(novedad=None)).descargar()
    assert 'No hay ninguna versión nueva' in str(fallo.value)


def test_instalar_aplica_lo_descargado():
    gestor = GestorFalso(novedad=InfoFalsa('4.1.0'))
    servicio = _con(gestor)
    servicio.descargar()
    servicio.instalar()
    assert len(gestor.aplicadas) == 1


def test_se_puede_instalar_sin_haber_descargado_antes_desde_la_misma_sesion():
    """Quien pulsa «instalar» tras reabrir la aplicación no debería repetir todo."""
    gestor = GestorFalso(novedad=InfoFalsa('4.1.0'))
    servicio = _con(gestor)
    servicio.instalar()
    assert len(gestor.aplicadas) == 1


def test_instalar_sin_nada_publicado_se_explica():
    with pytest.raises(RuntimeError) as fallo:
        _con(GestorFalso(novedad=None)).instalar()
    assert 'descargada' in str(fallo.value)


# ------------------------------------------------------------ la pantalla

def test_lo_que_viaja_a_la_pantalla_es_serializable_y_completo():
    novedad = _con(GestorFalso(novedad=InfoFalsa('4.1.0'))).consultar()
    datos = novedad.como_dict()
    import json
    json.dumps(datos)
    for clave in ('version_instalada', 'hay_novedad', 'version_publicada',
                  'motivo', 'notas', 'descargada', 'sin_instalador', 'avisos'):
        assert clave in datos, clave


# ------------------------------------------------- el permiso del privado

def test_con_el_repositorio_publico_no_hace_falta_ningun_permiso(monkeypatch):
    """Con el interruptor en público: cualquiera pregunta y la respuesta es real.

    Hoy el repositorio es **privado** —el instalador que se publicaba en sus
    Releases llevaba dentro la plantilla de la oficina—, así que este caso se
    fuerza en vez de darse solo. Se conserva porque el interruptor existe y los
    dos lados tienen que seguir funcionando: el día que la nómina deje de viajar
    dentro del paquete, volver a público es cambiar una línea.
    """
    monkeypatch.setattr(actualizaciones, 'REPOSITORIO_PRIVADO', False)
    novedad = _con(GestorFalso(novedad=None),
                   permiso=credenciales.Permiso()).consultar()
    assert novedad.hay_novedad is False
    assert 'última versión' in novedad.motivo
    assert novedad.avisos == []


def test_si_el_repositorio_fuera_privado_no_se_diria_que_ya_se_tiene_la_ultima(
        monkeypatch):
    """La forma en que esto fallaría en silencio, y por eso sigue comprobada.

    Con el repositorio privado y sin permiso, GitHub no contesta «no tienes
    acceso»: contesta que ese repositorio no existe, igual que si estuviera
    vacío. Velopack lo traduce a «no hay ninguna versión nueva», que es
    literalmente la respuesta de que todo va bien.

    Una instalación así se quedaría diciendo para siempre que está al día
    mientras se publican versiones una detrás de otra, y nadie tendría por qué
    sospechar nada. Hoy el repositorio es público y esto no puede pasar; la
    prueba se queda porque el interruptor está ahí para poder cambiarlo.
    """
    monkeypatch.setattr(actualizaciones, 'REPOSITORIO_PRIVADO', True)
    novedad = _con(GestorFalso(novedad=None),
                   permiso=credenciales.Permiso()).consultar()
    assert novedad.hay_novedad is False
    assert 'última versión' not in novedad.motivo
    assert 'permiso' in novedad.motivo


def test_con_el_permiso_caducado_ni_se_pregunta(monkeypatch):
    """Un permiso caducado contesta lo mismo que uno que falta: nada."""
    monkeypatch.setattr(actualizaciones, 'REPOSITORIO_PRIVADO', True)
    caducado = credenciales.Permiso('ghp_de_mentira', '2020-01-01')
    gestor = GestorFalso(novedad=InfoFalsa('4.1.0'))
    novedad = _con(gestor, permiso=caducado).consultar()
    assert novedad.hay_novedad is False
    assert 'caducó' in novedad.motivo


def test_se_avisa_antes_de_que_el_permiso_caduque_aunque_todo_vaya_bien():
    """El aviso va aparte del motivo, y este es el caso que obliga a ello.

    Cuando no hay versión nueva el motivo dice «tienes la última versión», que es
    exactamente cuando nadie mira más. Si el aviso de caducidad viviera ahí,
    desaparecería justo en el momento en que hace falta leerlo.
    """
    from datetime import date, timedelta
    pronto = credenciales.Permiso(
        'ghp_de_mentira', (date.today() + timedelta(days=5)).isoformat())
    novedad = _con(GestorFalso(novedad=None), permiso=pronto).consultar()
    assert 'última versión' in novedad.motivo
    assert novedad.avisos and 'caduca en 5 días' in novedad.avisos[0]


def test_un_permiso_con_meses_por_delante_no_molesta_a_nadie():
    novedad = _con(GestorFalso(novedad=None)).consultar()
    assert novedad.avisos == []


def test_el_aviso_de_caducidad_llega_a_la_pantalla():
    """Sale en `como_dict`, que es lo único que la pantalla lee."""
    from datetime import date, timedelta
    pronto = credenciales.Permiso(
        'ghp_de_mentira', (date.today() + timedelta(days=1)).isoformat())
    dicho = _con(GestorFalso(novedad=None), permiso=pronto).consultar().como_dict()
    assert dicho['avisos'] and 'mañana' in dicho['avisos'][0]


# --------------------------------------------------- leer y escribir el permiso

def test_un_permiso_que_no_existe_no_revienta_nada(tmp_path):
    """Es el caso de todos los días: en desarrollo no hay archivo ninguno."""
    permiso = credenciales.Permiso.leer(tmp_path / 'no_existe.json')
    assert not permiso
    assert permiso.aviso() == ''
    assert permiso.caducado() is False


def test_un_permiso_ilegible_se_trata_como_ausente(tmp_path):
    """Medio archivo escrito, un disco lleno, alguien que lo editó a mano."""
    roto = tmp_path / 'permiso.json'
    roto.write_text('{esto no es json', encoding='utf-8')
    assert not credenciales.Permiso.leer(roto)


def test_lo_que_escribe_el_empaquetado_es_lo_que_lee_el_programa(tmp_path):
    archivo = tmp_path / 'permiso.json'
    credenciales.Permiso.escribir('ghp_algo', '2027-01-15', archivo)
    leido = credenciales.Permiso.leer(archivo)
    assert leido.token == 'ghp_algo'
    assert leido.caduca == '2027-01-15'
    assert leido.dias_que_le_quedan(date(2027, 1, 5)) == 10


def test_una_fecha_de_caducidad_inventada_se_rechaza_al_escribirla(tmp_path):
    """Que reviente al construir y no dentro de un año, sin nadie mirando."""
    with pytest.raises(ValueError):
        credenciales.Permiso.escribir('ghp_algo', '15/01/2027', tmp_path / 'p.json')


def test_la_caducidad_por_defecto_no_pasa_del_año_que_github_permite():
    from datetime import date as fecha
    puesta = fecha.fromisoformat(credenciales.caducidad_por_defecto(fecha(2026, 1, 1)))
    assert (puesta - fecha(2026, 1, 1)).days <= 365
