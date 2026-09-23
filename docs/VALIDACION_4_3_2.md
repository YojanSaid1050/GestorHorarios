# Validación de la entrega 4.3.2

22 de septiembre de 2026. Revisión local sobre `main` en `7f1107e`, Linux y Python 3.12.

| Comprobación | Resultado |
| --- | --- |
| Batería completa `pytest --lentas` | 487 aprobadas, 7 omitidas, 2 avisos; 102,26 s |
| Ruff sobre gestor, empaquetado, pruebas y qa | Correcto |
| Diferencias Git: espacios y conflictos | Correcto |
| Sintaxis YAML de los dos workflows | Correcta |
| Orden del flujo | Compilar asistente → construir EXE → comprobar ventana → empaquetar → instalar/reinstalar → entregar |
| Secretos privados | Disponibles en construcción y empaquetado; no hay compilación de entrega sin GESTOR_NOMINA |
| Datos iniciales | Sustitución completa de la carpeta de ejemplo, sin conservar archivos opcionales ficticios |
| Actualización de septiembre | Período, fechas, códigos, duplicados y coincidencia con los nombres de la plantilla |
| Transcripción del Excel recibido | 17 nombres, 35 fechas, 595 turnos comprobados individualmente |
| Exención histórica | Fatiga y rachas puramente históricas exentas; extensión con jornadas nuevas sigue comprobándose |

Las 7 omisiones corresponden a tres pruebas de Velopack, una del almacén de credenciales de Windows, una del icono que requiere Pillow y dos que necesitan la nómina privada completa. No se cuentan como aprobadas. Los avisos de obsolescencia proceden de las dependencias de pruebas Starlette/httpx y AnyIO.

Se comprueba que una plantilla ausente, incompleta o idéntica al personal de ejemplo no se entregue como un instalador real. Una actualización de septiembre rechazada no modifica la plantilla previa. Las pruebas de importación aceptan una secuencia sin descansos a propósito: no evalúan cumplimiento de reglas en una base manual.

El Excel aporta solo nombres y turnos por fecha, como indicó el usuario. No se han importado sus demás campos ni modificado fichas de personal a partir de ellos. Agosto no se ha reconstruido ni reemplazado.

## Lo que falta ejecutar con los datos originales y Windows

- No se ha recibido la plantilla original completa ni una copia de la base instalada. No se puede afirmar que sus nombres coinciden con el Excel hasta comprobarlos contra GESTOR_NOMINA. El empaquetado se detiene si no coinciden.
- La compilación de PyInstaller/Inno Setup, WebView2 y la instalación/reinstalación se ejecutan en el workflow Windows; no se han ejecutado nativamente en este entorno Linux para esta entrega.
- Se han repetido los recorridos de Chromium: pantalla 55/55, interfaz 74/74, ventana con puente simulado 46/46, visual 32/32 y arranque 6/6. La aceptación visual nativa de Windows sigue pendiente. Véase ESTRES_Y_ACEPTACION_4_3_2.md.
- La plantilla actualizada no reemplaza meses ya guardados en una base existente. Recuperar solicitudes y ajustes exige una copia consistente de esa base.

No se ha subido código ni publicado una release desde esta sesión. El ZIP fuente no contiene la plantilla privada ni una base de datos de usuario.
