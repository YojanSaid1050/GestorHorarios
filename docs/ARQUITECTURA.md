# Refactorización 4.3.0 candidata

Revisión del 21 de septiembre de 2026 sobre `main`, commit `e5b555d` (4.2.1).
Esta entrega contiene código completo. No se ha publicado como versión estable.

## Alcance aplicado

| Responsabilidad | Ubicación nueva | Compatibilidad |
| --- | --- | --- |
| Servidor, puerto y cierre | `gestor/servidor_local.py` | `principal.py` conserva los puntos de entrada |
| Preparación de datos | `servicios/preparacion.py` | El ciclo de vida HTTP sigue invocándola |
| Solicitudes y asignaciones | `datos/solicitudes.py`, `datos/asignaciones.py` | `datos/novedades.py` reexporta las funciones anteriores |
| Validación de novedades | `servicios/validacion_novedades.py` | Las rutas conservan las respuestas HTTP |
| Modelos de entrada | `web/modelos_novedades.py` | Mismos contratos de validación |
| Reparación de horarios | `motor/reparaciones/` | `motor/reparacion.py` conserva la interfaz anterior |
| Excel | `servicios/exportacion_excel/` | `servicios/excel.py` conserva la entrada anterior |
| Pantalla | Scripts por publicación, historial, cuentas, calendario y edición | `index.html` establece el orden explícito |
| Diagnóstico nativo | `diagnostico_ventana.py`, `sonda_ventana.py` | Banderas optativas |
| Recuerdo de claves | `servicios/claves_locales.py` | Puente `leer_clave/guardar_clave/olvidar_clave`; almacén de Windows |
| Instalación | `empaquetado/asistente.iss` | Velopack conserva actualización y desinstalación |

Se extrajeron 64 funciones de los bloques principales: 61 conservan exactamente
su árbol sintáctico, dos eliminan importaciones repetidas y `crear_excel` consulta
la ruta de exportación vigente. Esto reduce el riesgo de cambiar reglas durante
la reorganización. Las correcciones de comportamiento se describen por separado.

El motor mantiene sus algoritmos y reglas actuales. La pantalla sigue usando
JavaScript con ámbito compartido: está dividida por responsabilidad, pero aún no
es una aplicación de módulos ES. No se ha sustituido cada función ni cambiado el
framework. No hay migración nueva del esquema de datos en esta refactorización.

## Dependencias que deben mantenerse

- `dominio` y `motor` no importan HTTP ni escritorio.
- `datos` guarda y consulta; `servicios` coordina; `web` valida entradas y traduce resultados.
- Las reparaciones importan módulos concretos, nunca su propia fachada de compatibilidad.
- El puente de escritorio solo expone operaciones. Sus objetos nativos son privados.
- La apariencia y el recuerdo de claves no condicionan la disponibilidad del acceso.
- Las pruebas de arquitectura verifican estas fronteras y que cada script se carga una sola vez.

## Correcciones incluidas y evidencia

| Hallazgo | Cambio | Comprobación |
| --- | --- | --- |
| `Puente.ventana` exponía todo el objeto nativo al enumerador recursivo de pywebview | Referencia privada `_ventana` | Enumerador real de pywebview 6.2.1 con propiedad centinela: reproduce el acceso original y deja de hacerlo tras corregirlo |
| Dependencia secuencial del tema antes de cargar cuentas | Cargas independientes; lectura abortable con límite, incluido el cuerpo de la respuesta | Chromium: apariencia sin respuesta y cuentas disponibles |
| Recuerdo de contraseña podía esperar indefinidamente | Esperas limitadas y fallo no fatal al entrar | Chromium con puente sin respuesta |
| Respuesta tardía de contraseña podía sobrescribir escritura o cambiar de cuenta | Verificación de cuenta y de escritura después de esperar | Dos regresiones en Chromium |
| Respaldo de contraseñas en texto legible en localStorage | Eliminar respaldo heredado; nuevo servicio del Administrador de credenciales de Windows | Prueba del borrado, fallo del almacén y aislamiento; prueba nativa preparada para Windows |
| `load/save/forget` se buscaban desde JS pero no estaban implementados en el puente de esta base | Implementación explícita con credenciales genéricas locales de Windows | Contrato y sonda de integración Windows |
| Elección de puerto separada de su uso | Mantener el socket reservado hasta cerrar | Servidor real responde y deja de aceptar conexiones al cerrarse |
| Fallos al crear ventana dejaban recursos sin liberar | Cierre del servidor y mutex en todos los caminos | Prueba de excepción antes de abrir la ventana |
| Autocomprobación solo cubría servidor | Añadir `--comprobar-ventana` con proceso y datos temporales | Código y pruebas de conservación de resultados; ejecución nativa pendiente |
| Instalador sin pasos configurables | Asistente Inno Setup nativo, imagen propia, carpeta y acceso directo | Revisión del código y pruebas de coordinación; compilación y aspecto nativos pendientes |

**El hallazgo del puente es reproducible, pero no demuestra por sí solo que sea
la única causa del bloqueo reportado en el equipo del usuario.** Para cerrarlo
hace falta ejecutar la candidata con una copia de la carpeta problemática.

## Combinaciones de operación revisadas

