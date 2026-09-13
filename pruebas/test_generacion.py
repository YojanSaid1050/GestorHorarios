# -*- coding: utf-8 -*-
"""Generar meses de verdad y comprobarlos con un juez que no es el motor.

El auditor de `pruebas/auditor.py` **no llama a la validación de la
aplicación**. Vuelve a implementar cada norma desde su enunciado, para que un
fallo del motor y un fallo de su propia validación no se tapen el uno al otro.
Si los dos estuvieran mal de la misma manera —que es lo que pasa cuando alguien
«arregla» la validación para que acepte lo que el motor produce— las pruebas
normales seguirían en verde y estas no.

Son lentas porque generan meses completos. Se ejecutan con `--lentas`.
"""
from __future__ import annotations

import collections

import pytest

from pruebas.auditor import AREAS, auditar

pytestmark = pytest.mark.lenta


@pytest.fixture
def instalacion(base):
    """Una instalación recién hecha: personal, reglas y las dos bases."""
    from gestor.servicios import reglas_cobertura, reglas_operacion, siembra
    reglas_cobertura.olvidar_lo_leido()
    reglas_operacion.invalidar_cache()
    resultado = siembra.sembrar()
    assert resultado.completa, f'faltan datos iniciales: {resultado.faltan}'
    return resultado


def _reglas_vigentes():
    from gestor.servicios import reglas_cobertura
    reglas_cobertura.olvidar_lo_leido()
    return {a: reglas_cobertura.regla(a).como_dict() for a in AREAS}


def _generar(mes, anio, **extra):
    """Un mes generado como lo genera la aplicación: enlazado con el anterior.

    Pasar la continuidad no es un detalle. Sin ella el mes sale del vacío: la
    rotación se reinicia, la racha de jornadas seguidas se pierde en la frontera
    y la semana compartida con el mes anterior se vuelve a decidir en vez de
    heredarse, con lo que la oficina acabaría con dos versiones del mismo día.
    """
    from gestor.datos import personal
    from gestor.motor.orquestacion import generar_horario_completo
    from gestor.servicios import continuidad
    contexto = continuidad.todo(mes, anio)
    contexto.update(extra)
    return generar_horario_completo(personal.listar(), [], mes, anio, **contexto)


# --------------------------------------------------------- que salga algo

def test_octubre_de_2026_se_genera_entero(instalacion):
    resultado = _generar(10, 2026)
    horario = resultado['horario']

    assert resultado['valido'], resultado.get('errores')
    assert len(horario) == 17, 'tienen que estar las 17 personas vigentes'
    assert all(len(f['dias']) == 35 for f in horario), (
        'el período de octubre son cinco semanas completas: 35 días')


def test_nadie_se_queda_sin_turno_ningun_dia(instalacion):
    """Una casilla vacía es un día del que nadie sabe qué pasó."""
    horario = _generar(10, 2026)['horario']
    vacias = [(f['nombre'], d['fecha']) for f in horario for d in f['dias']
              if not str(d.get('turno') or '').strip()]
    assert not vacias, f'casillas sin turno: {vacias[:5]}'


def test_solo_se_usan_codigos_que_existen(instalacion):
    from gestor.dominio import codigos
    horario = _generar(10, 2026)['horario']
    usados = {d['turno'] for f in horario for d in f['dias']}
    assert usados <= set(codigos.TODOS), f'códigos inventados: {usados - set(codigos.TODOS)}'


def _sembrados() -> list[dict]:
    """La plantilla tal y como está escrita en los datos iniciales.

    Las dos pruebas de aquí abajo llevaban los nombres escritos a mano. Eso las
    ataba a una plantilla concreta: al cambiar los datos iniciales —y se
    cambiaron enteros el día que el repositorio pasó a ser público— pedían gente
    que ya no existe. Lo que comprueban no es que este Fulanita: es que quien se
    retiró no trabaje y quien entró sí, sea quien sea.
    """
    import csv

    from gestor import rutas
    with rutas.dato_inicial('empleados_iniciales.csv').open(encoding='utf-8') as fila:
        return list(csv.DictReader(fila))


