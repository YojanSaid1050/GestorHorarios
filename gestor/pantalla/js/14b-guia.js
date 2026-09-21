// ---------------------------------------------------------------------------
// Primeros pasos
// ---------------------------------------------------------------------------
// Quien abre la aplicación por primera vez encuentra ocho pestañas y ningún
// indicio del orden en que se usan. Esta guía se muestra hasta que la persona
// pide no volver a verla, y siempre se puede recuperar desde la cabecera.
const CLAVE_GUIA = 'gestorhorarios_guia_oculta';

function guiaOculta() {
    try { return localStorage.getItem(CLAVE_GUIA) === '1'; } catch (_) { return false; }
}

function mostrarGuia(forzar = false) {
    const caja = $('guia-inicio');
    if (!caja) return;
    if (!forzar && guiaOculta()) return;
    const check = $('guia-no-mostrar');
    if (check) check.checked = guiaOculta();
    caja.classList.remove('hidden');
    // La guía se muestra plegada: una línea con el título y un botón. Antes
    // ocupaba la pantalla entera en todos los apartados y había que
    // desplazarse para llegar al trabajo. Solo se abre entera cuando se pide
    // desde «¿Cómo empiezo?».
    plegarGuia(forzar);
    if (forzar) caja.scrollIntoView({block: 'nearest', behavior: 'smooth'});
}

function plegarGuia(abierta) {
    const caja = $('guia-inicio');
    const boton = $('guia-desplegar');
    if (!caja) return;
    caja.classList.toggle('abierta', Boolean(abierta));
    if (boton) {
        boton.setAttribute('aria-expanded', abierta ? 'true' : 'false');
        const texto = boton.querySelector('span');
        if (texto) texto.textContent = abierta ? 'Ocultar los pasos' : 'Ver los siete pasos';
    }
}

function ocultarGuia() {
    $('guia-inicio')?.classList.add('hidden');
}

$('guia-cerrar')?.addEventListener('click', ocultarGuia);
$('guia-desplegar')?.addEventListener('click', () => plegarGuia(!$('guia-inicio')?.classList.contains('abierta')));
$('abrir-guia')?.addEventListener('click', () => mostrarGuia(true));
$('guia-no-mostrar')?.addEventListener('change', ev => {
    try {
        if (ev.target.checked) localStorage.setItem(CLAVE_GUIA, '1');
        else localStorage.removeItem(CLAVE_GUIA);
    } catch (_) { /* si el navegador no deja guardar, la guía simplemente reaparece */ }
});
document.querySelectorAll('.guide-step').forEach(boton => {
    boton.addEventListener('click', () => {
        const destino = boton.dataset.ir;
        document.querySelector(`[data-tab="${destino}"]`)?.click();
        window.scrollTo({top: 0, behavior: 'smooth'});
    });
});
