# Gestor de Horarios 4.3.0 candidata — instrucciones

Esta entrega contiene el código completo refactorizado y el código del nuevo
instalador. **No incluye un instalador `.exe` compilado ni una publicación nueva
en GitHub.** La compilación y la aceptación nativa necesitan Windows.

La corrección del puente evita que pywebview recorra el objeto nativo de ventana.
Además, el acceso carga las cuentas sin depender de la apariencia y limita las
esperas. El bloqueo reportado debe verificarse sobre una copia de tus datos:
no se ha reproducido aquí tu equipo Windows.

## 1. Conservar los datos antes de probar

Cierra todas las ventanas del Gestor y confirma en el Administrador de tareas que
no queda `GestorHorarios.exe`. No borres `horarios.db`, `-wal` ni `-shm` para
intentar solucionar el bloqueo. Copia la carpeta completa, con el programa cerrado.

En PowerShell:

```powershell
$origen = Join-Path $env:LOCALAPPDATA 'GestorHorarios-datos'
$marca = Get-Date -Format 'yyyyMMdd-HHmmss'
$respaldo = Join-Path $env:USERPROFILE "Desktop\GestorHorarios-respaldo-$marca"
$prueba = Join-Path $env:LOCALAPPDATA "GestorHorarios-prueba-$marca"
Copy-Item -LiteralPath $origen -Destination $respaldo -Recurse -ErrorAction Stop
Copy-Item -LiteralPath $origen -Destination $prueba -Recurse -ErrorAction Stop
$env:GESTOR_DATOS = $prueba
```

Si tus datos están en otra ubicación, sustituye `$origen`. Conserva `$respaldo`
sin modificar. `$prueba` será la copia de trabajo. Estas variables se aplican
solo a esta sesión de PowerShell.

## 2. Probar el código corregido

Extrae el ZIP completo en una carpeta nueva. Abre PowerShell en la carpeta que
contiene `requisitos.txt`. Usa Python 3.11 de 64 bits y Microsoft Edge WebView2.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requisitos.txt
.\.venv\Scripts\python.exe -m gestor.principal --comprobar
.\.venv\Scripts\python.exe -m gestor.principal --diagnostico-ventana
```

El título debe mostrar **4.3.0**. Si muestra 4.2.1 estás abriendo el programa
anterior. Comprueba que las cuentas aparecen, entra y revisa tu personal,
solicitudes y último oficial. No uses todavía el acceso directo de la versión instalada.

Al actualizar, se elimina el antiguo respaldo de contraseñas en el navegador.
Escribe tu contraseña una vez. La opción de recordarla utiliza el Administrador
de credenciales de Windows, con ámbito por carpeta de datos. Si falla, puedes
entrar igualmente escribiéndola. En Edge se puede usar su propio gestor de
contraseñas; la aplicación no guarda allí un respaldo en texto legible.

## 3. Si sigue bloqueándose

Cierra el proceso anterior antes de cada prueba. Mantén la misma `$prueba`.
Ejecuta, de uno en uno:

```powershell
.\.venv\Scripts\python.exe -m gestor.principal --ventana-segura --diagnostico-ventana
.\.venv\Scripts\python.exe -m gestor.principal --sin-puente --diagnostico-ventana
```

- **Ventana segura:** marco de Windows, posición inicial y sin leer ni guardar geometría previa. No borra tu configuración.
- **Sin puente:** también usa ventana segura y permite aislar la integración JS ↔ Python. Algunas acciones nativas, como guardar mediante diálogo, quedan fuera de esta prueba.

Para separar definitivamente ventana y servidor:

```powershell
$env:GESTOR_PUERTO = '8777'
.\.venv\Scripts\python.exe -m gestor.principal --servidor
```

Abre `http://127.0.0.1:8777` en Edge y pulsa Ctrl+F5. Si Edge funciona y la ventana
no, centra el diagnóstico en WebView2/puente/configuración de ventana. Si ambos
fallan, conserva lo que aparece en F12 → Consola y Red. Cierra el servidor con
Ctrl+C. No abras dos procesos que escriban sobre la misma carpeta de datos.

Archivos útiles dentro de `$prueba`:

- `registro.log`: arranque, eventos de ventana y versión instalada de pywebview.
- `diagnostico-ventana.log`: pilas periódicas cuando se usa la bandera de diagnóstico; espera al menos 45 segundos si se bloquea.

No compartas la base de datos ni claves para reportar el fallo. Revisa los
registros antes de compartirlos por si contienen nombres o rutas personales.

## 4. Autocomprobación de la ventana real

```powershell
.\.venv\Scripts\python.exe -m gestor.principal --comprobar-ventana
Get-Content (Join-Path $prueba 'comprobacion-ventana.json')
```

Abre una ventana real con **datos temporales de ejemplo**, comprueba cuentas y
puente y la cierra. Tiene un tope de 75 segundos. El resultado queda en
`comprobacion-ventana.json` y su registro en `comprobacion-ventana.log`. Esta prueba
complementa, pero no sustituye, la apertura con tu copia real.

## 5. Construir el nuevo instalador

Herramientas adicionales en Windows: PowerShell 7, SDK de .NET para ejecutar `vpk`, PyInstaller
e Inno Setup **6.6 o posterior**; los flujos de GitHub fijan **6.7.3**. Instala Inno
Setup con el script incluido, que descarga la versión oficial y verifica su firma:

