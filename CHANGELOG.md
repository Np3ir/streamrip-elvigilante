# Changelog

Todos los cambios notables en **Streamrip — ElVigilante Edition** se documentan aquí.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/es/1.1.0/).

---

## [2.2.0] — ElVigilante Edition

### Añadido

- **`artist_separator` configurable** (`[metadata]` en config.toml)
  — Permite elegir cómo se unen varios artistas en nombres de archivo y tags de audio
  (`", "`, `" & "`, `" / "`, `"; "`, etc.). Afecta tanto al tag `ARTIST`/`ALBUMARTIST`
  embebido como al nombre del archivo generado. Se aplica en Qobuz, Tidal y Deezer.
  El valor por defecto es `", "` — sin cambio de comportamiento para configs existentes.

- **`_resolve_track_folder()` acepta `str | os.PathLike[str]`** (`media/playlist.py`)
  — La función auxiliar que calcula la carpeta de cada track en una playlist ahora
  acepta rutas de tipo `pathlib.Path` además de `str`, usando `os.fspath()` internamente.

- **Warning de `rip()` mejorado** (`media/track.py`)
  — Cuando un track no se descarga tras agotar los reintentos, el mensaje de log incluye
  ahora el ID del track (`id=…`) y el número de reintentos configurado (`after N retries`)
  para facilitar la depuración.

- **`max_retries` normalizado a `int`** (`config.py`)
  — Si `max_retries` viene como string en el TOML (p.ej. `"3"`), se convierte a entero
  automáticamente. Valores negativos se resetean a 0 con un warning.

- **Renombrado de `test_semaphore.py` a `test_semaphore_behavior.py`** y conversión a
  `@pytest.mark.asyncio` — Tests asíncronos nativos sin `asyncio.run()`.

- **`source` y `extension` en `_FailingDownloadable`** (`test_track_retry_behavior.py`)
  — Atributos necesarios para que el path de `set_failed` nunca lance `AttributeError`
  al agotar los reintentos.

- **Lógica de postprocess protegida** (`media/track.py`)
  — Si el archivo no existe en disco tras la descarga (todos los reintentos agotados),
  `rip()` ahora registra un warning descriptivo y retorna en vez de fallar en
  `postprocess()`.

- **`_resolve_track_folder()` extraído** (`media/playlist.py`)
  — La lógica de resolución de carpeta para tracks de playlist se movió a una función
  auxiliar privada, eliminando código duplicado.

- **Backoff exponencial completo** (`client/downloadable.py`)
  — Los reintentos esperan `retry_delay * 2^intento` segundos, con un techo de
  `max_wait` segundos. DNS failures y errores de red se reintentan correctamente.

- **Credenciales Tidal por variables de entorno**
  — `TIDAL_CLIENT_ID` y `TIDAL_CLIENT_SECRET` se pueden exportar en vez de guardarlas
  en `config.toml`.

- **Suite de tests** (69 tests en 5 módulos)
  — `test_config.py`, `test_db.py`, `test_filepath_utils.py`,
  `test_semaphore_behavior.py`, `test_track_retry_behavior.py`.

- **Salida de color estilo TiDDL**
  — Verde para descargas correctas, amarillo para saltadas, rojo para errores.

### Corregido

- **Carpeta duplicada en playlists** con `set_playlist_to_album = true`
  — El nombre del álbum/playlist ya no se añade como subcarpeta cuando
  `set_playlist_to_album` está activado (se usaba como nombre de carpeta raíz y
  también como subcarpeta, duplicándolo).

- **AlbumMetadata `repr` en nombres de carpeta** (`media/playlist.py`)
  — Las carpetas de álbum en playlists mostraban el `repr()` del objeto
  `AlbumMetadata` en lugar del título limpio del álbum.

- **Crash en `postprocess()` cuando falla la descarga**
  — Si todos los reintentos se agotan y el archivo no existe, el proceso continuaba
  hacia `postprocess()` y fallaba. Ahora se detecta y se salta con un warning.

- **`assert` reemplazados por excepciones propias**
  — Evita `AssertionError` inesperados en producción.

- **Semáforo con configuración conflictiva**
  — Configuración `concurrency=False` con `max_connections > 1` ya no rompe el
  programa; emite un warning descriptivo.

### Cambiado

- **Estructura de paquete plana** (`flat layout`)
  — Los módulos viven directamente en `site-packages/streamrip/` además del
  layout de repositorio estándar en `streamrip/streamrip/`.

- **`config.toml` versión `2.0.6`**
  — Añadidos `max_retries`, `retry_delay`, `max_wait` en `[downloads]` y
  `artist_separator` en `[metadata]`.

---

## [2.0.6] — nathom/streamrip (upstream base)

Base desde la que parte este fork. Ver el
[historial del proyecto original](https://github.com/nathom/streamrip/releases)
para el historial previo.

---

> Este fork mantiene compatibilidad total con el formato de `config.toml` de la versión
> upstream. Los valores nuevos tienen defaults que preservan el comportamiento original.
