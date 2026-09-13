// Las novedades que pide la gente
// ---------------------------------------------------------------------------
// Parte de la pantalla del Gestor de Horarios. Los archivos de esta carpeta se
// cargan en orden y comparten el mismo ámbito, así que juntos son exactamente
// el app.js de antes. Ver frontend/js/LEEME.md.

'use strict';

async function cargarSolicitudes() {
    solicitudes = await api('/api/solicitudes');
    renderSolicitudes();
}

// Qué solicitudes son de este mes. Una solicitud con fechas entra si alguno de
// sus días cae dentro del periodo; una repetición sin fecha de fin —«los martes
// de cada semana, hasta eliminar»— entra desde el mes en que empezó y en todos
// los siguientes, porque sigue vigente.
function solicitudDelPeriodo(s) {
    if (verTodosLosMeses) return true;
    const r = rangoDelPeriodo();
    if (!r) return true;
    if (s.sin_fecha_fin) return String(s.fecha_inicio || '').slice(0, 10) <= r.hasta;
    return tocaElPeriodo([s.fecha_inicio, s.fecha_fin]);
}

function renderSolicitudes() {
    if (!Array.isArray(solicitudes)) return;
    actualizarContadoresMenu();
    renderBarrasPeriodo();
    const tb = $('tabla-solicitudes')?.querySelector('tbody');
    if (!tb) return;
    const diasNombre = ['Lun','Mar','Mié','Jue','Vie','Sáb','Dom'];

    const vigentes = solicitudes.filter(s => ['pendiente','aprobada'].includes(s.estado_efectivo || s.estado || (s.aprobada ? 'aprobada' : 'pendiente')));
    const solicitudesVisibles = vigentes.filter(solicitudDelPeriodo);
    const ocultas = vigentes.length - solicitudesVisibles.length;
    tb.innerHTML = solicitudesVisibles.map(s => {
        const persona = s.tipo === 'cambio_persona'
            ? s.intercambio_nombre
            : ['turno_dia','turno_semanas'].includes(s.tipo)
                ? `→ ${s.turno_solicitado || ''}`
                : s.modo_cobertura === 'reemplazar'
                    ? s.reemplazo_nombre
                    : '—';

        let fechas = fechaBonita(s.fecha_inicio);
        const vencida = !s.sin_fecha_fin && s.fecha_fin < ymd(new Date());
        if (s.tipo === 'turno_dia' && s.modo_periodo === 'semanal') {
            const dia = diasNombre[Number(s.dia_semana_recurrente)] || '';
            fechas = s.sin_fecha_fin ? `${dia} de cada semana · hasta eliminar` : `${dia} de cada semana · ${s.fecha_inicio.slice(0,7)}`;
        } else if (s.tipo === 'turno_semanas') {
            fechas = `Semanas: ${fechaBonita(s.fecha_inicio)} a ${fechaBonita(s.fecha_fin)}`;
        } else if (s.fecha_fin !== s.fecha_inicio) {
            fechas += ' a ' + fechaBonita(s.fecha_fin);
        }

        return `<tr class="${vencida ? 'row-expired' : ''}">
            <td>${esc(s.empleado_nombre)}</td>
            <td>${esc(nombreSolicitud(s.tipo))}</td>
            <td>${esc(persona || '—')}</td>
            <td>${esc(fechas)}</td>
            <td>${(() => { const st=s.estado_efectivo || s.estado || (s.aprobada?'aprobada':'pendiente'); const map={aprobada:'Aprobada',pendiente:'Pendiente',rechazada:'Rechazada',cancelada:'Cancelada',finalizada:'Finalizada',vencida:'Vencida'}; const cls=st==='aprobada'?'badge-ok':(st==='pendiente'?'badge-new':'badge-expired'); return `<span class="badge ${cls}">${map[st]||st}</span>`; })()}</td>
            <td class="table-actions">
                ${(s.estado_efectivo||s.estado)==='pendiente' ? `<button onclick="aprobar(${s.id})">Aprobar</button><button onclick="rechazar(${s.id})" class="secondary">Rechazar</button>` : ''}
                ${['pendiente','aprobada'].includes(s.estado_efectivo||s.estado) ? `<button onclick="cancelarSolicitud(${s.id})" class="secondary">Cancelar</button>` : ''}
                <button onclick="borrarSolicitud(${s.id})" class="danger-soft">Eliminar</button>
            </td>
        </tr>`;
    }).join('') || `<tr><td colspan="6">${
        verTodosLosMeses
            ? 'No hay ninguna solicitud registrada.'
            : `No hay solicitudes para ${esc(nombreDelPeriodo())}.${ocultas ? ` Hay ${ocultas} en otros meses: cámbialo arriba o marca «Ver todos los meses».` : ''}`
    }</td></tr>`;
    const nota = $('solicitudes-otros-meses');
    if (nota) {
        nota.textContent = (!verTodosLosMeses && ocultas)
            ? `Hay ${ocultas} solicitud(es) más en otros meses. No se han borrado: cambia de mes para verlas.`
            : '';
        nota.classList.toggle('hidden', !(!verTodosLosMeses && ocultas));
    }
}


