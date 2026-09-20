/* La cuenta de la tarjeta mientras se cierra la OT o se cobra en el mostrador.

   Iván carga lo que le cobra al cliente y abajo aparece lo que vamos a
   percibir de eso, que es lo que queda registrado como venta. */
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

  function pesos(n) { return '$ ' + Math.round(n).toLocaleString('es-AR'); }

  function cuando(fecha, dias) {
    if (!dias) return 'entra en el día';
    return 'entra el ' + DIAS[fecha.getDay()] + ' ' +
      fecha.toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit' }) +
      ' · ' + dias + ' día' + (dias === 1 ? '' : 's') + ' hábil' + (dias === 1 ? '' : 'es');
  }

  window.FerroCobro = function (raiz) {
    var select = raiz.querySelector('[name=condicion_id]');
    var total = raiz.querySelector('[name=total_cobrado]');
    var caja = raiz.querySelector('[data-percibir]');
    if (!select || !caja) return;

    var monto = caja.querySelector('[data-percibir-monto]');
    var notaCaja = caja.querySelector('[data-percibir-nota]');
    var notaCond = raiz.querySelector('[data-nota-condicion]');
    var paraPercibir = raiz.querySelector('[data-para-percibir]');
    var usar = raiz.querySelector('[data-usar-sugerido]');
    var viejo = raiz.querySelector('[data-cuenta-tarjeta]');   // mostrador

    function fecha() {
      var campo = raiz.querySelector('[name=fecha_fin], [name=fecha_cobro], [name=fecha]');
      return comoFecha(campo && campo.value);
    }

    function elegida() {
      var op = select.options[select.selectedIndex];
      if (!op || !op.value) return null;
      return { dias: +op.dataset.dias || 0, queda: +op.dataset.queda, nombre: op.dataset.nombre || op.text };
    }

    function cobrado() {
      if (total) return window.Plata ? Plata.aNumero(total.value) : +total.value;
      return +(caja.dataset.total || (viejo && viejo.dataset.total) || 0);
    }

    function actualizar() {
      var c = elegida();
      if (notaCond) {
        notaCond.textContent = c && c.queda < 100
          ? c.nombre + ' se queda el ' + (100 - c.queda).toLocaleString('es-AR', { maximumFractionDigits: 2 }) + ' %'
          : '';
      }
      if (paraPercibir) paraPercibir.textContent = '';
      if (!c) { caja.hidden = true; return; }

      var plata = cobrado();
      var entra = plata * c.queda / 100;
      var acredita = habiles(fecha(), c.dias);

      // Cuánto habría que cobrar para percibir el sugerido
      if (paraPercibir && total && c.queda < 100) {
        var sugerido = +total.dataset.sugerido || 0;
        if (sugerido) paraPercibir.textContent = ' · para percibirlos, cobrá ' + pesos(sugerido * 100 / c.queda);
      }

      monto.textContent = pesos(entra);
      notaCaja.textContent = c.queda < 100
        ? cuando(acredita, c.dias) + ' · ' + c.nombre + ' se queda ' + pesos(plata - entra)
        : cuando(acredita, c.dias);
      caja.classList.toggle('con-costo', c.queda < 100);
      caja.hidden = false;
    }

    if (usar && total) {
      usar.addEventListener('click', function (e) {
        e.preventDefault();
        if (window.Plata) Plata.escribir(total, +total.dataset.sugerido || 0);
        else total.value = total.dataset.sugerido;
        actualizar();
        total.focus();
      });
    }
    select.addEventListener('change', actualizar);
    raiz.addEventListener('input', actualizar);
    actualizar();
  };
})();