Las suites cubren solicitudes pendientes/aprobadas y regeneración, selección de
oficial, retiro con fecha efectiva, conservación de publicaciones anteriores,
cambios de reglas y festivos, semanas cerradas, reinicio de programación,
asignaciones, ajustes manuales, cambio programado de fijo/rotativo, usuarios,
exportación y restauración de copias. También se generan seis meses encadenados
con cinco opciones por mes y se comprueban sus reglas de forma independiente.

Se corrigieron expectativas obsoletas en la QA, sin cambiar la aplicación para
que las satisfaga: crear un borrador no limpia los cambios pendientes de un
oficial; un retiro futuro no elimina a la persona hoy; una restauración debe
comprobar `retirado_desde`, no solo el número de filas.

### Límite que sigue siendo importante

Los meses comparten semanas. Si se retira a una persona y el oficial anterior
todavía contiene días compartidos antiguos, la siguiente generación puede
heredarlos. La prueba de combinación actualiza primero ese oficial. **No se ha
implementado un bloqueo automático de generación por todas las dependencias
anteriores desactualizadas.** Hasta hacerlo, revisar y regenerar en orden
cronológico, respetando semanas cerradas y publicaciones.

## Funciones nuevas propuestas, aún no implementadas

Estas propuestas son parte del informe; no deben confundirse con funcionalidades
terminadas de esta candidata.

| Prioridad | Función | Qué debería permitir comprobar antes de guardar |
| --- | --- | --- |
| Alta | Asistente de cambio fijo ↔ rotativo | Fecha efectiva, lunes de inicio, nueva secuencia, solicitudes incompatibles, semanas cerradas y meses afectados |
| Alta | Vista previa del impacto | Comparar horario actual y propuesto por persona/día, explicando cambios y reglas |
| Alta | Dependencias entre meses | Detectar un oficial previo desactualizado y guiar su corrección antes de heredar semanas |
| Alta | Operaciones indivisibles para cambios compuestos | Solicitud, ajuste, invalidación e historial se confirman juntos o se deshacen juntos |
| Media | Centro de pendientes del administrador | Solicitudes por decidir, periodos desactualizados, excepciones y copias recientes con acciones concretas |
| Media | Portal de la persona | Su horario publicado, sus solicitudes y su estado; sin controles administrativos innecesarios |
| Media | Simulación de reglas | Evaluar una regla nueva sobre varios meses sin reemplazar oficiales |
| Media | Deshacer con versiones | Recuperar una revisión concreta, identificar autor y motivo, sin restaurar toda la base |
| Media | Diagnóstico exportable | Informe sin contraseñas con versión, estado del servidor, puente y errores, desde una pantalla de ayuda |

Para el nuevo sistema de cambios de turno, conservar la ficha laboral y una
línea temporal de vigencias. Un cambio con fecha no debe sobrescribir el pasado.
Separar «simular», «confirmar» y «publicar»; confirmar debe validar conflictos de
nuevo dentro de la transacción. Mostrar al administrador las personas y meses
afectados antes de confirmar. La persona debe ver cuándo empieza su cambio y
qué horario continúa vigente mientras se aprueba.

## Trabajo pendiente y límites de la revisión

1. Compilar e instalar en Windows, probar WebView2 y el almacén de credenciales real.
2. Reproducir el caso sobre una copia de los datos afectados y registrar el resultado.
3. Revisar instalación limpia y actualización 4.2.1 → 4.3.0, desinstalación con conservación de datos y escalado 100/125/150/200 %.
4. El servidor local conserva el diseño existente; esto no equivale a una auditoría completa de seguridad o concurrencia.
5. El empaquetado público conserva la política previa de plantilla de oficina. La entrega de revisión usa datos de ejemplo. Revisar esa política antes de publicar información real.
6. Las llamadas posteriores al acceso y operaciones largas requieren una política global de cancelación y estado incierto; no se ha aplicado un reintento automático que pueda duplicar escrituras.
7. Fijar también herramientas de construcción y dependencias transitivas en un archivo de bloqueo sería una mejora posterior.

No existe una prueba finita de «todas las combinaciones posibles». Esta entrega
identifica los recorridos ejecutados, los límites restantes y cómo repetir la
validación, sin presentar las comprobaciones de Linux como pruebas nativas.

## Referencias técnicas

- [Inno Setup: WizardStyle](https://jrsoftware.org/ishelp/topic_setup_wizardstyle.htm): estilo moderno, adaptación al tema y apariencia Windows 11.
- [Inno Setup: cambios de versión](https://jrsoftware.org/files/is6-whatsnew.htm): requiere 6.6 o posterior para las opciones usadas; CI fija 6.7.3.
- [Microsoft: CREDENTIALW](https://learn.microsoft.com/en-us/windows/win32/api/wincred/ns-wincred-credentialw): credenciales genéricas y persistencia local del usuario.
- [Microsoft: CredWriteW](https://learn.microsoft.com/en-us/windows/win32/api/wincred/nf-wincred-credwritew) y [CredReadW](https://learn.microsoft.com/en-us/windows/win32/api/wincred/nf-wincred-credreadw): escritura y lectura del almacén.
- Implementación inspeccionada: `webview/util.py`, `inject_pywebview`, del paquete fijado `pywebview==6.2.1`.
