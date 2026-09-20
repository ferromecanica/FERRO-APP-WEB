/* Desplegable propio para los campos de búsqueda.

   El que trae el navegador (input + datalist) no se puede pintar: sale negro
   con letras blancas. Este toma las mismas opciones del <datalist>, que queda
   en la página por si otro script lo lee, y las muestra con los colores de la
   app. Al elegir avisa con los eventos de siempre (input y change), así lo que
   ya escuchaba el campo sigue funcionando igual. */
(function () {
  var MAXIMO = 60;  // cuántas mostrar de una: la lista de repuestos es larga

  function pelado(texto) {
    return (texto || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  }

  function armar(campo) {
    var lista = document.getElementById(campo.getAttribute('list'));
    if (!lista || campo.dataset.desplegable) return;
    campo.dataset.desplegable = '1';
    campo.removeAttribute('list');        // que no salga el del navegador
    campo.setAttribute('autocomplete', 'off');

    var caja = document.createElement('div');
    caja.className = 'desplegable';
    caja.hidden = true;
    // Adentro del diálogo si el campo está en uno: si no, queda tapado
    (campo.closest('dialog') || document.body).appendChild(caja);

    var visibles = [], marcada = -1, eligiendo = false;

    function opciones() {
      return Array.prototype.map.call(lista.querySelectorAll('option'), function (o) {
        return { valor: o.value, nota: o.textContent.trim() };
      });
    }

    function ubicar() {
      /* Va fijo contra la pantalla: así queda bien tanto suelto en la página
         como adentro de un diálogo, sin depender de quién sea el padre. */
      var r = campo.getBoundingClientRect();
      var alto = caja.offsetHeight || 200;
      var abajo = window.innerHeight - r.bottom;
      caja.style.left = r.left + 'px';
      caja.style.width = r.width + 'px';
      if (abajo < alto + 12 && r.top > abajo) {
        caja.style.top = Math.max(8, r.top - alto - 4) + 'px';   // no entra abajo: va arriba
      } else {
        caja.style.top = (r.bottom + 4) + 'px';
        caja.style.maxHeight = Math.max(140, abajo - 12) + 'px';
      }
    }

    function cerrar() {
      caja.hidden = true;
      marcada = -1;
    }

    function elegir(op) {
      campo.value = op.valor;
      cerrar();
      // El aviso de "input" es para los otros scripts, no para volver a abrir
      eligiendo = true;
      campo.dispatchEvent(new Event('input', { bubbles: true }));
      campo.dispatchEvent(new Event('change', { bubbles: true }));
      eligiendo = false;
    }

    function marcar(i) {
      var filas = caja.querySelectorAll('.desplegable-op');
      if (!filas.length) return;
      marcada = (i + filas.length) % filas.length;
      filas.forEach(function (f, n) { f.classList.toggle('activa', n === marcada); });
      filas[marcada].scrollIntoView({ block: 'nearest' });
    }

    function abrir() {
      if (eligiendo) return;
      /* Todas las palabras tienen que aparecer, en cualquier orden y en
         cualquier parte: "fil bos cro" encuentra "Kit filtro Bosch Cronos". */
      var palabras = pelado(campo.value).split(/\s+/).filter(Boolean);
      visibles = opciones().filter(function (o) {
        var texto = pelado(o.valor + ' ' + o.nota);
        return palabras.every(function (p) { return texto.indexOf(p) !== -1; });
      }).slice(0, MAXIMO);

      if (!visibles.length) { cerrar(); return; }
      caja.innerHTML = '';
      visibles.forEach(function (o, n) {
        var fila = document.createElement('div');
        fila.className = 'desplegable-op';
        fila.innerHTML = '<span class="desplegable-valor"></span>' +
                         (o.nota ? '<span class="desplegable-nota"></span>' : '');
        fila.querySelector('.desplegable-valor').textContent = o.valor;
        if (o.nota) fila.querySelector('.desplegable-nota').textContent = o.nota;
        fila.addEventListener('mousedown', function (e) { e.preventDefault(); elegir(o); });
        fila.addEventListener('mouseenter', function () { marcar(n); });
        caja.appendChild(fila);
      });
      marcada = -1;
      caja.style.maxHeight = '';
      caja.hidden = false;
      ubicar();                 // con la caja visible ya se sabe cuánto mide
    }

    campo.addEventListener('focus', abrir);
    campo.addEventListener('input', abrir);
    campo.addEventListener('blur', function () { setTimeout(cerrar, 120); });
    campo.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        if (caja.hidden) { abrir(); return; }
        e.preventDefault();
        marcar(marcada + (e.key === 'ArrowDown' ? 1 : -1));
      } else if (e.key === 'Enter' && !caja.hidden && marcada >= 0) {
        e.preventDefault();
        elegir(visibles[marcada]);
      } else if (e.key === 'Escape' && !caja.hidden) {
        e.preventDefault();
        cerrar();
      }
    });
    window.addEventListener('resize', function () { if (!caja.hidden) ubicar(); });
    window.addEventListener('scroll', function () { if (!caja.hidden) ubicar(); }, true);
  }

  function arrancar(donde) {
    (donde || document).querySelectorAll('input[list]').forEach(armar);
  }

  window.FerroDesplegables = arrancar;
  document.addEventListener('DOMContentLoaded', function () { arrancar(document); });
  /* Los pedazos que trae htmx vienen con sus propios campos. */
  document.addEventListener('htmx:afterSwap', function (e) { arrancar(e.target); });
})();
