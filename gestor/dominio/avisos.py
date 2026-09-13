# -*- coding: utf-8 -*-
"""Qué avisos piden una decisión y cuáles solo informan.

La pantalla de Validación llegó a enseñar nueve avisos cuando solo dos pedían
que alguien hiciera algo. Los otros siete eran de dos clases muy distintas: los
que describen algo que ya se autorizó a propósito, y los que cuentan un ajuste
que la aplicación hizo sola para poder cerrar el mes. Mezclados con los que sí
importan, el resultado era que nadie los leía.

La clasificación vivía escrita en el JavaScript de la pantalla y buscaba trozos
de frase dentro de mensajes que escribe el backend. Eso se rompe en silencio:
basta con reescribir una frase para que un aviso cambie de grupo sin que nadie
se entere y aparezca pidiendo una decisión que ya estaba tomada. Aquí está en un
solo sitio, del lado que escribe los mensajes, y con pruebas que lo sostienen.
"""
from __future__ import annotations

# Ya estaba autorizado: alguien tomó la decisión antes y el aviso solo deja
# constancia. No hay nada que hacer con él.
YA_AUTORIZADO = (
    'la coincidencia está permitida',
    'autorizada por',
    'excepción de turno autorizada',
    'viene del mes anterior ya publicado',
    'asignación directa o cambio manual autorizado',
)

# Lo resolvió la aplicación sola: cuenta un ajuste que se hizo para poder cerrar
# el mes. Conviene poder leerlo, pero no espera respuesta.
RESUELTO_SOLO = (
    'se trasladó',
    'se traslado',
    'se colocó en el domingo',
    'se coloco en el domingo',
    'puente administrativo',
    'para recuperar el balance',
    'para cortar una racha',
    'cerró el periodo anterior descansando',
    'cerro el periodo anterior descansando',
    'se reubicó',
    'se reubico',
    'no se añadió',
    'no se anadio',
)

# Frases que niegan a las de arriba. Van antes que nada porque el texto de la
# negación CONTIENE el de la autorización: «sin una excepción de turno
# autorizada» lleva dentro «excepción de turno autorizada», y buscando trozos
# de frase a secas ese aviso acababa en «ya estaba autorizado» significando
# justamente lo contrario. Es el fallo que arrastraba la versión del JavaScript.
NIEGA_LA_AUTORIZACION = (
    'sin una excepción de turno autorizada',
    'sin una excepcion de turno autorizada',
    'sin excepción de turno autorizada',
    'sin excepcion de turno autorizada',
    'no está autorizada',
    'no esta autorizada',
    'sin autorizar',
)

DECISION = 'decision'
AUTORIZADO = 'autorizado'
RESUELTO = 'resuelto'
# Un mes que ya se trabajó no admite decisiones: lo que diga su validación es
# la historia de lo que pasó, medida con las reglas de hoy. Agosto de 2026 sale
# con treinta y tres avisos, y ninguno espera nada de nadie.
HISTORICO = 'historico'

ETIQUETAS = {
    DECISION: 'Esto pide que decidas algo',
    AUTORIZADO: 'Ya estaba autorizado',
    RESUELTO: 'Lo resolvió la aplicación sola',
    HISTORICO: 'Así fue un mes que ya se trabajó',
}


def clasificar(mensaje: str) -> str:
    """A cuál de los tres grupos pertenece este aviso.

    Se compara en minúsculas porque los mensajes empiezan por el nombre de una
    persona y la misma frase aparece a veces a mitad de oración.
    """
    texto = str(mensaje or '').lower()
    if any(marca in texto for marca in NIEGA_LA_AUTORIZACION):
        return DECISION
    if any(marca in texto for marca in YA_AUTORIZADO):
        return AUTORIZADO
    if any(marca in texto for marca in RESUELTO_SOLO):
        return RESUELTO
    return DECISION


def repartir(mensajes) -> dict[str, list[str]]:
    """Los mismos avisos, agrupados por lo que esperan de quien los lee."""
    grupos: dict[str, list[str]] = {DECISION: [], AUTORIZADO: [], RESUELTO: [], HISTORICO: []}
    for mensaje in mensajes or []:
        grupos[clasificar(mensaje)].append(mensaje)
    return grupos


