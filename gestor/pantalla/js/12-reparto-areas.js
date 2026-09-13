// El reparto AM/PM de cada área
// ---------------------------------------------------------------------------
// Parte de la pantalla del Gestor de Horarios. Los archivos de esta carpeta se
// cargan en orden y comparten el mismo ámbito, así que juntos son exactamente
// el app.js de antes. Ver frontend/js/LEEME.md.

'use strict';

// ---------------------------------------------------------------------------
// Reparto de turnos por área (reglas de cobertura)
// ---------------------------------------------------------------------------
// Cada área tiene un reparto normal (AM/PM) y un mínimo obligatorio, con fecha
// de vigencia. Cambiarlos aquí evita tener que tocar el código cuando la
// operación decide, por ejemplo, pasar de 1 AM + 2 PM a 2 AM + 1 PM.

let reglasCoberturaAreas = [];

function numeroOVacio(valor) {
    const texto = String(valor ?? '').trim();
    if (!texto) return null;
    const n = Number(texto);
    return Number.isFinite(n) ? Math.max(0, Math.trunc(n)) : null;
}

function frasePlanaDelArea(v, area) {
    // Una frase en el idioma de la oficina, no en el de la base de datos.
    // Antes lo primero que se veía eran ocho casillas numéricas —«objetivo»,
    // «mínimo», «máximo», «exigir desde rotativos»— y había que deducir qué
    // significaba el conjunto. Ahora se lee la regla y debajo se ajusta.
    const partes = [];
    if (v.am_minimo || v.pm_minimo) {
        const trozos = [];
        if (v.am_minimo) trozos.push(`${v.am_minimo} por la mañana`);
        if (v.pm_minimo) trozos.push(`${v.pm_minimo} por la tarde`);
        partes.push(`cada día tiene que haber ${trozos.join(' y ')}`);
    } else if (v.minimo_area) {
        partes.push(`cada día tiene que haber al menos ${v.minimo_area} `
            + `persona${v.minimo_area === 1 ? '' : 's'} trabajando, en la franja que sea`);
    } else {
        partes.push('no hay un mínimo obligatorio de personas');
    }
    if (v.am_objetivo !== null && v.am_objetivo !== undefined) {
        partes.push(`el reparto habitual es ${v.am_objetivo} de mañana y ${v.pm_objetivo} de tarde`);
    }
    const techos = [];
    if (v.am_maximo !== null && v.am_maximo !== undefined) techos.push(`${v.am_maximo} de mañana`);
    if (v.pm_maximo !== null && v.pm_maximo !== undefined) techos.push(`${v.pm_maximo} de tarde`);
    if (techos.length) partes.push(`como mucho caben ${techos.join(' y ')}`);
    return `En ${area.nombre}, ${partes.join('; ')}.`;
}

