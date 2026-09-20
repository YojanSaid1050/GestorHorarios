# -*- coding: utf-8 -*-
"""El personal: quién trabaja aquí, cómo rota y desde cuándo.

Lo que hay que entender de esta pantalla es que **un cambio no es retroactivo**.
Corregir hoy el turno de alguien abre un tramo nuevo desde el lunes que se
indique; los meses ya publicados se siguen leyendo con la configuración que
tenían. Sin eso, arreglar un dato en noviembre cambiaba agosto, septiembre y
octubre, y la oficina veía cómo un horario ya repartido dejaba de coincidir con
el papel de la pared.

Y **nada se borra**. Retirar a alguien deja escrito desde qué día ya no está:
sale de los horarios que se generen a partir de entonces y sigue apareciendo en
los que ya se repartieron, que es donde su nombre tiene que seguir estando.
Borrar de verdad solo se admite para un alta creada por error, y únicamente
mientras no haya dejado ningún rastro.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, field_validator

from gestor.datos import personal
from gestor.dominio import calendario, cobertura
from gestor.motor.comun import turno_base_de
from gestor.servicios import cambios_de_turno, historial, periodos

router = APIRouter(prefix='/api/empleados', tags=['personal'])


class Ficha(BaseModel):
    """Lo que la pantalla envía al guardar una persona.

    Llega plana y con `vigente_desde` dentro, que es como lleva enviándose
    siempre. Los campos que la pantalla manda por costumbre y aquí no cambian
    nada —`auto_asignado`— se admiten y se ignoran: rechazar la petición por un
    campo de más solo conseguiría que no se pudiera guardar a nadie.
    """
    nombre: str
    cargo: Optional[str] = None
    area: str
    tipo_turno: str
    turno_fijo: Optional[str] = None
    descanso_fijo: Optional[int] = None
    pareja_id: Optional[int] = None
    inicio_rotacion: Optional[str] = None
    fecha_ancla_rotacion: Optional[str] = None
    orden_rotacion: int = 0
    exento_especiales: bool = False
    cobertura_dias: Optional[list[int]] = None
    es_nuevo: bool = False
    auto_asignado: bool = False
    activo: bool = True
    vigente_desde: Optional[str] = None


class Retiro(BaseModel):
    """La salida de alguien. La fecha es el **último día vigente**.

    Se comprueba aquí, antes de que nada llegue al endpoint. Se comprobaba
    después de escribir: se retiraba a la persona con el texto tal cual en
    `retirado_desde` y solo entonces se intentaba leer la fecha para calcular el
    día siguiente. El error saltaba, la respuesta era un fallo, y la persona se
    quedaba retirada con una fecha que no es una fecha —invisible en la
    plantilla y sin forma de deshacerlo desde la pantalla—.
    """

    fecha_retiro: str
    motivo: Optional[str] = None

    @field_validator('fecha_retiro')
    @classmethod
    def _es_una_fecha(cls, valor: str) -> str:
        from datetime import date as _date
        try:
            return _date.fromisoformat(str(valor)[:10]).isoformat()
        except (TypeError, ValueError):
            raise ValueError(
                f'«{valor}» no es una fecha. Tiene que ser el último día que la '
                'persona trabaja, con el formato AAAA-MM-DD.') from None


class CambioDeTurno(BaseModel):
    vigente_desde: str
    tipo_turno: str
    turno_fijo: Optional[str] = None
    inicio_rotacion: Optional[str] = None
    descanso_fijo: Optional[int] = None
    aplicar_a_pareja: bool = True
    motivo: Optional[str] = None


MOTIVOS = {'renuncia': 'renuncia', 'fin_contrato': 'terminación de contrato',
           'traslado': 'traslado', 'otro': 'retiro'}


def _validar(ficha: dict) -> None:
    if ficha.get('area') not in cobertura.AREAS:
        raise ValueError(f'El área tiene que ser una de: {", ".join(cobertura.AREAS)}.')
    if ficha.get('tipo_turno') not in ('fijo', 'rotativo', 'administrativo'):
        raise ValueError('El tipo de turno tiene que ser fijo, rotativo o administrativo.')
    if ficha.get('tipo_turno') == 'fijo' and ficha.get('turno_fijo') not in ('AM', 'PM'):
        raise ValueError('Quien tiene turno fijo necesita saber si es de mañana o de tarde.')
    dias = ficha.get('cobertura_dias')
    if dias is not None and any(int(d) < 0 or int(d) > 6 for d in dias):
        raise ValueError('Los días de cobertura van del 0 (lunes) al 6 (domingo).')


def _obtener(empleado_id: int) -> dict:
    ficha = personal.obtener(empleado_id)
    if ficha is None:
        raise ValueError('Esa persona ya no está en la plantilla.')
    return ficha


def _a_columnas(datos: dict, es_alta: bool) -> dict:
    """De lo que envía la pantalla a lo que entiende la base.

    `vigente_desde` significa dos cosas distintas según de dónde venga, y
    confundirlas borraba la historia de una persona:

    * **al dar de alta** es su primer día, y ahí sí es la columna `alta_desde`;
    * **al editar la ficha** es «desde cuándo rige este cambio», que es otra
      cosa: la persona lleva en la oficina desde antes. Eso se guarda como un
      tramo en `empleados_historial`, no tocando su fecha de alta.

    Las dos usaban la misma traducción. Corregirle el turno a alguien poniendo
    «rige desde el 16 de noviembre» le cambiaba el alta de agosto a noviembre y
    **la borraba de todos los meses anteriores**: octubre se volvía a generar
    sin ella, y sus turnos se repartían entre los demás. Un mes ya entregado
    cambiaba solo por haber corregido una ficha.
    """
    columnas = {k: v for k, v in datos.items() if k not in ('auto_asignado', 'vigente_desde')}
    if es_alta and datos.get('vigente_desde'):
        columnas['alta_desde'] = datos['vigente_desde']
    return columnas


#: Cómo se dice cada día de la semana en la columna «Descanso». El número es el
#: que guarda `descanso_fijo`, con el lunes en 0, igual que Python.
DIAS_DE_LA_SEMANA = ('lunes', 'martes', 'miércoles', 'jueves', 'viernes',
                     'sábado', 'domingo')


def _descanso_mostrado(persona: dict) -> str:
    dia = persona.get('descanso_fijo')
    if dia is None:
        return 'Variable'
    try:
        return DIAS_DE_LA_SEMANA[int(dia)].capitalize()
    except (TypeError, ValueError, IndexError):
        return 'Variable'


@router.get('')
def listar(incluir_inactivos: bool = False):
    """La plantilla, con las columnas ya escritas para leerlas.

    `turno_base_mostrado` y `descanso_mostrado` se calculan aquí porque la tabla
    de Personal los enseña tal cual. No existían: la pantalla los leía con
    `|| ''` y `|| 'Variable'`, así que la columna **«Turno base» salía en blanco
    para toda la oficina** y la de **«Descanso» decía «Variable» para todos**,
    incluida la gente que tiene un día fijo configurado. Nada fallaba; solo
    faltaba, y lo que faltaba se parecía a un dato.

    El turno base sale de la misma regla que usa el horario
    (`gestor.motor.comun.turno_base_de`), no de una copia escrita aquí: que la
    tabla de Personal y la columna «Base» del horario digan cosas distintas de
    la misma persona es exactamente el fallo que se acaba de arreglar.
    """
    gente = personal.listar(incluir_retirados=incluir_inactivos)
    for persona in gente:
        persona['cobertura_texto'] = cobertura.describir(persona.get('cobertura_dias'))
        persona['turno_base_mostrado'] = turno_base_de(persona) or '—'
        persona['descanso_mostrado'] = _descanso_mostrado(persona)
    return gente


@router.get('/cambios-turno')
def cambios_programados():
    return {'ok': True, 'cambios': cambios_de_turno.programados()}


@router.post('')
def crear(ficha: Ficha):
    datos = ficha.model_dump()
    _validar(datos)
    if not str(datos.get('nombre') or '').strip():
        raise ValueError('Escribe el nombre de la persona.')
    pareja = datos.pop('pareja_id', None)
    identificador = personal.crear(_a_columnas(datos, es_alta=True))
    if pareja:
        personal.emparejar(identificador, int(pareja))
    historial.anotar('alta_personal', 'empleado',
                     {'id': identificador, 'nombre': datos['nombre']})
    aviso = periodos.avisar_desde(
        datos.get('vigente_desde') or str(calendario.PRIMER_DIA),
        f'entró {datos["nombre"]}', datos['area'], origen='personal')
    return {'ok': True, 'id': identificador,
            'mensaje': f'{datos["nombre"]} queda dada de alta.' + aviso}


@router.put('/{empleado_id}')
def actualizar(empleado_id: int, ficha: Ficha):
    """Guarda la ficha, abriendo un tramo nuevo desde la fecha indicada.

    La fecha llega dentro de la propia ficha porque la pantalla la pide en el
    mismo formulario: quien corrige un turno decide a la vez desde cuándo rige.
    """
    antes = _obtener(empleado_id)
    datos = ficha.model_dump()
    _validar(datos)
    pareja = datos.pop('pareja_id', 'sin cambio')
    desde = datos.get('vigente_desde')
    personal.actualizar(empleado_id, _a_columnas(datos, es_alta=False), desde)
    if pareja != 'sin cambio':
        personal.emparejar(empleado_id, int(pareja) if pareja else None)
    historial.anotar('cambio_personal', 'empleado', {
        'id': empleado_id, 'nombre': antes['nombre'], 'vigente_desde': desde})
    aviso = periodos.avisar_desde(desde or str(calendario.PRIMER_DIA),
                                 f'cambió la ficha de {antes["nombre"]}', datos['area'],
                                 origen='personal')
    return {'ok': True, 'mensaje': f'{datos["nombre"]} queda guardada.' + aviso}


@router.post('/{empleado_id}/retirar')
def retirar(empleado_id: int, retiro: Retiro):
    """Marca la salida. No borra: su rastro en meses publicados tiene que quedar.

    La fecha es el **último día vigente**, así que lo que cambia empieza al día
    siguiente. Marcar desde el propio día del retiro haría que el mes que
    contiene su último día bueno pareciera equivocado.
    """
    ficha = _obtener(empleado_id)
    personal.retirar(empleado_id, retiro.fecha_retiro)
    etiqueta = MOTIVOS.get(str(retiro.motivo or 'otro'), 'retiro')
    historial.anotar('retiro_personal', 'empleado', {
        'id': empleado_id, 'nombre': ficha['nombre'],
        'fecha_retiro': retiro.fecha_retiro, 'motivo': etiqueta})
    from datetime import date, timedelta
    dia_siguiente = (date.fromisoformat(str(retiro.fecha_retiro)[:10])
                     + timedelta(days=1)).isoformat()
    aviso = periodos.avisar_desde(dia_siguiente, f'se retiró {ficha["nombre"]}',
                                  ficha['area'], origen='personal')
    return {'ok': True, 'fecha_retiro': retiro.fecha_retiro, 'mensaje': (
        f'{ficha["nombre"]} queda retirada por {etiqueta}; su último día vigente es el '
        f'{retiro.fecha_retiro}. Los meses ya publicados la siguen mostrando; los que se '
        'generen después, no.' + aviso)}


@router.post('/{empleado_id}/reactivar')
def reactivar(empleado_id: int):
    ficha = _obtener(empleado_id)
    personal.reactivar(empleado_id)
    historial.anotar('reactivacion_personal', 'empleado',
                     {'id': empleado_id, 'nombre': ficha['nombre']})
    aviso = periodos.avisar_desde(
        ficha.get('alta_desde') or str(calendario.PRIMER_DIA),
        f'volvió {ficha["nombre"]}', ficha['area'], origen='personal')
    return {'ok': True, 'mensaje': (
        f'{ficha["nombre"]} vuelve a estar disponible para la programación.' + aviso)}


@router.delete('/{empleado_id}/definitivo')
def borrar_definitivo(empleado_id: int):
    resultado = cambios_de_turno.borrar_definitivo(empleado_id)
    historial.anotar('borrar_personal', 'empleado',
                     {'id': empleado_id, 'nombre': resultado['nombre']})
    return {'ok': True, 'mensaje': resultado['mensaje']}


# --------------------------------------------------------- cambios de turno

@router.post('/{empleado_id}/cambio-turno')
def programar_cambio(empleado_id: int, cambio: CambioDeTurno):
    resultado = cambios_de_turno.programar(empleado_id, cambio.model_dump())
    historial.anotar('cambio_turno', 'empleado', {
        'id': empleado_id, 'afectados': resultado['afectados'],
        'vigente_desde': resultado['vigente_desde'], 'motivo': cambio.motivo})
    aviso = periodos.avisar_desde(
        resultado['vigente_desde'], 'se programó un cambio de turno', resultado['area'],
        origen='personal')
    return {'ok': True, **resultado, 'mensaje': resultado['mensaje'] + aviso}


@router.put('/{empleado_id}/cambio-turno/{vigente_desde}')
def corregir_cambio(empleado_id: int, vigente_desde: str, cambio: CambioDeTurno):
    resultado = cambios_de_turno.corregir(empleado_id, vigente_desde, cambio.model_dump())
    historial.anotar('corregir_cambio_turno', 'empleado', {
        'id': empleado_id, 'antes': vigente_desde,
        'vigente_desde': resultado['vigente_desde']})
    aviso = periodos.avisar_desde(
        min(vigente_desde, resultado['vigente_desde']),
        'se corrigió un cambio de turno', resultado['area'], origen='personal')
    return {'ok': True, **resultado, 'mensaje': resultado['mensaje'] + aviso}


@router.delete('/{empleado_id}/cambio-turno/{vigente_desde}')
def deshacer_cambio(empleado_id: int, vigente_desde: str, incluir_pareja: bool = True):
    resultado = cambios_de_turno.deshacer(empleado_id, vigente_desde, incluir_pareja)
    historial.anotar('deshacer_cambio_turno', 'empleado', {
        'id': empleado_id, 'vigente_desde': vigente_desde,
        'afectados': resultado['deshechos']})
    aviso = periodos.avisar_desde(vigente_desde, 'se deshizo un cambio de turno',
                                  resultado['area'], origen='personal')
    return {'ok': True, **resultado, 'mensaje': resultado['mensaje'] + aviso}
