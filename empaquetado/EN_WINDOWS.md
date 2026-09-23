# Comprobación en Windows — versión 4.3.2

La guía de generación y recuperación de datos está en [docs/ENTREGA_WINDOWS.md](../docs/ENTREGA_WINDOWS.md).
La aceptación manual está en [docs/SOLUCION_WINDOWS.md](../docs/SOLUCION_WINDOWS.md).
Incluye respaldo, diagnóstico del bloqueo, construcción del asistente y aceptación
sobre una instalación nueva y sobre una actualización desde 4.2.1.

El instalador esperado es `GestorHorarios-Instalar-4.3.2.exe`.
Inno Setup 6.6 o posterior es obligatorio; CI utiliza 6.7.3.

La comprobación del servidor (`--comprobar`) no sustituye a la de la ventana
(`--comprobar-ventana`) ni a la prueba con los datos reales copiados.
Los recorridos de Chromium con un puente simulado tampoco verifican el movimiento
y redimensionado de una ventana nativa. Comprueba ambos marcos, los cuatro bordes,
las cuatro esquinas, minimizar/maximizar, teclado y reapertura en otro monitor.

No se ha compilado ni probado el instalador nativo desde el entorno Linux de esta
revisión. Registra el resultado de cada paso de aceptación antes de publicar.