function nombreRequerimiento(t) {
    return {
        actividad: 'Actividad asignada',
        asignacion_administrativa: 'Asignación administrativa temporal',
        descanso_extra: 'Día de descanso',
        excepcion_turno: 'Excepción de turno AM/PM',
    }[t] || t;
}


function textoRangoFechas(inicio, fin) {
    if (!inicio) return 'Selecciona una fecha.';
    const a = fechaLocal(inicio);
    const b = fechaLocal(fin || inicio);
    if (b < a) return 'La fecha final debe ser posterior o igual a la inicial.';
    const dias = Math.round((b - a) / 86400000) + 1;
    const fmt = d => d.toLocaleDateString('es-CO', {weekday:'short', day:'numeric', month:'short', year:'numeric'});
    return dias === 1 ? fmt(a) : `${fmt(a)} → ${fmt(b)} · ${dias} días`;
}

function actualizarResumenFechas() {
    const si = $('solicitud-inicio')?.value;
    const sf = $('solicitud-fin')?.value || si;
    if ($('solicitud-resumen-fechas')) $('solicitud-resumen-fechas').textContent = textoRangoFechas(si, sf);
    const ri = $('requerimiento-inicio')?.value;
    const rf = $('requerimiento-fin')?.value || ri;
    if ($('requerimiento-resumen-fechas')) $('requerimiento-resumen-fechas').textContent = textoRangoFechas(ri, rf);
}

function aplicarFinPorDias(inicioId, finId, dias) {
    const inicio = $(inicioId)?.value;
    if (!inicio) { toast('Primero selecciona la fecha inicial.', 'info', 'Selecciona una fecha'); return; }
    $(finId).value = sumarDiasIso(inicio, Number(dias) - 1);
    sincronizarSelectoresFecha();
    actualizarResumenFechas();
}

function fechasEntre(inicio, fin) {
    if (!inicio) return [];
    const a = fechaLocal(inicio);
    const b = fechaLocal(fin || inicio);
    if (b < a) throw new Error('La fecha final no puede ser anterior a la inicial.');
    const out = [];
    const d = new Date(a);
    while (d <= b) {
        out.push(ymd(d));
        d.setDate(d.getDate() + 1);
        if (out.length > 366) throw new Error('El rango no puede superar 366 días.');
    }
    return out;
}


function objetivosRequerimiento() {
    const alcance = $('requerimiento-alcance')?.value || 'persona';
    if (alcance === 'todos') return [...empleados];
    if (alcance === 'area') {
        const a = $('requerimiento-area')?.value;
        return empleados.filter(x => x.area === a);
    }
    const e = empleados.find(x => Number(x.id) === Number($('requerimiento-empleado')?.value));
    return e ? [e] : [];
}

