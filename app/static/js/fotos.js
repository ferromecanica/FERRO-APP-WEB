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
        lienzo.toBlob(function (blob) { blob ? ok(blob) : mal(new Error('No se pudo procesar la imagen')); }, 'image/jpeg', CALIDAD);
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
          datos.append('imagen', await achicar(archivos[n]), 'foto.jpg');
          datos.append('destino', destino());
          datos.append('descripcion', descripcion ? descripcion.value : '');
          var r = await fetch(caja.dataset.url, { method: 'POST', body: datos, headers: { 'X-CSRFToken': csrf() } });
          var j;
          try { j = await r.json(); } catch (e) {
            throw new Error(r.status === 413 ? 'la foto es demasiado grande' : 'el servidor respondió un error (' + r.status + ')');
          }
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

/* Visor de fotos: tocar una miniatura la abre grande; flechas, teclado (← → Esc) y deslizar con el dedo.
   Recorre las fotos del mismo apartado (Para el reporte / Del taller). */
(function () {
  var visor, img, texto, contador, linkDrive, fotos = [], actual = 0, inicioX = null;

  function armar() {
    visor = document.createElement('div');
    visor.className = 'visor';
    visor.hidden = true;
    visor.innerHTML =
      '<button type="button" class="visor-cerrar" title="Cerrar (Esc)"><i class="fa-solid fa-xmark"></i></button>' +
      '<button type="button" class="visor-flecha visor-ant" title="Anterior (←)"><i class="fa-solid fa-chevron-left"></i></button>' +
      '<figure class="visor-foto"><img alt=""><figcaption><span class="visor-texto"></span>' +
      '<span class="visor-pie"><span class="visor-contador"></span>' +
      '<a class="visor-drive" target="_blank" rel="noopener"><i class="fa-brands fa-google-drive"></i> Abrir en Drive</a></span></figcaption></figure>' +
      '<button type="button" class="visor-flecha visor-sig" title="Siguiente (→)"><i class="fa-solid fa-chevron-right"></i></button>';
    document.body.appendChild(visor);
    img = visor.querySelector('img');
    texto = visor.querySelector('.visor-texto');
    contador = visor.querySelector('.visor-contador');
    linkDrive = visor.querySelector('.visor-drive');
    visor.querySelector('.visor-cerrar').addEventListener('click', cerrar);
    visor.querySelector('.visor-ant').addEventListener('click', function () { mover(-1); });
    visor.querySelector('.visor-sig').addEventListener('click', function () { mover(1); });
    visor.addEventListener('click', function (e) { if (e.target === visor) cerrar(); });
    visor.addEventListener('touchstart', function (e) { inicioX = e.touches[0].clientX; }, { passive: true });
    visor.addEventListener('touchend', function (e) {
      if (inicioX === null) return;
      var dx = e.changedTouches[0].clientX - inicioX;
      if (Math.abs(dx) > 40) mover(dx < 0 ? 1 : -1);
      inicioX = null;
    });
  }

  function mostrar() {
    var f = fotos[actual];
    img.src = f.dataset.visor;
    texto.textContent = f.dataset.visorTexto || '';
    contador.textContent = (actual + 1) + ' / ' + fotos.length;
    linkDrive.href = f.dataset.visorDrive || '#';
    visor.classList.toggle('una-sola', fotos.length < 2);
  }
  function mover(paso) { actual = (actual + paso + fotos.length) % fotos.length; mostrar(); }
  function cerrar() { visor.hidden = true; img.src = ''; document.body.classList.remove('visor-abierto'); }

  document.addEventListener('click', function (e) {
    var a = e.target.closest('a[data-visor]');
    if (!a || !a.dataset.visor) return;
    e.preventDefault();
    if (!visor) armar();
    fotos = Array.prototype.slice.call(a.closest('.galeria').querySelectorAll('a[data-visor]'))
      .filter(function (x) { return x.dataset.visor; });
    actual = fotos.indexOf(a);
    mostrar();
    visor.hidden = false;
    document.body.classList.add('visor-abierto');
  });
  document.addEventListener('keydown', function (e) {
    if (!visor || visor.hidden) return;
    if (e.key === 'Escape') cerrar();
    if (e.key === 'ArrowLeft') mover(-1);
    if (e.key === 'ArrowRight') mover(1);
  });
})();
