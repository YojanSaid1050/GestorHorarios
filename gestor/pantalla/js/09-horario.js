// La cuadrícula del mes, las alternativas y generar
// ---------------------------------------------------------------------------
// Parte de la pantalla del Gestor de Horarios. Los archivos de esta carpeta se
// cargan en orden y comparten el mismo ámbito, así que juntos son exactamente
// el app.js de antes. Ver frontend/js/LEEME.md.

'use strict';

function renderHorario(r) {
    const h = r.horario || [];
    if (!h.length) {
        $('tabla-horario').innerHTML = '';
        return;
    }

    const dias = h[0].dias;
    $('tabla-horario').innerHTML = `<thead><tr>
        <th class="employee-name">Nombre</th><th>Área</th><th>Base</th>
        ${dias.map(d => `<th class="${claseColumnaDia(d)}${esLunes(d) ? ' semana-inicio' : ''}" data-fecha="${d.fecha}" title="${esc(tituloDia(d))}"><span class="dia-nombre">${esc(diaCorto(d.dia_semana))}</span><span class="dia-numero">${d.dia}</span>${esOtroMes(d) ? `<span class="dia-mes">${esc(MESES_CORTOS[Math.max(0, Number(d.mes || 1) - 1)] || '')}</span>` : ''}</th>`).join('')}
        <th class="stat-col" title="Horas de las semanas completas del período, del primer lunes al último domingo. Aquí todo el personal queda parejo: es el reparto que el horario equilibra.">Horas<small>del período</small></th>
        <th class="stat-col" title="Horas trabajadas solo en los días del mes natural. Aquí unos tienen más y otros menos según dónde caigan sus descansos, y es normal: el equilibrio se mide sobre el período completo.">Horas<small>del mes</small></th>
        <th class="stat-col" title="Domingos trabajados en el mes">Domingos<small>trabajados</small></th>
        <th class="stat-col" title="Festivos trabajados en el mes">Festivos<small>trabajados</small></th>
        <th class="stat-col" title="Domingos y festivos trabajados frente a los que le corresponden este mes">Especiales<small>hechos de los que tocan</small></th>
    </tr></thead><tbody>${h.map(e => {
        const st = (r.estadisticas || []).find(x => x.empleado_id === e.empleado_id) || {};
        return `<tr>
            <td class="employee-name">${esc(e.nombre)}</td>
            <td>${area(e.area)}</td>
            <td>${e.turno_base}</td>
            ${e.dias.map(d => `<td class="dia-turno shift-${d.turno}${d.es_ultimo_viernes_administrativo && ['ADM-GS','ADM-AC'].includes(d.turno) ? ' admin-friday-cell' : ''}${esOtroMes(d) ? ' otro-mes' : ''}${d.heredado ? ' heredado' : ''}${esLunes(d) ? ' semana-inicio' : ''}" title="${esc(comentarioDia(d))}">${d.turno === 'NV' ? '—' : d.turno}</td>`).join('')}
            <td class="stat-col stat-periodo">${st.horas_periodo ?? st.horas_mes ?? 0} h</td>
            <td class="stat-col">${st.horas_mes || 0} h</td>
            <td class="stat-col">${st.domingos_trabajados || 0}</td>
            <td class="stat-col">${st.festivos_trabajados || 0}</td>
            <td class="stat-col">${st.objetivo_especiales === 'EXENTO'
                ? '<span class="badge badge-ok">Exento</span>'
                : `${st.especiales_trabajados || 0} de ${st.objetivo_especiales ?? '—'}`}</td>
        </tr>`;
    }).join('')}</tbody>`;
}

function etiquetaBotonOficial() {
    // El nombre de ese botón cambia según lo que se haya regenerado («Usar
    // Horario GS y COM como oficial», por ejemplo). Cualquier texto que lo cite
    // tiene que leerlo de aquí: había tres sitios diciendo «Marcar como
    // oficial», que es como se llamaba hace dos versiones.
    const boton = $('hacer-oficial');
    const texto = (boton?.textContent || '').trim();
    return texto && texto !== 'Horario oficial' ? texto : 'Usar esta programación como oficial';
}

