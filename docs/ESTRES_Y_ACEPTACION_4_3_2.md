# Estrés y aceptación de Gestor de Horarios 4.3.2

Fecha: 22 de septiembre de 2026. Entorno: Linux, Python 3.12 y Chromium 153.
Código revisado desde `7f1107e`, con las correcciones locales de la entrega 4.3.2.

## Veredicto

Las pruebas funcionales y de estrés ejecutadas pasan después de las correcciones.
La entrega está preparada para la aceptación nativa en Windows; todavía no se
puede certificar el instalador final ni la generación con la plantilla privada
original completa, porque no están disponibles en este entorno.

**245 alternativas examinadas no significa 245 alternativas válidas:** el motor
aceptó 195 y marcó 50 como inválidas. Todas las 49 generaciones ofrecieron al
menos una alternativa válida. En las aceptadas, los auditores independientes no
encontraron incumplimientos nuevos de las normas que comprueban. Las opciones
inválidas permanecen identificadas: 40 presentan un conflicto de reparto de
domingos y 10, coincidencias entre personas que comparten PC. La prueba no borra
estos resultados ni desactiva las reglas para aprobarlos.

## Evidencia ejecutada

| Prueba | Resultado |
| --- | --- |
| Batería Python completa, incluyendo lentas | 487 aprobadas; 7 omitidas; 2 avisos de dependencias; 102,26 s |
| Estrés de generación | 49 generaciones, 5 alternativas cada una: 245 |
| Continuidad de meses | 24 meses consecutivos, octubre de 2026 a septiembre de 2028 |
| Escenarios combinados | 6 escenarios con alta, solicitudes, asignaciones, configuración, ajuste manual y cambio de turno |
| Lecturas concurrentes | 400 peticiones, 8 trabajadores, 0 errores HTTP |
| Latencia local de lecturas | Percentil 95: 0,3179 s; máximo: 0,588 s |
| Aprobaciones concurrentes incompatibles | 12 pares: exactamente una aprobación por par |
| Integridad SQLite | quick_check correcto y sin errores de claves foráneas tras cada escenario |
| Bases históricas | Agosto y septiembre conservados sin cambios en cada escenario |
| Recorrido principal de pantalla | 55/55 |
| Formularios y controles | 74/74 |
| Barra y puente simulado en navegador | 46/46 |
| Presentación clara y oscura | 32/32 |
| Arranque y respuestas tardías | 6/6 |
| Combinaciones existentes | 47/47 |
| Cruces existentes de novedades | 131/131 |
| Encadenado existente | 6/6 meses, 30 alternativas |
| Auditor de normas existente | Tanda aprobada |

Las suites existentes de combinaciones, cruces y encadenado se ejecutaron antes
del ajuste final que rechaza asignaciones sin horario. La batería Python, los
recorridos del navegador y el estrés definitivo se ejecutaron con esa corrección.
Los recuentos de comprobaciones no representan funciones únicas ni todas las
combinaciones posibles.

Las 7 omisiones corresponden a tres pruebas de Velopack, una de credenciales de
Windows, una de icono dependiente de Pillow y dos de la nómina privada. No se
cuentan como aprobadas. La primera tanda de navegador falló antes de interactuar
con la aplicación por una copia incompleta de Chromium. Se restauró el navegador
y se repitieron las cinco suites, todas con resultado correcto.

## Qué se combinó

Cada escenario mixto genera y publica octubre; incorpora una persona fija desde
una fecha posterior al inicio del mes; aprueba vacaciones, permiso e incapacidad;
crea una asignación administrativa con horario explícito; programa el paso de fijo
a rotativo para noviembre; cambia el máximo de jornadas consecutivas desde una
fecha futura; y vuelve a generar. Se comprueba que el horario oficial previo no
cambia por sí solo, que la nueva persona no trabaja antes de su incorporación y
que las novedades se reflejan en las fechas correspondientes.

Después se aplica un descanso manual, se regenera para comprobar su persistencia
y se genera noviembre para verificar el cambio a rotación. Los máximos 10, 11 y
12 son configuraciones explícitas de estos escenarios de prueba: no se cambian
los valores de trabajo del usuario. La auditoría consulta el máximo vigente para
el período y comprueba que cada alternativa haya usado ese mismo valor.

