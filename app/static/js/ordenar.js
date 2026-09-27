/* Clic en un título de tabla: ordena por esa columna; otro clic invierte
   (ascendente / descendente).

   La tabla dice de qué formulario de filtros cuelga con data-filtros="<id>";
   ahí viven los campos ocultos "orden" y "dir", y el htmx de ese formulario
   es el que vuelve a pedir el listado. */
(function () {
  document.addEventListener('click', function (e) {
    var th = e.target.closest('th[data-orden]');
    if (!th || e.target.closest('.asa')) return;   // el asa es para mover la columna, no para ordenar
    var tabla = th.closest('table');
    var form = document.getElementById(tabla && tabla.dataset.filtros);
    if (!form) return;
    var orden = form.querySelector('[name=orden]'), dir = form.querySelector('[name=dir]');
    dir.value = (orden.value === th.dataset.orden && dir.value === 'asc') ? 'desc' : 'asc';
    orden.value = th.dataset.orden;
    htmx.trigger(form, 'ordenar');
  });
})();
