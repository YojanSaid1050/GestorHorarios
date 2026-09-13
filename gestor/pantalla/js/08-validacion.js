// Qué salió bien, qué pide una decisión y qué no
// ---------------------------------------------------------------------------
// Parte de la pantalla del Gestor de Horarios. Los archivos de esta carpeta se
// cargan en orden y comparten el mismo ámbito, así que juntos son exactamente
// el app.js de antes. Ver frontend/js/LEEME.md.

'use strict';

function fechaBonita(iso) {
    if (!iso) return '';
    const [y,m,d] = iso.split('-');
    return `${d}/${m}/${y}`;
}

function explicar(msg) {
    const texto = String(msg || '').toLowerCase();
    let categoria = 'Regla general';
    let sugerencia = 'Revisa la configuración o la solicitud indicada y vuelve a generar. Si solo puede resolverse fuera del sistema, modifica una copia exportada del Excel; ese cambio manual no se conservará como continuidad.';

    if (texto.includes('gestión social tiene') || texto.includes('gestión social queda')) {
        categoria = 'Cobertura · Gestión Social';
        sugerencia = 'Debe quedar mínimo 1 persona AM y 1 PM. Mueve un descanso/novedad, elige un reemplazo compatible o modifica un turno sin dejar AM o PM en cero.';
    } else if (texto.includes('comunicaciones queda sin pm')) {
        categoria = 'Cobertura · Comunicaciones';
        sugerencia = 'Debe quedar al menos 1 persona PM. Reubica un descanso o usa un reemplazo de Comunicaciones.';
    } else if (texto.includes('días especiales') || texto.includes('domingo') || texto.includes('festivo')) {
        categoria = 'Domingos / festivos';
        sugerencia = 'Los domingos se equilibran por separado. Cada festivo es un descanso adicional: si la persona trabaja el festivo, debe aparecer un descanso compensatorio distinto del descanso semanal.';
    } else if (texto.includes('pareja') || texto.includes('pc')) {
        categoria = 'Pareja de PC';
        sugerencia = 'Revisa la pareja en Personal y evita que ambos coincidan en el mismo AM/PM.';
    } else if (texto.includes('reemplazo') || texto.includes('cubrir')) {
        categoria = 'Reemplazo';
        sugerencia = 'Elige otra persona disponible de la misma área. El reemplazo no hace doble turno y no puede dejar su turno original por debajo de la cobertura mínima.';
    } else if (texto.includes('intercambio')) {
        categoria = 'Intercambio de turno';
        sugerencia = 'Comprueba que ambas personas sean de la misma área, tengan AM/PM distintos y no tengan otra novedad bloqueada ese día.';
    } else if (texto.includes('descanso fijo')) {
        categoria = 'Descanso fijo';
        sugerencia = 'Ese día es obligatorio. Si el contrato cambió, edita el descanso fijo desde Personal; de lo contrario mueve la solicitud.';
    } else if (texto.includes('semana')) {
        categoria = 'Descanso semanal';
        sugerencia = 'Selecciona la semana completa en Solicitudes → Mover descanso y conserva un único descanso ordinario, salvo el segundo D permitido por domingo/festivo.';
    }
    return {categoria, sugerencia, accion: sugerencia};
}

function detalleValidacion(r, mensaje, nivel) {
    const lista = r.validaciones || [];
    const item = lista.find(x => x.mensaje === mensaje && (!nivel || x.nivel === nivel));
    if (item) return {categoria: item.categoria, sugerencia: item.sugerencia || item.accion};
    return explicar(mensaje);
}


