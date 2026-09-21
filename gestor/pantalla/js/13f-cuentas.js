// 13f-cuentas.js · Ver LEEME.md para el contrato de carga.
'use strict';

async function cargarCuentasLogin() {
    try {
        const data = await leerAlArrancar('/api/auth/cuentas-login');
        const select = $('login-usuario');
        if (!select) return;
        const previo = select.value;
        select.innerHTML = (data.cuentas || []).map(x => `<option value="${esc(x.usuario)}">${esc(x.nombre)}</option>`).join('');
        if (previo && [...select.options].some(o => o.value === previo)) select.value = previo;
        else if ([...select.options].some(o => o.value === 'katerine')) select.value = 'katerine';
        void conTopeDeEspera(rellenarClaveRecordada, 2).catch(error => {
            console.warn('[acceso] no se pudo recuperar la clave recordada:', error);
        });
    } catch (_) {
        const select=$('login-usuario');
        if (select) select.innerHTML='<option value="katerine">Katerine Manzanares</option><option value="admin">Administrador</option>';
        void conTopeDeEspera(rellenarClaveRecordada, 2).catch(error => {
            console.warn('[acceso] no se pudo recuperar la clave recordada:', error);
        });
    }
}

async function cargarUsuariosSeguridad() {
    const cont = $('lista-usuarios-admin');
    if (!sesionUsuario || sesionUsuario.rol !== 'admin') {
        if (cont) cont.innerHTML='';
        return;
    }
    const data = await api('/api/auth/usuarios');
    const usuarios = (data.usuarios || []).filter(x => x.rol !== 'admin');
    if (!cont) return;
    cont.innerHTML = usuarios.length ? usuarios.map(u => `
        <div class="user-admin-row" data-uid="${u.id}">
            <div class="user-admin-main"><strong>${esc(u.nombre)}</strong><span>@${esc(u.usuario)} · ${u.activo ? 'Activo' : 'Desactivado'}</span></div>
            <span class="password-field user-password-field"><input class="user-password-reset" type="password" minlength="8" autocomplete="new-password" placeholder="Nueva contraseña">${botonOjoClave()}</span>
            <button type="button" class="secondary user-reset-password">Cambiar clave</button>
            <button type="button" class="${u.activo ? 'danger-button' : 'secondary'} user-toggle-state">${u.activo ? 'Desactivar' : 'Activar'}</button>
        </div>`).join('') : '<div class="muted">No hay usuarios adicionales.</div>';
    conectarOjosDeClave(cont);
    cont.querySelectorAll('.user-admin-row').forEach(row => {
        const uid=Number(row.dataset.uid);
        row.querySelector('.user-reset-password').onclick=async()=>{
            const nueva=row.querySelector('.user-password-reset').value;
            if (!nueva || nueva.length<8) return toast('La contraseña debe tener al menos 8 caracteres.','warning','Contraseña incompleta');
            try { const r=await api(`/api/auth/usuarios/${uid}/password`,{method:'PUT',body:JSON.stringify({nueva_password:nueva})}); row.querySelector('.user-password-reset').value=''; toast(r.mensaje,'success','Cuenta actualizada'); }
            catch(e){ toast(e.message,'error','No se pudo cambiar la contraseña'); }
        };
        row.querySelector('.user-toggle-state').onclick=async()=>{
            const usuario=usuarios.find(x=>x.id===uid); if(!usuario)return;
            try { const r=await api(`/api/auth/usuarios/${uid}/estado`,{method:'PUT',body:JSON.stringify({activo:!usuario.activo})}); toast(r.mensaje,'success','Cuenta actualizada'); await cargarUsuariosSeguridad(); await cargarCuentasLogin(); }
            catch(e){ toast(e.message,'error','No se pudo actualizar la cuenta'); }
        };
    });
}

$('crear-usuario-horarios')?.addEventListener('click', async()=>{
    const nombre=$('nuevo-usuario-nombre')?.value.trim();
    const usuario=$('nuevo-usuario-login')?.value.trim();
    const password=$('nuevo-usuario-clave')?.value || '';
    const faltan=[]; if(!nombre)faltan.push('nombre'); if(!usuario)faltan.push('usuario'); if(!password)faltan.push('contraseña inicial');
    if(faltan.length) return toast(`Falta completar: ${faltan.join(', ')}.`,'warning','No se pudo crear la cuenta');
    if(password.length<8) return toast('La contraseña debe tener al menos 8 caracteres.','warning','Contraseña incompleta');
    try {
        const r=await api('/api/auth/usuarios',{method:'POST',body:JSON.stringify({nombre,usuario,password})});
        $('nuevo-usuario-nombre').value=''; $('nuevo-usuario-login').value=''; $('nuevo-usuario-clave').value='';
        await cargarUsuariosSeguridad(); await cargarCuentasLogin(); toast(r.mensaje,'success','Usuario creado');
    } catch(e){ toast(e.message,'error','No se pudo crear el usuario'); }
});

$('form-login')?.addEventListener('submit', async ev => {
    ev.preventDefault();
    const usuario=$('login-usuario').value;
    const password=$('login-password').value;
    if (!password) {
        avisoAcceso('Escribe tu contraseña', 'Sin ella no se puede entrar.');
        $('login-password').focus();
        return;
    }
    try {
        const data=await api('/api/auth/login',{method:'POST',body:JSON.stringify({usuario,password})});
        sessionToken=data.token; localStorage.setItem('gestorhorarios_session',sessionToken);
        // La persistencia se confirma antes de desbloquear la aplicación. Así,
        // incluso si la ventana se cierra de golpe justo después de entrar, la
        // credencial ya quedó escrita de forma atómica y protegida por Windows.
        let recuerdo = {recordada: false};
        try {
            recuerdo = (await guardarClaveRecordada(usuario, password)) || {recordada: false};
        } catch (fallo) {
            recuerdo = {recordada: false, motivo: fallo.message};
        }
        // Se vacía y se **desmarca**: si más tarde la sesión caduca y vuelve
        // esta pantalla, la contraseña recordada tiene que poder rellenarla.
        $('login-password').value=''; $('login-password').dataset.escrito='';
        $('login-alerta').classList.add('hidden');
        aplicarRolUI(data.usuario);
        if (recuerdo.motivo) {
            toast(`Has entrado sin problema, pero este equipo no pudo guardar tu contraseña: ${recuerdo.motivo}. `
                  + 'Tendrás que escribirla la próxima vez.',
                  'warning', 'No se pudo recordar la contraseña', 9000);
        }
        const resolve=resolverLoginPendiente; resolverLoginPendiente=null; resolve?.(data.usuario);
    } catch(e) {
        avisoAcceso('No se pudo entrar', e.message, 'error');
    }
});

$('toggle-login-password')?.addEventListener('click', () => {
    alternarVisibilidadClave($('toggle-login-password'), $('login-password'));
});

// Cualquier campo de contraseña del documento con su botón al lado queda
// conectado. Antes solo funcionaba el del acceso; los de cambiar la clave y
// crear usuario ni siquiera tenían botón.
function conectarOjosDeClave(raiz = document) {
    raiz.querySelectorAll('[data-toggle-password]').forEach(boton => {
        if (boton.dataset.ojoListo === '1') return;
        const campo = boton.closest('.password-field')?.querySelector('input[type="password"], input[type="text"]');
        if (!campo) return;
        boton.dataset.ojoListo = '1';
        boton.addEventListener('click', () => alternarVisibilidadClave(boton, campo));
    });
}
