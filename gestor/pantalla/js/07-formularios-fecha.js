// Fechas, semanas y el formulario de solicitud
// ---------------------------------------------------------------------------
// Parte de la pantalla del Gestor de Horarios. Los archivos de esta carpeta se
// cargan en orden y comparten el mismo ámbito, así que juntos son exactamente
// el app.js de antes. Ver frontend/js/LEEME.md.

'use strict';

function ymd(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
}

function fechaLocal(iso) {
    const [y,m,d] = iso.split('-').map(Number);
    return new Date(y, m - 1, d, 12, 0, 0);
}

function sumarDiasIso(iso, dias) {
    const d = fechaLocal(iso);
    d.setDate(d.getDate() + Number(dias));
    return ymd(d);
}

function mesActualFormulario() {
    return $('periodo').value || ymd(new Date()).slice(0,7);
}

function etiquetaFechaCorta(date) {
    const meses = ['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'];
    return `${date.getDate()} ${meses[date.getMonth()]}`;
}

function semanasDelMes(valorMes) {
    const match = /^(\d{4})-(\d{2})$/.exec(valorMes || '');
    if (!match) return [];
    const anio = Number(match[1]);
    const mes = Number(match[2]) - 1;
    const primero = new Date(anio, mes, 1, 12);
    const ultimoDia = new Date(anio, mes + 1, 0, 12);
    const lunes = new Date(primero);
    const delta = (lunes.getDay() + 6) % 7; // JS domingo=0; lunes=1
    lunes.setDate(lunes.getDate() - delta);

    // Agosto de 2026 es el mes base: la operación empieza el día 1 y no hay
    // nada antes, ni se desborda a la semana de septiembre. Es la misma regla
    // que aplica el servidor al calcular el período del mes base. Sin esto,
    // agosto ofrecía «Semana 1 · Lun 27 jul», una fecha de julio en una
    // aplicación que no trabaja con julio, y una sexta semana que ya es de
    // septiembre.
    //
    // El lunes real se conserva como identificador —es la clave con la que se
    // guarda el cierre de cada semana, aquí y en el servidor—: lo que se
    // recorta es lo que se enseña.
    const esMesBase = `${anio}-${String(mes + 1).padStart(2, '0')}` === PERIODO_MINIMO;
    const arranque = fechaLocal(INICIO_OPERACION_ISO);

    const out = [];
    const cursor = new Date(lunes);
    let numero = 1;
    while (cursor <= ultimoDia) {
        const domingo = new Date(cursor);
        domingo.setDate(domingo.getDate() + 6);
        const desde = (esMesBase && cursor < arranque) ? new Date(arranque) : new Date(cursor);
        const hasta = (esMesBase && domingo > ultimoDia) ? new Date(ultimoDia) : new Date(domingo);
        const texto = ymd(desde) === ymd(hasta)
            ? `Semana ${numero} · Solo el ${etiquetaFechaCorta(desde)}`
            : `Semana ${numero} · `
                + (desde.getDay() === 1 ? `Lun ${etiquetaFechaCorta(desde)}` : `Desde ${etiquetaFechaCorta(desde)}`)
                + ' – '
                + (hasta.getDay() === 0 ? `Dom ${etiquetaFechaCorta(hasta)}` : `hasta ${etiquetaFechaCorta(hasta)}`);
        out.push({
            lunes: ymd(cursor),
            // El domingo se publica porque hay pantallas que buscan en qué
            // semana cae una fecha; antes no venía y esa búsqueda no encontraba
            // nunca ninguna.
            domingo: ymd(domingo),
            texto,
        });
        cursor.setDate(cursor.getDate() + 7);
        numero += 1;
    }
    return out;
}

function actualizarSemanasSolicitud() {
    const input = $('solicitud-semana-periodo');
    if (!input.value) input.value = mesActualFormulario();
    const current = $('solicitud-semana').value;
    const semanas = semanasDelMes(input.value);
    $('solicitud-semana').innerHTML = semanas
        .map(x => `<option value="${x.lunes}">${esc(x.texto)}</option>`)
        .join('');
    if (semanas.some(x => x.lunes === current)) $('solicitud-semana').value = current;
}