def test_quien_se_retiro_no_aparece_trabajando(instalacion):
    """Alguien se retiró a mediados de agosto: en octubre no puede tener turno."""
    retirados = [f['nombre'] for f in _sembrados() if f.get('retirado_desde')]
    assert retirados, 'los datos iniciales ya no traen a nadie retirado'

    nombres = {f['nombre'] for f in _generar(10, 2026)['horario']}
    for quien in retirados:
        assert quien not in nombres, f'{quien} está retirado y sale trabajando'


def test_quien_entro_en_agosto_ya_esta_en_octubre(instalacion):
    """Quien se incorporó después del día 1 cuenta igual desde su fecha."""
    tardios = [f['nombre'] for f in _sembrados()
               if f['alta_desde'] > '2026-08-01' and not f.get('retirado_desde')]
    assert tardios, 'los datos iniciales ya no traen a nadie que entrara tarde'

    nombres = {f['nombre'] for f in _generar(10, 2026)['horario']}
    for quien in tardios:
        assert quien in nombres, f'falta {quien}, que entró durante agosto de 2026'


# ------------------------------------------ el juez independiente

def test_octubre_cumple_todas_las_normas(instalacion):
    """La comprobación que de verdad importa."""
    horario = _generar(10, 2026)['horario']
    fallos = auditar(horario, _reglas_vigentes())
    propios = [f for f in fallos if 'heredado' not in f[0]]
    assert not propios, ('octubre incumple:\n  '
                         + '\n  '.join(f'{n}: {d}' for n, d in propios[:8]))


def test_el_administrativo_de_atencion_al_ciudadano_no_sostiene_el_area(instalacion):
    """Ningún día puede quedar cubierto solo por ADM-AC.

    Es el fallo que se vio tres veces en la oficina. Se comprueba aquí sobre un
    mes de verdad y no sobre un ejemplo inventado, y se excluyen los días
    heredados del mes anterior, que la oficina ya trabajó así y no se pueden
    cambiar desde este mes.
    """
    horario = _generar(10, 2026)['horario']
    ac = [f for f in horario if f['area'] == 'atencion_ciudadano']
    malos = []
    for fecha in sorted({d['fecha'] for f in ac for d in f['dias']}):
        casillas = [next(d for d in f['dias'] if d['fecha'] == fecha) for f in ac]
        if any(c.get('es_ultimo_viernes_administrativo') for c in casillas):
            continue
        if all(str(c.get('origen') or '').startswith('base_') for c in casillas):
            continue
        if not any(c['turno'] in ('AM', 'PM') for c in casillas):
            malos.append((fecha, [c['turno'] for c in casillas]))
    assert not malos, f'días de AC sin nadie cubriendo: {malos[:5]}'


def test_el_viernes_2_de_octubre_se_informa_como_heredado(instalacion):
    """El día concreto que la versión anterior callaba.

    Viene del horario real de septiembre, que la oficina ya trabajó con tres de
    las cuatro personas de Atención al Ciudadano descansando y la cuarta en
    ADM-AC. No se puede cambiar desde octubre —septiembre está publicado— pero
    tiene que verse.
    """
    horario = _generar(10, 2026)['horario']
    fallos = auditar(horario, _reglas_vigentes())
    del_dia = [f for f in fallos if '2026-10-02' in f[1]]
    assert del_dia, 'el viernes 2 tiene que aparecer en la auditoría'
    assert all('heredado' in n for n, _ in del_dia), (
        'y tiene que constar que viene del mes anterior, no achacarse a octubre')


# ------------------------------------------------- las normas, una a una

def test_nadie_pasa_del_tope_de_jornadas_seguidas(instalacion):
    from gestor.dominio import codigos
    from gestor.servicios import reglas_operacion

    tope = reglas_operacion.maximo_dias('2026-10-01')
    horario = _generar(10, 2026)['horario']
    excedidos = []
    for fila in horario:
        racha = 0
        for dia in fila['dias']:
            if dia['turno'] in codigos.TRABAJADOS:
                racha += 1
                if racha > tope:
                    excedidos.append((fila['nombre'], dia['fecha'], racha))
            else:
                racha = 0
    assert not excedidos, f'rachas por encima de {tope}: {excedidos[:5]}'


