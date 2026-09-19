/* Tablas configurables (table.tabla-config[data-tabla]):
   - columnas movibles: se arrastra el título y se suelta en otra posición (Material queda primera)
   - ancho de columna ajustable arrastrando el borde del título (doble clic: vuelve al ancho automático)
   - botón "Columnas" para elegir cuáles ver ([data-columnas-para="<nombre de tabla>"])
   La configuración se recuerda en este navegador. Se aplica con reglas CSS, así sobrevive
   a las recargas de la tabla por el buscador. */
(function () {
  function leer(clave) {
    var cfg;
    try { cfg = JSON.parse(localStorage.getItem('ferro-tabla-' + clave)); } catch (e) { cfg = null; }
    cfg = cfg || {};
    cfg.ocultas = cfg.ocultas || []; cfg.anchos = cfg.anchos || {}; cfg.orden = cfg.orden || [];
    return cfg;
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

  function reordenar(tabla, orden) {
    if (!orden.length) return;
    var filas = tabla.querySelectorAll('tr');
    filas.forEach(function (fila) {
      var celdas = {};
      Array.prototype.forEach.call(fila.children, function (c) { celdas[c.dataset.col] = c; });
      orden.forEach(function (col) { if (celdas[col]) fila.appendChild(celdas[col]); });
      // columnas nuevas que no estaban en el orden guardado: al final, en su orden original
    });
  }

  function prepararTabla(tabla) {
    var clave = tabla.dataset.tabla, cfg = leer(clave);
    aplicar(clave, cfg);  // cfg se vuelve a leer antes de cada cambio de ancho
    reordenar(tabla, cfg.orden);
    tabla.querySelectorAll('thead th[data-col]').forEach(function (th) {
      if (th.querySelector('.asa')) return;
      if (th.dataset.col !== 'material') {
        th.draggable = true;
        th.addEventListener('dragstart', function (e) {
          if (document.body.classList.contains('redimensionando')) { e.preventDefault(); return; }
          e.dataTransfer.setData('text/plain', th.dataset.col);
          e.dataTransfer.effectAllowed = 'move';
          th.classList.add('arrastrando');
        });
        th.addEventListener('dragend', function () {
          th.classList.remove('arrastrando');
          tabla.querySelectorAll('.soltar-aca').forEach(function (x) { x.classList.remove('soltar-aca'); });
        });
      }
      th.addEventListener('dragover', function (e) {
        if (th.dataset.col === 'material') return;
        e.preventDefault(); e.dataTransfer.dropEffect = 'move'; th.classList.add('soltar-aca');
      });
      th.addEventListener('dragleave', function () { th.classList.remove('soltar-aca'); });
      th.addEventListener('drop', function (e) {
        e.preventDefault();
        var movida = e.dataTransfer.getData('text/plain'), destino = th.dataset.col;
        if (!movida || movida === destino || destino === 'material') return;
        var actual = Array.prototype.map.call(tabla.querySelectorAll('thead th[data-col]'), function (x) { return x.dataset.col; });
        actual.splice(actual.indexOf(movida), 1);
        var i = actual.indexOf(destino);
        var desdeIzq = Array.prototype.indexOf.call(th.parentNode.children, th) >
          Array.prototype.indexOf.call(th.parentNode.children, tabla.querySelector('thead th[data-col="' + movida + '"]'));
        actual.splice(desdeIzq ? i + 1 : i, 0, movida);
        var c = leer(clave); c.orden = actual; guardar(clave, c);
        reordenar(tabla, actual);
      });
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
      reset.type = 'button'; reset.className = 'btn btn-sm'; reset.textContent = 'Restablecer columnas, orden y anchos';
      var ayuda = document.createElement('div');
      ayuda.className = 'muted small';
      ayuda.textContent = 'Para mover una columna, arrastrá su título a otra posición.';
      menu.appendChild(ayuda);
      reset.addEventListener('click', function () { guardar(clave, {}); location.reload(); });
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