function tarjetaReglaCobertura(area) {
    const v = area.vigente || {};
    // El área exige turnos concretos solo si tiene un mínimo de AM o de PM.
    const porTurno = !!(v.am_minimo || v.pm_minimo);
    // El tope no está escrito en ningún sitio: es la gente que hay ahora en el
    // área, así que se mueve solo cuando entra o sale personal.
    const plantilla = Number(area.personal_operativo ?? 0);
    const tope = Number(area.maximo ?? plantilla ?? 1) || 1;
    const historial = (area.historial || []).slice().reverse();
    const previas = historial.filter(r => r.vigente_desde !== v.vigente_desde);
    const filas = previas.map(r => `<li>
            <span>Desde el ${esc(fechaBonita(r.vigente_desde))}: ${esc(textoReparto(r))}</span>
            ${r.id ? `<button type="button" class="danger-soft regla-eliminar" data-regla="${r.id}">Eliminar</button>` : ''}
        </li>`).join('');

    return `<div class="coverage-rule" data-area="${esc(area.area)}">
        <div class="coverage-rule-head">
            <strong>${esc(area.nombre)}</strong>
            <span class="badge badge-ok">${plantilla} persona${plantilla === 1 ? '' : 's'} en turnos</span>
        </div>

        <p class="coverage-plain">${esc(frasePlanaDelArea(v, area))}</p>

        <div class="coverage-question">
            <h4>1 · ¿Cuánta gente hace falta como mínimo cada día?</h4>
            <label class="coverage-mode">
                <select data-campo="modo_minimo">
                    <option value="area" ${porTurno ? '' : 'selected'}>Basta con que haya alguien trabajando</option>
                    <option value="turno" ${porTurno ? 'selected' : ''}>Hace falta gente en cada franja, mañana y tarde</option>
                </select>
                <small>Comunicaciones y Atención al Ciudadano funcionan con lo primero: lo que no
                    puede pasar es que el área se quede vacía. Gestión Social necesita lo segundo,
                    porque atiende en las dos franjas.</small>
            </label>
            <div class="coverage-fields">
                <label class="min-area ${porTurno ? 'hidden' : ''}">Personas como mínimo
                    <input type="number" min="1" max="${tope}" data-campo="minimo_total" value="${porTurno ? 1 : (v.minimo_area ?? 1)}">
                    <small>En la franja que sea. De 1 a ${tope}.</small>
                </label>
                <label class="min-turno ${porTurno ? '' : 'hidden'}">Por la mañana
                    <input type="number" min="0" max="${tope}" data-campo="am_minimo" value="${v.am_minimo ?? 0}">
                    <small>0 = la mañana no exige a nadie por su cuenta.</small>
                </label>
                <label class="min-turno ${porTurno ? '' : 'hidden'}">Por la tarde
                    <input type="number" min="0" max="${tope}" data-campo="pm_minimo" value="${v.pm_minimo ?? 0}">
                    <small>0 = la tarde no exige a nadie por su cuenta.</small>
                </label>
            </div>
        </div>

        <div class="coverage-question">
            <h4>2 · ¿Cómo se reparte normalmente entre mañana y tarde?</h4>
            <div class="coverage-fields">
                <label>De mañana
                    <input type="number" min="0" max="${tope}" data-campo="am_objetivo" value="${v.am_objetivo ?? ''}" placeholder="Automático">
                    <small>Vacío = la aplicación reparte sola.</small>
                </label>
                <label>De tarde
                    <input type="number" min="0" max="${tope}" data-campo="pm_objetivo" value="${v.pm_objetivo ?? ''}" placeholder="Automático">
                    <small>Entre las dos no pueden pasar de ${tope}.</small>
                </label>
            </div>
        </div>

        <div class="coverage-question">
            <h4>3 · ¿Desde cuándo rige este reparto?</h4>
            <label>
                <input type="date" min="${INICIO_OPERACION_ISO}" data-campo="vigente_desde" value="${esc(v.vigente_desde || INICIO_OPERACION_ISO)}">
                <small>Los meses anteriores conservan su programación. Agosto de 2026 es la base y no se modifica.</small>
            </label>
        </div>

        <div class="coverage-question coverage-avanzado">
            <h4>4 · Ajustes que casi nunca se tocan</h4>
            <div class="coverage-fields">
                <label>Como mucho, de mañana
                    <input type="number" min="0" max="${tope}" data-campo="am_maximo" value="${v.am_maximo ?? ''}" placeholder="Sin techo">
                    <small>Vacío = sin techo.</small>
                </label>
                <label>Como mucho, de tarde
                    <input type="number" min="0" max="${tope}" data-campo="pm_maximo" value="${v.pm_maximo ?? ''}" placeholder="Sin techo">
                    <small>Entre los dos tiene que caber todo el personal del área.</small>
                </label>
                <label>Exigir el mínimo solo si hay tantos rotativos
                    <input type="number" min="0" max="${tope}" data-campo="exigir_desde_rotativos" value="${v.exigir_desde_rotativos ?? 0}">
                    <small>0 = el mínimo se exige siempre.</small>
                </label>
            </div>
        </div>

        ${area.aviso ? `<p class="coverage-rule-warning ${area.aviso_nivel === 'informativo' ? 'informative' : ''}">${esc(area.aviso)}</p>` : ''}
        <div class="coverage-rule-actions">
            <button type="button" class="regla-guardar">Guardar reparto</button>
        </div>
        ${previas.length ? `<details class="coverage-rule-history"><summary>Repartos anteriores (${previas.length})</summary><ul>${filas}</ul></details>` : ''}
    </div>`;
}

function textoReparto(regla) {
    if (!regla) return 'Sin configurar';
    const objetivo = (regla.am_objetivo === null || regla.am_objetivo === undefined)
        ? 'reparto automático'
        : `${regla.am_objetivo} AM + ${regla.pm_objetivo} PM`;
    // El texto del mínimo lo calcula el servidor, que es quien conoce la regla.
    const suelo = regla.texto_minimo || 'sin mínimo obligatorio';
    const rangos = regla.texto_rangos ? ` · admite ${regla.texto_rangos}` : '';
    return `${objetivo} · ${suelo}${rangos}`;
}

