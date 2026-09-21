// 13d-historial.js · Ver LEEME.md para el contrato de carga.
'use strict';

let auditoriaItems = [];
// El vocabulario del Historial.
//
// Las claves son **exactamente** los nombres que el servidor escribe con
// `historial.anotar(...)`. Estaban escritas de memoria y casi ninguna coincidía:
// el servidor apunta `alta_personal` y aquí se esperaba `crear_empleado`,
// apunta `crear_asignacion` y aquí `crear_requerimiento`, apunta `marcar_oficial`
// y aquí `horario_oficial`. De las cincuenta acciones que el programa registra,
// acertaban once: el resto salía como «Cambio registrado».
//
// Y no era solo feo: el buscador de esta pantalla busca sobre el texto ya
// traducido, así que escribir «personal» o «asignación» no encontraba nada.
//
// `pruebas/test_historial.py` comprueba que no falte ninguna.
function nombreAccionHistorial(accion='') {
    const mapa={
        // Personal
        alta_personal:'Personal dado de alta', cambio_personal:'Personal modificado',
        retiro_personal:'Personal retirado', reactivacion_personal:'Personal reactivado',
        borrar_personal:'Personal eliminado definitivamente',
        cambio_turno:'Cambio de turno programado', corregir_cambio_turno:'Cambio de turno corregido',
        deshacer_cambio_turno:'Cambio de turno deshecho',
        // Solicitudes
        crear_solicitud:'Solicitud creada', editar_solicitud:'Solicitud corregida',
        aprobar_solicitud:'Solicitud aprobada', rechazar_solicitud:'Solicitud rechazada',
        cancelar_solicitud:'Solicitud cancelada', borrar_solicitud:'Solicitud eliminada',
        solicitud_pendiente:'Solicitud devuelta a pendiente',
        limpiar_solicitudes:'Solicitudes depuradas',
        // Asignaciones
        crear_asignacion:'Asignación creada', crear_asignacion_masiva:'Asignación para grupo creada',
        editar_asignacion:'Asignación corregida', cancelar_asignacion:'Asignación cancelada',
        cancelar_grupo_asignacion:'Asignación para grupo cancelada',
        borrar_asignacion:'Asignación eliminada',
        borrar_grupo_asignacion:'Asignación para grupo eliminada',
        limpiar_asignaciones:'Asignaciones depuradas',
        // Horario
        generar_horario:'Horario generado', marcar_oficial:'Horario marcado como oficial',
        deshacer_oficial:'Horario oficial deshecho', publicar_horario:'Horario publicado',
        reprogramacion_parcial:'Horario reorganizado',
        quitar_cambio_manual:'Cambio manual retirado', exportar_excel:'Excel exportado',
        cerrar_semana:'Semana cerrada', habilitar_semana:'Semana habilitada',
        // Configuración
        mover_festivo:'Festivo movido', restaurar_festivo:'Festivo restaurado',
        guardar_regla_cobertura:'Reparto por área guardado',
        borrar_regla_cobertura:'Reparto por área eliminado',
        guardar_regla_operacion:'Regla del horario guardada',
        borrar_regla_operacion:'Regla del horario eliminada',
        cambiar_modo_app:'Claro u oscuro cambiado', cambiar_tema_app:'Color de la aplicación cambiado',
        restablecer_tema_app:'Color de la aplicación restablecido',
        aplicar_paleta_excel:'Paleta del Excel aplicada',
        cambiar_barra_ventana:'Barra de la ventana cambiada',
        reiniciar_programacion:'Programación reiniciada',
        reiniciar_fabrica:'Aplicación restablecida de fábrica',
        // Seguridad y sistema
        inicio_sesion:'Inicio de sesión', crear_usuario:'Cuenta creada',
        estado_usuario:'Cuenta activada o desactivada',
        cambiar_clave_propia:'Contraseña propia actualizada',
        cambiar_clave_usuario:'Contraseña de otra cuenta actualizada',
        crear_copia:'Copia de seguridad creada', restaurar_copia:'Copia restaurada',
    };
    return mapa[accion] || 'Cambio registrado';
}
function nombreEntidadHistorial(entidad='') {
    // Las seis que el servidor usa de verdad. `requerimiento`, `semana`,
    // `festivo`, `operacion` y `auth` no las escribe nadie: se quedan por si
    // quedara alguna fila vieja de una versión anterior.
    const mapa={empleado:'Personal',solicitud:'Solicitudes',asignacion:'Asignaciones',
        horario:'Horario',configuracion:'Configuración',seguridad:'Seguridad',sistema:'Sistema',
        requerimiento:'Asignaciones',semana:'Semanas',festivo:'Festivos',operacion:'Sistema',auth:'Seguridad'};
    return mapa[String(entidad||'').toLowerCase()] || 'Aplicación';
}
function mesNombreNumero(m) {
    return ['','Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'][Number(m)] || String(m||'');
}
function detalleAuditoria(x) {
    const d=x.detalle||{};
    const partes=[];
    if (d.etiqueta) partes.push(d.etiqueta);
    else if (d.nombre) partes.push(d.nombre);
    else if (d.alcance==='todos') partes.push('Todo el personal');
    else if (d.area) partes.push(`Área ${nombreArea(d.area)}`);
    if (d.cantidad) partes.push(`${d.cantidad} persona(s)`);
    else if (Array.isArray(d.creados) && d.creados.length) partes.push(`${d.creados.length} persona(s)`);
    if (d.tipo && x.entidad==='requerimiento') partes.push(nombreRequerimiento(d.tipo));
    if (d.tipo && x.entidad==='solicitud') partes.push(nombreSolicitud(d.tipo));
    if (d.anio && d.mes) partes.push(`${mesNombreNumero(d.mes)} ${d.anio}`);
    if (d.fecha) partes.push(fechaBonita(d.fecha));
    if (d.fecha_original) partes.push(`${fechaBonita(d.fecha_original)}${d.fecha_nueva ? ` → ${fechaBonita(d.fecha_nueva)}` : ''}`);
    if (d.semana_inicio) partes.push(`Desde ${fechaBonita(d.semana_inicio)}${d.semana_fin ? ` hasta ${fechaBonita(d.semana_fin)}` : ''}`);
    if (d.forzado || d.permitir_excepciones_manuales) partes.push('Con excepción administrativa');
    if (d.motivo_excepcion_manual) partes.push(`Motivo: ${d.motivo_excepcion_manual}`);
    if (d.mensaje && !partes.some(p=>String(p).includes(d.mensaje))) partes.push(d.mensaje);
    if (d.realizado_por) partes.push(`Realizado por ${d.realizado_por}`);
    if (!partes.length) {
        if (x.accion==='crear_backup') partes.push('Se guardó una copia de seguridad de la información actual.');
        else if (x.accion==='restaurar_backup') partes.push('Se restauró una copia de seguridad.');
        else if (x.accion==='reiniciar_fabrica') partes.push('Se restauró la configuración inicial de la aplicación.');
        else partes.push('Cambio realizado correctamente.');
    }
    return partes.join(' · ');
}
function accionHistorialHtml(x) {
    const d=x.detalle||{};
    if (['cancelar_solicitud','rechazar_solicitud'].includes(x.accion) && d.id) {
        return `<button type="button" class="danger-soft" onclick="eliminarSolicitudDesdeHistorial(${Number(d.id)})">Eliminar registro</button>`;
    }
    // `cancelar_asignacion`, que es como lo escribe el servidor. Con el
    // nombre de antes, el botón «Eliminar registro» de una asignación
    // cancelada no aparecía nunca (el de solicitudes sí, porque ese
    // nombre sí coincidía).
    if (x.accion==='cancelar_asignacion' && d.id) {
        return `<button type="button" class="danger-soft" onclick="eliminarRequerimientoDesdeHistorial(${Number(d.id)})">Eliminar registro</button>`;
    }
    if (x.accion==='cancelar_grupo_asignacion' && d.grupo_id) {
        return `<button type="button" class="danger-soft" onclick="eliminarGrupoDesdeHistorial('${esc(d.grupo_id)}')">Eliminar grupo</button>`;
    }
    return '—';
}

