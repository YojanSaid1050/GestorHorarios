// El mes que se está programando
// ---------------------------------------------------------------------------
// Parte de la pantalla del Gestor de Horarios. Los archivos de esta carpeta se
// cargan en orden y comparten el mismo ámbito, así que juntos son exactamente
// el app.js de antes. Ver frontend/js/LEEME.md.

'use strict';

// ---------------------------------------------------------------------------
// El mes que se está programando
// ---------------------------------------------------------------------------
// La aplicación se usa mes a mes. Antes las solicitudes y las asignaciones no
// lo sabían: se guardaban todas juntas y a los pocos meses la lista era un
// montón donde no se distinguía qué se había puesto para qué mes. Ahora cada
// pantalla trabaja sobre el mes elegido arriba, y ese mes son las semanas
// completas del horario —septiembre de 2026 va del 31 de agosto al 4 de
// octubre—, es decir, exactamente los días que se ven en el horario.
//
// Nada se borra ni se esconde: lo de los demás meses sigue ahí y se ve
// cambiando de mes, o de golpe con «Ver todos los meses».

const MESES_NOMBRE = ['enero','febrero','marzo','abril','mayo','junio','julio',
                      'agosto','septiembre','octubre','noviembre','diciembre'];

function periodoActual() {
    const v = document.getElementById('periodo')?.value || '';
    return /^\d{4}-\d{2}$/.test(v) ? v : '';
}

function lunesDe(f) {
    const d = new Date(f + 'T00:00:00');
    d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
    return d;
}

// Mismo cálculo que `rango_periodo` en el servidor: semanas completas de lunes
// a domingo, salvo agosto de 2026, que es la base histórica y ocupa su mes.
function rangoDelPeriodo(valor = periodoActual()) {
    if (!valor) return null;
    const [anio, mes] = valor.split('-').map(Number);
    const primero = `${valor}-01`;
    const ultimoDia = new Date(anio, mes, 0).getDate();
    const ultimo = `${valor}-${String(ultimoDia).padStart(2, '0')}`;
    if (valor === PERIODO_MINIMO) return {desde: primero, hasta: ultimo, valor};
    const iniciar = lunesDe(primero);
    const minimo = new Date(PERIODO_MINIMO + '-01T00:00:00');
    const desde = iniciar < minimo ? minimo : iniciar;
    const terminar = lunesDe(ultimo);
    terminar.setDate(terminar.getDate() + 6);
    return {desde: ymd(desde), hasta: ymd(terminar), valor};
}

function nombreDelPeriodo(valor = periodoActual()) {
    if (!valor) return '';
    const [anio, mes] = valor.split('-').map(Number);
    return `${MESES_NOMBRE[mes - 1]} de ${anio}`;
}

function actualizarEjemploDeHoras() {
    // El texto que explica las dos columnas de horas llevaba el ejemplo escrito
    // a mano —«en septiembre de 2026, del 31 de agosto al 4 de octubre»— y se
    // enseñaba siempre. Con octubre abierto, el ejemplo contradecía la tabla
    // que tenía justo encima. Ahora habla del mes que se está mirando.
    const rango = rangoDelPeriodo();
    const nombre = nombreDelPeriodo();
    const donde = $('ejemplo-rango-periodo');
    if (donde) {
        donde.textContent = rango
            ? ` —en ${nombre}, del ${fechaCorta(rango.desde)} al ${fechaCorta(rango.hasta)}—`
            : '';
    }
    const mes = $('ejemplo-mes-periodo');
    if (mes) mes.textContent = nombre ? nombre.split(' de ')[0].toLowerCase() : 'ese mes';
}

function nombrePeriodoRespuesta(datos = {}) {
    const valor = datos?.anio && datos?.mes
        ? `${datos.anio}-${String(datos.mes).padStart(2, '0')}`
        : periodoActual();
    const nombre = nombreDelPeriodo(valor) || 'este período';
    return nombre.charAt(0).toUpperCase() + nombre.slice(1);
}

