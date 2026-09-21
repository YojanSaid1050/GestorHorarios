# Pantalla por responsabilidades

El orden de carga lo declara `index.html`: infraestructura, estado/acceso,
funciones de trabajo, edición, período, publicación, historial, fechas,
cuentas, credenciales, guía, calendario, edición instalada, puente nativo y
finalmente arranque. Cada script se incluye exactamente una vez.

El acceso a red y los límites del primer inicio viven en `00-infraestructura.js`.
Las cuentas se consultan sin esperar al tema. El arranque es el último módulo:
no depende de que una petición tarde lo suficiente para registrar controles.

Los controladores conservan por compatibilidad el ámbito compartido de la
pantalla original. No son módulos ES ni una reescritura con un framework. Las
funciones trasladadas conservan sus contratos. Al añadir una pantalla, registrar
su módulo antes de `14-arranque.js` y ejecutar las pruebas de API y navegador.
