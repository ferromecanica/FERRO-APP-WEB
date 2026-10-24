"""La pantalla de ingreso: sin carteles de más, pero avisando los errores."""
import os
import re

os.environ['LOGIN_OBLIGATORIO'] = '1'

from wsgi import app
app.config['WTF_CSRF_ENABLED'] = False
assert app.config['LOGIN_OBLIGATORIO'], 'la prueba necesita el login prendido'
c = app.test_client()
carteles = lambda b: re.findall(r'class="flash flash-(\w+)">\s*(.*?)\s*</div>', b, re.S)

# ── Al mandarte al login no se avisa nada: el cartel se leía como un campo más ──
b = c.get('/administracion/', follow_redirects=True).get_data(as_text=True)
assert carteles(b) == [], carteles(b)
assert 'Ingresá para continuar' not in b
assert 'Contraseña' in b and 'Ingresar' in b, 'tiene que verse el formulario'

# ── Pero un error sí se avisa ──
b = c.post('/login', data={'email': 'nadie@ejemplo.com', 'password': 'loquesea'},
           follow_redirects=True).get_data(as_text=True)
assert ('error', 'Email o contraseña incorrectos.') in carteles(b), carteles(b)

print('LOGIN OK')