function nombreAlternativa(alt, indice = 0) {
    if (!alt) return `Opción ${indice + 1}`;
    if (alt.nombre_alternativa) return String(alt.nombre_alternativa);
    if (alt.historico_base) return 'Base agosto';
    const numero = Number(alt.alternativa || 0);
    if (numero === 1) return 'Mejor opción';
    return numero > 0 ? `Opción ${numero}` : `Opción ${indice + 1}`;
}

function resumenEstadosHorario() {
    const box = $('resumen-estados-horario');
    if (!box) return;
    const oficial = horarioActualReferencia || alternativasActuales.find(x => x?.oficial) || null;
    const publicado = horarioPublicadoReferencia || alternativasActuales.find(x => x?.publicado) || null;
    // «Sin seleccionar» dejaba a medias la información: lo importante es que
    // todavía hay que elegir una de las opciones abiertas.
    const textoOficial = oficial
        ? 'Horario actual'
        : (alternativasActuales.length
            ? `sin elegir · marca una de las ${alternativasActuales.length} opciones`
            : 'sin elegir');
    box.innerHTML = `<span><b>Oficial:</b> ${esc(textoOficial)}</span><span><b>Publicado:</b> ${publicado ? 'Sí' : 'No publicado'}</span>`;
}

function renderHorarioActualReferencia() {
    const box=$('horario-actual-referencia');
    if (!box) return;
    if (!horarioActualReferencia?.horario_id) { box.classList.add('hidden'); box.innerHTML=''; return; }
    box.classList.remove('hidden');
    const viendo=Number(ultimo?.horario_id)===Number(horarioActualReferencia.horario_id);
    box.innerHTML=`<div><strong>Horario actual</strong><span>Es la programación oficial que sigue vigente mientras comparas nuevas opciones.${horarioActualReferencia.publicado ? ' Ya está publicada.' : ''}</span></div><button type="button" class="secondary ${viendo?'active':''}" id="ver-horario-actual">${viendo?'Viendo horario actual':'Ver horario actual'}</button>`;
    $('ver-horario-actual')?.addEventListener('click',()=>{
        ultimo=horarioActualReferencia;
        renderHorario(ultimo);
        renderValidacion(ultimo);
        renderAlternativas(respuestaGeneracion);
        actualizarDisponibilidadExportacion();
    });
}

