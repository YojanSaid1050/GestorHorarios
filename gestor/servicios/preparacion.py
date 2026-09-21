"""Preparación de datos al inicio, independiente del transporte HTTP."""
from gestor import rutas
from gestor.registro import obtener

problemas_de_arranque: list[str] = []

def preparar_todo() -> None:
    from gestor.datos.base import preparar_base
    from gestor.servicios import siembra
    from gestor.servicios.acceso import (
        asegurar_cuentas_iniciales,
        marcar_las_claves_de_fabrica_que_siguen_puestas,
    )

    problemas_de_arranque.clear()
    try:
        preparar_base()
    except Exception as exc:                                       # noqa: BLE001
        obtener().exception('no se pudo preparar la base de datos')
        problemas_de_arranque.append(
            f'No se pudo preparar la base de datos en {rutas.BASE_DE_DATOS}: {exc}')
        return

    try:
        resultado = siembra.sembrar()
        if resultado.faltan:
            problemas_de_arranque.append(
                'A esta instalación le faltan archivos que deberían venir dentro del '
                f'programa: {", ".join(resultado.faltan)}. Puedes dejarlos en '
                f'{rutas.RAIZ_DATOS / "datos_iniciales"} y volver a abrir la aplicación, '
                'o reinstalarla. No generes esos meses de nuevo: se perdería la '
                'programación que ya está vigente.')
    except Exception as exc:                                       # noqa: BLE001
        obtener().exception('no se pudo sembrar la instalación')
        problemas_de_arranque.append(f'No se pudieron cargar los datos iniciales: {exc}')

    try:
        asegurar_cuentas_iniciales()
        # Y las instalaciones que ya existen, que es donde está el problema: la
        # oficina lleva meses con las dos contraseñas que vienen escritas dentro
        # del programa, porque nunca se le pidió otra cosa. Se marcan para que
        # haya que cambiarlas; a quien ya la cambió no se le toca nada.
        cuantas = marcar_las_claves_de_fabrica_que_siguen_puestas()
        if cuantas:
            obtener().info('%s cuenta(s) siguen con la contraseña de fábrica: se '
                           'les pedirá cambiarla antes de poder usar el programa',
                           cuantas)
    except Exception as exc:                                       # noqa: BLE001
        obtener().exception('no se pudieron asegurar las cuentas')
        problemas_de_arranque.append(f'No se pudieron preparar las cuentas: {exc}')
