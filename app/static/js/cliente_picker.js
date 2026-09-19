/* Selector de cliente con alta rápida (templates/ot/_cliente_picker.html).
   Buscar: campo #cliente. Alta: recuadro #cliente-nuevo con sus propios campos. */
window.FerroClientePicker = function () {
  var input = document.getElementById('cliente');
  var info = document.getElementById('cliente-info');
  var caja = document.getElementById('cliente-nuevo');
  var marca = caja.querySelector('input[name="c_nuevo"]');
  var nombre = caja.querySelector('input[name="c_nombre"]');
  var opciones = Array.prototype.map.call(document.querySelectorAll('#lista-clientes option'), function (o) { return o.value; });
  var obligatorio = !!input.dataset.obligatorio;
  var estado = { dueno: null, vehiculoNuevo: false, vehiculoSinDueno: false };

  function esc(t) { var d = document.createElement('div'); d.textContent = t; return d.innerHTML; }
  function existe(v) { return opciones.indexOf(v) !== -1; }

  function modoNuevo(activo) {
    caja.hidden = !activo;
    marca.disabled = !activo;
    nombre.required = activo;
    input.disabled = activo;
    input.required = !activo && obligatorio;
    if (activo) { input.value = ''; nombre.focus(); } else { input.focus(); }
    revisar();
  }

  function revisar() {
    var v = input.value.trim();
    if (!caja.hidden) {
      info.textContent = estado.dueno ? 'El vehículo pasa al cliente nuevo.' : '';
    } else if (v && !existe(v)) {
      info.innerHTML = '<i class="fa-solid fa-circle-exclamation" style="color:var(--warn)"></i> No está en la lista. Si es nuevo, tocá <strong>+ Cliente nuevo</strong>.';
    } else if (v && estado.dueno && v !== estado.dueno) {
      info.innerHTML = '<i class="fa-solid fa-right-left"></i> El vehículo es de <strong>' + esc(estado.dueno.split(' · ')[0]) + '</strong>: pasa a este cliente.';
    } else if (v && !estado.dueno && estado.vehiculoNuevo) {
      info.textContent = 'El vehículo nuevo queda asociado a este cliente.';
    } else if (v && !estado.dueno && estado.vehiculoSinDueno) {
      info.textContent = 'El vehículo no tenía dueño: queda asociado a este cliente.';
    } else if (!v && !obligatorio) {
      info.textContent = 'Sin cliente por ahora: se pide al cerrar la OT.';
    } else {
      info.textContent = '';
    }
  }

  input.addEventListener('input', revisar);
  document.getElementById('btn-cliente-nuevo').addEventListener('click', function () { modoNuevo(true); });
  document.getElementById('cerrar-cliente-nuevo').addEventListener('click', function () { modoNuevo(false); });
  revisar();
  return { input: input, estado: estado, revisar: revisar, existe: existe, enAlta: function () { return !caja.hidden; } };
};