function candidatosCoberturaValidacion(mensaje) {
    if (!ultimo?.horario?.length) return [];
    const texto = String(mensaje || '');
    const fecha = (texto.match(/\d{4}-\d{2}-\d{2}/) || [])[0];
    if (!fecha) return [];
    const lower = texto.toLowerCase();
    let areaObjetivo = null;
    if (lower.includes('gestión social')) areaObjetivo = 'gestion_social';
    else if (lower.includes('comunicaciones')) areaObjetivo = 'comunicaciones';
    if (!areaObjetivo) return [];
    let turno = null;
    if (lower.includes('sin pm') || lower.includes(' 0 pm') || lower.includes('pm el')) turno = 'PM';
    else if (lower.includes('sin am') || lower.includes(' 0 am') || lower.includes('am el')) turno = 'AM';
    if (!turno && areaObjetivo === 'comunicaciones') turno = 'PM';
    if (!turno) return [];
    return ultimo.horario
        .filter(e => e.area === areaObjetivo && e.tipo_turno !== 'administrativo')
        .map(e => ({e, d: e.dias?.find(x => x.fecha === fecha)}))
        .filter(x => x.d && ['AM','PM'].includes(x.d.turno) && x.d.turno !== turno && !x.d.solicitud_id && !x.d.requerimiento_id)
        .slice(0,5)
        .map(x => ({empleado_id:x.e.empleado_id,nombre:x.e.nombre,fecha,turno}));
}

window.prepararSolucionCobertura = (empleadoId, fecha, turno) => {
    document.querySelector('[data-tab="modificar"]').click();
    $('modificar-alcance').value = 'todos';
    $('g-modificar-persona').classList.add('hidden');
    $('g-modificar-reestructurar').classList.add('hidden');
    $('g-modificar-areas')?.classList.add('hidden');
    const semana = semanasDelMes($('periodo').value).find(x => fecha >= x.lunes && fecha <= x.domingo);
    if (semana) {
        const cerrada = semanasEstadoActual.some(x => x.lunes === semana.lunes && x.bloqueada);
        if (cerrada) {
            document.querySelector('[data-tab="horario"]').click();
            toast(`La ${semana.texto} está cerrada. Habilítala primero desde Horario si realmente necesitas corregirla.`, 'warning', 'Semana cerrada');
            return;
        }
        $('modificar-semana-inicio').value = semana.lunes;
        actualizarSemanasFinModificar();
        $('modificar-semana-fin').value = semana.lunes;
    }
    renderEditorManual();
    const sel = document.querySelector(`#tabla-manual .manual-shift[data-eid="${empleadoId}"][data-fecha="${fecha}"]`);
    if (sel) {
        sel.value = turno;
        sel.dispatchEvent(new Event('change'));
        sel.scrollIntoView({block:'center', inline:'center'});
        toast(`Se preparó ${turno} para ${fecha}. Revisa el resto de la semana y pulsa «${($('aplicar-manual')?.textContent || 'Validar cambios y buscar opciones').trim()}».`, 'info', 'Solución preparada');
    } else {
        toast('La persona candidata tiene una novedad protegida o la celda no es editable. Escoge otra solución.', 'warning', 'Solución no disponible');
    }
};

function accionesValidacion(mensaje) {
    const t = String(mensaje || '').toLowerCase();
    if (t.includes('gestión social') || t.includes('comunicaciones queda sin pm')) {
        return [
            {id:'reestructurar',label:'Permitir reestructuración'},
            {id:'manual',label:'Resolver manualmente'},
            {id:'solicitudes',label:'Revisar solicitudes'},
        ];
    }
    if (t.includes('pareja') || t.includes('pc')) return [
        {id:'personal',label:'Revisar pareja PC'}, {id:'manual',label:'Resolver manualmente'}
    ];
    if (t.includes('descanso') || t.includes('semana')) return [
        {id:'solicitudes',label:'Mover descanso'}, {id:'manual',label:'Resolver manualmente'}
    ];
    if (t.includes('festivo') || t.includes('compensatorio')) return [
        {id:'requerimientos',label:'Añadir ajuste directo'}, {id:'manual',label:'Resolver manualmente'}
    ];
    return [{id:'manual',label:'Resolver manualmente'}];
}

