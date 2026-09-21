# -*- coding: utf-8 -*-
"""Conducir la aplicación como la conduce una persona.

Todas las suites que abren un navegador comparten esto. Vale la pena tenerlo en
un sitio porque cada detalle de aquí costó una vuelta entera de pruebas:

· Se pulsa por JavaScript y nunca con el clic nativo del navegador. El nativo
  espera treinta segundos si hay un modal delante, así que un despiste se
  convertía en un bloqueo mudo en vez de en un fallo con mensaje.

· Las fechas se eligen abriendo el calendario propio de la aplicación. Poner el
  valor por código no lo registra —el campo nativo está oculto— y el formulario
  contestaba «Falta completar: Fecha» sin que se entendiera por qué.

· Para saber si una generación terminó no se cuenta cuántas opciones hay: si
  antes había cinco y después hay cinco, el número no cambia aunque sean otras.
  Contando, esta ayuda declaraba rotas generaciones correctas.
"""
from __future__ import annotations

from qa.servidor import CLAVE_ADMIN_QA


class App:
    """La aplicación abierta en un navegador, con lo justo para conducirla."""

    def __init__(self, pag):
        self.pag = pag
        self.pasos = []
        self.errores_js = []
        pag.on('pageerror', lambda e: self.errores_js.append(str(e)))

    acta = None

    def paso(self, ok, que, detalle=''):
        self.pasos.append((bool(ok), que, detalle))
        if self.acta is not None:
            self.acta.comprobar(bool(ok), que, detalle)
        else:
            print(f"  [{'ok' if ok else 'FALLA'}] {que}"
                  + (f'  -> {detalle}' if not ok else ''), flush=True)

    def entrar(self, base, usuario='admin', clave=CLAVE_ADMIN_QA):
        """Entrar eligiendo la cuenta **por su nombre**, no por su posición.

        Elegirla por posición ya costó una vuelta entera: la lista de cuentas
        pone primero al administrador, así que el índice 1 era la operadora y
        la suite intentaba entrar con su usuario y la contraseña del otro. El
        recorrido seguía —la pantalla de acceso no bloquea nada— y el paso
        salía en rojo sin que se entendiera por qué.
        """
        self.pag.goto(base, wait_until='networkidle')
        self.pag.wait_for_selector('#login-usuario option', state='attached', timeout=15000)
        self.pag.select_option('#login-usuario', value=usuario)
        # Se comprueba que la contraseña **siga escrita** antes de enviar.
        #
        # La pantalla de acceso termina de cargarse en varios pasos y el último
        # rellena el cuadro con la contraseña recordada, que en una instalación
        # nueva está vacía. Escribiendo antes de que ese paso llegue, lo escrito
        # se borraba solo y la aplicación contestaba «Escribe tu contraseña» con
        # la contraseña puesta. Ese fallo era de la aplicación y está corregido;
        # esta espera se queda porque una carrera perdida no debe volver a
        # parecer un fallo de acceso.
        for _ in range(10):
            self.pag.fill('#login-password', clave)
            self.pag.wait_for_timeout(600)
            if self.pag.input_value('#login-password') == clave:
                break
        self.pag.click('#form-login button[type="submit"]')
        for _ in range(20):
            self.pag.wait_for_timeout(500)
            if self.pag.evaluate(
                    "()=>!document.body.classList.contains('auth-locked')"):
                self.pag.wait_for_timeout(2500)
                return True
        return False

    def modales(self):
        return self.pag.evaluate(
            "() => [...document.querySelectorAll('.modal-backdrop')]"
            ".filter(m => !m.classList.contains('hidden') && "
            "getComputedStyle(m).display !== 'none').map(m => m.id)")

    def aceptar(self):
        for _ in range(3):
            abiertos = self.modales()
            if not abiertos:
                return True
            if 'modal-confirmar' in abiertos:
                self.pag.eval_on_selector('#confirmar-aceptar', 'b=>b.click()')
            else:
                self.pag.evaluate(
                    "(ids) => ids.forEach(id => {const m=document.getElementById(id);"
                    "const b=m && (m.querySelector('.modal-actions button:not(.secondary)')"
                    " || m.querySelector('.modal-x')); if(b) b.click();})", abiertos)
            self.pag.wait_for_timeout(2200)
        return not self.modales()

    def cerrar_modales(self):
        for _ in range(3):
            abiertos = self.modales()
            if not abiertos:
                return
            self.pag.evaluate(
                "(ids) => ids.forEach(id => {const m=document.getElementById(id);"
                "const x=m && (m.querySelector('.modal-x') || m.querySelector('.secondary'));"
                "if(x) x.click();})", abiertos)
            self.pag.wait_for_timeout(900)

    def campos_de_clave(self):
        """Cuántos cuadros de contraseña hay abiertos ahora mismo.

        Se cuentan en vez de preguntar si hay alguno porque en un recorrido
        largo puede quedar uno de antes. Comparando el número antes y después se
        sabe si el que se acaba de abrir se cerró, sin confundirlo con otro que
        ya estaba.
        """
        return self.pag.evaluate(
            "() => document.querySelectorAll("
            "'.modal-backdrop #clave-usuario-temporal,"
            " .modal-backdrop #clave-admin-temporal').length")

    def clave(self, texto):
        """Rellenar el cuadro que pide la contraseña y continuar.

        Este cuadro se crea al vuelo y no tiene identificador —ni él ni sus
        botones—, así que ni `aceptar()` ni nada de lo que había aquí sabía
        tocarlo. La consecuencia fue que dos botones de Configuración, los dos
        reinicios, no los pulsó nunca ninguna prueba: la suite llegaba hasta el
        cuadro de la contraseña y se quedaba ahí, y como después comprobaba la
        pantalla y no la base de datos, el paso salía en verde. Los dos fallos
        que había debajo llegaron a producción.

        Se trabaja siempre sobre el **último** cuadro abierto, que es el que
        está encima. Buscándolo por identificador se rellenaba uno viejo que
        había quedado en la página, se pulsaba su «Continuar» —que ya no
        escuchaba nadie— y el cuadro de verdad se quedaba esperando: la acción
        no llegaba a pedirse y aun así el paso parecía correcto.
        """
        return self.pag.evaluate(
            "(v) => {const cajas = [...document.querySelectorAll('.modal-backdrop')]"
            "   .filter(m => m.querySelector('#clave-usuario-temporal,"
            " #clave-admin-temporal'));"
            " if (!cajas.length) return false;"
            " const caja = cajas[cajas.length - 1];"
            " const i = caja.querySelector('#clave-usuario-temporal,"
            " #clave-admin-temporal');"
            " i.value = v; i.dispatchEvent(new Event('input', {bubbles: true}));"
            " const b = [...caja.querySelectorAll('button')]"
            "   .find(x => /continuar|aceptar/i.test(x.innerText));"
            " if (!b) return false; b.click(); return true;}", texto)

    def confirmar_y_clave(self, selector, texto, espera=4000):
        """Pulsar un botón peligroso hasta el final: confirmación y contraseña.

        Se espera a que el cuadro de la contraseña **aparezca** y a que después
        **desaparezca**, en vez de contar segundos: con esperas fijas esto
        fallaba de forma intermitente al final del recorrido, cuando la máquina
        va más cargada, y daba por buena una contraseña que nunca se escribió.
        """
        self.cerrar_modales()
        antes = self.campos_de_clave()
        if not self.pulsar(selector, 0, 1200):
            return False
        self.aceptar()
        for _ in range(20):
            if self.campos_de_clave() > antes:
                break
            self.pag.wait_for_timeout(500)
        else:
            return False
        if not self.clave(texto):
            return False
        for _ in range(20):
            self.pag.wait_for_timeout(500)
            if self.campos_de_clave() <= antes:
                break
        else:
            return False
        self.pag.wait_for_timeout(espera)
        return True

    def ir(self, tab):
        self.cerrar_modales()
        self.pag.eval_on_selector(f'button[data-tab="{tab}"]',
                                  'b=>{b.scrollIntoView({block:"center"});b.click();}')
        self.pag.wait_for_timeout(900)

    def pulsar(self, sel, i=0, espera=2000):
        guion = ("([s,i]) => {const e=document.querySelectorAll(s)[i];"
                 " if(!e || e.disabled) return false;"
                 " e.scrollIntoView({block:'center'}); e.click(); return true;}")
        ok = self.pag.evaluate(guion, [sel, i])
        if ok:
            self.pag.wait_for_timeout(espera)
        return ok

    def texto(self, sel):
        return self.pag.evaluate("(s)=>document.querySelector(s)?.innerText || ''", sel)

    def valor(self, sel):
        return self.pag.evaluate("(s)=>document.querySelector(s)?.value ?? null", sel)

    def escribir(self, sel, v):
        return self.pag.evaluate(
            "([s,v]) => {const e=document.querySelector(s); if(!e) return false;"
            " e.value=v; e.dispatchEvent(new Event('input',{bubbles:true}));"
            " e.dispatchEvent(new Event('change',{bubbles:true})); return true;}", [sel, v])

    def toast(self):
        return self.texto('#toast')

    def alerta(self, sel):
        return self.pag.evaluate(
            "(s)=>{const e=document.querySelector(s);"
            "return e && !e.classList.contains('hidden') ? e.innerText.trim() : '';}", sel)

    def periodo(self, anio, mes):
        self.cerrar_modales()
        g = self.pag.query_selector('#periodo + .date-select-group')
        g.query_selector('select.date-year').select_option(str(anio))
        self.pag.wait_for_timeout(400)
        g.query_selector('select.date-month').select_option(str(mes))
        self.pag.wait_for_timeout(3000)

    def opciones(self):
        return self.pag.query_selector_all('#lista-alternativas .alternative-button')

    def generar(self, espera=180):
        """Pulsa «generar» y espera a que el resultado esté en pantalla.

        Tres cosas que aquí costaron una vuelta cada una, y las tres son la
        misma lección: **la señal de «ya terminó» tiene que ser un estado, no
        un texto ni un número.**

        · **Contar opciones no vale.** Si antes había cinco y después hay cinco,
          el número no cambia aunque sean otras. Contando, esta ayuda declaraba
          rotas generaciones perfectamente correctas.

        · **Buscar palabras en el botón tampoco.** Se miraba si decía «gener»,
          «cre» o «calcul»; el botón en reposo dice «Crear horario inicial», así
          que «cre» estaba siempre y la espera no terminaba nunca.

        · **Comparar con el texto de antes, tampoco.** El botón cambia de nombre
          a propósito cuando el mes pasa a tener horario: de «Crear horario
          inicial» a «Volver a crear opciones». Comparando, quedaba «ocupado»
          para siempre.

        Lo que sí vale es `disabled`, que es exactamente lo que la aplicación
        pone y quita mientras trabaja.
        """
        self.cerrar_modales()
        firma = self.pag.evaluate(
            "()=>(document.getElementById('lista-alternativas')?.innerHTML || '')")
        if not self.pulsar('#generar', 0, 1200):
            return False
        for _ in range(espera):
            self.pag.wait_for_timeout(1000)
            estado = self.pag.evaluate(
                "()=>{const b=document.getElementById('generar');"
                " const l=document.getElementById('lista-alternativas');"
                " return {ocupado: !!b && (b.disabled || b.dataset.busy === '1'),"
                "         lista: (l?.innerHTML || '')};}")
            if not estado['ocupado'] and estado['lista'] != firma and self.opciones():
                self.pag.wait_for_timeout(1500)
                return True
        return False

    def oficializar(self):
        self.pulsar('#hacer-oficial', 0, 2500)
        self.aceptar()
        self.pag.wait_for_timeout(1500)
        return self.texto('#hacer-oficial').strip() == 'Horario oficial'

    def elegir_fecha(self, id_campo, iso):
        """Elegir una fecha abriendo el calendario propio de la aplicación.

        Se cierra antes cualquier calendario abierto y se busca el día **dentro
        del calendario que está abierto ahora**, no en toda la página. Sin eso,
        al rellenar «desde» y luego «hasta» el clic caía en el calendario
        anterior: la segunda fecha se quedaba igual que la primera y una prueba
        de solapamiento acababa comprobando dos días distintos que no se pisan.
        """
        self.pag.keyboard.press('Escape')
        self.pag.wait_for_timeout(300)
        abierto = self.pag.evaluate(
            "(id)=>{const c=document.getElementById(id);"
            "const b=c && c.parentElement && c.parentElement.querySelector('.date-display');"
            "if(!b) return false; b.scrollIntoView({block:'center'}); b.click(); return true;}",
            id_campo)
        if not abierto:
            return False
        self.pag.wait_for_timeout(700)
        buscar = ("(iso)=>{const c=document.querySelector('.datepicker');"
                  " return !!(c && c.querySelector('.dp-dia[data-iso=\"'+iso+'\"]'));}")
        for _ in range(18):
            if self.pag.evaluate(buscar, iso):
                break
            avanzo = self.pag.evaluate(
                "()=>{const c=document.querySelector('.datepicker'); if(!c) return false;"
                " const b=c.querySelector('.dp-nav[data-salto=\"1\"]:not([disabled])');"
                " if(!b) return false; b.click(); return true;}")
            if not avanzo:
                break
            self.pag.wait_for_timeout(400)
        pulso = self.pag.evaluate(
            "(iso)=>{const c=document.querySelector('.datepicker'); if(!c) return false;"
            " const d=c.querySelector('.dp-dia[data-iso=\"'+iso+'\"]');"
            " if(!d) return false; d.click(); return true;}", iso)
        if not pulso:
            return False
        self.pag.wait_for_timeout(700)
        return self.valor(f'#{id_campo}') == iso

    def resumen(self):
        ok = sum(1 for o, _, _ in self.pasos if o)
        if self.acta is None:
            print(f'\n{ok}/{len(self.pasos)} pasos correctos', flush=True)
        return ok == len(self.pasos)
