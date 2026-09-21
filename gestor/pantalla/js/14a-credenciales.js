// Recordar la contraseña, la carga inicial, la guía y el calendario
// ---------------------------------------------------------------------------
// Parte de la pantalla del Gestor de Horarios. Los archivos de esta carpeta se
// cargan en orden y comparten el mismo ámbito, así que juntos son exactamente
// el app.js de antes. Ver frontend/js/LEEME.md.

'use strict';

// ---------------------------------------------------------------------------
// Recordar la contraseña en este equipo
// ---------------------------------------------------------------------------
// Las claves se recuerdan mediante el almacén protegido de Windows.
// Eliminar el respaldo antiguo en texto legible sin copiarlo a otro sitio.
const CLAVE_RECORDADAS = 'gestorhorarios_claves_recordadas';
try { localStorage.removeItem(CLAVE_RECORDADAS); } catch (_) {}

function apiClaveNativa() {
    return window.pywebview?.api || null;
}

async function esperarApiClaveNativa(intentos = 20) {
    for (let i = 0; i < intentos; i += 1) {
        const apiNativa = apiClaveNativa();
        if (apiNativa?.leer_clave && apiNativa?.guardar_clave && apiNativa?.olvidar_clave) return apiNativa;
        await new Promise(resolve => setTimeout(resolve, 25));
    }
    return null;
}

async function guardarClaveRecordada(usuario, password) {
    const recordar = !!$('login-recordar')?.checked;
    const apiNativa = await esperarApiClaveNativa();
    if (!apiNativa) return {recordada: false,
        motivo: recordar ? 'esta opción necesita la aplicación de Windows' : null};
    const resultado = await conTopeDeEspera(() => recordar
        ? apiNativa.guardar_clave(usuario, password) : apiNativa.olvidar_clave(usuario), 3);
    if (recordar && resultado?.ok !== true) {
        return {recordada: false, motivo: String(resultado?.error || 'este equipo no pudo guardarla')};
    }
    return {recordada: recordar};
}

async function rellenarClaveRecordada() {
    const usuario = $('login-usuario')?.value;
    const campo = $('login-password');
    const casilla = $('login-recordar');
    if (!usuario || !campo || !casilla) return;
    // Si la persona ya escribió, no se le toca lo escrito.
    //
    // Esto llega hasta el final con dos `await` por medio —la lista de cuentas y
    // la caja de claves del sistema, que tarda hasta ocho intentos—, así que la
    // línea de abajo se ejecutaba **medio segundo después de abrirse la
    // pantalla**. Quien escribía deprisa veía su contraseña desaparecer sola del
    // cuadro y, al pulsar Entrar, «Escribe tu contraseña» con la contraseña
    // recién escrita. Aparecía como intermitente, que es la peor forma de
    // aparecer: la segunda vez ya no pasaba y nadie lo podía reproducir.
    if (campo.dataset.escrito === '1') return;
    let guardada = '';
    const apiNativa = await esperarApiClaveNativa(8);
    if (apiNativa) {
        try {
            const resultado = await conTopeDeEspera(() => apiNativa.leer_clave(usuario), 2);
            if (resultado?.ok && resultado.recordada) guardada = resultado.password || '';
        } catch (_) {}
    }
    if ($('login-usuario')?.value !== usuario || campo.dataset.escrito === '1') return;
    campo.value = guardada || '';
    casilla.checked = !!guardada;
}

$('login-password')?.addEventListener('input', ev => {
    // Lo marca la persona al teclear. Al cambiar de cuenta se borra la marca:
    // ahí sí queremos la contraseña recordada de la cuenta nueva.
    ev.target.dataset.escrito = ev.target.value ? '1' : '';
});
$('login-usuario')?.addEventListener('change', () => {
    const campo = $('login-password');
    if (campo) { campo.value = ''; campo.dataset.escrito = ''; }
    void rellenarClaveRecordada();
});
$('login-recordar')?.addEventListener('change', async ev => {
    if (ev.target.checked) return;
    const usuario = $('login-usuario')?.value;
    if (!usuario) return;
    const apiNativa = await esperarApiClaveNativa(8);
    try {
        if (apiNativa) {
            const resultado = await conTopeDeEspera(() => apiNativa.olvidar_clave(usuario), 3);
            if (resultado?.ok !== true) throw new Error('No se pudo borrar.');
        }
    } catch (_) {
        avisoAcceso('No se pudo borrar la contraseña recordada',
                    'Cierra y vuelve a abrir la aplicación para intentarlo de nuevo.');
    }
});

$('cerrar-sesion')?.addEventListener('click', async () => {
    try { await api('/api/auth/logout',{method:'POST'}); } catch(_) {}
    // «Recordar» pertenece al equipo, no a la sesión. Salir invalida el token,
    // pero conserva la comodidad elegida para la próxima apertura.
    bloquearSesion();
    location.reload();
});

$('cambiar-clave-propia')?.addEventListener('click', async () => {
    const actual=$('clave-actual').value, nueva=$('clave-nueva').value;
    if (!actual || !nueva) { toast('Escribe tu contraseña actual y la nueva contraseña.','warning','Faltan datos'); return; }
    try {
        const r=await api('/api/auth/password',{method:'PUT',body:JSON.stringify({actual,nueva})});
        toast(r.mensaje,'success','Contraseña actualizada');
        // Si esta cuenta estaba marcada para recordar, sustituye la clave vieja
        // inmediatamente; de lo contrario el siguiente acceso se rellenaría
        // con una contraseña que ya no sirve.
        const usuario = sesionUsuario?.usuario;
        if (usuario) {
            try {
                const apiNativa = await esperarApiClaveNativa();
                if (apiNativa) {
                    const anterior = await conTopeDeEspera(() => apiNativa.leer_clave(usuario), 2);
                    if (anterior?.ok && anterior.recordada) {
                        const resultado = await conTopeDeEspera(() => apiNativa.guardar_clave(usuario, nueva), 3);
                        if (resultado?.ok !== true) throw new Error('No se actualizó el recuerdo.');
                    }
                }
            } catch (_) {
                toast('Tu contraseña cambió. Escribe la nueva al volver a entrar; no se pudo actualizar la copia recordada.',
                      'warning', 'Vuelve a entrar');
            }
        }
        localStorage.removeItem('gestorhorarios_session');
        setTimeout(()=>location.reload(),700);
    } catch(e){ toast(e.message,'error','No se pudo cambiar la contraseña'); }
});
