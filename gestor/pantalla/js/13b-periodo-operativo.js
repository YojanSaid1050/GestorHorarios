// 13b-periodo-operativo.js · Ver LEEME.md para el contrato de carga.
'use strict';

const AREAS_UI = {
    gestion_social: {estado:'estado-area-gs', nombre:'Gestión Social', sigla:'GS'},
    comunicaciones: {estado:'estado-area-com', nombre:'Comunicaciones', sigla:'COM'},
    atencion_ciudadano: {estado:'estado-area-ac', nombre:'Atención al Ciudadano', sigla:'AC'},
};

function hayCambiosPendientesDe(origen) {
    return contarCambiosPendientesDe(origen) > 0;
}

// Cuántos cambios pendientes vienen de las solicitudes y cuántos de las
// asignaciones.
//
// Se mira `origen`, que es el único campo que el servidor pone de verdad en
// cada razón, junto con `mensaje` (ver `gestor/servicios/periodos.py`). Antes
// se buscaban `tipo`, `solicitud_id`, `requerimiento_id` y `grupo_id`, que no
// existen en ninguna parte del programa: esta función **devolvía cero siempre**.
//
// Cero aquí no se notaba como un fallo, se notaba como cuatro botones
// apagados: los dos de «actualizar desde…» y los dos de «aplicar…» quedaban
// deshabilitados para siempre, y su globo de ayuda decía que no había cambios
// pendientes mientras la pestaña de al lado avisaba de que sí los había.
function contarCambiosPendientesDe(origen) {
    const deEsteOrigen = origen === 'solicitudes'
        ? ['solicitudes']
        : ['asignaciones', 'requerimientos'];
    const razones = Object.values(estadoPeriodoActual?.areas || {})
        .filter(x => x?.requiere_actualizacion)
        .flatMap(x => x?.razones || [])
        .filter(r => r?.mostrar_en_estado !== false)
        .filter(r => deEsteOrigen.includes(String(r?.origen || '')));
    // Sin repetir: el servidor ya evita apuntar dos veces el mismo motivo, pero
    // la misma razón aparece una vez por área y aquí se juntan las tres.
    return new Set(razones.map(r => `${r.origen}:${r.mensaje || ''}`)).size;
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
