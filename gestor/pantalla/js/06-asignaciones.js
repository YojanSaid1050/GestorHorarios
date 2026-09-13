// Asignaciones y ajustes, sueltos y por grupo
// ---------------------------------------------------------------------------
// Parte de la pantalla del Gestor de Horarios. Los archivos de esta carpeta se
// cargan en orden y comparten el mismo ámbito, así que juntos son exactamente
// el app.js de antes. Ver frontend/js/LEEME.md.

'use strict';

function nombreArea(area) {
    return ({gestion_social:'Gestión Social',atencion_ciudadano:'Atención al Ciudadano',comunicaciones:'Comunicaciones'})[area] || area || 'Área';
}

let cambiosTurnoProgramados = [];

async function cargarCambiosTurno() {
    const tabla = $('tabla-cambios-turno');
    const tarjeta = $('cambios-turno-card');
    if (!tabla) return;
    const tb = tabla.querySelector('tbody');
    let cambios = [];
    try {
        cambios = (await api('/api/empleados/cambios-turno')).cambios || [];
        cambiosTurnoProgramados = cambios;
    } catch (e) {
        tb.innerHTML = `<tr><td colspan="5" class="table-empty">No se pudieron consultar los cambios de turno: ${esc(e.message)}</td></tr>`;
        return;
    }
    if (tarjeta) tarjeta.classList.toggle('hidden', cambios.length === 0);
    if (!cambios.length) {
        tb.innerHTML = '<tr><td colspan="5" class="table-empty">Todavía no hay ningún cambio de turno programado.</td></tr>';
        return;
    }
    // Los del mes que se está viendo primero, pero se enseñan todos: un cambio
    // de turno vale de su fecha en adelante, así que saber que en noviembre
    // alguien pasa a rotativo importa aunque se esté mirando septiembre.
    tb.innerHTML = cambios.map(c => `<tr class="${tocaElPeriodo([c.vigente_desde]) ? '' : 'de-otro-mes'}">
        <td>${esc(c.empleado_nombre)}</td>
        <td>${esc(fechaBonita(c.vigente_desde))}</td>
        <td>${esc(c.antes)}</td>
        <td><strong>${esc(c.despues)}</strong></td>
        <td class="table-actions">
            <button type="button" class="secondary"
                onclick="editarCambioTurnoProgramado(${c.empleado_id}, '${esc(c.vigente_desde)}')">Editar</button>
            <button type="button" class="danger-soft"
                onclick="deshacerCambioTurno(${c.empleado_id}, '${esc(c.vigente_desde)}', '${esc(c.empleado_nombre)}')">Deshacer</button>
        </td>
    </tr>`).join('');
}

window.editarCambioTurnoProgramado = (empleadoId, fecha) => {
    const cambio = cambiosTurnoProgramados.find(x =>
        Number(x.empleado_id) === Number(empleadoId) && x.vigente_desde === fecha);
    if (!cambio) return toast('No se encontró el cambio que deseas editar.', 'warning', 'Cambio no disponible');
    $('cambio-turno-fecha-original').value = cambio.vigente_desde;
    $('cambio-turno-empleado').value = String(cambio.empleado_id);
    $('cambio-turno-empleado').disabled = true;
    $('cambio-turno-tipo').value = cambio.tipo_turno || 'rotativo';
    if (cambio.turno_fijo) $('cambio-turno-fijo').value = cambio.turno_fijo;
    if (cambio.inicio_rotacion) $('cambio-turno-inicio').value = cambio.inicio_rotacion;
    $('cambio-turno-fecha').value = cambio.vigente_desde;
    $('cambio-turno-fecha')._syncCalendario?.();
    $('cambio-turno-pareja').value = 'si';
    $('cambio-turno-motivo').value = '';
    $('guardar-cambio-turno').textContent = 'Guardar corrección';
    $('cancelar-edicion-cambio-turno').classList.remove('hidden');
    camposCambioTurno();
    document.getElementById('cambio-turno-card')?.scrollIntoView({block:'start', behavior:'smooth'});
    toast('Puedes corregir la fecha o el tipo de turno. La persona se mantiene para evitar trasladar un cambio por error.', 'info', 'Editando cambio programado');
};

