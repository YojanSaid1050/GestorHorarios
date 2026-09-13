// Modificar el horario: semanas, cambios a mano, reprogramar
// ---------------------------------------------------------------------------
// Parte de la pantalla del Gestor de Horarios. Los archivos de esta carpeta se
// cargan en orden y comparten el mismo ámbito, así que juntos son exactamente
// el app.js de antes. Ver frontend/js/LEEME.md.

'use strict';

// ================================================================
// V10.8 · Reprogramación parcial y modificación manual asistida
// ================================================================
let semanasEstadoActual = [];

function semanasEditablesModificar() {
    const semanasMes = semanasDelMes($('periodo').value);
    if (!semanasEstadoActual.length) return semanasMes;
    const estado = new Map(semanasEstadoActual.map(s => [s.lunes, !!s.bloqueada]));
    return semanasMes.filter(s => !estado.get(s.lunes));
}

function semanaCerradaDeFecha(fechaIso) {
    // En modo rango las semanas cerradas ni se ofrecen, pero en «Solo este día»
    // el calendario deja elegir cualquier fecha del mes. Sin esto, la celda de
    // una semana cerrada salía editable, se podía cambiar y el rechazo solo
    // llegaba al pulsar el botón, sin decir por qué.
    if (!fechaIso || !semanasEstadoActual.length) return null;
    const lunes = rangoSemanaDeFecha(fechaIso).inicio;
    return semanasEstadoActual.find(s => s.lunes === lunes && s.bloqueada) || null;
}

function actualizarSemanasFinModificar() {
    const inicio = $('modificar-semana-inicio')?.value;
    const semanas = semanasEditablesModificar();
    const idx = semanas.findIndex(x => x.lunes === inicio);
    let disponibles = idx >= 0 ? [semanas[idx]] : [];
    if (idx >= 0) {
        for (let i = idx + 1; i < semanas.length; i++) {
            const anterior = fechaLocal(semanas[i - 1].lunes);
            anterior.setDate(anterior.getDate() + 7);
            if (ymd(anterior) !== semanas[i].lunes) break;
            disponibles.push(semanas[i]);
        }
    }
    const finActual = $('modificar-semana-fin')?.value;
    $('modificar-semana-fin').innerHTML = disponibles
        .map(x => `<option value="${x.lunes}">${esc(x.texto)}</option>`).join('');
    if (disponibles.some(x => x.lunes === finActual)) $('modificar-semana-fin').value = finActual;
    else if (disponibles.length) $('modificar-semana-fin').value = disponibles[disponibles.length - 1].lunes;
}

function actualizarSemanasModificar() {
    const semanas = semanasEditablesModificar();
    const iniActual = $('modificar-semana-inicio')?.value;
    $('modificar-semana-inicio').innerHTML = semanas
        .map(x => `<option value="${x.lunes}">${esc(x.texto)}</option>`).join('');
    if (semanas.some(x => x.lunes === iniActual)) $('modificar-semana-inicio').value = iniActual;
    else if (semanas.length) $('modificar-semana-inicio').value = semanas[0].lunes;
    actualizarSemanasFinModificar();

    const sinSemanas = semanas.length === 0;
    $('modificar-semana-inicio').disabled = sinSemanas;
    $('modificar-semana-fin').disabled = sinSemanas;
    $('reprogramar-parcial').disabled = sinSemanas;
    $('cargar-editor-manual').disabled = sinSemanas || !ultimo?.horario?.length;
    if ($('cargar-horario-oficial-modificar')) $('cargar-horario-oficial-modificar').disabled = sinSemanas || !horarioActualReferencia?.horario?.length;
    if (sinSemanas) {
        $('editor-manual-info').textContent = 'Todas las semanas de este mes están cerradas. Habilita una semana en Horario para poder modificarla.';
    } else if (!ultimo?.horario?.length) {
        $('editor-manual-info').textContent = 'Primero genera o abre una programación.';
    }
}

function usarHorarioParaModificar(fuente) {
    const elegido = fuente === 'oficial' ? horarioActualReferencia : ultimo;
    if (!elegido?.horario?.length) {
        toast(fuente === 'oficial' ? 'Todavía no hay un horario oficial para este período.' : 'Primero crea o selecciona una programación.', 'warning', 'Horario no disponible');
        return;
    }
    ultimo = elegido;
    renderHorario(ultimo);
    renderValidacion(ultimo);
    renderAlternativas(respuestaGeneracion);
    actualizarDisponibilidadExportacion();
    renderEditorManual();
    $('editor-manual-info').textContent = fuente === 'oficial'
        ? 'Se cargó el horario oficial. Los cambios manuales se prepararán sobre esta versión.'
        : 'Se cargó la programación visible. Los cambios manuales se prepararán sobre esta versión.';
    toast(fuente === 'oficial' ? 'El horario oficial está listo para editar.' : 'La programación visible está lista para editar.', 'info', 'Fuente cargada');
}

function domingoDeLunes(lunesIso) {
    const d = fechaLocal(lunesIso);
    d.setDate(d.getDate() + 6);
    return ymd(d);
}

function rangoModificacion() {
    const inicio = $('modificar-semana-inicio').value;
    const finLunes = $('modificar-semana-fin').value;
    if (!inicio || !finLunes) throw new Error('Selecciona la semana inicial y la semana final.');
    const fin = domingoDeLunes(finLunes);
    if (fin < inicio) throw new Error('La semana final no puede ser anterior a la inicial.');
    return {inicio, fin};
}

function empleadoModificacionId() {
    if ($('modificar-alcance').value !== 'persona') return null;
    const id = Number($('modificar-persona').value || 0);
    if (!id) throw new Error('Selecciona la persona que deseas modificar.');
    return id;
}

function modoManualSoloDia() { return ($('manual-modo')?.value || 'dia') === 'dia'; }

function fechaManualSeleccionada() {
    const valor=$('manual-fecha')?.value || '';
    if (!valor) throw new Error('Selecciona la fecha que deseas modificar.');
    if (valor < FECHA_MINIMA) throw new Error('La programación comienza el 1 de agosto de 2026.');
    const mesVisible=$('periodo')?.value || '';
    if (!valor.startsWith(mesVisible+'-')) throw new Error('La fecha debe pertenecer al mes que estás viendo.');
    return valor;
}

function rangoSemanaDeFecha(fechaIso) {
    const d=fechaLocal(fechaIso);
    const delta=(d.getDay()+6)%7;
    d.setDate(d.getDate()-delta);
    const inicio=ymd(d);
    d.setDate(d.getDate()+6);
    return {inicio,fin:ymd(d)};
}

function diasVisiblesManual() {
    if (!ultimo?.horario?.length) return [];
    if (modoManualSoloDia()) {
        const fecha=fechaManualSeleccionada();
        return ultimo.horario[0].dias.filter(d=>d.fecha===fecha);
    }
    const {inicio, fin} = rangoModificacion();
    return ultimo.horario[0].dias.filter(d => d.fecha >= inicio && d.fecha <= fin);
}

function filasVisiblesManual() {
    if (!ultimo?.horario?.length) return [];
    if (modoManualSoloDia()) {
        const id=Number($('manual-persona')?.value || 0);
        // La carga/refresco de Personal y Horario puede ocurrir antes de que
        // el operador haya elegido una persona. Nunca debe romper otra acción
        // (por ejemplo, Generar horario) por una validación exclusiva del
        // editor manual: en ese caso el editor queda vacío y muestra ayuda.
        if (!id) return [];
        return ultimo.horario.filter(e=>Number(e.empleado_id)===id);
    }
    if ($('modificar-alcance').value === 'areas') {
        const areas = [...document.querySelectorAll('.manual-area:checked')].map(x => x.value);
        return areas.length ? ultimo.horario.filter(e => areas.includes(e.area)) : [];
    }
    if ($('modificar-alcance').value !== 'persona') return ultimo.horario;
    const id = Number($('modificar-persona').value || 0);
    return ultimo.horario.filter(e => Number(e.empleado_id) === id);
}

