// ---------------------------------------------------------------------------
// Calendario propio
// ---------------------------------------------------------------------------
// El calendario nativo del navegador no se puede diseñar: cada sistema lo pinta
// a su manera y en la ventana de escritorio salía con colores que no son los de
// la aplicación. Este lo sustituye por uno propio, con el mismo estilo que el
// resto, y conserva el campo original para que nada del código cambie: se sigue
// leyendo y escribiendo `input.value` en formato AAAA-MM-DD.
const MESES_LARGOS = ['enero','febrero','marzo','abril','mayo','junio','julio',
                      'agosto','septiembre','octubre','noviembre','diciembre'];
const DIAS_CORTOS = ['L','M','X','J','V','S','D'];

let calendarioAbierto = null;

function cerrarCalendario() {
    if (!calendarioAbierto) return;
    calendarioAbierto.caja.remove();
    calendarioAbierto.campo.setAttribute('aria-expanded', 'false');
    calendarioAbierto = null;
}

function fechaLegibleCorta(iso) {
    if (!iso) return '';
    const [a, m, d] = String(iso).split('-').map(Number);
    if (!a || !m || !d) return '';
    return `${String(d).padStart(2,'0')} ${MESES_LARGOS[m-1].slice(0,3)} ${a}`;
}

function limitesDe(input) {
    const min = input.min || INICIO_OPERACION_ISO;
    const max = input.max || '';
    return {min, max};
}