// Un cambio de turno se podía poner pero no quitar: quien se equivocaba de
// fecha o de persona se quedaba con él en la lista para siempre y seguía
// afectando al horario. Deshacer devuelve a la persona —y a su pareja, que se
// mueven juntas— exactamente a lo que tenía antes.
window.deshacerCambioTurno = async (empleadoId, fecha, nombre) => {
    const ok = await confirmarUI({
        titulo: 'Deshacer este cambio de turno',
        mensaje: `¿Quitar el cambio de ${nombre} del ${fechaBonita(fecha)}?`,
        detalle: 'La persona vuelve al turno que tenía justo antes. Si tiene pareja y las dos '
               + 'cambiaron ese mismo día, se deshace también la suya: cambian juntas y en turnos '
               + 'contrarios, así que quitar solo una las dejaría a las dos en el mismo turno. '
               + 'Los meses que ya se generaron con este cambio quedarán marcados para recalcular.',
        aceptar: 'Sí, deshacer',
        peligro: true,
    });
    if (!ok) return;
    try {
        const r = await api(`/api/empleados/${empleadoId}/cambio-turno/${fecha}`, {method: 'DELETE'});
        toast(r.mensaje, 'success', 'Cambio deshecho');
        await cargarEmpleados();
        await cargarCambiosTurno();
        await cargarEstadoPeriodo().catch(() => {});
        actualizarAccionGenerar();
    } catch (e) {
        toast(e.message, 'error', 'No se pudo deshacer');
    }
};

async function cargarRequerimientos() {
    const requerimientosTodos = await api('/api/requerimientos');
    requerimientos = (requerimientosTodos || []).filter(r => (r.estado || 'activo') === 'activo' && (r.estado_efectivo || 'activo') !== 'finalizado');
    renderRequerimientos();
}

// Qué asignaciones son de este mes. Una habitualidad indefinida —«los domingos
// trabaja en AM»— no pertenece a un mes: sigue viva desde que se creó, así que
// aparece en todos los meses desde entonces. Lo demás entra si alguno de sus
// días cae dentro del periodo.
function requerimientoDelPeriodo(r) {
    if (verTodosLosMeses) return true;
    const rango = rangoDelPeriodo();
    if (!rango) return true;
    if (r.recurrente_indefinido) return String(r.vigente_desde || '').slice(0, 10) <= rango.hasta;
    return tocaElPeriodo([...(r.fechas || []), r.vigente_desde]);
}

function renderRequerimientos() {
    if (!Array.isArray(requerimientos)) return;
    actualizarContadoresMenu();
    renderBarrasPeriodo();
    const tb = $('tabla-requerimientos')?.querySelector('tbody');
    if (!tb) return;
    const diasNombre = ['Lun','Mar','Mié','Jue','Vie','Sáb','Dom'];
    const grupos = new Map();
    const filas = [];
    const delMes = requerimientos.filter(requerimientoDelPeriodo);
    const ocultas = requerimientos.length - delMes.length;
    for (const r of delMes) {
        if (r.grupo_id) {
            if (!grupos.has(r.grupo_id)) grupos.set(r.grupo_id, []);
            grupos.get(r.grupo_id).push(r);
        } else filas.push({tipo:'individual', items:[r]});
    }
    for (const items of grupos.values()) filas.push({tipo:'grupo', items});
    filas.sort((a,b) => {
        const ra=a.items[0], rb=b.items[0];
        const fa=(ra.fechas||[])[0] || ra.vigente_desde || '';
        const fb=(rb.fechas||[])[0] || rb.vigente_desde || '';
        return fa.localeCompare(fb) || String(ra.empleado_nombre||'').localeCompare(String(rb.empleado_nombre||''));
    });
    function textoFechas(r) {
        const fechas=r.fechas||[];
        return r.recurrente_indefinido
            ? `${(r.dias_semana || []).map(d => diasNombre[Number(d)]).join(', ')} · desde ${fechaBonita(r.vigente_desde)} · hasta finalizar`
            : (fechas.length <= 3 ? fechas.map(fechaBonita).join(', ') : `${fechaBonita(fechas[0])} a ${fechaBonita(fechas[fechas.length - 1])} · ${fechas.length} días`);
    }
    tb.innerHTML = filas.map(gr => {
        const r=gr.items[0];
        const vencido = gr.items.every(x => x.estado_efectivo === 'finalizado' || x.estado === 'cancelado' || (!x.recurrente_indefinido && (x.fechas||[]).length && x.fechas[x.fechas.length-1] < ymd(new Date())));
        const esGrupo=gr.tipo==='grupo';
        const etiqueta = esGrupo ? (r.grupo_etiqueta || (r.grupo_alcance==='area' ? `Área ${nombreArea(r.grupo_area)}` : 'Todo el personal')) : r.empleado_nombre;
        const horarios=[...new Set(gr.items.map(x => x.turno_excepcion || x.horario_administrativo || '—'))];
        const horario=horarios.length===1 ? horarios[0] : 'Según área';
        const cobertura = gr.items.some(x=>x.cubrir_pm) ? 'Cobertura configurada' : 'Automática';
        const cantidad = esGrupo ? `<small class="group-count">${gr.items.length} persona(s)</small>` : '';
        const acciones = esGrupo
            ? `<button onclick="cancelarGrupoRequerimiento('${r.grupo_id}')" class="secondary">Cancelar grupo</button><button onclick="eliminarGrupoRequerimiento('${r.grupo_id}')" class="danger-soft">Eliminar grupo</button>`
            : `<button onclick="editarRequerimiento(${r.id})">Editar</button><button onclick="cancelarRequerimiento(${r.id})" class="secondary">Cancelar</button><button onclick="eliminarRequerimiento(${r.id})" class="danger-soft">Eliminar</button>`;
        return `<tr class="${vencido ? 'row-expired' : ''}">
            <td><strong>${esc(etiqueta)}</strong>${cantidad}</td>
            <td>${esc(nombreRequerimiento(r.tipo))}</td>
            <td>${esc(horario)}</td>
            <td>${esc(textoFechas(r))}</td>
            <td>${esc(r.tipo === 'descanso_extra' ? '—' : cobertura)}</td>
            <td>${esc(r.descripcion || '—')}</td>
            <td class="table-actions">${acciones}</td>
        </tr>`;
    }).join('') || `<tr><td colspan="7">${
        verTodosLosMeses
            ? 'No hay ninguna asignación registrada.'
            : `No hay asignaciones ni ajustes para ${esc(nombreDelPeriodo())}.${ocultas ? ` Hay ${ocultas} en otros meses: cámbialo arriba o marca «Ver todos los meses».` : ''}`
    }</td></tr>`;
    const nota = $('requerimientos-otros-meses');
    if (nota) {
        nota.textContent = (!verTodosLosMeses && ocultas)
            ? `Hay ${ocultas} asignación(es) más en otros meses. No se han borrado: cambia de mes para verlas.`
            : '';
        nota.classList.toggle('hidden', !(!verTodosLosMeses && ocultas));
    }
}

