"""Contratos de composición: sin ciclos nuevos ni scripts olvidados."""
import ast
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def test_todos_los_scripts_se_cargan_una_vez_y_arranque_al_final():
    pantalla = RAIZ / 'gestor/pantalla'
    html = (pantalla / 'index.html').read_text(encoding='utf-8')
    scripts = re.findall(r'<script src="/js/([^"?]+)(?:\?[^\"]*)?"></script>', html)
    assert len(scripts) == len(set(scripts))
    assert set(scripts) == {p.name for p in (pantalla / 'js').glob('*.js')}
    assert scripts[0] == '00-infraestructura.js'
    assert scripts[-1] == '14-arranque.js'


def test_las_reglas_y_repositorios_no_dependen_de_http_o_del_escritorio():
    for carpeta in ('dominio', 'datos', 'motor'):
        for path in (RAIZ / 'gestor' / carpeta).rglob('*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    assert not (node.module or '').startswith(
                        ('fastapi', 'webview', 'gestor.web', 'gestor.escritorio')), str(path)


def test_reparaciones_no_dependen_de_su_fachada():
    for path in (RAIZ / 'gestor/motor/reparaciones').glob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert node.module != 'gestor.motor.reparacion', str(path)
