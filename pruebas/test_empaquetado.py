# -*- coding: utf-8 -*-
"""El instalador y el arranque: que lo que llamamos exista de verdad.

Estas pruebas existen por un fallo concreto que ya se coló una vez y que ninguna
otra prueba habría cogido: el código llamaba a `VelopackApp`, que en la librería
instalada **no existe** —se llama `App`—, y el `except ImportError` que estaba
puesto para poder trabajar sin Velopack se lo tragaba en silencio. Resultado:
todo en verde, y una instalación en Windows en la que los enlaces no se crean,
la actualización no se aplica y la desinstalación no pregunta nada.

De ahí la regla: **de una dependencia externa se comprueba la forma, no el
comportamiento**. No se llama a GitHub ni se instala nada; solo se comprueba que
las clases y los métodos que este programa usa son los que la librería trae.

El resto vigila que el número de versión siga viviendo en un solo sitio.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from gestor import version

RAIZ = Path(__file__).resolve().parents[1]
velopack = pytest.importorskip('velopack', reason='Velopack solo hace falta en Windows')


# ------------------------------------------------- la forma de Velopack

def test_existe_lo_que_usa_el_arranque():
    """`App`, con los tres métodos que `principal.py` llama."""
    App = velopack.App
    for metodo in ('run', 'set_auto_apply_on_startup',
                   'on_before_uninstall_fast_callback'):
        assert hasattr(App, metodo), f'velopack.App no tiene {metodo}'


def test_el_gancho_de_desinstalar_se_registra_llamándolo():
    """Es un método, no un atributo. Asignarlo da «read-only» y no hace nada."""
    aplicacion = velopack.App()
    aplicacion.set_auto_apply_on_startup(False)
    aplicacion.on_before_uninstall_fast_callback(lambda _version: None)


def test_existe_lo_que_usan_las_actualizaciones():
    for metodo in ('check_for_updates', 'download_updates',
                   'apply_updates_and_restart', 'get_current_version'):
        assert hasattr(velopack.UpdateManager, metodo), (
            f'velopack.UpdateManager no tiene {metodo}')
    assert hasattr(velopack, 'GithubSource')


def test_el_arranque_no_se_traga_un_nombre_equivocado():
    """Que el módulo nombre lo que existe, y no algo que el `except` esconda."""
    codigo = (RAIZ / 'gestor' / 'principal.py').read_text(encoding='utf-8')
    assert 'VelopackApp' not in codigo, (
        'ese nombre no existe en la librería: el ImportError lo escondería')
    assert 'from velopack import App' in codigo


# ----------------------------------------------- la versión, en un sitio

def test_la_versión_tiene_tres_números():
    assert re.fullmatch(r'\d+\.\d+\.\d+', version.VERSION), version.VERSION
    assert version.numeros() == tuple(int(x) for x in version.VERSION.split('.'))


def test_nadie_más_escribe_la_versión_a_mano():
    """Ocho copias del número fue lo que dejó al instalador anunciando otra.

    Se busca el número exacto de esta versión en el código y en el empaquetado.
    Solo puede estar en `version.py`; los demás la leen de ahí.
    """
    sospechosos = []
    for archivo in list((RAIZ / 'gestor').rglob('*.py')) + \
            list((RAIZ / 'empaquetado').rglob('*.py')) + \
            list((RAIZ / 'empaquetado').rglob('*.spec')):
        if archivo.name == 'version.py':
            continue
        if version.VERSION in archivo.read_text(encoding='utf-8'):
            sospechosos.append(str(archivo.relative_to(RAIZ)))
    assert not sospechosos, (
        'la versión está escrita a mano en: ' + ', '.join(sospechosos))


# --------------------------------------------- la receta de empaquetado

def test_la_receta_mete_la_pantalla_y_los_datos_iniciales():
    """Sin ellos el programa instalado abre en blanco o arranca vacío."""
    receta = (RAIZ / 'empaquetado' / 'gestor.spec').read_text(encoding='utf-8')
    assert "'gestor/pantalla'" in receta
    assert "'datos_iniciales'" in receta


def test_la_receta_es_de_carpeta_y_no_de_archivo_único():
    """Velopack no puede reemplazar por partes lo que viaja en un solo bloque."""
    receta = (RAIZ / 'empaquetado' / 'gestor.spec').read_text(encoding='utf-8')
    assert 'COLLECT(' in receta
    assert 'exclude_binaries=True' in receta


def test_uvicorn_viaja_con_las_piezas_que_carga_por_nombre():
    """El analizador estático no las ve: sin lista, el .exe falla al arrancar."""
    receta = (RAIZ / 'empaquetado' / 'gestor.spec').read_text(encoding='utf-8')
    for pieza in ('uvicorn.loops.auto', 'uvicorn.protocols.http.auto',
                  'uvicorn.lifespan.on'):
        assert pieza in receta, f'falta {pieza} en hiddenimports'


# ---------------------------------------------------- la desinstalación

def test_al_desinstalar_no_borra_nada_sin_un_sí_expreso(monkeypatch, carpeta_de_datos):
    """Conservar de más es un fastidio; borrar de más es irreparable."""
    from gestor import desinstalacion, rutas

    rutas.preparar()
    rutas.BASE_DE_DATOS.write_bytes(b'datos de la oficina')
    monkeypatch.setattr(desinstalacion, '_preguntar', lambda *_: False)

    desinstalacion.al_desinstalar()
    assert rutas.BASE_DE_DATOS.is_file(), 'un «no» tiene que conservarlo todo'


def test_una_desinstalación_silenciosa_nunca_borra(monkeypatch, carpeta_de_datos):
    """No hay nadie delante a quien preguntar, así que no se decide por él."""
    import sys

    from gestor import desinstalacion, rutas

    rutas.preparar()
    rutas.BASE_DE_DATOS.write_bytes(b'datos de la oficina')
    monkeypatch.setattr(sys, 'argv', ['GestorHorarios.exe', '/SILENT'])
    monkeypatch.setattr(desinstalacion, '_preguntar',
                        lambda *_: pytest.fail('no debería preguntar'))

    desinstalacion.al_desinstalar()
    assert rutas.BASE_DE_DATOS.is_file()


def test_si_no_se_puede_preguntar_se_conserva():
    """Fuera de Windows no hay diálogo, y eso significa «no», nunca «sí»."""
    from gestor import desinstalacion

    assert desinstalacion._preguntar('¿?', 'Título') is False


# ------------------------------------------------------------- el icono

def test_el_icono_del_programa_existe_y_es_el_de_la_aplicación():
    """El mismo logo que se ve en la pestaña del navegador.

    No es un adorno: es cómo la gente reconoce el programa en la barra de
    tareas. Si falta, el .exe sale con el icono genérico de Python y en un
    escritorio con quince ventanas abiertas no se distingue de nada.
    """
    icono = RAIZ / 'empaquetado' / 'icono.ico'
    assert icono.is_file(), 'falta empaquetado/icono.ico'
    assert icono.stat().st_size > 5000, 'el icono parece vacío o truncado'


def test_el_icono_trae_todos_los_tamaños_que_windows_pide():
    """Windows elige uno según dónde lo enseñe, y escala él lo que no encuentra.

    Con un solo tamaño dentro, el icono se ve borroso en todos los demás sitios.
    """
    imagen = pytest.importorskip('PIL.Image', reason='Pillow solo hace falta aquí')
    tamaños = set(imagen.open(RAIZ / 'empaquetado' / 'icono.ico').info.get('sizes', []))
    for lado in (16, 32, 48, 256):
        assert (lado, lado) in tamaños, f'al icono le falta el tamaño {lado}×{lado}'


def test_la_receta_apunta_al_icono():
    receta = (RAIZ / 'empaquetado' / 'gestor.spec').read_text(encoding='utf-8')
    assert 'icono.ico' in receta


def test_el_nombre_del_ejecutable_depende_del_sistema():
    """Estaba escrito con el `.exe` a mano.

    Al construir fuera de Windows —que es como se valida la receta antes de
    gastar una vuelta en la máquina buena— la compilación terminaba bien y el
    script decía que había fallado.
    """
    import sys

    sys.path.insert(0, str(RAIZ / 'empaquetado'))
    from construir import nombre_del_ejecutable

    nombre = nombre_del_ejecutable()
    assert nombre.startswith(version.ID_APLICACION)
    assert nombre.endswith('.exe') == (sys.platform == 'win32')


# ------------------------------ la plantilla de la oficina, fuera del repo

def test_la_plantilla_de_verdad_se_escribe_donde_el_programa_la_busca(
        tmp_path, monkeypatch):
    """Los dos sitios tienen que ser el mismo, y no lo parecen.

    El programa lee sus archivos de `_internal/`, que es lo que PyInstaller le da
    como raíz. Escribir la plantilla junto al .exe —un nivel más arriba, que es
    donde parece que va— produce un fallo silencioso: el instalador se
    construye, el programa arranca, todo funciona, y la oficina se encuentra con
    dieciocho desconocidos en Personal.
    """
    import sys as _sys

    _sys.path.insert(0, str(RAIZ / 'empaquetado'))
    import construir
    import plantilla

    real = tmp_path / 'nomina'
    (real / 'datos_iniciales').mkdir(parents=True)
    (real / 'datos_iniciales' / 'empleados_iniciales.csv').write_text(
        'nombre\nQuien Trabaja Aqui\n', encoding='utf-8')
    (real / 'datos_iniciales' / 'reglas_internas.json').write_text(
        '[]', encoding='utf-8')

    salida = tmp_path / 'GestorHorarios'
    (salida / '_internal').mkdir(parents=True)
    monkeypatch.setattr(construir, 'SALIDA', salida)
    monkeypatch.setenv(plantilla.VARIABLE, plantilla.empaquetar(real))

    assert construir.poner_la_plantilla_de_la_oficina() is True
    puesta = salida / '_internal' / 'datos_iniciales' / 'empleados_iniciales.csv'
    assert puesta.is_file(), 'la plantilla no quedó donde el programa la busca'
    assert 'Quien Trabaja Aqui' in puesta.read_text(encoding='utf-8')


def test_sin_el_secreto_se_construye_igual_pero_se_dice(tmp_path, monkeypatch, capsys):
    """Quien clone el proyecto tiene que poder compilarlo sin pedir nada a nadie.

    Y aun así hay que decirlo: ese instalador arranca perfectamente y no sirve
    para la oficina.
    """
    import sys as _sys

    _sys.path.insert(0, str(RAIZ / 'empaquetado'))
    import construir
    import plantilla

    salida = tmp_path / 'GestorHorarios'
    (salida / '_internal').mkdir(parents=True)
    monkeypatch.setattr(construir, 'SALIDA', salida)
    monkeypatch.delenv(plantilla.VARIABLE, raising=False)

    assert construir.poner_la_plantilla_de_la_oficina() is False
    assert 'plantilla inventada' in capsys.readouterr().err


def test_la_plantilla_no_puede_colar_archivos_que_no_se_esperan(tmp_path):
    """Esto se desempaqueta **encima del programa que se va a entregar**.

    Un archivo cualquiera colado ahí dentro acabaría dentro del instalador que
    se instala en los equipos de la oficina, así que la lista de lo que puede
    venir está cerrada.
    """
    import sys as _sys

    _sys.path.insert(0, str(RAIZ / 'empaquetado'))
    import plantilla

    real = tmp_path / 'nomina'
    (real / 'datos_iniciales').mkdir(parents=True)
    (real / 'datos_iniciales' / 'empleados_iniciales.csv').write_text('n\n',
                                                                     encoding='utf-8')
    (real / 'cualquier_cosa.exe').write_bytes(b'MZ')
    with pytest.raises(SystemExit) as parada:
        plantilla.empaquetar(real)
    assert 'cualquier_cosa.exe' in str(parada.value)


def test_si_pyinstaller_cambia_de_sitio_las_cosas_se_para(tmp_path, monkeypatch):
    """Sin `_internal` no se adivina dónde va: se para y se dice."""
    import sys as _sys

    _sys.path.insert(0, str(RAIZ / 'empaquetado'))
    import construir

    salida = tmp_path / 'GestorHorarios'
    salida.mkdir(parents=True)
    monkeypatch.setattr(construir, 'SALIDA', salida)
    with pytest.raises(SystemExit):
        construir.carpeta_que_lee_el_programa()


# ----------------------------------- que el ejecutable se comprueba a sí mismo

def test_el_arranque_admite_las_dos_banderas_que_no_abren_ventana():
    """`--comprobar` y `--servidor`. Si se renombran, el empaquetado se rompe.

    El empaquetado ejecuta `<programa> --comprobar` al terminar y falla si no
    pasa. Un cambio de nombre aquí dejaría esa comprobación llamando a algo que
    no existe: el programa abriría una ventana, el proceso no terminaría nunca y
    la construcción se quedaría colgada en lugar de decir qué pasa.
    """
    codigo = (RAIZ / 'gestor' / 'principal.py').read_text(encoding='utf-8')
    assert "'--comprobar' in sys.argv" in codigo
    assert "'--servidor' in sys.argv" in codigo


def test_la_comprobacion_mira_lo_que_de_verdad_se_ha_caido_alguna_vez():
    """Cada línea de la autocomprobación corresponde a un fallo real.

    Se comprueba que sigan estando, porque son las que justifican que exista: la
    pantalla que faltaba y dejaba el programa en blanco, los datos iniciales sin
    los que arranca vacío, y la ruta que recibe un archivo subido —que sin
    `python-multipart` no se puede ni declarar, y tumba la aplicación entera al
    arrancar—.
    """
    codigo = (RAIZ / 'gestor' / 'autocomprobacion.py').read_text(encoding='utf-8')
    for lo_que_se_mira in ('/api/salud', '/api/auth/login', '/api/empleados',
                           '/api/horarios/opciones/2026/8',
                           '/api/operacion/restore'):
        assert lo_que_se_mira in codigo, f'ya no se comprueba {lo_que_se_mira}'


def test_el_empaquetado_se_para_si_el_ejecutable_no_pasa_su_comprobacion(
        tmp_path, monkeypatch):
    """Un instalador que no abre es peor que ninguno, así que no se empaqueta."""
    import subprocess
    import sys as _sys

    _sys.path.insert(0, str(RAIZ / 'empaquetado'))
    import construir

    monkeypatch.setattr(construir, 'SALIDA', tmp_path)
    monkeypatch.setattr(
        construir.subprocess, 'run',
        lambda *_a, **_k: subprocess.CompletedProcess(
            [], 1, stdout='  [FALLA] el programa arranca y responde\n',
            stderr='ImportError: No module named multipart'))
    with pytest.raises(SystemExit) as parada:
        construir.autocomprobar()
    assert 'no pasa su propia comprobación' in str(parada.value)


def test_la_receta_busca_el_nombre_que_tiene_aqui_el_modulo_de_subidas():
    """`python-multipart` cambió de nombre entre versiones.

    Hasta la 0.0.12 se importaba como `multipart` y desde entonces como
    `python_multipart`. Escribir los dos a pelo en la receta no vale: PyInstaller
    anota «Hidden import not found» para el que falte y **sigue construyendo**,
    así que el aviso se pierde y el fallo sale al arrancar. La receta pregunta
    cuál existe y se para si no existe ninguno.
    """
    receta = (RAIZ / 'empaquetado' / 'gestor.spec').read_text(encoding='utf-8')
    assert 'NOMBRE_DE_MULTIPART' in receta
    assert 'find_spec' in receta
    assert "'python_multipart'," not in receta, (
        'vuelve a estar escrito a mano: si no existe, nadie se enterará')


def test_python_multipart_está_en_los_requisitos():
    """Estaba instalado por venir con otra cosa, y así es como falta en Windows."""
    requisitos = (RAIZ / 'requisitos.txt').read_text(encoding='utf-8')
    assert 'python-multipart' in requisitos


def test_las_reglas_de_la_oficina_quedan_donde_el_programa_las_lee(tmp_path, monkeypatch):
    """El mismo sitio equivocado, por segunda vez, con otro archivo.

    La primera versión de la inyección dejaba `reglas_internas.json` en la raíz
    de la carpeta del programa, que es donde parece que va. El programa lo busca
    en `datos_iniciales/`. Resultado: el instalador se construía, arrancaba y
    funcionaba, y las reglas particulares de la oficina no se aplicaban nunca,
    sin un error y sin un aviso.

    No se comprueba que el archivo esté en tal ruta: se comprueba que **el
    programa lo encuentre**, preguntándoselo a él.
    """
    import sys as _sys

    _sys.path.insert(0, str(RAIZ / 'empaquetado'))
    import plantilla

    real = tmp_path / 'nomina' / 'datos_iniciales'
    real.mkdir(parents=True)
    (real / 'empleados_iniciales.csv').write_text('nombre\nAlguien\n', encoding='utf-8')
    (real / 'reglas_internas.json').write_text(
        '[{"tipo": "NuncaJuntos", "una": "Alguien", "otra": "Otra Persona",'
        ' "porque": "una prueba"}]', encoding='utf-8')

    programa = tmp_path / 'programa'
    programa.mkdir()
    assert plantilla.aplicar(programa, plantilla.empaquetar(tmp_path / 'nomina'))

    from gestor import rutas
    from gestor.dominio import internas
    monkeypatch.setattr(rutas, 'DATOS_INICIALES', programa / 'datos_iniciales')
    reglas = internas.reglas_activas()
    assert len(reglas) == 1, (
        'el programa no encuentra las reglas de la oficina donde la plantilla '
        'las dejó')
    assert reglas[0].porque == 'una prueba'


def test_nada_de_la_plantilla_puede_ir_fuera_de_datos_iniciales():
    """La condición escrita, para que no se sostenga solo en la costumbre."""
    import sys as _sys

    _sys.path.insert(0, str(RAIZ / 'empaquetado'))
    import plantilla

    assert plantilla.PERMITIDOS
    for permitido in plantilla.PERMITIDOS:
        assert permitido.startswith(plantilla.DENTRO_DE), permitido