function renderAlternativas(respuesta) {
    const panel = $('alternativas-panel');
    const lista = $('lista-alternativas');
    const alternativas = (respuesta?.alternativas || []).slice(0,5);
    if (!respuesta && !horarioActualReferencia) {
        panel.classList.add('hidden');
        lista.innerHTML = '';
        if ($('resumen-estados-horario')) $('resumen-estados-horario').innerHTML = '';
        return;
    }

    panel.classList.remove('hidden');
    const explorados=Number(respuesta?.candidatos_explorados || 0);
    const distintos=Number(respuesta?.candidatos_validos_distintos || 0);
    $('texto-alternativas').textContent = respuesta?.mensaje || (alternativas.length
        ? `${alternativas.length} mejores opciones disponibles.${explorados ? ` Se exploraron ${explorados} candidatos y ${distintos} fueron válidos y diferentes.` : ''}`
        : 'No hay opciones nuevas pendientes. Puedes consultar el horario actual.');
    renderHorarioActualReferencia();
    lista.innerHTML = alternativas.map((alt, i) => {
        const activa = Number(alt?.horario_id) === Number(ultimo?.horario_id);
        const badges = [
            activa ? '<span class="alternative-state viewing">VIENDO</span>' : '',
            alt.oficial ? '<span class="alternative-state official-state">OFICIAL</span>' : '',
            alt.publicado ? '<span class="alternative-state published-state">PUBLICADO</span>' : '',
        ].filter(Boolean).join('');
        return `<button type="button"
            class="alternative-button ${activa ? 'active' : ''} ${alt.oficial ? 'official' : ''} ${alt.publicado ? 'published' : ''}"
            onclick="seleccionarAlternativa(${i})">
            <span class="alternative-name">${esc(nombreAlternativa(alt, i))}${descripcionCumplimiento(alt) ? `<small>${esc(descripcionCumplimiento(alt))}</small>` : ''}</span>
            <span class="alternative-states">${badges}</span>
        </button>`;
    }).join('');

    const esOficial = !!ultimo?.oficial;
    const esPublicado = !!ultimo?.publicado;
    const [anioActual, mesActual] = ($('periodo')?.value || '').split('-').map(Number);
    const agostoHistorico = anioActual === 2026 && mesActual === 8;
    $('hacer-oficial').disabled = esOficial || (!ultimo?.valido && !agostoHistorico) || !ultimo?.horario_id;
    const areasCambio = (ultimo?.areas_actualizadas || []).map(a => AREAS_UI[a]?.sigla || AREAS_UI[a]?.nombre || a);
    const etiquetaCambio = areasCambio.length && areasCambio.length < 3 ? `Horario ${areasCambio.join(' y ')}` : 'esta programación';
    // El nombre del botón cambia según lo que se haya regenerado, así que
    // cualquier texto que lo cite tiene que leerlo de aquí y no escribirlo a
    // mano. Había tres sitios diciendo «Marcar como oficial», que es como se
    // llamaba hace dos versiones.
    $('hacer-oficial').textContent = esOficial ? 'Horario oficial' : `Usar ${etiquetaCambio} como oficial`;
    $('publicar-horario').disabled = !esOficial || esPublicado || !ultimo?.horario_id;
    $('publicar-horario').textContent = esPublicado ? 'Horario publicado' : 'Publicar horario';
    const quitar = $('quitar-oficial');
    if (quitar) {
        // Solo tiene sentido ofrecerlo sobre el horario oficial y sin publicar.
        quitar.classList.toggle('hidden', !esOficial || esPublicado);
        quitar.disabled = !esOficial || esPublicado || !ultimo?.horario_id;
    }

    if (esOficial && esPublicado) {
        $('estado-oficial').textContent = 'Sin acciones pendientes para esta versión.';
    } else if (esOficial) {
        $('estado-oficial').textContent = 'Cuando termines de revisarla, puedes publicarla.';
    } else if (esPublicado) {
        $('estado-oficial').textContent = 'Esta versión fue publicada anteriormente; revisa cuál está marcada como oficial.';
    } else {
        $('estado-oficial').textContent = 'Revisa esta alternativa y márcala como oficial únicamente si deseas usarla como base del mes.';
    }
    resumenEstadosHorario();
    cargarResumenPublicacion().catch(()=>{});
}

window.seleccionarAlternativa = indice => {
    const alt = alternativasActuales[indice];
    if (!alt) return;
    ultimo = alt;
    renderHorario(ultimo);
    renderValidacion(ultimo);
    actualizarDisponibilidadExportacion();
    renderAlternativas(respuestaGeneracion);
    cargarSemanasBloqueo().catch(()=>{});
};