function renderReglasCobertura() {
    const cont = $('reglas-cobertura-lista');
    if (!cont) return;
    cont.innerHTML = reglasCoberturaAreas.map(tarjetaReglaCobertura).join('')
        || '<p class="muted">No se pudieron leer las reglas de cobertura.</p>';
    aplicarFechaMinimaDocumento(cont);
    activarCalendarios(cont);
    cont.querySelectorAll('.regla-guardar').forEach(boton => {
        boton.onclick = () => guardarReglaCobertura(boton.closest('.coverage-rule'), boton);
    });
    // Mostrar solo los campos del modo elegido: pedir a la vez «1 en el área» y
    // «1 AM y 1 PM» confunde, porque son dos formas distintas de lo mismo.
    cont.querySelectorAll('[data-campo="modo_minimo"]').forEach(select => {
        const aplicar = () => {
            const tarjeta = select.closest('.coverage-rule');
            const porTurno = select.value === 'turno';
            tarjeta.querySelectorAll('.min-area').forEach(x => x.classList.toggle('hidden', porTurno));
            tarjeta.querySelectorAll('.min-turno').forEach(x => x.classList.toggle('hidden', !porTurno));
        };
        select.onchange = aplicar;
        aplicar();
    });
    cont.querySelectorAll('.regla-eliminar').forEach(boton => {
        boton.onclick = () => eliminarReglaCobertura(Number(boton.dataset.regla), boton);
    });
}

// --- Máximo de jornadas seguidas ------------------------------------------
// El tope dejó de estar escrito en el código: es una regla con fecha de
// vigencia, igual que el reparto por área. Cambiarlo no toca los meses ya
// oficializados, solo marca para recalcular los que empiezan desde esa fecha.

async function cargarReglaRacha() {
    const caja = $('regla-racha');
    if (!caja) return;
    const data = await api('/api/configuracion/reglas-operacion');
    const vigente = data.vigente || {};
    const etiqueta = $('regla-racha-vigente');
    if (etiqueta) etiqueta.textContent = vigente.texto || 'Sin configurar';
    const campo = $('regla-racha-max');
    if (campo) {
        campo.min = String(data.minimo ?? 7);
        campo.max = String(data.maximo ?? 14);
        campo.value = String(vigente.max_dias_consecutivos ?? 10);
    }
    const ayuda = $('regla-racha-ayuda');
    if (ayuda) ayuda.textContent = `De ${data.minimo ?? 7} a ${data.maximo ?? 14}. Por debajo de ${data.minimo ?? 7} no existe ninguna programación posible con un solo descanso semanal.`;
    const desde = $('regla-racha-desde');
    if (desde && !desde.value) desde.value = vigente.vigente_desde || INICIO_OPERACION_ISO;

    const previas = (data.historial || []).filter(r => r.vigente_desde !== vigente.vigente_desde);
    const caja_historial = $('regla-racha-historial-caja');
    const lista = $('regla-racha-historial');
    if (lista && caja_historial) {
        lista.innerHTML = previas.map(r => `<li>
            <span>Desde el ${esc(fechaBonita(r.vigente_desde))}: ${esc(r.texto || '')}</span>
            ${r.id ? `<button type="button" class="danger-soft regla-racha-eliminar" data-regla="${r.id}">Eliminar</button>` : ''}
        </li>`).join('');
        caja_historial.hidden = previas.length === 0;
        lista.querySelectorAll('.regla-racha-eliminar').forEach(boton => {
            boton.onclick = async () => {
                try {
                    const r = await api(`/api/configuracion/reglas-operacion/${boton.dataset.regla}`, {method: 'DELETE'});
                    toast(r.mensaje, 'ok', 'Regla eliminada');
                    await cargarReglaRacha();
                } catch (error) {
                    toast(error?.message || 'No se pudo eliminar la regla.', 'error');
                }
            };
        });
    }
}

async function guardarReglaRacha(boton) {
    const cuerpo = {
        vigente_desde: $('regla-racha-desde')?.value,
        max_dias_consecutivos: Number($('regla-racha-max')?.value || 0),
        nota: '',
    };
    if (!cuerpo.vigente_desde) return toast('Indica desde qué día rige el máximo.', 'error');
    if (boton) boton.disabled = true;
    try {
        const r = await api('/api/configuracion/reglas-operacion', {method: 'PUT', body: JSON.stringify(cuerpo)});
        toast(r.mensaje, 'ok', 'Máximo actualizado');
        await cargarReglaRacha();
        if (typeof cargarEstadoPeriodo === 'function') await cargarEstadoPeriodo();
    } catch (error) {
        toast(error?.message || 'No se pudo guardar el máximo.', 'error');
    } finally {
        if (boton) boton.disabled = false;
    }
}

async function cargarReglasCobertura() {
    const data = await api('/api/configuracion/reglas-cobertura');
    reglasCoberturaAreas = data.areas || [];
    renderReglasCobertura();
}

