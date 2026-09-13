# -*- coding: utf-8 -*-
"""Usar la aplicación terminada como la usaría una persona, con un navegador.

Esto es lo que encuentra los fallos que ninguna prueba de Python encuentra: un
botón que llama a una dirección que ya no existe, una respuesta con otro nombre
de campo, un modal que tapa lo siguiente, una tabla que se queda vacía porque el
servidor devuelve un objeto donde la pantalla espera una lista.

Tres reglas de esta suite:

* **se comprueba el efecto, no el mensaje**. Que salga un aviso verde diciendo
  «guardado» no prueba nada: se vuelve a preguntar al servidor y se mira si de
  verdad quedó guardado. La versión anterior daba pasos por buenos porque salía
  el aviso, y dos botones de Configuración no los pulsó nunca nadie;
* **los errores de JavaScript son fallos**. Se escuchan todos y se listan al
  final. Uno solo basta para dejar media pantalla muerta sin que se vea nada
  raro;
* **cada recorrido empieza sobre una instalación nueva**, para que ningún paso
  herede lo que dejó otro.
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from qa.servidor import Servidor, entrar_como_admin  # noqa: E402
from qa.uso import App  # noqa: E402

CAPTURAS = Path('/tmp/qa_capturas')
NAVEGADOR = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'

#: Las de verdad, leídas del HTML. La lista escrita a mano se descolgaba en
#: cuanto se renombraba una: la suite pedía «asignaciones» y la pantalla la
#: llamaba «requerimientos», y el recorrido se paraba ahí.
PESTANAS = ['personal', 'solicitudes', 'requerimientos', 'horario', 'modificar',
            'validacion', 'historial', 'configuracion']


class Acta:
    """Lo que se ha comprobado y con qué resultado."""

    def __init__(self):
        self.pasos: list[tuple[bool, str, str]] = []

    def comprobar(self, ok: bool, que: str, detalle: str = '') -> bool:
        self.pasos.append((bool(ok), que, detalle))
        marca = 'ok  ' if ok else 'FALLA'
        print(f'  [{marca}] {que}' + (f'   -> {detalle}' if not ok and detalle else ''),
              flush=True)
        return bool(ok)

    def resumen(self) -> int:
        buenos = sum(1 for ok, _, _ in self.pasos if ok)
        print(f'\n{buenos}/{len(self.pasos)} comprobaciones correctas')
        malos = [(q, d) for ok, q, d in self.pasos if not ok]
        if malos:
            print('\nLo que falló:')
            for que, detalle in malos:
                print(f'  · {que}' + (f'   -> {detalle}' if detalle else ''))
        return 0 if not malos else 1


def _recorrer_pestanas(app, acta, servidor):
    """Abrir todas y comprobar que ninguna se queda en blanco."""
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    for pestana in PESTANAS:
        app.ir(pestana)
        visible = app.pag.evaluate(
            "(t)=>{const s=document.getElementById(t);"
            " if(!s) return -1;"
            " return s.classList.contains('active') ? s.innerText.trim().length : -2;}",
            pestana)
        acta.comprobar(visible > 60, f'la pestaña «{pestana}» abre y tiene contenido',
                       {-1: 'no existe esa sección', -2: 'no llegó a abrirse'}.get(
                           visible, f'{visible} caracteres'))
        app.pag.screenshot(path=str(CAPTURAS / f'{pestana}.png'), full_page=True)


def _generar_y_oficializar(app, acta, servidor, cabeceras):
    app.ir('horario')
    app.periodo(2026, 10)
    acta.comprobar(app.generar(), 'se generan las propuestas de octubre desde la pantalla')
    estado, opciones = servidor.pedir('/api/horarios/opciones/2026/10',
                                      cabeceras=cabeceras)
    acta.comprobar(estado == 200 and opciones['cantidad'] >= 1,
                   'el servidor guardó las propuestas', str(opciones.get('cantidad')))

    acta.comprobar(app.oficializar(), 'la propuesta queda marcada como oficial')
    estado, oficial = servidor.pedir('/api/horarios/oficial/2026/10', cabeceras=cabeceras)
    acta.comprobar(oficial.get('hay_oficial') is True,
                   'y el servidor lo confirma, no solo la pantalla')


def _solicitud(app, acta, servidor, cabeceras):
    """Crear una novedad, aprobarla y ver que el mes queda marcado."""
    app.ir('solicitudes')
    # El tipo primero: cada tipo enseña unos campos distintos, y con el que
    # viene por defecto —mover el descanso semanal— ni siquiera hay fechas que
    # rellenar. Poner la fecha antes que el tipo era escribir en un campo que
    # todavía no estaba en pantalla.
    app.pag.select_option('#solicitud-tipo', 'permiso')
    app.pag.wait_for_timeout(700)
    app.pag.select_option('#solicitud-empleado', index=1)
    puesta = app.elegir_fecha('solicitud-inicio', '2026-10-20')
    app.elegir_fecha('solicitud-fin', '2026-10-20')
    acta.comprobar(puesta, 'el calendario de la aplicación deja elegir la fecha',
                   f'quedó «{app.valor("#solicitud-inicio")}»')
    app.pulsar('#form-solicitud button[type="submit"]', 0, 2500)
    app.aceptar()

    estado, solicitudes = servidor.pedir('/api/solicitudes', cabeceras=cabeceras)
    acta.comprobar(estado == 200 and isinstance(solicitudes, list) and solicitudes,
                   'la solicitud llegó al servidor',
                   f'{estado} · {type(solicitudes).__name__}')
    if not solicitudes:
        return
    identificador = solicitudes[0]['id']
    acta.comprobar(solicitudes[0]['estado'] == 'pendiente',
                   'nace pendiente, no aprobada')

    estado, aprobada = servidor.pedir(
        f'/api/solicitudes/{identificador}/aprobar', 'PATCH', None, cabeceras)
    acta.comprobar(estado == 200, 'se aprueba', str(aprobada)[:120])
    acta.comprobar('volver a generar' in aprobada.get('mensaje', ''),
                   'y el mensaje avisa de qué mes conviene rehacer',
                   aprobada.get('mensaje', ''))

    estado, periodo = servidor.pedir('/api/operacion/periodo/2026/10',
                                     cabeceras=cabeceras)
    acta.comprobar(periodo.get('desactualizado') is True,
                   'octubre queda marcado como desactualizado')
    acta.comprobar(periodo['areas'] and any(
        a['requiere_actualizacion'] for a in periodo['areas'].values()),
        'y se sabe qué área es la afectada, no las tres')


def _cambio_de_turno(app, acta, servidor, cabeceras):
    estado, gente = servidor.pedir('/api/empleados', cabeceras=cabeceras)
    rotativa = next((p for p in gente if p['tipo_turno'] == 'rotativo'), None)
    if rotativa is None:
        return
    estado, resultado = servidor.pedir(
        f'/api/empleados/{rotativa["id"]}/cambio-turno', 'POST',
        {'vigente_desde': '2026-11-04', 'tipo_turno': 'fijo', 'turno_fijo': 'AM',
         'aplicar_a_pareja': True}, cabeceras)
    acta.comprobar(estado == 200, 'se programa un cambio de turno', str(resultado)[:150])
    if estado != 200:
        return
    acta.comprobar(resultado['vigente_desde'] == '2026-11-09',
                   'la fecha se corre al lunes siguiente para no partir la semana',
                   resultado.get('vigente_desde', ''))

    estado, lista = servidor.pedir('/api/empleados/cambios-turno', cabeceras=cabeceras)
    acta.comprobar(estado == 200 and lista['cambios'],
                   'el cambio aparece en la lista de cambios programados')
    if lista['cambios']:
        cambio = lista['cambios'][0]
        acta.comprobar(cambio['antes'] != cambio['despues'],
                       'la lista dice lo de antes y lo de después',
                       f'{cambio["antes"]} → {cambio["despues"]}')
        estado, deshecho = servidor.pedir(
            f'/api/empleados/{cambio["empleado_id"]}/cambio-turno/'
            f'{cambio["vigente_desde"]}', 'DELETE', None, cabeceras)
        acta.comprobar(estado == 200, 'y se puede deshacer', str(deshecho)[:120])
        estado, despues = servidor.pedir('/api/empleados/cambios-turno',
                                         cabeceras=cabeceras)
        acta.comprobar(not despues['cambios'], 'deshacer lo quita de verdad de la lista')


def _reglas(app, acta, servidor, cabeceras):
    app.ir('configuracion')
    estado, reglas = servidor.pedir('/api/configuracion/reglas-cobertura',
                                    cabeceras=cabeceras)
    acta.comprobar(estado == 200 and len(reglas['areas']) == 3,
                   'las tres áreas traen su reparto vigente')
    comunicaciones = next(a for a in reglas['areas'] if a['area'] == 'comunicaciones')
    acta.comprobar(bool(comunicaciones['vigente']['id']),
                   'cada reparto trae el número con el que se puede quitar')

    estado, guardada = servidor.pedir(
        '/api/configuracion/reglas-cobertura', 'PUT',
        {'area': 'comunicaciones', 'vigente_desde': '2026-12-07',
         'minimo_total': 1, 'am_objetivo': 1, 'pm_objetivo': 1,
         'am_maximo': 2, 'pm_maximo': 2}, cabeceras)
    acta.comprobar(estado == 200, 'se guarda un reparto nuevo con fecha',
                   str(guardada)[:150])

    estado, despues = servidor.pedir('/api/configuracion/reglas-cobertura',
                                     cabeceras=cabeceras)
    comunicaciones = next(a for a in despues['areas'] if a['area'] == 'comunicaciones')
    acta.comprobar(len(comunicaciones['historial']) >= 3,
                   'el reparto anterior se conserva en el historial',
                   str(len(comunicaciones['historial'])))
    acta.comprobar(comunicaciones['vigente']['vigente_desde'] == '2026-12-07',
                   'y el vigente pasa a ser el nuevo')

    estado, quitada = servidor.pedir(
        f'/api/configuracion/reglas-cobertura/{comunicaciones["vigente"]["id"]}',
        'DELETE', None, cabeceras)
    acta.comprobar(estado == 200, 'y se puede quitar', str(quitada)[:120])


def _no_se_deja_sin_regla(acta, servidor, cabeceras):
    estado, reglas = servidor.pedir('/api/configuracion/reglas-cobertura',
                                    cabeceras=cabeceras)
    social = next(a for a in reglas['areas'] if a['area'] == 'gestion_social')
    if len(social['historial']) != 1:
        return
    estado, respuesta = servidor.pedir(
        f'/api/configuracion/reglas-cobertura/{social["vigente"]["id"]}',
        'DELETE', None, cabeceras)
    acta.comprobar(estado == 400 and 'sin ninguna regla' in respuesta.get('detail', ''),
                   'no se puede dejar un área sin ninguna regla de cobertura',
                   str(respuesta)[:150])


def _semanas(acta, servidor, cabeceras):
    estado, semanas = servidor.pedir('/api/operacion/semanas/2026/10',
                                     cabeceras=cabeceras)
    acta.comprobar(estado == 200 and len(semanas['semanas']) >= 4,
                   'octubre tiene sus semanas completas',
                   str(len(semanas.get('semanas', []))))
    lunes = semanas['semanas'][0]['lunes']
    estado, cerrada = servidor.pedir(
        '/api/operacion/semanas', 'PUT',
        {'anio': 2026, 'mes': 10, 'lunes_semana': lunes, 'bloqueada': True}, cabeceras)
    acta.comprobar(estado == 200, 'se cierra una semana', str(cerrada)[:120])
    estado, ahora = servidor.pedir('/api/operacion/semanas/2026/10', cabeceras=cabeceras)
    acta.comprobar(ahora['semanas'][0]['bloqueada'] is True,
                   'y queda cerrada de verdad, no solo en el mensaje')
    servidor.pedir('/api/operacion/semanas', 'PUT',
                   {'anio': 2026, 'mes': 10, 'lunes_semana': lunes,
                    'bloqueada': False}, cabeceras)


def _exportar(acta, servidor, cabeceras):
    for libro in ('trabajo', 'completo'):
        estado, salida = servidor.pedir(
            '/api/exportacion/exportar/2026/10', 'POST',
            {'libro': libro, 'nombre': f'prueba_{libro}.xlsx'}, cabeceras)
        acta.comprobar(estado == 200 and salida.get('archivo', '').endswith('.xlsx'),
                       f'sale el libro «{libro}»', str(salida)[:150])
        if estado == 200:
            acta.comprobar(Path(salida['ruta']).is_file(),
                           f'y el archivo de «{libro}» existe en el disco',
                           salida.get('ruta', ''))
    estado, modo = servidor.pedir('/api/exportacion/modo', cabeceras=cabeceras)
    acta.comprobar(estado == 200 and 'dialogo_nativo' in modo,
                   'la pantalla puede saber cómo se va a guardar')


def _apariencia(app, acta, servidor, cabeceras):
    estado, temas = servidor.pedir('/api/configuracion/tema-app', cabeceras=cabeceras)
    acta.comprobar(estado == 200 and temas.get('opciones'),
                   'los temas se ofrecen con el nombre que la pantalla lee')
    if temas.get('opciones'):
        elegido = temas['opciones'][-1]['id']
        estado, puesto = servidor.pedir('/api/configuracion/tema-app', 'PUT',
                                        {'tema': elegido}, cabeceras)
        acta.comprobar(estado == 200 and puesto['tema']['id'] == elegido,
                       'y se puede cambiar el tema', str(puesto)[:120])

    estado, colores = servidor.pedir('/api/configuracion/colores-excel',
                                     cabeceras=cabeceras)
    acta.comprobar(estado == 200 and colores.get('paletas'),
                   'hay paletas de color para el Excel')
    estado, guardados = servidor.pedir(
        '/api/configuracion/colores-excel', 'PUT', {'header': '#123456'}, cabeceras)
    # El color se guarda sin la almohadilla, que es como lo quiere el Excel.
    acta.comprobar(
        estado == 200 and str(guardados['colores'].get('header', '')).lstrip('#').upper()
        == '123456',
        'se guarda un color suelto sin envoltorio, como lo manda la pantalla',
        str(guardados)[:150])


def _reglas_activas(acta, servidor, cabeceras):
    estado, reglas = servidor.pedir('/api/operacion/reglas', cabeceras=cabeceras)
    acta.comprobar(estado == 200 and len(reglas['reglas']) >= 10,
                   'la pantalla de Validación tiene reglas que enseñar',
                   str(len(reglas.get('reglas', []))))
    if estado == 200:
        acta.comprobar(all(r.get('que_hacer') for r in reglas['reglas']),
                       'y todas dicen qué hacer, no solo qué está mal')
        acta.comprobar({r['nivel'] for r in reglas['reglas']} <= {
            'bloqueante', 'decision', 'advertencia'},
            'los niveles son los tres que la pantalla sabe agrupar')


def _editor_manual(acta, servidor, cabeceras):
    estado, oficial = servidor.pedir('/api/horarios/oficial/2026/10', cabeceras=cabeceras)
    if not oficial.get('hay_oficial'):
        return
    guardado = oficial['horario']
    celda = None
    for fila in guardado['datos']['horario']:
        for dia in fila['dias']:
            if (dia.get('mes_propio') and dia.get('turno') in ('AM', 'PM')
                    and not dia.get('heredado')
                    and not str(dia.get('origen') or '').startswith('base_')):
                celda = (fila, dia)
                break
        if celda:
            break
    if celda is None:
        return
    fila, dia = celda
    estado, resultado = servidor.pedir(
        '/api/horarios/reprogramar-parcial', 'POST', {
            'mes': 10, 'anio': 2026, 'horario_id': guardado['id'],
            'solo_este_dia': True,
            'ajustes_manuales': [{'empleado_id': fila['empleado_id'],
                                  'fecha': dia['fecha'], 'turno': 'D'}]}, cabeceras)
    acta.comprobar(estado == 200, 'un cambio manual de un día se procesa',
                   str(resultado)[:200])
    if estado != 200:
        return
    diagnostico = resultado['diagnostico_ajustes_manuales']
    acta.comprobar(bool(diagnostico), 'y viene con su diagnóstico')
    if diagnostico:
        acta.comprobar(diagnostico[0]['estado'] in ('aplicado', 'forzado', 'no_aplicado'),
                       'que dice qué pasó con el cambio', diagnostico[0]['estado'])
        acta.comprobar(bool(diagnostico[0]['mensaje']),
                       'con una frase que se puede leer',
                       diagnostico[0].get('mensaje', ''))

    estado, retirado = servidor.pedir(
        f'/api/horarios/ajuste-manual/{fila["empleado_id"]}/{dia["fecha"]}',
        'DELETE', None, cabeceras)
    acta.comprobar(estado == 200, 'el cambio manual se puede retirar', str(retirado)[:120])
    estado, otra_vez = servidor.pedir(
        f'/api/horarios/ajuste-manual/{fila["empleado_id"]}/{dia["fecha"]}',
        'DELETE', None, cabeceras)
    acta.comprobar(otra_vez.get('detail', '').startswith('No existe'),
                   'y retirarlo dos veces se explica en vez de fallar seco',
                   str(otra_vez)[:120])


def _errores_de_javascript(app, acta):
    acta.comprobar(not app.errores_js,
                   'ningún error de JavaScript durante todo el recorrido',
                   ' | '.join(app.errores_js[:4]))


def main() -> int:
    from playwright.sync_api import sync_playwright

    acta = Acta()
    with Servidor('/tmp/qa_pantalla') as servidor:
        cabeceras = entrar_como_admin(servidor)
        print(f'Servidor en {servidor.base}\n')
        with sync_playwright() as guion:
            navegador = guion.chromium.launch(
                executable_path=NAVEGADOR, args=['--no-sandbox'])
            pagina = navegador.new_page(viewport={'width': 1600, 'height': 1000})
            app = App(pagina)
            try:
                acta.comprobar(app.entrar(servidor.base),
                               'se entra con usuario y contraseña',
                               app.alerta('#login-alerta'))

                print('\n— la aplicación abre y todas las pantallas tienen contenido')
                _recorrer_pestanas(app, acta, servidor)

                print('\n— armar el mes, elegirlo y publicarlo')
                _generar_y_oficializar(app, acta, servidor, cabeceras)

                print('\n— una novedad, de principio a fin')
                _solicitud(app, acta, servidor, cabeceras)

                print('\n— cambiar de turno a alguien, y deshacerlo')
                _cambio_de_turno(app, acta, servidor, cabeceras)

                print('\n— las reglas de cobertura')
                _reglas(app, acta, servidor, cabeceras)
                _no_se_deja_sin_regla(acta, servidor, cabeceras)

                print('\n— cerrar y abrir semanas')
                _semanas(acta, servidor, cabeceras)

                print('\n— las reglas que se enseñan en Validación')
                _reglas_activas(acta, servidor, cabeceras)

                print('\n— el editor manual')
                _editor_manual(acta, servidor, cabeceras)

                print('\n— sacar el Excel')
                _exportar(acta, servidor, cabeceras)

                print('\n— la apariencia')
                _apariencia(app, acta, servidor, cabeceras)

                print('\n— revisión final')
                _errores_de_javascript(app, acta)
                pagina.screenshot(path=str(CAPTURAS / 'final.png'), full_page=True)
            except Exception:
                acta.comprobar(False, 'el recorrido terminó entero',
                               traceback.format_exc()[-600:])
            finally:
                navegador.close()

    print(f'\nCapturas en {CAPTURAS}')
    return acta.resumen()


if __name__ == '__main__':
    raise SystemExit(main())
