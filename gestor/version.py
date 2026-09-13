# -*- coding: utf-8 -*-
"""La versión, escrita una sola vez.

En la aplicación anterior el número de versión estaba a mano en ocho sitios —el
motor, la salud, el instalador, la firma del ejecutable, el nombre del archivo
que sale, el README y las direcciones del CSS— y cada uno se actualizaba por
separado. Llegó a pasar que el instalador anunciaba una versión y la aplicación
decía otra, y el número binario del ejecutable se quedó cinco versiones atrás
sin que nadie lo notara, porque solo se ve abriendo las propiedades del archivo
en Windows.

Aquí se escribe una vez. Todo lo demás la lee: el empaquetado la inyecta en el
instalador y en la firma, la pantalla la pide al servidor, y una prueba
comprueba que no ha vuelto a aparecer escrita a mano en ningún otro sitio.
"""
from __future__ import annotations

NOMBRE = 'Gestor de Horarios'
VERSION = '4.0.0'
AUTOR = 'xYojanSaidx'

#: El identificador del producto para Velopack y para Windows. No cambia nunca:
#: es lo que hace que instalar encima se entienda como actualizar y no como una
#: segunda copia.
ID_APLICACION = 'GestorHorarios'

#: De dónde se bajan las versiones nuevas.
REPOSITORIO = 'YojanSaid1050/GestorHorarios'

#: ¿Hace falta identificarse para bajar una versión de ahí?
#:
#: Hoy **no**: el repositorio es público y el programa instalado no lleva ninguna
#: credencial encima. Lo que vive en el repositorio son dieciocho personas
#: inventadas; la plantilla de verdad viaja aparte y se aplica al construir.
#:
#: Si algún día se hiciera privado, esto pasa a `True` y el instalador tiene que
#: llevar un permiso de solo lectura dentro (ver `gestor/credenciales.py`). El
#: interruptor existe porque la diferencia no es cosmética: con el repositorio
#: privado y sin permiso, GitHub contesta que no existe —igual que si estuviera
#: vacío—, y el programa se quedaría diciendo para siempre que ya está al día.
REPOSITORIO_PRIVADO = False


def numeros() -> tuple[int, int, int]:
    partes = VERSION.split('.')
    return int(partes[0]), int(partes[1]), int(partes[2])


def como_dict() -> dict:
    return {
        'nombre': NOMBRE,
        'version': VERSION,
        'autor': AUTOR,
        'id_aplicacion': ID_APLICACION,
    }
