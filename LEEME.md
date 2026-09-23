# Gestor de Horarios

Programación de turnos por semanas completas para una oficina de tres áreas
—Gestión Social, Atención al Ciudadano y Comunicaciones—. Se instala en Windows,
se abre como un programa de escritorio y guarda todo en el equipo: no hay
servidor al que conectarse ni cuenta que crear fuera.

Versión **4.3.2**. Construcción y recuperación de datos: [entrega de Windows](docs/ENTREGA_WINDOWS.md).
Diagnóstico y aceptación manual: [guía de Windows](docs/SOLUCION_WINDOWS.md).
Arquitectura y alcance: [refactorización](docs/ARQUITECTURA.md). Todo —código, comentarios, pruebas y pantalla— está escrito
en castellano, a propósito: lo mantiene y lo lee gente que trabaja en castellano.

## La idea que hay que entender antes que nada

**Un mes no es un mes.** Es el conjunto de **semanas completas** que le
corresponden, de lunes a domingo, y por eso dos meses seguidos comparten días.

```
octubre de 2026   →   28 de septiembre  ...  1 de noviembre
noviembre de 2026 →   26 de octubre     ...  6 de diciembre
```

El 27 de octubre pertenece a los dos. Casi todo lo raro que hace este programa
—que aprobar una novedad marque dos meses como desactualizados, que al publicar
noviembre haya días que ya vienen decididos y bloqueados— sale de aquí. Un turno
no se parte por la mitad de una semana porque el calendario cambie de página.

## Cómo se usa

1. **Personal** — quién trabaja, en qué área, con qué tipo de turno y desde
   cuándo. Nadie desaparece del historial: quien se va se retira, no se borra.
2. **Solicitudes** — vacaciones, permisos, incapacidades, capacitaciones,
   cambios entre compañeros. Nacen pendientes; aprobarlas es una decisión aparte
   y solo entonces condicionan el horario.
3. **Asignaciones** — lo que la oficina impone: una actividad, una jornada
   administrativa, un descanso extra.
4. **Horario** — se generan varias opciones del mes. Ninguna reemplaza sola a la
   que estaba: se revisa, se elige y se marca como oficial.
5. **Modificar** — retocar un día concreto a mano, con el diagnóstico delante de
   qué reglas se saltan y por qué.
6. **Validación** — qué cumple y qué no, con el nombre de cada regla y qué hacer.
7. **Historial** y **Configuración** — quién hizo qué, y las reglas, los
   festivos, la apariencia, las cuentas y las copias de seguridad.

Al final sale un Excel con el formato que la oficina ya usaba.

## Las reglas, en una página

* **Cobertura mínima por área y franja.** Cuántas personas tienen que estar en
  mañana y en tarde. Se configura por área y rige desde una fecha: octubre se
  sigue midiendo con la regla que tenía octubre aunque hoy sea otra.
* **La válvula.** Un mínimo nunca puede exigir a toda el área a la vez
  —`exigido = min(pedido, operativos − 1)`—, porque entonces nadie podría
  descansar y el mes entero saldría incumpliendo.
* **Solo ADM-GS cubre turno.** La jornada administrativa de Gestión Social
  conserva la franja que esa persona tenía y por eso releva. **ADM-AC no cubre
  nada**: es el horario propio y permanente de Atención al Ciudadano.
* **Un descanso por semana**, y el máximo de jornadas seguidas configurable.
* **De la tarde a la mañana siguiente, no.**
* **Las parejas nunca coinciden en la misma franja**: para eso son parejas.
* **El último viernes del mes** es jornada administrativa para todo el personal…
  salvo que sea festivo, y entonces manda el festivo. Navidad de 2026 y el
  Viernes Santo de 2027 caen justo ahí.
* **Compensatorio por festivo trabajado.**

Cada una está escrita, con su nivel y con qué hacer cuando no se cumple, en
`gestor/dominio/catalogo.py`, que es lo que la pantalla enseña.

## Cómo está montado

| Carpeta | Qué hay |
| --- | --- |
| `gestor/dominio/` | Las reglas y el calendario. Nada de aquí sabe que existe una base de datos ni una pantalla. |
| `gestor/motor/` | El reparto de turnos. Portado sin tocar una coma desde la versión anterior, para poder comparar línea a línea que sigue haciendo lo mismo. |
| `gestor/servicios/` | Lo que coordina: generar, publicar, editar, exportar, avisar de meses desactualizados. |
| `gestor/datos/` | SQLite y el esquema. |
| `gestor/web/` | La API, y la traducción de cualquier error a castellano. |
| `gestor/pantalla/` | La interfaz: un HTML y catorce archivos de JavaScript, sin ningún framework. |
| `pruebas/` | pytest, pieza por pieza. |
| `qa/` | Las pruebas que levantan la aplicación de verdad y la usan. Tienen su propio [LEEME](qa/LEEME.md). |
| `empaquetado/` | El instalador de Windows: PyInstaller y Velopack. |

