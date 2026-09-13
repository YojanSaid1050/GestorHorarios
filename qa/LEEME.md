# Las pruebas que abren la aplicación de verdad

`pruebas/` mira las piezas por dentro con pytest. Esto es lo otro: **levanta el
servidor de verdad, sobre una instalación nueva, y lo usa**. Es donde aparecen
los fallos que ninguna prueba de Python encuentra, porque no están dentro de
ninguna pieza sino en el encaje entre dos.

Tres ejemplos reales, todos encontrados aquí:

* la cabecera de la cuadrícula decía **«undefined»** en cada columna al abrir
  agosto o septiembre. Los turnos eran correctos; lo que faltaba era el
  calendario de cada día, que la transcripción no traía;
* un `.slice` sobre ese dato ausente **tumbaba el arranque entero** de la
  pantalla: la excepción subía hasta el último `catch` y se quedaban sin
  ejecutar los calendarios, la guía y los ojos de las contraseñas. La aplicación
  parecía cargada y media estaba muerta;
* la pantalla llamaba a **cuarenta y dos direcciones que el servidor no tenía**.
  Nada fallaba al arrancar; los botones simplemente no hacían nada.

## Qué hay

| Archivo | Qué comprueba |
| --- | --- |
| `encadenado.py` | Seis meses seguidos —octubre de 2026 a marzo de 2027—, generados, elegidos y publicados uno sobre otro. Cada opción de cada mes pasa por el auditor independiente. |
| `combinaciones.py` | Lo que pasa **entre** piezas: se aprueba una novedad, se retira a alguien, se cambia una regla, se mueve un festivo, se cierra una semana, se reinicia. Cada escenario comprueba que la aplicación se entera **y** que no ha tocado nada por su cuenta. |
| `pantalla.py` | El recorrido completo con un navegador: entrar, abrir cada pestaña, generar, oficializar, registrar una novedad, cambiar un turno, editar a mano, exportar, cambiar la apariencia. |
| `reglas.py` | Cada norma, comprobada **desde su enunciado** sobre cada opción de cada mes, con los números delante: cuántos casos se revisaron, cuáles quedaron exentos y por qué. |
| `interfaz.py` | Al revés que `pantalla.py`: hace el censo de todo lo que se puede pulsar y lo pulsa, rellena cada formulario bien y mal, y recorre todas las combinaciones de sus selectores. |
| `visual.py` | Que todo se lea, en claro y en oscuro, midiendo el contraste real elemento por elemento. |
| `diagnostico.py` | No comprueba nada: abre una pantalla y cuenta qué hay. Para cuando un recorrido se atasca y no se sabe dónde. |
| `servidor.py` | Levanta la aplicación con su propia carpeta de datos y habla con ella. |
| `uso.py` | Conducir la pantalla como la conduce una persona. |

## Cómo se ejecutan

```
python qa/encadenado.py       # ~1 min
python qa/combinaciones.py    # ~1 min
python qa/reglas.py           # ~4 min
python qa/pantalla.py         # ~3 min, necesita navegador
python qa/interfaz.py         # ~4 min, necesita navegador
python qa/visual.py           # ~2 min, necesita navegador
```

Cada una devuelve 0 si todo salió bien. Ninguna comparte carpeta de datos con
otra: cada una empieza sobre una instalación recién hecha, porque compartirla
fue lo que hizo, en la versión anterior, que una suite denunciara un fallo de
reparto que en realidad había dejado escrito otra media hora antes.

## Por qué hay dos suites que parecen la misma

`pantalla.py` recorre **caminos**: entrar, generar, aprobar, exportar. Un camino
comprueba que lo previsto funciona, y por eso no encuentra nunca lo que está
fuera de lo previsto. `interfaz.py` va al revés: parte del **censo** de todo lo
que se puede pulsar —leído de la pantalla, no de una lista escrita a mano— y
termina diciendo qué quedó sin tocar y con qué motivo. Un control excluido sin
motivo escrito hace fallar la suite.

Lo mismo pasa con `reglas.py` frente al auditor de `pruebas/`: el auditor
contesta sí o no, y esto contesta **qué miró**. Un «0 incumplimientos» sin el
número de casos detrás no distingue «la regla se cumple» de «la regla no se
llegó a comprobar», que es exactamente el error que dejó pasar el hueco de
cobertura de Navidad y del Viernes Santo: los dos caen en el último viernes de
su mes, la exención del viernes administrativo los tapaba enteros y nadie medía
la cobertura de esos días.

## Dos reglas que se respetan en todas

**Se comprueba el efecto, no el mensaje.** Que salga un aviso verde diciendo
«guardado» no prueba nada. Después de cada acción se vuelve a preguntar al
servidor y se mira si de verdad quedó guardado. La versión anterior daba pasos
por buenos porque salía el aviso, y así hubo dos botones de Configuración que no
pulsó nunca ninguna prueba.

**La señal de que algo terminó es un estado, no un texto.** Esperar a que el
botón «deje de decir “generando”» parece razonable y no lo es: el botón en
reposo dice «Crear horario inicial», y la palabra «cre» está siempre ahí. Esa
espera no terminaba nunca. Se mira `disabled`, que es lo que la aplicación pone
y quita de verdad.

## Lo que `visual.py` no puede medir

Sobre un degradado no hay **un** color de fondo. Cuando la herramienta encuentra
uno por el camino, lo dice y no lo mide, en vez de inventar un número: midiendo
contra el color que hay debajo denunciaba la cabecera de la aplicación como
ilegible con un 1,1:1 cuando es texto blanco sobre morado y se lee
perfectamente. Un medidor que inventa fallos es peor que no tenerlo: se aprende
a ignorar lo que dice.

Y distingue dos cosas que no son la misma: lo que **no se lee** —texto del color
de su fondo— hace fallar la suite; lo que se lee pero queda por debajo del
contraste recomendado se lista aparte, con sus colores exactos, para que lo
decida quien eligió la paleta.