function actualizarSemanasCambioTemporal() {
    const periodo = $('solicitud-rango-semana-periodo');
    if (!periodo.value) periodo.value = mesActualFormulario();
    const semanas = semanasDelMes(periodo.value);
    const ini = $('solicitud-rango-semana-inicio').value;
    const fin = $('solicitud-rango-semana-fin').value;
    const html = semanas.map(x => `<option value="${x.lunes}">${esc(x.texto)}</option>`).join('');
    $('solicitud-rango-semana-inicio').innerHTML = html;
    $('solicitud-rango-semana-fin').innerHTML = html;
    if (semanas.some(x => x.lunes === ini)) $('solicitud-rango-semana-inicio').value = ini;
    if (semanas.some(x => x.lunes === fin)) $('solicitud-rango-semana-fin').value = fin;
    if (!$('solicitud-rango-semana-inicio').value && semanas.length) $('solicitud-rango-semana-inicio').value = semanas[0].lunes;
    if (!$('solicitud-rango-semana-fin').value && semanas.length) $('solicitud-rango-semana-fin').value = semanas[semanas.length-1].lunes;
}

function camposSolicitud() {
    const t = $('solicitud-tipo').value;
    const cap = t === 'capacitacion';
    const esAdmGs = t === 'asignacion_adm_gs';
    const cov = ['vacaciones','incapacidad','permiso','capacitacion'].includes(t) || esAdmGs;
    const one = ['descanso_extra','cambio_am','cambio_pm','cambio_pareja','cambio_persona','asignacion_adm_gs'].includes(t);
    const esDescanso = t === 'descanso';
    const intercambio = t === 'cambio_persona';
    const turnoDia = t === 'turno_dia';
    const turnoSemanas = t === 'turno_semanas';
    const requiereTurno = turnoDia || turnoSemanas;
    const modoTurno = $('solicitud-turno-modo').value || 'rango';
    const turnoSemanal = turnoDia && modoTurno === 'semanal';
    const admiteDuracion = ['vacaciones','incapacidad','permiso','capacitacion'].includes(t);
    const modoGeneral = $('solicitud-modo-fechas-general')?.value || 'uno';

    $('g-hi').classList.toggle('hidden', !cap);
    $('g-hf').classList.toggle('hidden', !cap);
    $('g-cobertura').classList.toggle('hidden', !cov);
    $('g-intercambio').classList.toggle('hidden', !intercambio);
    $('g-turno-dia').classList.toggle('hidden', !requiereTurno);
    $('g-turno-modo').classList.toggle('hidden', !turnoDia);
    $('g-turno-periodo').classList.add('hidden');
    $('g-turno-semanal-dia').classList.toggle('hidden', !turnoSemanal);
    $('g-rango-semana-periodo').classList.toggle('hidden', !turnoSemanas);
    $('g-rango-semana-inicio').classList.toggle('hidden', !turnoSemanas);
    $('g-rango-semana-fin').classList.toggle('hidden', !turnoSemanas);
    $('g-semana-periodo').classList.toggle('hidden', !esDescanso);
    $('g-semana').classList.toggle('hidden', !esDescanso);
    $('g-dia-descanso').classList.toggle('hidden', !esDescanso);
    $('g-solicitud-modo-fechas-general').classList.toggle('hidden', !admiteDuracion);

    const mostrarFechas = !esDescanso && !turnoSemanal && !turnoSemanas;
    const mostrarFin = mostrarFechas && ((admiteDuracion && modoGeneral === 'rango') || (turnoDia && !turnoSemanal));
    $('g-fecha-inicio').classList.toggle('hidden', !mostrarFechas);
    $('g-fecha-fin').classList.toggle('hidden', !mostrarFin);
    $('solicitud-inicio').disabled = !mostrarFechas;
    $('solicitud-fin').disabled = !mostrarFechas;

    if (!cov) $('solicitud-cobertura').value = 'sin_cubrir';
    $('g-reemplazo').classList.toggle('hidden', !cov || $('solicitud-cobertura').value !== 'reemplazar');

    if (mostrarFechas && (one || !mostrarFin)) {
        $('solicitud-fin').value = $('solicitud-inicio').value;
        $('solicitud-fin').disabled = true;
    } else if (mostrarFin) {
        $('solicitud-fin').disabled = false;
    }
    actualizarResumenFechas();

    $('texto-fecha-inicio').textContent = turnoDia && modoTurno === 'rango' ? 'Inicio del cambio' : 'Inicio';

    if (esDescanso) actualizarSemanasSolicitud();
    if (turnoSemanal) $('solicitud-turno-periodo').value = '';
    if (turnoSemanas) {
        if (!$('solicitud-rango-semana-periodo').value) $('solicitud-rango-semana-periodo').value = mesActualFormulario();
        actualizarSemanasCambioTemporal();
    }

    const e = empleados.find(x => x.id === +$('solicitud-empleado').value);
    $('solicitud-reemplazo').innerHTML = opts(
        e ? empleados.filter(x => x.id !== e.id && x.area === e.area && x.tipo_turno !== 'administrativo') : [],
        'Seleccionar reemplazo'
    );
    $('solicitud-intercambio').innerHTML = opts(candidatosIntercambio(), 'Seleccionar persona');

    const coberturaSelect = $('solicitud-cobertura');
    const coberturaLabel = $('texto-cobertura-label');
    const coberturaAyuda = $('texto-cobertura-ayuda');
    if (esAdmGs) {
        const valorActual = coberturaSelect.value || 'sin_cubrir';
        coberturaLabel.textContent = '¿Necesita cobertura PM?';
        coberturaSelect.innerHTML = `
            <option value="sin_cubrir">No · ADM-GS conserva la cobertura PM</option>
            <option value="reemplazar">Sí · cubrir PM con otra persona</option>`;
        coberturaSelect.value = ['sin_cubrir','reemplazar'].includes(valorActual) ? valorActual : 'sin_cubrir';

        const fecha = $('solicitud-inicio').value;
        const visible = ultimo?.horario?.find(x => Number(x.empleado_id) === Number(e?.id))?.dias?.find(x => x.fecha === fecha);
        let preguntarCobertura = !visible; // Si aún no hay horario visible, se ofrece la decisión por seguridad.
        let detalle = 'Una jornada administrativa suele ocupar el turno de mañana. Si ese día todavía no tiene horario, puedes dejar dicho desde ya quién quieres que cubra la tarde.';

        if (visible?.turno === 'AM') {
            preguntarCobertura = false;
            coberturaSelect.value = 'sin_cubrir';
            detalle = 'La programación visible muestra AM: ADM-GS sustituirá esa cobertura AM y el turno PM quedará intacto.';
        } else if (visible?.turno === 'PM') {
            const filaGs = ultimo?.horario?.filter(x => x.area === 'gestion_social') || [];
            const otrosPm = filaGs
                .filter(x => Number(x.empleado_id) !== Number(e?.id))
                .filter(x => {
                    const dia = x.dias?.find(d => d.fecha === fecha);
                    return dia?.turno === 'PM' || (dia?.turno === 'ADM-GS' && dia?.cobertura_operativa === 'PM');
                }).length;
            preguntarCobertura = otrosPm < 1;
            if (preguntarCobertura) {
                detalle = 'Esta persona es la única cobertura PM visible. Si eliges “Sí”, selecciona quién quedará PM; si eliges “No”, ADM-GS conservará la cobertura PM de ese día.';
            } else {
                coberturaSelect.value = 'sin_cubrir';
                detalle = 'Ya existe otra cobertura PM. ADM-GS sustituirá AM y no es necesario seleccionar reemplazo.';
            }
        }

        $('g-cobertura').classList.toggle('hidden', !preguntarCobertura);
        coberturaAyuda.textContent = detalle;
        if (!preguntarCobertura) $('g-reemplazo').classList.add('hidden');
    } else {
        coberturaLabel.textContent = 'Cobertura';
        const valorActual = coberturaSelect.value || 'sin_cubrir';
        coberturaSelect.innerHTML = `
            <option value="sin_cubrir">Sin cubrir</option>
            <option value="reemplazar">Reemplazar</option>`;
        coberturaSelect.value = ['sin_cubrir','reemplazar'].includes(valorActual) ? valorActual : 'sin_cubrir';
        coberturaAyuda.textContent = cov ? 'Si eliges reemplazar, la persona seleccionada cambia temporalmente de turno sin hacer doble jornada.' : '';
    }
    const admCoberturaVisible = !esAdmGs || !$('g-cobertura').classList.contains('hidden');
    $('g-reemplazo').classList.toggle('hidden', !cov || !admCoberturaVisible || coberturaSelect.value !== 'reemplazar');
    actualizarPasosVisibles();
}