def test_cada_persona_descansa_cada_semana(instalacion):
    """Salvo la primera, que se comparte con el mes anterior."""
    from gestor.dominio import codigos
    horario = _generar(10, 2026)['horario']
    semanas = sorted({d['lunes_semana'] for f in horario for d in f['dias']})
    sin_descanso = []
    for fila in horario:
        for lunes in semanas[1:]:
            dias = [d for d in fila['dias'] if d['lunes_semana'] == lunes]
            if not dias or all(d.get('vigente') is False for d in dias):
                continue
            if not any(d['turno'] not in codigos.TRABAJADOS for d in dias):
                sin_descanso.append((fila['nombre'], lunes))
    assert not sin_descanso, f'semanas sin descanso: {sin_descanso[:5]}'


def test_las_parejas_no_coinciden_en_el_mismo_turno(instalacion):
    """El sentido de una pareja de punto de contacto es que quede una de las dos."""
    from gestor.datos import personal
    horario = {f['nombre']: f for f in _generar(10, 2026)['horario']}
    fichas = {p['nombre']: p for p in personal.listar()}
    coincidencias = []
    for nombre, ficha in fichas.items():
        companera = ficha.get('nombre_pareja')
        if not companera or companera not in horario or nombre not in horario:
            continue
        dias_a = {d['fecha']: d['turno'] for d in horario[nombre]['dias']}
        for dia in horario[companera]['dias']:
            turno = dias_a.get(dia['fecha'])
            if turno and turno == dia['turno'] and turno in ('AM', 'PM'):
                coincidencias.append((nombre, companera, dia['fecha'], turno))
    # Se informa cuántas hay: la regla es evitarlo, no prohibirlo a cualquier
    # precio, porque a veces no hay otra forma de cubrir el turno.
    proporcion = len(coincidencias) / max(1, sum(len(f['dias']) for f in horario.values()))
    assert proporcion < 0.05, (
        f'las parejas coinciden demasiado ({len(coincidencias)} veces): {coincidencias[:5]}')


def test_generar_dos_veces_lo_mismo_da_lo_mismo(instalacion):
    """Sin esto, comparar dos propuestas no significa nada.

    El motor explora al azar dentro de un presupuesto, pero con los mismos datos
    y la misma variante tiene que llegar al mismo sitio. Si no, dos generaciones
    seguidas del mismo mes daban horarios distintos y nadie podía saber cuál era
    el bueno.
    """
    def firma(resultado):
        return [[(d['fecha'], d['turno']) for d in f['dias']]
                for f in resultado['horario']]

    assert firma(_generar(10, 2026)) == firma(_generar(10, 2026))


def test_dos_variantes_dan_horarios_distintos(instalacion):
    """Y por eso se pueden comparar cinco propuestas."""
    uno = _generar(10, 2026, variante=0)['horario']
    otro = _generar(10, 2026, variante=3)['horario']
    iguales = sum(1 for a, b in zip(uno, otro, strict=False)
                  for da, db in zip(a['dias'], b['dias'], strict=False)
                  if da['turno'] == db['turno'])
    total = sum(len(f['dias']) for f in uno)
    assert iguales < total, 'las dos variantes salieron idénticas'


# ------------------------------------------------------ los días heredados

def test_los_dias_del_mes_anterior_llegan_bloqueados(instalacion):
    """La primera semana de octubre es también la última de septiembre.

    Septiembre está publicado: esos días se muestran para dar contexto pero no
    se recalculan. Que lleguen marcados es lo que evita que el mes nuevo
    reescriba un horario que la oficina ya está trabajando.
    """
    horario = _generar(10, 2026)['horario']
    primera_semana = [d for f in horario for d in f['dias'] if d['fecha'] < '2026-10-05']
    assert primera_semana, 'octubre empieza el 28 de septiembre'
    heredados = [d for d in primera_semana if d.get('bloqueado') or d.get('heredado')]
    assert heredados, 'los días que vienen de septiembre tienen que llegar marcados'


