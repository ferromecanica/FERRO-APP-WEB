/**
 * Conexión de Ferro con Google Drive: reportes PDF y fotos de las OT.
 *
 * accion=reporte (o sin acción): Ferro manda el HTML del reporte, del presupuesto o de la
 *   circular contable. Va a la carpeta que diga carpeta (presupuestos | circulares) o, si
 *   Ferro manda carpeta_id, a esa carpeta de Drive. Si no dice nada, a la de reportes.
 *   Este script reemplaza
 *   __LOGO__, __FIRMA__ y __FOTO:archivo__ por las imágenes de Drive, lo convierte a PDF,
 *   lo guarda en la carpeta de reportes (reemplazando uno anterior con el mismo nombre)
 *   y devuelve el link.
 * accion=foto: guarda una foto (JPEG en base64) en la carpeta de fotos (o en una subcarpeta,
 *   p. ej. "Repuestos", que se crea sola) y devuelve su id.
 * accion=borrar_foto: manda una foto a la papelera.
 * accion=copiar_fotos: trae las fotos viejas de AppSheet. Recibe la carpeta de origen
 *   (origen_id con el id, o origen con el nombre) y los nombres de archivo separados
 *   por "|"; copia a la carpeta de fotos de Ferro los que falten y devuelve el id de cada uno.
 * accion=ver_carpetas: lista las carpetas que se llaman como dice nombre, con su id, dónde
 *   están y cuántos archivos tienen. Sirve cuando hay más de una con el mismo nombre.
 * accion=guardar_backup: guarda la copia diaria de la base en la carpeta de backups y
 *   manda a la papelera las de más de DIAS_BACKUP días. La manda Ferro solo, una vez por
 *   día: en PythonAnywhere gratis no hay tareas programadas.
 *
 * Instalación (una sola vez), en el MISMO proyecto de Apps Script donde está el backup diario:
 *  1. Archivo → "+" → Script → pegar este código y completar SECRETO.
 *     Ojo: que ningún otro archivo del proyecto declare las mismas constantes.
 *  2. Implementar → Nueva implementación → tipo "Aplicación web":
 *       Ejecutar como: Yo    ·    Quién tiene acceso: Cualquier usuario
 *  3. Autorizar y copiar la URL de la aplicación web (termina en /exec).
 *
 * Para actualizar este código sin cambiar la URL:
 *  Implementar → Administrar implementaciones → lápiz → Versión: "Nueva versión" → Implementar.
 */
// El mismo valor que BACKUP_SECRET en el .env del servidor.
// Si en el proyecto hay OTRO archivo que ya declara SECRETO, borrá esta línea:
// no se puede declarar dos veces (es lo que rompió el script el 19/09).
const SECRETO = 'PEGAR_ACA_EL_BACKUP_SECRET';
const FOLDER_REPORTES_ID = '1o1ZkDqFamPa13Vmgzq5Um2FFYla84GIq';
const FOLDER_PRESUPUESTOS_ID = '1lBvBQ6mPestQoBhgmEPnE25x-JgWUAtb';
const FOLDER_CIRCULARES_ID = '1zZTFHxFu898i_EHbxE7cJjhreTLuc8Zp';
const FOLDER_LOGO_ID = '1hKdsArmHtOGlBSA_ZQ_LCeRv4UKKfyC3';
const NOMBRE_LOGO = 'SOBRIO FONDO BLANCO.jpeg';
const NOMBRE_FIRMA = 'FIRMA.jpg';
const FOLDER_FOTOS_ID = '1XbCu2_FdiR08_mzfzhPcsNifW2Cr1qjf';
const FOLDER_BACKUPS_ID = '1Mimm6jGOAwV0iV_nCtq7wnC_k5aohcSq';
const DIAS_BACKUP = 60;  // las copias más viejas que esto se van a la papelera

function doPost(e) {
  try {
    const p = e.parameter;
    if (!p.secreto || p.secreto !== SECRETO) return json({ ok: false, error: 'secreto incorrecto' });
    const accion = p.accion || 'reporte';
    if (accion === 'reporte') return generarReporte(p);
    if (accion === 'foto') return guardarFoto(p);
    if (accion === 'borrar_foto') return borrarFoto(p);
    if (accion === 'copiar_fotos') return copiarFotos(p);
    if (accion === 'ver_carpetas') return verCarpetas(p);
    if (accion === 'guardar_backup') return guardarBackup(p);
    return json({ ok: false, error: 'acción desconocida: ' + accion });
  } catch (err) {
    return json({ ok: false, error: String(err.message || err) });
  }
}

function generarReporte(p) {
  if (!p.html || !p.nombre) return json({ ok: false, error: 'faltan datos' });
  let html = p.html
    .split('__LOGO__').join(imagenBase64(FOLDER_LOGO_ID, NOMBRE_LOGO) || '')
    .split('__FIRMA__').join(imagenBase64(FOLDER_LOGO_ID, NOMBRE_FIRMA) || '');
  html = html.replace(/__FOTO:(.+?)__/g, function (_, archivo) {
    return imagenBase64(FOLDER_FOTOS_ID, archivo) || '';
  });

  const CARPETAS = { presupuestos: FOLDER_PRESUPUESTOS_ID, circulares: FOLDER_CIRCULARES_ID };
  const carpeta = DriveApp.getFolderById(
    p.carpeta_id || CARPETAS[p.carpeta] || FOLDER_REPORTES_ID);
  const anteriores = carpeta.getFilesByName(p.nombre);
  while (anteriores.hasNext()) anteriores.next().setTrashed(true);

  const pdf = Utilities.newBlob(html, MimeType.HTML, 'temp.html').getAs(MimeType.PDF).setName(p.nombre);
  const archivo = carpeta.createFile(pdf);
  return json({ ok: true, url: archivo.getUrl() });
}