$('form-solicitud').onsubmit = async ev => {
    ev.preventDefault();
    const tipoSolicitudActual = $('solicitud-tipo')?.value;
    const extrasSolicitud = [
        {id:'solicitud-empleado', nombre:'Empleado', ok: !!$('solicitud-empleado')?.value},
        {id:'solicitud-intercambio', nombre:'Persona para intercambio', ok: tipoSolicitudActual !== 'cambio_persona' || !!$('solicitud-intercambio')?.value},
        {id:'solicitud-semana', nombre:'Semana a modificar', ok: tipoSolicitudActual !== 'descanso' || !!$('solicitud-semana')?.value},
        {id:'solicitud-rango-semana-inicio', nombre:'Semana inicial', ok: tipoSolicitudActual !== 'turno_semanas' || !!$('solicitud-rango-semana-inicio')?.value},
        {id:'solicitud-rango-semana-fin', nombre:'Semana final', ok: tipoSolicitudActual !== 'turno_semanas' || !!$('solicitud-rango-semana-fin')?.value},
        {id:'solicitud-inicio', nombre:'Fecha inicial', ok: ['descanso','turno_semanas'].includes(tipoSolicitudActual) || ($('solicitud-turno-modo')?.value === 'semanal' && tipoSolicitudActual === 'turno_dia') || !!$('solicitud-inicio')?.value},
        {id:'solicitud-fin', nombre:'Fecha final', ok: $('g-fecha-fin')?.classList.contains('hidden') || !!$('solicitud-fin')?.value},
        {id:'solicitud-reemplazo', nombre:'Reemplazo', ok: $('g-reemplazo')?.classList.contains('hidden') || !!$('solicitud-reemplazo')?.value},
        {id:'solicitud-hi', nombre:'Hora de inicio', ok: tipoSolicitudActual !== 'capacitacion' || !!$('solicitud-hi')?.value},
        {id:'solicitud-hf', nombre:'Hora de finalización', ok: tipoSolicitudActual !== 'capacitacion' || !!$('solicitud-hf')?.value},
    ];
    if (mostrarFaltantesFormulario($('form-solicitud'), extrasSolicitud)) return;

    const id = $('solicitud-id').value;
    const t = $('solicitud-tipo').value;
    const cov = ['vacaciones','incapacidad','permiso','capacitacion','asignacion_adm_gs'].includes(t);
    const modo = cov ? $('solicitud-cobertura').value : 'sin_cubrir';

    let fechaInicio = $('solicitud-inicio').value;
    let fechaFin = $('solicitud-fin').value || fechaInicio;
    let modoPeriodo = 'rango';
    let diaRecurrente = null;
    let sinFechaFin = false;

    if (t === 'descanso') {
        const lunes = $('solicitud-semana').value;
        if (!lunes) throw new Error('Selecciona la semana que deseas modificar.');
        fechaInicio = sumarDiasIso(lunes, +$('solicitud-dia-descanso').value);
        fechaFin = fechaInicio;
    } else if (t === 'turno_dia') {
        modoPeriodo = $('solicitud-turno-modo').value;
        if (modoPeriodo === 'semanal') {
            fechaInicio = ymd(new Date());
            fechaFin = fechaInicio;
            sinFechaFin = true;
            diaRecurrente = +$('solicitud-turno-semanal-dia').value;
        } else {
            if (!fechaInicio) throw new Error('Selecciona la fecha inicial del cambio.');
            if (!fechaFin) fechaFin = fechaInicio;
            const dias = Math.round((fechaLocal(fechaFin) - fechaLocal(fechaInicio)) / 86400000) + 1;
            if (dias < 1 || dias > 3) throw new Error('El cambio de turno por rango debe cubrir entre 1 y 3 días consecutivos.');
        }
    } else if (t === 'turno_semanas') {
        const inicioSemana = $('solicitud-rango-semana-inicio').value;
        const finSemana = $('solicitud-rango-semana-fin').value;
        if (!inicioSemana || !finSemana) throw new Error('Selecciona la semana inicial y la semana final.');
        fechaInicio = inicioSemana;
        fechaFin = sumarDiasIso(finSemana, 6);
        if (fechaLocal(fechaFin) < fechaLocal(fechaInicio)) throw new Error('La semana final no puede ser anterior a la inicial.');
    } else if (['descanso_extra','cambio_am','cambio_pm','cambio_pareja','cambio_persona','asignacion_adm_gs'].includes(t)) {
        fechaFin = fechaInicio;
    } else if (['vacaciones','incapacidad','permiso','capacitacion'].includes(t) && $('solicitud-modo-fechas-general').value === 'uno') {
        fechaFin = fechaInicio;
    }

    const d = {
        empleado_id: +$('solicitud-empleado').value,
        tipo: t,
        fecha_inicio: fechaInicio,
        fecha_fin: fechaFin,
        hora_inicio: t === 'capacitacion' ? $('solicitud-hi').value : null,
        hora_fin: t === 'capacitacion' ? $('solicitud-hf').value : null,
        modo_cobertura: modo,
        reemplazo_empleado_id: modo === 'reemplazar' && $('solicitud-reemplazo').value ? +$('solicitud-reemplazo').value : null,
        intercambio_empleado_id: t === 'cambio_persona' && $('solicitud-intercambio').value ? +$('solicitud-intercambio').value : null,
        dia_descanso_solicitado: t === 'descanso' ? +$('solicitud-dia-descanso').value : null,
        turno_solicitado: ['turno_dia','turno_semanas'].includes(t) ? $('solicitud-turno-dia').value : null,
        modo_periodo: t === 'turno_dia' ? modoPeriodo : 'rango',
        dia_semana_recurrente: t === 'turno_dia' && modoPeriodo === 'semanal' ? diaRecurrente : null,
        sin_fecha_fin: sinFechaFin,
        aprobada: $('solicitud-aprobada').checked,
        observacion: $('solicitud-observacion').value.trim(),
    };

    try {
        await api(id ? '/api/solicitudes/' + id : '/api/solicitudes', {
            method: id ? 'PUT' : 'POST',
            body: JSON.stringify(d),
        });
        limpiarErroresFormulario($('form-solicitud'));
        $('form-solicitud').reset();
        $('solicitud-id').value = '';
        $('solicitud-semana-periodo').value = mesActualFormulario();
        $('solicitud-turno-periodo').value = mesActualFormulario();
        $('solicitud-rango-semana-periodo').value = mesActualFormulario();
        camposSolicitud();
        sincronizarSelectoresFecha();
        await cargarSolicitudes();
        await cargarEstadoPeriodo();
        actualizarAccionGenerar();
        toast('La solicitud fue guardada correctamente.', 'success', 'Solicitud guardada');
    } catch (e) {
        mostrarAlertaFormulario($('form-solicitud'), e.message, 'No se pudo guardar la solicitud');
        toast(e.message, 'error', 'No se pudo guardar la solicitud');
    }
};

