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
VERSION = '4.3.2'
AUTOR = 'xYojanSaidx'

#: El identificador del producto para Velopack y para Windows. No cambia nunca:
#: es lo que hace que instalar encima se entienda como actualizar y no como una
#: segunda copia.
ID_APLICACION = 'GestorHorarios'

#: De dónde se bajan las versiones nuevas.
REPOSITORIO = 'YojanSaid1050/GestorHorarios'

#: ¿Hace falta identificarse para bajar una versión de ahí?
#:
#: Hoy **no**: el repositorio es público, las actualizaciones se bajan sin
#: credenciales y el programa instalado no lleva ninguna encima.
#:
#: ## Lo que hay pendiente aquí, y conviene que esté escrito
#:
#: El instalador que se publica en las Releases lleva dentro `datos_iniciales/`
#: con la plantilla de la oficina, sus dos meses transcritos y las reglas
#: internas con el motivo de cada una al lado. El secreto `GESTOR_NOMINA`
#: protege la **entrada** al empaquetado, no el archivo que sale de él: con el
#: repositorio público, cualquiera puede descargar ese instalador y leerlo.
#:
#: Está decidido dejarlo así por ahora y arreglarlo más adelante. Las dos formas
#: de cerrarlo son poner el repositorio en privado —este interruptor a `True`,
#: y los pasos están en `empaquetado/EN_WINDOWS.md`— o dejar de meter la nómina
#: en el paquete y cargarla desde una copia privada al instalar.
#:
#: El interruptor existe porque la diferencia no es cosmética: con el
#: repositorio privado y sin permiso, GitHub contesta que no existe —igual que
#: si estuviera vacío—, y el programa se quedaría diciendo para siempre que ya
#: está al día. Por eso, con esto en `True`, el empaquetado se **niega a
#: construir** si falta el secreto `GESTOR_PERMISO`.
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