window.cancelarGrupoRequerimiento = async grupoId => {
    const items = requerimientos.filter(x => x.grupo_id === grupoId);
    if (!items.length) return;
    const r=items[0];
    const etiqueta=r.grupo_etiqueta || (r.grupo_alcance==='area' ? `Área ${nombreArea(r.grupo_area)}` : 'Todo el personal');
    const ok=await confirmarUI({
        titulo:'Cancelar asignación masiva',
        mensaje:`¿La asignación de ${etiqueta} ya no se realizará?`,
        detalle:`Se cancelará para ${items.length} persona(s), quedará registrada en Historial y el horario deberá regenerarse para retirar la condición.`,
        aceptar:'Cancelar asignación', peligro:false,
    });
    if (!ok) return;
    try {
        const data=await api('/api/requerimientos/grupo/'+encodeURIComponent(grupoId)+'/cancelar',{method:'PATCH'});
        await cargarRequerimientos(); await cargarEstadoPeriodo();
        toast(data.mensaje,'success','Asignación masiva cancelada');
    } catch(e) { toast(e.message,'error','No se pudo cancelar el grupo'); }
};

window.eliminarGrupoRequerimiento = async grupoId => {
    const items = requerimientos.filter(x => x.grupo_id === grupoId);
    if (!items.length) return;
    const r=items[0];
    const etiqueta=r.grupo_etiqueta || (r.grupo_alcance==='area' ? `Área ${nombreArea(r.grupo_area)}` : 'Todo el personal');
    const ok=await confirmarUI({
        titulo:'Eliminar asignación masiva definitivamente',
        mensaje:`¿Quieres borrar por completo la asignación de ${etiqueta}?`,
        detalle:`Se eliminará de las ${items.length} persona(s), de los estados y del historial. Usa Cancelar si la asignación sí existía pero finalmente no se realizará.`,
        aceptar:'Eliminar definitivamente', peligro:true,
    });
    if (!ok) return;
    try {
        const data=await api('/api/requerimientos/grupo/'+encodeURIComponent(grupoId),{method:'DELETE'});
        await cargarRequerimientos(); await cargarEstadoPeriodo();
        toast(data.mensaje,'success','Asignación masiva eliminada');
    } catch(e) { toast(e.message,'error','No se pudo eliminar el grupo'); }
};