[
    'solicitud-tipo','solicitud-inicio','solicitud-fin','solicitud-cobertura',
    'solicitud-empleado','solicitud-turno-modo','solicitud-semana-periodo','solicitud-rango-semana-periodo',
    'solicitud-turno-periodo','solicitud-modo-fechas-general','solicitud-inicio','solicitud-fin'
].forEach(id => $(id).onchange = () => {
    if (id === 'solicitud-semana-periodo') actualizarSemanasSolicitud();
    if (id === 'solicitud-rango-semana-periodo') actualizarSemanasCambioTemporal();
    camposSolicitud();
});

$('cancelar-solicitud').onclick = () => {
    limpiarErroresFormulario($('form-solicitud'));
    $('form-solicitud').reset();
    $('solicitud-id').value = '';
    $('solicitud-semana-periodo').value = mesActualFormulario();
    $('solicitud-turno-periodo').value = mesActualFormulario();
    $('solicitud-rango-semana-periodo').value = mesActualFormulario();
    actualizarSemanasCambioTemporal();
    camposSolicitud();
    sincronizarSelectoresFecha();
};

window.aprobar = async id => {
    try {
        const pre = await api(`/api/solicitudes/${id}/prevalidar`);
        if (!pre.compatible) {
            const detalle=(pre.conflictos||[]).map(c=>`${c.fecha ? c.fecha + ': ' : ''}${c.mensaje}`).join('\n');
            toast(detalle || 'La solicitud tiene conflictos que deben resolverse antes de aprobarla.', 'warning', 'Prevalidación de solicitud');
            return;
        }
        await api(`/api/solicitudes/${id}/aprobar`, {method: 'PATCH'});
        await cargarSolicitudes(); await cargarEstadoPeriodo();
        toast('La solicitud ya será tenida en cuenta al generar el horario.', 'success', 'Solicitud aprobada');
    } catch (e) {
        toast(e.message, 'error', 'No se pudo aprobar');
    }
};

