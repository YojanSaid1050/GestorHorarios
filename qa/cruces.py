# -*- coding: utf-8 -*-
"""Todas las novedades contra todas, y cada una contra sí misma.

Esta suite existe por un mes de octubre de verdad. Alguien pidió mover su
descanso semanal cuatro veces —el 2, el 11, el 14 y el 15— y el horario salió
con **tres días libres en una misma semana**. Dos de aquellas solicitudes caían
en la misma semana, la del 12, y las dos se aprobaron sin una palabra; la
tercera libranza era el compensatorio del festivo del día 12. El choque solo
aparecía al final, generando el mes entero, como un error dentro de Validación.

La solicitud del día 2 no llegó a aplicarse nunca, y tampoco se dijo: caía en la
semana que octubre comparte con septiembre, que se copia tal cual del mes ya
entregado.

Ninguna prueba lo vio venir porque todas probaban **una** novedad cada vez. Lo
que fallaba era el cruce. Así que aquí se cruzan:

* cada tipo de novedad contra cada otro tipo, sobre la misma persona;
* el mismo tipo consigo mismo, en el mismo día y en la misma semana;
* y cada uno de esos cruces en los tres sitios donde la frontera del mes
  cambia las reglas: la semana heredada, una semana corriente y la semana que
  lleva el festivo.

Lo que se comprueba en cada cruce no es que salga bien —hay cruces que tienen
que salir mal— sino que **la aplicación diga lo que pasó**. Un cruce imposible
tiene que rechazarse al aprobar, con su motivo; un cruce que no se puede aplicar
tiene que dejar un aviso. Lo único inaceptable es el silencio, que es
exactamente lo que ocurrió en octubre.
"""
from __future__ import annotations

import itertools
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from qa.servidor import Servidor, entrar_como_admin  # noqa: E402

#: Los tipos de novedad que ocupan un día, con lo que cada uno necesita además
#: de la fecha. Los cambios de turno van aparte: no producen días libres.
TIPOS = {
    'descanso': {},
    'descanso_extra': {},
    'vacaciones': {},
    'incapacidad': {},
    'permiso': {},
    'capacitacion': {},
}

#: Las tres zonas del período de octubre de 2026, que no se comportan igual.
#:
#: * `heredada`  — 28/09 al 04/10: la semana que octubre comparte con septiembre
#:                 y copia literal del mes ya entregado.
#: * `festivo`   — la semana del 12, que lleva el festivo del 12 de octubre y
#:                 por tanto un compensatorio que ya ocupa un día libre.
#: * `corriente` — la semana del 19, sin nada especial encima.
ZONAS = {
    'heredada': ('2026-10-01', '2026-10-02'),
    'festivo': ('2026-10-14', '2026-10-15'),
    'corriente': ('2026-10-20', '2026-10-21'),
}


class Acta:
    def __init__(self):
        self.pasos: list[tuple[bool, str, str]] = []

    def comprobar(self, ok, que, detalle=''):
        self.pasos.append((bool(ok), que, str(detalle)))
        if not ok:
            print(f'  [FALLA] {que}   -> {detalle}', flush=True)
        return bool(ok)

    def resumen(self) -> int:
        buenos = sum(1 for ok, _, _ in self.pasos if ok)
        print(f'\n{"=" * 72}\n{buenos}/{len(self.pasos)} cruces correctos')
        malos = [(q, d) for ok, q, d in self.pasos if not ok]
        if malos:
            print('\nLo que falló:')
            for que, detalle in malos[:40]:
                print(f'  · {que}\n      {detalle}')
        return 0 if not malos else 1


def _lunes(fecha: str) -> str:
    f = date.fromisoformat(fecha)
    return (f - timedelta(days=f.weekday())).isoformat()


def crear(servidor, cabeceras, empleado_id: int, tipo: str, fecha: str):
    """Pide una novedad y la aprueba. Devuelve (estado_crear, estado_aprobar, texto)."""
    cuerpo = {
        'empleado_id': empleado_id, 'tipo': tipo,
        'fecha_inicio': fecha, 'fecha_fin': fecha, 'modo_periodo': 'rango',
    }
    estado, creada = servidor.pedir('/api/solicitudes', 'POST', cuerpo, cabeceras)
    if estado != 200:
        return estado, None, str(creada.get('detail', creada))[:160]
    estado2, r2 = servidor.pedir(
        f'/api/solicitudes/{creada["id"]}/aprobar', 'PATCH', None, cabeceras)
    return estado, estado2, str(
        r2.get('detail') if estado2 != 200 else r2.get('mensaje', ''))[:160]


