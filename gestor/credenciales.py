# -*- coding: utf-8 -*-
"""El permiso de lectura con el que se bajan las versiones nuevas.

El repositorio de este programa es **privado**: dentro están los nombres y los
horarios de la oficina, y no tienen por qué estar a la vista de internet. Pero un
repositorio privado no deja bajar nada a quien no se identifique, así que el
instalador viaja con un permiso de solo lectura para ese repositorio y nada más.

## Esto no es un secreto, y hay que decirlo claro

Cualquiera que tenga el programa instalado puede sacar este archivo de la carpeta
y leer el permiso. No hay forma de evitarlo: un programa que se actualiza solo
tiene que llevar encima con qué identificarse, y lo que lleva encima se puede
mirar. Quien intente esconderlo mejor solo consigue que el siguiente que lo lea
tarde diez minutos más.

Lo que sí se consigue, y es lo que se buscaba, es que **nadie pueda mirar el
repositorio sin tener antes el programa instalado**. No se puede encontrar
buscando, ni clonar, ni indexar. Y quien tenga el programa instalado ya tiene la
nómina dentro de él, así que el permiso no le enseña nada que no tuviera.

Por eso el permiso tiene que ser lo más pequeño que GitHub permita: **solo
lectura, solo de este repositorio**. Uno más ancho convertiría una molestia en un
problema de verdad.

## Dónde vive

En un archivo suelto dentro del programa instalado, no dentro del código. Así el
permiso se cambia sin volver a compilar nada, y sobre todo **no está en el
repositorio**: lo escribe el empaquetado en el momento de construir, leyéndolo de
un secreto de GitHub Actions.

Sin el archivo el programa funciona igual: comprueba, no puede identificarse y lo
dice. Nunca deja de arrancar por esto.

## La fecha de caducidad, que es la trampa de verdad

Estos permisos caducan —un año como mucho—, y el día que caduque las
actualizaciones dejan de llegar. Sin más. Nadie ve un error, porque nadie está
mirando: sencillamente no vuelve a aparecer una versión nueva nunca, y eso puede
tardar meses en notarse.

Por eso junto al permiso se guarda su fecha de caducidad, y la aplicación avisa
**antes** de que llegue. Es la mitad más importante de este archivo.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from gestor import rutas

#: El archivo que escribe el empaquetado. No está en el repositorio.
ARCHIVO = rutas.RAIZ_PROGRAMA / 'permiso_actualizaciones.json'

#: Con cuánta antelación se empieza a avisar de que el permiso va a caducar.
#: Treinta días es tiempo de sobra para renovarlo sin prisas, y poco como para
#: que el aviso no se convierta en parte del paisaje.
DIAS_DE_AVISO = 30


class Permiso:
    """Lo que hay en el archivo, o la ausencia de él, contestando preguntas."""

    def __init__(self, token: str = '', caduca: Optional[str] = None):
        self.token = token or ''
        self.caduca = caduca or ''

    # ------------------------------------------------------------ leerlo

    @classmethod
    def leer(cls, archivo: Optional[Path] = None) -> 'Permiso':
        """Nunca lanza. Un permiso ilegible es un permiso que no hay."""
        ruta = archivo or ARCHIVO
        try:
            datos = json.loads(ruta.read_text(encoding='utf-8'))
        except Exception:                                          # noqa: BLE001
            return cls()
        if not isinstance(datos, dict):
            return cls()
        return cls(str(datos.get('token') or ''), str(datos.get('caduca') or ''))

    # --------------------------------------------------------- preguntas

    def __bool__(self) -> bool:
        return bool(self.token)

    def _fecha(self) -> Optional[date]:
        try:
            return date.fromisoformat(self.caduca)
        except ValueError:
            return None

    def dias_que_le_quedan(self, hoy: Optional[date] = None) -> Optional[int]:
        """Los días hasta que caduque, o `None` si no se sabe cuándo."""
        fin = self._fecha()
        if fin is None:
            return None
        return (fin - (hoy or date.today())).days

    def caducado(self, hoy: Optional[date] = None) -> bool:
        quedan = self.dias_que_le_quedan(hoy)
        return quedan is not None and quedan < 0

    def aviso(self, hoy: Optional[date] = None) -> str:
        """Lo que hay que contarle a quien usa el programa, o cadena vacía.

        Se escribe para alguien que no sabe qué es un token ni tiene por qué
        saberlo: se le dice qué va a dejar de pasar y a quién avisar, no cómo se
        renueva un permiso de GitHub.
        """
        if not self.token:
            return ''
        quedan = self.dias_que_le_quedan(hoy)
        if quedan is None:
            return ''
        if quedan < 0:
            return ('El permiso para buscar versiones nuevas caducó el '
                    f'{self.caduca}. La aplicación sigue funcionando igual, pero '
                    'ya no se entera de las actualizaciones. Avisa a quien la '
                    'mantiene para que publique una versión con el permiso '
                    'renovado.')
        if quedan <= DIAS_DE_AVISO:
            cuando = 'hoy' if quedan == 0 else (
                'mañana' if quedan == 1 else f'en {quedan} días')
            return (f'El permiso para buscar versiones nuevas caduca {cuando} '
                    f'({self.caduca}). Cuando caduque, la aplicación dejará de '
                    'enterarse de las actualizaciones. Avisa a quien la mantiene.')
        return ''

    # --------------------------------------------------------- escribirlo

    @classmethod
    def escribir(cls, token: str, caduca: str, archivo: Optional[Path] = None) -> Path:
        """Lo usa el empaquetado. La fecha va en formato 2027-03-15."""
        if token and caduca:
            date.fromisoformat(caduca)      # que reviente aquí y no dentro de un año
        ruta = archivo or ARCHIVO
        ruta.write_text(
            json.dumps({'token': token, 'caduca': caduca}, indent=2),
            encoding='utf-8')
        return ruta


def caducidad_por_defecto(hoy: Optional[date] = None) -> str:
    """Un año menos un día: el máximo que GitHub da a un permiso de estos."""
    return ((hoy or date.today()) + timedelta(days=364)).isoformat()


def permiso() -> Permiso:
    """El permiso de esta instalación. Se lee cada vez, que es barato.

    Se lee cada vez a propósito: así renovarlo es dejar el archivo nuevo en su
    sitio, sin reiniciar nada.
    """
    return Permiso.leer()
