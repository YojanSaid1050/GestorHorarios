# Resultados de la revisión

Fecha: 21 de septiembre de 2026. Base: `e5b555d`, versión 4.2.1.
Candidata: 4.3.0. Entorno ejecutado: Linux, Python 3.12, Chromium sin interfaz.
El objetivo de compilación sigue siendo Windows x64 con Python 3.11.

| Comprobación ejecutada | Resultado |
| --- | --- |
| `ruff check gestor empaquetado pruebas qa` | Correcto |
| `pytest --lentas` | **426 aprobadas, 4 omitidas**, 2 avisos de obsolescencia de dependencias |
| Autocomprobación del código fuente `--comprobar` | Código de salida 0 |
| `qa/arranque.py` | **6/6** |
| `qa/pantalla.py` | **55/55** |
| `qa/combinaciones.py` | **47/47** |
| `qa/interfaz.py` | **74/74**, sin errores de JavaScript durante el recorrido |
| `qa/visual.py` | **32/32**, claro y oscuro |
| `qa/ventana.py` | **46/46**, puente simulado |
| `qa/encadenado.py` | **6/6 meses**, 5 opciones por mes, sin incumplimientos detectados por su auditor |
| Comparación estructural de funciones trasladadas | 61 idénticas; 2 limpian importaciones; 1 actualiza el acceso a la ruta de Excel |

Las cuatro omisiones corresponden al módulo dependiente de Velopack/Windows,
dos pruebas que necesitan la nómina privada y la prueba del almacén de
credenciales real de Windows. No se incluyen esos resultados como aprobados.

El censo de interfaz informa 58 controles identificados, 57 pulsados y 10
exclusiones justificadas en distintos estados de pantalla; estas cifras no son
categorías mutuamente excluyentes ni deben sumarse.

La medición visual inspecciona contraste y desbordamientos en los estados
recorridos. No certifica conformidad integral con WCAG: omite algunos fondos
con degradado y su umbral de fallo de contraste es más laxo que el objetivo de
texto normal. No reemplaza la evaluación de teclado, lector de pantalla y escalado.

## Comprobaciones que siguen pendientes

- Compilar el `.exe` y el asistente con Inno Setup en Windows.
- Ejecutar `--comprobar-ventana` sobre el paquete real y probar el almacén nativo.
- Reabrir con una copia de la carpeta que causaba el bloqueo.
- Verificar instalación, actualización y desinstalación, visualmente y conservando datos.
- Ejecutar el flujo de GitHub añadido. No se ha publicado código ni una release en esta revisión.

## Repetir la validación

Desde la raíz del proyecto y con las dependencias instaladas:

```powershell
python -m ruff check gestor empaquetado pruebas qa
python -m pytest --lentas
python -m gestor.principal --comprobar
python -m pip install playwright
python -m playwright install chromium
python qa/arranque.py
python qa/pantalla.py
python qa/combinaciones.py
python qa/interfaz.py
python qa/visual.py
python qa/ventana.py
python qa/encadenado.py
```

Las suites de QA usan datos propios de ejemplo. Algunas conservan las rutas
`/tmp/qa_*` heredadas: ejecutarlas en un entorno de prueba y nunca apuntarlas a
una carpeta que contenga datos de trabajo. `GESTOR_CHROMIUM` y
`GESTOR_CHROMIUM_ARGUMENTOS` permiten elegir el navegador del entorno de QA.

Las evidencias entregadas contienen salidas finales y capturas con datos de
prueba. No contienen una captura del instalador nativo ni una base real del usuario.