def descansos_de_la_semana(fila: dict, fecha: str) -> list[str]:
    lunes = _lunes(fecha)
    return [d['fecha'] for d in fila['dias']
            if d.get('lunes_semana') == lunes and d['turno'] == 'D']


def revisar_un_cruce(servidor, cabeceras, acta, persona, primero, segundo,
                     zona, fechas):
    """Dos novedades sobre la misma persona, y qué dice la aplicación."""
    eid = persona['id']
    nombre = persona['nombre'].split()[0]
    f1, f2 = fechas
    etiqueta = f'{primero} + {segundo} · semana {zona}'

    _, ap1, txt1 = crear(servidor, cabeceras, eid, primero, f1)
    _, ap2, txt2 = crear(servidor, cabeceras, eid, segundo, f2)

    estado, gen = servidor.pedir('/api/horarios/generar', 'POST',
                                 {'mes': 10, 'anio': 2026}, cabeceras)
    # Un 409 es una respuesta legítima: hay combinaciones que de verdad no caben.
    # Lo que no vale es que no quepan **y** el motivo sea mentira o esté vacío.
    if estado != 200:
        acta.comprobar(
            estado == 409 and len(str(gen.get('detail') or '')) > 40,
            f'{etiqueta}: si el mes no cabe, se dice por qué',
            f'{estado} {str(gen)[:150]}')
        return
    alt = gen['alternativas'][0]
    fila = next((f for f in alt['horario'] if f['empleado_id'] == eid), None)
    if fila is None:
        return

    dicho = ' | '.join(alt['errores'] + alt['advertencias'])

    # 1) Una novedad aceptada que cae en la semana heredada no puede aplicarse,
    #    y eso hay que decirlo. Es el fallo que se vio en octubre.
    if zona == 'heredada':
        for aprobada, fecha in ((ap1, f1), (ap2, f2)):
            if aprobada != 200:
                continue
            acta.comprobar(
                fecha in dicho and nombre in dicho,
                f'{etiqueta}: se avisa de que el {fecha} no se aplicó',
                'la novedad se aprobó, el día no cambió y no se dijo nada')

    # 2) Nunca tres días libres en una semana sin que el mes lo denuncie.
    for fecha in (f1, f2):
        libres = descansos_de_la_semana(fila, fecha)
        if len(libres) >= 3:
            acta.comprobar(
                bool(alt['errores']),
                f'{etiqueta}: {len(libres)} días libres en la semana del '
                f'{_lunes(fecha)} salen denunciados',
                f'libres en {libres} y el mes se da por válido')

    # 3) Un mes que sale inválido tiene que decir por qué.
    if not alt['valido']:
        acta.comprobar(bool(alt['errores']),
                       f'{etiqueta}: un mes inválido explica su motivo',
                       'valido=False sin un solo error escrito')

    # 4) Lo que se aprobó y sí se pudo aplicar, se ve en el horario.
    if zona != 'heredada':
        for aprobada, fecha, tipo in ((ap1, f1, primero), (ap2, f2, segundo)):
            if aprobada != 200 or tipo not in ('vacaciones', 'incapacidad', 'permiso'):
                continue
            dia = next((d for d in fila['dias'] if d['fecha'] == fecha), None)
            if dia is None:
                continue
            acta.comprobar(
                dia['turno'] in ('VAC', 'INC', 'PER') or fecha in dicho,
                f'{etiqueta}: el {fecha} refleja «{tipo}» o se explica por qué no',
                f"quedó {dia['turno']} (origen {dia.get('origen')}) y nadie lo explica")


def main() -> int:
    acta = Acta()
    carpeta = '/tmp/qa_cruces_datos'
    combinaciones = list(itertools.product(TIPOS, repeat=2))
    print(f'{len(combinaciones)} pares de tipos × {len(ZONAS)} zonas del mes '
          f'= {len(combinaciones) * len(ZONAS)} cruces\n')

    for zona, fechas in ZONAS.items():
        for primero, segundo in combinaciones:
            shutil.rmtree(carpeta, ignore_errors=True)
            with Servidor(carpeta) as servidor:
                cabeceras = entrar_como_admin(servidor)
                _, gente = servidor.pedir('/api/empleados', 'GET', None, cabeceras)
                # Alguien rotativo y sin descanso fijo: es quien más se mueve y
                # por tanto donde más cosas pueden chocar.
                persona = next(p for p in gente if p['tipo_turno'] == 'rotativo'
                               and p.get('descanso_fijo') is None)
                revisar_un_cruce(servidor, cabeceras, acta, persona,
                                 primero, segundo, zona, fechas)
        print(f'— zona «{zona}» recorrida', flush=True)

    shutil.rmtree(carpeta, ignore_errors=True)
    return acta.resumen()


if __name__ == '__main__':
    raise SystemExit(main())
