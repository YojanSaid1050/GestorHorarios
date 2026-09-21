# -*- coding: utf-8 -*-
"""Pulsar todos los botones, rellenar todos los formularios, probar las combinaciones.

Las otras suites recorren **caminos**: entrar, generar, aprobar una solicitud,
exportar. Un camino comprueba que lo previsto funciona, y por eso no encuentra
nunca lo que está fuera de lo previsto: el botón que nadie pulsa, la casilla que
nadie rellena, la mezcla de opciones que nadie combina. Los dos botones de
reinicio de Configuración vivieron rotos varias versiones exactamente por eso: no
había ningún camino que pasara por ellos.

Esto va al revés. Primero se hace el **censo** de todo lo que se puede pulsar
—leyéndolo de la pantalla, no de una lista escrita a mano— y al final se dice
cuántos de esos controles se tocaron y **cuáles no, con el motivo escrito**. Un
control sin motivo es un fallo de esta suite, no una decisión.

Tres cosas se miran de cada formulario, y las tres importan por separado:

* **que rechace lo incompleto.** Un formulario que se traga un envío vacío deja
  una fila a medias en la base de datos que revienta tres pantallas más allá,
  donde ya no se entiende de dónde vino;
* **que el rechazo se lea.** El mensaje tiene que estar en castellano y decir qué
  falta. `[object Object]`, `undefined` o un `Internal Server Error` en la cara
  del usuario cuentan como fallo aunque técnicamente el envío se haya rechazado;
* **que lo válido llegue de verdad.** Se vuelve a preguntar al servidor. El aviso
  verde de «guardado» no prueba nada: ya hubo una versión que lo enseñaba
  mientras el `POST` contestaba 422.
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from qa.navegador import abrir as abrir_navegador  # noqa: E402
from qa.servidor import CLAVE_ADMIN_QA, Servidor, entrar_como_admin  # noqa: E402
from qa.uso import App  # noqa: E402

CLAVE_ADMIN = CLAVE_ADMIN_QA

PESTANAS = ['personal', 'solicitudes', 'requerimientos', 'horario', 'modificar',
            'validacion', 'historial', 'configuracion']

#: Lo que **no** se pulsa en el barrido, con el motivo de cada uno escrito.
#:
#: Esta lista es la parte honrada del censo. Sin ella bastaría con no tocar un
#: botón para que no diera problemas, que es justo la costumbre que dejó los dos
#: reinicios sin probar. Aquí cada exclusión tiene que justificarse.
#:
#: Un motivo tiene que decir la verdad, y esto ya se saltó una vez: los reinicios
#: y la copia de seguridad estuvieron puestos aquí diciendo «se prueban aparte en
#: qa/pantalla.py», y no era cierto —no los tocaba nadie—. Una exclusión con un
#: motivo falso es peor que no excluir nada, porque además cierra la pregunta.
#: Ahora se prueban de verdad, al final del recorrido y en este orden, en
#: `lo_que_destruye()`: cada uno deja la instalación en un estado que el
#: siguiente aprovecha, y el último la deja de fábrica.
FUERA_DEL_BARRIDO = {
    'reiniciar-fabrica': 'destruye la instalación; se prueba al final, en lo_que_destruye()',
    'reiniciar-programacion': 'borra los horarios; se prueba al final, en lo_que_destruye()',
    'limpiar-historial': 'borra la auditoría; se prueba al final, en lo_que_destruye()',
    'cerrar-sesion': 'termina la sesión y deja el resto del barrido sin poder entrar',
    'crear-backup': 'escribe un archivo; se prueba al final, en lo_que_destruye()',
    'descargar-actualizacion': 'bajaría una versión de GitHub desde la máquina de pruebas',
    'instalar-actualizacion': 'reiniciaría el programa a media prueba',
    'abrir-archivo-exportado': 'abre el visor del sistema, que aquí no existe',
    'abrir-exportaciones': 'abre el explorador de archivos del sistema',
    'toggle-login-password': 'solo se ve en la pantalla de acceso, ya cerrada',
}

#: Combinaciones de opciones de cada formulario. Cada línea es una pregunta:
#: «con este tipo elegido, ¿el formulario se reconfigura sin romperse y pide lo
#: que corresponde?». Son las mezclas que un camino lineal no llega a tocar.
COMBINACIONES = {
    'form-solicitud': ('solicitud-tipo',
                       ['descanso', 'vacaciones', 'incapacidad', 'permiso',
                        'capacitacion', 'cambio_pareja', 'cambio_persona',
                        'turno_dia', 'turno_semanas']),
    'form-requerimiento': ('requerimiento-tipo',
                           ['actividad', 'asignacion_administrativa',
                            'descanso_extra', 'excepcion_turno']),
}

RUIDO = ('[object Object]', 'undefined', 'null', 'NaN', 'Internal Server Error',
         'Traceback', 'Unprocessable', 'Bad Request', 'field required')

#: La etiqueta de cada campo obligatorio que **no se ve** en pantalla. Es la
#: lista con la que se comprueba que la queja del formulario no nombre ninguno.
ETIQUETAS_INVISIBLES_JS = """
(id) => {
  const form = document.getElementById(id);
  if (!form) return [];
  const nombre = e => {
    const l = e.closest('label');
    if (!l) return e.id || '';
    return (l.childNodes[0]?.textContent || l.innerText || '').trim().split('\\n')[0];
  };
  return [...form.querySelectorAll('[required]')]
    .filter(e => e.offsetParent === null)
    .filter(e => !e.classList.contains('native-date-hidden'))
    .map(nombre)
    .filter(x => x.length > 2);
}
"""


class Acta:
    """Lo comprobado y con qué resultado."""

    def __init__(self):
        self.pasos: list[tuple[bool, str, str]] = []

    def comprobar(self, ok: bool, que: str, detalle: str = '') -> bool:
        self.pasos.append((bool(ok), que, detalle))
        print(f"  [{'ok  ' if ok else 'FALLA'}] {que}"
              + (f'\n          {detalle}' if not ok and detalle else ''), flush=True)
        return bool(ok)

    def resumen(self) -> int:
        malos = [(q, d) for ok, q, d in self.pasos if not ok]
        print('\n' + '=' * 72)
        print(f'{len(self.pasos) - len(malos)}/{len(self.pasos)} comprobaciones correctas')
        for que, detalle in malos:
            print(f'  FALLA · {que}' + (f'\n          {detalle}' if detalle else ''))
        return 1 if malos else 0


# --------------------------------------------------------------- el censo

CENSO_JS = """
() => {
  const visible = e => {
    const r = e.getBoundingClientRect();
    const s = getComputedStyle(e);
    return s.display !== 'none' && s.visibility !== 'hidden' && (r.width + r.height) > 0;
  };
  const clave = e => {
    if (e.id) return '#' + e.id;
    for (const a of ['data-tab', 'data-ir', 'data-ir-config', 'data-vista-personal',
                     'data-periodo-paso', 'data-days', 'data-req-days',
                     'data-modo-opcion', 'data-toggle-password']) {
      if (e.hasAttribute(a)) return `[${a}="${e.getAttribute(a)}"]`;
    }
    if (e.type === 'submit') {
      const f = e.closest('form');
      return f && f.id ? `#${f.id} button[type="submit"]` : 'button[type="submit"]';
    }
    return null;
  };
  const salida = [];
  for (const e of document.querySelectorAll('button')) {
    if (!visible(e)) continue;
    if (e.closest('.modal-backdrop')) continue;
    const k = clave(e);
    if (!k) continue;
    const t = (e.innerText || e.getAttribute('aria-label') || '').trim();
    salida.push({clave: k, texto: t.slice(0, 40), apagado: !!e.disabled});
  }
  return salida;
}
"""


def censo(app, acta) -> dict:
    """Todo lo que se puede pulsar, leído de la pantalla pestaña por pestaña.

    Escrito a mano se descuelga: basta con que alguien renombre un botón para que
    la lista mienta y la suite crea haber probado algo que ya no existe. Leído de
    la pantalla, un botón nuevo aparece solo en el censo y, si nadie lo pulsa,
    sale en el recuento del final.
    """
    todos: dict[str, dict] = {}
    abierta: dict[str, bool] = {}
    for pestana in PESTANAS:
        app.ir(pestana)
        app.pag.wait_for_timeout(500)
        abierta[pestana] = bool(app.pag.evaluate(
            "(id)=>{const s=document.getElementById(id);"
            " return !!s && s.classList.contains('active')"
            "        && (s.innerText || '').trim().length > 60;}", pestana))
        for control in app.pag.evaluate(CENSO_JS):
            control['pestana'] = pestana
            todos.setdefault(control['clave'], control)
        sin_basura_en_la_pantalla(app, acta, pestana)
    # Lo que se comprueba es que **ninguna pestaña se quedó sin abrir**, no que
    # todas aporten botones: «Validación» no tiene ni uno, porque es una pantalla
    # de lectura, y contar controles la habría denunciado siempre.
    #
    # Importa porque una pestaña que no abre aporta cero controles al censo, y lo
    # que no entra en el censo no se echa de menos: el recuento del final seguiría
    # diciendo que se pulsó todo.
    cerradas = [p for p in PESTANAS if not abierta[p]]
    acta.comprobar(not cerradas,
                   f'las {len(PESTANAS)} pestañas abren y tienen contenido '
                   f'({len(todos)} controles en total)',
                   'no llegaron a abrirse: ' + ', '.join(cerradas))
    return todos


# ------------------------------------------------------------- el barrido

def sigue_viva(app) -> bool:
    """¿La aplicación responde todavía?

    Un error de JavaScript no apaga la pantalla: la deja quieta. La pestaña que
    se estaba viendo sigue ahí, con sus datos, y parece que todo va bien hasta
    que alguien intenta ir a otro sitio. Por eso el barrido no se conforma con
    mirar la consola: después de cada pestaña intenta **navegar**, que es lo
    primero que deja de funcionar.
    """
    app.cerrar_modales()
    app.ir('horario')
    en_horario = app.pag.evaluate(
        "()=>document.getElementById('horario')?.classList.contains('active')")
    app.ir('personal')
    return bool(en_horario) and bool(app.pag.evaluate(
        "()=>document.getElementById('personal')?.classList.contains('active')"))


#: Palabras que nunca tiene que leer una persona en la pantalla. Todas son la
#: misma cosa: un dato que no llegó y que se pintó tal cual en vez de fallar.
BASURA_EN_PANTALLA = ('undefined', 'null', 'NaN', '[object Object]')

MIRAR_SI_HAY_BASURA = r"""
(palabras) => {
  const malo = [];
  const visible = el => {
    const c = getComputedStyle(el);
    return c.display !== 'none' && c.visibility !== 'hidden';
  };
  const andador = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = andador.nextNode(); n; n = andador.nextNode()) {
    const texto = (n.textContent || '').trim();
    if (!texto) continue;
    const padre = n.parentElement;
    if (!padre || padre.closest('script, style') || !visible(padre)) continue;
    for (const palabra of palabras) {
      // Con límites de palabra: «anulado» lleva «null» dentro y no es basura.
      const suelta = palabra.replace(/[[\]]/g, '\\$&');
      const limite = '[^A-Za-zÀ-ÿ0-9_]';
      if (new RegExp(`(^|${limite})${suelta}($|${limite})`, 'i').test(texto)) {
        malo.push({palabra, texto: texto.slice(0, 90),
                   donde: padre.tagName.toLowerCase() + (padre.id ? '#' + padre.id : '')});
      }
    }
  }
  return malo;
}
"""


def sin_basura_en_la_pantalla(app, acta, pestana: str) -> None:
    """Que no se lea «null» ni «undefined» en ninguna parte.

    Es la mitad automática de la lección que costó cuarenta agujeros: la pantalla
    lee lo que manda el servidor con `|| 0` y `?? '—'`, así que un campo que falta
    no rompe nada. Cuando **no** hay red de esas, lo que falta se pinta tal cual:
    la columna «Base» del horario enseñó la palabra «null» a la oficina, y la
    línea de la copia de seguridad decía «Última copia: undefined».

    Lo que se lee en la pantalla se puede mirar sin saber de dónde viene, y eso
    es justo lo que hace esto. La otra mitad —los ceros de mentira, que no se
    distinguen mirando— la comprueba `pruebas/test_contrato.py`.
    """
    encontrado = app.pag.evaluate(MIRAR_SI_HAY_BASURA, list(BASURA_EN_PANTALLA))
    acta.comprobar(
        not encontrado,
        f'en «{pestana}» no se lee ningún «null» ni «undefined»',
        ' | '.join(f'{x["palabra"]} en {x["donde"]}: «{x["texto"]}»'
                   for x in encontrado[:4]))


def barrido(app, acta, controles: dict) -> set:
    """Pulsar, uno a uno, todo lo que no esté excluido con motivo."""
    pulsados = set()
    for pestana in PESTANAS:
        del_tab = [c for c in controles.values() if c['pestana'] == pestana]
        app.ir(pestana)
        errores_antes = len(app.errores_js)
        rotos = []
        for control in del_tab:
            nombre = control['clave'].lstrip('#')
            if nombre in FUERA_DEL_BARRIDO:
                continue
            app.cerrar_modales()
            try:
                app.pulsar(control['clave'], 0, 450)
            except Exception as fallo:                                  # noqa: BLE001
                rotos.append(f"{control['clave']} → {fallo}")
                continue
            pulsados.add(control['clave'])
            app.cerrar_modales()
            nuevos = app.errores_js[errores_antes:]
            if nuevos:
                rotos.append(f"{control['clave']} ({control['texto']}) → {nuevos[-1][:120]}")
                errores_antes = len(app.errores_js)
        acta.comprobar(not rotos,
                       f'se pulsan los {len(del_tab)} controles de «{pestana}» sin romper nada',
                       ' | '.join(rotos[:4]))
        acta.comprobar(sigue_viva(app),
                       f'después de «{pestana}» la aplicación sigue navegando')
    return pulsados


# --------------------------------------------------------- los formularios

def _mensaje_de_error(app, form_id: str) -> str:
    """Lo que la persona lee cuando el formulario no la deja seguir."""
    caja = {'form-empleado': '#empleado-form-alerta',
            'form-solicitud': '#solicitud-form-alerta',
            'form-requerimiento': '#requerimiento-form-alerta',
            'form-cambio-turno': '#cambio-turno-alerta'}.get(form_id, '')
    return (app.alerta(caja) if caja else '') or app.toast()


def _enviar(app, form_id: str, espera: int = 1800) -> None:
    """Enviar el formulario después de **borrar el aviso anterior**.

    Sin borrarlo, un envío que no dice nada se confunde con el aviso que dejó el
    paso de antes: la comprobación lee un texto, lo da por bueno y el formulario
    mudo pasa desapercibido. Es la misma trampa que «salió el aviso verde, luego
    se guardó», solo que un paso más atrás.
    """
    app.cerrar_modales()
    app.pag.evaluate(
        "()=>{const t=document.getElementById('toast');"
        " if(t){t.textContent=''; t.classList.add('hidden');}}")
    app.pulsar(f'#{form_id} button[type="submit"]', 0, espera)


def _limpiar(app, form_id: str) -> None:
    """Dejar el formulario como recién abierto, sin usar su botón «Cancelar».

    Se limpia campo a campo a propósito: «Cancelar» hace además otras cosas
    —cerrar fichas, volver a cargar listas— y usarlo aquí mezclaría lo que se
    quiere medir con lo que ese botón arrastra.
    """
    app.pag.evaluate(
        "(id)=>{const f=document.getElementById(id); if(!f) return;"
        " f.querySelectorAll('input,textarea').forEach(e=>{"
        "   if(e.type==='checkbox'||e.type==='radio') return;"
        "   e.value=''; e.dispatchEvent(new Event('input',{bubbles:true}));"
        "   e.dispatchEvent(new Event('change',{bubbles:true}));});"
        # Las listas también, o el formulario «vacío» no lo está: el barrido
        # deja elegida una persona en los desplegables, y el envío se guardaba
        # de verdad mientras la comprobación creía estar midiendo un rechazo.
        " f.querySelectorAll('select').forEach(e=>{"
        "   e.selectedIndex = 0;"
        "   e.dispatchEvent(new Event('change',{bubbles:true}));});}", form_id)
    app.pag.wait_for_timeout(400)


def formularios_vacios(app, acta, servidor, cabeceras) -> None:
    """Enviar cada formulario en blanco: tiene que negarse y explicarse."""
    donde = {'form-empleado': 'personal', 'form-solicitud': 'solicitudes',
             'form-requerimiento': 'requerimientos',
             'form-cambio-turno': 'requerimientos'}
    for form_id, pestana in donde.items():
        antes = _cuantos(servidor, cabeceras)
        app.ir(pestana)
        _limpiar(app, form_id)
        _enviar(app, form_id)

        mensaje = _mensaje_de_error(app, form_id)
        acta.comprobar(bool(mensaje.strip()),
                       f'«{form_id}» en blanco no se guarda en silencio: avisa',
                       'ni alerta ni aviso: el envío se fue sin decir nada')
        acta.comprobar(not any(r in mensaje for r in RUIDO),
                       f'«{form_id}» explica lo que falta con palabras',
                       f'el usuario lee: {mensaje[:160]!r}')
        acta.comprobar(_cuantos(servidor, cabeceras) == antes,
                       f'«{form_id}» en blanco no deja nada a medias en la base',
                       f'antes {antes} · ahora {_cuantos(servidor, cabeceras)}')
        _limpiar(app, form_id)


def _cuantos(servidor, cabeceras) -> tuple:
    """Cuántas filas hay de cada cosa. Es la única prueba de que algo se guardó.

    Un `-1` significa que la dirección no contestó lo que se esperaba, y no se
    disimula: comparar `-1` con `-1` daría igual siempre y todas las
    comprobaciones de «esto no se guardó» pasarían sin haber mirado nada. Por eso
    `contar_bien` lo denuncia antes de empezar.
    """
    def largo(camino):
        estado, datos = servidor.pedir(camino, cabeceras=cabeceras)
        if estado != 200 or not isinstance(datos, list):
            return -1
        return len(datos)
    return (largo('/api/empleados'), largo('/api/solicitudes'),
            largo('/api/requerimientos'))


def contar_bien(acta, servidor, cabeceras) -> None:
    """Que las tres cuentas se puedan leer. Si no, lo que viene detrás no vale."""
    cuenta = _cuantos(servidor, cabeceras)
    acta.comprobar(all(x >= 0 for x in cuenta),
                   'las listas de personal, solicitudes y asignaciones se leen',
                   f'alguna dirección no contestó una lista: {cuenta}')


def empleado_valido(app, acta, servidor, cabeceras) -> None:
    """Alta completa de una persona, comprobada contra el servidor."""
    antes, _, _ = _cuantos(servidor, cabeceras)
    app.ir('personal')
    _limpiar(app, 'form-empleado')
    app.escribir('#empleado-nombre', 'Prueba De Interfaz')
    app.escribir('#empleado-area', 'comunicaciones')
    app.escribir('#empleado-tipo', 'rotativo')
    # Se da de alta como **persona nueva**, que es el camino real de un ingreso:
    # marcada así, la aplicación le calcula sola el turno inicial y el lunes de
    # referencia, y no los pide. Sin marcarla, el formulario los exige —con
    # razón— y el alta se quedaba a medias.
    app.pag.eval_on_selector(
        '#empleado-nuevo',
        "c=>{c.checked=true; c.dispatchEvent(new Event('change',{bubbles:true}));}")
    app.pag.wait_for_timeout(400)
    app.elegir_fecha('empleado-vigente-desde', '2026-10-05')
    _enviar(app, 'form-empleado', 2500)

    estado, empleados = servidor.pedir('/api/empleados', cabeceras=cabeceras)
    creado = next((e for e in empleados if e['nombre'] == 'Prueba De Interfaz'), None)
    queja = _mensaje_de_error(app, 'form-empleado')[:140]
    acta.comprobar(creado is not None,
                   'el alta de personal llega de verdad a la base de datos',
                   f'{antes} antes, {len(empleados)} ahora: {queja}')
    if creado:
        acta.comprobar(creado['area'] == 'comunicaciones' and creado['tipo_turno'] == 'rotativo',
                       'y llega con el área y el tipo que se eligieron',
                       str({k: creado.get(k) for k in ('area', 'tipo_turno')}))
        acta.comprobar(str(creado.get('vigente_desde')) == '2026-10-05',
                       'y con la fecha que se marcó en el calendario propio',
                       str(creado.get('vigente_desde')))
        servidor.pedir(f"/api/empleados/{creado['id']}/definitivo",
                       'DELETE', None, cabeceras)


def solicitud_valida(app, acta, servidor, cabeceras) -> None:
    """Una solicitud correcta, y su rechazo cuando las fechas van al revés."""
    app.ir('solicitudes')
    _limpiar(app, 'form-solicitud')
    estado, empleados = servidor.pedir('/api/empleados', cabeceras=cabeceras)
    alguien = str(empleados[0]['id'])

    # 1) Fechas invertidas: es el error que más veces se comete a mano.
    app.escribir('#solicitud-empleado', alguien)
    app.escribir('#solicitud-tipo', 'vacaciones')
    app.escribir('#solicitud-modo-fechas-general', 'rango')
    app.elegir_fecha('solicitud-inicio', '2026-10-20')
    app.elegir_fecha('solicitud-fin', '2026-10-13')
    antes = _cuantos(servidor, cabeceras)[1]
    _enviar(app, 'form-solicitud')
    mensaje = _mensaje_de_error(app, 'form-solicitud')
    acta.comprobar(_cuantos(servidor, cabeceras)[1] == antes,
                   'unas vacaciones que terminan antes de empezar no se guardan',
                   f'se guardó igual · {mensaje[:140]}')
    acta.comprobar(bool(mensaje.strip()) and not any(r in mensaje for r in RUIDO),
                   'y se dice por qué, con palabras',
                   f'el usuario lee: {mensaje[:160]!r}')

    # 2) Las mismas fechas en su orden: ahora sí.
    _limpiar(app, 'form-solicitud')
    app.escribir('#solicitud-empleado', alguien)
    app.escribir('#solicitud-tipo', 'vacaciones')
    app.escribir('#solicitud-modo-fechas-general', 'rango')
    app.elegir_fecha('solicitud-inicio', '2026-10-13')
    app.elegir_fecha('solicitud-fin', '2026-10-20')
    _enviar(app, 'form-solicitud', 2500)
    estado, solicitudes = servidor.pedir('/api/solicitudes', cabeceras=cabeceras)
    guardada = next((s for s in solicitudes
                     if s.get('fecha_inicio') == '2026-10-13'
                     and s.get('fecha_fin') == '2026-10-20'), None)
    acta.comprobar(guardada is not None,
                   'las mismas fechas en su orden sí se guardan',
                   _mensaje_de_error(app, 'form-solicitud')[:160])
    if guardada:
        acta.comprobar(guardada.get('estado') == 'pendiente',
                       'y nacen pendientes, sin tocar todavía ningún turno',
                       str(guardada.get('estado')))
        servidor.pedir(f"/api/solicitudes/{guardada['id']}", 'DELETE', None, cabeceras)


def combinaciones(app, acta) -> None:
    """Recorrer cada opción de los selectores que cambian el formulario entero.

    Un formulario que se reconfigura solo es donde se esconden los fallos que
    ningún camino encuentra: el campo que queda pedido pero invisible —y entonces
    el envío se rechaza sin que se vea por qué—, o el que queda visible cuando ya
    no tiene sentido. Se recorren **todas** las opciones, no una de muestra.
    """
    donde = {'form-solicitud': 'solicitudes', 'form-requerimiento': 'requerimientos'}
    for form_id, (selector, opciones) in COMBINACIONES.items():
        app.ir(donde[form_id])
        rotas, fantasmas, mudas = [], [], []
        for opcion in opciones:
            errores_antes = len(app.errores_js)
            _limpiar(app, form_id)
            app.escribir(f'#{selector}', opcion)
            app.pag.wait_for_timeout(450)
            if app.errores_js[errores_antes:]:
                rotas.append(f'{opcion} → {app.errores_js[-1][:100]}')
                continue

            # Se envía vacío a propósito y se lee la queja. Lo que se comprueba
            # no es qué campos lleva el formulario por dentro —eso sería copiar
            # su implementación y darle la razón siempre—, sino la única
            # propiedad que le importa a quien lo usa: **que no reclame nada que
            # no esté en pantalla**. Un formulario que pide «Turno fijo» con el
            # turno fijo escondido no se puede completar por mucho que se
            # intente, y era exactamente lo que había que descartar en cada una
            # de estas combinaciones.
            _enviar(app, form_id, 1200)
            queja = _mensaje_de_error(app, form_id)
            if not queja.strip():
                mudas.append(opcion)
                continue
            invisibles = app.pag.evaluate(ETIQUETAS_INVISIBLES_JS, form_id)
            nombrados = [x for x in invisibles if x and x.lower() in queja.lower()]
            if nombrados:
                fantasmas.append(f'{opcion}: pide «{", ".join(nombrados)}», que no se ve')
        acta.comprobar(not mudas,
                       f'«{form_id}» vacío siempre dice algo, sea cual sea el tipo',
                       'se envió sin decir nada con: ' + ', '.join(mudas))
        acta.comprobar(not rotas,
                       f'«{form_id}» aguanta las {len(opciones)} opciones de {selector}',
                       ' | '.join(rotas[:3]))
        acta.comprobar(not fantasmas,
                       f'«{form_id}» no deja campos obligatorios escondidos',
                       ' | '.join(fantasmas[:3]))


def cambio_de_tipo_de_turno(app, acta, servidor, cabeceras) -> None:
    """El formulario pequeño que nadie recorre: cambiar de fijo a rotativo."""
    app.ir('requerimientos')
    estado, empleados = servidor.pedir('/api/empleados', cabeceras=cabeceras)
    rotativo = next((e for e in empleados if e.get('tipo_turno') == 'rotativo'), None)
    if not rotativo:
        acta.comprobar(False, 'hay alguien de turno rotativo con quien probar el cambio')
        return
    _limpiar(app, 'form-cambio-turno')
    app.escribir('#cambio-turno-empleado', str(rotativo['id']))
    app.escribir('#cambio-turno-tipo', 'fijo')
    app.pag.wait_for_timeout(400)
    app.escribir('#cambio-turno-fijo', 'AM')
    app.elegir_fecha('cambio-turno-fecha', '2026-11-09')
    app.escribir('#cambio-turno-motivo', 'prueba de interfaz')
    _enviar(app, 'form-cambio-turno', 2500)

    estado, lista = servidor.pedir('/api/empleados/cambios-turno', cabeceras=cabeceras)
    programado = None
    if estado == 200:
        programado = next((c for c in lista.get('cambios', [])
                           if c.get('empleado_id') == rotativo['id']), None)
    acta.comprobar(programado is not None,
                   'el cambio de tipo de turno se programa desde su formulario',
                   f'{estado} · {_mensaje_de_error(app, "form-cambio-turno")[:140]}')
    if programado:
        acta.comprobar(str(programado.get('vigente_desde')) == '2026-11-09',
                       'y empieza el lunes que se eligió, no antes',
                       str(programado.get('vigente_desde')))
        servidor.pedir(f"/api/empleados/{rotativo['id']}/cambio-turno/"
                       f"{programado['vigente_desde']}", 'DELETE', None, cabeceras)


def crear_cuenta(app, acta, servidor, cabeceras) -> None:
    """El formulario de Configuración que no vive dentro de ningún `<form>`."""
    app.ir('configuracion')
    app.pulsar('[data-ir-config="cfg-usuarios"]', 0, 700)
    app.escribir('#nuevo-usuario-nombre', 'Cuenta De Prueba')
    app.escribir('#nuevo-usuario-login', 'prueba_interfaz')
    app.escribir('#nuevo-usuario-clave', 'Prueba2026*')
    app.pulsar('#crear-usuario-horarios', 0, 2200)
    app.aceptar()
    app.pag.wait_for_timeout(1500)

    estado, cuentas = servidor.pedir('/api/auth/usuarios', cabeceras=cabeceras)
    lista = cuentas if isinstance(cuentas, list) else (cuentas or {}).get('usuarios', [])
    creada = next((c for c in lista if c.get('usuario') == 'prueba_interfaz'), None)
    acta.comprobar(creada is not None,
                   'se crea una cuenta nueva desde Configuración',
                   f'{estado} · {app.toast()[:140]}')
    if creada:
        # No hay forma de borrar una cuenta, y es a propósito: quien firmó algo
        # tiene que seguir apareciendo en el historial. Se desactiva, que es lo
        # que hace la aplicación cuando alguien deja la oficina.
        apagada, _ = servidor.pedir(f"/api/auth/usuarios/{creada['id']}/estado",
                                    'PUT', {'activo': False}, cabeceras)
        acta.comprobar(apagada == 200,
                       'y se puede desactivar después, sin borrarla del historial',
                       f'la baja contestó {apagada}')


def cuenta_incompleta(app, acta) -> None:
    """Media cuenta no se crea, y se dice cuál es la mitad que falta."""
    app.ir('configuracion')
    app.pulsar('[data-ir-config="cfg-usuarios"]', 0, 700)
    for campo in ('#nuevo-usuario-nombre', '#nuevo-usuario-login',
                  '#nuevo-usuario-clave'):
        app.escribir(campo, '')
    app.escribir('#nuevo-usuario-nombre', 'Sin Contraseña')
    app.pulsar('#crear-usuario-horarios', 0, 1600)
    aviso = app.toast()
    acta.comprobar('Falta' in aviso or 'falta' in aviso,
                   'una cuenta sin contraseña no se crea y se dice qué falta',
                   f'el usuario lee: {aviso[:160]!r}')
    acta.comprobar(not any(r in aviso for r in RUIDO),
                   'y el aviso está escrito para una persona',
                   f'el usuario lee: {aviso[:160]!r}')


class Sesion:
    """Las cabeceras de la sesión, que aquí caducan a mitad de camino.

    Restaurar una copia y restablecer de fábrica reemplazan la tabla de sesiones,
    así que el token con el que se venía preguntando deja de valer. Eso está
    bien —es lo que tiene que pasar—, pero convierte cualquier consulta
    posterior en un 401 cuyo cuerpo es `{'detail': '...'}`.

    Y ahí estaba la trampa: `len({'detail': ...})` es **1**, así que «cuánta
    gente hay» contestaba «una persona» y el informe denunciaba que restablecer
    de fábrica destruía la aplicación. No era verdad; era esta suite midiendo un
    mensaje de error como si fuera una lista. Un comprobador que inventa fallos
    es peor que no tenerlo, porque se aprende a no hacerle caso.

    Por eso aquí no se lee nunca una lista sin mirar antes el estado, y por eso
    se vuelve a entrar en cuanto el token deja de valer.
    """

    def __init__(self, servidor, acta):
        self.servidor = servidor
        self.acta = acta
        self.cabeceras = entrar_como_admin(servidor)

    def renovar(self) -> None:
        self.cabeceras = entrar_como_admin(self.servidor)

    def lista(self, camino: str, clave: str = '') -> list:
        """Una lista de verdad, o un fallo con su nombre. Nunca un número falso."""
        estado, datos = self.servidor.pedir(camino, cabeceras=self.cabeceras)
        if estado == 401:
            self.renovar()
            estado, datos = self.servidor.pedir(camino, cabeceras=self.cabeceras)
        if estado != 200:
            self.acta.comprobar(False, f'se puede leer {camino}', f'contestó {estado}')
            return []
        if clave:
            datos = datos.get(clave, [])
        return datos if isinstance(datos, list) else []

    def dato(self, camino: str, clave: str):
        estado, datos = self.servidor.pedir(camino, cabeceras=self.cabeceras)
        if estado == 401:
            self.renovar()
            estado, datos = self.servidor.pedir(camino, cabeceras=self.cabeceras)
        if estado != 200:
            self.acta.comprobar(False, f'se puede leer {camino}', f'contestó {estado}')
            return None
        return datos.get(clave)


def lo_que_destruye(app, acta, servidor, cabeceras) -> set:
    """Los cinco botones que borran cosas, en el único orden en que se pueden probar.

    Estos cinco no caben en el barrido: el primero que se pulse deja al resto del
    recorrido sin nada sobre lo que trabajar. Pero quedarse ahí es exactamente lo
    que los dejó rotos varias versiones seguidas, y son los que más falta hacen
    cuando algo va mal —quien pulsa «restaurar una copia» está teniendo un día
    malo y no puede permitirse un segundo problema—.

    Así que van al final, encadenados a propósito: cada uno deja la instalación
    en el estado que el siguiente necesita, y el último la deja de fábrica.

    De cada uno se comprueba lo mismo: **qué se llevó por delante y qué no**. Un
    reinicio que borra de más es tan fallo como uno que no borra nada, y el de
    más no se nota hasta que alguien busca lo que ya no está.
    """
    pulsados = set()
    sesion = Sesion(servidor, acta)
    app.ir('configuracion')

    # 1 · La copia de seguridad. Se hace con datos dentro, que es lo que le da
    #     sentido: una copia de una base vacía no prueba que se copie nada.
    app.pulsar('[data-ir-config="cfg-copias"]', 0, 700)
    antes = set(sesion.lista('/api/operacion/copias', 'copias'))
    hecha = app.confirmar_y_clave('#crear-backup', CLAVE_ADMIN, 3000)
    pulsados.add('#crear-backup')
    nuevas = set(sesion.lista('/api/operacion/copias', 'copias')) - antes
    acta.comprobar(hecha and len(nuevas) == 1,
                   'se crea una copia de seguridad desde su botón',
                   f'copias nuevas: {sorted(nuevas)} · {app.toast()[:120]}')

    # 2 · Restaurarla. Es el botón más peligroso de la aplicación —reemplaza la
    #     base entera— y era el único que no probaba nadie. Se retira a alguien,
    #     se restaura, y tiene que volver en activo: sin quitar nada antes,
    #     restaurar una copia idéntica al presente no demuestra nada.
    personal_antes = sesion.lista('/api/empleados')
    if nuevas and personal_antes:
        victima = personal_antes[0]
        estado, _ = servidor.pedir(f"/api/empleados/{victima['id']}/retirar", 'POST',
                                   {'fecha_retiro': '2026-10-05'}, sesion.cabeceras)
        acta.comprobar(estado == 200
                       and any(e['id'] == victima['id'] and e.get('retirado_desde') == '2026-10-05'
                               for e in sesion.lista('/api/empleados?incluir_inactivos=true')),
                       'se registra una retirada futura para tener algo que recuperar',
                       f'la retirada contestó {estado}')

        copia = servidor.carpeta / 'copias' / next(iter(nuevas))
        restaurada = _restaurar(app, copia)
        pulsados.add('#archivo-backup')
        sesion.renovar()
        vuelto = sesion.lista('/api/empleados')
        acta.comprobar(restaurada and len(vuelto) == len(personal_antes),
                       'restaurar la copia deja el personal como estaba',
                       f'{len(personal_antes)} antes · {len(vuelto)} después · '
                       f'{app.toast()[:140]}')
        acta.comprobar(any(e['id'] == victima['id']
                           and e.get('retirado_desde') == victima.get('retirado_desde')
                           for e in vuelto),
                       'y deshace la retirada: vuelve en activo, no como un hueco',
                       victima['nombre'])

    # 3 · El historial. No toca ningún dato: solo se pierde el rastro. El botón
    #     vive en la pestaña «Historial», no en Configuración.
    app.ir('historial')
    personal_antes = len(sesion.lista('/api/empleados'))
    acta.comprobar(app.confirmar_y_clave('#limpiar-historial', CLAVE_ADMIN, 2500),
                   'se borra el historial desde su botón, con la contraseña')
    pulsados.add('#limpiar-historial')
    acta.comprobar(not sesion.lista('/api/operacion/auditoria', 'historial'),
                   'y queda vacío de verdad, no solo en pantalla',
                   f'quedan {len(sesion.lista("/api/operacion/auditoria", "historial"))}')
    acta.comprobar(len(sesion.lista('/api/empleados')) == personal_antes,
                   'sin llevarse por delante ningún dato de verdad')

    # 4 · Reiniciar la programación. Aquí se comprueba sobre todo lo que **no**
    #     se borra: los dos meses base y el personal. Un reinicio que se llevara
    #     agosto y septiembre dejaría el programa sin el punto de partida del que
    #     cuelga todo lo demás.
    app.ir('configuracion')
    app.pulsar('[data-ir-config="cfg-reiniciar"]', 0, 700)
    app.escribir('#reiniciar-periodo', '2026-10')
    app.pag.wait_for_timeout(500)
    reiniciada = app.confirmar_y_clave('#reiniciar-programacion', CLAVE_ADMIN, 4000)
    pulsados.add('#reiniciar-programacion')
    sesion.renovar()
    acta.comprobar(reiniciada and not sesion.dato('/api/horarios/opciones/2026/10',
                                                 'cantidad'),
                   'reiniciar la programación se lleva las opciones de octubre',
                   f'quedan {sesion.dato("/api/horarios/opciones/2026/10", "cantidad")}'
                   f' · {app.toast()[:120]}')
    acta.comprobar(bool(sesion.dato('/api/horarios/opciones/2026/8', 'cantidad')),
                   'y **no** se lleva agosto, que es un mes base',
                   'agosto se quedó sin programación: el reinicio pisó la base')
    acta.comprobar(len(sesion.lista('/api/empleados')) == personal_antes,
                   'ni el personal, que el reinicio no tiene por qué tocar')

    # 5 · De fábrica. Lo último, porque después de esto no queda nada que probar.
    app.ir('configuracion')
    app.pulsar('[data-ir-config="cfg-fabrica"]', 0, 700)
    de_fabrica = app.confirmar_y_clave('#reiniciar-fabrica', CLAVE_ADMIN, 5000)
    pulsados.add('#reiniciar-fabrica')
    sesion.renovar()
    gente = sesion.lista('/api/empleados')
    acta.comprobar(de_fabrica and len(gente) == personal_antes,
                   'restablecer de fábrica deja el personal como venía de origen',
                   f'{len(gente)} personas · {app.toast()[:140]}')
    acta.comprobar(bool(sesion.dato('/api/horarios/opciones/2026/8', 'cantidad')),
                   'y vuelve a sembrar los dos meses base',
                   'después de reiniciar de fábrica no hay mes base')
    acta.comprobar(sesion.lista('/api/solicitudes') == [],
                   'y no queda ninguna novedad de la instalación anterior')
    return pulsados


def _restaurar(app, copia: Path) -> bool:
    """Subir el archivo de la copia por el mismo camino que usa una persona.

    El campo es un `input type=file` escondido detrás de un botón, así que se le
    entrega el archivo directamente. Lo que viene después —la confirmación y la
    contraseña— sí se pasa como se pasa de verdad, porque es justo donde esto
    podría estar roto sin que nadie lo supiera.
    """
    if not copia.is_file():
        return False
    antes = app.campos_de_clave()
    app.pag.set_input_files('#archivo-backup', str(copia))
    app.pag.wait_for_timeout(1200)
    app.aceptar()
    for _ in range(20):
        if app.campos_de_clave() > antes:
            break
        app.pag.wait_for_timeout(400)
    else:
        return False
    if not app.clave(CLAVE_ADMIN):
        return False
    # La pantalla se recarga sola un segundo después de restaurar, así que hay
    # que esperar a que vuelva a estar en pie antes de seguir preguntándole nada.
    app.pag.wait_for_timeout(5000)
    try:
        app.pag.wait_for_selector('button[data-tab="personal"]', timeout=15000)
    except Exception:                                              # noqa: BLE001
        return False
    # Y hay que volver a entrar. Restaurar reemplaza la base **entera**, y las
    # sesiones abiertas viven dentro de ella: al recargarse, la pantalla se
    # encuentra con que su sesión ya no consta y pide entrar otra vez. Es el
    # comportamiento correcto —no queda otro— y por eso está escrito aquí en vez
    # de tratarse como un fallo, pero significa que el recorrido se queda fuera
    # justo en mitad de los cinco botones que más importan.
    if app.pag.evaluate("()=>document.body.classList.contains('auth-locked')"):
        return app.entrar(app.pag.url.split('#')[0])
    return True


def recuento(acta, controles: dict, pulsados: set) -> None:
    """Lo que da sentido a todo lo anterior: qué quedó sin tocar y por qué."""
    sin_tocar = []
    for clave, control in controles.items():
        if clave in pulsados:
            continue
        nombre = clave.lstrip('#')
        if nombre in FUERA_DEL_BARRIDO:
            continue
        sin_tocar.append(f"{clave} ({control['texto']} · {control['pestana']})")
    # Se cuentan solo los que están en el censo: `lo_que_destruye` toca además
    # cosas que no son botones —el campo de archivo de la copia—, y sumarlas daba
    # un «pulsados 60 de 57» que no quiere decir nada.
    del_censo = len([c for c in pulsados if c in controles])
    print(f'\n  censo: {len(controles)} controles · pulsados {del_censo} · '
          f'excluidos con motivo {len(FUERA_DEL_BARRIDO)}')
    acta.comprobar(not sin_tocar,
                   'ningún control se queda sin pulsar y sin motivo escrito',
                   ' | '.join(sin_tocar[:6]))


def main() -> int:
    from playwright.sync_api import sync_playwright

    acta = Acta()
    with Servidor('/tmp/qa_interfaz') as servidor:
        cabeceras = entrar_como_admin(servidor)
        with sync_playwright() as guion:
            navegador = abrir_navegador(guion)
            pagina = navegador.new_page(viewport={'width': 1500, 'height': 1000})
            app = App(pagina)
            App.acta = acta
            try:
                acta.comprobar(app.entrar(servidor.base), 'se entra como administrador')
                # Con un horario delante, media pantalla tiene botones que sin él
                # ni siquiera existen: el censo se hace **después** de generarlo.
                # El selector de mes vive en «Horario», así que hay que estar ahí
                # para poder tocarlo.
                app.ir('horario')
                app.periodo(2026, 10)
                acta.comprobar(app.generar(), 'se genera octubre para tener qué pulsar')

                contar_bien(acta, servidor, cabeceras)
                controles = censo(app, acta)
                pulsados = barrido(app, acta, controles)
                formularios_vacios(app, acta, servidor, cabeceras)
                empleado_valido(app, acta, servidor, cabeceras)
                solicitud_valida(app, acta, servidor, cabeceras)
                combinaciones(app, acta)
                cambio_de_tipo_de_turno(app, acta, servidor, cabeceras)
                cuenta_incompleta(app, acta)
                crear_cuenta(app, acta, servidor, cabeceras)
                # Lo último de todo: después de esto no queda instalación.
                pulsados |= lo_que_destruye(app, acta, servidor, cabeceras)
                recuento(acta, controles, pulsados)

                acta.comprobar(not app.errores_js,
                               'ni un solo error de JavaScript en todo el recorrido',
                               ' | '.join(x[:110] for x in app.errores_js[:4]))
            except Exception:                                           # noqa: BLE001
                acta.comprobar(False, 'el recorrido termina', traceback.format_exc()[-900:])
            finally:
                App.acta = None
                navegador.close()
    return acta.resumen()


if __name__ == '__main__':
    raise SystemExit(main())
