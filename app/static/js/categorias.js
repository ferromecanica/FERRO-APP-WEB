/* Desplegables de categoría y subcategoría (la subcategoría muestra solo las de la categoría elegida),
   con alta rápida opcional. Uso: FerroCategorias(arbol, {categoria, subcategoria, nuevaCategoria?, …}) */
window.FerroCategorias = function (arbol, o) {
  var selCat = document.getElementById(o.categoria), selSub = document.getElementById(o.subcategoria);

  function opcion(valor, texto) { var op = document.createElement('option'); op.value = valor; op.textContent = texto; return op; }

  function llenarCategorias(elegida) {
    selCat.innerHTML = '';
    selCat.appendChild(opcion('', o.vacioCategoria));
    arbol.forEach(function (c) { selCat.appendChild(opcion(c.id, c.nombre)); });
    selCat.value = elegida || '';
  }
  function llenarSubcategorias(elegida) {
    var cat = arbol.find(function (c) { return String(c.id) === selCat.value; });
    selSub.innerHTML = '';
    selSub.appendChild(opcion('', cat ? o.vacioSubcategoria : o.vacioSubcategoria + ' (elegí categoría)'));
    (cat ? cat.subs : []).forEach(function (s) { selSub.appendChild(opcion(s.id, s.nombre)); });
    selSub.value = elegida || '';
    selSub.disabled = !cat;
  }

  function csrf() { var m = document.querySelector('input[name="csrf_token"]'); return m ? m.value : ''; }
  function crear(url, datos) {
    var cuerpo = new FormData();
    Object.keys(datos).forEach(function (k) { cuerpo.append(k, datos[k]); });
    return fetch(url, { method: 'POST', body: cuerpo, headers: { 'X-CSRFToken': csrf() } })
      .then(function (r) { return r.json(); })
      .then(function (j) { if (!j.ok) throw new Error(j.error); return j; });
  }

  llenarCategorias(selCat.dataset.valor);
  llenarSubcategorias(selSub.dataset.valor);
  selCat.addEventListener('change', function () {
    llenarSubcategorias('');
    selSub.dispatchEvent(new Event('change', { bubbles: true }));
  });

  if (o.nuevaCategoria) {
    document.getElementById(o.nuevaCategoria).addEventListener('click', function () {
      var nombre = prompt('Nombre de la categoría nueva:');
      if (!nombre || !nombre.trim()) return;
      crear(o.urlCategoria, { nombre: nombre }).then(function (j) {
        arbol.push({ id: j.id, nombre: j.nombre, subs: [] });
        arbol.sort(function (a, b) { return a.nombre.localeCompare(b.nombre); });
        llenarCategorias(j.id); llenarSubcategorias('');
      }).catch(function (e) { alert(e.message); });
    });
  }
  if (o.nuevaSubcategoria) {
    document.getElementById(o.nuevaSubcategoria).addEventListener('click', function () {
      var cat = arbol.find(function (c) { return String(c.id) === selCat.value; });
      if (!cat) { alert('Primero elegí la categoría.'); return; }
      var nombre = prompt('Subcategoría nueva dentro de ' + cat.nombre + ':');
      if (!nombre || !nombre.trim()) return;
      crear(o.urlSubcategoria, { nombre: nombre, categoria_id: cat.id }).then(function (j) {
        cat.subs.push({ id: j.id, nombre: j.nombre });
        cat.subs.sort(function (a, b) { return a.nombre.localeCompare(b.nombre); });
        llenarSubcategorias(j.id);
      }).catch(function (e) { alert(e.message); });
    });
  }
};

/* Botón "+" al lado de un desplegable: pide un nombre, lo da de alta y lo deja elegido. */
window.FerroAltaEnSelect = function (selectId, botonId, url, pregunta) {
  var sel = document.getElementById(selectId);
  document.getElementById(botonId).addEventListener('click', function () {
    var nombre = prompt(pregunta);
    if (!nombre || !nombre.trim()) return;
    var cuerpo = new FormData(); cuerpo.append('nombre', nombre);
    var token = document.querySelector('input[name="csrf_token"]');
    fetch(url, { method: 'POST', body: cuerpo, headers: { 'X-CSRFToken': token ? token.value : '' } })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (!j.ok) throw new Error(j.error);
        var op = document.createElement('option'); op.value = j.id; op.textContent = j.nombre;
        var despues = Array.prototype.find.call(sel.options, function (o) { return o.value && o.textContent.localeCompare(j.nombre) > 0; });
        sel.insertBefore(op, despues || null);
        sel.value = j.id;
        sel.dispatchEvent(new Event('input', { bubbles: true }));
      })
      .catch(function (e) { alert(e.message); });
  });
};