function guardarFoto(p) {
  if (!p.nombre || !p.contenido) return json({ ok: false, error: 'faltan datos' });
  const blob = Utilities.newBlob(Utilities.base64Decode(p.contenido), 'image/jpeg', p.nombre);
  let carpeta = DriveApp.getFolderById(FOLDER_FOTOS_ID);
  if (p.subcarpeta) {
    const existentes = carpeta.getFoldersByName(p.subcarpeta);
    carpeta = existentes.hasNext() ? existentes.next() : carpeta.createFolder(p.subcarpeta);
  }
  const archivo = carpeta.createFile(blob);
  try {
    // Para poder ver la miniatura desde Ferro (el link no es público ni se puede adivinar)
    archivo.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
  } catch (e) { /* si la cuenta no lo permite, la foto igual queda guardada */ }
  return json({ ok: true, id: archivo.getId(), nombre: archivo.getName() });
}

function borrarFoto(p) {
  if (!p.id) return json({ ok: false, error: 'falta el id' });
  DriveApp.getFileById(p.id).setTrashed(true);
  return json({ ok: true });
}

function guardarBackup(p) {
  if (!p.nombre || !p.contenido) return json({ ok: false, error: 'faltan datos' });
  const carpeta = DriveApp.getFolderById(FOLDER_BACKUPS_ID);

  const iguales = carpeta.getFilesByName(p.nombre);   // si ya hay una de hoy, se reemplaza
  while (iguales.hasNext()) iguales.next().setTrashed(true);
  const blob = Utilities.newBlob(Utilities.base64Decode(p.contenido), 'application/gzip', p.nombre);
  const archivo = carpeta.createFile(blob);

  const limite = new Date(Date.now() - DIAS_BACKUP * 24 * 60 * 60 * 1000);
  let borradas = 0;
  const viejas = carpeta.getFiles();
  while (viejas.hasNext()) {
    const f = viejas.next();
    if (f.getName().indexOf('ferro-backup-') === 0 && f.getDateCreated() < limite) {
      f.setTrashed(true);
      borradas++;
    }
  }
  return json({ ok: true, id: archivo.getId(), nombre: archivo.getName(), borradas: borradas });
}

function verCarpetas(p) {
  if (!p.nombre) return json({ ok: false, error: 'falta el nombre' });
  const carpetas = [];
  const encontradas = DriveApp.getFoldersByName(p.nombre);
  while (encontradas.hasNext() && carpetas.length < 20) {
    const c = encontradas.next();
    let archivos = 0;
    const it = c.getFiles();
    while (it.hasNext() && archivos < 5000) { it.next(); archivos++; }
    const padres = c.getParents();
    carpetas.push({
      id: c.getId(), archivos: archivos, papelera: c.isTrashed(),
      dentro_de: padres.hasNext() ? padres.next().getName() : 'Mi unidad',
    });
  }
  return json({ ok: true, carpetas: carpetas });
}

function copiarFotos(p) {
  if (!p.nombres || (!p.origen && !p.origen_id)) {
    return json({ ok: false, error: 'faltan la carpeta de origen o los nombres' });
  }

  let origen;
  if (p.origen_id) {
    origen = DriveApp.getFolderById(p.origen_id);
  } else {
    const encontradas = DriveApp.getFoldersByName(p.origen);
    if (!encontradas.hasNext()) return json({ ok: false, error: 'no encontré la carpeta ' + p.origen });
    origen = encontradas.next();
    if (encontradas.hasNext()) {
      return json({ ok: false, error: 'hay más de una carpeta llamada ' + p.origen +
                                      ': mandá origen_id (accion=ver_carpetas las lista)' });
    }
  }

  const destino = DriveApp.getFolderById(FOLDER_FOTOS_ID);
  const resultado = {};
  p.nombres.split('|').forEach(function (nombre) {
    if (!nombre) return;
    const yaEstan = destino.getFilesByName(nombre);   // si ya se copió, no se copia de nuevo
    if (yaEstan.hasNext()) { resultado[nombre] = yaEstan.next().getId(); return; }
    const originales = origen.getFilesByName(nombre);
    if (!originales.hasNext()) { resultado[nombre] = null; return; }
    const copia = originales.next().makeCopy(nombre, destino);
    try {
      copia.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
    } catch (e) { /* si la cuenta no lo permite, la foto igual queda copiada */ }
    resultado[nombre] = copia.getId();
  });
  return json({ ok: true, fotos: resultado });
}

function imagenBase64(folderId, nombre) {
  try {
    const archivos = DriveApp.getFolderById(folderId).getFilesByName(nombre);
    if (!archivos.hasNext()) return null;
    const f = archivos.next();
    return 'data:' + f.getMimeType() + ';base64,' + Utilities.base64Encode(f.getBlob().getBytes());
  } catch (e) {
    return null;
  }
}

function json(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
