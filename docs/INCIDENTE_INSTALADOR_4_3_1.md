# Instalador 4.3.1: carpeta de destino y cierre del escritorio

Base de esta corrección: `main`, commit `5e7a6cb`. Se entrega código fuente para
construir un instalador nuevo. No se ha ejecutado Windows en este entorno.

## Lo que demuestra el registro

En los dos intentos adjuntos, el motor Velopack 1.2.0 recibió `C:\WINDOWS` como
destino. WebView2 estaba instalado y el paquete se leyó correctamente.

Velopack trató la carpeta ocupada como una instalación que podía reemplazar.
El registro enumera intentos de cerrar `explorer.exe`, `sihost.exe`, `ShellHost.exe`
y otros procesos de Windows. Después intentó renombrar la carpeta del sistema
para preparar una sustitución. Esa operación falló con «Acceso denegado».

Esto explica la aparente recarga del escritorio descrita por el usuario. El log
no confirma un reinicio del controlador gráfico ni demuestra daño en los archivos
de Windows. Sí prueba que el destino transmitido era incorrecto y peligroso.

## Causa y responsabilidad de la corrección

El asistente tenía `CreateAppDir=no`. En Inno Setup esa opción desactiva la página
de selección de carpeta y hace que `{app}` corresponda a `{win}`. Por tanto,
`DisableDirPage=no` por sí solo no bastaba para mostrarla. Esta configuración
incorrecta estaba en la entrega anterior y debió detectarse antes de entregarla.

Además, la validación de carpeta estaba únicamente en `NextButtonClick` para
una página que el propio asistente omitía. El motor se ejecutaba después sin
volver a comprobar el destino. El workflow probaba el EXE de la aplicación y
compilaba el instalador, pero no ejecutaba una instalación: de ahí el resultado
verde pese al fallo.

## Cambios incluidos

- `CreateAppDir=yes`: restaura la página de destino y la semántica de `{app}`.
- Una comprobación común valida la selección y vuelve a hacerlo en
  `PrepareToInstall`, antes de extraer o ejecutar Velopack. Se exige además que
  la ruta elegida coincida con `{app}`.
- Se rechazan carpetas del sistema, raíces de disco, directorios principales
  del perfil, ubicaciones de datos y sus padres, rutas de red o dispositivo,
  rutas ambiguas y enlaces/uniones de carpetas.
- Una carpeta ocupada solo se acepta si contiene el ejecutable del Gestor,
  `Update.exe` y el manifiesto de Velopack con el identificador correcto.
- Una ruta del registro se conserva para actualizar solo después de validarla.
  Las rutas registradas inválidas se ignoran, sin cambiar el registro del usuario.
- En instalaciones silenciosas los rechazos no abren cuadros esperando un clic.
- La versión sube a **4.3.1** para distinguir el nuevo EXE del defectuoso.

La ubicación predeterminada sigue siendo `%LOCALAPPDATA%\GestorHorarios`.
Los datos continúan separados en `%LOCALAPPDATA%\GestorHorarios-datos`, o en la
ubicación configurada mediante `GESTOR_DATOS`. Para una instalación nueva se puede
elegir otra carpeta local vacía. Para actualizar se muestra y conserva la ruta de
la instalación reconocida; este cambio no añade una función para trasladarla.

## Nueva aceptación automática en Windows

Ambos workflows añaden **Probar destinos e instalación real del asistente**,
después de compilar y antes de entregar o publicar el instalador.

Primero compilan el mismo asistente con un doble inofensivo del motor. Ese doble
solo puede escribir archivos ficticios dentro de su temporal; nunca cierra
procesos ni instala paquetes. Se comprueba:

1. Destino con espacios y acentos, reinstalación reconocida y carpeta vacía.
2. Rechazo de carpetas ajenas sin modificar su contenido.
3. Rechazo de Windows, System32, Program Files, perfil, LocalAppData, datos,
   padre de los datos y raíz de disco, antes de llamar al motor.
4. Rechazo de una unión de carpetas dirigida a Windows.
5. Una entrada de registro de prueba que apunta a Windows se ignora y se respeta
   el destino válido solicitado.

Solo después se ejecuta el instalador real: instalación nueva, reinstalación,
comprobación de ruta registrada, conservación de un archivo testigo de datos
externos y apertura de la ventana del programa instalado. Se exige un informe
de ventana correcto. El script se limita a runners Windows de GitHub Actions y
rechaza un runner que ya tenga una instalación registrada.

Los resultados y registros quedan en `dist/diagnostico/instalador`, dentro del
artefacto de diagnóstico. El instalador no se entrega si falla esta aceptación.
Estas pruebas aún deben ejecutarse en la próxima ejecución de Windows. No cubren
la apariencia en todos los monitores ni la actualización con los datos reales.

## Validación realizada en esta entrega

- Batería completa en Linux: **462 aprobadas, 7 omitidas y 2 advertencias**.
- Pruebas específicas de asistente, sonda y doble del motor: **10 aprobadas**.
- Ruff y comprobación de diferencias: correctos.
- Ambos workflows conservan el orden de empaquetar → probar instalación → entregar.
- Revisadas las constantes y funciones utilizadas frente a las fuentes de Inno.
- La compilación y ejecución del Pascal, la instalación Windows y la revisión
  visual siguen pendientes del workflow y de la prueba en Windows. El resultado
  local no acredita que ya hayan pasado esas etapas nativas.

## Qué hacer en el equipo afectado

1. Cancela el instalador anterior. No lo vuelvas a ejecutar como administrador
   ni cambies permisos de Windows para resolver este error.
2. Si el escritorio quedó inestable, guarda tu trabajo y reinicia el equipo.
   Conserva el registro; no borres ni renombres carpetas de Windows.
3. Con el Gestor cerrado, respalda su carpeta completa de datos. No necesitas
   desinstalar la aplicación ni editar el registro como parte de esta corrección.
4. Aplica los archivos de esta entrega al repositorio, conserva las carpetas y
   sube un commit nuevo. Si main avanzó desde `5e7a6cb`, integra el diff.
5. Inicia **Actions → Revisar refactorización e instalador → Run workflow → main**.
   Una repetición de la ejecución anterior usa el código anterior.
6. Comprueba que también pasó la nueva etapa de instalación. Descarga el artefacto
   `GestorHorarios-revision-Windows` y utiliza exclusivamente
   **GestorHorarios-Instalar-4.3.1.exe**.
7. Verifica la carpeta mostrada en el asistente. Tras instalar, confirma que el
   escritorio permanece estable, aparecen las cuentas y se conservan tus datos.

No publiques la versión hasta completar la comprobación en el equipo de prueba.
Si algo falla, conserva el paso rojo expandido y el artefacto de diagnóstico.

## Fuentes

- [Inno Setup: efectos de CreateAppDir=no](https://jrsoftware.org/ishelp/topic_setup_createappdir.htm).
- [Referencia de Inno Setup 6.7.3, sección CreateAppDir](https://github.com/jrsoftware/issrc/blob/is-6_7_3/ISHelp/isetup.xml).
- [Inno Setup: eventos NextButtonClick y PrepareToInstall](https://jrsoftware.org/ishelp/topic_scriptevents.htm).
- [Velopack 1.2.0: reemplazo de una instalación ocupada](https://github.com/velopack/velopack/blob/1.2.0/src/bins/src/commands/install.rs).
