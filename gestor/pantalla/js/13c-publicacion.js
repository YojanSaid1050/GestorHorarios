// 13c-publicacion.js · Ver LEEME.md para el contrato de carga.
'use strict';

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