function renderEditorManual() {
    const tabla = $('tabla-manual');
    const semanasEditables = semanasEditablesModificar();
    if (!semanasEditables.length) {
        tabla.innerHTML = '<tbody><tr><td><div class="manual-locked-note">No hay semanas habilitadas para modificar en este mes. Las semanas cerradas no se muestran en el editor.</div></td></tr></tbody>';
        $('aplicar-manual').disabled = true;
        $('descartar-manual').disabled = true;
        return;
    }
    if (!ultimo?.horario?.length) {
        tabla.innerHTML = '<tbody><tr><td>Primero genera o selecciona una programación.</td></tr></tbody>';
        $('aplicar-manual').disabled = true;
        $('descartar-manual').disabled = true;
        return;
    }
    if (modoManualSoloDia()) {
        let fechaElegida = null;
        try { fechaElegida = fechaManualSeleccionada(); } catch (e) { fechaElegida = null; }
        const cerrada = semanaCerradaDeFecha(fechaElegida);
        if (cerrada) {
            tabla.innerHTML = `<tbody><tr><td><div class="manual-locked-note">`
                + `El ${esc(fechaLegibleCorta(fechaElegida))} está en la ${esc(cerrada.texto)}, que está cerrada. `
                + `Las semanas cerradas se conservan tal cual y no se pueden modificar. `
                + `Para cambiar este día, habilita esa semana en <strong>Horario</strong> y vuelve aquí.`
                + `</div></td></tr></tbody>`;
            $('aplicar-manual').disabled = true;
            $('descartar-manual').disabled = true;
            return;
        }
    }
    let dias;
    try { dias = diasVisiblesManual(); } catch (e) {
        tabla.innerHTML = `<tbody><tr><td>${esc(e.message)}</td></tr></tbody>`;
        return;
    }
    const filas = filasVisiblesManual();
    if (!filas.length) {
        const alcance = $('modificar-alcance')?.value;
        const ayuda = alcance === 'areas' ? 'Selecciona al menos un área para cargar sus celdas.' : 'Selecciona una persona en este editor para cargar sus celdas.';
        tabla.innerHTML = `<tbody><tr><td><div class="manual-locked-note">${ayuda} Esta selección no es necesaria para generar o actualizar el horario.</div></td></tr></tbody>`;
        $('aplicar-manual').disabled = true;
        $('descartar-manual').disabled = true;
        return;
    }
    // El nombre del día se pide a `diaCorto`, que aguanta que falte. Aquí se
    // leía `d.dia_semana.slice(0,3)` directamente, y un mes cuyos días no
    // traían ese dato reventaba el arranque **entero**: la excepción subía
    // hasta el `catch` final y se quedaban sin ejecutar los calendarios, la
    // guía y los ojos de las contraseñas. La pantalla parecía cargada y media
    // aplicación estaba muerta.
    tabla.innerHTML = `<thead><tr><th class="employee-name">Nombre</th>${dias.map(d => `<th class="${d.es_festivo ? 'holiday' : (d.es_domingo ? 'sunday' : '')}">${d.dia ?? ''}<br>${esc(diaCorto(d.dia_semana))}</th>`).join('')}</tr></thead><tbody>${filas.map(e => `<tr><td class="employee-name">${esc(e.nombre)}</td>${dias.map(meta => {
        const d = e.dias.find(x => x.fecha === meta.fecha);
        if (!d) return '<td>—</td>';
        const forzadoActivo=!!$('forzar-programacion-manual')?.checked;
        const fueraVigencia = d.turno === 'NV' || d.vigente === false;
        const protegido = fueraVigencia || !!d.solicitud_id || !!d.requerimiento_id || ['VAC','INC','PER','CAP'].includes(d.turno);
        const admGsEditable = d.turno === 'ADM-GS' && !protegido;
        const admAcEditable = d.turno === 'ADM-AC' && !protegido && e.area === 'atencion_ciudadano';
        const descansoAdminEditable = d.turno === 'D' && e.tipo_turno === 'administrativo' && d.origen === 'descanso_administrativo';
        const editableNormal = !protegido && (['AM','PM','D'].includes(d.turno) || admGsEditable || admAcEditable || descansoAdminEditable);
        const editable = !fueraVigencia && (editableNormal || forzadoActivo);
        if (!editable) return `<td class="shift-${d.turno}" title="${esc(d.observacion || d.origen)}">${d.turno === 'NV' ? '—' : esc(d.turno)}<small>${fueraVigencia ? 'Fuera de vigencia' : 'Protegido'}</small></td>`;
        const opcionesOperativas = (e.tipo_turno !== 'administrativo' || forzadoActivo) ? `
            <option value="AM" ${d.turno==='AM'?'selected':''}>AM</option>
            <option value="PM" ${d.turno==='PM'?'selected':''}>PM</option>` : '';
        // Un administrativo permanente solo puede llevar el código de su área.
        // Ofrecer AM, PM o el administrativo de otra área era ofrecer algo que
        // la aplicación siempre iba a rechazar después.
        const codigoAdmDelArea = e.area === 'atencion_ciudadano' ? 'ADM-AC' : 'ADM-GS';
        const esAdministrativo = e.tipo_turno === 'administrativo' && !forzadoActivo;
        const admGsOption = (!protegido && (!esAdministrativo || codigoAdmDelArea === 'ADM-GS'))
            ? `<option value="ADM-GS" ${d.turno==='ADM-GS'?'selected':''}>ADM-GS · Administrativo</option>` : '';
        const admAcOption = ((forzadoActivo || e.area === 'atencion_ciudadano')
                             && (!esAdministrativo || codigoAdmDelArea === 'ADM-AC'))
            ? `<option value="ADM-AC" ${d.turno==='ADM-AC'?'selected':''}>ADM-AC · Administrativo</option>` : '';
        const etiquetaCelda = `Turno de ${e.nombre} el ${d.fecha}`;
        // El descanso solo se ofrece a quien puede tenerlo ese día: para un
        // administrativo, únicamente si la celda ya venía como descanso.
        const opcionDescanso = (!esAdministrativo || d.turno === 'D')
            ? `<option value="D" ${d.turno==='D'?'selected':''}>D</option>` : '';
        return `<td><select class="manual-shift shift-${d.turno}" data-eid="${e.empleado_id}" data-fecha="${d.fecha}" data-original="${d.turno}" aria-label="${esc(etiquetaCelda)}" title="${esc(etiquetaCelda)}">
            ${opcionesOperativas}
            ${opcionDescanso}
            ${admGsOption}${admAcOption}
        </select></td>`;
    }).join('')}</tr>`).join('')}</tbody>`;
    tabla.querySelectorAll('.manual-shift').forEach(sel => {
        sel.onchange = () => {
            sel.classList.toggle('manual-changed', sel.value !== sel.dataset.original);
            sel.classList.remove('shift-AM','shift-PM','shift-D','shift-ADM-GS','shift-ADM-AC');
            sel.classList.add(`shift-${sel.value}`);
            actualizarContadorManual();
        };
    });
    $('aplicar-manual').disabled = false;
    $('descartar-manual').disabled = false;
    actualizarContadorManual();
}

function cambiosManuales() {
    const forzado=!!$('forzar-programacion-manual')?.checked;
    const justificacion=$('motivo-forzado')?.value.trim() || '';
    return [...document.querySelectorAll('#tabla-manual .manual-shift')]
        .filter(x => x.value !== x.dataset.original)
        .map(x => ({empleado_id: Number(x.dataset.eid), fecha: x.dataset.fecha, turno: x.value, forzado, justificacion: forzado ? justificacion : ''}));
}

function actualizarContadorManual() {
    const n = cambiosManuales().length;
    const forzar = !!$('forzar-programacion-manual')?.checked;
    $('editor-manual-info').textContent = n
        ? `${n} cambio(s) pendiente(s). ${forzar ? 'Excepción autorizable activa: si confirmas y justificas, las reglas operativas afectadas quedarán registradas como excepciones y no bloquearán el horario.' : 'Se validarán contra todas las reglas antes de generar alternativas.'}`
        : 'No hay cambios manuales pendientes.';
}

function renderDiagnosticoManual(items = [], reglasGenerales = []) {
    const box = $('manual-diagnostico');
    if (!box) return;
    if (!items.length && !reglasGenerales.length) {
        box.classList.add('hidden');
        box.innerHTML = '';
        return;
    }
    box.classList.remove('hidden');
    let html = '<div class="manual-diagnostics-head"><strong>Resultado de la modificación</strong><span>Las reglas que afecten tus cambios se muestran aquí mismo.</span></div>';
    if (reglasGenerales.length) {
        html += `<div class="manual-diagnostic-item bloqueado"><strong>Reglas que impiden generar una alternativa</strong><ul>${reglasGenerales.map(m=>`<li>${esc(m)}</li>`).join('')}</ul></div>`;
    }
    html += items.map(x => {
        const detalles = [...(x.bloqueos || []), ...(x.excepciones || [])];
        const estado = x.estado || 'revisar';
        const titulosEstado = {
            bloqueado: 'No se puede aplicar todavía',
            forzado: 'Aplicado con excepción',
            aplicado: 'Aplicado',
            heredado: 'Ese día pertenece al mes anterior',
        };
        const tituloEstado = titulosEstado[estado] || 'Revisar';
        const autos=(x.cambios_automaticos||[]);
        const sugerencias=(x.sugerencias||[]);
        return `<div class="manual-diagnostic-item ${esc(estado)}">
            <strong>${esc(x.empleado_nombre)} · ${fechaBonita(x.fecha)} · ${esc(x.turno_anterior || '—')} → ${esc(x.turno)} — ${tituloEstado}</strong>
            <div>${esc(x.mensaje || '')}</div>
            ${detalles.length ? `<ul>${detalles.map(m => `<li>${esc(m)}</li>`).join('')}</ul>` : ''}
            ${autos.length ? `<div class="automatic-related"><strong>Reajustes automáticos en esa semana:</strong>${autos.map(a=>`<div>${fechaBonita(a.fecha)} · ${esc(a.antes||'—')} → ${esc(a.despues||'—')} · ${esc(a.motivo||'')}</div>`).join('')}</div>` : ''}
            ${sugerencias.length ? `<div class="manual-diagnostic-suggestions">${sugerencias.map(v=>`<span>${esc(v)}</span>`).join('')}</div>` : ''}
        </div>`;
    }).join('');
    box.innerHTML = html;
}

