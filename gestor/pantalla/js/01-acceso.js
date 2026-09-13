// Entrar, salir y qué puede hacer cada quien
// ---------------------------------------------------------------------------
// Parte de la pantalla del Gestor de Horarios. Los archivos de esta carpeta se
// cargan en orden y comparten el mismo ámbito, así que juntos son exactamente
// el app.js de antes. Ver frontend/js/LEEME.md.

'use strict';

const $ = id => document.getElementById(id);
let empleados = [];
let empleadosListado = [];
let solicitudes = [];
let requerimientos = [];
let ultimo = null;
let alternativasActuales = [];
let respuestaGeneracion = null;
let sesionUsuario = null;
let sessionToken = localStorage.getItem('gestorhorarios_session') || '';
let resolverLoginPendiente = null;
let estadoPeriodoActual = null;
let horarioActualReferencia = null;
let horarioPublicadoReferencia = null;
const PERIODO_MINIMO = '2026-08';
// Primer día con programación. Agosto de 2026 es la base histórica de la
// aplicación: nada anterior se puede crear ni modificar, y todos los campos de
// fecha lo usan como tope inferior en lugar de repetir la fecha a mano.
const INICIO_OPERACION_ISO = `${PERIODO_MINIMO}-01`;

// Deja todos los campos de fecha del documento con el mismo tope inferior, sin
// tener que repetirlo en cada uno del HTML. Se vuelve a aplicar cada vez que se
// pinta una tabla, porque las filas se crean desde JavaScript.
function aplicarFechaMinimaDocumento(raiz = document) {
    raiz.querySelectorAll('input[type="date"]').forEach(el => {
        if (el.dataset.sinMinimo === '1') return;
        if (!el.min || el.min < INICIO_OPERACION_ISO) el.min = INICIO_OPERACION_ISO;
    });
    raiz.querySelectorAll('input[type="month"]').forEach(el => {
        if (el.dataset.sinMinimo === '1') return;
        if (!el.min || el.min < PERIODO_MINIMO) el.min = PERIODO_MINIMO;
    });
}
const FECHA_MINIMA = INICIO_OPERACION_ISO;
let editorFormularioEstado = null;

function aplicarRolUI(usuario) {
    sesionUsuario = usuario || null;
    document.body.dataset.role = usuario?.rol || '';
    document.body.classList.toggle('auth-locked', !usuario);
    $('sesion-actual')?.classList.toggle('hidden', !usuario);
    if ($('sesion-nombre')) $('sesion-nombre').textContent = usuario?.nombre || '';
}

// Los avisos del acceso se dicen en una línea, sin titulares alarmantes: la
// pantalla de entrada es lo primero que se ve y no tiene por qué asustar.
function avisoAcceso(titulo, detalle = '', tono = 'aviso') {
    const caja = document.getElementById('login-alerta');
    if (!caja) return;
    caja.innerHTML = `<strong>${esc(titulo)}</strong>${detalle ? `<span>${esc(detalle)}</span>` : ''}`;
    caja.classList.toggle('error', tono === 'error');
    caja.classList.remove('hidden');
}

function bloquearSesion(mensaje='') {
    sessionToken = '';
    sesionUsuario = null;
    localStorage.removeItem('gestorhorarios_session');
    aplicarRolUI(null);
    if (mensaje) avisoAcceso('Vuelve a entrar', mensaje);
}

async function esperarInicioSesion() {
    if (sessionToken) {
        try {
            const data = await api('/api/auth/session');
            aplicarRolUI(data.usuario);
            return data.usuario;
        } catch (_) { bloquearSesion(); }
    }
    aplicarRolUI(null);
    return new Promise(resolve => { resolverLoginPendiente = resolve; });
}