window.eliminarSolicitudDesdeHistorial = async id => {
    const ok=await confirmarUI({titulo:'Eliminar solicitud del historial',mensaje:'¿Esta solicitud se creó por error y debe desaparecer por completo?',detalle:'Se eliminará el registro y todas sus trazas. Si realmente existió pero fue cancelada, déjala en Historial.',aceptar:'Eliminar definitivamente',peligro:true});
    if(!ok)return;
    try { const r=await api('/api/solicitudes/'+id,{method:'DELETE'}); await Promise.all([cargarSolicitudes(),cargarAuditoria(),cargarEstadoPeriodo()]); toast(r.mensaje,'success','Solicitud eliminada'); } catch(e){toast(e.message,'error','No se pudo eliminar');}
};
window.eliminarRequerimientoDesdeHistorial = async id => {
    const ok=await confirmarUI({titulo:'Eliminar asignación del historial',mensaje:'¿Esta asignación se creó por error y debe desaparecer por completo?',detalle:'Se eliminará de la base, del estado del período y del Historial. Si sí existió pero se canceló, conserva el registro.',aceptar:'Eliminar definitivamente',peligro:true});
    if(!ok)return;
    try { const r=await api('/api/requerimientos/'+id,{method:'DELETE'}); await Promise.all([cargarRequerimientos(),cargarAuditoria(),cargarEstadoPeriodo()]); toast(r.mensaje,'success','Asignación eliminada'); } catch(e){toast(e.message,'error','No se pudo eliminar');}
};
window.eliminarGrupoDesdeHistorial = async grupoId => {
    const ok=await confirmarUI({titulo:'Eliminar grupo del historial',mensaje:'¿Este grupo masivo se creó por error y debe desaparecer por completo?',detalle:'Se borrarán todas sus asignaciones y todas las trazas del grupo. Si la actividad sí existió pero se canceló, no la elimines.',aceptar:'Eliminar grupo definitivamente',peligro:true});
    if(!ok)return;
    try { const r=await api('/api/requerimientos/grupo/'+encodeURIComponent(grupoId),{method:'DELETE'}); await Promise.all([cargarRequerimientos(),cargarAuditoria(),cargarEstadoPeriodo()]); toast(r.mensaje,'success','Grupo eliminado'); } catch(e){toast(e.message,'error','No se pudo eliminar');}
};