window.accionValidacion = accion => {
    if (accion === 'manual' || accion === 'reestructurar') {
        document.querySelector('[data-tab="modificar"]').click();
        if (accion === 'reestructurar' && $('modificar-alcance').value === 'persona') $('modificar-reestructurar').value = 'si';
        toast(accion === 'reestructurar' ? 'Activa una persona y permite reajustes en su misma área, luego selecciona solo las semanas necesarias.' : 'Carga la programación visible y modifica únicamente las celdas necesarias.','info','Solución seleccionada');
    } else if (accion === 'solicitudes') {
        document.querySelector('[data-tab="solicitudes"]').click();
    } else if (accion === 'requerimientos') {
        document.querySelector('[data-tab="requerimientos"]').click();
    } else if (accion === 'personal') {
        document.querySelector('[data-tab="personal"]').click();
    }
};

function menuSolucionesValidacion(mensaje) {
    const acciones = accionesValidacion(mensaje);
    const candidatos = candidatosCoberturaValidacion(mensaje);
    const botonesCandidatos = candidatos.map(c => `<button type="button" onclick="prepararSolucionCobertura(${c.empleado_id},'${c.fecha}','${c.turno}')">${esc(c.nombre)} → ${c.turno}</button>`).join('');
    return `<div class="validation-actions"><span>Soluciones:</span>${botonesCandidatos}${acciones.map(a => `<button type="button" class="secondary" onclick="accionValidacion('${a.id}')">${esc(a.label)}</button>`).join('')}</div>`;
}

// Agosto de 2026 es el horario que ya se ejecutó: se conserva tal cual, y sus
// incidencias frente a las reglas de hoy son un registro, no trabajo pendiente.
// Contarlas junto al resto hacía que el mes base apareciera con 36 avisos, como
// si hubiera 36 cosas por arreglar cuando no hay ninguna.
function esIncidenciaHistorica(r, mensaje) {
    const item = (r?.validaciones || []).find(x => x.mensaje === mensaje);
    return String(item?.categoria || '').toLowerCase().includes('incidencia histórica');
}

// De todo lo que la aplicación tiene que decir sobre un mes, solo una parte
// pide una decisión. El resto son dos cosas distintas: lo que ya está
// autorizado —una coincidencia de pareja que alguien aprobó— y lo que la
// aplicación resolvió sola —un descanso que movió para cuadrar los domingos—.
//
// Mezclarlo todo bajo «advertencias» hacía que un mes impecable enseñara nueve
// avisos y pareciera que algo iba mal. Se separa: lo que hay que mirar arriba,
// y lo demás plegado, para consultarlo si se quiere.
const AVISOS_YA_AUTORIZADOS = [
    'la coincidencia está permitida',
    'autorizada por',
    'excepción de turno autorizada',
    'Viene del mes anterior ya publicado',
];
const AVISOS_RESUELTOS_SOLOS = [
    'se trasladó',
    'se colocó en el domingo',
    'Puente administrativo',
    'para recuperar el balance',
    'para cortar una racha',
    'cerró el periodo anterior descansando',
    'se reubicó',
];

// Frases que NIEGAN una autorización. Van primero porque el texto de la
// negación contiene el de la autorización: «sin una excepción de turno
// autorizada» lleva dentro «excepción de turno autorizada», así que buscando
// trozos de frase a secas ese aviso acababa en «ya estaba autorizado»
// significando justamente lo contrario.
const AVISOS_SIN_AUTORIZAR = [
    'sin una excepción de turno autorizada',
    'sin excepción de turno autorizada',
    'no está autorizada',
    'sin autorizar',
];

// Quién clasifica de verdad es el backend, que es quien escribe los mensajes
// (backend/avisos.py). Lo de aquí abajo solo se usa con horarios guardados
// antes de ese cambio, que no traen la marca.
function clasificarAvisoPorTexto(mensaje) {
    const texto = String(mensaje || '').toLowerCase();
    if (AVISOS_SIN_AUTORIZAR.some(x => texto.includes(x.toLowerCase()))) return 'decision';
    if (AVISOS_YA_AUTORIZADOS.some(x => texto.includes(x.toLowerCase()))) return 'autorizado';
    if (AVISOS_RESUELTOS_SOLOS.some(x => texto.includes(x.toLowerCase()))) return 'resuelto';
    return 'decision';
}