async function ejecutarReprogramacion(ajustesManuales = [], forzarOverride = null) {
    if (!ultimo?.horario_id || !ultimo?.horario?.length) {
        throw new Error('Primero genera o selecciona una programación guardada para usarla como base.');
    }
    const [anio, mes] = $('periodo').value.split('-').map(Number);
    const soloEsteDia=!!(ajustesManuales.length && modoManualSoloDia());
    const rango = soloEsteDia ? rangoSemanaDeFecha(ajustesManuales[0].fecha) : rangoModificacion();
    const {inicio, fin} = rango;
    const alcance = $('modificar-alcance').value;
    const empleadoId = soloEsteDia ? Number(ajustesManuales[0].empleado_id) : empleadoModificacionId();
    const areas = alcance === 'areas' ? [...document.querySelectorAll('.manual-area:checked')].map(x => x.value) : [];
    if (!soloEsteDia && alcance === 'areas' && !areas.length) throw new Error('Selecciona al menos un área para reorganizar.');
    const reestructurarOtros = soloEsteDia ? false : (empleadoId ? $('modificar-reestructurar').value === 'si' : true);
    const forzarManual = !!(ajustesManuales.length && (forzarOverride === null ? $('forzar-programacion-manual')?.checked : forzarOverride));
    const motivoForzado = $('motivo-forzado')?.value.trim() || '';
    if (forzarManual && motivoForzado.length < 5) throw new Error('Indica el motivo de la excepción manual antes de forzar la programación.');
    setEstado(soloEsteDia ? 'Validando únicamente el día seleccionado…' : 'Buscando las mejores opciones dentro de las semanas seleccionadas…', 'working');
    const respuesta = await api('/api/horarios/reprogramar-parcial', {
        method: 'POST',
        body: JSON.stringify({
            mes,
            anio,
            semana_inicio: inicio,
            semana_fin: fin,
            empleado_id: empleadoId,
            areas,
            horario_id: ultimo.horario_id,
            ajustes_manuales: ajustesManuales,
            reestructurar_otros: reestructurarOtros,
            permitir_excepciones_manuales: forzarManual,
            motivo_excepcion_manual: motivoForzado,
            solo_este_dia: soloEsteDia,
        }),
    });
    renderDiagnosticoManual(respuesta.diagnostico_ajustes_manuales || [], (respuesta.diagnostico?.errores || []));
    respuestaGeneracion = respuesta;
    alternativasActuales = respuesta.alternativas || [];
    if (!alternativasActuales.length) {
        // Igual que al generar: la reprogramación que no encuentra salida no
        // puede hacer desaparecer el horario que ya estaba en pantalla.
        const diagnosticoParcial = respuesta.diagnostico || null;
        if (!ultimo?.horario?.length) ultimo = diagnosticoParcial;
        renderValidacion(diagnosticoParcial || {errores:['No fue posible reprogramar el rango seleccionado.'], advertencias:[]});
        setEstado('Reprogramación requiere revisión', 'warning', 2200);
        const err = new Error('No se encontró una alternativa válida. Revisa Validación: el rango o los ajustes manuales pueden ser incompatibles con cobertura, descansos o parejas de PC.');
        err.reprogramacion = respuesta;
        throw err;
    }
    const primeraId = alternativasActuales[0]?.horario_id || null;
    await cargarOpcionesPeriodo(primeraId, respuesta.mensaje || 'Se generaron alternativas para el rango seleccionado.');
    actualizarDisponibilidadExportacion();
    setEstado(soloEsteDia ? 'Cambio de un día preparado' : 'Alternativas parciales listas', 'success', 1600);
    if (!ajustesManuales.length) {
        const status = $('estado-reprogramacion-parcial');
        if (status) {
            status.textContent = 'Ya generaste alternativas para este rango. Puedes revisarlas en Horario o volver a generarlas si cambiaste algo.';
            status.classList.remove('hidden');
        }
        const btn = $('reprogramar-parcial');
        if (btn) btn.textContent = 'Volver a buscar las 5 mejores opciones de estas semanas';
        document.querySelector('[data-tab="horario"]').click();
    }
    await cargarEstadoPeriodo();
    return respuesta;
}

$('modificar-alcance').onchange = () => {
    const persona = $('modificar-alcance').value === 'persona';
    const areas = $('modificar-alcance').value === 'areas';
    $('g-modificar-persona').classList.toggle('hidden', !persona);
    $('g-modificar-reestructurar').classList.toggle('hidden', !persona);
    $('g-modificar-areas').classList.toggle('hidden', !areas);
    renderEditorManual();
};
$('modificar-persona').onchange = renderEditorManual;
document.querySelectorAll('.manual-area').forEach(x => x.addEventListener('change', renderEditorManual));
function reiniciarEstadoReprogramacionParcial() {
    const status = $('estado-reprogramacion-parcial');
    if (status) { status.classList.add('hidden'); status.textContent=''; }
    const btn = $('reprogramar-parcial');
    if (btn) btn.textContent = 'Buscar las 5 mejores opciones para estas semanas';
}
$('modificar-semana-inicio').onchange = () => { reiniciarEstadoReprogramacionParcial(); actualizarSemanasFinModificar(); renderEditorManual(); };
$('modificar-semana-fin').onchange = () => { reiniciarEstadoReprogramacionParcial(); renderEditorManual(); };
function configurarModoManual() {
    const solo=modoManualSoloDia();
    $('g-manual-persona')?.classList.toggle('hidden', !solo);
    $('g-manual-fecha')?.classList.toggle('hidden', !solo);
    if ($('aplicar-manual')) $('aplicar-manual').textContent=solo ? 'Validar y preparar este cambio' : 'Validar cambios y buscar opciones';
    if ($('restablecer-dia-automatico')) $('restablecer-dia-automatico').classList.toggle('hidden', !solo);
    renderEditorManual();
}
$('manual-modo')?.addEventListener('change',configurarModoManual);
$('manual-persona')?.addEventListener('change',renderEditorManual);
$('manual-fecha')?.addEventListener('change',renderEditorManual);
$('forzar-programacion-manual').onchange = () => {
    $('g-motivo-forzado')?.classList.toggle('hidden', !$('forzar-programacion-manual').checked);
    renderEditorManual();
    actualizarContadorManual();
};

$('reprogramar-parcial').onclick = async () => {
    try {
        const r = await ejecutarReprogramacion([]);
        toast(r.mensaje, r.completo ? 'success' : 'warning', 'Opciones de horario listas');
    } catch (e) {
        setEstado('No se pudo reprogramar', 'error', 2200);
        toast(e.message, 'error', 'No fue posible reorganizar el horario');
    }
};

$('cargar-editor-manual').onclick = () => {
    try { usarHorarioParaModificar('visible'); }
    catch (e) { toast(e.message, 'error', 'No se pudo cargar el editor'); }
};
$('cargar-horario-oficial-modificar')?.addEventListener('click', () => {
    try { usarHorarioParaModificar('oficial'); }
    catch (e) { toast(e.message, 'error', 'No se pudo cargar el horario oficial'); }
});

$('descartar-manual').onclick = () => renderEditorManual();

$('restablecer-dia-automatico')?.addEventListener('click', async () => {
    if (!modoManualSoloDia()) return;
    try {
        const eid=Number($('manual-persona')?.value || 0);
        const fecha=fechaManualSeleccionada();
        if (!eid) throw new Error('Selecciona la persona.');
        const persona=empleados.find(x=>Number(x.id)===eid);
        const ok=await confirmarUI({
            titulo:'Volver este día a Automático',
            mensaje:`¿Quieres retirar el cambio manual de ${persona?.nombre || 'esta persona'} para ${fechaBonita(fecha)}?`,
            detalle:'La decisión manual dejará de estar protegida. La aplicación volverá a calcular esa fecha cuando actualices el horario.',
            aceptar:'Volver a Automático',
            peligro:false,
        });
        if(!ok) return;
        await api(`/api/horarios/ajuste-manual/${eid}/${fecha}`,{method:'DELETE'});
        const {anio,mes}=periodo();
        setEstado('Recalculando el día sin el ajuste manual…','working');
        const generada=await api('/api/horarios/generar',{method:'POST',body:JSON.stringify({mes,anio,horario_id:ultimo?.horario_id || null})});
        if ((generada.alternativas||[]).length) {
            await cargarOpcionesPeriodo(generada.alternativas[0].horario_id,generada.mensaje);
            toast('El cambio manual fue retirado. Revisa las nuevas opciones y marca como oficial la que quieras conservar.','success','Día devuelto a Automático');
        } else {
            toast('El cambio manual fue retirado, pero el mes necesita revisión antes de poder generar una nueva opción.','warning','Ajuste retirado');
        }
        renderEditorManual();
    } catch(e) {
        if (String(e.message).includes('No existe un cambio manual activo')) toast('Ese día no tiene un cambio manual persistente que retirar.','info','Ya está en Automático');
        else toast(e.message,'error','No se pudo volver a Automático');
    }
});