window.editarRequerimiento = id => {
    const r = requerimientos.find(x => Number(x.id) === Number(id));
    if (!r) return;
    $('requerimiento-id').value = r.id;
    $('requerimiento-alcance').value = 'persona';
    $('requerimiento-empleado').value = r.empleado_id;
    $('requerimiento-tipo').value = r.tipo;
    const fechasReq = r.fechas || [];
    let modoReq = r.recurrente_indefinido ? 'recurrente' : (fechasReq.length > 1 ? 'varios' : 'uno');
    if (!r.recurrente_indefinido && r.tipo === 'excepcion_turno' && fechasReq.length > 1) {
        const span = Math.round((fechaLocal(fechasReq[fechasReq.length - 1]) - fechaLocal(fechasReq[0])) / 86400000) + 1;
        if (span > fechasReq.length) modoReq = 'recurrente';
    }
    $('requerimiento-modo-fechas').value = modoReq;
    $('requerimiento-inicio').value = r.recurrente_indefinido ? (r.vigente_desde || ymd(new Date())) : (fechasReq?.[0] || '');
    $('requerimiento-fin').value = r.recurrente_indefinido ? '' : (fechasReq?.[fechasReq.length - 1] || fechasReq?.[0] || '');
    document.querySelectorAll('.req-weekday').forEach(x => x.checked = false);
    if (modoReq === 'recurrente') {
        const dias = new Set(r.recurrente_indefinido ? (r.dias_semana || []).map(Number) : fechasReq.map(iso => (fechaLocal(iso).getDay() + 6) % 7));
        document.querySelectorAll('.req-weekday').forEach(x => x.checked = dias.has(Number(x.value)));
    }
    configurarHorarioRequerimiento();
    if (r.turno_excepcion) $('requerimiento-horario').value = r.turno_excepcion;
    else if (r.horario_administrativo) $('requerimiento-horario').value = r.horario_administrativo;
    $('requerimiento-cobertura').value = r.cubrir_pm ? 'si' : 'no';
    configurarHorarioRequerimiento();
    $('requerimiento-reemplazo').value = r.reemplazo_empleado_id || '';
    $('requerimiento-descripcion').value = r.descripcion || '';
    sincronizarSelectoresFecha();
    abrirEditorFormulario('form-requerimiento', `Editar asignación · ${r.empleado_nombre || ''}`, 'Ajusta únicamente lo necesario. Guardar la edición no cambia tu posición en la lista.');
};

window.cancelarRequerimiento = async id => {
    const r = requerimientos.find(x => Number(x.id) === Number(id));
    if (!r) return;
    const ok = await confirmarUI({
        titulo:'Cancelar asignación o ajuste',
        mensaje:`¿${nombreRequerimiento(r.tipo)} ya no se realizará?`,
        detalle:'Se conservará en Historial como cancelada y el período quedará pendiente de regeneración para retirar su efecto.',
        aceptar:'Cancelar asignación', peligro:false,
    });
    if (!ok) return;
    try {
        const data=await api(`/api/requerimientos/${id}/cancelar`,{method:'PATCH'});
        await cargarRequerimientos(); await cargarEstadoPeriodo();
        toast(data.mensaje,'success','Asignación cancelada');
    } catch(e) { toast(e.message,'error','No se pudo cancelar'); }
};

window.eliminarRequerimiento = async id => {
    const r = requerimientos.find(x => Number(x.id) === Number(id));
    const ok = await confirmarUI({
        titulo: 'Eliminar asignación o ajuste',
        mensaje: `¿Quieres eliminar ${nombreRequerimiento(r?.tipo || 'este requerimiento')} de ${r?.empleado_nombre || 'esta persona'}?`,
        detalle: 'Se borrará definitivamente de la asignación, los estados y el historial. Si ya había afectado un horario, el período quedará pendiente de regeneración. Usa Cancelar si la asignación sí existía pero finalmente no se realizará.',
        aceptar: 'Eliminar definitivamente', peligro: true,
    });
    if (!ok) return;
    try {
        const data = await api('/api/requerimientos/' + id, {method:'DELETE'});
        await cargarRequerimientos(); await cargarEstadoPeriodo();
        toast(data.mensaje || 'El requerimiento directo fue eliminado.', 'success', 'Eliminado');
    } catch (e) { toast(e.message, 'error', 'No se pudo eliminar'); }
};

let resolverSoluciones = null;
function cerrarSoluciones(valor = null) {
    $('modal-soluciones').classList.add('hidden');
    if (resolverSoluciones) {
        const r = resolverSoluciones; resolverSoluciones = null; r(valor);
    }
}
$('cerrar-soluciones').onclick = () => cerrarSoluciones(null);
$('solucion-cancelar').onclick = () => cerrarSoluciones(null);
$('modal-soluciones').onclick = ev => { if (ev.target === $('modal-soluciones')) cerrarSoluciones(null); };

