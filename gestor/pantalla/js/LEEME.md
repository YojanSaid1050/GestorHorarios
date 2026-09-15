# La pantalla, por partes

Esto era un solo archivo, `app.js`, de 6.577 líneas. Ahora son quince, uno por
zona de la aplicación, y el navegador los carga en orden desde `index.html`.

## Por qué así y no con módulos ES

La aplicación genera botones con el manejador escrito dentro del HTML:

```js
`<button onclick="cancelarGrupoRequerimiento('${r.grupo_id}')">Cancelar grupo</button>`
```

Un `onclick` escrito así solo encuentra funciones **globales**. Con módulos ES
(`import` / `export`) cada archivo tiene su propio ámbito y los veinticuatro
manejadores de este tipo dejarían de funcionar en el acto.

Por eso son archivos sueltos cargados en orden, que comparten el ámbito global
igual que antes. Al partirlo, **concatenar los archivos del uno al catorce
devolvía el `app.js` original línea por línea**, que es como se comprobó que la
partición no había cambiado nada.

Aquello era una comprobación de un día, no una regla: desde entonces el código ha
seguido cambiando dentro de cada archivo y ya no reconstruye nada. Lo que sí sigue
valiendo es el orden. El `15-ventana` es posterior a aquel archivo: código nuevo,
no un trozo del original.

## El orden importa

Se cargan en el orden numerado, que es el mismo que tenían dentro del archivo
original. Cambiar el orden puede romper cosas: una `const` de un archivo no
existe todavía para los que se cargan antes que él. Si añades un archivo nuevo,
ponlo al final o donde de verdad corresponda, y añádelo a `index.html`.

## Qué hay en cada uno

| Archivo | De qué habla |
|---|---|
| `01-acceso` | Entrar, salir y qué puede hacer cada quien |
| `02-periodo` | El mes que se está programando |
| `03-estructura` | Las pestañas, los contadores y los formularios por pasos |
| `04-personal` | La plantilla: altas, retiros, parejas y cambios de turno |
| `05-solicitudes` | Las novedades que pide la gente |
| `06-asignaciones` | Asignaciones y ajustes, sueltos y por grupo |
| `07-formularios-fecha` | Fechas, semanas y el formulario de solicitud |
| `08-validacion` | Qué salió bien, qué pide una decisión y qué no |
| `09-horario` | La cuadrícula del mes, las alternativas y generar |
| `10-exportacion` | Sacar el Excel |
| `11-apariencia` | Colores del horario, paletas, claro y oscuro |
| `12-reparto-areas` | El reparto AM/PM de cada área |
| `13-modificar` | Modificar el horario: semanas, cambios a mano, reprogramar |
| `14-arranque` | Recordar la contraseña, la carga inicial, la guía y el calendario |
| `15-ventana` | La barra de título propia: mover, los tres botones y estirar los bordes |
