/* Campos de plata: se escriben con el $ y los puntos de miles puestos.
   Basta con ponerle la clase "plata" al input; el servidor entiende el formato.

   Con la clase "con-signo" además deja escribir en negativo, para los ajustes
   de la caja chica ("saqué $5.000"). El resto de los campos no lo permite: una
   venta o un repuesto en menos no significa nada. */
(function () {
  function soloNumero(texto, conSigno) {
    var limpio = (texto || '').replace(/[^\d,-]/g, '');
    var negativo = conSigno && limpio.charAt(0) === '-';
    return (negativo ? '-' : '') + limpio.replace(/-/g, '');
  }

  function formatear(texto, conSigno) {
    var limpio = soloNumero(texto, conSigno);
    var negativo = limpio.charAt(0) === '-';
    limpio = limpio.replace('-', '');
    if (!limpio) return negativo ? '$ -' : '';   // recién escribió el menos
    var partes = limpio.split(',');
    var entero = partes[0].replace(/^0+(?=\d)/, '') || '0';
    entero = entero.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    return '$ ' + (negativo ? '-' : '') + entero + (partes.length > 1 ? ',' + partes[1].slice(0, 2) : '');
  }

  function aNumero(texto, conSigno) {
    var limpio = soloNumero(texto, conSigno).replace(/\./g, '').replace(',', '.');
    return parseFloat(limpio) || 0;
  }

  function pintar(donde) {
    (donde || document).querySelectorAll('input.plata').forEach(function (campo) {
      if (campo.value) campo.value = formatear(campo.value, campo.classList.contains('con-signo'));
    });
  }

  window.Plata = {
    aNumero: aNumero,
    formatear: formatear,
    pintar: pintar,
    /* Escribe un número en un campo, con los decimales que haga falta. */
    escribir: function (campo, valor, decimales) {
      if (!valor) { campo.value = ''; return; }
      campo.value = formatear(valor.toLocaleString('es-AR', {
        minimumFractionDigits: decimales || 0, maximumFractionDigits: decimales || 0,
      }));
    },
  };

  document.addEventListener('input', function (e) {
    var campo = e.target;
    if (!campo.classList || !campo.classList.contains('plata')) return;
    var antes = campo.value.length, cursor = campo.selectionStart;
    campo.value = formatear(campo.value, campo.classList.contains('con-signo'));
    var corrimiento = campo.value.length - antes;
    try {
      campo.setSelectionRange(Math.max(0, cursor + corrimiento), Math.max(0, cursor + corrimiento));
    } catch (err) { /* algunos navegadores no dejan mover el cursor */ }
    campo.dispatchEvent(new CustomEvent('plata-cambio', { bubbles: true }));
  });

  document.addEventListener('DOMContentLoaded', function () { pintar(document); });
  /* Los pedazos que trae htmx (fichas, renglones) vienen sin formatear. */
  document.addEventListener('htmx:afterSwap', function (e) { pintar(e.target); });
})();