function renderAuditoria() {
    const tbody = $('tabla-auditoria')?.querySelector('tbody');
    if (!tbody) return;
    const tipo=($('historial-tipo')?.value||'').toLowerCase();
    const q=($('historial-buscar')?.value||'').trim().toLowerCase();
    const items=auditoriaItems.filter(x=>{
        if(tipo && String(x.entidad||'').toLowerCase()!==tipo) return false;
        if(!q) return true;
        return `${x.creado_en||''} ${nombreAccionHistorial(x.accion)} ${nombreEntidadHistorial(x.entidad)} ${detalleAuditoria(x)}`.toLowerCase().includes(q);
    });
    tbody.innerHTML = items.map(x => `<tr><td>${esc(x.creado_en)}</td><td>${esc(nombreAccionHistorial(x.accion))}</td><td>${esc(nombreEntidadHistorial(x.entidad))}</td><td class="audit-detail">${esc(detalleAuditoria(x))}</td><td class="table-actions">${accionHistorialHtml(x)}</td></tr>`).join('') || '<tr><td colspan="5">No hay acciones que coincidan con los filtros.</td></tr>';
}
async function cargarAuditoria() {
    const data = await api('/api/operacion/auditoria?limite=300');
    auditoriaItems=data.items||[]; renderAuditoria();
}
if ($('historial-tipo')) $('historial-tipo').onchange=renderAuditoria;
if ($('historial-buscar')) $('historial-buscar').oninput=renderAuditoria;


