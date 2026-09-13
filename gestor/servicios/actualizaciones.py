# -*- coding: utf-8 -*-
"""Comprobar, descargar e instalar una versión nueva desde internet.

Tres pasos, y cada uno lo pide una persona. **No se encadenan solos a
propósito**: que el programa se reemplace a sí mismo mientras alguien está
armando el horario de un mes sería la peor sorpresa posible.

Por debajo trabaja Velopack, y eso resuelve el fallo que la versión anterior no
podía resolver por más Pascal que se le escribiera. El instalador de antes
sobrescribía el ejecutable en su sitio: si el archivo estaba en uso o un
antivirus lo bloqueaba, la copia fallaba, la instalación continuaba y terminaba
diciendo «completada» con el programa viejo todavía en la carpeta. Velopack
coloca cada versión en su propia carpeta y solo al final cambia cuál es la
buena, así que una actualización o está entera o no está.

Dos cosas que este módulo se toma en serio:

* **Sin internet la aplicación funciona igual.** Comprobar si hay novedad es una
  comodidad, no un requisito para trabajar. Todo lo que puede fallar por la red
  se devuelve como «no pude comprobar, y este es el motivo», nunca como una
  excepción que suba hasta la pantalla.
* **Fuera de una instalación de verdad no se inventa nada.** En desarrollo, en
  las pruebas o si alguien ejecuta el .exe portable, Velopack no está
  gobernando nada; se dice eso mismo en vez de fingir que hay actualizaciones.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Optional

from gestor import credenciales
from gestor.version import REPOSITORIO, REPOSITORIO_PRIVADO, VERSION

registro = logging.getLogger(__name__)

#: Cuánto se recuerda una consulta antes de volver a preguntar. La API de
#: GitHub sin credenciales tiene cuota, y gastarla en cada arranque no aporta
#: nada: una versión nueva no aparece dos veces en la misma mañana.
MEMORIA_SEGUNDOS = 6 * 60 * 60


@dataclass
class Novedad:
    """Lo que la pantalla necesita saber para contarlo."""

    version_instalada: str = VERSION
    hay_novedad: bool = False
    version_publicada: Optional[str] = None
    motivo: str = ''
    notas: str = ''
    descargada: bool = False
    #: Cierto cuando la aplicación no está bajo una instalación gobernada por
    #: Velopack: desarrollo, pruebas o ejecutable suelto.
    sin_instalador: bool = False
    avisos: list[str] = field(default_factory=list)

    def como_dict(self) -> dict:
        return {
            'version_instalada': self.version_instalada,
            'hay_novedad': self.hay_novedad,
            'version_publicada': self.version_publicada,
            'motivo': self.motivo,
            'notas': self.notas,
            'descargada': self.descargada,
            'sin_instalador': self.sin_instalador,
            'avisos': list(self.avisos),
        }


class Actualizaciones:
    """La conversación con el canal de versiones, guardada en un objeto.

    Es una clase y no cuatro funciones sueltas porque hay estado que dura entre
    llamadas —lo último que se consultó y lo que ya está descargado— y tenerlo
    en variables de módulo fue justo lo que obligó, en la versión anterior, a
    escribir una función `olvidar_lo_consultado()` solo para las pruebas.
    """

    def __init__(self, repositorio: str = REPOSITORIO, reloj=None, permiso=None):
        self.repositorio = repositorio
        #: El permiso de lectura del repositorio privado. Se lee una vez al
        #: construir el objeto y se puede sustituir en las pruebas.
        self._permiso = permiso if permiso is not None else credenciales.permiso()
        self._reloj = reloj or __import__('time').monotonic
        self._candado = threading.Lock()
        self._ultima: Optional[Novedad] = None
        self._consultada_en: float = 0.0
        self._pendiente = None          # el paquete ya descargado, si lo hay
        self._gestor = None
        self._gestor_probado = False

    # ------------------------------------------------------------ velopack

    def _obtener_gestor(self):
        """El `UpdateManager` de Velopack, o `None` si no hay instalación.

        Se intenta una sola vez. Si la biblioteca no está —correr el código a
        pelo en Linux, por ejemplo— o si esta copia no la gobierna Velopack, se
        recuerda que no y no se vuelve a intentar en cada consulta.
        """
        if self._gestor_probado:
            return self._gestor
        self._gestor_probado = True
        try:
            from velopack import GithubSource, UpdateManager
        except Exception as exc:                                  # noqa: BLE001
            registro.info('Velopack no está disponible aquí: %s', exc)
            return None
        try:
            # El segundo argumento es el permiso de lectura. Va vacío mientras el
            # repositorio sea público y con el permiso puesto cuando es privado,
            # que es como está hoy: sin él, GitHub contesta que ese repositorio
            # no existe —no que no se tiene permiso—, y el programa se quedaría
            # diciendo para siempre que ya tiene la última versión.
            fuente = GithubSource(f'https://github.com/{self.repositorio}',
                                  self._permiso.token, False)
            self._gestor = UpdateManager(fuente)
        except Exception as exc:                                  # noqa: BLE001
            registro.info('esta copia no está instalada con Velopack: %s', exc)
            self._gestor = None
        return self._gestor

    def esta_instalada(self) -> bool:
        return self._obtener_gestor() is not None

    def version_en_uso(self) -> str:
        gestor = self._obtener_gestor()
        if gestor is None:
            return VERSION
        try:
            return str(gestor.get_current_version() or VERSION)
        except Exception:                                          # noqa: BLE001
            return VERSION

    # ----------------------------------------------------------- comprobar

    def consultar(self, forzar: bool = False) -> Novedad:
        """¿Hay una versión nueva publicada? No descarga nada."""
        with self._candado:
            if (not forzar and self._ultima is not None
                    and self._reloj() - self._consultada_en < MEMORIA_SEGUNDOS):
                return self._ultima
            novedad = self._consultar_de_verdad()
            self._ultima = novedad
            self._consultada_en = self._reloj()
            return novedad

    def _avisos(self) -> list[str]:
        """Lo del permiso, que hay que decir salga lo que salga la consulta.

        Va aparte del `motivo` a propósito: el motivo cuenta el resultado de esta
        consulta —«tienes la última»— y el aviso cuenta algo que va a pasar más
        adelante. Metiéndolos en el mismo sitio, el aviso de caducidad
        desaparecía justo cuando todo iba bien, que es cuando hace falta.
        """
        aviso = self._permiso.aviso()
        return [aviso] if aviso else []

    def _consultar_de_verdad(self) -> Novedad:
        instalada = self.version_en_uso()
        avisos = self._avisos()
        gestor = self._obtener_gestor()
        if gestor is None:
            return Novedad(
                version_instalada=instalada, sin_instalador=True, avisos=avisos,
                motivo=('Esta copia no se instaló con el instalador, así que no se '
                        'actualiza sola. Descarga la versión nueva desde la página '
                        'del proyecto.'))
        if REPOSITORIO_PRIVADO and self._permiso.caducado():
            # Preguntar con un permiso caducado no devuelve un error: GitHub
            # contesta que el repositorio no existe, y eso aquí se leería como
            # «no hay nada nuevo». Es exactamente la forma que tiene esto de
            # fallar en silencio, así que ni se pregunta.
            return Novedad(
                version_instalada=instalada, avisos=avisos,
                motivo=('No se pudo comprobar si hay una versión nueva: el permiso '
                        'para consultarlas caducó.'))
        try:
            info = gestor.check_for_updates()
        except Exception as exc:                                   # noqa: BLE001
            registro.info('no se pudo comprobar si hay versión nueva: %s', exc)
            return Novedad(
                version_instalada=instalada, avisos=avisos,
                motivo=f'No se pudo comprobar si hay una versión nueva: {exc}')
        if info is None:
            if REPOSITORIO_PRIVADO and not self._permiso:
                # Con el repositorio privado y sin permiso, GitHub contesta lo
                # mismo que si estuviera vacío. Decir «tienes la última versión»
                # sería inventarse una respuesta que nadie ha dado. Con el
                # repositorio público —que es como está hoy— no hay nada que
                # comprobar: cualquiera puede preguntar y la respuesta es real.
                return Novedad(
                    version_instalada=instalada, avisos=avisos,
                    motivo=('No se pudo comprobar si hay una versión nueva: a esta '
                            'copia le falta el permiso para consultarlas.'))
            return Novedad(version_instalada=instalada, avisos=avisos,
                           motivo='Tienes la última versión publicada.')
        publicada = self._version_de(info)
        return Novedad(
            version_instalada=instalada, hay_novedad=True, avisos=avisos,
            version_publicada=publicada,
            motivo=f'Hay publicada una versión {publicada}.',
            notas=str(getattr(info, 'release_notes', '') or ''),
            descargada=self._pendiente is not None)

    @staticmethod
    def _version_de(info) -> str:
        for camino in ('target_full_release', 'TargetFullRelease'):
            paquete = getattr(info, camino, None)
            version = getattr(paquete, 'version', None)
            if version:
                return str(version)
        return str(getattr(info, 'version', '') or 'nueva')

    # ----------------------------------------------------------- descargar

    def descargar(self, al_avanzar=None) -> dict:
        """Baja la versión nueva y la deja lista, sin instalarla todavía."""
        gestor = self._obtener_gestor()
        if gestor is None:
            raise RuntimeError(
                'Esta copia no se instaló con el instalador, así que no puede '
                'actualizarse sola.')
        info = gestor.check_for_updates()
        if info is None:
            raise RuntimeError('No hay ninguna versión nueva que descargar.')
        gestor.download_updates(info, al_avanzar) if al_avanzar else gestor.download_updates(info)
        self._pendiente = info
        if self._ultima is not None:
            self._ultima.descargada = True
        version = self._version_de(info)
        return {
            'ok': True,
            'version': version,
            'mensaje': (f'La versión {version} quedó descargada. Cuando la instales, '
                        'la aplicación se cerrará un momento y volverá a abrirse sola.'),
        }

    # ------------------------------------------------------------ instalar

    def instalar(self) -> dict:
        """Aplica lo descargado y reinicia la aplicación.

        Esta llamada no vuelve: Velopack cierra el proceso para cambiar la
        carpeta activa y lo arranca de nuevo. Por eso la pantalla tiene que
        haber avisado antes, y por eso los datos —que viven en otra carpeta— no
        se ven afectados.
        """
        gestor = self._obtener_gestor()
        if gestor is None:
            raise RuntimeError(
                'Esta copia no se instaló con el instalador, así que no puede '
                'actualizarse sola.')
        if self._pendiente is None:
            self._pendiente = gestor.check_for_updates()
        if self._pendiente is None:
            raise RuntimeError('No hay ninguna versión descargada que instalar.')
        gestor.apply_updates_and_restart(self._pendiente)
        return {'ok': True, 'mensaje': 'La aplicación se está reiniciando con la versión nueva.'}


#: La instancia que usa la aplicación. Las pruebas se construyen la suya.
actualizaciones = Actualizaciones()
