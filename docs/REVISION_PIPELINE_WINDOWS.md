# Revisión del workflow y del instalador

Base revisada: `main`, commit `b20337e`. Esta entrega corrige el código fuente;
no contiene un EXE compilado ni acredita una ejecución nueva de Actions.

## Causa del fallo comunicado

El script leía `ISCC.exe.VersionInfo.ProductVersion` y exigía `6.7.3`.
El registro del usuario devuelve `0.0.0.0`. Esa propiedad del ejecutable de
consola no es una comprobación válida de la versión del motor de Inno Setup.
El fallo estaba en la comprobación que se añadió, no demuestra que la descarga
haya instalado una versión equivocada.

Se revisó el código oficial de **6.7.3**, no únicamente la documentación de la
versión más reciente. En esa versión `--version` no está implementado y `/?`
termina con código 1. No se usan como solución alternativa.

`preparar_inno.ps1` conserva la descarga oficial y la verificación de firma.
Después compila un instalador mínimo cuyo preprocesador exige
`DecodeVer(Ver, 3) == "6.7.3"`. También exige que el compilador acepte
`WizardStyle=modern dynamic windows11`, termine correctamente y genere el EXE.
Ese EXE de comprobación se elimina sin ejecutarlo. El compilador solo se añade
al PATH si supera esta comprobación.

## Etapas posteriores revisadas

| Etapa | Revisión y cambio | Límite de la verificación |
| --- | --- | --- |
| Dependencias | PyInstaller 6.22.3 y hooks 2026.7 en un fichero común; `vpk` 1.2.0 en ambos workflows. Son las versiones instaladas con éxito en el registro proporcionado. | Fijar versiones directas reduce variaciones; no congela el runner ni todas las dependencias transitivas. |
| Ruff y pytest | Pasos separados. Un pytest correcto ya no puede ocultar el código de salida de Ruff. | Ejecutados localmente en Linux. |
| Pruebas de empaquetado | La ausencia de Velopack omite solo sus tres pruebas, no todo el módulo. | 31 pruebas del módulo pasan aquí; las comprobaciones nativas siguen requiriendo Windows. |
| PyInstaller | Se mantiene la receta de carpeta, recursos de pantalla, metadatos de pywebview y componentes de WebView2. `--solo-exe` construye y comprueba el servidor. | Inspección de receta y pruebas; no compilación Windows local. |
| Ventana real | El nuevo script inicia el EXE, espera hasta 100 s, exige informe nuevo, salida 0 y `ok=true`. Restaura `GESTOR_DATOS` al terminar. | Necesita Windows con WebView2 y escritorio utilizable. La sonda usa datos temporales. |
| Velopack | Contrastados en el código 1.2.0: `--framework webview2`, `--shortcuts StartMenuRoot`, `--silent`, `--installto` y `--log`. | Compatibilidad de argumentos comprobada; instalación real pendiente. |
| Asistente de Inno | Se conserva la bienvenida, tema dinámico, estilo Windows 11, destino, acceso directo opcional y ejecución final. Se compila después de probar el EXE. | Compilar no comprueba por sí solo el aspecto, escalado, actualización ni desinstalación. |
| Artefactos | Los diagnósticos se conservan si existen incluso tras un fallo; el instalador solo se adjunta si pasan las etapas anteriores. | Un fallo anterior a la sonda puede no producir diagnósticos de ventana. |
| Publicación | Misma prueba del EXE antes de empaquetar; etiqueta obligatoria y coherente con la versión. | No se ha publicado una versión nueva. |

El nuevo orden es: preparar herramientas, revisar código, probar funciones,
construir y comprobar servidor, probar WebView2, empaquetar, conservar resultados.
Los workflows de revisión y publicación usan esa separación; el de publicación
añade los requisitos existentes de etiqueta y plantilla de oficina.

## Resultado local de esta revisión

- Batería completa con `pytest --lentas -q`: **457 aprobadas y 7 omitidas**, salida 0.
- Las omisiones corresponden a dependencias o condiciones no disponibles aquí:
  Velopack, Pillow, diálogo nativo y plantilla privada de oficina.
- Dos advertencias de deprecación de las dependencias de TestClient; no fallos.
- Ruff: correcto. `git diff --check`: correcto.
- Ambos YAML se analizaron y se comprobó el orden ejecutable → ventana → paquetes,
  además de la condición de éxito para entregar instaladores o publicar.
- No se ejecutaron los scripts PowerShell, Inno, Velopack ni el EXE en este Linux.
  Tampoco se ha reproducido el bloqueo con los datos reales del usuario.

## Cómo subirlo y ejecutarlo

1. Aplica los archivos del ZIP de corrección conservando sus carpetas. Incluye
   `.github/workflows`, los dos scripts de empaquetado, el fichero de versiones,
   la prueba y la documentación. Si tu rama avanzó desde `b20337e`, revisa el diff.
2. Guarda y sube un commit a `main`. Subir el ZIP como archivo al repositorio no
   aplica la corrección: deben actualizarse los archivos que contiene.
3. En GitHub abre **Actions → Revisar refactorización e instalador → Run workflow**.
   Selecciona **main** e inicia una ejecución nueva.
4. No uses **Re-run jobs** de la ejecución fallida para probar el cambio: GitHub
   reutiliza el commit original en una repetición.
5. Si termina correctamente, descarga `GestorHorarios-revision-Windows` y extrae
   `GestorHorarios-Instalar-4.3.0.exe`. `GestorHorarios-diagnostico-Windows` contiene
   el resultado de la ventana cuando se alcanzó esa etapa.
6. Si falla, conserva el primer paso rojo expandido y el diagnóstico disponible.
   No cambies otra dependencia antes de leer ese error.

El workflow no instala el asistente sobre un perfil Windows de uso. Antes de
sustituir la versión instalada, completa la aceptación de
[SOLUCION_WINDOWS.md](SOLUCION_WINDOWS.md): instalación nueva y actualización,
datos conservados, escalado/temas, cierre y reapertura, y desinstalación.
No crees la etiqueta de publicación hasta terminar esa aceptación.

## Fuentes consultadas

- [ISCC de Inno Setup 6.7.3: argumentos, motor y códigos de salida](https://github.com/jrsoftware/issrc/blob/is-6_7_3/Projects/ISCC.dpr).
- [Referencia ISPP de 6.7.3: variable Ver](https://github.com/jrsoftware/issrc/blob/is-6_7_3/ISHelp/ispp.xml).
- [Funciones EncodeVer y DecodeVer de 6.7.3](https://github.com/jrsoftware/issrc/blob/is-6_7_3/Files/ISPPBuiltins.iss).
- [Verificación oficial de la firma de Inno Setup](https://jrsoftware.org/isdl-verify.php).
- [Argumentos de empaquetado de Velopack 1.2.0](https://github.com/velopack/velopack/blob/1.2.0/src/vpk/Velopack.Vpk/Commands/Packaging/WindowsPackCommand.cs).
- [Argumentos del instalador de Velopack 1.2.0](https://github.com/velopack/velopack/blob/1.2.0/src/bins/src/setup.rs).
- [Detección e instalación de WebView2 en Velopack 1.2.0](https://github.com/velopack/velopack/blob/1.2.0/src/bins/src/windows/runtimes.rs).
- [GitHub: las repeticiones conservan GITHUB_SHA y GITHUB_REF](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs).