window.rechazar = async id => {
    try {
        await api(`/api/solicitudes/${id}/rechazar`, {method: 'PATCH'});
        await cargarSolicitudes(); await cargarEstadoPeriodo();
        toast('La solicitud fue rechazada y se conservará en el historial.', 'info', 'Solicitud rechazada');
    } catch (e) {
        toast(e.message, 'error', 'No se pudo actualizar');
    }
};

window.cancelarSolicitud = async id => {
    const s = solicitudes.find(x => Number(x.id) === Number(id));
    const ok = await confirmarUI({
        titulo:'Cancelar solicitud',
        mensaje:'¿Esta solicitud finalmente no se realizará?',
        detalle:`${s?.empleado_nombre || ''}${s ? ' · ' + nombreSolicitud(s.tipo) : ''}. Quedará registrada como cancelada en Historial y, si estaba aprobada, se retirará del horario al regenerar.`,
        aceptar:'Cancelar solicitud', peligro:false,
    });
    if (!ok) return;
    try {
        await api(`/api/solicitudes/${id}/cancelar`, {method:'PATCH'});
        await cargarSolicitudes(); await cargarEstadoPeriodo();
        toast('La solicitud fue cancelada y se conserva en el historial.', 'success', 'Solicitud cancelada');
    } catch (e) { toast(e.message,'error','No se pudo cancelar'); }
};


window.borrarSolicitud = async id => {
    const solicitud = solicitudes.find(x => x.id === id);
    const ok = await confirmarUI({
        titulo: 'Eliminar solicitud',
        mensaje: `¿Quieres eliminar la solicitud ${solicitud ? nombreSolicitud(solicitud.tipo) : ''}?`,
        detalle: solicitud ? `${solicitud.empleado_nombre} · ${solicitud.fecha_inicio}${solicitud.fecha_fin !== solicitud.fecha_inicio ? ' a ' + solicitud.fecha_fin : ''}. Se borrará también del historial; usa Cancelar si la solicitud sí existía pero finalmente no se realizará.` : '',
        aceptar: 'Eliminar definitivamente',
        peligro: true,
    });
    if (!ok) return;
    try {
        const data = await api('/api/solicitudes/' + id, {method: 'DELETE'});
        await cargarSolicitudes(); await cargarEstadoPeriodo();
        toast(data.mensaje || 'La solicitud fue eliminada.', 'success', 'Solicitud eliminada');
    } catch (e) {
        toast(e.message, 'error', 'No se pudo eliminar');
    }
};