def cuantos_piden_decision(mensajes) -> int:
    """El número que debe llevar el distintivo de la pestaña de Validación.

    Contarlos todos era lo que hacía que la pestaña marcara nueve cuando solo
    dos pedían algo.
    """
    return sum(1 for m in (mensajes or []) if clasificar(m) == DECISION)


def legible(mensaje: str, nivel: str) -> dict:
    """Cómo se le enseña a una persona un aviso de validación.

    Le pone nombre a la categoría —«Fatiga laboral · PM → AM», «Descanso
    semanal»— y le añade la sugerencia de qué hacer, que es lo que convierte un
    mensaje técnico en algo accionable. Vivía dentro del motor de generación,
    entre seis mil líneas que sí tocan el horario; aquí no toca nada: entra un
    texto y sale cómo contarlo.
    """
    texto = mensaje.lower()
    categoria = 'Regla general'
    sugerencia = (
        'Revisa la fecha y la persona indicadas, corrige la configuración o la solicitud desde la aplicación y vuelve a generar. '
        'Si el ajuste solo puede hacerse fuera del sistema, exporta primero una alternativa válida y modifica una copia del Excel manualmente; '
        'ese cambio manual no quedará guardado como continuidad para el mes siguiente.'
    )

    if 'máximo 7 días consecutivos' in texto or '8 jornadas seguidas' in texto:
        categoria = 'Descanso después de máximo 7 días'
        sugerencia = 'Debe existir al menos un día no laborado después de un máximo de siete jornadas consecutivas. Puedes reorganizar descansos o, si es una decisión excepcional, autorizar únicamente el cambio manual con una justificación.'
    elif 'fatiga laboral:' in texto or 'pm→am' in texto or 'pm->am' in texto:
        categoria = 'Fatiga laboral · PM → AM'
        sugerencia = (
            'El motor nunca crea un descanso extra para resolver fatiga. Si ya existe un descanso semanal automático en esa semana, puede trasladarlo al cambio de turno. '
            'Si no existe un descanso trasladable o moverlo rompería la cobertura, usa un día administrativo del área como puente (PM → ADM → AM). '
            'Si la fecha está protegida por una solicitud, asignación o modificación explícita, corrige esa decisión o utiliza el forzado manual con motivo administrativo.'
        )
    elif (
        'cambio operativo normal debe hacerse al iniciar una semana nueva' in texto
        or 'tiene am y pm dentro de la semana' in texto
    ):
        categoria = 'Cambio semanal de turno'
        sugerencia = (
            'AM y PM deben mantenerse consistentes durante la semana y el cambio normal se realiza al iniciar una semana nueva. '
            'La fatiga PM→AM se controla por separado: puede usar un D ya existente/trasladable, VAC/INC/PER o, como último recurso, un puente ADM antes del AM. Nunca crea un descanso extra para cumplirla. Si se trata de un caso autorizado que necesita días concretos en otro turno, '
            'usa Asignaciones y ajustes → Excepción de turno.'
        )
    elif 'gestión social tiene' in texto or 'gestión social queda' in texto:
        categoria = 'Cobertura · Gestión Social'
        sugerencia = (
            'Gestión Social debe conservar mínimo 1 persona AM y 1 PM. En Solicitudes, mueve el descanso o la novedad de una persona, '
            'elige un reemplazo compatible o cambia un turno puntual sin dejar AM o PM sin ninguna persona. Si no existe personal suficiente '
            'para lograr 1 AM y 1 PM, la solicitud no puede aprobarse dentro de las reglas actuales.'
        )
    elif 'comunicaciones queda sin pm' in texto:
        categoria = 'Cobertura · Comunicaciones'
        sugerencia = (
            'Reubica el descanso o la novedad de una persona de Comunicaciones, o selecciona un reemplazo de la misma área. '
            'Puede haber 0 AM, pero siempre debe quedar al menos 1 PM.'
        )
    elif 'compensatorio' in texto or 'festivo' in texto:
        categoria = 'Festivo · descanso adicional'
        sugerencia = (
            'Cada festivo es independiente del descanso semanal y del domingo. Si la persona trabaja el festivo, debe recibir otro D compensatorio. '
            'Revisa cobertura o usa Solicitudes → Añadir descanso extra si necesitas fijar manualmente un día adicional compatible.'
        )
    elif 'domingo' in texto:
        categoria = 'Balance · Domingos'
        sugerencia = (
            'Del total de domingos del mes se trabaja la mitad hacia abajo y se descansa el resto: con cuatro, dos y dos; '
            'con cinco, dos trabajados y tres descansados. Se equilibran por separado de los festivos. '
            'Si el conflicto persiste, suele venir del máximo de jornadas seguidas: el descanso semanal solo puede avanzar '
            '«máximo − 6» días por semana, así que un tope bajo impide llegar a los domingos. Puedes subirlo en '
            'Configuración → Máximo de jornadas seguidas, mover un descanso desde Solicitudes, o autorizar la excepción a mano.'
        )
    elif 'pareja' in texto or 'pc' in texto:
        categoria = 'Pareja de PC'
        sugerencia = (
            'En Personal, verifica que la pareja de PC esté correctamente configurada. Para un cambio puntual, usa un turno que no haga coincidir '
            'a la pareja en AM o PM el mismo día, o selecciona otra persona compatible.'
        )
    elif 'reemplazo' in texto or 'cubrir' in texto:
        categoria = 'Reemplazo'
        sugerencia = (
            'Selecciona en la solicitud otra persona de la misma área que esté disponible ese día. El reemplazo cambia temporalmente de turno; '
            'no puede hacer doble turno ni dejar su turno original por debajo de la cobertura mínima.'
        )
    elif 'intercambio' in texto:
        categoria = 'Intercambio de turno'
        sugerencia = (
            'Selecciona dos personas operativas de la misma área con turnos AM/PM distintos y sin otra novedad bloqueada ese día. '
            'El intercambio también debe respetar las parejas de PC.'
        )
    elif 'cambiar de' in texto or 'cambio puntual' in texto or 'turno solicitado' in texto or 'cambio de turno' in texto:
        categoria = 'Cambio puntual de turno'
        sugerencia = (
            'Edita o elimina la solicitud de cambio de turno. El nuevo AM/PM solo puede aplicarse si Gestión Social conserva al menos 1 AM y 1 PM, '
            'Comunicaciones conserva al menos 1 PM y no se crea conflicto de PC.'
        )
    elif 'descanso fijo' in texto:
        categoria = 'Descanso fijo'
        sugerencia = (
            'Ese día está configurado como descanso fijo en Personal. En una modificación manual puntual, la app intentará mover ese descanso a otro día compatible de la misma semana. '
            'Si el cambio debe ser permanente, actualiza el descanso fijo desde Personal.'
        )
    elif 'descanso semanal ordinario' in texto or 'semana del' in texto:
        categoria = 'Descanso semanal'
        sugerencia = (
            'Debe existir un descanso semanal ordinario además de cualquier descanso por festivo, compensatorio o descanso extra. '
            'Usa Solicitudes → Mover descanso semanal para fijarlo en otra fecha compatible.'
        )
    elif 'no tiene día no laborado' in texto or 'semana del' in texto:
        categoria = 'Descanso semanal'
        sugerencia = (
            'Usa Solicitudes → Mover descanso y selecciona esa semana completa de lunes a domingo. Debe quedar al menos un día no laborado, '
            'incluyendo los días de la semana que pertenezcan al mes anterior.'
        )

    return {
        'nivel': nivel,
        'categoria': categoria,
        'mensaje': mensaje,
        'sugerencia': sugerencia,
        # Qué espera este aviso de quien lo lee: una decisión, o solo que se
        # sepa. Se calcula aquí, del lado que escribe los mensajes, porque
        # antes vivía en el JavaScript buscando trozos de frase: bastaba
        # reescribir una para que un aviso ya resuelto volviera a pedir una
        # decisión sin que nadie se enterara.
        'atencion': clasificar(mensaje),
        # Compatibilidad con el frontend de versiones anteriores.
        'accion': sugerencia,
    }
