// Si a la instalación le falta el archivo de una programación base, ese mes
// aparecería vacío y la aplicación ofrecería generarlo, como si nunca hubiera
// existido. Se dice en voz alta: es un problema de la copia instalada, no algo
// que se arregle generando el mes otra vez.
function avisarProblemasDeBase(problemas) {
    if (!Array.isArray(problemas) || !problemas.length) return;
    const meses = problemas.map(p => p.periodo).join(', ');
    const archivos = problemas.map(p => p.archivo).filter(Boolean).join(' y ');
    const carpeta = problemas.map(p => p.carpeta_reposicion).filter(Boolean)[0] || '';
    const comoArreglarlo = archivos && carpeta
        ? `Copia ${archivos} en ${carpeta} y vuelve a abrir la aplicación; o reinstálala con su carpeta «data» completa.`
        : 'Vuelve a instalar la aplicación con su carpeta «data» completa.';
    toast(`Falta la programación base de ${meses}, así que ese mes sale vacío. ${comoArreglarlo} No lo generes de nuevo: se perdería la programación que ya está vigente.`,
          'error', 'Instalación incompleta', 20000);
    console.error('[base] programación base incompleta:', problemas);
}

// El nombre y la versión vienen del servidor, así que la portada, el título de
// la ventana y la pantalla de acceso dicen siempre lo mismo sin repetirlo a
// mano en tres sitios.
async function aplicarEdicion() {
    try {
        const salud = await fetch('/api/salud').then(r => r.json());
        // `problemas`, que es como se llama en `/api/salud`. Con el nombre de
        // antes, `Array.isArray(undefined)` salía y el aviso de «Instalación
        // incompleta» no se dio nunca, que es tanto como no tenerlo.
        avisarProblemasDeBase(salud?.problemas);
        const e = salud?.edicion;
        if (!e) return;
        const nombre = `${e.nombre} ${e.version}`.trim();
        document.title = nombre;
        const marca = $('nombre-edicion');
        if (marca) marca.textContent = nombre;
        // La pantalla de acceso dice qué aplicación es y en qué versión: es lo
        // único que alguien necesita confirmar antes de escribir su clave.
        const titulo = $('login-titulo');
        if (titulo) titulo.textContent = e.nombre || nombre;
        const edicion = $('login-edicion');
        if (edicion) edicion.textContent = `Programación de turnos · ${e.version || ''}`.trim();
        // La tarjeta de actualizaciones enseña la versión instalada desde el
        // primer momento, sin obligar a pulsar «comprobar» para saber qué se
        // tiene puesto. Es la pregunta que hace todo el que llama pidiendo
        // ayuda, y hasta ahora había que ir a buscarla al pie de la ventana.
        const instalada = $('version-instalada');
        if (instalada) instalada.textContent = e.version_motor || e.version || '—';
    } catch (_) { /* sin conexión, se queda la disposición del propio archivo */ }
}
