# -*- coding: utf-8 -*-
"""Los colores y el tema: cómo se ve la aplicación y cómo sale el Excel.

Los mismos colores pintan la tabla en pantalla y las celdas del Excel, y eso es
a propósito: quien mira el papel y quien mira la pantalla tienen que ver lo
mismo.

Lo único que aquí tiene trampa es `separar_turnos`. Una paleta bonita puede
dejar dos códigos con colores casi iguales, y entonces el cuadro deja de leerse
de un vistazo —que es para lo que sirve el color— y hay que ir letra por letra.
Esa función separa los cuatro que más se confunden (AM, PM, ADM-GS y ADM-AC)
manteniendo el aire de la paleta elegida.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from gestor.datos.base import abierta, transaccion
from gestor.registro import obtener


def _leer(clave: str) -> Optional[str]:
    """Lee un ajuste. Si la base todavía no está, se trabaja con lo de fábrica.

    Puede llamarse antes de que exista el esquema —al arrancar, o si la carpeta
    de datos no se puede leer—. Que la aplicación abra con los colores de
    fábrica es mucho mejor que que no abra; pero **se deja constancia**, porque
    tragárselo en silencio fue lo que hizo que durante versiones nadie supiera
    que los ajustes no se estaban leyendo.
    """
    try:
        with abierta() as conexion:
            fila = conexion.execute(
                'SELECT valor FROM configuracion WHERE clave=?', (clave,)).fetchone()
    except Exception:                                              # noqa: BLE001
        obtener().warning('no se pudo leer el ajuste «%s»; se usa el de fábrica', clave)
        return None
    return str(fila['valor']) if fila else None


def _guardar(clave: str, valor: str) -> None:
    with transaccion() as conexion:
        conexion.execute(
            'INSERT INTO configuracion(clave, valor) VALUES(?,?) '
            'ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor', (clave, valor))


DEFAULT_EXCEL_COLORS: dict[str, str] = {
    'header': '5B2A86',
    'saturday_header': '684488',
    'sunday_header': '76518F',
    'holiday_header': 'A878CA',
    'admin_friday_header': 'C9A7E8',
    'admin_friday_cell': 'EAF3E7',
    # AM en blanco, PM en lila y ADM-GS en verde: ver `separar_turnos`.
    'AM': 'FFFFFF',
    'PM': 'E2D9F3',
    'ADM-GS': 'D9EAD3',
    'ADM-AC': 'D9EAF7',
    'D': 'D9D9D9',
    'VAC': 'D9D2E9',
    'INC': 'F4CCCC',
    'PER': 'FCE5CD',
    'CAP': 'CFE2F3',
    # Días de otro mes que completan la primera y la última semana del período.
    'otro_mes_header': '41648C',
    'otro_mes_cell': 'EDF3F9',
}

_COLOR_RE = re.compile(r'^[0-9A-Fa-f]{6}$')


# ---------------------------------------------------------------------------
# Separación de los cuatro códigos que se leen de un vistazo
# ---------------------------------------------------------------------------
# En la tabla del horario hay cuatro celdas que la vista tiene que distinguir
# sin pararse a leer la letra: AM, PM, ADM-GS y ADM-AC. Cada paleta las traía
# con tonos propios y, en todas, PM y ADM-GS acababan en el mismo verde: dos
# jornadas distintas con el mismo aspecto.
#
# Se resuelve con una regla que no depende de la paleta:
#
#   AM      · blanco siempre. Es el turno más frecuente y el que abre el día;
#             en blanco la tabla respira y todo lo demás resalta sobre él.
#   PM      · el verde propio de la paleta.
#   ADM-GS  · familia lila/violeta, nunca verde: es una jornada administrativa,
#             no un turno operativo, y debe verse como otra cosa.
#   ADM-AC  · azul, que es como se ha leído siempre.
#
# La regla se aplica a todas las paletas —las de fábrica y las derivadas del
# color de la aplicación—, así que ninguna futura puede volver a mezclarlas.
TURNO_AM_FIJO = 'FFFFFF'
# El lila es de PM y el verde de ADM-GS: se intercambiaron respecto a la
# primera versión de esta regla, a petición de la operación.
TURNO_PM_LILA = 'E2D9F3'
TURNO_PM_LILA_CLARO = 'EDE6F7'
ADM_AC_POR_DEFECTO = 'D9EAF7'


def _luminancia(hex_color: str) -> float:
    try:
        r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, IndexError):
        return 1.0
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255


def _matiz(hex_color: str):
    """Matiz en grados, o ``None`` si el color es un gris sin tono.

    Los colores del horario son muy claros, así que la saturación es baja en
    todos y no sirve para separarlos: lo que distingue un verde pálido de un
    lila pálido es el matiz. Por eso se compara ahí y no en familias anchas.
    """
    try:
        r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except (ValueError, IndexError):
        return None
    mayor, menor = max(r, g, b), min(r, g, b)
    delta = mayor - menor
    if delta < 0.02:
        return None
    if mayor == r:
        h = ((g - b) / delta) % 6
    elif mayor == g:
        h = (b - r) / delta + 2
    else:
        h = (r - g) / delta + 4
    return (h * 60) % 360


def _se_confunden(a: str, b: str) -> bool:
    """¿Dos celdas contiguas se leerían como el mismo color?"""
    ha, hb = _matiz(a), _matiz(b)
    if ha is None and hb is None:
        return True
    if ha is None or hb is None:
        return False
    diferencia = abs(ha - hb)
    return min(diferencia, 360 - diferencia) < 45


def _mezclar(hex_color: str, hacia: str, proporcion: float) -> str:
    """Mezcla dos colores. proporcion=0 devuelve el primero; 1, el segundo."""
    a = [int(hex_color[i:i+2], 16) for i in (0, 2, 4)]
    b = [int(hacia[i:i+2], 16) for i in (0, 2, 4)]
    return ''.join(f'{round(x + (y - x) * proporcion):02X}'
                   for x, y in zip(a, b, strict=True))


def separar_turnos(colores: dict[str, str]) -> dict[str, str]:
    """Deja AM en blanco y PM fuera de la familia de ADM-GS.

    El verde de la paleta se queda en ADM-GS y PM pasa al lila. Es al revés de
    como estaba al principio: se intercambiaron a petición de la operación,
    que lee mejor el turno de tarde en lila y la jornada administrativa en
    verde.

    Solo toca lo justo: si PM ya estaba en una familia distinta a la de ADM-GS
    —porque alguien lo ajustó a mano— se respeta tal cual.
    """
    salida = dict(colores)
    salida['AM'] = TURNO_AM_FIJO
    pm = str(salida.get('PM') or '').upper().lstrip('#')
    adm_gs = str(salida.get('ADM-GS') or '').upper().lstrip('#')
    if not _COLOR_RE.match(pm):
        return salida
    if _COLOR_RE.match(adm_gs) and _se_confunden(pm, adm_gs):
        # Se conserva la claridad del tono original para no romper el aire de
        # la paleta: solo cambia la familia de color.
        claro = _luminancia(pm) > 0.86
        salida['PM'] = TURNO_PM_LILA_CLARO if claro else TURNO_PM_LILA
    adm_ac = str(salida.get('ADM-AC') or '').upper().lstrip('#')
    if _COLOR_RE.match(adm_ac) and _se_confunden(adm_ac, str(salida.get('ADM-GS') or '')):
        salida['ADM-AC'] = ADM_AC_POR_DEFECTO

    # El último viernes administrativo del mes no es un turno aparte: es un día
    # administrativo señalado. Su celda tiene que leerse como ADM-GS —el mismo
    # tono, más claro— y nunca como PM. Al intercambiar PM y ADM-GS, el tono
    # que traía este día se quedó en la familia del lila y el viernes acababa
    # pareciendo turno de tarde, que es justo lo contrario de lo que dice.
    if _COLOR_RE.match(adm_gs):
        viernes = str(salida.get('admin_friday_cell') or '').upper().lstrip('#')
        propio = bool(_COLOR_RE.match(viernes))
        confunde_con_pm = propio and _se_confunden(viernes, str(salida['PM']))
        de_la_familia = propio and _se_confunden(viernes, adm_gs)
        if confunde_con_pm or not de_la_familia:
            salida['admin_friday_cell'] = _mezclar(adm_gs, 'FFFFFF', 0.45)
    return salida



# Paletas completas para el horario y el Excel. Se aplican de un clic y después
# se puede seguir ajustando cada color por separado: son un punto de partida,
# no una alternativa al ajuste manual.
PALETAS_EXCEL: dict[str, dict] = {
    'actual': {
        'nombre': 'La de siempre',
        'descripcion': 'Morados de la aplicación con los turnos en tonos suaves.',
        'colores': dict(DEFAULT_EXCEL_COLORS),
    },
    'contraste': {
        'nombre': 'Alto contraste',
        'descripcion': 'Colores más saturados: se distinguen de lejos y en proyector.',
        'colores': {
            **DEFAULT_EXCEL_COLORS,
            'header': '3F1D66', 'saturday_header': '5B3A80', 'sunday_header': '7A3FA8',
            'holiday_header': 'B14BD8', 'admin_friday_header': '8E5FC4', 'admin_friday_cell': 'E3D2F5',
            'AM': 'FFE08A', 'PM': '89CCA5', 'ADM-GS': 'A9DDB4', 'ADM-AC': '9FC9EC',
            'D': 'BFBFBF', 'VAC': 'C4B3E0', 'INC': 'F2A6A6', 'PER': 'F8C68C', 'CAP': 'A6CDEA',
            'otro_mes_header': '2E4E70', 'otro_mes_cell': 'DCE7F2',
        },
    },
    'impresion': {
        'nombre': 'Para imprimir',
        'descripcion': 'Grises y tramas claras: gasta poca tinta y se lee en blanco y negro.',
        'colores': {
            'header': '3C3C3C', 'saturday_header': '5A5A5A', 'sunday_header': '6E6E6E',
            'holiday_header': '8A8A8A', 'admin_friday_header': '9C9C9C', 'admin_friday_cell': 'EDEDED',
            'AM': 'F2F2F2', 'PM': 'D6D6D6', 'ADM-GS': 'E0E0E0', 'ADM-AC': 'CCCCCC',
            'D': 'A6A6A6', 'VAC': 'E8E8E8', 'INC': 'DCDCDC', 'PER': 'EFEFEF', 'CAP': 'E4E4E4',
            'otro_mes_header': '767676', 'otro_mes_cell': 'F7F7F7',
        },
    },
    'sobria': {
        'nombre': 'Sobria',
        'descripcion': 'Azules y verdes apagados, sin morado. Aspecto más institucional.',
        'colores': {
            'header': '1F3B63', 'saturday_header': '2F4F7A', 'sunday_header': '3D6392',
            'holiday_header': '5C86B8', 'admin_friday_header': '7BA0C9', 'admin_friday_cell': 'E4EDF6',
            'AM': 'FBEFD3', 'PM': 'D2E6DC', 'ADM-GS': 'DDEBDC', 'ADM-AC': 'DAE6F2',
            'D': 'DEDEDE', 'VAC': 'DDE2EF', 'INC': 'F1D5D5', 'PER': 'F6E3CE', 'CAP': 'D8E6F0',
            'otro_mes_header': '46617F', 'otro_mes_cell': 'EEF3F8',
        },
    },
    'calida': {
        'nombre': 'Cálida',
        'descripcion': 'Tierras y verdes oliva. Menos saturación, más contraste entre turnos.',
        'colores': {
            'header': '6B3F2A', 'saturday_header': '855140', 'sunday_header': '9E6A54',
            'holiday_header': 'C08B6E', 'admin_friday_header': 'D0A88E', 'admin_friday_cell': 'F5E7DC',
            'AM': 'FCE9C4', 'PM': 'D3DEB8', 'ADM-GS': 'DFE6C6', 'ADM-AC': 'E4DCC9',
            'D': 'DCD6CE', 'VAC': 'E9DECB', 'INC': 'EFCDBE', 'PER': 'F6DEC2', 'CAP': 'DDE3D2',
            'otro_mes_header': '8A6A57', 'otro_mes_cell': 'F5EFE8',
        },
    },
    'pastel': {
        'nombre': 'Pastel',
        'descripcion': 'Tonos muy claros y encabezados suaves. Cansa menos en pantalla.',
        'colores': {
            'header': '7C6BA8', 'saturday_header': '8E80B6', 'sunday_header': 'A095C4',
            'holiday_header': 'BCB1D9', 'admin_friday_header': 'D3CCE8', 'admin_friday_cell': 'F0ECF8',
            'AM': 'FFF6DE', 'PM': 'DCEFE4', 'ADM-GS': 'E4F2E1', 'ADM-AC': 'E4F0FA',
            'D': 'E6E6E6', 'VAC': 'E7E1F2', 'INC': 'FADCDC', 'PER': 'FDEEDD', 'CAP': 'E1EEF8',
            'otro_mes_header': '6E7E96', 'otro_mes_cell': 'F3F6FA',
        },
    },
    'noche': {
        'nombre': 'Encabezados oscuros',
        'descripcion': 'Encabezados casi negros con turnos claros. Muy legible impreso a color.',
        'colores': {
            'header': '1C1C24', 'saturday_header': '2B2B36', 'sunday_header': '3A3A48',
            'holiday_header': '55556A', 'admin_friday_header': '7A7A90', 'admin_friday_cell': 'E6E6EC',
            'AM': 'FFEDB8', 'PM': 'C3E3D2', 'ADM-GS': 'CFE9CF', 'ADM-AC': 'CEE4F6',
            'D': 'D2D2D8', 'VAC': 'D6CFE8', 'INC': 'F3C4C4', 'PER': 'FBDCB8', 'CAP': 'C6DDF1',
            'otro_mes_header': '4A4A5C', 'otro_mes_cell': 'EFEFF3',
        },
    },
    'menta': {
        'nombre': 'Menta',
        'descripcion': 'Verdes fríos con acentos coral para las novedades.',
        'colores': {
            'header': '146356', 'saturday_header': '1F7A6B', 'sunday_header': '2E9382',
            'holiday_header': '5FB5A4', 'admin_friday_header': '92D0C3', 'admin_friday_cell': 'E1F4EF',
            'AM': 'FFF4D6', 'PM': 'C9E9DA', 'ADM-GS': 'D6EFE2', 'ADM-AC': 'D6EAF2',
            'D': 'DCDCDC', 'VAC': 'DDE4F0', 'INC': 'F7CFC7', 'PER': 'FBE2C9', 'CAP': 'D2E9EF',
            'otro_mes_header': '3F6F72', 'otro_mes_cell': 'EDF6F6',
        },
    },
    'indigo': {
        'nombre': 'Índigo',
        'descripcion': 'Azules profundos y turnos fríos. Buen contraste sin saturar.',
        'colores': {
            'header': '2A2F6B', 'saturday_header': '3A4185', 'sunday_header': '4C55A0',
            'holiday_header': '7B83C4', 'admin_friday_header': 'A9AFDD', 'admin_friday_cell': 'E7E9F7',
            'AM': 'FFF0C9', 'PM': 'D2E6DE', 'ADM-GS': 'DCEAE0', 'ADM-AC': 'D5E3F7',
            'D': 'DBDBE2', 'VAC': 'DCDAF0', 'INC': 'F4CDD3', 'PER': 'FBE0C6', 'CAP': 'D3E1F5',
            'otro_mes_header': '4C5670', 'otro_mes_cell': 'EEF1F7',
        },
    },
    'arena': {
        'nombre': 'Arena',
        'descripcion': 'Beige y gris cálido. Aspecto de documento impreso.',
        'colores': {
            'header': '5A5044', 'saturday_header': '6E6254', 'sunday_header': '857767',
            'holiday_header': 'A89785', 'admin_friday_header': 'C9BCAB', 'admin_friday_cell': 'F1EBE2',
            'AM': 'FBF0D8', 'PM': 'DCE3D2', 'ADM-GS': 'E3E8D8', 'ADM-AC': 'E2E6E2',
            'D': 'DEDAD3', 'VAC': 'E6E0D6', 'INC': 'EED2C9', 'PER': 'F6E4CE', 'CAP': 'DFE6E4',
            'otro_mes_header': '7A7266', 'otro_mes_cell': 'F5F2EC',
        },
    },
    'daltonico': {
        'nombre': 'Fácil de distinguir',
        'descripcion': 'Azul y naranja en vez de verde y rojo, para daltonismo rojo-verde.',
        'colores': {
            'header': '25405E', 'saturday_header': '335878', 'sunday_header': '447195',
            'holiday_header': '6E9AB8', 'admin_friday_header': 'A3C2D6', 'admin_friday_cell': 'E6F0F6',
            'AM': 'FFE0B2', 'PM': 'CFE4F5', 'ADM-GS': 'BBDDF2', 'ADM-AC': 'D7E9F7',
            'D': 'D6D6D6', 'VAC': 'DCD5EC', 'INC': 'F6D6B0', 'PER': 'FBE8C8', 'CAP': 'C9DDEE',
            'otro_mes_header': '5A6472', 'otro_mes_cell': 'EFF2F5',
        },
    },
}


# Paletas derivadas del color de la aplicación
# ---------------------------------------------------------------------------
# Quien elige "Verde" para la aplicación normalmente quiere que el horario y el
# Excel vayan a juego. En vez de escribir a mano diecisiete colores por cada
# tema, se derivan de las mismas variables que usa la interfaz: el encabezado
# toma el color principal, los encabezados secundarios sus tonos intermedios y
# los días de otro mes el tono oscuro. Los códigos de turno y de novedad se
# mantienen suaves y reconocibles en todas las familias, porque su función es
# distinguirse entre sí, no repetir el color de la marca.
_TURNOS_SUAVES = {
    # PM en lila y ADM-GS en verde, igual que en el resto de paletas.
    'AM': 'FFFFFF', 'PM': 'E2D9F3', 'ADM-GS': 'D9EAD3', 'ADM-AC': 'D9EAF7',
    'D': 'D9D9D9', 'VAC': 'D9D2E9', 'INC': 'F4CCCC', 'PER': 'FCE5CD', 'CAP': 'CFE2F3',
}


def _paleta_desde_tema(tema: dict) -> dict[str, str]:
    principal = tema['primary']
    medio = tema['mid']
    claro = tema['light']
    palido = tema['pale']
    oscuro = tema['dark']
    return {
        'header': principal,
        'saturday_header': _mezclar(principal, medio, 0.45),
        'sunday_header': medio,
        'holiday_header': _mezclar(medio, claro, 0.45),
        'admin_friday_header': _mezclar(medio, claro, 0.75),
        'admin_friday_cell': _mezclar(claro, 'FFFFFF', 0.45),
        **_TURNOS_SUAVES,
        'otro_mes_header': oscuro,
        'otro_mes_cell': palido,
    }


def _normalizar_paletas() -> None:
    """Aplica la regla de separación de turnos a todas las paletas."""
    for paleta in PALETAS_EXCEL.values():
        paleta['colores'] = separar_turnos(paleta['colores'])


def _registrar_paletas_de_tema() -> None:
    for clave, tema in APP_THEMES.items():
        if clave == 'morado':
            # El morado ya está representado por «La de siempre».
            continue
        PALETAS_EXCEL[f'tema_{clave}'] = {
            'nombre': f"A juego · {tema['nombre']}",
            'descripcion': f"Toma los colores de la aplicación en {tema['nombre'].lower()}.",
            'colores': separar_turnos(_paleta_desde_tema(tema)),
            'familia': 'tema',
        }
    _normalizar_paletas()


PALETA_PROPIA_ID = 'personalizada'


def listar_paletas_excel() -> list[dict]:
    salida = []
    # La combinación propia va primero: es la que alguien construyó a mano y la
    # que va a querer recuperar si probó otras.
    propia = obtener_paleta_personalizada()
    if propia:
        salida.append({
            'id': PALETA_PROPIA_ID,
            'nombre': 'La mía',
            'descripcion': 'Los colores que ajustaste tú. Se actualiza sola cada vez que cambias uno.',
            'familia': 'propia',
            'colores': propia,
        })
    salida.extend(
        {'id': clave, 'nombre': p['nombre'], 'descripcion': p['descripcion'],
         'familia': p.get('familia', 'horario'), 'colores': dict(p['colores'])}
        for clave, p in PALETAS_EXCEL.items()
    )
    return salida


def aplicar_paleta_excel(paleta: str) -> dict:
    """Vuelca una paleta completa sobre la configuración de colores.

    Aplicar una paleta de la lista **no** toca la combinación propia: se puede
    ir probando paletas sin miedo, porque «La mía» sigue esperando con lo que
    la persona había dejado ajustado.
    """
    clave = str(paleta or '')
    if clave == PALETA_PROPIA_ID:
        propia = obtener_paleta_personalizada()
        if not propia:
            raise ValueError('Todavía no has ajustado ningún color, así que no hay combinación propia que aplicar.')
        return guardar_colores_excel(propia, recordar_como_propia=False)
    elegida = PALETAS_EXCEL.get(clave)
    if not elegida:
        raise ValueError('Esa paleta no existe.')
    return guardar_colores_excel(dict(elegida['colores']), recordar_como_propia=False)


APP_THEMES: dict[str, dict[str, str]] = {
    'morado': {'nombre': 'Morado', 'primary': '5B2A86', 'dark': '402060', 'mid': '7D4AA8', 'light': 'E8D9F6', 'pale': 'F7F1FC', 'focus': 'B995D5', 'border': 'CDBBDA', 'soft_border': 'DDCAED'},
    'azul': {'nombre': 'Azul', 'primary': '2563A6', 'dark': '174A7E', 'mid': '4F83C2', 'light': 'DCEBFA', 'pale': 'F3F8FD', 'focus': '8AB6E6', 'border': 'B7D1EB', 'soft_border': 'C9DDF1'},
    'rojo': {'nombre': 'Rojo coral', 'primary': 'C74343', 'dark': '9F3030', 'mid': 'D16666', 'light': 'F8DEDE', 'pale': 'FDF5F5', 'focus': 'E69A9A', 'border': 'E8B8B8', 'soft_border': 'F0CCCC'},
    'verde': {'nombre': 'Verde', 'primary': '2F7D5A', 'dark': '245F46', 'mid': '52A079', 'light': 'DCF0E6', 'pale': 'F3FAF6', 'focus': '8CC6AA', 'border': 'B8DCCB', 'soft_border': 'CDE7DA'},
    'turquesa': {'nombre': 'Turquesa', 'primary': '117A7A', 'dark': '116A6A', 'mid': '42A7A7', 'light': 'D9F1F1', 'pale': 'F2FAFA', 'focus': '82CACA', 'border': 'AFDCDC', 'soft_border': 'C9E8E8'},
    'naranja': {'nombre': 'Naranja', 'primary': 'B85C24', 'dark': 'A34E1E', 'mid': 'E18B56', 'light': 'FBE5D8', 'pale': 'FDF7F3', 'focus': 'EAB18E', 'border': 'F0C9B0', 'soft_border': 'F6DCCC'},
    'rosado': {'nombre': 'Rosado', 'primary': 'B94E7A', 'dark': '984064', 'mid': 'D97AA0', 'light': 'F7DFE9', 'pale': 'FDF5F8', 'focus': 'E7A3BE', 'border': 'E9B8CB', 'soft_border': 'F2CFDC'},
    'cablemovil': {
        'nombre': 'CABLEMOVIL institucional',
        'primary': '1E233E', 'dark': '14182B', 'mid': '223B85',
        'light': 'E7EAF3', 'pale': 'F6F7FA', 'focus': 'FB0F0C',
        'border': 'AEB7D0', 'soft_border': 'D6DCEB',
        'accent': 'FB0F0C',
        'brand_asset': 'CABLEMOVIL_header.png',
        'login_asset': 'CABLEMOVIL_logo.png',
    },
}
DEFAULT_APP_THEME = 'morado'

_registrar_paletas_de_tema()


# Claro, oscuro o el del sistema. Se guarda la elección, no el resultado: quien
# deja «el del sistema» y cambia Windows a oscuro por la tarde ve la aplicación
# cambiar con él, sin volver a entrar aquí.
MODOS_APP: dict[str, str] = {
    'claro': 'Claro',
    'oscuro': 'Oscuro',
    'sistema': 'El del sistema',
}
DEFAULT_APP_MODE = 'sistema'
CLAVE_MODO_APP = 'app_mode'


def obtener_modo_app() -> str:
    valor = (_leer(CLAVE_MODO_APP) or '').strip().lower()
    return valor if valor in MODOS_APP else DEFAULT_APP_MODE


def guardar_modo_app(modo: str) -> str:
    modo = str(modo or '').strip().lower()
    if modo not in MODOS_APP:
        raise ValueError('Elige entre claro, oscuro o el del sistema.')
    _guardar(CLAVE_MODO_APP, modo)
    return modo


def obtener_tema_app() -> dict:
    elegido = (_leer('app_theme') or '').strip()
    return {'id': elegido if elegido in APP_THEMES else DEFAULT_APP_THEME,
            **APP_THEMES.get(elegido, APP_THEMES[DEFAULT_APP_THEME])}


def guardar_tema_app(tema_id: str) -> dict:
    tema_id = str(tema_id or '').strip().lower()
    if tema_id not in APP_THEMES:
        raise ValueError(
            f'Ese tema no existe. Los que hay son: {", ".join(sorted(APP_THEMES))}.')
    _guardar('app_theme', tema_id)
    return {'id': tema_id, **APP_THEMES[tema_id]}


def restablecer_tema_app() -> dict:
    with transaccion() as conexion:
        conexion.execute("DELETE FROM configuracion WHERE clave='app_theme'")
    return {'id': DEFAULT_APP_THEME, **APP_THEMES[DEFAULT_APP_THEME]}


def listar_temas_app() -> list[dict]:
    return [{'id': i, **t} for i, t in APP_THEMES.items()]


# ------------------------------------------------------- los colores del Excel

def _normalizar_color(valor: str) -> str:
    texto = str(valor or '').strip().lstrip('#').upper()
    if len(texto) == 3:
        texto = ''.join(c * 2 for c in texto)
    if len(texto) != 6 or any(c not in '0123456789ABCDEF' for c in texto):
        raise ValueError(f'«{valor}» no es un color válido. Escríbelo como RRGGBB.')
    return texto


def obtener_colores_excel() -> dict[str, str]:
    """Los colores con los que sale el Excel.

    Se parte de los de fábrica y se pisan con los guardados: así, si algún día
    se añade un código nuevo, las instalaciones que ya existen lo reciben con su
    color por defecto en vez de quedarse sin ninguno.
    """
    colores = dict(DEFAULT_EXCEL_COLORS)
    guardados = _leer('excel_colors')
    if guardados:
        try:
            colores.update({k: _normalizar_color(v)
                            for k, v in json.loads(guardados).items()
                            if k in DEFAULT_EXCEL_COLORS})
        except Exception:                                          # noqa: BLE001
            pass
    return separar_turnos(colores)


def obtener_paleta_personalizada():
    """Los colores que alguien ajustó a mano, si los hay.

    Se guardan aparte de los que están puestos ahora mismo. Así se pueden ir
    probando paletas de la lista sin miedo: «La mía» sigue esperando con lo que
    esa persona había dejado, y volver a ella es un clic.
    """
    guardada = _leer('excel_colors_propia')
    if not guardada:
        return None
    try:
        return {k: _normalizar_color(v) for k, v in json.loads(guardada).items()
                if k in DEFAULT_EXCEL_COLORS}
    except Exception:                                              # noqa: BLE001
        return None


def guardar_paleta_personalizada(colores: dict) -> None:
    _guardar('excel_colors_propia', json.dumps(colores, ensure_ascii=False))


def guardar_colores_excel(valores: dict, recordar_como_propia: bool = True) -> dict[str, str]:
    limpios = {k: _normalizar_color(v) for k, v in (valores or {}).items()
               if k in DEFAULT_EXCEL_COLORS}
    if not limpios:
        raise ValueError('No se reconoció ningún color de los enviados.')
    actuales = dict(DEFAULT_EXCEL_COLORS)
    guardados = _leer('excel_colors')
    if guardados:
        try:
            actuales.update(json.loads(guardados))
        except Exception:                                          # noqa: BLE001
            pass
    actuales.update(limpios)
    _guardar('excel_colors', json.dumps(actuales, ensure_ascii=False))
    if recordar_como_propia:
        # Solo cuando alguien cambia un color a mano. Aplicar una paleta de la
        # lista no puede pisar «La mía»: sería perder lo que construyó.
        guardar_paleta_personalizada(actuales)
    return obtener_colores_excel()


def restablecer_colores_excel() -> dict[str, str]:
    with transaccion() as conexion:
        conexion.execute("DELETE FROM configuracion WHERE clave='excel_colors'")
    return obtener_colores_excel()


def restablecer_color_excel(clave: str) -> dict[str, str]:
    if clave not in DEFAULT_EXCEL_COLORS:
        raise ValueError(f'«{clave}» no es uno de los colores configurables.')
    return guardar_colores_excel({clave: DEFAULT_EXCEL_COLORS[clave]})
