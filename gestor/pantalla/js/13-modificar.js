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
        // `detalles`, que es como lo manda `gestor/servicios/edicion.py`. Con
        // los nombres de antes, un cambio aplicado como excepción decía
        // «Aplicado con excepción» y **no decía excepción de qué**.
        const detalles = x.detalles || [];
        const estado = x.estado || 'revisar';
        // Los tres estados que el servidor emite de verdad son `no_aplicado`,
        // `forzado` y `aplicado`. `no_aplicado` —el más importante de los tres,
        // porque es el cambio que NO se pudo poner— no estaba en esta lista:
        // caía en «Revisar», con la misma pinta gris que todo lo demás.
        const titulosEstado = {
            no_aplicado: 'No se pudo aplicar',
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