def test_el_reparto_por_areas_es_el_configurado(instalacion):
    """Comunicaciones trabaja 2 de mañana y 1 de tarde desde el 31 de agosto."""
    horario = _generar(10, 2026)['horario']
    com = [f for f in horario if f['area'] == 'comunicaciones']
    repartos = collections.Counter()
    for fecha in sorted({d['fecha'] for f in com for d in f['dias']}):
        casillas = [next(d for d in f['dias'] if d['fecha'] == fecha) for f in com]
        if any(c.get('es_ultimo_viernes_administrativo') for c in casillas):
            continue
        am = sum(1 for c in casillas if c['turno'] == 'AM')
        pm = sum(1 for c in casillas if c['turno'] == 'PM')
        repartos[(am, pm)] += 1
    assert not [r for r in repartos if r[0] > 2], f'más de 2 en la mañana: {dict(repartos)}'
    assert not [r for r in repartos if r[1] > 1], f'más de 1 en la tarde: {dict(repartos)}'


# ------------------------------------------------------ meses encadenados

def _oficializar(mes, anio, resultado):
    from gestor.datos import horarios
    ids = horarios.guardar_propuestas(anio, mes, f'g-{anio}-{mes:02d}', [resultado])
    return horarios.marcar_oficial(ids[0])


def test_seis_meses_encadenados_cumplen_todas_las_normas(instalacion):
    """La prueba que más ha encontrado, y la que más se parece al uso real.

    La oficina no genera un mes suelto: encadena. Cada mes arranca del oficial
    anterior, y los fallos que importan aparecen en la costura —una racha que
    cruza el cambio de mes, una rotación que se reinicia, una semana compartida
    que se decide dos veces—. Un mes aislado puede salir perfecto y la cadena
    romperse en el tercero.
    """
    reglas = _reglas_vigentes()
    problemas = []
    for anio, mes in ((2026, 10), (2026, 11), (2026, 12), (2027, 1), (2027, 2), (2027, 3)):
        resultado = _generar(mes, anio)
        assert resultado['valido'], (
            f'{anio}-{mes:02d} no salió válido: {resultado.get("errores")[:3]}')
        propios = [f for f in auditar(resultado['horario'], reglas)
                   if 'heredado' not in f[0]]
        problemas.extend(f'{anio}-{mes:02d} · {n}: {d}' for n, d in propios)
        _oficializar(mes, anio, resultado)

    assert not problemas, ('la cadena de meses incumple:\n  '
                           + '\n  '.join(problemas[:10]))


def test_la_semana_compartida_es_la_misma_en_los_dos_meses(instalacion):
    """Un día que está en dos períodos no puede tener dos versiones.

    El 28 de septiembre aparece en la programación de septiembre y en la de
    octubre. Si octubre lo recalculara, la oficina tendría dos papeles que dicen
    cosas distintas del mismo día.
    """
    from gestor.datos import horarios

    septiembre = horarios.oficial(2026, 9)
    assert septiembre, 'la base de septiembre tiene que estar publicada'
    octubre = _generar(10, 2026)['horario']

    por_persona = {f['empleado_id']: f for f in septiembre['horario']}
    discrepancias = []
    for fila in octubre:
        anterior = por_persona.get(fila['empleado_id'])
        if not anterior:
            continue
        antes = {d['fecha']: d['turno'] for d in anterior['dias']}
        for dia in fila['dias']:
            if dia['fecha'] in antes and antes[dia['fecha']] != dia['turno']:
                discrepancias.append(
                    (fila['nombre'], dia['fecha'], antes[dia['fecha']], dia['turno']))
    assert not discrepancias, (
        f'octubre reescribió días que septiembre ya publicó: {discrepancias[:5]}')


def test_sin_el_mes_anterior_se_explica_que_hacer(instalacion):
    """Y se dice qué mes preparar, no un «no se puede» a secas."""
    from gestor.servicios import continuidad

    assert continuidad.falta_el_mes_anterior(10, 2026) == '', (
        'septiembre está publicado: octubre se puede generar'
    )
    aviso = continuidad.falta_el_mes_anterior(11, 2026)
    assert 'octubre de 2026' in aviso, 'el aviso tiene que nombrar el mes que falta'
    assert 'noviembre de 2026' in aviso