$('aplicar-manual').onclick = async () => {
    const cambios = cambiosManuales();
    if (!cambios.length) {
        toast('No has cambiado ninguna celda AM, PM, D, ADM-GS o ADM-AC.', 'warning', 'Sin cambios manuales');
        return;
    }
    try {
        // Siempre se valida primero sin forzar. Solo una autorización explícita y justificada puede superar reglas operativas.
        const r = await ejecutarReprogramacion(cambios, false);
        const excepciones = (r.diagnostico_ajustes_manuales || []).filter(x => x.estado === 'forzado').length;
        toast(modoManualSoloDia() ? 'El cambio de este día quedó preparado sin modificar ninguna otra fecha. Revísalo y márcalo como oficial para conservarlo.' : `${cambios.length} ajuste(s) procesados. Se prepararon ${r.cantidad} opción(es).${excepciones ? ` ${excepciones} cambio(s) quedaron como excepción autorizada.` : ''}`, excepciones ? 'warning' : 'success', 'Cambio preparado');
    } catch (e) {
        renderDiagnosticoManual(e.reprogramacion?.diagnostico_ajustes_manuales || [], e.reprogramacion?.diagnostico?.errores || []);
        // Un rechazo puede venir de dos sitios muy distintos, y confundirlos
        // dejaba a la persona sin salida. Si el servidor dice que no se puede
        // ni intentar —la semana está cerrada, la fecha no es de este mes—, no
        // hay diagnóstico que revisar ni excepción que autorizar: lo único útil
        // es su mensaje, que además está bien escrito. Antes se descartaba y se
        // enseñaba «revisa el diagnóstico» junto a un diagnóstico vacío.
        if (!e.reprogramacion) {
            $('g-motivo-forzado')?.classList.add('hidden');
            toast(e.message || 'No se pudo preparar el cambio.', 'error', 'No se puede modificar este día');
            setEstado('El cambio no se pudo ni intentar', 'warning', 2800);
            return;
        }
        const deseaForzar = !!$('forzar-programacion-manual')?.checked;
        if (!deseaForzar) {
            $('g-motivo-forzado')?.classList.remove('hidden');
            toast('La modificación incumple una o más reglas. Revisa el diagnóstico. Si necesitas mantener la decisión, activa “Autorizar una excepción”, escribe la justificación y vuelve a aplicar.', 'warning', 'La programación no cumple las reglas');
            setEstado('Cambios rechazados por validación', 'warning', 2800);
            return;
        }
        const motivo = $('motivo-forzado')?.value.trim() || '';
        if (motivo.length < 5) {
            $('g-motivo-forzado')?.classList.remove('hidden');
            toast('Escribe el motivo administrativo de la excepción antes de forzar.', 'warning', 'Falta el motivo');
            return;
        }
        const detalle = (e.reprogramacion?.diagnostico?.errores || []).slice(0,5).join(' · ') || e.message;
        const ok = await confirmarUI({
            titulo: 'Autorizar excepción manual',
            mensaje: 'Este cambio rompe una o más reglas operativas. ¿Quieres conservar exactamente esta decisión como una excepción autorizada?',
            detalle: `${detalle}${(e.reprogramacion?.diagnostico?.errores || []).length > 5 ? ' · …' : ''} La justificación quedará registrada. Solo las protecciones técnicas de datos y permisos permanecen bloqueadas.`,
            aceptar: 'Autorizar y conservar el cambio',
            peligro: true,
        });
        if (!ok) return;
        try {
            const r = await ejecutarReprogramacion(cambios, true);
            const forzados = (r.diagnostico_ajustes_manuales || []).filter(x => x.estado === 'forzado').length;
            toast(`Reprogramación forzada: ${forzados || cambios.length} cambio(s) conservados como excepción. El motivo quedó registrado en el historial.`, 'warning', 'Excepción administrativa aplicada');
        } catch (forceError) {
            renderDiagnosticoManual(forceError.reprogramacion?.diagnostico_ajustes_manuales || [], forceError.reprogramacion?.diagnostico?.errores || []);
            setEstado('No se pudo conservar el cambio', 'error', 3000);
            toast('Aun con la autorización existe un problema técnico o de integridad que no puede ignorarse. Revisa el diagnóstico.', 'error', 'No se pudo aplicar la excepción');
        }
    }
};

const AREAS_UI = {
    gestion_social: {estado:'estado-area-gs', nombre:'Gestión Social', sigla:'GS'},
    comunicaciones: {estado:'estado-area-com', nombre:'Comunicaciones', sigla:'COM'},
    atencion_ciudadano: {estado:'estado-area-ac', nombre:'Atención al Ciudadano', sigla:'AC'},
};

function hayCambiosPendientesDe(origen) {
    return contarCambiosPendientesDe(origen) > 0;
}

function contarCambiosPendientesDe(origen) {
    const razones = Object.values(estadoPeriodoActual?.areas || {})
        .filter(x => x?.requiere_actualizacion)
        .flatMap(x => x?.razones || [])
        .filter(r => r?.mostrar_en_estado !== false);
    const filtradas = razones.filter(r => origen === 'solicitudes'
        ? (r?.solicitud_id || String(r?.tipo || '').includes('solicitud'))
        : (r?.requerimiento_id || r?.grupo_id || /requerimiento|asignacion/.test(String(r?.tipo || ''))));
    const claves = new Set(filtradas.map(r =>
        r.solicitud_id ? `s:${r.solicitud_id}`
            : r.grupo_id ? `g:${r.grupo_id}`
                : r.requerimiento_id ? `r:${r.requerimiento_id}`
                    : `${r.tipo || origen}:${r.mensaje || ''}`));
    return claves.size;
}

const CONTENIDO_BOTON_OCUPADO = new WeakMap();

function ponerBotonOcupado(btn, ocupado, textoOcupado='Procesando…') {
    if (!btn) return;
    if (ocupado) {
        if (btn.dataset.busy === '1') return;
        btn.dataset.busy='1';
        // Se guarda el contenido, no solo el texto: hay botones que llevan
        // dentro sus propias piezas —las fichas de paleta enseñan una tira con
        // los colores— y restaurarlos como texto plano los dejaba desnudos.
        CONTENIDO_BOTON_OCUPADO.set(btn, btn.innerHTML);
        btn.disabled=true;
        btn.setAttribute('aria-busy','true');
        btn.textContent=textoOcupado;
    } else {
        btn.dataset.busy='0';
        btn.disabled=false;
        btn.setAttribute('aria-busy','false');
        const anterior = CONTENIDO_BOTON_OCUPADO.get(btn);
        if (anterior !== undefined) {
            btn.innerHTML = anterior;
            CONTENIDO_BOTON_OCUPADO.delete(btn);
        }
        delete btn.dataset.textoAnterior;
    }
}

function renderEstadoAreas(d) {
    const estados=d?.areas || {};
    const hayHorario=!!(ultimo?.horario_id || horarioActualReferencia?.horario_id || alternativasActuales.length);
    for (const [area, ui] of Object.entries(AREAS_UI)) {
        const ids=[ui.estado, `${ui.estado}-solicitudes`, `${ui.estado}-asignaciones`];
        const estado=estados?.[area];
        ids.forEach(id => { const span=$(id); if (span) {
            span.classList.remove('pending','ok');
            if (!estado) span.textContent='Sin cambios detectados';
            else if (estado.requiere_actualizacion) {
                span.textContent='Cambios pendientes'; span.classList.add('pending');
            } else {
                span.textContent='Actualizada'; span.classList.add('ok');
            }
        }});
    }
    ['solicitudes','asignaciones'].forEach(origen => {
        const id = `aplicar-regeneracion-${origen}`;
        const accion=$(id);
        if (accion && accion.dataset.busy !== '1') {
            const pertinente = hayCambiosPendientesDe(origen);
            accion.disabled = !hayHorario || !pertinente;
            accion.title = !hayHorario
                ? 'Primero crea el horario inicial.'
                : pertinente
                    ? `Aplica únicamente los cambios pendientes de ${origen} al alcance seleccionado.`
                    : `No hay cambios de ${origen} pendientes para este período.`;
        }
    });
}