## Ponerlo en marcha

```bash
pip install -r requisitos.txt
python -m gestor.principal          # abre la ventana de escritorio
```

Para verlo en un navegador, sin la ventana:

```bash
python -m uvicorn gestor.web.aplicacion:app --port 8000
```

La carpeta de datos se puede mover con la variable `GESTOR_DATOS`; es lo que
hacen las pruebas para no tocar la instalación real.

## Comprobar que sigue bien

```bash
ruff check .                  # el estilo, con las reglas de pyproject.toml
python -m pytest              # las pruebas rápidas
python -m pytest --lentas     # también las que generan meses enteros
python qa/reglas.py           # cada norma, sobre cada opción de seis meses
python qa/interfaz.py         # todos los botones, todos los formularios
```

`qa/LEEME.md` explica qué hace cada suite y por qué hay dos que parecen la misma.

Y el propio programa se comprueba a sí mismo:

```bash
python -m gestor.principal --comprobar      # o GestorHorarios.exe --comprobar
```

Arranca otro proceso del programa sobre una carpeta temporal y contesta en diez
segundos si está entero: la pantalla, los datos iniciales, los meses base, el
acceso, la ruta que recibe una copia de seguridad y el permiso de
actualizaciones. Existe porque hay una familia de fallos que no se ve de ninguna
otra forma —PyInstaller no encuentra una pieza que se carga por nombre, lo anota
en una línea entre veinte mil y **termina con éxito**—, y el empaquetado la
ejecuta al terminar: si no pasa, no se llega a hacer el instalador.

Lo que no se puede comprobar desde aquí —el candado entre procesos, los diálogos
nativos de Windows, instalar una versión encima de otra y el desinstalador— está
en [`empaquetado/EN_WINDOWS.md`](empaquetado/EN_WINDOWS.md), como una lista para
ir marcando.

## Los dos meses que nunca se generan

`gestor/dominio/calendario.MESES_BASE` fija agosto y septiembre de 2026 como
**meses base**: están transcritos del Excel real de la oficina, no los produce el
programa, y no se regeneran, ni se reinician, ni se marcan como desactualizados.
Son el punto de partida del que cuelga todo lo demás; el primer mes generado de
verdad es octubre de 2026.

## Actualizaciones

El programa comprueba solo si hay una versión nueva y se actualiza sin perder los
datos. El número de versión vive en un único archivo, `gestor/version.py`, y una
prueba comprueba que no vuelva a aparecer escrito a mano en ningún otro sitio:
en la versión anterior estaba en ocho, y llegó a pasar que el instalador
anunciaba una versión y la aplicación decía otra.

El repositorio es **público**, así que el programa instalado no lleva ninguna
credencial encima: cualquiera puede preguntar si hay una versión nueva y la
respuesta es de verdad.

## Las dieciocho personas de este repositorio no existen

Dentro de esta aplicación viven los nombres, los horarios y las reglas
particulares de dieciocho compañeros de una oficina. Eso no tiene por qué estar
en internet, así que **lo que hay escrito en `datos_iniciales/` es una plantilla
inventada**: sirve para clonar el proyecto y verlo funcionar, y no dice nada de
nadie. Ninguno de esos nombres comparte una sola palabra con los reales.

La plantilla de verdad viaja en el secreto `GESTOR_NOMINA` del repositorio y se
aplica al construir. Si falta, la construcción se detiene: no se entrega un instalador de ejemplo. La plantilla inicial no contiene las solicitudes ni los ajustes guardados posteriormente; ese trabajo se recupera restaurando la base anterior. Así, el instalador que llega a la oficina sigue trayendo
su gente y sus dos meses base. Se prepara así, en el equipo donde esté la carpeta
`nomina/` —que está en `.gitignore`—:

```bash
python empaquetado/plantilla.py --empaquetar
```

Lo mismo pasa con las **reglas internas**: «que Fulana no libre sola», «que estos
dos no coincidan». Dicen quién y por qué, y eso es asunto de la oficina. Estaban
escritas en `gestor/dominio/internas.py` y ahora se leen de `reglas_internas.json`,
que viaja con la nómina. De fábrica no hay ninguna.

`pruebas/test_privacidad.py` comprueba que no se haya colado ningún nombre real
en el repositorio, palabra por palabra y contra la lista de verdad. Se cuela con
toda naturalidad —en el comentario que explica una regla, en la persona de
mentira de una prueba— y una vez empujado a un repositorio público, borrarlo
después no lo deshace.

## Al desinstalar

Pregunta si borrar los datos, con el **«no» seleccionado**. Si no hay nadie a
quien preguntar —una desinstalación silenciosa— no borra nada. Conservar de más
es un fastidio; borrar de más no tiene arreglo.
