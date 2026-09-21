# Corrección de compilación de Inno Setup — 4.3.1

Base: main `e02173b`. La versión sigue siendo 4.3.1: el intento anterior no llegó
a generar el asistente final.

## Causa del error

El registro informa «'BEGIN' expected» en la línea 1 de `destino_seguro.iss`.
Sus dos primeras líneas empezaban por `;`, una sintaxis de comentario de las
secciones declarativas de Inno. Este archivo se incluye dentro de `[Code]`,
donde se interpreta Pascal Script. Los comentarios se corrigieron a `//`.
El error estaba en el código entregado, no en la instalación de Inno ni en vpk.
Velopack había terminado correctamente antes de que Inno rechazara el script.

## Cambios

- Corregidos los dos comentarios; no se cambió la lógica de destinos.
- Añadida una prueba de regresión que detecta este uso de comentarios en Pascal.
  La prueba falló con las líneas anteriores y pasó después de corregirlas.
- Añadido `empaquetado/comprobar_sintaxis_inno.py` a ambos workflows. Después de
  preparar Inno, compila el asistente completo antes de construir la aplicación.
  Utiliza Python.exe únicamente como archivo de relleno para [Files]. No ejecuta
  el instalador generado y lo elimina al terminar.
- Se mantienen `CreateAppDir=yes`, la selección de carpeta y todas las
  protecciones de destino de 4.3.1. No vuelvas a usar el instalador 4.3.0.

## Validación

12 pruebas específicas aprobadas, Ruff correcto, YAML y orden de los pasos
comprobados. No se repitió la batería funcional completa porque esta corrección
no cambia funciones de la aplicación. La compilación nativa de Inno y las pruebas
de instalación real deben pasar en Windows; no se ejecutaron en este Linux.

## Aplicar y ejecutar

1. Copia los archivos del ZIP de corrección conservando las carpetas, incluidas
   `.github/workflows`. Si tienes cambios posteriores a `e02173b`, integra el diff.
2. Guarda y sube un commit nuevo a main.
3. Actions → Revisar refactorización e instalador → Run workflow → main.
   Inicia una ejecución nueva; no repitas la ejecución del commit anterior.
4. Deben pasar «Compilar el asistente antes de construir la aplicación» y, al
   final, «Probar destinos e instalación real del asistente».
5. Descarga el artefacto GestorHorarios-revision-Windows únicamente cuando pase
   el workflow completo. El nombre esperado sigue siendo
   `GestorHorarios-Instalar-4.3.1.exe`.

El ZIP completo es una alternativa al ZIP de corrección; no necesitas aplicar
ambos. Esta entrega contiene código fuente, no un instalador ya compilado.

Referencia: [Inno Setup, sección Code y Pascal Script](https://jrsoftware.org/ishelp/topic_scriptcreating.htm).