function configurarAlcanceRequerimiento() {
    const tipoReq = $('requerimiento-tipo')?.value;
    const editando = !!$('requerimiento-id')?.value;
    // V13.2.0: todos los tipos de asignación admiten alcance por área o para
    // todo el personal. El backend prevalida persona a persona y además revisa
    // los conflictos del grupo completo, así que no hace falta limitar la
    // excepción de turno ni el día de descanso a una sola persona.
    const permiteMasivo = !editando && ['actividad','asignacion_administrativa','excepcion_turno','descanso_extra'].includes(tipoReq);
    const alcance = $('requerimiento-alcance');
    if (!permiteMasivo) alcance.value = 'persona';
    alcance.disabled = !permiteMasivo;
    const valor = alcance.value;
    $('g-requerimiento-area')?.classList.toggle('hidden', valor !== 'area');
    $('g-requerimiento-empleado')?.classList.toggle('hidden', valor !== 'persona');
    $('requerimiento-empleado').required = valor === 'persona';
    const ayuda = alcance.parentElement?.querySelector('small');
    if (ayuda) ayuda.textContent = permiteMasivo
        ? 'Puedes elegir una persona, un área entera o a todo el mundo. Antes de guardar se comprueba una por una, y te dice si alguna no puede.'
        : 'Al editar una asignación existente solo se modifica la persona a la que ya pertenece.';
}