// ¿Alguno de estos días cae dentro del mes que se está viendo?
function tocaElPeriodo(fechas, valor = periodoActual()) {
    const r = rangoDelPeriodo(valor);
    if (!r) return true;
    return (fechas || []).filter(Boolean).some(f => {
        const d = String(f).slice(0, 10);
        return d >= r.desde && d <= r.hasta;
    });
}

// Ver todos los meses de golpe es la excepción, no lo normal: sirve para
// repasar el histórico sin tener que ir mes a mes. No se guarda entre
// sesiones, para que la aplicación siempre abra en su modo de trabajo.
let verTodosLosMeses = false;

function fechaCorta(f) {
    const d = new Date(f + 'T00:00:00');
    const mes = ['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'][d.getMonth()];
    return `${d.getDate()} ${mes}`;
}

function renderBarrasPeriodo() {
    const r = rangoDelPeriodo();
    document.querySelectorAll('[data-periodo-bar]').forEach(barra => {
        const nombre = barra.querySelector('[data-periodo-nombre]');
        const rango = barra.querySelector('[data-periodo-rango]');
        const todo = barra.querySelector('[data-ver-todo]');
        barra.classList.toggle('viendo-todo', verTodosLosMeses);
        if (nombre) {
            const texto = verTodosLosMeses ? 'Todos los meses' : nombreDelPeriodo();
            nombre.textContent = texto.charAt(0).toUpperCase() + texto.slice(1);
        }
        if (rango) {
            rango.textContent = verTodosLosMeses
                ? 'Estás viendo el histórico completo; para registrar algo, vuelve a un mes.'
                : (r ? `Del ${fechaCorta(r.desde)} al ${fechaCorta(r.hasta)} · semanas completas del horario` : '');
        }
        if (todo) todo.checked = verTodosLosMeses;
        barra.querySelectorAll('[data-periodo-paso]').forEach(b => { b.disabled = verTodosLosMeses; });
    });
    actualizarEjemploDeHoras();
}

function conectarBarrasPeriodo() {
    document.querySelectorAll('[data-periodo-bar]').forEach(barra => {
        barra.querySelectorAll('[data-periodo-paso]').forEach(boton => {
            boton.onclick = () => {
                const actual = periodoActual();
                if (!actual) return;
                const [anio, mes] = actual.split('-').map(Number);
                const d = new Date(anio, mes - 1 + Number(boton.dataset.periodoPaso), 1);
                const destino = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
                if (destino < PERIODO_MINIMO) {
                    toast('La programación comienza en agosto de 2026.', 'info', 'No hay mes anterior');
                    return;
                }
                $('periodo').value = destino;
                $('periodo').dispatchEvent(new Event('change'));
            };
        });
        const todo = barra.querySelector('[data-ver-todo]');
        if (todo) todo.onchange = () => {
            verTodosLosMeses = todo.checked;
            renderBarrasPeriodo();
            renderSolicitudes();
            renderRequerimientos();
            actualizarLimitesDeFecha();
        };
    });
}

