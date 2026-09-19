/* Subida de fotos de OT: achica cada foto en el navegador (así sube rápido con datos
   móviles) y las manda de a una a Ferro, que las guarda en Drive.
   Uso: <div data-subir-fotos data-url="/ot/10000/fotos"> … (ver templates/ot/_subir_fotos.html) */
(function () {
  var LADO_MAX = 1600, CALIDAD = 0.8;

  function achicar(archivo) {
    return new Promise(function (ok, mal) {
      var img = new Image(), url = URL.createObjectURL(archivo);
      img.onload = function () {
        var escala = Math.min(1, LADO_MAX / Math.max(img.naturalWidth, img.naturalHeight));
        var lienzo = document.createElement('canvas');
        lienzo.width = Math.round(img.naturalWidth * escala);
        lienzo.height = Math.round(img.naturalHeight * escala);
        lienzo.getContext('2d').drawImage(img, 0, 0, lienzo.width, lienzo.height);
        URL.revokeObjectURL(url);
        ok(lienzo.toDataURL('image/jpeg', CALIDAD));
      };
      img.onerror = function () { URL.revokeObjectURL(url); mal(new Error('No se pudo leer la imagen')); };
      img.src = url;
    });
  }

  function csrf() {
    var m = document.querySelector('input[name="csrf_token"]');
    return m ? m.value : '';
  }

  document.querySelectorAll('[data-subir-fotos]').forEach(function (caja) {
    var inputs = caja.querySelectorAll('input[type="file"]');
    var cola = caja.querySelector('.cola-fotos');
    var destino = function () { var r = caja.querySelector('input[name="destino_foto"]:checked'); return r ? r.value : 'reporte'; };
    var descripcion = caja.querySelector('input[name="descripcion_foto"]');

    async function subir(archivos) {
      if (!archivos.length) return;
      var errores = 0;
      inputs.forEach(function (i) { i.disabled = true; });
      for (var n = 0; n < archivos.length; n++) {
        var fila = document.createElement('div');
        fila.className = 'cola-item';
        fila.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Subiendo foto ' + (n + 1) + ' de ' + archivos.length + '…';
        cola.appendChild(fila);
        try {
          var datos = new FormData();
          datos.append('imagen', await achicar(archivos[n]));
          datos.append('destino', destino());
          datos.append('descripcion', descripcion ? descripcion.value : '');
          var r = await fetch(caja.dataset.url, { method: 'POST', body: datos, headers: { 'X-CSRFToken': csrf() } });
          var j = await r.json();
          if (!j.ok) throw new Error(j.error || 'Error al subir');
          fila.innerHTML = '<i class="fa-solid fa-circle-check" style="color:var(--ok)"></i> Foto ' + (n + 1) + ' subida';
        } catch (e) {
          errores++;
          fila.innerHTML = '<i class="fa-solid fa-circle-exclamation" style="color:var(--danger)"></i> Foto ' + (n + 1) + ': ' + e.message;
        }
      }
      inputs.forEach(function (i) { i.disabled = false; i.value = ''; });
      if (!errores) location.reload();
    }

    inputs.forEach(function (input) {
      input.addEventListener('change', function () { subir(Array.prototype.slice.call(input.files)); });
    });
  });
})();

/* Editar una foto (destino y descripción) en el lugar */
document.addEventListener('click', function (e) {
  var editar = e.target.closest('[data-editar-foto]');
  if (editar) {
    var fig = document.getElementById('foto-' + editar.dataset.editarFoto);
    fig.querySelector('.foto-edicion').hidden = false;
    fig.querySelector('figcaption').hidden = true;
  }
  var cancelar = e.target.closest('[data-cancelar-foto]');
  if (cancelar) {
    var f = cancelar.closest('figure');
    f.querySelector('.foto-edicion').hidden = true;
    f.querySelector('figcaption').hidden = false;
  }
});