async function actualizarSoloArea(area, boton = null) {
    const ui=AREAS_UI[area]; if (!ui) return;
    const btn=boton || $('aplicar-regeneracion-solicitudes') || $('aplicar-regeneracion-asignaciones');
    const baseId=ultimo?.horario_id || horarioActualReferencia?.horario_id || null;
    if (!baseId) {
        toast('Primero genera el horario completo del mes. Después podrás actualizar un área sin modificar las otras dos.','warning','Aún no existe una programación base');
        return false;
    }
    const {anio,mes}=periodo();
    ponerBotonOcupado(btn,true,'Actualizando área…');
    try {
        setEstado(`Actualizando únicamente ${ui.nombre}…`,'working');
        const data=await api(`/api/horarios/generar-area/${encodeURIComponent(area)}`,{
            method:'POST',body:JSON.stringify({mes,anio,horario_id:baseId}),
        });
        if (!(data.alternativas||[]).length) {
            const errores=data?.diagnostico?.errores || [];
            toast(errores[0] || `No fue posible encontrar una alternativa válida para ${ui.nombre}. Las otras áreas no fueron modificadas.`,'warning','Área sin alternativa válida');
            return false;
        }
        const preferir=data.alternativas[0]?.horario_id || null;
        await cargarOpcionesPeriodo(preferir,data.mensaje || `${ui.nombre} actualizado sin modificar las otras áreas.`);
        await cargarEstadoPeriodo();
        await cargarSemanasBloqueo();
        const verificadas=(data.alternativas||[]).every(x=>x.independencia_verificada!==false);
        toast(
            verificadas
                ? `${ui.nombre} se recalculó. Las otras dos áreas se conservaron sin cambios.`
                : `${ui.nombre} se recalculó; revisa el diagnóstico de independencia antes de oficializar.`,
            verificadas ? 'success' : 'warning',
            verificadas ? 'Área actualizada' : 'Revisión necesaria'
        );
        document.querySelector('[data-tab="horario"]')?.click();
        setEstado('Alternativas del área listas','success',1400);
        return true;
    } catch(e) {
        setEstado('No se pudo actualizar el área','error',2200);
        toast(e.message,'error',`No se pudo actualizar ${ui.nombre}`);
        return false;
    } finally {
        ponerBotonOcupado(btn,false);
        renderEstadoAreas(estadoPeriodoActual);
    }
}

async function ejecutarRegeneracionPendientes() {
    const btn = $('regenerar-pendientes');
    if (!btn || btn.dataset.busy === '1') return;
    try {
        if (!estadoPeriodoActual) await cargarEstadoPeriodo();
        const areas = Object.entries(estadoPeriodoActual?.areas || {})
            .filter(([,info]) => info?.requiere_actualizacion)
            .map(([area]) => area)
            .filter(area => AREAS_UI[area]);
        if (!areas.length) {
            toast('No hay áreas con cambios pendientes para aplicar.', 'info', 'Horario actualizado');
            return;
        }
        const hayHorario = alternativasActuales.length > 0 || !!ultimo?.horario_id || !!horarioActualReferencia?.horario_id;
        if (!hayHorario) {
            toast('Primero crea el horario inicial del mes.', 'warning', 'Aún no existe una programación');
            return;
        }
        ponerBotonOcupado(btn, true, 'Aplicando cambios…');
        for (const area of areas) {
            await actualizarSoloArea(area, btn);
        }
        await cargarEstadoPeriodo().catch(()=>{});
        actualizarAccionGenerar();
    } finally {
        ponerBotonOcupado(btn, false);
    }
}

async function actualizarAreasPendientesDesde(origen) {
    const tab = origen === 'asignaciones' ? 'requerimientos' : 'solicitudes';
    document.querySelector(`[data-tab="${tab}"]`)?.click();
    const selector = $(`alcance-regeneracion-${origen}`);
    if (selector) selector.value = 'pendientes';
    selector?.focus();
    toast(`El cambio de ${origen} quedó pendiente. Elige el área o todas y pulsa «Regenerar alcance elegido».`, 'info', 'Selecciona el alcance');
}

async function aplicarRegeneracionAlcance(origen) {
    const btn = $(`aplicar-regeneracion-${origen}`);
    if (!btn || btn.dataset.busy === '1') return;
    const alcance = $(`alcance-regeneracion-${origen}`)?.value || 'pendientes';
    const hayHorario = alternativasActuales.length > 0 || !!ultimo?.horario_id;
    if (!hayHorario) {
        toast('Primero crea el horario inicial del mes.', 'warning', 'Aún no existe una programación');
        return;
    }
    ponerBotonOcupado(btn, true, 'Aplicando cambios…');
    try {
        if (alcance === 'todas') {
            await ejecutarGeneracionHorario('pendientes');
        } else {
            const areas = alcance === 'pendientes'
                ? Object.entries(estadoPeriodoActual?.areas || {}).filter(([,x]) => x?.requiere_actualizacion).map(([a]) => a)
                : [alcance];
            const validas = areas.filter(a => AREAS_UI[a]);
            if (!validas.length) {
                toast('No hay áreas con cambios pendientes para aplicar.', 'info', 'Horario actualizado');
                return;
            }
            for (const area of validas) await actualizarSoloArea(area, btn);
        }
    } finally {
        ponerBotonOcupado(btn, false);
        await cargarEstadoPeriodo().catch(()=>{});
        actualizarAccionGenerar();
    }
}

$('actualizar-desde-solicitudes')?.addEventListener('click', () => actualizarAreasPendientesDesde('solicitudes'));
$('actualizar-desde-asignaciones')?.addEventListener('click', () => actualizarAreasPendientesDesde('asignaciones'));
$('aplicar-regeneracion-solicitudes')?.addEventListener('click', () => aplicarRegeneracionAlcance('solicitudes'));
$('aplicar-regeneracion-asignaciones')?.addEventListener('click', () => aplicarRegeneracionAlcance('asignaciones'));

async function cargarEstadoPeriodo() {
    const {anio,mes}=periodo();
    const box=$('estado-periodo'); if(!box) return;
    try {
        const d=await api(`/api/operacion/periodo/${anio}/${mes}`);
        estadoPeriodoActual = d;
        renderEstadoAreas(d);
        if (!(d.mostrar_aviso_pendiente ?? d.requiere_actualizacion)) {
            // Falta un paso, pero no es el de recalcular: el mes ya se recalculó
            // y lo que queda es escoger entre las opciones. Sin este aviso el
            // mes se veía «al día» mientras el horario que consulta la gente
            // seguía siendo el anterior, y las novedades aprobadas no aparecían
            // por ninguna parte.
            if (d.alternativas_sin_elegir) {
                box.classList.remove('hidden', 'warning-box');
                box.classList.add('info-box');
                box.innerHTML = `<strong>Falta escoger el horario del mes</strong>`
                    + `<div>Se calcularon <b>${d.opciones_en_espera} opciones</b> nuevas y todavía `
                    + `no se ha escogido ninguna.</div>`
                    + `<small>Mientras tanto, el horario del mes sigue siendo el anterior: `
                    + `lo que se aprobó después de calcularlo no aparece en él hasta que `
                    + `escojas una de las opciones y la marques como horario del mes.</small>`;
                actualizarAccionGenerar();
                return;
            }
            box.classList.add('hidden');
            box.classList.remove('info-box');
            box.innerHTML='';
            actualizarAccionGenerar();
            return;
        }
        box.classList.remove('hidden');
        box.classList.remove('info-box');
        box.classList.add('warning-box');
        const visibles=(d.razones||[]).filter(r=>r.mostrar_en_estado!==false);
        const pendientes=Object.entries(d.areas||{}).filter(([,x])=>x?.requiere_actualizacion).map(([a])=>AREAS_UI[a]?.nombre||a);
        const alcance=pendientes.length ? `<div><b>Áreas pendientes:</b> ${pendientes.map(esc).join(' · ')}</div>` : '';
        const cola='<small>El horario oficial no cambia solo: se queda como está hasta que apliques los cambios. Al aplicarlos se recalculan únicamente las áreas pendientes; las demás conservan sus turnos exactamente igual.</small>';
        // El aviso dice de dónde viene lo pendiente. Decir «hay cambios» en un
        // mes que no tiene ninguna solicitud ni asignación propia despistaba:
        // lo que pasa es que depende de otro mes, o que hay que resincronizar.
        let titulo, detalle;
        if (d.origen_pendiente === 'continuidad') {
            titulo = 'Este mes depende de otro que cambió';
            detalle = `<small>Este mes no tiene solicitudes ni asignaciones nuevas. Se calculó a partir del mes anterior, y ese mes se modificó después, así que conviene volver a generarlo para que la continuidad cuadre.</small><ul>${visibles.map(r=>`<li>${esc(r.mensaje||String(r))}</li>`).join('')}</ul>`;
        } else if (d.origen_pendiente === 'sincronizacion') {
            titulo = 'El horario quedó desincronizado';
            detalle = '<small>Hubo un cambio que después se deshizo o se canceló, pero el horario oficial se calculó cuando aún estaba vigente. Vuelve a generarlo para dejarlo al día. No hay ninguna solicitud ni asignación pendiente.</small>';
        } else {
            titulo = 'Hay cambios pendientes de aplicar al horario';
            detalle = visibles.length
                ? `<ul>${visibles.map(r=>`<li>${esc(r.mensaje||String(r))}</li>`).join('')}</ul>`
                : '<small>Hay cambios recientes que todavía no están reflejados en el horario oficial.</small>';
        }
        box.innerHTML=`<strong>${titulo}</strong>${alcance}${detalle}${cola}`;
        actualizarAccionGenerar();
    } catch(e) {
        box.classList.remove('hidden');
        box.textContent='No se pudo consultar si el horario tiene cambios pendientes.';
        renderEstadoAreas(null);
    }
}