// Los campos de fecha de las dos pantallas no dejan salirse del mes: es la
// misma regla que aplica el servidor, dicha antes de escribir.
function actualizarLimitesDeFecha() {
    const r = rangoDelPeriodo();
    document.querySelectorAll('[data-limite-periodo]').forEach(campo => {
        if (!r || verTodosLosMeses) { campo.removeAttribute('min'); campo.removeAttribute('max'); return; }
        campo.min = r.desde;
        campo.max = r.hasta;
    });
    // Dentro del formulario había un segundo —y un tercer— selector de mes,
    // para elegir de qué mes eran las semanas. Ahora eso ya está decidido por
    // la pantalla: siguen al mes de arriba y no se tocan por separado, que era
    // la forma más fácil de registrar en septiembre una semana de agosto.
    const actual = periodoActual();
    if (actual) {
        ['solicitud-semana-periodo', 'solicitud-turno-periodo', 'solicitud-rango-semana-periodo']
            .forEach(id => {
                const campo = $(id);
                if (!campo) return;
                if (campo.value !== actual) campo.value = actual;
                campo.readOnly = true;
                campo.tabIndex = -1;
                campo.classList.add('campo-fijado');
                const ayuda = 'Es el mes que estás programando. Para cambiarlo, usa las flechas de arriba.';
                campo.title = ayuda;
                // El campo de mes se dibuja como dos desplegables propios: se
                // apagan también, o el mes seguiría siendo editable por detrás.
                campo.nextElementSibling?.querySelectorAll?.('select').forEach(sel => {
                    sel.disabled = true;
                    sel.title = ayuda;
                });
            });
        if (typeof actualizarSemanasSolicitud === 'function') actualizarSemanasSolicitud();
        if (typeof actualizarSemanasCambioTemporal === 'function') actualizarSemanasCambioTemporal();
    }
    sincronizarSelectoresFecha();
}

async function api(url, opt = {}) {
    const response = await fetch(url, {
        ...opt,
        headers: {
            ...(opt.body && !(opt.body instanceof FormData) ? {'Content-Type': 'application/json'} : {}),
            ...(sessionToken ? {'X-Session-Token': sessionToken} : {}),
            // El mes que se está programando viaja en todas las llamadas: es
            // lo que permite al servidor rechazar una novedad que pertenece a
            // otro mes en vez de dejarla caer en el montón común.
            ...(periodoActual() ? {'X-Periodo': periodoActual()} : {}),
            ...(opt.headers || {}),
        },
    });

    // El cuerpo de una Response solo puede consumirse una vez. Leemos texto
    // una única vez y, si corresponde, lo convertimos a JSON. Esto evita el
    // error "body stream already read" cuando el backend devuelve un 4xx/5xx.
    const contentType = response.headers.get('content-type') || '';
    const raw = await response.text();
    let data = null;

    if (raw) {
        if (contentType.includes('json')) {
            try {
                data = JSON.parse(raw);
            } catch {
                data = raw;
            }
        } else {
            data = raw;
        }
    }

    if (!response.ok) {
        const message = typeof data === 'string'
            ? data
            : typeof data?.detail === 'string'
                ? data.detail
                : Array.isArray(data?.detail)
                    ? data.detail.map(x => x.msg || JSON.stringify(x)).join(' · ')
                    : (data?.detail?.mensaje || data?.mensaje || (data ? JSON.stringify(data) : `Error HTTP ${response.status}`));
        const esReautenticacion = !!(opt.headers?.['X-Admin-Password'] || opt.headers?.['X-User-Password']);
        if (response.status === 401 && !url.includes('/api/auth/login') && !esReautenticacion) bloquearSesion(message);
        // Algunos rechazos traen datos, no solo un texto: qué meses se verían
        // afectados, qué hay que confirmar. Se conservan para que quien llama
        // pueda preguntar en condiciones en vez de mostrar un aviso a secas.
        const error = new Error(message);
        error.status = response.status;
        error.detalle = (data && typeof data === 'object') ? (data.detail ?? data) : null;
        throw error;
    }

    return data;
}

function iconoToast(tipo) {
    const icons = {
        success: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>',
        warning: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 9v4m0 4h.01M10.3 3.7 2.6 17a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 3.7a2 2 0 0 0-3.4 0Z"/></svg>',
        error: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 9-6 6m0-6 6 6M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"/></svg>',
        info: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 16v-4m0-4h.01M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"/></svg>',
    };
    return icons[tipo] || icons.info;
}