function elegirSolucionConflictos(pre) {
    return new Promise(resolve => {
        resolverSoluciones = resolve;
        $('soluciones-titulo').textContent = 'Conflicto detectado';
        $('soluciones-resumen').textContent = `${pre.fechas_conflictivas?.length || 0} fecha(s) presentan conflicto. La app no elegirá por ti.`;
        $('soluciones-lista').innerHTML = (pre.conflictos || []).map(c => `<div class="solution-item"><strong>${esc(c.mensaje)}</strong><div>${(c.fechas || []).map(fechaBonita).join(' · ')}</div><ul>${(c.soluciones || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>`).join('');
        $('solucion-manual').classList.remove('hidden');
        $('solucion-manual').textContent = 'Resolver manualmente';
        $('solucion-omitir').textContent = 'Guardar fechas sin conflicto';
        $('solucion-omitir').disabled = !(pre.fechas_disponibles || []).length;
        $('solucion-omitir').onclick = () => cerrarSoluciones({accion:'omitir',fechas:pre.fechas_disponibles || []});
        $('solucion-manual').onclick = () => cerrarSoluciones({accion:'manual'});
        $('modal-soluciones').classList.remove('hidden');
    });
}

function elegirSolucionMasiva(problemas, compatibles) {
    return new Promise(resolve => {
        resolverSoluciones = resolve;
        $('soluciones-titulo').textContent = 'Asignación masiva con conflictos';
        $('soluciones-resumen').textContent = `${problemas.length} persona(s) o combinación(es) requieren revisión. Puedes guardar únicamente los casos compatibles.`;
        $('soluciones-lista').innerHTML = problemas.map(p => `<div class="solution-item"><strong>${esc(p.nombre)}</strong><div>${esc(p.mensaje)}</div>${p.fechas?.length ? `<small>Fechas afectadas: ${p.fechas.map(fechaBonita).join(' · ')}</small>` : ''}</div>`).join('');
        $('solucion-manual').classList.remove('hidden');
        $('solucion-manual').textContent = 'Ir a modificación manual';
        $('solucion-omitir').textContent = `Guardar solo compatibles (${compatibles})`;
        $('solucion-omitir').disabled = compatibles < 1;
        $('solucion-omitir').onclick = () => cerrarSoluciones({accion:'compatibles'});
        $('solucion-manual').onclick = () => cerrarSoluciones({accion:'manual'});
        $('modal-soluciones').classList.remove('hidden');
    });
}

function asignacionAfectaPeriodoVisible({fechas=[], recurrente=false, vigenteDesde=''}) {
    const valor=$('periodo')?.value || '';
    if (!valor) return false;
    if ((fechas||[]).some(f=>String(f).startsWith(valor+'-'))) return true;
    if (recurrente && vigenteDesde) {
        const [y,m]=valor.split('-').map(Number);
        const finMes=new Date(y,m,0,12);
        return fechaLocal(String(vigenteDesde).slice(0,10)) <= finMes;
    }
    return false;
}

async function actualizarHorarioActualTrasAsignacion(contexto) {
    if ($('requerimiento-actualizar-horario')?.value !== 'si') return false;
    if (!asignacionAfectaPeriodoVisible(contexto)) {
        toast('La asignación quedó guardada, pero no corresponde al mes que estás viendo. Abre el mes afectado y actualiza su horario cuando lo necesites.', 'info', 'Asignación guardada');
        return false;
    }
    const areas = [...new Set((contexto.areas || []).filter(a => AREAS_UI[a]))];
    const hayHorario = alternativasActuales.length > 0 || !!ultimo?.horario_id || !!horarioActualReferencia?.horario_id;
    if (!hayHorario) {
        toast('La asignación quedó guardada. Como el mes todavía no tiene horario, entrará automáticamente al crear el horario inicial.', 'info', 'Asignación lista');
        return false;
    }
    // Una asignación de GS no debe reconstruir COM y AC. Se encadenan solo las
    // áreas realmente afectadas y cada paso usa como base el resultado del
    // anterior. Si el alcance es todo el personal, sí corresponde recalcular
    // el horario completo.
    if (areas.length > 0 && areas.length < Object.keys(AREAS_UI).length) {
        let aplicada = true;
        for (const area of areas) aplicada = (await actualizarSoloArea(area)) && aplicada;
        return aplicada;
    }
    const {anio,mes}=periodo();
    setEstado('Actualizando el horario con la nueva asignación…','working');
    const generada=await api('/api/horarios/generar',{method:'POST',body:JSON.stringify({mes,anio,horario_id:ultimo?.horario_id || null})});
    if (!(generada.alternativas||[]).length) {
        respuestaGeneracion=generada;
        const diagnosticoAsignacion = generada.diagnostico || null;
        if (!ultimo?.horario?.length) ultimo = diagnosticoAsignacion;
        renderValidacion(diagnosticoAsignacion || {errores:['La asignación fue guardada, pero el horario necesita revisión.'],advertencias:[]});
        toast(
            'La asignación se guardó, pero no se pudo crear una opción válida automáticamente. '
            + (generada.mensaje || 'Revisa Validación o usa Modificar horario.'),
            'warning', 'Horario pendiente de revisión');
        return false;
    }
    await cargarOpcionesPeriodo(generada.alternativas[0]?.horario_id || null, generada.mensaje);
    setEstado('Horario actualizado','success',1400);
    return true;
}