function clasificarAviso(mensaje, resultado) {
    const marcado = (resultado?.validaciones || [])
        .find(v => v && v.mensaje === mensaje && v.atencion);
    if (marcado) return marcado.atencion;
    return clasificarAvisoPorTexto(mensaje);
}

function renderValidacion(r) {
    const p = $('panel-validacion');
    const errs = r.errores || [];
    const todas = advertenciasVisibles(r);
    const historicas = todas.filter(m => esIncidenciaHistorica(r, m));
    const warns = todas.filter(m => !historicas.includes(m));
    const paraDecidir = warns.filter(m => clasificarAviso(m, r) === 'decision');
    const estadoHorario = errs.length
        ? 'Hay bloqueos que debes corregir'
        : paraDecidir.length
            ? `Listo, con ${paraDecidir.length} punto(s) que conviene mirar`
            : historicas.length
                ? 'Mes ya ejecutado · nada pendiente'
                : warns.length
                    ? 'Listo · nada que decidir'
                    : 'Listo · sin nada que revisar';

    let html = `<div class="validation-summary">
        <strong>${estadoHorario}</strong>
        <div>${errs.length} bloqueo(s) · ${paraDecidir.length} para decidir · ${warns.length - paraDecidir.length} ya resuelto(s) o autorizado(s)${historicas.length ? ` · ${historicas.length} del histórico` : ''}</div>
        <small>${historicas.length && !errs.length && !warns.length
            ? 'Este mes ya se trabajó tal y como está. Lo de abajo son diferencias con las reglas de hoy, guardadas como registro: no hay nada que corregir.'
            : 'Los ajustes automáticos ya aplicados se consultan en el detalle del horario y en Historial. Aquí solo aparecen situaciones que requieren una decisión o revisión manual.'}</small>
    </div>`;

    if (errs.length) html += '<h3 class="validation-section-title">Bloqueos que debes resolver</h3>';
    errs.forEach(m => {
        const x = detalleValidacion(r, m, 'error');
        html += `<div class="validation-card error">
            <strong>${esc(x.categoria)}</strong>${esc(m)}
            <small class="suggestion"><strong>Sugerencia:</strong> ${esc(x.sugerencia)}</small>
            ${menuSolucionesValidacion(m)}
        </div>`;
    });

    const porTipo = {decision: [], autorizado: [], resuelto: [], historico: []};
    warns.forEach(m => {
        const tipo = clasificarAviso(m, r);
        (porTipo[tipo] || porTipo.decision).push(m);
    });

    if (porTipo.decision.length) {
        html += '<h3 class="validation-section-title">Esto pide que decidas algo</h3>';
        porTipo.decision.forEach(m => {
            const x = detalleValidacion(r, m, 'advertencia');
            html += `<div class="validation-card warn">
                <strong>${esc(x.categoria)}</strong>${esc(m)}
                <small class="suggestion"><strong>Sugerencia:</strong> ${esc(x.sugerencia)}</small>
            </div>`;
        });
    }

    const plegados = [
        ['autorizado', 'Ya estaba autorizado',
         'Son excepciones que alguien aprobó a propósito. Están aquí para que consten, no para corregirlas.'],
        ['resuelto', 'Lo resolvió la aplicación sola',
         'Cambios que hizo para que el mes cuadrara: descansos movidos, rachas cortadas. No hay nada que hacer con ellos.'],
    ];
    plegados.forEach(([tipo, titulo, explicacion]) => {
        const items = porTipo[tipo];
        if (!items.length) return;
        html += `<details class="validation-history">
            <summary>${esc(titulo)} · ${items.length}</summary>
            <div class="validation-card info"><strong>Por qué están aquí</strong>${esc(explicacion)}</div>
            ${items.map(m => {
                const x = detalleValidacion(r, m, 'advertencia');
                return `<div class="validation-card warn"><strong>${esc(x.categoria)}</strong>${esc(m)}</div>`;
            }).join('')}
        </details>`;
    });

    if (historicas.length) {
        html += `<h3 class="validation-section-title">Registro del mes ya ejecutado (${historicas.length})</h3>`;
        html += `<details class="validation-history"><summary>Ver ${historicas.length} incidencia(s) históricas de ${esc(nombrePeriodoRespuesta(r))}</summary>`;
        html += `<div class="validation-card info"><strong>Por qué están aquí</strong>${esc(nombrePeriodoRespuesta(r))} es una programación base que ya se trabajó. Se conserva tal y como fue, aunque algunas reglas de hoy sean más estrictas. No hay que hacer nada con esto.</div>`;
        historicas.forEach(m => {
            const x = detalleValidacion(r, m, 'advertencia');
            html += `<div class="validation-card info">
                <strong>${esc(x.categoria)}</strong>${esc(m)}
                <small class="suggestion">${esc(x.sugerencia || '')}</small>
            </div>`;
        });
        html += '</details>';
    }

    if (!errs.length && !warns.length && !historicas.length) {
        html += '<div class="validation-card ok"><strong>Sin fallos ni advertencias</strong>La programación cumple las reglas configuradas. Los ajustes automáticos se conservaron sin requerir intervención.</div>';
    }

    p.innerHTML = html;
    const tabValidacion = document.querySelector('[data-tab="validacion"]');
    // El contador de la barra separa lo que impide publicar de lo que solo
    // conviene mirar: en rojo van los conflictos, y los avisos no tiñen nada.
    // Las incidencias del mes histórico no cuentan: no hay nada que hacer con
    // ellas y sumarlas hacía que agosto pareciera el mes con más problemas.
    if (tabValidacion) {
        // El número del menú cuenta lo que pide una decisión. Contar también
        // lo que la aplicación ya resolvió sola hacía que un mes impecable
        // luciera un 9 en rojo.
        tabValidacion.dataset.count = String(errs.length + paraDecidir.length);
        tabValidacion.dataset.errores = String(errs.length);
        tabValidacion.dataset.historicas = String(historicas.length);
    }
    actualizarContadoresMenu();
}