function configurarHorarioRequerimiento() {
    configurarAlcanceRequerimiento();
    const objetivos = objetivosRequerimiento();
    const alcance = $('requerimiento-alcance')?.value || 'persona';
    const masivo = alcance !== 'persona';
    const e = objetivos.length === 1 ? objetivos[0] : null;
    const tipoReq = $('requerimiento-tipo')?.value;
    const descripcionReq = $('requerimiento-descripcion');
    if (descripcionReq) descripcionReq.required = false;
    const esDescanso = tipoReq === 'descanso_extra';
    const esExcepcion = tipoReq === 'excepcion_turno';
    $('g-requerimiento-horario')?.classList.toggle('hidden', esDescanso);

    if (objetivos.length && !esDescanso) {
        const sel = $('requerimiento-horario');
        const valorPrevio = sel.value;
        if (esExcepcion) {
            sel.innerHTML = '<option value="AM">AM · Excepción operativa</option><option value="PM">PM · Excepción operativa</option>';
        } else if (esDescanso) {
            sel.innerHTML = '<option value="">No aplica</option>';
        } else if (masivo) {
            const todosOperativos = objetivos.every(x => x.tipo_turno !== 'administrativo');
            if (tipoReq === 'actividad') {
                sel.innerHTML = (todosOperativos
                    ? '<option value="OPERATIVO">Mantener el turno programado de cada persona</option><option value="AM">AM para todo el grupo</option><option value="PM">PM para todo el grupo</option>'
                    : '') + '<option value="ADM-AUTO">Horario administrativo correspondiente a cada área</option>';
            } else {
                sel.innerHTML = '<option value="ADM-AUTO">Horario administrativo correspondiente a cada área</option>';
            }
        } else if (tipoReq === 'actividad' && e.tipo_turno !== 'administrativo') {
            const adm = e.area === 'atencion_ciudadano'
                ? '<option value="ADM-GS">ADM-GS · Administrativo Guía Social</option><option value="ADM-AC">ADM-AC · Administrativo especial Atención al Ciudadano</option>'
                : '<option value="ADM-GS">ADM-GS · Administrativo Guía Social</option>';
            sel.innerHTML = '<option value="OPERATIVO">Mantener el turno programado de ese día</option><option value="AM">AM</option><option value="PM">PM</option>' + adm;
        } else if (e.area === 'gestion_social') {
            sel.innerHTML = '<option value="ADM-GS">ADM-GS · Administrativo Guía Social</option>';
        } else if (e.area === 'atencion_ciudadano') {
            sel.innerHTML = e.tipo_turno === 'administrativo'
                ? '<option value="ADM-AC">ADM-AC · Administrativo especial Atención al Ciudadano</option>'
                : '<option value="ADM-GS">ADM-GS · Administrativo Guía Social</option><option value="ADM-AC">ADM-AC · Administrativo especial Atención al Ciudadano</option>';
        } else if (e.area === 'comunicaciones') {
            sel.innerHTML = '<option value="ADM-GS">ADM-GS · Administrativo Guía Social</option>';
        } else {
            sel.innerHTML = '<option value="">No aplica</option>';
        }
        if ([...sel.options].some(o => o.value === valorPrevio)) sel.value = valorPrevio;
    }

    let modoFechas = $('requerimiento-modo-fechas')?.value;
    const recurrenteDisponible = esExcepcion;
    const optRec = [...$('requerimiento-modo-fechas').options].find(o => o.value === 'recurrente');
    if (optRec) optRec.hidden = !recurrenteDisponible;
    if (modoFechas === 'recurrente' && !recurrenteDisponible) {
        $('requerimiento-modo-fechas').value = 'uno';
        modoFechas = 'uno';
    }
    const varios = modoFechas === 'varios';
    const recurrente = modoFechas === 'recurrente';
    $('g-requerimiento-inicio')?.classList.remove('hidden');
    $('g-requerimiento-fin')?.classList.toggle('hidden', !varios || recurrente);
    $('g-requerimiento-dias-semana')?.classList.toggle('hidden', !recurrente);
    $('requerimiento-inicio').required = true;
    const inicioLabel = $('requerimiento-inicio-label');
    const inicioAyuda = $('requerimiento-inicio-ayuda');
    if (inicioLabel) inicioLabel.textContent = recurrente ? 'Inicio de vigencia' : 'Fecha';
    if (inicioAyuda) inicioAyuda.textContent = recurrente
        ? 'Desde esta fecha se aplica cada semana en los días seleccionados, hasta que canceles o elimines la asignación.'
        : varios ? 'Primer día del rango de aplicación.' : 'Día en que se aplicará esta asignación.';
    if (!varios && !recurrente && $('requerimiento-inicio')?.value) $('requerimiento-fin').value = $('requerimiento-inicio').value;
    actualizarResumenFechas();

    const horarioLabel = $('g-requerimiento-horario');
    if (horarioLabel) {
        horarioLabel.childNodes[0].nodeValue = esExcepcion ? 'Turno de la excepción ' : (tipoReq === 'actividad' ? 'Horario de la actividad ' : 'Horario administrativo ');
    }
    const admGs = !masivo && !esDescanso && !esExcepcion && $('requerimiento-horario')?.value === 'ADM-GS';
    let mostrarCobertura = admGs;
    const fecha = $('requerimiento-inicio')?.value;
    let ayuda = 'Una jornada administrativa suele ocupar el turno de mañana. Si esa persona era la única de tarde y no quieres poner a nadie en su lugar, la propia jornada administrativa cubre la tarde.';
    if (admGs && e && fecha && ultimo?.horario?.length) {
        const visible = ultimo.horario.find(x => Number(x.empleado_id) === Number(e.id))?.dias?.find(d => d.fecha === fecha);
        if (visible?.turno === 'AM') {
            mostrarCobertura = false;
            $('requerimiento-cobertura').value = 'no';
            ayuda = 'La programación visible muestra AM: ADM-GS sustituirá esa cobertura y PM quedará intacto.';
        } else if (visible?.turno === 'PM') {
            const otrosPm = (ultimo.horario || [])
                .filter(x => x.area === 'gestion_social' && Number(x.empleado_id) !== Number(e.id))
                .filter(x => {
                    const d = x.dias?.find(y => y.fecha === fecha);
                    return d?.turno === 'PM' || (d?.turno === 'ADM-GS' && d?.cobertura_operativa === 'PM');
                }).length;
            if (otrosPm >= 1) {
                mostrarCobertura = false;
                $('requerimiento-cobertura').value = 'no';
                ayuda = 'Ya existe otra cobertura PM; no hace falta seleccionar reemplazo.';
            } else {
                ayuda = 'Esta persona es la única PM visible. Puedes dejar que ADM-GS conserve PM o seleccionar una persona para cubrir PM.';
            }
        }
    }
    $('g-requerimiento-cobertura')?.classList.toggle('hidden', !mostrarCobertura);
    if ($('requerimiento-cobertura-ayuda')) $('requerimiento-cobertura-ayuda').textContent = ayuda;

    const requiereReemplazo = mostrarCobertura && $('requerimiento-cobertura')?.value === 'si';
    $('g-requerimiento-reemplazo')?.classList.toggle('hidden', !requiereReemplazo);
    if ($('requerimiento-reemplazo')) {
        const candidatos = e ? empleados.filter(x => x.id !== e.id && x.area === e.area && x.tipo_turno !== 'administrativo') : [];
        const actual = $('requerimiento-reemplazo').value;
        $('requerimiento-reemplazo').innerHTML = opts(candidatos, 'Seleccionar persona');
        if ([...$('requerimiento-reemplazo').options].some(o => o.value === actual)) $('requerimiento-reemplazo').value = actual;
    }
    actualizarPasosVisibles();
}