async function cargarOpcionesPeriodo(preferirHorarioId = null, mensaje = '') {
    const {anio, mes} = periodo();
    const data = await api(`/api/horarios/opciones/${anio}/${mes}`);
    const opciones = (data?.alternativas || []).slice(0,5);
    horarioActualReferencia = data?.horario_actual || data?.horario_oficial || null;
    horarioPublicadoReferencia = data?.horario_publicado || null;
    alternativasActuales = opciones;
    respuestaGeneracion = {
        alternativas: opciones,
        oficial_id: data?.oficial_id || null,
        publicado_id: data?.publicado_id || null,
        grupo_id: data?.grupo_id || null,
        horario_actual: horarioActualReferencia,
        horario_publicado: horarioPublicadoReferencia,
        candidatos_explorados: data?.candidatos_explorados || 0,
        candidatos_validos_distintos: data?.candidatos_validos_distintos || opciones.length,
        mensaje: mensaje || (opciones.length
            ? (data?.hay_opciones_pendientes ? 'Hay opciones optimizadas nuevas para comparar con el horario actual.' : `${opciones.length} opción(es) optimizadas guardadas para este período.`)
            : 'No hay opciones nuevas pendientes. El horario actual se muestra como referencia.'),
    };
    ultimo = opciones.find(x => Number(x.horario_id) === Number(preferirHorarioId))
        || (preferirHorarioId && Number(horarioActualReferencia?.horario_id) === Number(preferirHorarioId) ? horarioActualReferencia : null)
        || opciones[0]
        || horarioActualReferencia
        || horarioPublicadoReferencia
        || null;
    if (!ultimo) {
        limpiarProgramacionVisible();
        horarioActualReferencia=null; horarioPublicadoReferencia=null;
        actualizarAccionGenerar();
        return null;
    }
    renderHorario(ultimo);
    renderValidacion(ultimo);
    renderAlternativas(respuestaGeneracion);
    actualizarDisponibilidadExportacion();
    actualizarAccionGenerar();
    return ultimo;
}


$('hacer-oficial').onclick = async () => {
    if (!ultimo?.horario_id) {
        toast('Selecciona primero una alternativa guardada.', 'warning', 'Sin alternativa');
        return;
    }
    const horarioId = ultimo.horario_id;
    const ok = await confirmarUI({
        titulo: 'Marcar como horario oficial',
        mensaje: '¿Quieres usar esta alternativa como el horario oficial del mes?',
        detalle: 'El horario oficial es la referencia que usa la aplicación para continuar al mes siguiente. Publicarlo es un paso separado que confirma que ya fue revisado y comunicado.',
        aceptar: 'Marcar como oficial',
        peligro: false,
    });
    if (!ok) return;
    await oficializar(horarioId, false);
};

// Cada mes se calcula desde el oficial del anterior, así que cambiar este
// deshace los siguientes. Cuando alguno ya está publicado —la gente trabaja con
// él— se pregunta antes, con los meses por delante, en vez de deshacerlo en
// silencio.
async function oficializar(horarioId, confirmarCadena) {
    try {
        const data = await api(`/api/horarios/${horarioId}/oficial`, {
            method: 'PATCH',
            body: JSON.stringify({confirmar_cadena: !!confirmarCadena}),
        });
        await cargarOpcionesPeriodo(horarioId);
        await cargarEmpleados();
        await cargarEstadoPeriodo();
        await cargarResumenPublicacion();
        const deshechos = data.periodos_deshechos || [];
        toast(data.mensaje, deshechos.length ? 'warning' : 'success',
              deshechos.length ? 'Oficial actualizado · hay meses por rehacer' : 'Horario oficial actualizado');
    } catch (e) {
        if (!confirmarCadena && e.detalle?.requiere_confirmacion) {
            const meses = (e.detalle.periodos_afectados || []);
            const publicados = meses.filter(m => m.publicado).map(m => m.nombre);
            const resto = meses.filter(m => !m.publicado).map(m => m.nombre);
            const partes = [];
            if (publicados.length) partes.push(`Dejará de estar publicado: ${listaLegible(publicados)}.`);
            if (resto.length) partes.push(`Perderá el carácter oficial: ${listaLegible(resto)}.`);
            partes.push('Habrá que volver a generar esos meses y, los que estuvieran publicados, volver a comunicarlos.');
            const seguir = await confirmarUI({
                titulo: 'Hay meses posteriores que dependen de este',
                mensaje: e.message,
                detalle: partes.join(' '),
                aceptar: 'Entiendo, marcar como oficial',
                peligro: true,
            });
            if (seguir) await oficializar(horarioId, true);
            return;
        }
        toast(e.message, 'error', 'No se pudo marcar como oficial');
    }
}