// Los ajustes que el motor ya aplicó correctamente son trazabilidad, no
// incidencias para el operador. Solo se muestran mensajes que requieren una
// decisión o corrección manual.
function advertenciasVisibles(r) {
    const automaticas = [
        /ajuste automático/i,
        /descanso semanal .*se traslad[oó]/i,
        /descanso .*traslad[oó].*sin crear un segundo descanso/i,
        /se reubic[oó].*descanso/i,
        /reubic[oó].*descanso semanal automático/i,
        /para recuperar el balance/i,
        /puente administrativo.*por fatiga/i,
        /qued[oó] en ADM-.*porque no hab[ií]a un descanso/i,
        /reajuste automático/i,
    ];
    return (r?.advertencias || []).filter(m => !automaticas.some(re => re.test(String(m))));
}

function descripcionCumplimiento(alternativa) {
    const diagnostico = alternativa?.cumplimiento_normativo;
    if (!diagnostico) return '';
    const nota = Number(diagnostico.nota);
    if (nota === 10) return 'Cumplimiento normativo: 10/10 · cumple todas las reglas';
    if (nota === 9) {
        const personas = (diagnostico.personas_fuera_balance_dominical || []).length;
        return `Cumplimiento normativo: 9/10 · ${personas || 1} excepción(es) explícita(s) para revisar`;
    }
    return 'No cumple las reglas obligatorias';
}

// Referencia operativa visible en diagnósticos de cobertura de Gestión Social.