Las peticiones concurrentes leen salud, personal, solicitudes y horario oficial.
Las carreras de escritura intentan aprobar dos ausencias incompatibles de una
misma persona y fecha. Esto cubre concurrencia acotada; no mide cientos de
usuarios, agotamiento de disco, cortes eléctricos ni resistencia de larga duración.

## Reglas verificadas y límites

Se recalculan desde los horarios: casillas completas, códigos, cobertura mínima,
techos de AM/PM, ausencia de cobertura de ADM-AC, descanso semanal, máximo de
jornadas, transición PM→AM, parejas, compensatorios por festivo, último viernes
administrativo y vigencia del personal. También existe un comprobador de reglas
internas, pero sin la plantilla privada su cobertura no acredita las reglas
particulares de la oficina. La equidad de domingos queda reflejada en los
rechazos del motor; no se presenta como una comprobación independiente adicional
implementada por esta nueva prueba.

Las bases manuales son históricas e impunes. No se regeneran para eliminar
incumplimientos; las jornadas nuevas y las prolongaciones de rachas se siguen
validando. Un bloqueo manual por sí solo no convierte una jornada en histórica.

Los recorridos visuales comprueban flujos y desbordamientos en tamaños concretos,
y se inspeccionaron capturas. No sustituyen una aceptación de accesibilidad,
lectura con escalado de Windows ni una evaluación estética de todos los diálogos.

## Fallos corregidos

1. **Asignaciones sin horario.** El servidor permitía guardar una asignación
   administrativa incompleta y después no podía producir una opción válida.
   Ahora las asignaciones administrativas y actividades exigen un horario
   compatible, muestran un mensaje comprensible y no guardan la entrada inválida.
   Se añadieron seis casos de regresión para ausencia, vacío y código desconocido.
2. **Exención excesiva del auditor.** Confundía una casilla bloqueada con historia
   exenta. Ahora distingue el origen histórico y exige que ambos extremos de una
   transición sean históricos para eximirla.
3. **Falso resultado positivo del encadenado.** Una generación HTTP fallida podía
   terminar con código de éxito si no había llegado al auditor. Ahora una tanda
   incompleta devuelve error.

## Repetición y entrega Windows

Con las dependencias del proyecto instaladas:

```text
python qa/estres.py --meses 24 --escenarios 6 --lecturas 400
```

Guarda `resultado.json` y cada respuesta de generación comprimida en
`dist/diagnostico/estres`. Un escenario incompleto o una opción aceptada que
incumple la auditoría produce código de salida 1. Se usan servidores HTTP reales
y bases temporales aisladas. Los datos de prueba no son la plantilla del instalador.

`qa/todo.py` incluye ahora esta prueba y la de arranque, además de sus suites
anteriores; los recorridos de navegador requieren Playwright y Chromium.

Ambos workflows incorporan una tanda de estrés de 12 meses, 3 escenarios y 200
lecturas antes de construir el ejecutable. La comprobación nativa conserva sus
pasos obligatorios: compilar Inno, construir, abrir WebView2, empaquetar, probar
rutas e instalar/reinstalar. Estos pasos no se han ejecutado aquí en Windows.

1. Subir el contenido del ZIP de código al repositorio, incluidos los workflows.
2. Mantener `GESTOR_NOMINA` con la plantilla original completa. Añadir
   `GESTOR_BASE_SEPTIEMBRE` con el texto del paquete privado de septiembre.
   No subir ese paquete privado como código público.
3. Actions → **Generar versión final de Windows** → **Run workflow** sobre la
   rama actualizada. Una ejecución nueva utiliza el código nuevo.
4. Descargar **GestorHorarios-Windows** cuando todas las etapas hayan pasado.
   **GestorHorarios-diagnostico-Windows** conserva el acta del estrés y el
   diagnóstico nativo, también si falla una etapa.
5. En el equipo de uso, comprobar la ruta elegida, apertura del acceso, nombres,
   agosto, septiembre y una generación futura sobre una copia de los datos reales.

El paquete privado contiene 17 nombres y 595 turnos, transcritos del Excel de
septiembre. No reconstruye las fichas originales ni agosto. El instalador no
sobrescribe meses ya guardados en una base existente. Para recuperar solicitudes,
asignaciones e historial previos se necesita la copia original de esa base.

No se ha publicado una release ni subido cambios al remoto desde esta sesión.