async function cargarReglasActivas() {
    const box=$('reglas-activas'); if(!box) return;
    try {
        const d=await api('/api/operacion/reglas');
        const reglas=(d.reglas||[]);
        const grupos = [
            {nivel:'bloqueante', titulo:'No se pueden saltar', ayuda:'Protegen lo que ya está decidido, como una semana cerrada. Para poder editar hay que abrirla primero.'},
            {nivel:'decision', titulo:'Se cumplen solas, pero puedes autorizar una excepción', ayuda:'La aplicación las respeta al armar el mes. Desde Modificar horario puedes saltártelas explicando por qué.'},
            {nivel:'advertencia', titulo:'Solo avisan', ayuda:'Te señalan algo para que lo mires. No impiden dar el mes por bueno.'},
        ];
        const estado = r => r.nivel === 'bloqueante' ? 'Obligatoria' : (r.nivel === 'advertencia' ? 'Aviso' : 'Se puede autorizar');
        const contenido = grupos.map(g => {
            const items = reglas
                .filter(r => (r.nivel || 'decision') === g.nivel)
                .sort((a,b) => (Number(b.prioridad||0)-Number(a.prioridad||0)) || String(a.nombre||'').localeCompare(String(b.nombre||'')));
            if (!items.length) return '';
            return `<section class="rule-group rule-group-${g.nivel}">
                <div class="rule-group-heading"><div><strong>${g.titulo}</strong><small>${g.ayuda}</small></div><span>${items.length}</span></div>
                <div class="rule-cards">${items.map(r=>`<article class="rule-user-card ${esc(r.nivel||'')}">
                    <div class="rule-user-head"><strong>${esc(r.nombre||'Regla de programación')}</strong><span class="rule-status">${esc(estado(r))}</span></div>
                    <p>${esc(r.descripcion||'')}</p>
                    <small><strong>Qué hacer:</strong> ${esc(r.que_hacer||'Revisa la programación antes de continuar.')}</small>
                </article>`).join('')}</div>
            </section>`;
        }).join('');
        box.innerHTML=`<strong>Reglas activas</strong>${contenido || '<div class="muted">No hay reglas configuradas.</div>'}
            ${d.nota_horas ? `<small class="hours-rule-note">${esc(d.nota_horas)}</small>` : ''}`;
    } catch(e) {
        box.innerHTML='<strong>Reglas activas</strong><div class="muted">No se pudo cargar el catálogo de reglas.</div>';
    }
}

function actualizarAccionGenerar() {
    const btn = $('generar');
    const regenerar = $('regenerar-pendientes');
    const accionesModulo = [
        {boton:$('actualizar-desde-solicitudes'), origen:'solicitudes'},
        {boton:$('actualizar-desde-asignaciones'), origen:'asignaciones'},
    ].filter(x => x.boton);
    if (!btn) return;
    const cerradas = semanasEstadoActual.filter(x => x.bloqueada).length;
    // Nombre histórico conservado para compatibilidad con instalaciones y
    // pruebas anteriores; la etiqueta visible ahora es más clara para el
    // operador: "Aplicar cambios (semanas abiertas)".
    const nombreHistoricoSemanasEditables = 'Regenerar semanas editables';
    const hayHorario = alternativasActuales.length > 0 || !!ultimo?.horario_id;
    const hayOficial = !!horarioActualReferencia?.horario_id
        || alternativasActuales.some(x => x?.oficial);
    const requiereActualizar = !!(estadoPeriodoActual?.mostrar_aviso_pendiente
        ?? estadoPeriodoActual?.requiere_actualizacion);
    if (!hayHorario) {
        btn.textContent = 'Crear horario inicial';
        btn.title = 'Genera y compara las cinco mejores opciones encontradas para este mes.';
        btn.disabled = false;
    } else {
        // Un mes que ya tiene horario también se puede volver a calcular: no se
        // pierde nada, porque el horario oficial no cambia hasta que se marca
        // como oficial una de las opciones nuevas. Antes el botón quedaba
        // apagado y parecía que ya no se podía rehacer.
        btn.textContent = 'Volver a crear opciones';
        btn.disabled = false;
        btn.title = 'Vuelve a calcular las cinco mejores opciones de este mes. El horario oficial actual no cambia hasta que marques otra opción como oficial.';
    }
    if (regenerar) {
        regenerar.disabled = !hayHorario || !requiereActualizar;
        regenerar.textContent = cerradas ? 'Aplicar cambios (semanas abiertas)' : 'Aplicar cambios pendientes';
        regenerar.title = !hayHorario
            ? 'Primero genera el horario completo.'
            : requiereActualizar
                ? (cerradas ? `${cerradas} semana(s) cerrada(s) se conservarán exactamente como están. ${nombreHistoricoSemanasEditables} solo se aplica a las semanas abiertas.` : 'Aplica las solicitudes, asignaciones y cambios pendientes del período.')
                : 'No hay cambios pendientes por aplicar.';
    }
    // Un botón apagado sin explicación deja parado a quien no conoce la
    // aplicación. El motivo estaba solo en el globo de ayuda del ratón, que no
    // existe al usar una pantalla táctil: ahora se escribe también a la vista.
    const ayuda = $('ayuda-acciones');
    if (ayuda) {
        let texto = '';
        if (!hayHorario) {
            // Antes de invitar a crearlo hay que mirar si se puede. Cada mes se
            // calcula a partir del oficial del anterior; si ese no está
            // elegido, la aplicación decía «Pulsa Crear horario inicial» y al
            // pulsarlo lo rechazaba. Ahora se dice antes y con el mes por su
            // nombre.
            const falta = mesAnteriorSinOficial();
            texto = falta
                ? `Para crear el horario de ${nombreDelPeriodo()} hace falta antes el de ${falta}: `
                  + 'ese mes todavía no tiene horario oficial. Cada mes se calcula a partir del oficial del '
                  + 'anterior, para que las rachas, los descansos y la rotación no se corten en la frontera '
                  + 'entre meses.'
                : 'Este mes todavía no tiene horario. Pulsa «Crear horario inicial» para que la aplicación proponga las mejores opciones.';
            // El botón NO se desactiva por este aviso, y es a propósito. Este
            // cálculo vive en la pantalla y duplica una regla que el servidor ya
            // comprueba; cuando se equivocó —leía mal la respuesta y creía que
            // septiembre no estaba oficial— dejó la aplicación sin poder crear
            // octubre, sin manera de insistir. Un aviso puede equivocarse
            // callándose; nunca impidiendo trabajar. Si de verdad falta el mes
            // anterior, quien contesta que no es el servidor, y su mensaje dice
            // exactamente qué hacer.
            if (falta) btn.title = `Puede que primero haya que marcar como oficial el horario de ${falta}.`;
        } else if (requiereActualizar) {
            const origen = estadoPeriodoActual?.origen_pendiente;
            if (origen === 'continuidad') {
                texto = 'Este mes no tiene solicitudes ni asignaciones propias: lo que cambió fue el mes del que depende. Vuelve a generarlo para que la continuidad cuadre.';
            } else if (origen === 'sincronizacion') {
                texto = 'No queda ninguna solicitud ni asignación pendiente, pero el horario se calculó antes de que se deshiciera un cambio. Vuelve a generarlo para dejarlo al día.';
            } else {
                texto = cerradas
                    ? `Hay cambios pendientes. Al aplicarlos, las ${cerradas} semana(s) cerrada(s) se conservarán exactamente como están. Solo se recalculan las áreas afectadas.`
                    : 'Hay cambios pendientes de aplicar a este mes. Usa «Aplicar cambios pendientes»: solo se recalculan las áreas afectadas, las demás quedan igual.';
            }
        } else if (!hayOficial) {
            texto = `Hay ${alternativasActuales.length || 'varias'} opciones creadas y ninguna marcada como oficial todavía. Compáralas y pulsa «${etiquetaBotonOficial()}» en la que quieras usar como base del mes.`;
        } else {
            texto = 'Este mes ya tiene su horario y no hay cambios pendientes. Puedes volver a crear opciones para compararlas —el oficial no cambia hasta que marques otra— o ajustar días sueltos en «Modificar horario».';
        }
        ayuda.textContent = texto;
    }
    accionesModulo.forEach(({boton:b, origen}) => {
        const pertinente = hayCambiosPendientesDe(origen);
        b.disabled = !hayHorario || !requiereActualizar || !pertinente;
        b.title = !hayHorario
            ? 'Primero genera el horario completo.'
            : !pertinente
                ? `No hay cambios de ${origen} pendientes para este período.`
                // No aplica nada: lleva al recuadro de abajo donde se elige el
                // alcance. Decía «Abre la pestaña correspondiente» estando ya
                // en ella.
                : 'Baja al recuadro donde se elige el área (GS, COM, AC o todas) y se aplican los cambios.';
    });
}

// El mes del que depende el que se está mirando. Se consulta al cambiar de
// período y se guarda aquí, porque la ayuda de la barra se pinta en caliente y
// no puede esperar a una petición.
let estadoMesAnterior = {periodo: null, nombre: '', tieneOficial: true};

function periodoAnteriorA(valor) {
    if (!valor) return null;
    const [anio, mes] = valor.split('-').map(Number);
    const anterior = mes === 1 ? `${anio - 1}-12` : `${anio}-${String(mes - 1).padStart(2, '0')}`;
    return anterior < PERIODO_MINIMO ? null : anterior;
}

