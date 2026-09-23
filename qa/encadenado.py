# -*- coding: utf-8 -*-
"""Seis meses seguidos, auditados uno a uno contra el enunciado de las reglas.

Es la prueba que más se parece a lo que hace la oficina de verdad: generar
octubre, elegirlo, publicarlo, y con eso encima generar noviembre. Cada mes
hereda la última semana del anterior, así que un fallo de continuidad no aparece
en el mes donde se produce sino tres meses después.

Cada mes se revisa con el **auditor independiente**, que no llama a la
validación del motor: vuelve a implementar cada norma desde su enunciado. Si el
motor y su propia validación estuvieran mal de la misma manera —que es lo que
pasa cuando alguien «arregla» la validación para que acepte lo que el motor
produce— las pruebas normales seguirían en verde y esto no.

Se ejecuta contra el servidor de verdad, por las mismas direcciones que usa la
pantalla. Así se comprueban a la vez el motor, las rutas y el encaje entre los
dos.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from pruebas.auditor import auditar  # noqa: E402
from qa.servidor import Servidor, entrar_como_admin  # noqa: E402

MESES = [(2026, 10), (2026, 11), (2026, 12), (2027, 1), (2027, 2), (2027, 3)]


def reglas_vigentes_en(servidor, cabeceras, anio, mes) -> dict:
    """El reparto que regía en ese mes, no el de hoy.

    Es la misma idea que sostiene toda la aplicación: un mes se mide con las
    reglas con las que se hizo. Preguntando por «la vigente» a secas, un cambio
    de reparto hecho en diciembre convertía en incumplimientos los horarios
    correctos de octubre y noviembre, y el auditor denunciaba un fallo que no
    existía.
    """
    from gestor.dominio import calendario

    inicio = calendario.rango(int(mes), int(anio))[0].isoformat()
    estado, datos = servidor.pedir('/api/configuracion/reglas-cobertura',
                                   cabeceras=cabeceras)
    assert estado == 200, datos
    por_area = {}
    for area in datos['areas']:
        anteriores = [r for r in area['historial'] if r['vigente_desde'] <= inicio]
        elegida = anteriores[-1] if anteriores else area['vigente']
        if elegida:
            por_area[area['area']] = elegida
    return por_area


def revisar_un_mes(servidor, cabeceras, anio, mes, fallos_totales) -> bool:
    """Genera, elige, publica y audita. Devuelve si el mes quedó limpio."""
    inicio = time.time()
    estado, generado = servidor.pedir('/api/horarios/generar', 'POST',
                                      {'mes': mes, 'anio': anio}, cabeceras)
    if estado != 200:
        print(f'  {anio}-{mes:02d}  NO SE PUDO GENERAR: {generado.get("detail")}')
        return False
    alternativas = generado['alternativas']
    print(f'  {anio}-{mes:02d}  {len(alternativas)} propuestas '
          f'({round(time.time() - inicio, 1)} s)', flush=True)

    reglas = reglas_vigentes_en(servidor, cabeceras, anio, mes)
    limpio = True
    for numero, alternativa in enumerate(alternativas, start=1):
        fallos = auditar(alternativa['horario'], reglas)
        propios = [f for f in fallos if '(heredado)' not in f[0]]
        heredados = [f for f in fallos if '(heredado)' in f[0]]
        marca = 'ok ' if not propios else 'MAL'
        detalle = f'{len(heredados)} heredado(s)' if heredados else ''
        print(f'      opción {numero}: {marca} '
              f'{len(propios)} incumplimiento(s) propios  {detalle}')
        for norma, texto in propios[:6]:
            print(f'          · {norma}: {texto}')
        if propios:
            limpio = False
            fallos_totales.extend(propios)

    elegida = next((a for a in alternativas if a['valido']), alternativas[0])
    estado, _ = servidor.pedir(f'/api/horarios/{elegida["horario_id"]}/oficial',
                               'PATCH', None, cabeceras)
    assert estado == 200
    estado, publicado = servidor.pedir(
        f'/api/operacion/publicacion/{elegida["horario_id"]}', 'POST',
        {'confirmar_excepciones': True}, cabeceras)
    if estado != 200:
        print(f'      NO SE PUDO PUBLICAR: {publicado.get("detail")}')
        return False
    resumen = publicado['resumen']
    print(f'      publicado · aceptadas: {len(resumen["incidencias_aceptadas"])}'
          f' · bloqueantes: {sum(resumen["conteos"].values())}')
    for x in resumen['incidencias_aceptadas'][:4]:
        print(f'          (aceptado) {x.get("motivo")}: {x.get("detalle")}')
    return limpio


def main() -> int:
    fallos: list = []
    with Servidor('/tmp/qa_encadenado') as servidor:
        cabeceras = entrar_como_admin(servidor)
        print(f'Servidor en {servidor.base}\n')
        print('Seis meses encadenados, cada uno auditado contra el enunciado:\n')
        limpios = 0
        for anio, mes in MESES:
            if revisar_un_mes(servidor, cabeceras, anio, mes, fallos):
                limpios += 1
            print()

    print(f'{limpios}/{len(MESES)} meses sin ningún incumplimiento propio.')
    if fallos or limpios != len(MESES):
        print(f'\n{len(fallos)} incumplimiento(s) en total:')
        for norma, texto in fallos[:25]:
            print(f'  · {norma}: {texto}')
        return 1
    print('Ninguna regla incumplida en ninguna de las opciones de ningún mes.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
