# Referencia completa de configuración

Streamrip lee su configuración desde `config.toml`.
Usa `rip config path` para ver la ruta exacta y `rip config open` para editarlo.

---

## Ubicación del archivo

| Sistema | Ruta |
|---------|------|
| Windows | `%APPDATA%\streamrip\config.toml` |
| macOS | `~/Library/Application Support/streamrip/config.toml` |
| Linux | `~/.config/streamrip/config.toml` |

Si el archivo no existe, se crea automáticamente con valores por defecto la primera vez que ejecutas cualquier comando `rip`.

---

## `[downloads]`

Controla dónde y cómo se descargan los archivos.

| Clave | Tipo | Por defecto | Descripción |
|-------|------|-------------|-------------|
| `folder` | string | `""` | Carpeta de descarga. Vacío = directorio actual. Puedes usar `~` para el home. |
| `source_subdirectories` | bool | `false` | Crea una subcarpeta por fuente (`Qobuz/`, `Tidal/`, `Deezer/`, etc.) dentro de `folder`. |
| `disc_subdirectories` | bool | `true` | En álbumes con 2 o más discos, crea subcarpetas `Disc 1/`, `Disc 2/`, etc. |
| `concurrency` | bool | `true` | Descarga varios tracks en paralelo. Si conviertes audio, actívalo para mayor velocidad. |
| `max_connections` | int | `6` | Conexiones simultáneas. `-1` = sin límite. Valores altos pueden causar bloqueos o throttling. |
| `requests_per_minute` | int | `60` | Llamadas a la API por minuto. `-1` = sin límite. |
| `verify_ssl` | bool | `true` | Verificar certificados SSL. Solo desactiva si tienes errores de certificado. |
| `max_retries` | int | `3` | Intentos antes de marcar la descarga como fallida. `0` = sin reintentos. |
| `retry_delay` | float | `2.0` | Segundos de espera tras el primer fallo. Cada intento dobla el tiempo (backoff exponencial). |
| `max_wait` | float | `60.0` | Espera máxima en segundos entre reintentos. Limita el crecimiento del backoff. |

**Ejemplo:**

```toml
[downloads]
folder              = "D:/Música"
source_subdirectories = true
concurrency         = true
max_connections     = 4
max_retries         = 5
retry_delay         = 3.0
max_wait            = 120.0
```

---

## `[qobuz]`

| Clave | Tipo | Por defecto | Descripción |
|-------|------|-------------|-------------|
| `quality` | int | `3` | `1`=MP3 320kbps · `2`=FLAC 16/44.1 · `3`=FLAC 24/≤96kHz · `4`=FLAC 24/≥96kHz |
| `download_booklets` | bool | `true` | Descargar PDFs de libretos cuando están disponibles. |
| `use_auth_token` | bool | `false` | `true` para usar token de autenticación; `false` para email+contraseña. |
| `email_or_userid` | string | `""` | Email de la cuenta (o userid si `use_auth_token=true`). |
| `password_or_token` | string | `""` | Hash MD5 del password (o token si `use_auth_token=true`). |
| `app_id` | string | `""` | No cambiar. Se rellena automáticamente. |
| `secrets` | list | `[]` | No cambiar. Se rellenan automáticamente. |

**Cómo obtener el hash MD5 del password:**

```bash
python3 -c "import hashlib; print(hashlib.md5('TU_PASSWORD'.encode()).hexdigest())"
```

---

## `[tidal]`

| Clave | Tipo | Por defecto | Descripción |
|-------|------|-------------|-------------|
| `quality` | int | `3` | `0`=AAC 256kbps · `1`=AAC 320kbps · `2`=FLAC 16/44.1 ("HiFi") · `3`=FLAC 24/44.1 MQA |
| `download_videos` | bool | `true` | Descargar álbumes de video de Tidal. |
| `user_id` | string | `""` | Auto-rellenado al autenticarte. No cambiar. |
| `country_code` | string | `""` | Auto-rellenado al autenticarte. No cambiar. |
| `access_token` | string | `""` | Auto-rellenado. Caduca aproximadamente cada semana. |
| `refresh_token` | string | `""` | Auto-rellenado. Se usa para renovar el access token. |
| `token_expiry` | string | `""` | Timestamp Unix de caducidad del access token. |

