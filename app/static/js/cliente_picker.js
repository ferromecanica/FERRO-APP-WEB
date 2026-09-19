/* Selector de cliente con alta rápida (templates/ot/_cliente_picker.html). */
window.FerroClientePicker = function () {
  var input = document.getElementById('cliente');
  var info = document.getElementById('cliente-info');
  var nuevo = document.getElementById('cliente-nuevo');
  var opciones = Array.prototype.map.call(document.querySelectorAll('#lista-clientes option'), function (o) { return o.value; });
  var estado = { dueno: null, vehiculoNuevo: false, vehiculoSinDueno: false };

  function esc(t) { var d = document.createElement('div'); d.textContent = t; return d.innerHTML; }
  function existe(v) { return opciones.indexOf(v) !== -1; }

  function revisar() {
    var v = input.value.trim(), hay = existe(v);
    nuevo.hidden = hay || (!v && nuevo.hidden);
    if (hay && estado.dueno && v !== estado.dueno) {
      info.innerHTML = '<i class="fa-solid fa-right-left"></i> El vehículo es de <strong>' + esc(estado.dueno.split(' · ')[0]) +
        '</strong>: pasa a este cliente.';
    } else if (hay && !estado.dueno && estado.vehiculoNuevo) {
      info.textContent = 'El vehículo nuevo queda asociado a este cliente.';
    } else if (hay && !estado.dueno && estado.vehiculoSinDueno) {
      info.textContent = 'El vehículo no tenía dueño: queda asociado a este cliente.';
    } else if (!v && input.dataset.opcional && nuevo.hidden) {
      info.textContent = 'Sin cliente por ahora: se pide al cerrar la OT.';
    } else {
      info.textContent = '';
    }
  }

  input.addEventListener('input', revisar);
  document.getElementById('btn-cliente-nuevo').addEventListener('click', function () {
    input.value = '';
    input.placeholder = 'Nombre y apellido del cliente nuevo';
    nuevo.hidden = false;
    input.focus();
    revisar();
  });
  revisar();
  return { input: input, estado: estado, revisar: revisar, existe: existe };
};
