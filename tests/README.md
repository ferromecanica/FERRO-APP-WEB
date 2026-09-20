# Pruebas

Cada archivo prueba un módulo de punta a punta contra una base de prueba.

    cp instance/ferro.sqlite /tmp/respaldo.sqlite        # si tenés datos que no querés perder
    .venv/bin/flask --app wsgi demo                      # base con datos ficticios (sobre una base vacía)
    PYTHONPATH=. .venv/bin/python tests/test_ingresos.py

Cada prueba deja datos en la base: conviene partir de una base recién creada
(`rm instance/ferro.sqlite && .venv/bin/python scripts/migrar.py && .venv/bin/flask --app wsgi demo`).

Las pruebas dejan datos en la base: corrigen precios, crean presupuestos, etc.
Si una falla porque "no cambia nada", empezá de una base nueva.