**Variables de entorno alternativas:**

```bash
export TIDAL_CLIENT_ID="tu_client_id"
export TIDAL_CLIENT_SECRET="tu_client_secret"
```

---

## `[deezer]`

| Clave | Tipo | Por defecto | Descripción |
|-------|------|-------------|-------------|
| `quality` | int | `2` | `0`=MP3 128kbps · `1`=MP3 320kbps · `2`=FLAC lossless |
| `arl` | string | `""` | Cookie ARL de tu cuenta Deezer. Ver instrucciones abajo. |
| `use_deezloader` | bool | `true` | Habilitar descargas gratuitas a 320kbps si no hay cuenta. |
| `deezloader_warnings` | bool | `true` | Avisar cuando no hay cuenta Deezer activa y se usa deezloader. |

**Cómo obtener el ARL de Deezer:**

1. Abre [deezer.com](https://www.deezer.com) e inicia sesión
2. Abre las herramientas de desarrollador (`F12`)
3. Ve a **Aplicación → Almacenamiento → Cookies → deezer.com**
4. Busca la cookie llamada `arl` y copia su valor

---

## `[soundcloud]`

| Clave | Tipo | Por defecto | Descripción |
|-------|------|-------------|-------------|
| `quality` | int | `0` | Solo `0` disponible actualmente. |
| `client_id` | string | `""` | Client ID de SoundCloud. Cambia periódicamente. |
| `app_version` | string | `""` | Versión de la app de SoundCloud. |

---

## `[youtube]`

| Clave | Tipo | Por defecto | Descripción |
|-------|------|-------------|-------------|
| `quality` | int | `0` | Solo `0` disponible actualmente. |
| `download_videos` | bool | `false` | Descargar el video además del audio. |
| `video_downloads_folder` | string | `""` | Carpeta para los videos. Vacío = misma carpeta que el audio. |

---

## `[database]`

| Clave | Tipo | Por defecto | Descripción |
|-------|------|-------------|-------------|
| `downloads_enabled` | bool | `true` | Registrar tracks descargados. Los tracks ya en la BD se saltan. Usa `--no-db` para ignorarlo puntualmente. |
| `downloads_path` | string | `""` | Ruta a la BD de descargas. Vacío = ruta por defecto en el directorio de la app. |
| `failed_downloads_enabled` | bool | `true` | Registrar descargas fallidas para poder reintentarlas. |
| `failed_downloads_path` | string | `""` | Ruta a la BD de descargas fallidas. |

---

## `[conversion]`

Convierte los archivos descargados a otro formato después de la descarga.
Requiere **FFmpeg** instalado.

| Clave | Tipo | Por defecto | Descripción |
|-------|------|-------------|-------------|
| `enabled` | bool | `false` | Activar conversión automática. |
| `codec` | string | `"ALAC"` | Formato destino: `FLAC` · `ALAC` · `MP3` · `AAC` · `OGG` · `OPUS` |
| `sampling_rate` | int | `48000` | Hz. Los tracks con frecuencia mayor se downsamplearán. |
| `bit_depth` | int | `24` | Solo `16` o `24`. Los tracks con mayor profundidad se convertirán. |
| `lossy_bitrate` | int | `320` | kbps. Solo aplica a MP3, AAC, OGG, OPUS. |

**Ejemplo — convertir todo a MP3 320:**

```toml
[conversion]
enabled       = true
codec         = "MP3"
lossy_bitrate = 320
```

**Ejemplo — ALAC a 16-bit para compatibilidad:**

```toml
[conversion]
enabled       = true
codec         = "ALAC"
sampling_rate = 44100
bit_depth     = 16
```

---

## `[qobuz_filters]`

Filtros para descargar discografías de artistas en Qobuz.
Todos son `false` por defecto (sin filtrado).

| Clave | Tipo | Descripción |
|-------|------|-------------|
| `extras` | bool | Excluir ediciones de coleccionista, grabaciones en vivo, etc. |
| `repeats` | bool | Cuando hay álbumes con título idéntico, conservar solo el de mayor calidad. |
| `non_albums` | bool | Excluir EPs y singles. |
| `features` | bool | Excluir álbumes donde el artista buscado es solo colaborador. |
| `non_studio_albums` | bool | Excluir álbumes en vivo. |
| `non_remaster` | bool | Solo descargar versiones remasterizadas. |

---

## `[artwork]`

| Clave | Tipo | Por defecto | Descripción |
|-------|------|-------------|-------------|
| `embed` | bool | `true` | Embeber carátula en el archivo de audio. |
| `embed_size` | string | `"large"` | `thumbnail` (50px) · `small` (150px) · `large` (600px) · `original` (hasta 30 MB, puede fallar al embeber) |
| `embed_max_width` | int | `-1` | Redimensionar carátula embebida si supera este ancho en px. `-1` = sin límite. |
| `save_artwork` | bool | `true` | Guardar la carátula como `cover.jpg` en la carpeta del álbum. |
| `saved_max_width` | int | `-1` | Redimensionar carátula guardada. `-1` = sin límite. |

---

## `[metadata]`

| Clave | Tipo | Por defecto | Descripción |
|-------|------|-------------|-------------|
| `set_playlist_to_album` | bool | `true` | Usar el nombre de la playlist como valor del campo `ALBUM` en los tags. Útil para software que organiza por álbum. |
| `renumber_playlist_tracks` | bool | `true` | Usar la posición del track en la playlist como `TRACKNUMBER` en vez de su posición en el álbum original. |
| `exclude` | list | `[]` | Lista de nombres de tags a excluir. P.ej. `["lyrics", "isrc", "copyright"]`. Ver [wiki de tags](https://github.com/nathom/streamrip/wiki/Metadata-Tag-Names). |
| `artist_separator` | string | `", "` | Separador para unir múltiples artistas en tags y nombres de archivo. Ver [tabla de opciones](#opciones-de-artist_separator). |

### Opciones de `artist_separator`

| Valor | Ejemplo de resultado |
|-------|---------------------|
| `", "` (defecto) | `Calvin Harris, Dua Lipa` |
| `" & "` | `Calvin Harris & Dua Lipa` |
| `" / "` | `Calvin Harris / Dua Lipa` |
| `"; "` | `Calvin Harris; Dua Lipa` |
| `" x "` | `Calvin Harris x Dua Lipa` |

---

## `[filepaths]`

Controla los nombres de carpetas y archivos generados.

| Clave | Tipo | Por defecto | Descripción |
|-------|------|-------------|-------------|
| `add_singles_to_folder` | bool | `false` | Crear una carpeta para un single (track suelto) usando `folder_format`. |
| `folder_format` | string | ver abajo | Plantilla para el nombre de la carpeta del álbum. |
| `track_format` | string | ver abajo | Plantilla para el nombre del archivo del track (sin extensión). |
| `restrict_characters` | bool | `false` | Solo permitir caracteres ASCII imprimibles en nombres de archivo. |
| `truncate_to` | int | `120` | Longitud máxima del nombre de archivo. Valores menores evitan problemas en Windows. |

**Valores por defecto:**

```toml
folder_format = "{albumartist} - {title} ({year}) [{container}] [{bit_depth}B-{sampling_rate}kHz]"
track_format  = "{tracknumber:02}. {artist} - {title}{explicit}"
```

### Variables disponibles en `folder_format`

| Variable | Descripción | Ejemplo |
|----------|-------------|---------|
| `{albumartist}` | Artista del álbum | `Daft Punk` |
| `{title}` | Título del álbum | `Random Access Memories` |
| `{album}` | Alias de `{title}` | `Random Access Memories` |
| `{year}` | Año | `2013` |
| `{container}` | Formato de audio | `FLAC` |
| `{bit_depth}` | Profundidad de bits | `24` |
| `{sampling_rate}` | Frecuencia en kHz | `96.0` |
| `{id}` | ID de la fuente | `0060254728697` |
| `{albumcomposer}` | Compositor del álbum | `Thomas Bangalter` |
| `{artist_initials}` | Primera letra del artista (o `#` para no-latino) | `D` |
| `{release_date}` | Fecha completa | `2013-05-17` |

### Variables disponibles en `track_format`

| Variable | Descripción | Ejemplo |
|----------|-------------|---------|
| `{tracknumber}` | Número de track (formato: `{tracknumber:02}` para ceros) | `1` ó `01` |
| `{artist}` | Artista(s) del track | `Daft Punk feat. Pharrell Williams` |
| `{albumartist}` | Artista del álbum | `Daft Punk` |
| `{title}` | Título del track | `Get Lucky` |
| `{composer}` | Compositor | `Thomas Bangalter` |
| `{albumcomposer}` | Compositor del álbum | `Thomas Bangalter` |
| `{explicit}` | ` (explicit)` si es explícito, vacío si no | `(explicit)` |

### Ejemplos de plantillas

```toml
# Minimalista
folder_format = "{albumartist}/{title} ({year})"
track_format  = "{tracknumber:02}. {title}"

# Con formato de calidad
folder_format = "{albumartist} - {title} ({year}) [{container} {bit_depth}bit]"
track_format  = "{tracknumber:02}. {artist} - {title}"

# Organizado por inicial
folder_format = "{artist_initials}/{albumartist}/{title} ({year})"
track_format  = "{tracknumber:02}. {title}{explicit}"

# Solo álbum y track (máxima compatibilidad de rutas)
folder_format = "{albumartist} - {title}"
track_format  = "{tracknumber:02}. {title}"
```

---

## `[lastfm]`

| Clave | Tipo | Por defecto | Descripción |
|-------|------|-------------|-------------|
| `source` | string | `"qobuz"` | Fuente donde buscar los tracks de la playlist. |
| `fallback_source` | string | `""` | Fuente alternativa si no hay resultados en la principal. |

---

## `[cli]`

| Clave | Tipo | Por defecto | Descripción |
|-------|------|-------------|-------------|
| `text_output` | bool | `true` | Mostrar mensajes de estado en la terminal. |
| `progress_bars` | bool | `true` | Mostrar barras de progreso de descarga. |
| `max_search_results` | int | `100` | Número máximo de resultados en el menú interactivo de búsqueda. |

---

## `[misc]`

| Clave | Tipo | Por defecto | Descripción |
|-------|------|-------------|-------------|
| `version` | string | `"2.0.6"` | Versión del formato de config. **No cambiar.** |
| `check_for_updates` | bool | `true` | Mostrar un aviso si hay una nueva versión de streamrip disponible. |

---

## Anulación por línea de comandos

Algunas opciones del config se pueden sobreescribir puntualmente con flags:

| Flag | Equivalente en config |
|------|-----------------------|
| `-f CARPETA` | `downloads.folder` |
| `-q CALIDAD` | `*.quality` (todas las fuentes) |
| `-c CODEC` | `conversion.codec` + `conversion.enabled = true` |
| `-ndb` | `database.downloads_enabled = false` |
| `--no-progress` | `cli.progress_bars = false` |
| `--no-ssl-verify` | `downloads.verify_ssl = false` |

---

## Configuraciones de ejemplo completas

### Para uso general (calidad máxima)

```toml
[downloads]
folder = "~/Music"
concurrency = true
max_connections = 6
max_retries = 3

[qobuz]
quality = 4   # FLAC 24-bit máxima resolución

[tidal]
quality = 3   # FLAC 24-bit MQA

[deezer]
quality = 2   # FLAC

[metadata]
artist_separator = " & "
set_playlist_to_album = true

[filepaths]
folder_format = "{albumartist} - {title} ({year}) [{container}]"
track_format  = "{tracknumber:02}. {artist} - {title}"

[artwork]
embed = true
embed_size = "large"
save_artwork = true
```

### Para almacenamiento reducido (MP3)

```toml
[downloads]
folder = "~/Music/MP3"
concurrency = true

[qobuz]
quality = 1   # MP3 320kbps

[conversion]
enabled = false   # Qobuz ya entrega MP3

[filepaths]
folder_format = "{albumartist}/{title} ({year})"
track_format  = "{tracknumber:02}. {title}"
restrict_characters = true
truncate_to = 80

[artwork]
embed = true
embed_size = "small"
save_artwork = false
```

### Para playlists de Tidal

```toml
[downloads]
folder = "~/Music/Playlists"

[tidal]
quality = 3

[metadata]
set_playlist_to_album = true
renumber_playlist_tracks = true
artist_separator = " & "

[filepaths]
folder_format = "{title} ({year})"
track_format  = "{tracknumber:02}. {artist} - {title}"
```