function listaLegible(nombres) {
    if (!nombres.length) return '';
    if (nombres.length === 1) return nombres[0];
    return `${nombres.slice(0, -1).join(', ')} y ${nombres[nombres.length - 1]}`;
}

$('quitar-oficial').onclick = async () => {
    if (!ultimo?.horario_id) return;
    const horarioId = ultimo.horario_id;
    const ok = await confirmarUI({
        titulo: 'Quitar el carácter oficial',
        mensaje: '¿Dejar este mes sin horario oficial?',
        detalle: 'La programación no se borra: sigue estando entre las opciones del mes. Solo deja de ser la referencia que la aplicación usa para continuar al mes siguiente, para que puedas elegir otra con calma.',
        aceptar: 'Quitar carácter oficial',
        peligro: true,
    });
    if (!ok) return;
    try {
        const data = await api(`/api/horarios/${horarioId}/oficial`, {method: 'DELETE'});
        await cargarOpcionesPeriodo(horarioId);
        await cargarEstadoPeriodo();
        await cargarResumenPublicacion().catch(()=>{});
        toast(data.mensaje, 'success', 'Mes sin horario oficial');
    } catch (e) {
        toast(e.message, 'error', 'No se pudo quitar el carácter oficial');
    }
};

async function refrescarVistasTrasGenerar() {
    const errores = [];
    for (const [nombre, tarea] of [
        ['personal', cargarEmpleados],
        ['estado del período', cargarEstadoPeriodo],
        ['semanas del mes', cargarSemanasBloqueo],
    ]) {
        try { await tarea(); }
        catch (e) {
            console.error(`No se pudo refrescar ${nombre} después de generar:`, e);
            errores.push(`${nombre}: ${e.message}`);
        }
    }
    return errores;
}

