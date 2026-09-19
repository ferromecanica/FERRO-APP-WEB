/* Tablas configurables (table.tabla-config[data-tabla]):
   - ancho de columna ajustable arrastrando el borde del título (doble clic: vuelve al ancho automático)
   - botón "Columnas" para elegir cuáles ver ([data-columnas-para="<nombre de tabla>"])
   La configuración se recuerda en este navegador. Se aplica con reglas CSS, así sobrevive
   a las recargas de la tabla por el buscador. */
(function () {
  function leer(clave) {
    try { return JSON.parse(localStorage.getItem('ferro-tabla-' + clave)) || { ocultas: [], anchos: {} }; }
    catch (e) { return { ocultas: [], anchos: {} }; }
  }
  function guardar(clave, cfg) {
    try { localStorage.setItem('ferro-tabla-' + clave, JSON.stringify(cfg)); } catch (e) { /* modo privado */ }
  }

  function aplicar(clave, cfg) {
    var id = 'estilo-tabla-' + clave, estilo = document.getElementById(id);
    if (!estilo) { estilo = document.createElement('style'); estilo.id = id; document.head.appendChild(estilo); }
    var sel = '[data-tabla="' + clave + '"] ';
    var reglas = cfg.ocultas.map(function (c) { return sel + '[data-col="' + c + '"]{display:none}'; });
    Object.keys(cfg.anchos).forEach(function (c) {
      var w = cfg.anchos[c] + 'px';
      reglas.push(sel + '[data-col="' + c + '"]{width:' + w + ';min-width:' + w + ';max-width:' + w + '}');
    });
    estilo.textContent = reglas.join('\n');
  }

  function prepararTabla(tabla) {
    var clave = tabla.dataset.tabla, cfg = leer(clave);
    aplicar(clave, cfg);  // cfg se vuelve a leer antes de cada cambio de ancho
    tabla.querySelectorAll('thead th[data-col]').forEach(function (th) {
      if (th.querySelector('.asa')) return;
      var asa = document.createElement('span');
      asa.className = 'asa';
      asa.title = 'Arrastrá para cambiar el ancho · doble clic: automático';
      th.appendChild(asa);
      asa.addEventListener('click', function (e) { e.stopPropagation(); });
      asa.addEventListener('dblclick', function (e) {
        e.stopPropagation();
        cfg = leer(clave); delete cfg.anchos[th.dataset.col]; guardar(clave, cfg); aplicar(clave, cfg);
      });
      asa.addEventListener('mousedown', function (e) {
        e.preventDefault();
        cfg = leer(clave);  // lo último guardado (ej. columnas ocultadas recién)
        var x0 = e.clientX, w0 = th.getBoundingClientRect().width;
        document.body.classList.add('redimensionando');
        function mover(ev) {
          cfg.anchos[th.dataset.col] = Math.max(50, Math.round(w0 + ev.clientX - x0));
          aplicar(clave, cfg);
        }
        function soltar() {
          document.removeEventListener('mousemove', mover);
          document.removeEventListener('mouseup', soltar);
          document.body.classList.remove('redimensionando');
          guardar(clave, cfg);
        }
        document.addEventListener('mousemove', mover);
        document.addEventListener('mouseup', soltar);
      });
    });
  }

  function prepararSelector(caja) {
    var clave = caja.dataset.columnasPara, boton = caja.querySelector('button'), menu = caja.querySelector('.menu-columnas');
    function armar() {
      var tabla = document.querySelector('table[data-tabla="' + clave + '"]');
      if (!tabla) return;
      var cfg = leer(clave);
      menu.innerHTML = '';
      tabla.querySelectorAll('thead th[data-col]').forEach(function (th) {
        var col = th.dataset.col, fija = col === 'material';
        var label = document.createElement('label');
        label.className = 'check';
        label.innerHTML = '<input type="checkbox"' + (cfg.ocultas.indexOf(col) < 0 ? ' checked' : '') + (fija ? ' disabled' : '') + '> ' +
          th.firstChild.textContent.trim();
        label.querySelector('input').addEventListener('change', function (e) {
          var c = leer(clave);
          c.ocultas = c.ocultas.filter(function (x) { return x !== col; });
          if (!e.target.checked) c.ocultas.push(col);
          guardar(clave, c); aplicar(clave, c);
        });
        menu.appendChild(label);
      });
      var reset = document.createElement('button');
      reset.type = 'button'; reset.className = 'btn btn-sm'; reset.textContent = 'Restablecer columnas y anchos';
      reset.addEventListener('click', function () { guardar(clave, { ocultas: [], anchos: {} }); aplicar(clave, leer(clave)); armar(); });
      menu.appendChild(reset);
    }
    boton.addEventListener('click', function (e) { e.stopPropagation(); armar(); menu.hidden = !menu.hidden; });
    menu.addEventListener('click', function (e) { e.stopPropagation(); });
    document.addEventListener('click', function () { menu.hidden = true; });
  }

  function iniciar() {
    document.querySelectorAll('table.tabla-config[data-tabla]').forEach(prepararTabla);
  }
  document.querySelectorAll('[data-columnas-para]').forEach(prepararSelector);
  iniciar();
  document.body.addEventListener('htmx:afterSwap', iniciar);
})();