function comentarioDia(d) {
    const origen = String(d?.origen || '');
    const obs = String(d?.observacion || '').trim();
    if (origen === 'turno_base') return `Turno base ${d.turno}.`;
    if (origen === 'descanso_fijo') return 'Descanso fijo configurado para esta persona.';
    if (origen === 'compensatorio_festivo') return `Descanso compensatorio del festivo ${d.festivo_origen || ''}.`.trim();
    if (origen.startsWith('requerimiento:actividad')) { const cob=d.cobertura_operativa ? ` · cubre ${d.cobertura_operativa}` : ''; return `Actividad asignada: ${obs || d.turno}${cob}.`; }
    if (origen.startsWith('requerimiento:asignacion_administrativa')) { const cob=d.cobertura_operativa ? ` · cubre ${d.cobertura_operativa}` : ''; return `Asignación administrativa directa: ${obs || d.turno}${cob}.`; }
    if (origen === 'ajuste_manual') return obs || `Modificación manual a ${d.turno}.`;
    if (origen === 'ultimo_viernes_administrativo') return 'Último viernes del mes: jornada administrativa general.';
    if (origen.startsWith('solicitud:')) return obs || 'Aplicado por solicitud aprobada.';
    return obs || origen || d.turno;
}

const DIAS_ABREVIADOS = {
    lunes: 'Lun', martes: 'Mar', miercoles: 'Mié', 'miércoles': 'Mié',
    jueves: 'Jue', viernes: 'Vie', sabado: 'Sáb', 'sábado': 'Sáb', domingo: 'Dom',
};

function diaCorto(nombre) {
    const limpio = String(nombre || '').trim().toLowerCase();
    if (DIAS_ABREVIADOS[limpio]) return DIAS_ABREVIADOS[limpio];
    const sin = limpio.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    if (DIAS_ABREVIADOS[sin]) return DIAS_ABREVIADOS[sin];
    return (nombre || '').slice(0, 3).replace(/^./, c => c.toUpperCase());
}

const MESES_CORTOS = ['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'];

// Los días que completan la primera y la última semana pertenecen a otro mes.
// Se muestran igual —el horario se lee por semanas— pero se marcan para que
// nadie los confunda con los días del mes y no cuenten en las horas del mes.
function esOtroMes(d) {
    return d && d.mes_propio === false;
}

function claseColumnaDia(d) {
    const nombre = String(d.dia_semana || '').toLowerCase();
    const base = d.es_festivo
        ? 'holiday'
        : (d.es_ultimo_viernes_administrativo
            ? 'admin-friday'
            : (d.es_domingo
                ? 'sunday'
                : ((nombre.startsWith('sáb') || nombre.startsWith('sab')) ? 'saturday' : '')));
    return `${base}${esOtroMes(d) ? ' otro-mes' : ''}`.trim();
}

// El globo de ayuda de cada columna explica qué tiene de especial ese día.
function tituloDia(d) {
    const partes = [`${diaCorto(d.dia_semana)} ${d.dia}`];
    if (esOtroMes(d)) {
        const mes = MESES_CORTOS[Math.max(0, Number(d.mes || 1) - 1)] || '';
        partes.push(`De ${mes}. · completa la semana y no cuenta en las horas del mes`);
    }
    if (d.nombre_festivo) partes.push(`Festivo: ${d.nombre_festivo}`);
    else if (d.es_festivo) partes.push('Festivo');
    if (d.es_domingo) partes.push('Domingo');
    if (d.es_ultimo_viernes_administrativo) {
        partes.push('Último viernes del mes · jornada administrativa para todo el personal');
    }
    if (d.heredado) partes.push('Publicado con el mes anterior · no se puede cambiar aquí');
    return partes.join(' · ');
}

// El horario se lee por semanas: la línea que separa el domingo del lunes es
// la única división de la rejilla que significa algo, así que es la única que
// se dibuja marcada. El resto es una cuadrícula fina que deja seguir la fila
// sin taparle el color al turno.
function esLunes(d) {
    if (d && d.dia_semana_numero != null) return Number(d.dia_semana_numero) === 0;
    return String(d?.dia_semana || '').toLowerCase().startsWith('lun');
}
