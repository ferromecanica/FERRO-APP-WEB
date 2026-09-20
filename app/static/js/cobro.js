/* La cuenta de la tarjeta mientras se cierra la OT o se cobra en el mostrador:
   cuánto hay que cobrarle al cliente y cuándo cae la plata en el banco. */
(function () {
  var DIAS = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];

  function habiles(desde, cuantos) {
    var dia = new Date(desde.getTime());
    while (cuantos > 0) {
      dia.setDate(dia.getDate() + 1);
      if (dia.getDay() !== 0 && dia.getDay() !== 6) cuantos--;
    }
    return dia;
  }

  function comoFecha(valor) {
    var p = (valor || '').split('-');
    return p.length === 3 ? new Date(+p[0], +p[1] - 1, +p[2]) : new Date();
  }

  function pesos(n) {
    return '$ ' + Math.round(n).toLocaleString('es-AR');
  }

  window.FerroCobro = function (raiz) {
    var select = raiz.querySelector('[name=condicion_id]');
    var total = raiz.querySelector('[name=total_cobrado], [name=total_mostrador]');
    var aviso = raiz.querySelector('[data-cuenta-tarjeta]');
    if (!select || !aviso) return;

    function fecha() {
      var campo = raiz.querySelector('[name=fecha_fin], [name=fecha_cobro], [name=fecha]');
      return comoFecha(campo && campo.value);
    }

    function actualizar() {
      var op = select.options[select.selectedIndex];
      var dias = op ? +op.dataset.dias || 0 : 0;
      var queda = op ? +op.dataset.queda : 100;
      var recargo = op ? +op.dataset.recargo || 0 : 0;
      var facturado = total ? (window.Plata ? Plata.aNumero(total.value) : +total.value)
        : (+aviso.dataset.total || 0);

      if (!op || !op.value || (recargo === 0 && queda === 100 && dias === 0)) {
        aviso.hidden = true;
        return;
      }
      var acredita = habiles(fecha(), dias);
      var partes = [];
      if (facturado) {
        var bruto = facturado * (1 + recargo / 100);
        if (recargo) partes.push('le cobrás <strong>' + pesos(bruto) + '</strong> (recargo ' +
          recargo.toLocaleString('es-AR', { maximumFractionDigits: 2 }) + ' %)');
        partes.push('te acreditan <strong>' + pesos(bruto * queda / 100) + '</strong>');
      }
      partes.push(dias ? ('el ' + DIAS[acredita.getDay()] + ' ' +
        acredita.toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit' }) +
        ' (' + dias + ' día' + (dias === 1 ? '' : 's') + ' hábil' + (dias === 1 ? '' : 'es') + ')') : 'en el día');
      aviso.innerHTML = '<i class="fa-solid fa-credit-card"></i> ' + partes.join(' · ');
      aviso.hidden = false;
    }

    select.addEventListener('change', actualizar);
    raiz.addEventListener('input', actualizar);
    actualizar();
  };
})();
