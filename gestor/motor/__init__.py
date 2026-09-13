# -*- coding: utf-8 -*-
"""El motor que arma un mes de horario.

Un mes no se calcula de una vez: se arma en etapas, siempre las mismas y
siempre en el mismo orden, y cada etapa tiene aquí su propio módulo.

    1. `construccion`  · el mes en bruto, desde la plantilla y el mes anterior
    2. `decisiones`    · lo que alguien decidió: solicitudes, asignaciones, cambios a mano
    3. `balance`       · lo que reparte el motor: descanso semanal, domingos, festivos
    4. `reparacion`    · arreglar rachas largas, áreas sin cubrir, cambios PM→AM
    5. `validacion`    · decir qué salió bien y qué no, sin tocar nada

Debajo de las cinco hay dos módulos de apoyo: `vocabulario`, con los códigos de
turno y los topes, y `comun`, con lo que varias etapas necesitan por igual.
`orquestacion` las llama en orden y junta el resultado.

Las importaciones van en un solo sentido —vocabulario, común, y de ahí hacia
arriba— así que ningún módulo puede depender de otro que dependa de él. Eso es
lo que permite leer una etapa sin tener que abrir las otras cuatro.

Antes esto era un solo archivo de 6.321 líneas. No se cambió ni una línea de
lógica al partirlo: cada función viajó tal cual, con sus comentarios.
"""
from gestor.motor.balance import *  # noqa: F401,F403
from gestor.motor.comun import *  # noqa: F401,F403
from gestor.motor.construccion import *  # noqa: F401,F403
from gestor.motor.decisiones import *  # noqa: F401,F403
from gestor.motor.orquestacion import *  # noqa: F401,F403
from gestor.motor.reparacion import *  # noqa: F401,F403
from gestor.motor.validacion import *  # noqa: F401,F403
from gestor.motor.vocabulario import *  # noqa: F401,F403