$('form-requerimiento').onsubmit = async ev => {
    ev.preventDefault();
    const alcanceReq = $('requerimiento-alcance')?.value || 'persona';
    const tipoActualReq = $('requerimiento-tipo')?.value;
    const modoActualReq = $('requerimiento-modo-fechas')?.value;
    const extrasReq = [
        {id:'requerimiento-empleado', nombre:'Empleado', ok: alcanceReq !== 'persona' || !!$('requerimiento-empleado')?.value},
        {id:'requerimiento-area', nombre:'Área', ok: alcanceReq !== 'area' || !!$('requerimiento-area')?.value},
        {id:'requerimiento-inicio', nombre:'Fecha inicial', ok: !!$('requerimiento-inicio')?.value},
        {id:'requerimiento-fin', nombre:'Fecha final', ok: modoActualReq !== 'varios' || !!$('requerimiento-fin')?.value},
        {id:'g-requerimiento-dias-semana', nombre:'Día(s) habituales de la semana', ok: !(tipoActualReq === 'excepcion_turno' && modoActualReq === 'recurrente') || !!document.querySelector('.req-weekday:checked')},
        {id:'requerimiento-horario', nombre:'Horario de la actividad / asignación', ok: tipoActualReq === 'descanso_extra' || !!$('requerimiento-horario')?.value},
        {id:'requerimiento-reemplazo', nombre:'Persona que cubrirá PM', ok: $('g-requerimiento-reemplazo')?.classList.contains('hidden') || !!$('requerimiento-reemplazo')?.value},
    ];
    if (mostrarFaltantesFormulario($('form-requerimiento'), extrasReq)) return;
    try {
        const id = $('requerimiento-id').value;
        const actualizarHorarioAhora = $('requerimiento-actualizar-horario')?.value === 'si';
        const tipoReq = $('requerimiento-tipo').value;
        const inicio = $('requerimiento-inicio').value;
        const modoFechas = $('requerimiento-modo-fechas').value;
        const recurrenteIndefinido = tipoReq === 'excepcion_turno' && modoFechas === 'recurrente';
        const fin = modoFechas === 'varios' ? $('requerimiento-fin').value : inicio;
        const diasSemana = recurrenteIndefinido ? [...document.querySelectorAll('.req-weekday:checked')].map(x => Number(x.value)) : [];
        if (recurrenteIndefinido && !diasSemana.length) throw new Error('Selecciona al menos un día habitual de la semana.');
        const fechas = recurrenteIndefinido ? [] : fechasEntre(inicio, fin);
        const valorHorario = tipoReq === 'descanso_extra' ? null : $('requerimiento-horario').value;
        if (tipoReq !== 'descanso_extra' && !valorHorario) throw new Error('Selecciona el horario que se aplicará.');

        const objetivos = objetivosRequerimiento();
        if (!objetivos.length) throw new Error('No hay personal compatible con el alcance seleccionado.');
        const masivo = !id && ($('requerimiento-alcance')?.value || 'persona') !== 'persona';
        const esExcepcion = tipoReq === 'excepcion_turno';

        function horarioPara(e) {
            if (valorHorario !== 'ADM-AUTO') return valorHorario;
            return {
                gestion_social: 'ADM-GS',
                atencion_ciudadano: e.tipo_turno === 'administrativo' ? 'ADM-AC' : 'ADM-GS',
                comunicaciones: 'ADM-GS',
            }[e.area] || null;
        }

        function payloadPara(e) {
            const horario = horarioPara(e);
            const coberturaPermitida = !masivo && !esExcepcion && horario === 'ADM-GS' && !$('g-requerimiento-cobertura').classList.contains('hidden');
            const cubrir = coberturaPermitida && $('requerimiento-cobertura').value === 'si';
            const payload = {
                empleado_id: Number(e.id),
                tipo: tipoReq,
                fechas: [...fechas],
                recurrente_indefinido: recurrenteIndefinido,
                dias_semana: [...diasSemana],
                horario_administrativo: (!esExcepcion && tipoReq !== 'descanso_extra') ? horario : null,
                turno_excepcion: esExcepcion ? horario : null,
                cubrir_pm: cubrir,
                reemplazo_empleado_id: cubrir ? +$('requerimiento-reemplazo').value : null,
                descripcion: $('requerimiento-descripcion').value.trim(),
                vigente_desde: recurrenteIndefinido ? (inicio || ymd(new Date())) : (fechas[0] || null),
                estado: 'activo',
            };
            if (cubrir && !payload.reemplazo_empleado_id) throw new Error('Selecciona quién cubrirá PM.');
            return payload;
        }

        if (id) {
            const payload = payloadPara(objetivos[0]);
            await api('/api/requerimientos/' + id, {method:'PUT', body:JSON.stringify(payload)});
        } else if (!masivo) {
            const payload = payloadPara(objetivos[0]);
            const pre = await api('/api/requerimientos/prevalidar', {method:'POST',body:JSON.stringify(payload)});
            if (pre.tiene_conflictos) {
                const solucion = await elegirSolucionConflictos(pre);
                if (!solucion) return;
                if (solucion.accion === 'manual') {
                    document.querySelector('[data-tab="modificar"]').click();
                    toast('Carga la programación visible y realiza el ajuste exactamente en las celdas necesarias.', 'info', 'Resolución manual');
                    return;
                }
                if (solucion.accion === 'omitir') {
                    payload.fechas = solucion.fechas;
                    if (!payload.fechas.length) throw new Error('No quedaron fechas disponibles para guardar.');
                }
            }
            await api('/api/requerimientos', {method:'POST', body:JSON.stringify(payload)});
        } else {
            const basePayload = payloadPara(objetivos[0]);
            const alcanceMasivo = $('requerimiento-alcance')?.value || 'todos';
            const bulk = {empleado_ids: objetivos.map(x => Number(x.id)), requerimiento: basePayload, aplicar_solo_compatibles: false, permitir_conflictos_grupo: false, alcance: alcanceMasivo, area: alcanceMasivo === 'area' ? $('requerimiento-area').value : null};
            const pre = await api('/api/requerimientos/masivo/prevalidar', {method:'POST',body:JSON.stringify(bulk)});
            const bloqueadosIndividuales=(pre.resultados||[]).filter(x=>!x.compatible);
            if (bloqueadosIndividuales.length) {
                const problemas=bloqueadosIndividuales.map(x=>({nombre:x.empleado_nombre,mensaje:(x.conflictos||[]).map(c=>c.mensaje).join(' · '),fechas:(x.conflictos||[]).map(c=>c.fecha).filter(Boolean)}));
                const solucion=await elegirSolucionMasiva(problemas,pre.compatibles||0);
                if (!solucion) return;
                if (solucion.accion==='manual') { document.querySelector('[data-tab="modificar"]').click(); return; }
                if (solucion.accion!=='compatibles') return;
                bulk.aplicar_solo_compatibles=true;
            }
            if ((pre.conflictos_grupo||[]).length) {
                const detalle=(pre.conflictos_grupo||[]).map(c=>c.mensaje).join(' · ');
                const irManual=await confirmarUI({
                    titulo:'Esta asignación necesita una excepción manual',
                    mensaje:'Aplicarla al grupo completo rompería una regla operativa y no puede guardarse como una asignación normal.',
                    detalle:`${detalle} Si la decisión debe mantenerse, puedes ir a Modificar horario y autorizar el cambio con una justificación.`,
                    aceptar:'Ir a Modificar horario',
                    peligro:false,
                });
                if (irManual) document.querySelector('[data-tab="modificar"]')?.click();
                return;
            }
            const resultadoMasivo=await api('/api/requerimientos/masivo',{method:'POST',body:JSON.stringify(bulk)});
            toast(resultadoMasivo.mensaje, (resultadoMasivo.omitidos?.length || resultadoMasivo.conflictos_grupo_aceptados?.length) ? 'warning':'success','Asignación masiva');
        }

        limpiarErroresFormulario($('form-requerimiento'));
        $('form-requerimiento').reset();
        document.querySelectorAll('.req-weekday').forEach(x => x.checked = false);
        $('requerimiento-id').value = '';
        $('requerimiento-alcance').value = 'persona';
        configurarHorarioRequerimiento();
        sincronizarSelectoresFecha();
        await cargarRequerimientos();
        await cargarEstadoPeriodo();
        actualizarAccionGenerar();
        cerrarEditorFormulario();
        if (actualizarHorarioAhora) {
            await actualizarHorarioActualTrasAsignacion({
                fechas,
                recurrente:recurrenteIndefinido,
                vigenteDesde:inicio,
                areas:[...new Set(objetivos.map(x => x.area))],
            });
        }
        if (!masivo) {
            toast(
                tipoReq === 'actividad'
                    ? `Actividad asignada para ${fechas.length} día(s). El motor impedirá descanso automático en esas fechas.`
                    : tipoReq === 'excepcion_turno'
                        ? (recurrenteIndefinido ? `Excepción ${valorHorario} habitual guardada. Se aplicará cada semana hasta que la elimines.` : `Excepción ${valorHorario} guardada para ${fechas.length} fecha(s).`)
                        : 'El ajuste directo quedó guardado y activo.',
                'success', 'Requerimiento guardado'
            );
        }
    } catch (e) {
        mostrarAlertaFormulario($('form-requerimiento'), e.message, 'No se pudo guardar');
        toast(e.message, 'error', 'No se pudo guardar');
    }
};

