# Cómo empaquetar e instalar esto en Windows

Comparación de las tres formas razonables de instalar esta aplicación, hecha
contra los problemas que ha tenido de verdad y no contra una lista de
características.

## De qué se parte

Lo que hay que resolver, en orden de lo que más ha dolido:

1. **Instalar encima tiene que actualizar.** Ha fallado varias veces y siempre
   con el mismo síntoma: el asistente dice «instalación completada» y al abrir
   el programa sigue apareciendo la versión de antes.
2. **Los datos tienen que sobrevivir** a la actualización, y al desinstalar hay
   que poder elegir si se borran.
3. **Sin permisos de administrador.** Son PC de oficina.
4. **Sin certificado de pago.**
5. **Construible desde GitHub Actions**, sin un Windows a mano.

## Por qué falla el planteamiento actual

Inno Setup **reemplaza el ejecutable en su sitio**. Si el archivo está en uso o
un antivirus lo bloquea, la copia falla, el instalador continúa y termina bien:
queda la versión vieja con la entrada del registro de la nueva. No es un fallo
del guion, es la consecuencia de sobrescribir en sitio, y no se arregla
escribiendo más Pascal.

## Las tres opciones

### Velopack — recomendada

Instala en `%LOCALAPPDATA%` en **carpetas por versión** (`app-3.6.2`,
`app-3.7.0`…) y cambia cuál es la buena al final. Una actualización nunca
sobrescribe el programa que se está ejecutando: o está entera o no está. El
fallo del punto 1 deja de ser posible por construcción, no por vigilancia.

Verificado en esta máquina: el paquete `velopack` de PyPI (1.2.0, junio de 2026,
MIT, publicado por los propios autores) expone justo lo que hace falta:

    UpdateManager  → check_for_updates, download_updates,
                     apply_updates_and_restart, get_current_version
    App            → on_first_run, on_before_uninstall_fast_callback

`UpdateManager` sustituye entero el `actualizaciones.py` escrito a mano —
comprobar, descargar y aplicar, con descargas diferenciales— y
`on_before_uninstall_fast_callback` es el gancho donde preguntar si hay que
borrar los datos, en Python y no en Pascal.

- Sin permisos de administrador · sin certificado obligatorio · GitHub Releases
  como canal de actualización · construible en `windows-latest`.
- A cambio: hay que pasar el ejecutable a modo carpeta (`--onedir`), que además
  arranca más rápido y es lo que permite las descargas diferenciales.

### MSIX

Lo más limpio de Microsoft: instalar y desinstalar no dejan rastro y hay
actualización automática desde una URL.

Dos cosas lo descartan para esta oficina:

- **Exige un certificado de firma en el que el equipo confíe.** Uno autofirmado
  obliga a instalar el certificado a mano en cada PC.
- **Aísla el disco.** Lo que la aplicación escribe en `%LOCALAPPDATA%` se
  redirige dentro del contenedor del paquete. Para una base SQLite eso cambia
  dónde viven los datos y complica justamente lo que se acaba de arreglar:
  saber qué carpeta borrar.

### Inno Setup, ya corregido

Es lo que hay, funciona y ahora está cubierto por pruebas que ejecutan su
`[Code]` de verdad. Sirve perfectamente si se prefiere no cambiar de
herramienta, pero el comportamiento de actualización se sigue escribiendo a
mano, y el modo de fallo del punto 1 sigue existiendo: lo que se añadió es
detectarlo y avisar, no evitarlo.

## Resumen

|                                   | Velopack | MSIX | Inno |
|-----------------------------------|:--------:|:----:|:----:|
| Actualizar no puede quedar a medias | sí     | sí   | no   |
| Sin permisos de administrador      | sí       | sí   | sí   |
| Sin certificado de pago            | sí       | no   | sí   |
| Actualización desde la propia app  | SDK      | sí   | a mano |
| Preguntar por los datos al desinstalar | Python | limitado | Pascal |
| Construible en GitHub Actions      | sí       | sí   | sí   |

## Lo que aquí no se puede demostrar

Este contenedor es Linux. Ni Inno Setup ni `makeappx` ni el empaquetado de
Windows de `vpk` corren aquí, así que **la comparación de arriba no está
ejecutada de punta a punta**. Lo que sí está comprobado en esta máquina es el
SDK de Python de Velopack.

La prueba de verdad la hace `.github/workflows/instaladores.yml`: construye los
tres, y a cada uno le pasa el mismo examen en un Windows real —instalar,
instalar encima, comprobar que el ejecutable que quedó es el nuevo, desinstalar
y comprobar que los datos siguen—. Hasta que ese flujo pase, esto es una
recomendación razonada, no un resultado.