function toast(mensaje, tipo = 'info', titulo = '', duracion = 5200) {
    const t = $('toast');
    const defaultTitle = {
        success: 'Completado',
        warning: 'Revisar',
        error: 'Error',
        info: 'Información',
    }[tipo] || 'Información';

    t.className = `toast show ${tipo}`;
    t.innerHTML = `
        <div class="toast-icon">${iconoToast(tipo)}</div>
        <div class="toast-content">
            <strong>${esc(titulo || defaultTitle)}</strong>
            <span>${esc(mensaje)}</span>
        </div>
        <button class="toast-close" type="button" aria-label="Cerrar">×</button>
    `;
    t.querySelector('.toast-close').onclick = () => cerrarToast();
    clearTimeout(toast.timer);
    toast.timer = setTimeout(cerrarToast, Math.max(2000, Number(duracion) || 5200));
}

function cerrarToast() {
    const t = $('toast');
    t.classList.remove('show');
}

// Ningún error de interfaz debe volver a fallar silenciosamente.
window.addEventListener('error', event => {
    const mensaje = event?.error?.message || event?.message || 'Error inesperado de interfaz.';
    toast(mensaje, 'error', 'Error de interfaz');
});

window.addEventListener('unhandledrejection', event => {
    const razon = event?.reason;
    const mensaje = razon?.message || String(razon || 'Error inesperado de interfaz.');
    toast(mensaje, 'error', 'Error de interfaz');
});

function area(a) {
    return {
        gestion_social: 'Gestión Social',
        atencion_ciudadano: 'Atención al Ciudadano',
        comunicaciones: 'Comunicaciones',
    }[a] || a;
}

function tipo(t) {
    return {fijo: 'Fijo', rotativo: 'Rotativo', administrativo: 'Administrativo'}[t] || t;
}

function nombreSolicitud(t) {
    return {
        descanso: 'Mover descanso semanal',
        descanso_extra: 'Día de descanso',
        excepcion_turno: 'Excepción de turno AM/PM',
        vacaciones: 'Vacaciones',
        incapacidad: 'Incapacidad',
        permiso: 'Permiso',
        capacitacion: 'Capacitación',
        cambio_am: 'Cambio con pareja (legado)',
        cambio_pm: 'Cambio con pareja (legado)',
        cambio_pareja: 'Intercambio AM/PM con pareja',
        cambio_persona: 'Intercambio con otra persona',
        turno_dia: 'Cambio de turno',
        turno_semanas: 'Cambio temporal por semanas',
        asignacion_adm_gs: 'ADM-GS',
    }[t] || t;
}

function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
}


function etiquetaCampo(el) {
    const label = el?.closest('label');
    if (!label) return el?.getAttribute('aria-label') || el?.id || 'Campo requerido';
    const clone = label.cloneNode(true);
    clone.querySelectorAll('input,select,textarea,small,.date-select-group,.date-presets').forEach(x => x.remove());
    return (clone.textContent || '').replace(/\s+/g,' ').trim().replace(/[:*]+$/,'') || el?.id || 'Campo requerido';
}

function campoVisibleParaValidar(el) {
    if (!el || el.disabled) return false;
    const contenedor = el.closest('label, .weekday-picker');
    return !(contenedor?.classList.contains('hidden'));
}

function limpiarErroresFormulario(form) {
    form?.querySelectorAll('.field-invalid').forEach(x => x.classList.remove('field-invalid'));
    limpiarAlertaFormulario(form);
}

function alertaFormulario(form) {
    if (!form) return null;
    const mapa = {
        'form-empleado':'empleado-form-alerta',
        'form-solicitud':'solicitud-form-alerta',
        'form-requerimiento':'requerimiento-form-alerta',
    };
    return $(mapa[form.id] || '');
}

function limpiarAlertaFormulario(form) {
    const box = alertaFormulario(form);
    if (!box) return;
    box.classList.add('hidden');
    box.innerHTML = '';
}

function mostrarAlertaFormulario(form, mensaje, titulo = 'Revisa el formulario') {
    const box = alertaFormulario(form);
    if (!box) return;
    box.innerHTML = `<strong>${esc(titulo)}</strong><span>${esc(mensaje)}</span>`;
    box.classList.add('error');
    box.classList.remove('hidden');
}