function construirMes(campo, ancla) {
    const {min, max} = limitesDe(campo);
    const anio = ancla.getFullYear(), mes = ancla.getMonth();
    const primero = new Date(anio, mes, 1);
    // La semana empieza en lunes, como el resto de la aplicación.
    const desplazamiento = (primero.getDay() + 6) % 7;
    const dias = new Date(anio, mes + 1, 0).getDate();
    const seleccionado = campo.value || '';
    const hoy = new Date();
    const hoyIso = `${hoy.getFullYear()}-${String(hoy.getMonth()+1).padStart(2,'0')}-${String(hoy.getDate()).padStart(2,'0')}`;

    let celdas = '';
    for (let i = 0; i < desplazamiento; i++) celdas += '<span class="dp-hueco"></span>';
    for (let d = 1; d <= dias; d++) {
        const iso = `${anio}-${String(mes+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
        // Hay campos que solo admiten lunes —la fecha desde la que se cuenta la
        // alternancia AM/PM de un rotativo—. El calendario dejaba elegir
        // cualquier día y el rechazo llegaba al guardar, cuando ya se había
        // rellenado todo el formulario. Se apagan aquí.
        const soloLunes = campo.dataset.soloLunes === '1';
        const esLunes = new Date(anio, mes, d).getDay() === 1;
        const fuera = (min && iso < min) || (max && iso > max) || (soloLunes && !esLunes);
        const clases = ['dp-dia'];
        if (iso === seleccionado) clases.push('sel');
        if (iso === hoyIso) clases.push('hoy');
        const finde = new Date(anio, mes, d).getDay();
        if (finde === 0 || finde === 6) clases.push('finde');
        celdas += fuera
            ? `<span class="dp-dia fuera" aria-disabled="true">${d}</span>`
            : `<button type="button" class="${clases.join(' ')}" data-iso="${iso}" `
              + `aria-label="${d} de ${MESES_LARGOS[mes]} de ${anio}"`
              + `${iso === seleccionado ? ' aria-current="date"' : ''}>${d}</button>`;
    }

    // Las flechas se apagan cuando al otro lado no queda ningún día elegible:
    // así se ve de un vistazo hasta dónde llega lo que se puede elegir, en vez
    // de pasar meses en blanco.
    const primeroDelMes = `${anio}-${String(mes+1).padStart(2,'0')}-01`;
    const ultimoDelMes = `${anio}-${String(mes+1).padStart(2,'0')}-${String(dias).padStart(2,'0')}`;
    const anteriorFuera = !!(min && primeroDelMes <= min);
    const siguienteFuera = !!(max && ultimoDelMes >= max);
    return `
      <div class="dp-cabecera">
        <button type="button" class="dp-nav" data-salto="-1" aria-label="Mes anterior" ${anteriorFuera ? 'disabled' : ''}>‹</button>
        <strong>${MESES_LARGOS[mes][0].toUpperCase()}${MESES_LARGOS[mes].slice(1)} de ${anio}</strong>
        <button type="button" class="dp-nav" data-salto="1" aria-label="Mes siguiente" ${siguienteFuera ? 'disabled' : ''}>›</button>
      </div>
      <div class="dp-semana">${DIAS_CORTOS.map(x => `<span>${x}</span>`).join('')}</div>
      <div class="dp-rejilla">${celdas}</div>
      <div class="dp-pie">
        <button type="button" class="dp-accion" data-accion="hoy">Hoy</button>
        <button type="button" class="dp-accion" data-accion="limpiar">Borrar</button>
      </div>`;
}

function abrirCalendario(campo) {
    if (calendarioAbierto?.campo === campo) { cerrarCalendario(); return; }
    cerrarCalendario();
    const {min} = limitesDe(campo);
    const partida = campo.value || min || INICIO_OPERACION_ISO;
    const [a, m] = partida.split('-').map(Number);
    let ancla = new Date(a, (m || 1) - 1, 1);

    const caja = document.createElement('div');
    caja.className = 'datepicker';
    caja.setAttribute('role', 'dialog');
    caja.setAttribute('aria-label', 'Elegir fecha');
    const pintar = () => { caja.innerHTML = construirMes(campo, ancla); };
    pintar();
    document.body.appendChild(caja);

    const colocar = () => {
        const r = campo.getBoundingClientRect();
        const alto = caja.offsetHeight || 320;
        const abajo = window.innerHeight - r.bottom;
        const arriba = abajo < alto + 12 && r.top > alto + 12;
        caja.style.top = `${(arriba ? r.top - alto - 6 : r.bottom + 6) + window.scrollY}px`;
        caja.style.left = `${Math.max(8, Math.min(r.left + window.scrollX, window.scrollX + window.innerWidth - caja.offsetWidth - 8))}px`;
    };
    colocar();

    caja.addEventListener('click', ev => {
        // Este clic es del calendario y aquí termina. Sin esto, al pulsar las
        // flechas de mes el calendario se redibuja y el clic sigue subiendo
        // hasta el cierre-al-pulsar-fuera; para entonces el botón que se pulsó
        // ya no existe —lo acaba de reemplazar el redibujado—, así que se
        // tomaba por un clic fuera y el calendario se cerraba. Ese era el
        // motivo de que no se pudiera cambiar de mes.
        ev.stopPropagation();
        const salto = ev.target.closest('[data-salto]');
        if (salto) {
            ancla = new Date(ancla.getFullYear(), ancla.getMonth() + Number(salto.dataset.salto), 1);
            pintar(); colocar(); return;
        }
        const accion = ev.target.closest('[data-accion]');
        if (accion) {
            if (accion.dataset.accion === 'limpiar') {
                if (!campo.required) { campo.value = ''; campo.dispatchEvent(new Event('change', {bubbles:true})); }
                cerrarCalendario();
            } else {
                // «Hoy» solo tiene sentido si hoy se puede elegir. Fuera del
                // rango permitido lleva al día más cercano que sí se puede.
                const {min: mn, max: mx} = limitesDe(campo);
                const h = new Date();
                let destino = `${h.getFullYear()}-${String(h.getMonth()+1).padStart(2,'0')}-${String(h.getDate()).padStart(2,'0')}`;
                if (mn && destino < mn) destino = mn;
                if (mx && destino > mx) destino = mx;
                const [da, dm] = destino.split('-').map(Number);
                ancla = new Date(da, dm - 1, 1);
                pintar(); colocar();
            }
            return;
        }
        const dia = ev.target.closest('.dp-dia[data-iso]');
        if (dia) {
            campo.value = dia.dataset.iso;
            campo.dispatchEvent(new Event('input', {bubbles:true}));
            campo.dispatchEvent(new Event('change', {bubbles:true}));
            cerrarCalendario();
            campo.focus();
        }
    });

    calendarioAbierto = {campo, caja, recolocar: colocar};
    campo.setAttribute('aria-expanded', 'true');
}

document.addEventListener('click', ev => {
    if (!calendarioAbierto) return;
    if (calendarioAbierto.caja.contains(ev.target)) return;
    if (ev.target.closest('.date-field')?.contains(calendarioAbierto.campo)) return;
    cerrarCalendario();
});
document.addEventListener('keydown', ev => { if (ev.key === 'Escape' && calendarioAbierto) cerrarCalendario(); });
window.addEventListener('resize', () => calendarioAbierto?.recolocar());
window.addEventListener('scroll', () => calendarioAbierto?.recolocar(), true);

// Convierte los campos de fecha en un control propio. El input original se
// conserva (oculto para el ratón, no para el código) para que toda la
// aplicación siga leyendo `input.value` exactamente igual que antes.
function activarCalendarios(raiz = document) {
    raiz.querySelectorAll('input[type="date"]').forEach(campo => {
        if (campo.dataset.dpListo === '1') return;
        campo.dataset.dpListo = '1';
        const envoltura = document.createElement('div');
        envoltura.className = 'date-field';
        campo.parentNode.insertBefore(envoltura, campo);
        envoltura.appendChild(campo);
        const boton = document.createElement('button');
        boton.type = 'button';
        boton.className = 'date-display';
        boton.innerHTML = `<span class="date-text"></span>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3v3M17 3v3M3.5 9h17M5 5.5h14a1.5 1.5 0 0 1 1.5 1.5v12A1.5 1.5 0 0 1 19 20.5H5A1.5 1.5 0 0 1 3.5 19V7A1.5 1.5 0 0 1 5 5.5Z"/></svg>`;
        envoltura.appendChild(boton);
        const etiqueta = campo.getAttribute('aria-label') || campo.getAttribute('title')
            || campo.closest('label')?.childNodes[0]?.textContent?.trim() || 'fecha';
        boton.setAttribute('aria-label', `Elegir ${etiqueta}`);
        boton.setAttribute('aria-haspopup', 'dialog');
        const refrescar = () => {
            const texto = boton.querySelector('.date-text');
            texto.textContent = fechaLegibleCorta(campo.value) || 'Sin fecha';
            texto.classList.toggle('vacio', !campo.value);
        };
        // El botón tiene que seguir al campo: los formularios habilitan y
        // deshabilitan sus fechas según el tipo de solicitud. Antes el estado
        // se copiaba una sola vez, al crear el control, así que un campo que
        // nacía deshabilitado se quedaba con el botón muerto para siempre: se
        // veía el control nuevo y no se abría nada al pulsarlo.
        const seguirEstado = () => {
            boton.disabled = campo.disabled;
            boton.classList.toggle('desactivado', campo.disabled);
        };
        const sincronizar = () => { refrescar(); seguirEstado(); };
        sincronizar();
        campo.addEventListener('change', refrescar);
        campo.addEventListener('input', refrescar);
        // El resto de la aplicación asigna `input.value` y `input.disabled`
        // directamente, sin lanzar eventos. Se vigila el atributo para no
        // depender de que cada sitio se acuerde de avisar.
        new MutationObserver(seguirEstado).observe(campo, {
            attributes: true, attributeFilter: ['disabled'],
        });
        campo._syncCalendario = sincronizar;
        boton.addEventListener('click', () => { if (!campo.disabled) abrirCalendario(campo); });
    });
}