function mesAnteriorSinOficial() {
    const valor = periodoActual();
    if (!valor || valor === PERIODO_MINIMO) return null;
    if (estadoMesAnterior.periodo !== valor) return null;   // todavía no se sabe
    return estadoMesAnterior.tieneOficial ? null : estadoMesAnterior.nombre;
}

async function cargarEstadoMesAnterior() {
    const valor = periodoActual();
    const anterior = periodoAnteriorA(valor);
    if (!anterior) {
        estadoMesAnterior = {periodo: valor, nombre: '', tieneOficial: true};
        return;
    }
    const [anio, mes] = anterior.split('-').map(Number);
    try {
        // La ruta contesta {ok, horario} y `horario` es un OBJETO —la
        // alternativa oficial— o null si no hay ninguna. Aquí se miraba
        // `horario.length`, como si fuera una lista, así que daba «no hay
        // oficial» siempre: septiembre estaba oficial y publicado y la
        // aplicación no dejaba crear octubre.
        const d = await api(`/api/horarios/oficial/${anio}/${mes}`);
        estadoMesAnterior = {periodo: valor, nombre: nombreDelPeriodo(anterior),
                             tieneOficial: !!(d && d.horario)};
    } catch (e) {
        // Ante la duda no se bloquea nada. Este aviso solo puede adelantar algo
        // que el servidor ya comprueba por su cuenta; si se equivoca, que sea
        // callándose y no impidiendo trabajar.
        estadoMesAnterior = {periodo: valor, nombre: nombreDelPeriodo(anterior),
                             tieneOficial: true};
    }
}

async function cargarSemanasBloqueo() {
    const {anio, mes} = periodo();
    const data = await api(`/api/operacion/semanas/${anio}/${mes}`);
    semanasEstadoActual = data.semanas || [];
    await cargarEstadoMesAnterior();
    actualizarAccionGenerar();
    const renderWeekBox = id => {
        const box=$(id); if(!box) return;
        box.innerHTML = semanasEstadoActual.map(s => `
            <button type="button" class="week-lock ${s.bloqueada ? 'locked' : ''}" data-lunes="${s.lunes}" data-bloqueada="${s.bloqueada ? '1' : '0'}">
                <strong>${esc(s.texto)}</strong><span>${s.bloqueada ? 'Cerrada · habilitar' : 'Editable · cerrar'}</span>
            </button>`).join('');
        box.querySelectorAll('.week-lock').forEach(btn => btn.onclick = async () => {
            const bloquear = btn.dataset.bloqueada !== '1';
            if (bloquear && cambiosManuales().length) {
                const ok = await confirmarUI({
                    titulo:'Cerrar semana',
                    mensaje:'Hay cambios manuales pendientes que todavía no se han aplicado.',
                    detalle:'Al cerrar una semana, el editor se actualizará y esos cambios sin guardar se descartarán. Aplica los cambios primero si deseas conservarlos.',
                    aceptar:'Cerrar y descartar cambios',
                    peligro:false,
                });
                if (!ok) return;
            }
            try {
                const r = await api('/api/operacion/semanas', {method:'PUT', body:JSON.stringify({anio,mes,lunes_semana:btn.dataset.lunes,bloqueada:bloquear})});
                toast(r.mensaje,'success',bloquear ? 'Semana cerrada' : 'Semana habilitada');
                await cargarSemanasBloqueo();
            } catch (e) { toast(e.message,'error','No se pudo cambiar la semana'); }
        });
    };
    renderWeekBox('lista-semanas-bloqueo');
    renderWeekBox('lista-semanas-modificar');
    actualizarSemanasModificar();
    renderEditorManual();
}

function detalleProblemaPublicacion(item) {
    if (!item) return '';
    if (typeof item === 'string') return item;
    // El servidor manda la frase ya escrita, y es la que hay que enseñar. Al
    // armarla aquí a partir de los campos sueltos salían cosas como «falta
    // cobertura cobertura del área»: el campo ya traía la palabra dentro.
    if (item.detalle) return item.detalle;
    if (item.tipo === 'error') return 'Error de validación';
    if (item.tipo === 'cobertura' || item.area) return `${item.area || 'Área'} · ${item.fecha || ''} · falta cobertura ${item.turno || ''}`.trim();
    if (item.tipo === 'pc' || item.personas) return `${(item.personas || []).join(' y ')} · ${item.fecha || ''} · coinciden en ${item.turno || 'el mismo turno'}`;
    if (item.tipo === 'compensatorio' || item.festivo) return `${item.empleado || 'Persona'} · festivo ${item.festivo || ''} sin compensatorio`;
    return JSON.stringify(item);
}

function resumenPublicacionHtml(r) {
    // Compatibilidad documental: la etiqueta fija anterior era
    // «Agosto histórico · publicable con confirmación». Ahora se construye
    // con el mes real porque septiembre también es una programación base.
    if (!r) return 'Selecciona una programación para revisar si está lista para publicar.';
    const c = r.conteos || {};
    const items = [
        ['Cobertura faltante', c.dias_sin_cobertura || 0],
        ['Conflictos de PC', c.conflictos_pc || 0],
        ['Compensatorios pendientes', c.compensatorios_pendientes || 0],
        ['Errores por resolver', c.errores_bloqueantes || 0],
    ];
    const problemasBase = r.problemas_agosto_publicables || [];
    const periodoBase = nombrePeriodoRespuesta(r);
    const ignorados = r.problemas_ignorados_semanas_bloqueadas || [];
    let estado;
    if (r.publicado) estado = 'Publicado';
    else if (r.es_agosto_historico && problemasBase.length) estado = `${periodoBase} histórico · publicable con confirmación`;
    else if (r.listo) estado = 'Listo para publicar';
    else if (r.requiere_confirmacion) estado = 'Publicable con confirmación manual';
    else estado = 'Requiere revisión';

    // Si agosto ya está publicado, esto es el registro de lo que se aceptó, no
    // una lista de cosas por decidir. Decirle a alguien «revisa qué se está
    // aceptando» sobre un mes que ya se trabajó es pedirle una decisión que
    // no existe.
    const detalleBase = problemasBase.length ? `
        <div class="publish-note ${r.publicado ? 'info' : 'warning'}">
            <strong>${esc(periodoBase)} conserva incidencias del horario ya ejecutado.</strong>
            <div>${r.publicado
                ? 'Este mes ya se trabajó y se publicó tal y como está. Estas son sus diferencias con las reglas de hoy, guardadas como registro:'
                : 'Puedes publicarlo igualmente, pero primero revisa qué se está aceptando:'}</div>
            <ul class="publish-issues">${problemasBase.slice(0,12).map(x => `<li>${esc(detalleProblemaPublicacion(x))}</li>`).join('')}</ul>
            ${problemasBase.length > 12 ? `<small>Y ${problemasBase.length-12} incidencia(s) adicional(es).</small>` : ''}
        </div>` : '';
    const detalleBloqueadas = ignorados.length ? `
        <div class="publish-note locked">
            <strong>${ignorados.length} alerta(s) pertenecen a semanas cerradas.</strong>
            <div>Se muestran como referencia, pero no impiden publicar porque esas semanas ya están bloqueadas y no forman parte de los cambios pendientes.</div>
        </div>` : '';
    const detalleManual = (r.excepciones_manuales || []).length ? `
        <div class="publish-note"><strong>Excepciones manuales:</strong> ${(r.excepciones_manuales || []).map(esc).join(' · ')}</div>` : '';

    return `<div class="publish-head"><strong>${esc(estado)}</strong></div>
        <div class="publish-metrics">${items.map(([n,v]) => `<div><b>${v}</b><small>${esc(n)}</small></div>`).join('')}</div>
        <div class="publish-details">${detalleBase}${detalleBloqueadas}${detalleManual}</div>`;
}


async function cargarResumenPublicacion() {
    const box = $('resumen-publicacion');
    if (!box) return null;
    if (!ultimo?.horario_id || !ultimo?.oficial) { box.classList.add('hidden'); box.innerHTML=''; return null; }
    const r = await api(`/api/operacion/publicacion/${ultimo.horario_id}/resumen`);
    if (r.publicado && r.listo && !(r.problemas_agosto_publicables||[]).length && !(r.excepciones_manuales||[]).length) {
        box.classList.add('hidden'); box.innerHTML=''; return r;
    }
    box.innerHTML = resumenPublicacionHtml(r);
    box.classList.remove('hidden');
    return r;
}