```powershell
.\.venv\Scripts\python.exe -m pip install -r empaquetado/requisitos-construccion.txt
dotnet tool install -g vpk --version 1.2.0
.\empaquetado\preparar_inno.ps1
.\.venv\Scripts\python.exe -m ruff check gestor empaquetado pruebas qa
.\.venv\Scripts\python.exe -m pytest --lentas
.\.venv\Scripts\python.exe empaquetado/construir.py --solo-exe
.\empaquetado\comprobar_ventana.ps1
.\.venv\Scripts\python.exe -c "from empaquetado.construir import empaquetar; empaquetar()"
```

Ejecuta los comandos uno a uno y detente si alguno falla. Si `vpk` ya está
instalado, comprueba con `dotnet tool list -g` que sea 1.2.0. Para ajustarlo:
`dotnet tool update -g vpk --version 1.2.0 --allow-downgrade`. El script coloca Inno en
`%LOCALAPPDATA%\Programs\Inno Setup 6` y añade esa ubicación al PATH de la sesión.
En GitHub Actions la añade también al PATH de los pasos siguientes.

Salida esperada:

```text
dist\instalador\GestorHorarios-Instalar-4.3.0.exe
```

El asistente incluye bienvenida, tema claro/oscuro según el sistema, estilo
Windows 11, imagen propia, carpeta de destino, acceso directo opcional,
confirmación, progreso y opción de abrir al terminar. La instalación existente
conserva su ubicación. Velopack sigue gestionando actualizaciones y desinstalación;
no se registra un segundo desinstalador.

En un equipo sin WebView2 hará falta conexión para obtenerlo. Los datos siguen
separados del programa. El registro del motor de instalación está en
`%LOCALAPPDATA%\GestorHorarios-datos\instalacion.log`.

Sin `GESTOR_NOMINA`, el paquete lleva datos de ejemplo para una instalación nueva.
No confundas esa plantilla de prueba con la plantilla de oficina. No incluyas
credenciales ni datos personales en el ZIP fuente ni en un repositorio público.

## 6. Aceptación antes de sustituir la versión de uso

En Windows, preferiblemente en un equipo de prueba:

1. Instala desde cero; comprueba cada paso del asistente, cancelación, carpeta con espacios, acceso directo y apertura sin consola.
2. Revisa 100/125/150/200 % de escala y temas claro/oscuro: textos completos, botones visibles y navegación con teclado.
3. Actualiza una instalación 4.2.1 de prueba con datos reconocibles: solicitudes, cuentas, oficial, ajustes y exportaciones deben conservarse.
4. Abre, minimiza, maximiza, cierra y vuelve a abrir; prueba marco nativo y barra propia.
5. Genera, valida, modifica, marca oficial y exporta. Prueba una solicitud y un cambio fijo ↔ rotativo con fecha futura.
6. Si un cambio afecta semanas compartidas, revisa primero los meses anteriores marcados como desactualizados; no basta con crear un borrador.
7. Crea y restaura una copia; comprueba el estado de una persona y una solicitud, además del número de filas.
8. Prueba «recordar contraseña», reapertura, cambio de contraseña y desmarcado. Verifica que desmarcar elimina el recuerdo.
9. Desinstala el paquete de prueba conservando datos y reinstala; comprueba la recuperación.

Solo después de esta aceptación, instala sobre tu entorno de uso conservando el
respaldo. Para que el programa instalado use su carpeta habitual, cierra la
sesión de PowerShell de prueba o ejecuta:

```powershell
Remove-Item Env:GESTOR_DATOS -ErrorAction SilentlyContinue
Remove-Item Env:GESTOR_PUERTO -ErrorAction SilentlyContinue
```

No copies la base de prueba encima de la original como paso automático.

## 7. Integrar el código en GitHub

El ZIP es una instantánea completa; no contiene `.git`. Con tus cambios actuales
ya guardados en un commit, crea una rama nueva desde el `main` actualizado y
compara/aplica esta instantánea. No sobrescribas trabajo tuyo sin revisar el diff.
Esta corrección del workflow parte de `b20337e`; si `main` avanzó, habrá que
integrar esos cambios.

El flujo **«Revisar refactorización e instalador»** se ejecuta en una PR o
manualmente y prepara el artefacto Windows con datos de ejemplo. Primero ejecuta
la sonda de WebView2; solo si pasa construye y adjunta el instalador. El diagnóstico
queda en un artefacto separado, también cuando falla. Esta revisión del flujo
no se ha ejecutado aquí en Windows.
Si el runner no dispone de escritorio utilizable, conserva su diagnóstico y
repite la prueba en un Windows interactivo antes de aceptar la versión.

No crees la etiqueta `v4.3.0` hasta completar las comprobaciones: esa etiqueta
activa la publicación. La revisión actual no ha modificado tu GitHub.

Consulta [ARQUITECTURA.md](ARQUITECTURA.md) para los cambios, límites y **funciones
nuevas propuestas que todavía no están implementadas**.

Consulta [REVISION_PIPELINE_WINDOWS.md](REVISION_PIPELINE_WINDOWS.md) para el
fallo de Inno Setup, las etapas revisadas y cómo iniciar una ejecución nueva.