async function ejecutarGeneracionHorario(modo = 'inicial') {
    const idBoton = modo === 'pendientes' ? 'regenerar-pendientes' : 'generar';
    const btnGenerar=$(idBoton);
    if (btnGenerar?.dataset.busy === '1') return;
    const hayHorario = alternativasActuales.length > 0 || !!ultimo?.horario_id;
    // Crear por primera vez y volver a crear opciones son la misma operación
    // vista desde dos momentos distintos. Antes la segunda quedaba bloqueada por
    // un aviso, y el botón parecía roto: se pulsaba y no pasaba nada.
    if (modo === 'inicial' && hayHorario) modo = 'alternativas';
    const [anio, mes] = $('periodo').value.split('-').map(Number);
    ponerBotonOcupado(btnGenerar,true,'Generando opciones…');
    try {
        const tieneSemanasCerradas = semanasEstadoActual.some(x => x.bloqueada);
        const textoEstado = modo === 'pendientes'
            ? (tieneSemanasCerradas ? 'Recalculando solo semanas habilitadas…' : 'Aplicando cambios pendientes al horario…')
            : modo === 'alternativas'
                ? 'Buscando nuevas alternativas sin borrar la programación actual…'
                : 'Buscando las 5 mejores opciones de horario…';
        setEstado(textoEstado, 'working');
        const horarioOficial = alternativasActuales.find(x => x?.oficial) || horarioActualReferencia;
        const baseId = horarioOficial?.horario_id || ultimo?.horario_id || null;
        // Aplicar cambios pendientes recalcula ÚNICAMENTE las áreas marcadas y
        // copia las demás tal cual. Antes se rehacía el mes entero, así que un
        // permiso de una persona podía mover turnos de las otras dos áreas.
        const areasPendientes = Object.entries(estadoPeriodoActual?.areas || {})
            .filter(([, x]) => x?.requiere_actualizacion)
            .map(([a]) => a);
        const parcialPorArea = modo === 'pendientes' && baseId && areasPendientes.length
            && areasPendientes.length < 3;
        const generada = parcialPorArea
            ? await api('/api/horarios/generar-areas', {
                method: 'POST',
                body: JSON.stringify({mes, anio, horario_id: baseId, areas: areasPendientes}),
            })
            : await api('/api/horarios/generar', {
                method: 'POST',
                body: JSON.stringify({mes, anio, horario_id: baseId}),
            });
        const nuevas = generada.alternativas || [];
        if (nuevas.length) {
            const primera = nuevas[0]?.horario_id || null;
            await cargarOpcionesPeriodo(primera, generada.mensaje || 'Se generaron nuevas alternativas para revisar.');
            const parcial = !!generada.parcial_automatico;
            toast(
                generada.completo
                    ? (parcial
                        ? 'Se recalcularon solamente las semanas habilitadas. Las semanas cerradas quedaron exactamente como estaban.'
                        : 'Se seleccionaron las cinco mejores opciones encontradas. Compara el Top 5 y marca la que quieras usar como horario oficial.')
                    : generada.mensaje,
                generada.completo ? 'success' : 'warning',
                generada.completo ? (parcial ? 'Semanas editables regeneradas' : 'Top 5 listo') : 'Alternativas limitadas'
            );
        } else {
            // Que no salga una alternativa nueva no borra el horario que ya
            // estaba: si el mes tenía uno oficial, sigue siendo el vigente y
            // debe continuar en pantalla. Antes se perdía la referencia y la
            // aplicación decía que el mes no tenía horario.
            const diagnostico = generada.diagnostico || null;
            const conservado = ultimo?.horario?.length ? ultimo : null;
            ultimo = conservado || diagnostico;
            renderHorario(conservado || diagnostico || {horario: []});
            renderValidacion(diagnostico || {errores: ['No fue posible crear una alternativa válida.'], advertencias: []});
            renderAlternativas(null);
            actualizarDisponibilidadExportacion();
            toast(
                (generada.mensaje || 'Ninguna variante pudo cumplir todas las reglas. Revisa Validación y las solicitudes aprobadas.')
                + (conservado ? ' El horario que ya estaba sigue siendo el vigente.' : ''),
                'warning', 'Sin alternativa válida');
        }
        setEstado('Alternativas listas', 'success', 1400);
        const erroresRefresco = await refrescarVistasTrasGenerar();
        if (erroresRefresco.length) {
            toast(`El horario sí fue generado. Una vista secundaria necesita actualizarse: ${erroresRefresco.join(' · ')}`, 'warning', 'Horario generado con aviso');
        }
        document.querySelector('[data-tab="horario"]').click();
    } catch (e) {
        setEstado(modo === 'inicial' ? 'No se pudo generar' : 'No se pudo actualizar', 'error', 2200);
        toast(e.message, 'error', modo === 'inicial' ? 'No se pudo generar el horario' : 'No se pudo actualizar el horario');
    } finally {
        ponerBotonOcupado(btnGenerar,false);
        actualizarAccionGenerar();
        renderEstadoAreas(estadoPeriodoActual);
    }
}

$('generar').onclick = () => ejecutarGeneracionHorario('inicial');
// Envuelto en una flecha a propósito: `ejecutarRegeneracionPendientes` se
// declara en 13-modificar.js, que carga después de este archivo. Pasar la
// función directamente la buscaría ahora, cuando todavía no existe; dentro
// de la flecha se busca al pulsar, con todo ya cargado.
$('regenerar-pendientes')?.addEventListener('click', () => ejecutarRegeneracionPendientes());

let ultimaRutaExportada = null;
let exportacionDialogoNativo = null;
const CLAVE_ULTIMA_EXPORTACION = 'gestorhorarios_ultima_exportacion';