$('publicar-horario').onclick = async () => {
    if (!ultimo?.horario_id || !ultimo?.oficial) {
        toast('Primero marca esta alternativa como horario oficial.','warning','No se puede publicar'); return;
    }
    try {
        const resumen = await cargarResumenPublicacion();
        let confirmarExcepciones = false;
        const problemasAgosto = resumen?.problemas_agosto_publicables || [];
        if (resumen?.es_agosto_historico && problemasAgosto.length) {
            // El mes sale del propio resumen. Estaba escrito «agosto» a mano, así
            // que en septiembre —que también es una programación base ya
            // ejecutada— el aviso hablaba del mes equivocado aunque las
            // incidencias listadas fueran las correctas.
            const mesBase = nombrePeriodoRespuesta(resumen);
            const listado = problemasAgosto.slice(0,8).map(detalleProblemaPublicacion).join(' · ');
            const extra = problemasAgosto.length > 8 ? ` · y ${problemasAgosto.length-8} incidencia(s) más` : '';
            const ok = await confirmarUI({
                titulo:`Publicar ${mesBase}`,
                mensaje:`${mesBase} es una programación que ya se trabajó. Puede quedar publicada tal como está, aunque tenga diferencias con las reglas de hoy.`,
                detalle:`Estas son las diferencias que quedarán aceptadas: ${listado}${extra}. La excepción vale solo para ${mesBase}; los meses que generes a partir de ahora se miden con las reglas completas.`,
                aceptar:'Aceptar y publicar', peligro:false,
            });
            if (!ok) return;
            confirmarExcepciones = true;
        } else if (resumen?.requiere_confirmacion || (resumen?.cobertura_sin_am_pm || []).length) {
            const ok = await confirmarUI({
                titulo:'Publicar con excepciones manuales',
                mensaje:'La programación contiene cambios manuales que requieren tu confirmación.',
                detalle:'Revisa las alertas indicadas. Esta confirmación solo acepta excepciones manuales permitidas; los errores bloqueantes de otros meses deben corregirse antes de publicar.',
                aceptar:'Confirmar y publicar', peligro:false,
            });
            if (!ok) return;
            confirmarExcepciones = true;
        } else {
            const ok = await confirmarUI({
                titulo:'Publicar horario',
                mensaje:'¿Confirmas que esta programación ya fue revisada y puede publicarse?',
                detalle:'El horario oficial seguirá siendo la referencia del mes siguiente. Las semanas cerradas se conservarán y sus alertas no bloquearán esta publicación.',
                aceptar:'Publicar', peligro:false
            });
            if (!ok) return;
        }
        const data = await api(`/api/operacion/publicacion/${ultimo.horario_id}`, {method:'POST',body:JSON.stringify({confirmar_excepciones:confirmarExcepciones})});
        const publicadoId = ultimo.horario_id;
        await cargarOpcionesPeriodo(publicadoId);
        await cargarResumenPublicacion();
        await cargarEstadoPeriodo();
        toast(data.mensaje,'success','Horario publicado');
    } catch (e) { toast(e.message,'error','No se pudo publicar'); }
};


let auditoriaItems = [];
function nombreAccionHistorial(accion='') {
    const mapa={
        crear_requerimiento:'Asignación creada', crear_requerimiento_masivo:'Asignación para grupo creada',
        cancelar_requerimiento:'Asignación cancelada', eliminar_requerimiento:'Asignación eliminada', cancelar_grupo_requerimientos:'Asignación para grupo cancelada',
        eliminar_grupo_requerimientos:'Asignación para grupo eliminada', finalizar_requerimiento:'Asignación finalizada',
        crear_solicitud:'Solicitud creada', aprobar_solicitud:'Solicitud aprobada', rechazar_solicitud:'Solicitud rechazada', cancelar_solicitud:'Solicitud cancelada', eliminar_solicitud:'Solicitud eliminada',
        publicar_horario:'Horario publicado', reprogramacion_parcial:'Horario reorganizado', modificar_horario_manual:'Cambio manual de horario', generar_horario:'Horario generado', horario_oficial:'Horario marcado como oficial',
        desactivar_empleado:'Empleado desactivado', reactivar_empleado:'Empleado reactivado', editar_empleado:'Personal modificado', crear_empleado:'Empleado creado', eliminar_empleado_definitivo:'Empleado eliminado definitivamente',
        cambiar_festivo:'Festivo modificado', restaurar_festivo:'Festivo restaurado', crear_backup:'Copia de seguridad creada', restaurar_backup:'Copia restaurada', reiniciar_programacion:'Programación reiniciada', reiniciar_fabrica:'Aplicación restablecida',
        iniciar_sesion:'Inicio de sesión', cerrar_sesion:'Cierre de sesión', cambiar_password:'Contraseña actualizada', establecer_password_usuario:'Contraseña de usuario configurada',
        cerrar_semana:'Semana cerrada', habilitar_semana:'Semana habilitada', cambiar_semana:'Estado de semana actualizado', cambiar_tema:'Apariencia actualizada', cambiar_colores:'Colores actualizados'
    };
    return mapa[accion] || 'Cambio registrado';
}
function nombreEntidadHistorial(entidad='') {
    const mapa={empleado:'Personal',solicitud:'Solicitudes',requerimiento:'Asignaciones',horario:'Horario',semana:'Semanas',festivo:'Festivos',configuracion:'Configuración',operacion:'Sistema',seguridad:'Seguridad',auth:'Seguridad'};
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
    if (x.accion==='cancelar_requerimiento' && d.id) {
        return `<button type="button" class="danger-soft" onclick="eliminarRequerimientoDesdeHistorial(${Number(d.id)})">Eliminar registro</button>`;
    }
    if (x.accion==='cancelar_grupo_requerimientos' && d.grupo_id) {
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


const MESES_ES=['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
// `crearSelectorFecha` se retiró en R12: los tres desplegables de día, mes y
// año quedaron sustituidos por el calendario propio (ver `activarCalendarios`).

function crearSelectorMes(input) {
    if (!input || input.dataset.selectorCreado==='1') return;
    input.dataset.selectorCreado='1'; input.classList.add('native-date-hidden');
    const wrap=document.createElement('div'); wrap.className='date-select-group month-only';
    const sm=document.createElement('select'), sy=document.createElement('select');
    sm.className='date-month'; sy.className='date-year';

    // La programación empieza en agosto de 2026 y no existe nada antes. En vez
    // de dejar elegir enero y corregirlo después con un aviso —que es lo que
    // hacía antes—, los meses anteriores al mínimo sencillamente no se ofrecen.
    const minimo = () => String(input.min || PERIODO_MINIMO || '2026-08');
    const anioMinimo = () => Number(minimo().slice(0, 4));
    const mesMinimo = () => Number(minimo().slice(5, 7));

    const actual=new Date().getFullYear(), hasta=Math.max(2036,actual+10);
    const primerAnio=anioMinimo();
    sy.innerHTML=Array.from({length:hasta-primerAnio+1},(_,i)=>primerAnio+i)
        .map(y=>`<option value="${y}">${y}</option>`).join('');

    function pintarMeses(){
        const anio=Number(sy.value)||primerAnio;
        const desde=anio===anioMinimo() ? mesMinimo() : 1;
        const previo=Number(sm.value)||desde;
        sm.innerHTML=MESES_ES
            .map((m,i)=>({m, n:i+1}))
            .filter(x=>x.n>=desde)
            .map(x=>`<option value="${x.n}">${x.m}</option>`).join('');
        sm.value=String(previo>=desde ? previo : desde);
    }

    function cargar(){
        const m=/^(\d{4})-(\d{2})$/.exec(input.value||'');
        if(m){ sy.value=String(Number(m[1])); pintarMeses(); sm.value=String(Number(m[2])); }
        else { pintarMeses(); }
    }
    function actualizar(){
        pintarMeses();
        let valor=`${sy.value}-${String(sm.value).padStart(2,'0')}`;
        if (valor < minimo()) valor=minimo();
        input.value=valor; cargar(); input.dispatchEvent(new Event('change',{bubbles:true}));
    }
    sm.onchange=actualizar; sy.onchange=actualizar; wrap.append(sm,sy); input.insertAdjacentElement('afterend',wrap); cargar(); input._syncSelectorMes=cargar;
}
function inicializarSelectoresFecha(){
    // Las fechas de día completo ya no usan tres desplegables: las lleva el
    // calendario propio, que muestra el mes entero y evita elegir un día que
    // no existe. Los períodos (mes y año) sí conservan sus desplegables,
    // porque ahí no se elige un día.
    document.querySelectorAll('input[type="month"]').forEach(crearSelectorMes);
}
function sincronizarSelectoresFecha(){
    document.querySelectorAll('input.native-date-hidden').forEach(x=>{ x._syncSelectorMes?.(); });
    document.querySelectorAll('input[type="date"]').forEach(x=>{ x._syncCalendario?.(); });
}

async function cargarCuentasLogin() {
    try {
        const r = await fetch('/api/auth/cuentas-login', {cache:'no-store'});
        const data = await r.json();
        const select = $('login-usuario');
        if (!select) return;
        const previo = select.value;
        select.innerHTML = (data.cuentas || []).map(x => `<option value="${esc(x.usuario)}">${esc(x.nombre)}</option>`).join('');
        if (previo && [...select.options].some(o => o.value === previo)) select.value = previo;
        else if ([...select.options].some(o => o.value === 'katerine')) select.value = 'katerine';
        await rellenarClaveRecordada();
    } catch (_) {
        const select=$('login-usuario');
        if (select) select.innerHTML='<option value="katerine">Katerine Manzanares</option><option value="admin">Administrador</option>';
        await rellenarClaveRecordada();
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
