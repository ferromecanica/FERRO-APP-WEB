/* La cuenta del cobro mientras se cierra la OT o se cobra en el mostrador.

   Iván carga lo que le cobra al cliente y abajo aparece lo que vamos a
   percibir de eso, que es lo que queda registrado como venta. El cliente
   puede pagar con dos formas a la vez (una parte en efectivo y el resto con
   tarjeta): cada parte tiene su comisión y su fecha, y se suman. */
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

  function numero(campo) {
    if (!campo) return 0;
    return window.Plata ? Plata.aNumero(campo.value) : (+campo.value || 0);
  }

  function cuando(fecha, dias) {
    if (!dias) return 'entra en el día';
    return 'entra el ' + DIAS[fecha.getDay()] + ' ' +
      fecha.toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit' }) +
      ' · ' + dias + ' día' + (dias === 1 ? '' : 's') + ' hábil' + (dias === 1 ? '' : 'es');
  }

  window.FerroCobro = function (raiz) {
    var caja = raiz.querySelector('[data-percibir]');
    var filas = [].slice.call(raiz.querySelectorAll('[data-pago]'));
    if (!caja || !filas.length) return;

    var monto = caja.querySelector('[data-percibir-monto]');
    var notaCaja = caja.querySelector('[data-percibir-nota]');
    var paraPercibir = raiz.querySelector('[data-para-percibir]');
    var usar = raiz.querySelector('[data-usar-sugerido]');
    var agregar = raiz.querySelector('[data-agregar-pago]');
    var quitar = raiz.querySelector('[data-quitar-pago]');
    var segunda = raiz.querySelector('[data-segunda]');
    var primero = filas[0].querySelector('input');

    function fecha() {
      var campo = raiz.querySelector('[name=fecha_fin], [name=fecha_cobro], [name=fecha]');
      return comoFecha(campo && campo.value);
    }

    function leer(fila) {
      if (fila.hidden) return null;
      var select = fila.querySelector('select');
      var op = select.options[select.selectedIndex];
      if (!op || !op.value) return null;
      return {
        dias: +op.dataset.dias || 0, queda: +op.dataset.queda,
        nombre: op.dataset.nombre || op.text, destino: op.dataset.destino || '',
        bruto: numero(fila.querySelector('input')), fila: fila,
      };
    }

    function actualizar() {
      var partes = filas.map(leer).filter(Boolean);
      filas.forEach(function (f) {
        var nota = f.querySelector('[data-nota-condicion]');
        var p = leer(f);
        if (nota) {
          nota.textContent = p && p.queda < 100
            ? p.nombre + ' se queda el ' + (100 - p.queda).toLocaleString('es-AR', { maximumFractionDigits: 2 }) + ' %'
            : (p && p.destino === 'Caja' ? 'va a la caja de Iván' : '');
        }
      });

      if (paraPercibir) paraPercibir.textContent = '';
      if (!partes.length) { caja.hidden = true; return; }

      var bruto = 0, entra = 0, ultima = 0, tapa = null;
      partes.forEach(function (p) {
        bruto += p.bruto;
        entra += p.bruto * p.queda / 100;
        if (p.dias >= ultima) { ultima = p.dias; tapa = p; }
      });

      // Con una sola forma de pago: cuánto habría que cobrar para percibir el sugerido
      if (paraPercibir && partes.length === 1 && primero && partes[0].queda < 100) {
        var sugerido = +primero.dataset.sugerido || 0;
        if (sugerido) paraPercibir.textContent = ' · para percibirlos, cobrá ' + pesos(sugerido * 100 / partes[0].queda);
      }

      monto.textContent = pesos(entra);
      var detalle = cuando(habiles(fecha(), ultima), ultima);
      if (bruto - entra >= 1) detalle += ' · la tarjeta se queda ' + pesos(bruto - entra);
      if (partes.length > 1) {
        detalle = partes.map(function (p) {
          return p.nombre + ' ' + pesos(p.bruto * p.queda / 100);
        }).join(' + ') + ' · ' + detalle;
      }
      notaCaja.textContent = detalle;
      caja.classList.toggle('con-costo', bruto - entra >= 1);
      caja.hidden = false;
    }

    if (usar && primero) {
      usar.addEventListener('click', function (e) {
        e.preventDefault();
        var sugerido = +primero.dataset.sugerido || 0;
        if (window.Plata) Plata.escribir(primero, sugerido); else primero.value = sugerido;
        actualizar();
        primero.focus();
      });
    }
    if (agregar && segunda) {
      agregar.addEventListener('click', function () {
        segunda.hidden = false;
        agregar.hidden = true;
        // Lo que falta para llegar al sugerido, que es lo más probable que cobre
        var resto = (+primero.dataset.sugerido || 0) - numero(primero);
        var campo = segunda.querySelector('input');
        if (resto > 0 && !numero(campo)) {
          if (window.Plata) Plata.escribir(campo, resto); else campo.value = resto;
        }
        segunda.querySelector('select').focus();
        actualizar();
      });
    }
    if (quitar && segunda) {
      quitar.addEventListener('click', function () {
        segunda.hidden = true;
        if (agregar) agregar.hidden = false;
        segunda.querySelector('select').value = '';
        segunda.querySelector('input').value = '';
        actualizar();
      });
    }
    if (segunda && !segunda.hidden && agregar) agregar.hidden = true;
    raiz.addEventListener('change', actualizar);
    raiz.addEventListener('input', actualizar);
    actualizar();
  };
})();
