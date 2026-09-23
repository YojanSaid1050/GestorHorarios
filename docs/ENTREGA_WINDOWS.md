# Entrega Windows 4.3.2 y datos de la oficina

Esta entrega parte de `main` en `7f1107e`. El código no se ha subido a GitHub desde esta revisión.

## Generar todos los paquetes

1. Integra el ZIP del código en tu repositorio, incluida `.github/workflows`, y guarda los cambios en `main`.
2. En **Settings → Secrets and variables → Actions**, conserva `GESTOR_NOMINA` con la plantilla original completa. Si falta, el workflow se detiene: ya no entrega un instalador con datos ficticios.
3. Para aplicar el Excel de septiembre recibido, crea **GESTOR_BASE_SEPTIEMBRE** con todo el contenido del archivo privado `GESTOR_BASE_SEPTIEMBRE.txt`. Conserva `GESTOR_NOMINA`: el secreto nuevo solo reemplaza septiembre. Si no se configura, se conserva el septiembre de la plantilla original.
4. Abre **Actions → Generar versión final de Windows → Run workflow → main**. Inicia una ejecución nueva después de subir los cambios; repetir una ejecución antigua no prueba el código nuevo.
5. Espera a que termine todo el trabajo Windows. Descarga **GestorHorarios-Windows**, extráelo y ejecuta **GestorHorarios-Instalar-4.3.2.exe**.

Ese artefacto incluye el asistente de Inno Setup, el ZIP portátil, los paquetes `.nupkg` y los archivos de actualización producidos por Velopack. Los diagnósticos se guardan aparte en **GestorHorarios-diagnostico-Windows**, incluido el informe XML de las pruebas. Los artefactos se conservan 7 días.

El flujo comprueba código y funciones, compila el asistente, construye el EXE, comprueba su servidor y ventana WebView2, genera los paquetes, prueba destinos protegidos, instala y reinstala en el runner y abre la aplicación instalada. Solo entrega los paquetes cuando todos esos pasos pasan. En las PR ejecuta las comprobaciones sin generar instaladores ni consumir la plantilla privada.

**Publicar una versión** sigue siendo un flujo separado para etiquetas `vX.Y.Z` que coincidan con `gestor/version.py`. Publica los paquetes después de las mismas comprobaciones nativas. Ejecutar la generación manual desde `main` no publica una release.

## Plantilla original y septiembre actualizado

`GESTOR_NOMINA` contiene la carpeta privada `nomina/datos_iniciales/`, con las fichas de personal, agosto y septiembre. Se prepara localmente con:

```powershell
python empaquetado/plantilla.py --empaquetar
```

El contenido devuelto se guarda como secreto, no como un archivo del repositorio. La actualización separada de septiembre valida período, nombres, duplicados, 35 fechas por persona y códigos de turno. No sustituye las fichas de personal ni agosto, y no infiere reglas de rotación a partir de una casilla.

El Excel adjunto solo permite transcribir septiembre: 17 personas, del 31/08 al 04/10, 595 asignaciones. Se usan exclusivamente los nombres y turnos por fecha. Se ignoran notas, controles y los demás campos del Excel, según la indicación del usuario.

No se ha recibido la plantilla original completa ni la base de uso. La coincidencia con ella y la continuidad con agosto deben verificarse al disponer de esos datos. Esta entrega no reconstruye agosto a partir de datos sintéticos.

## Bases manuales exentas de las reglas

Agosto y septiembre son referencias históricas importadas. No se regeneran ni se corrigen para ajustarlas a las reglas actuales. Las verificaciones del importador son de estructura: nombres conocidos, fechas completas y códigos reconocidos.

Se corrigió la detección de fatiga PM→AM y de rachas para que un incumplimiento íntegramente contenido en la base no bloquee el mes que hereda esos días. Sus jornadas siguen contando cuando una decisión nueva prolonga la racha o crea una transición nueva: la exención histórica no se extiende al resto de octubre.

## Recuperar todo lo guardado

La plantilla inicial no contiene las solicitudes, cuentas, ajustes manuales e historial de tu instalación anterior. Una actualización tampoco reemplaza un septiembre ya guardado: el arranque conserva los meses existentes.

1. Conserva una copia del estado actual. Si puedes abrir la instalación original, usa su opción de copia de seguridad: incluye correctamente los datos de SQLite aunque utilice WAL.
2. Localiza el `horarios.db` anterior o una copia `.db` de la carpeta `copias`. La ubicación habitual es `%LOCALAPPDATA%\GestorHorarios-datos`; si usabas `GESTOR_DATOS`, busca en esa carpeta alternativa.
3. En la aplicación actual entra como administrador y abre **Configuración → Copia de seguridad → Restaurar copia**. Selecciona la copia original y confirma con la contraseña actual. La aplicación guarda una copia previa antes de restaurar.
4. Vuelve a entrar con una cuenta y contraseña de la base restaurada. Revisa personal, solicitudes, horarios oficiales y ajustes conocidos.

Si la aplicación antigua no abre, cierra todos sus procesos y conserva la carpeta de datos completa, incluidos `horarios.db-wal` y `horarios.db-shm` si existen. No copies solamente una base activa ni borres esos archivos: puede haber operaciones recientes en WAL. Trabaja sobre una copia.

Para modificar septiembre en una base existente conservando el resto de su historia, hace falta esa base o una copia consistente. No uses «Restablecer aplicación» para recuperar datos, ni mezcles el Excel con las fichas ficticias de la instalación de prueba.

## Verificación y límites

Consulta `VALIDACION_4_3_2.md` para los resultados ejecutados en esta revisión. El objetivo de Windows sigue siendo Python 3.11; las pruebas locales se ejecutan con Linux y Python 3.12. El workflow contiene las comprobaciones nativas, pero deben ejecutarse en GitHub con tus secretos antes de aceptar el instalador nuevo.

La versión 4.3.2 identifica estos cambios de entrega y datos. No significa que todas las funciones propuestas en `ARQUITECTURA.md` estén implementadas ni que se haya probado el equipo que presentó el bloqueo original.
