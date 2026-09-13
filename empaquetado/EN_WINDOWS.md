# Lo que solo se puede comprobar en Windows

Todo lo demás de este proyecto se comprueba solo: `ruff`, 280 pruebas de pytest,
seis meses encadenados, cada norma sobre cada opción de cada mes, los 57
controles de la pantalla pulsados y el contraste medido en claro y en oscuro. Y
el propio ejecutable se comprueba a sí mismo al construirse.

Queda esto, que necesita un Windows de verdad porque depende de cosas que el
sistema pone y no el programa: el candado entre procesos, los diálogos nativos,
y un instalador reemplazando otro en su sitio.

Son unos veinte minutos. Hazlo **en un equipo que no sea el de la oficina**, o al
menos después de una copia de seguridad: dos de estos pasos borran datos a
propósito.

---

## 0 · Construir

```powershell
pip install -r requisitos.txt
pip install pyinstaller
dotnet tool install -g vpk

$env:GESTOR_NOMINA = "<la linea larga de empaquetado/plantilla.py --empaquetar>"
python empaquetado/construir.py
```

Sin `GESTOR_NOMINA` se construye igual, pero con las dieciocho personas
inventadas: sirve para probar el instalador, **no para la oficina**. El script lo
dice en voz alta al pasar por ahí.

Al terminar, el ejecutable se arranca solo y contesta. **Diez líneas en verde y
«La instalación está entera».** Si alguna sale en rojo, el empaquetado se para
ahí y no llega a hacer el instalador: eso es lo que tiene que pasar.

El instalador queda en `dist\instalador\`.

---

## 1 · Que abra

Ejecuta `GestorHorarios-win-Setup.exe` y espera a que abra la ventana sola.

- [ ] La ventana abre y se ve la pantalla de acceso, no una ventana en blanco.
- [ ] En Personal sale **la gente de verdad de la oficina**, no Ximena Rocío
      Peralta Osorio y compañía. Si salen esos nombres inventados, este
      instalador se construyó sin `GESTOR_NOMINA` y no sirve para entregar.
- [ ] El icono de la barra de tareas es el logo del programa, no el de Python.
- [ ] En las propiedades del `.exe` (clic derecho → Detalles) la versión dice
      **4.0.0**. Es lo que se quedó cinco versiones atrás en la aplicación
      anterior sin que nadie lo notara.

Entra con `admin`. Genera octubre de 2026 y exporta el Excel: con eso ya has
pasado por casi todo el programa.

## 2 · El candado

Abre el programa otra vez sin cerrar el primero, desde el acceso directo.

- [ ] **No** se abre una segunda ventana.
- [ ] Sale un aviso diciendo que ya está abierto y dónde buscarlo.

Esto no se puede probar en Linux —el candado es un mutex de Windows— y es lo que
impide que dos procesos escriban en la misma base de datos, que es la forma más
rápida de perder un mes de trabajo.

## 3 · «Guardar como»

En Horario, exporta y elige guardar en otra carpeta.

- [ ] Se abre el **diálogo de Windows** de guardar archivo, no una descarga del
      navegador.
- [ ] El archivo aparece donde lo pusiste y Excel lo abre sin quejarse.
- [ ] «Abrir la carpeta de exportaciones» abre el Explorador.

## 4 · Actualizar encima, sin perder nada  ← el importante

Este es el paso que justifica haber cambiado de instalador. El de la versión
anterior sobrescribía el ejecutable en su sitio: si estaba en uso o un antivirus
lo bloqueaba, la copia fallaba, la instalación seguía y terminaba diciendo
«completada» con el programa viejo todavía en la carpeta.

1. Con la versión instalada, **crea datos que reconozcas**: una solicitud de
   vacaciones para alguien y un horario de octubre marcado como oficial.
2. Cambia el número en `gestor/version.py` a `4.0.1` y vuelve a construir.
3. Instala el nuevo encima, sin desinstalar el anterior.

- [ ] Instala sin pedir que cierres nada raro.
- [ ] Al abrir, la versión que se ve es **4.0.1**.
- [ ] **La solicitud y el horario oficial siguen ahí.** Esto es lo que no puede
      fallar: el programa se reemplaza entero y los datos viven en otra carpeta.
- [ ] En Configuración → «Archivos y datos», la carpeta de datos es
      `%LOCALAPPDATA%\GestorHorarios-datos` y la del programa es otra.

## 5 · Que se entere de una versión nueva

Con el repositorio ya subido y una Release publicada:

- [ ] Configuración → Comprobar actualización encuentra la versión publicada.
- [ ] Descargar e instalar deja el programa reiniciado en la versión nueva.

El repositorio es público, así que esto funciona sin ninguna credencial dentro
del programa. Es exactamente lo que se buscaba al hacerlo público.

## 6 · Restaurar una copia

Este botón no funcionó nunca hasta ahora, así que merece una vuelta entera.

1. Configuración → crear copia de seguridad.
2. Retira a alguien del personal.
3. Restaura la copia.

- [ ] Vuelve la persona retirada, y en activo.
- [ ] Te pide entrar otra vez: las sesiones abiertas también estaban en la copia.
- [ ] Elige a mano un archivo que **no** sea una copia —una foto, un Excel—: se
      niega diciendo qué es y **no toca nada**.

## 7 · Desinstalar

Desde Configuración de Windows → Aplicaciones.

- [ ] Pregunta si borrar los datos, y el botón que está marcado por defecto es
      **«No»**.
- [ ] Si no contestas, a los dos minutos se rinde sola y **conserva los datos**.
      Sin ese tope, una desinstalación en un equipo sin nadie delante se queda
      esperando un clic para siempre: es lo que paró tres publicaciones.
- [ ] Contestando «No», la carpeta `%LOCALAPPDATA%\GestorHorarios-datos` sigue
      ahí con todo dentro.
- [ ] Contestando «Sí» (en una instalación de pruebas), la carpeta desaparece.

Conservar de más es un fastidio; borrar de más no tiene arreglo, y por eso el
«no» va marcado.

---

## Si algo sale mal

El programa apunta lo que falla en `%LOCALAPPDATA%\GestorHorarios-datos\registro.log`,
y la pantalla de «Archivos y datos» enseña esa ruta. Es lo primero que hay que
mirar.

Para una respuesta rápida sobre una instalación cualquiera, desde una terminal en
la carpeta del programa:

```powershell
.\GestorHorarios.exe --comprobar
```

Contesta en diez segundos qué está entero y qué falta, sobre una carpeta de datos
temporal: no toca la de la oficina.