function mostrarFaltantesFormulario(form, extras = []) {
    if (!form) return false;
    limpiarErroresFormulario(form);
    const faltantes = [];
    const nodos = [];
    form.querySelectorAll('[required]').forEach(el => {
        if (!campoVisibleParaValidar(el)) return;
        const vacio = el.type === 'checkbox' ? !el.checked : !String(el.value || '').trim();
        if (vacio) {
            faltantes.push(etiquetaCampo(el));
            nodos.push(el);
            el.closest('label')?.classList.add('field-invalid');
        }
    });
    for (const extra of extras) {
        if (!extra || extra.ok) continue;
        faltantes.push(extra.nombre);
        const el = extra.id ? $(extra.id) : null;
        if (el) { nodos.push(el); el.closest('label, .weekday-picker')?.classList.add('field-invalid'); }
    }
    const unicos = [...new Set(faltantes.filter(Boolean))];
    if (!unicos.length) return false;
    const detalle = `Falta completar o seleccionar: ${unicos.join(' · ')}`;
    mostrarAlertaFormulario(form, detalle, 'Formulario incompleto');
    toast(detalle, 'warning', 'Formulario incompleto');
    const primero = nodos[0];
    if (primero && !primero.classList.contains('native-date-hidden')) primero.focus?.();
    else primero?.nextElementSibling?.querySelector('select')?.focus?.();
    return true;
}

function irAHistorial(entidad = '') {
    document.querySelector('[data-tab="historial"]')?.click();
    if ($('historial-tipo')) $('historial-tipo').value = entidad;
    renderAuditoria();
}

function periodo() {
    const valor = $('periodo')?.value || '';
    const match = /^(\d{4})-(\d{2})$/.exec(valor);
    if (!match) {
        throw new Error('Selecciona un mes y un año válidos antes de continuar.');
    }
    const anio = Number(match[1]);
    const mes = Number(match[2]);
    if (!Number.isInteger(anio) || !Number.isInteger(mes) || mes < 1 || mes > 12) {
        throw new Error('El periodo seleccionado no es válido.');
    }
    if (`${anio}-${String(mes).padStart(2,'0')}` < PERIODO_MINIMO) {
        throw new Error('La programación comienza en agosto de 2026. Selecciona agosto de 2026 o un mes posterior.');
    }
    return {anio, mes};
}