$('cancelar-requerimiento').onclick = () => {
    cerrarEditorFormulario();
    limpiarErroresFormulario($('form-requerimiento'));
    $('form-requerimiento').reset();
    document.querySelectorAll('.req-weekday').forEach(x => x.checked = false);
    $('requerimiento-id').value = '';
    $('requerimiento-alcance').value = 'persona';
    configurarHorarioRequerimiento();
    sincronizarSelectoresFecha();
};
['cambio-turno-tipo','cambio-turno-empleado','cambio-turno-fecha'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('change', camposCambioTurno);
});
document.getElementById('form-cambio-turno')?.addEventListener('submit', guardarCambioTurno);
document.getElementById('regla-racha-guardar')?.addEventListener('click', function () { guardarReglaRacha(this); });

['requerimiento-alcance','requerimiento-area','requerimiento-empleado','requerimiento-tipo','requerimiento-horario','requerimiento-modo-fechas','requerimiento-cobertura','requerimiento-inicio','requerimiento-fin']
    .forEach(id => { if ($(id)) $(id).onchange = configurarHorarioRequerimiento; });


document.querySelectorAll('[data-days]').forEach(btn => btn.onclick = () => aplicarFinPorDias('solicitud-inicio','solicitud-fin',btn.dataset.days));
document.querySelectorAll('[data-req-days]').forEach(btn => btn.onclick = () => aplicarFinPorDias('requerimiento-inicio','requerimiento-fin',btn.dataset.reqDays));
document.querySelectorAll('.req-weekday').forEach(x => x.onchange = configurarHorarioRequerimiento);