// Un solo control para ver la contraseña: icono de ojo. El icono nativo de
// WebView2/Edge queda oculto por CSS, así que nunca hay dos botones con la
// misma función. El estado se refleja en aria-pressed para lectores de
// pantalla y para elegir el icono correcto.
const ICONO_OJO = `<svg class="eye-open" viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12Z"/><circle cx="12" cy="12" r="2.8"/></svg><svg class="eye-slash" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 3l18 18"/><path d="M10.6 6.7A9.9 9.9 0 0 1 12 6.6c6.4 0 10 5.4 10 5.4a18 18 0 0 1-3.3 3.8"/><path d="M6.5 8.3A17.6 17.6 0 0 0 2 12s3.6 5.4 10 5.4c1.4 0 2.6-.2 3.7-.6"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/></svg>`;

function alternarVisibilidadClave(boton, input) {
    if (!boton || !input) return;
    const mostrar = input.type === 'password';
    input.type = mostrar ? 'text' : 'password';
    boton.setAttribute('aria-pressed', mostrar ? 'true' : 'false');
    const etiqueta = mostrar ? 'Ocultar contraseña' : 'Mostrar contraseña';
    boton.setAttribute('aria-label', etiqueta);
    boton.setAttribute('title', etiqueta);
    try { input.focus({preventScroll:true}); } catch(_) { input.focus(); }
}

function botonOjoClave() {
    return `<button class="password-toggle" type="button" data-toggle-password aria-pressed="false" aria-label="Mostrar contraseña" title="Mostrar contraseña">${ICONO_OJO}</button>`;
}

function pedirClaveAdmin(titulo='Confirmar acción de administrador') {
    return new Promise(resolve => {
        const overlay=document.createElement('div'); overlay.className='modal-backdrop';
        overlay.innerHTML=`<div class="modal-card"><div class="modal-head"><div><h3>${esc(titulo)}</h3><p>Por seguridad, escribe nuevamente la contraseña del administrador.</p></div></div><label>Contraseña de administrador<span class="password-field"><input id="clave-admin-temporal" type="password" autocomplete="current-password">${botonOjoClave()}</span></label><div class="modal-actions"><button type="button" class="secondary" data-cancel>Cancelar</button><button type="button" data-ok>Continuar</button></div></div>`;
        document.body.appendChild(overlay);
        const input=overlay.querySelector('#clave-admin-temporal');
        const cerrar=v=>{overlay.remove();resolve(v);};
        overlay.querySelector('[data-cancel]').onclick=()=>cerrar(null);
        overlay.querySelector('[data-ok]').onclick=()=>cerrar(input.value || '');
        overlay.querySelector('[data-toggle-password]').onclick=ev=>alternarVisibilidadClave(ev.currentTarget,input);
        input.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();cerrar(input.value||'');} if(e.key==='Escape')cerrar(null);});
        setTimeout(()=>input.focus(),0);
    });
}

function pedirClaveUsuario(titulo='Confirmar acción') {
    return new Promise(resolve => {
        const overlay=document.createElement('div'); overlay.className='modal-backdrop';
        overlay.innerHTML=`<div class="modal-card"><div class="modal-head"><div><h3>${esc(titulo)}</h3><p>Confirma tu contraseña para continuar.</p></div></div><label>Tu contraseña<span class="password-field"><input id="clave-usuario-temporal" type="password" autocomplete="current-password">${botonOjoClave()}</span></label><div class="modal-actions"><button type="button" class="secondary" data-cancel>Cancelar</button><button type="button" data-ok>Continuar</button></div></div>`;
        document.body.appendChild(overlay);
        const input=overlay.querySelector('#clave-usuario-temporal');
        const cerrar=v=>{overlay.remove();resolve(v);};
        overlay.querySelector('[data-cancel]').onclick=()=>cerrar(null);
        overlay.querySelector('[data-ok]').onclick=()=>cerrar(input.value || '');
        overlay.querySelector('[data-toggle-password]').onclick=ev=>alternarVisibilidadClave(ev.currentTarget,input);
        input.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();cerrar(input.value||'');} if(e.key==='Escape')cerrar(null);});
        setTimeout(()=>input.focus(),0);
    });
}