$('limpiar-historial').onclick = async () => {
    // Este botón no había funcionado nunca, y tenía tres cosas mal a la vez:
    //
    // · el servidor pide la contraseña de administrador y aquí no se pedía ni
    //   se mandaba, así que contestaba «La contraseña no es correcta» siempre;
    // · el aviso leía `eliminados` y lo que llega se llama `borradas`, así que
    //   habría dicho «undefined registro(s)» aunque hubiera funcionado;
    // · y el texto prometía que los datos se conservaban «en la base para la
    //   trazabilidad técnica». No es verdad: se borran. Alguien podía aceptar
    //   creyendo que el rastro quedaba, y el rastro es justo lo que se pierde.
    //
    // Los tres salieron el día que una prueba lo pulsó por primera vez.
    const ok = await confirmarUI({
        titulo:'Borrar el historial',
        mensaje:'¿Borrar todos los registros del historial?',
        detalle:'Se borran de la base de datos y no hay forma de recuperarlos: '
              + 'se pierde el rastro de quién hizo qué y cuándo. No se toca ningún '
              + 'horario, solicitud ni asignación. Si lo que quieres es guardarlo '
              + 'antes, crea una copia de seguridad desde Configuración.',
        aceptar:'Borrar el historial', peligro:true});
    if (!ok) return;
    const claveAdmin = await pedirClaveAdmin('Borrar el historial');
    if (!claveAdmin) return;
    try {
        const r = await api('/api/operacion/auditoria',
                            {method:'DELETE', headers:{'X-Admin-Password':claveAdmin}});
        await cargarAuditoria();
        toast(`Se borraron ${r.borradas} registro(s) del historial.`,
              'success','Historial borrado');
    } catch (e) { toast(e.message,'error','No se pudo borrar el historial'); }
};

$('crear-backup').onclick = async () => {
    const claveAdmin = await pedirClaveAdmin('Crear copia de seguridad');
    if (!claveAdmin) return;
    try {
        const r = await api('/api/operacion/backup',{method:'POST',headers:{'X-Admin-Password':claveAdmin}});
        $('estado-backup').textContent = `Última copia: ${r.nombre} · ${r.creado_en || ''} · V${r.version || ''} · ${Math.round((r.tamano_bytes||0)/1024)} KB`;
        toast(r.mensaje,'success','Copia creada');
    } catch (e) { toast(e.message,'error','No se pudo crear la copia'); }
};

$('archivo-backup').onchange = async ev => {
    const file = ev.target.files?.[0]; if (!file) return;
    const ok = await confirmarUI({titulo:'Restaurar copia de seguridad',mensaje:`¿Restaurar ${file.name}?`,detalle:'La base actual será reemplazada por el contenido de la copia. Crea antes otra copia si necesitas conservar el estado actual.',aceptar:'Restaurar',peligro:true});
    if (!ok) { ev.target.value=''; return; }
    const claveAdmin = await pedirClaveAdmin('Restaurar copia de seguridad');
    if (!claveAdmin) { ev.target.value=''; return; }
    try {
        const fd = new FormData(); fd.append('archivo',file);
        const r = await api('/api/operacion/restore',{method:'POST',body:fd,headers:{'X-Admin-Password':claveAdmin}});
        toast(r.mensaje,'success','Copia restaurada');
        setTimeout(()=>location.reload(),1000);
    } catch (e) { toast(e.message,'error','No se pudo restaurar'); }
    finally { ev.target.value=''; }
};