async function guardarReglaCobertura(tarjeta, boton) {
    if (!tarjeta) return;
    const leer = campo => tarjeta.querySelector(`[data-campo="${campo}"]`)?.value;
    const porTurno = leer('modo_minimo') === 'turno';
    const payload = {
        area: tarjeta.dataset.area,
        vigente_desde: leer('vigente_desde'),
        // Un modo excluye al otro: o el área exige personas, o exige turnos.
        minimo_total: porTurno ? 0 : (numeroOVacio(leer('minimo_total')) ?? 1),
        am_minimo: porTurno ? (numeroOVacio(leer('am_minimo')) ?? 0) : 0,
        pm_minimo: porTurno ? (numeroOVacio(leer('pm_minimo')) ?? 0) : 0,
        am_maximo: numeroOVacio(leer('am_maximo')),
        pm_maximo: numeroOVacio(leer('pm_maximo')),
        am_objetivo: numeroOVacio(leer('am_objetivo')),
        pm_objetivo: numeroOVacio(leer('pm_objetivo')),
        exigir_desde_rotativos: numeroOVacio(leer('exigir_desde_rotativos')) ?? 0,
    };
    if (!payload.vigente_desde) {
        toast('Indica desde qué fecha se aplica este reparto.', 'warning', 'Falta la fecha');
        return;
    }
    ponerBotonOcupado(boton, true, 'Guardando…');
    try {
        const r = await api('/api/configuracion/reglas-cobertura', {method:'PUT', body:JSON.stringify(payload)});
        await cargarReglasCobertura();
        await cargarEstadoPeriodo().catch(()=>{});
        toast(r.mensaje, 'success', 'Reparto actualizado');
    } catch (e) {
        toast(e.message, 'error', 'No se pudo guardar el reparto');
    } finally {
        ponerBotonOcupado(boton, false);
    }
}

async function eliminarReglaCobertura(id, boton) {
    const ok = await confirmarUI({
        titulo: 'Eliminar este reparto',
        mensaje: '¿Quitar esta configuración anterior?',
        detalle: 'Los meses que ya se generaron con ella conservan su programación; solo deja de estar disponible para futuros cálculos.',
        aceptar: 'Eliminar reparto',
        peligro: true,
    });
    if (!ok) return;
    ponerBotonOcupado(boton, true, 'Eliminando…');
    try {
        const r = await api('/api/configuracion/reglas-cobertura/' + id, {method:'DELETE'});
        await cargarReglasCobertura();
        toast(r.mensaje, 'success', 'Reparto eliminado');
    } catch (e) {
        toast(e.message, 'error', 'No se pudo eliminar');
    } finally {
        ponerBotonOcupado(boton, false);
    }
}

function temaSeleccionado() {
    const id = $('tema-app')?.value;
    return temasAppDisponibles.find(t => t.id === id) || null;
}

async function cargarModoApp() {
    // Se aplica lo guardado antes de pintar nada más: así no se ve un
    // parpadeo en claro antes de que la aplicación se ponga oscura.
    try {
        const data = await api('/api/configuracion/modo-app');
        aplicarModoApp(data.modo || 'sistema');
    } catch (_) {
        aplicarModoApp('sistema');
    }
}

function conectarSelectorDeModo() {
    document.querySelectorAll('[data-modo-opcion]').forEach(boton => {
        boton.onclick = async () => {
            const elegido = boton.dataset.modoOpcion;
            const anterior = modoElegido;
            aplicarModoApp(elegido);
            try {
                const data = await api('/api/configuracion/modo-app', {
                    method: 'PUT', body: JSON.stringify({modo: elegido}),
                });
                const nota = $('modo-app-nota');
                if (nota && elegido === 'sistema') {
                    nota.textContent = `Ahora mismo tu equipo está en ${modoEfectivo()}. El cambio queda guardado.`;
                } else if (nota) {
                    nota.textContent = 'El cambio se ve al instante y queda guardado.';
                }
                toast(data.mensaje, 'success', 'Apariencia actualizada');
            } catch (e) {
                aplicarModoApp(anterior);
                toast(e.message, 'error', 'No se pudo cambiar el modo');
            }
        };
    });
}

async function cargarTemaApp() {
    const data = await api('/api/configuracion/tema-app');
    temasAppDisponibles = data.opciones || [];
    const select = $('tema-app');
    if (select) {
        select.innerHTML = temasAppDisponibles.map(t => `<option value="${esc(t.id)}">${esc(t.nombre)}</option>`).join('');
        select.value = data.tema?.id || 'morado';
    }
    aplicarTemaApp(data.tema);
}
