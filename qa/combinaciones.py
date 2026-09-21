# -*- coding: utf-8 -*-
"""La aplicación usada a lo bruto: cosas que cambian debajo de un mes ya hecho.

Las pruebas de Python miran una pieza cada vez. Esto mira lo que pasa **entre**
piezas, que es donde vivían los fallos de la versión anterior: se aprueba una
novedad y el mes sigue diciendo que está al día; se retira a alguien y su nombre
reaparece; se cambia una regla y el mes de antes se recalcula solo.

Cada escenario hace tres cosas: provoca el cambio, comprueba que la aplicación
**se entera** y comprueba que **no ha tocado nada por su cuenta**. La segunda
mitad importa tanto como la primera: regenerar por su cuenta un mes que la
oficina ya imprimió sería el peor comportamiento posible.

Al final, cada mes que quedó generado se pasa por el auditor independiente.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from pruebas.auditor import auditar  # noqa: E402
from qa.encadenado import reglas_vigentes_en  # noqa: E402
from qa.servidor import CLAVE_ADMIN_QA, Servidor, entrar_como_admin  # noqa: E402


class Acta:
    def __init__(self):
        self.pasos: list[tuple[bool, str, str]] = []

    def comprobar(self, ok, que, detalle=''):
        self.pasos.append((bool(ok), que, str(detalle)))
        print(f'  [{"ok  " if ok else "FALLA"}] {que}'
              + (f'   -> {detalle}' if not ok and detalle else ''), flush=True)
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


def _turnos(horario) -> dict:
    return {(f['empleado_id'], d['fecha']): d['turno']
            for f in horario for d in f['dias']}


def _generar_y_oficializar(servidor, cabeceras, anio, mes):
    estado, generado = servidor.pedir('/api/horarios/generar', 'POST',
                                      {'mes': mes, 'anio': anio}, cabeceras)
    if estado != 200:
        return None, generado
    elegida = next((a for a in generado['alternativas'] if a['valido']),
                   generado['alternativas'][0])
    servidor.pedir(f'/api/horarios/{elegida["horario_id"]}/oficial', 'PATCH',
                   None, cabeceras)
    return elegida, generado


# --------------------------------------------------------------- escenarios

def novedad_aprobada(servidor, cabeceras, acta):
    """Aprobar unas vacaciones no puede reescribir el mes por su cuenta."""
    print('\n— se aprueba una novedad sobre un mes ya hecho')
    elegida, _ = _generar_y_oficializar(servidor, cabeceras, 2026, 10)
    if elegida is None:
        acta.comprobar(False, 'octubre se genera')
        return
    antes = _turnos(elegida['horario'])

    estado, gente = servidor.pedir('/api/empleados', cabeceras=cabeceras)
    quien = gente[0]
    estado, creada = servidor.pedir('/api/solicitudes', 'POST', {
        'empleado_id': quien['id'], 'tipo': 'vacaciones',
        'fecha_inicio': '2026-10-13', 'fecha_fin': '2026-10-17'}, cabeceras)
    acta.comprobar(estado == 200, 'se registra la novedad', creada)
    servidor.pedir(f'/api/solicitudes/{creada["id"]}/aprobar', 'PATCH', None, cabeceras)

    estado, periodo = servidor.pedir('/api/operacion/periodo/2026/10',
                                     cabeceras=cabeceras)
    acta.comprobar(periodo['desactualizado'] is True,
                   'el mes queda marcado como desactualizado')
    acta.comprobar(periodo['origen_pendiente'] == 'solicitudes',
                   'y se sabe que viene de una solicitud, no de otra cosa',
                   periodo['origen_pendiente'])

    estado, oficial = servidor.pedir('/api/horarios/oficial/2026/10',
                                     cabeceras=cabeceras)
    ahora = _turnos(oficial['horario']['datos']['horario'])
    acta.comprobar(ahora == antes,
                   'y el horario oficial NO se ha tocado solo',
                   f'{sum(1 for k in antes if antes[k] != ahora.get(k))} casillas movidas')

    estado, regenerado = servidor.pedir('/api/horarios/generar', 'POST',
                                        {'mes': 10, 'anio': 2026}, cabeceras)
    acta.comprobar(estado == 200, 'se puede volver a generar con la novedad dentro')
    if estado == 200:
        nuevos = _turnos(regenerado['alternativas'][0]['horario'])
        vacaciones = [nuevos.get((quien['id'], f'2026-10-{d}')) for d in (13, 14, 15, 16)]
        acta.comprobar(all(t == 'VAC' for t in vacaciones),
                       'y las vacaciones aparecen en el horario nuevo', vacaciones)
        estado, periodo = servidor.pedir('/api/operacion/periodo/2026/10',
                                         cabeceras=cabeceras)
        acta.comprobar(periodo['desactualizado'] is True,
                       'el borrador no borra el pendiente del oficial')
        nueva = regenerado['alternativas'][0]['horario_id']
        servidor.pedir(f'/api/horarios/{nueva}/oficial', 'PATCH', None, cabeceras)
        estado, periodo = servidor.pedir('/api/operacion/periodo/2026/10',
                                         cabeceras=cabeceras)
        acta.comprobar(periodo['desactualizado'] is False,
                       'el pendiente se resuelve al elegir la propuesta actualizada')


def retiro_de_personal(servidor, cabeceras, acta):
    """Retirar a alguien: sale de lo nuevo y sigue en lo ya publicado."""
    print('\n— se retira a alguien a mitad de la programación')
    elegida, _ = _generar_y_oficializar(servidor, cabeceras, 2026, 10)
    servidor.pedir(f'/api/operacion/publicacion/{elegida["horario_id"]}', 'POST',
                   {'confirmar_excepciones': True}, cabeceras)

    estado, gente = servidor.pedir('/api/empleados', cabeceras=cabeceras)
    quien = next(p for p in gente if p['tipo_turno'] == 'rotativo')
    estado, retirada = servidor.pedir(
        f'/api/empleados/{quien["id"]}/retirar', 'POST',
        {'fecha_retiro': '2026-10-31', 'motivo': 'renuncia'}, cabeceras)
    acta.comprobar(estado == 200, 'se retira', retirada)

    estado, activos = servidor.pedir('/api/empleados', cabeceras=cabeceras)
    ficha = next((p for p in activos if p['id'] == quien['id']), None)
    acta.comprobar(ficha is None or ficha['retirado_desde'] == '2026-10-31',
                   'el retiro queda fechado y no elimina anticipadamente a la persona')
    estado, todos = servidor.pedir('/api/empleados?incluir_inactivos=true',
                                   cabeceras=cabeceras)
    acta.comprobar(quien['id'] in {p['id'] for p in todos},
                   'pero no se ha borrado: sigue estando')

    estado, oficial = servidor.pedir('/api/horarios/oficial/2026/10',
                                     cabeceras=cabeceras)
    sigue = any(int(f['empleado_id']) == quien['id']
                for f in oficial['horario']['datos']['horario'])
    acta.comprobar(sigue, 'y el mes ya publicado la sigue mostrando')

    # La semana compartida del oficial anterior se conserva. Incorporar primero
    # el retiro en octubre evita heredar un 1 de noviembre anterior al cambio.
    _generar_y_oficializar(servidor, cabeceras, 2026, 10)
    estado, nuevo = servidor.pedir('/api/horarios/generar', 'POST',
                                   {'mes': 11, 'anio': 2026}, cabeceras)
    if estado == 200:
        fuera = [d['turno'] for f in nuevo['alternativas'][0]['horario']
                 if int(f['empleado_id']) == quien['id']
                 for d in f['dias'] if d['fecha'] > '2026-10-31']
        acta.comprobar(all(t == 'NV' for t in fuera),
                       'y en noviembre ya no se le reparte ningún turno',
                       sorted(set(fuera))[:5])

    servidor.pedir(f'/api/empleados/{quien["id"]}/reactivar', 'POST', None, cabeceras)


def cambio_de_regla(servidor, cabeceras, acta):
    """Cambiar el reparto de un área desde una fecha no toca lo anterior."""
    print('\n— se cambia el reparto de un área a mitad de camino')
    _generar_y_oficializar(servidor, cabeceras, 2026, 11)
    estado, antes_reglas = servidor.pedir('/api/configuracion/reglas-cobertura',
                                          cabeceras=cabeceras)
    # El 30 de noviembre está dentro del período de noviembre —que llega al 6 de
    # diciembre— y también dentro del de diciembre. La fecha se elige a
    # propósito para comprobar las dos mitades de la regla: a quién alcanza y a
    # quién no.
    estado, guardada = servidor.pedir('/api/configuracion/reglas-cobertura', 'PUT', {
        'area': 'gestion_social', 'vigente_desde': '2026-11-30',
        'am_minimo': 2, 'pm_minimo': 2, 'minimo_total': 0}, cabeceras)
    acta.comprobar(estado == 200, 'se guarda el reparto nuevo', guardada)

    estado, noviembre = servidor.pedir('/api/operacion/periodo/2026/11',
                                       cabeceras=cabeceras)
    acta.comprobar(noviembre['desactualizado'] is True,
                   'noviembre queda marcado: su período llega al 6 de diciembre',
                   noviembre['razones'])
    acta.comprobar(noviembre['origen_pendiente'] == 'reglas',
                   'y se sabe que fue por una regla', noviembre['origen_pendiente'])

    # Octubre puede estar marcado por otra cosa —este mismo recorrido ha
    # retirado y reincorporado a alguien antes—, así que lo que se comprueba no
    # es que esté limpio sino que **esta regla** no lo ha alcanzado. Comprobar
    # «no está marcado» a secas hacía fallar la prueba por un motivo correcto.
    estado, octubre = servidor.pedir('/api/operacion/periodo/2026/10',
                                     cabeceras=cabeceras)
    por_reglas = [r for r in octubre['razones'] if r.get('origen') == 'reglas']
    acta.comprobar(not por_reglas,
                   'y a octubre no le alcanza: su período terminó el 1 de noviembre',
                   por_reglas)

    estado, diciembre = servidor.pedir('/api/horarios/generar', 'POST',
                                       {'mes': 12, 'anio': 2026}, cabeceras)
    acta.comprobar(estado == 200, 'diciembre se genera con el reparto nuevo',
                   str(diciembre)[:200])
    return diciembre if estado == 200 else None


def festivo_movido(servidor, cabeceras, acta):
    print('\n— se traslada un festivo')
    estado, movido = servidor.pedir('/api/configuracion/festivos', 'PUT', {
        'fecha_original': '2026-11-16', 'fecha_nueva': '2026-11-17',
        'nombre': 'Trasladado a mano'}, cabeceras)
    acta.comprobar(estado == 200, 'se traslada', movido)
    estado, festivos = servidor.pedir('/api/configuracion/festivos/2026',
                                      cabeceras=cabeceras)
    marcado = next((f for f in festivos['festivos']
                    if f['fecha_original'] == '2026-11-16'), None)
    acta.comprobar(marcado and marcado['modificado'] and
                   marcado['fecha_efectiva'] == '2026-11-17',
                   'y queda marcado como movido, con su fecha nueva', marcado)
    servidor.pedir('/api/configuracion/festivos/2026-11-16', 'DELETE', None, cabeceras)
    estado, vuelta = servidor.pedir('/api/configuracion/festivos/2026',
                                    cabeceras=cabeceras)
    devuelto = next(f for f in vuelta['festivos'] if f['fecha_original'] == '2026-11-16')
    acta.comprobar(not devuelto['modificado'], 'y se puede devolver a su sitio')


def semana_cerrada(servidor, cabeceras, acta):
    """Una semana cerrada se conserva letra por letra al regenerar."""
    print('\n— se cierra una semana y se vuelve a generar el mes')
    elegida, _ = _generar_y_oficializar(servidor, cabeceras, 2026, 11)
    if elegida is None:
        return
    antes = _turnos(elegida['horario'])

    estado, semanas = servidor.pedir('/api/operacion/semanas/2026/11',
                                     cabeceras=cabeceras)
    lunes = semanas['semanas'][1]['lunes']
    estado, cerrada = servidor.pedir('/api/operacion/semanas', 'PUT', {
        'anio': 2026, 'mes': 11, 'lunes_semana': lunes, 'bloqueada': True}, cabeceras)
    acta.comprobar(estado == 200, f'se cierra la semana del {lunes}', cerrada)

    estado, resultado = servidor.pedir('/api/horarios/reprogramar-parcial', 'POST', {
        'mes': 11, 'anio': 2026, 'horario_id': elegida['horario_id']}, cabeceras)
    acta.comprobar(estado == 200, 'se reprograma el mes entero', str(resultado)[:200])
    if estado != 200:
        return
    from datetime import date, timedelta
    inicio = date.fromisoformat(lunes)
    de_la_semana = {(inicio + timedelta(days=i)).isoformat() for i in range(7)}
    despues = _turnos(resultado['alternativas'][0]['horario'])
    movidas = [k for k in antes
               if k[1] in de_la_semana and antes[k] != despues.get(k)]
    acta.comprobar(not movidas,
                   'y la semana cerrada queda exactamente igual, casilla por casilla',
                   f'{len(movidas)} casillas movidas: {movidas[:3]}')

    servidor.pedir('/api/operacion/semanas', 'PUT', {
        'anio': 2026, 'mes': 11, 'lunes_semana': lunes, 'bloqueada': False}, cabeceras)


def reinicio(servidor, cabeceras, acta):
    """Reiniciar tiene que llevarse todo lo que reconstruye el mes."""
    print('\n— se reinicia la programación desde octubre')
    estado, respuesta = servidor.pedir(
        '/api/configuracion/reiniciar-programacion', 'POST',
        {'mes': 10, 'anio': 2026},
        {**cabeceras, 'X-User-Password': CLAVE_ADMIN_QA})
    acta.comprobar(estado == 200, 'se reinicia', str(respuesta)[:200])
    if estado != 200:
        return
    for anio, mes in ((2026, 10), (2026, 11), (2026, 12)):
        estado, opciones = servidor.pedir(f'/api/horarios/opciones/{anio}/{mes}',
                                          cabeceras=cabeceras)
        acta.comprobar(opciones['cantidad'] == 0,
                       f'{anio}-{mes:02d} se queda sin ninguna propuesta',
                       opciones['cantidad'])
    estado, septiembre = servidor.pedir('/api/horarios/oficial/2026/9',
                                        cabeceras=cabeceras)
    acta.comprobar(septiembre['hay_oficial'] is True,
                   'y septiembre, que es base, se conserva')
    estado, desactualizados = servidor.pedir('/api/operacion/desactualizados',
                                             cabeceras=cabeceras)
    acta.comprobar(not desactualizados['meses'],
                   'y no queda ningún aviso de meses viejos colgando',
                   desactualizados['meses'])


def _auditar_lo_que_quede(servidor, cabeceras, acta):
    print('\n— auditoría independiente de todo lo que quedó generado')
    for anio, mes in ((2026, 10), (2026, 11), (2026, 12)):
        # Cada mes se mide con el reparto que regía **entonces**. Midiéndolos
        # todos con el de hoy, el cambio de reparto que hace esta misma suite
        # convertía en incumplimientos los meses correctos de antes.
        por_area = reglas_vigentes_en(servidor, cabeceras, anio, mes)
        estado, opciones = servidor.pedir(f'/api/horarios/opciones/{anio}/{mes}',
                                          cabeceras=cabeceras)
        if not opciones.get('cantidad'):
            continue
        for alternativa in opciones['alternativas']:
            fallos = [f for f in auditar(alternativa['horario'], por_area)
                      if '(heredado)' not in f[0]]
            acta.comprobar(not fallos,
                           f'{anio}-{mes:02d} · opción {alternativa["alternativa"]} '
                           'cumple todas las reglas',
                           '; '.join(f'{n}: {t}' for n, t in fallos[:3]))


def main() -> int:
    acta = Acta()
    with Servidor('/tmp/qa_combinaciones') as servidor:
        cabeceras = entrar_como_admin(servidor)
        print(f'Servidor en {servidor.base}')
        novedad_aprobada(servidor, cabeceras, acta)
        retiro_de_personal(servidor, cabeceras, acta)
        cambio_de_regla(servidor, cabeceras, acta)
        festivo_movido(servidor, cabeceras, acta)
        semana_cerrada(servidor, cabeceras, acta)
        _auditar_lo_que_quede(servidor, cabeceras, acta)
        reinicio(servidor, cabeceras, acta)
    return acta.resumen()


if __name__ == '__main__':
    raise SystemExit(main())
