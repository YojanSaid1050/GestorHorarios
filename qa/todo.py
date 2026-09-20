# -*- coding: utf-8 -*-
"""La batería entera, de una vez, con un veredicto al final.

En este orden, porque cada tanda tarda más que la anterior y no tiene sentido
abrir un navegador si las pruebas de Python ya han fallado:

1. **ruff** — que el código esté limpio;
2. **pytest --lentas** — todas las pruebas, incluidas las que generan meses;
3. **encadenado** — seis meses reales, uno sobre otro, auditados;
4. **reglas** — cada norma, comprobada desde su enunciado sobre cada opción de
   cada mes, con el número de casos revisados delante;
5. **combinaciones** — lo que pasa entre piezas cuando algo cambia debajo;
6. **pantalla**, **interfaz**, **ventana** y **visual** — la aplicación usada con
   un navegador: los caminos, todos los botones y formularios, la barra de la
   ventana conducida con el ratón, y que todo se lea.

Se ejecutan **todas** aunque una falle. Pararse en la primera esconde las demás,
y lo que hace falta al terminar una tanda de cambios es la lista completa de lo
que quedó roto, no el primer síntoma.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

TANDA = [
    ('el código está limpio', [sys.executable, '-m', 'ruff', 'check', '.']),
    ('las pruebas de Python', [sys.executable, '-m', 'pytest', '--lentas', '-q']),
    ('seis meses encadenados', [sys.executable, 'qa/encadenado.py']),
    ('cada norma, número a número', [sys.executable, 'qa/reglas.py']),
    ('cambios sobre meses ya hechos', [sys.executable, 'qa/combinaciones.py']),
    ('la aplicación usada con un navegador', [sys.executable, 'qa/pantalla.py']),
    ('todos los botones y formularios', [sys.executable, 'qa/interfaz.py']),
    ('la barra propia de la ventana', [sys.executable, 'qa/ventana.py']),
    ('cada novedad cruzada con cada otra', [sys.executable, 'qa/cruces.py']),
    ('que todo se lea, en claro y en oscuro', [sys.executable, 'qa/visual.py']),
]


def main() -> int:
    resultados = []
    for titulo, orden in TANDA:
        print(f'\n{"=" * 72}\n  {titulo}\n{"=" * 72}', flush=True)
        empezó = time.time()
        proceso = subprocess.run(orden, cwd=RAIZ, capture_output=True, text=True)
        salida = (proceso.stdout or '') + (proceso.stderr or '')
        # De lo que sale bien basta el final; de lo que falla hace falta todo.
        print(salida if proceso.returncode else '\n'.join(salida.splitlines()[-12:]))
        resultados.append((titulo, proceso.returncode == 0, round(time.time() - empezó)))

    print(f'\n{"=" * 72}\n  RESUMEN\n{"=" * 72}')
    for titulo, bien, segundos in resultados:
        print(f'  [{"ok  " if bien else "FALLA"}] {titulo:44s} {segundos:4d} s')
    fallidas = [t for t, bien, _ in resultados if not bien]
    if fallidas:
        print(f'\n{len(fallidas)} de {len(resultados)} tandas con fallos: '
              + ', '.join(fallidas))
        return 1
    print('\nTodo en verde.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