if ($('eliminar-solicitudes-vencidas')) $('eliminar-solicitudes-vencidas').onclick = () => irAHistorial('solicitud');
if ($('eliminar-requerimientos-vencidos')) $('eliminar-requerimientos-vencidos').onclick = () => irAHistorial('requerimiento');
if ($('eliminar-solicitudes-finalizadas')) $('eliminar-solicitudes-finalizadas').onclick = async () => {
    const ok=await confirmarUI({titulo:'Eliminar solicitudes finalizadas',mensaje:'¿Eliminar únicamente las solicitudes que ya se cumplieron?',detalle:'No se eliminarán solicitudes canceladas, rechazadas ni pendientes vencidas.',aceptar:'Eliminar finalizadas',peligro:true});
    if (!ok) return;
    try { const d=await api('/api/solicitudes/finalizadas',{method:'DELETE'}); await cargarSolicitudes(); toast(d.mensaje,'success','Finalizadas eliminadas'); } catch(e) { toast(e.message,'error','No se pudieron eliminar'); }
};
if ($('eliminar-requerimientos-finalizados')) $('eliminar-requerimientos-finalizados').onclick = async () => {
    const ok=await confirmarUI({titulo:'Eliminar asignaciones finalizadas',mensaje:'¿Eliminar únicamente las asignaciones que ya se cumplieron?',detalle:'Las canceladas permanecen en Historial y las habitualidades activas no se eliminan.',aceptar:'Eliminar finalizadas',peligro:true});
    if (!ok) return;
    try { const d=await api('/api/requerimientos/finalizados',{method:'DELETE'}); await cargarRequerimientos(); toast(d.mensaje,'success','Finalizadas eliminadas'); } catch(e) { toast(e.message,'error','No se pudieron eliminar'); }
};

function candidatosIntercambio() {
    const e = empleados.find(x => x.id === +$('solicitud-empleado').value);
    if (!e || e.tipo_turno === 'administrativo') return [];
    return empleados.filter(x =>
        x.id !== e.id &&
        x.area === e.area &&
        x.tipo_turno !== 'administrativo'
    );
}