function esperar(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

let estadoTimer = null;
function setEstado(texto = '', tipo = 'working', ocultarDespues = 0) {
    const box = $('actividad');
    clearTimeout(estadoTimer);
    if (!texto) {
        box.classList.add('hidden');
        return;
    }
    $('estado').textContent = texto;
    box.className = `activity-pill ${tipo}`;
    if (ocultarDespues > 0) {
        estadoTimer = setTimeout(() => box.classList.add('hidden'), ocultarDespues);
    }
}

let resolverConfirmacion = null;
function cerrarConfirmacion(valor) {
    $('modal-confirmar').classList.add('hidden');
    if (resolverConfirmacion) {
        const resolver = resolverConfirmacion;
        resolverConfirmacion = null;
        resolver(valor);
    }
}

function confirmarUI({titulo, mensaje, detalle = '', aceptar = 'Confirmar', cancelar = 'Cancelar', peligro = true}) {
    if (resolverConfirmacion) cerrarConfirmacion(false);
    $('confirmar-titulo').textContent = titulo || 'Confirmar acción';
    $('confirmar-mensaje').textContent = mensaje || '';
    $('confirmar-detalle').textContent = detalle || '';
    $('confirmar-detalle').classList.toggle('hidden', !detalle);
    $('confirmar-aceptar').textContent = aceptar;
    $('confirmar-cancelar').textContent = cancelar;
    $('confirmar-aceptar').classList.toggle('danger-button', !!peligro);
    $('confirmar-icono').classList.toggle('info', !peligro);
    $('modal-confirmar').classList.remove('hidden');
    return new Promise(resolve => { resolverConfirmacion = resolve; });
}

$('confirmar-cancelar').onclick = () => cerrarConfirmacion(false);
$('confirmar-aceptar').onclick = () => cerrarConfirmacion(true);
$('confirmar-cerrar').onclick = () => cerrarConfirmacion(false);
$('modal-confirmar').onclick = ev => {
    if (ev.target === $('modal-confirmar')) cerrarConfirmacion(false);
};

// La tecla Escape cierra la ventana que esté abierta. Sin esto, quien abre una
// ficha por error tiene que buscar el aspa o el botón de cancelar; con el
// teclado es la salida que todo el mundo espera.
function cerrarVentanaAbierta() {
    if (!$('modal-confirmar')?.classList.contains('hidden')) { cerrarConfirmacion(false); return true; }
    if (!$('modal-edicion-formulario')?.classList.contains('hidden')) { cerrarEditorFormulario(); return true; }
    if (!$('modal-retirar-empleado')?.classList.contains('hidden')) {
        $('modal-retirar-empleado').classList.add('hidden'); return true;
    }
    if (!$('modal-exportar')?.classList.contains('hidden')) { cerrarModalExportacion(); return true; }
    if (!$('modal-soluciones')?.classList.contains('hidden')) {
        const cancelar = document.querySelector('#modal-soluciones [data-cerrar], #modal-soluciones .modal-x');
        if (cancelar) { cancelar.click(); } else { $('modal-soluciones').classList.add('hidden'); }
        return true;
    }
    return false;
}

document.addEventListener('keydown', ev => {
    if (ev.key !== 'Escape') return;
    // Los diálogos que se crean al vuelo ya gestionan su propio Escape.
    if (document.querySelector('.modal-backdrop:not([id])')) return;
    if (cerrarVentanaAbierta()) ev.preventDefault();
});

function abrirEditorFormulario(formId, titulo, ayuda='Realiza los cambios y guarda para volver a la lista en la misma posición.') {
    const form=$(formId), modal=$('modal-edicion-formulario'), contenido=$('edicion-formulario-contenido');
    if (!form || !modal || !contenido) return;
    if (editorFormularioEstado) cerrarEditorFormulario(false);
    editorFormularioEstado={form,parent:form.parentNode,next:form.nextSibling,scrollY:window.scrollY};
    $('edicion-formulario-titulo').textContent=titulo || 'Editar';
    $('edicion-formulario-ayuda').textContent=ayuda;
    contenido.appendChild(form);
    modal.classList.remove('hidden');
    setTimeout(()=>form.querySelector('input:not([type="hidden"]),select,textarea')?.focus(),0);
}

function cerrarEditorFormulario(restaurarScroll=true) {
    const modal=$('modal-edicion-formulario');
    if (!editorFormularioEstado) { modal?.classList.add('hidden'); return; }
    const {form,parent,next,scrollY}=editorFormularioEstado;
    if (next && next.parentNode===parent) parent.insertBefore(form,next); else parent.appendChild(form);
    editorFormularioEstado=null;
    modal?.classList.add('hidden');
    if (restaurarScroll) requestAnimationFrame(()=>window.scrollTo({top:scrollY,behavior:'auto'}));
}

$('cerrar-edicion-formulario')?.addEventListener('click',()=>cerrarEditorFormulario());
$('modal-edicion-formulario')?.addEventListener('click',ev=>{ if(ev.target===$('modal-edicion-formulario')) cerrarEditorFormulario(); });

// La barra de arriba —periodo, crear opciones, exportar— es del horario. Se
// veía en las ocho pantallas, así que en Personal o en Solicitudes había tres
// botones que allí no hacen nada, y encima un segundo selector de mes junto al
// de la propia pantalla. Ahora aparece solo donde se usa.
const PESTANAS_CON_BARRA = new Set(['horario', 'modificar', 'validacion']);

function ajustarBarraDeHerramientas(pestana) {
    const barra = document.querySelector('.toolbar');
    if (barra) barra.classList.toggle('hidden', !PESTANAS_CON_BARRA.has(pestana));
}
