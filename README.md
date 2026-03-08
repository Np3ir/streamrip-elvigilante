# Streamrip — ElVigilante Edition

> Fork de [nathom/streamrip](https://github.com/nathom/streamrip) con mayor fiabilidad, seguridad mejorada y opciones de configuración extendidas.

Descargador de música y video potente y scriptable para **Qobuz**, **Tidal**, **Deezer** y **SoundCloud**, con salida en color estilo TiDDL.

---

## Índice

- [Novedades de este fork](#novedades-de-este-fork)
- [Características](#características)
- [Instalación](#instalación)
- [Inicio rápido](#inicio-rápido)
- [Comandos](#comandos)
- [Configuración](#configuración)
- [Separador de artistas](#separador-de-artistas)
- [Plantillas de rutas](#plantillas-de-rutas)
- [Autenticación por fuente](#autenticación-por-fuente)
- [Pruebas](#pruebas)
- [Documentación adicional](#documentación-adicional)
- [Aviso legal](#aviso-legal)
- [Créditos](#créditos)

---

## Novedades de este fork

| Mejora | Descripción |
|--------|-------------|
| **Credenciales Tidal por variables de entorno** | Usa `TIDAL_CLIENT_ID` / `TIDAL_CLIENT_SECRET` en vez de hardcodear |
| **Reintentos configurables** | `max_retries`, `retry_delay` y `max_wait` en `config.toml` |
| **Backoff exponencial** | Los reintentos esperan 2 s → 4 s → 8 s … hasta `max_wait` |
| **Separador de artistas configurable** | Elige `", "`, `" & "`, `" / "` etc. para nombres de archivos y tags |
| **Postprocess seguro** | Si el archivo no existe tras los reintentos, salta el postprocess en vez de fallar |
| **Carpeta de playlist corregida** | `set_playlist_to_album = true` ya no duplica el nombre de la carpeta |
| **Excepciones propias** | Los `assert` se reemplazaron por `ValueError` / `KeyError` |
| **Aviso de semáforo** | Configuración de concurrencia conflictiva loguea warning en vez de romper |
| **Suite de tests** | 69 tests unitarios: config, database, rutas, semáforo y reintentos |
| **Código revisado** | Múltiples rondas de revisión con Sourcery AI |

---

## Características

- **Audio de alta calidad** — FLAC hasta 24-bit/192 kHz, AAC, MP3
- **Soporte de video** — Videos de Tidal (MP4/HLS) con metadatos completos
- **Metadatos automáticos** — Tags completos, carátula, letras y créditos embebidos
- **Playlist / Artista** — Descarga playlists, álbumes completos y discografías
- **Descargas concurrentes** — Motor async con rate limiting inteligente
- **Salida TiDDL** — Verde = éxito, amarillo = saltado, rojo = error
- **Base de datos local** — Evita re-descargar tracks ya descargados
- **Last.fm** — Descarga playlists de Last.fm buscando en Qobuz/Tidal/Deezer

---

## Instalación

### Desde GitHub (recomendado)

```bash
pip install git+https://github.com/Np3ir/streamrip-elvigilante
```

### Para desarrollo

```bash
git clone https://github.com/Np3ir/streamrip-elvigilante
cd streamrip-elvigilante
pip install -e ".[dev]"
```

### Requisitos

| Requisito | Versión mínima | Notas |
|-----------|---------------|-------|
| Python | 3.10 | 3.11+ recomendado |
| FFmpeg | cualquiera | Solo necesario si usas conversión de audio |

**Instalar FFmpeg:**

- **Windows:** `winget install ffmpeg` o descarga desde [ffmpeg.org](https://ffmpeg.org/download.html)
- **macOS:** `brew install ffmpeg`
- **Linux:** `sudo apt install ffmpeg` / `sudo dnf install ffmpeg`

---

## Inicio rápido

```bash
# 1. Abrir el config para editarlo
rip config open

# 2. Descargar por URL (álbum, track, artista o playlist)
rip url "https://tidal.com/browse/album/12345678"
rip url "https://open.qobuz.com/album/0060254728697"
rip url "https://www.deezer.com/album/123456"
rip url "https://soundcloud.com/artist/track-name"

# 3. Buscar interactivamente
rip search qobuz album "Rumours"
rip search tidal track "Bohemian Rhapsody"

# 4. Descargar varias URLs de un archivo de texto
rip file urls.txt

# 5. Ver la base de datos de descargas
rip database browse downloads
```

---

## Comandos

### Opciones globales (aplican a todos los comandos)

```
rip [OPCIONES] COMANDO [ARGS]

Opciones:
  --config-path PATH    Ruta al archivo de configuración
  -f, --folder PATH     Carpeta de descarga (sobreescribe config.toml)
  -ndb, --no-db         Ignorar la base de datos (re-descarga todo)
  -q, --quality 0-4     Calidad máxima permitida
  -c, --codec CODEC     Convertir a: ALAC, FLAC, MP3, AAC, OGG
  --no-progress         No mostrar barras de progreso
  --no-ssl-verify       Desactivar verificación SSL
  -v, --verbose         Modo debug (muestra logs detallados)
  --version             Mostrar versión
```

---

### `rip url`

Descarga contenido desde una o más URLs.

```bash
rip url URL [URL ...]
```

**Ejemplos:**

```bash
# Un álbum
rip url "https://tidal.com/browse/album/12345678"

# Múltiples URLs a la vez
rip url "https://tidal.com/browse/album/12345678" \
        "https://open.qobuz.com/album/abc123"

# Con calidad máxima forzada
rip -q 2 url "https://www.deezer.com/album/456789"

# Convertir a MP3 tras descargar
rip -c MP3 url "https://tidal.com/browse/track/99999"

# Descargar a una carpeta específica
rip -f /tmp/musica url "https://soundcloud.com/artist/track"
```

**Tipos de URL soportados:**

| Fuente | Tipos |
|--------|-------|
| Qobuz | álbum, track, artista, playlist |
| Tidal | álbum, track, artista, playlist, video |
| Deezer | álbum, track, artista, playlist |
| SoundCloud | track, playlist |

---

### `rip file`

Descarga contenido desde URLs en un archivo de texto o JSON.

```bash
rip file RUTA_ARCHIVO
```

**Formato texto** (`urls.txt`):

```
https://tidal.com/browse/album/12345678
https://open.qobuz.com/album/0060254728697
https://www.deezer.com/album/123456
```

**Formato JSON** (`items.json`):

```json
[
  {"source": "tidal",  "media_type": "album", "id": "12345678"},
  {"source": "qobuz",  "media_type": "track", "id": "abc123"},
  {"source": "deezer", "media_type": "album", "id": "456789"}
]
```

```bash
# Texto (una URL por línea)
rip file urls.txt

# JSON con IDs directos
rip file items.json
```

> Las URLs duplicadas en el archivo de texto se eliminan automáticamente.

---

### `rip search`

Búsqueda interactiva con menú.

```bash
rip search [OPCIONES] FUENTE TIPO CONSULTA
```

| Parámetro | Valores posibles |
|-----------|-----------------|
| FUENTE | `qobuz` · `tidal` · `deezer` · `soundcloud` |
| TIPO | `track` · `album` · `artist` · `playlist` |

**Opciones:**

```
-f, --first              Descargar el primer resultado sin mostrar menú
-o, --output-file PATH   Guardar resultados en JSON en vez de mostrar menú
-n, --num-results N      Máximo de resultados (por defecto: 100)
```

**Ejemplos:**

```bash
# Búsqueda interactiva
rip search qobuz album "Rumours"
rip search tidal track "Bohemian Rhapsody"
rip search deezer artist "Radiohead"

# Descargar el primer resultado directamente
rip search -f qobuz album "Dark Side of the Moon"

# Guardar resultados en JSON para procesarlos después
rip search -o resultados.json qobuz album "Daft Punk"
```

---

### `rip id`

Descarga por ID interno de la fuente.

```bash
rip id FUENTE TIPO ID
```

```bash
rip id qobuz  album  "0060254728697"
rip id tidal  track  "12345678"
rip id deezer album  "456789"
```

---

### `rip lastfm`

Descarga los tracks de una playlist de Last.fm buscándolos en Qobuz/Tidal/Deezer.

```bash
rip lastfm [OPCIONES] URL
```

**Opciones:**

```
-s,  --source          Fuente principal (por defecto: valor en config.toml)
-fs, --fallback-source Fuente alternativa si no hay resultados
```

**Ejemplos:**

```bash
# Fuente configurada en config.toml
rip lastfm "https://www.last.fm/user/usuario/playlists/12345"

# Forzar búsqueda en Tidal con fallback a Deezer
rip lastfm -s tidal -fs deezer "https://www.last.fm/user/usuario/playlists/12345"
```

---

### `rip config`

Gestiona el archivo de configuración.

```bash
# Abrir en el editor predeterminado del sistema
rip config open

# Abrir en Vim / Neovim
rip config open --vim

# Mostrar la ruta del archivo de configuración
rip config path

# Resetear a los valores por defecto
rip config reset

# Resetear sin confirmación
rip config reset --yes
```

---

### `rip database`

Consulta las bases de datos de descargas.

```bash
# Ver tracks descargados
rip database browse downloads

# Ver descargas fallidas
rip database browse failed
```

---

## Configuración

El archivo `config.toml` se crea automáticamente la primera vez que ejecutas `rip`.
Usa `rip config path` para saber su ubicación y `rip config open` para editarlo.

### Ubicación por plataforma

| Sistema | Ruta |
|---------|------|
| Windows | `%APPDATA%\streamrip\config.toml` |
| macOS | `~/Library/Application Support/streamrip/config.toml` |
| Linux | `~/.config/streamrip/config.toml` |

### Sección `[downloads]`

```toml
[downloads]
folder              = "~/Music"   # carpeta de descarga
source_subdirectories = false     # subcarpeta por fuente (Qobuz/, Tidal/, …)
disc_subdirectories   = true      # subcarpetas Disc 1/, Disc 2/ en álbumes con varios discos
concurrency           = true      # descargas paralelas
max_connections       = 6         # conexiones simultáneas (-1 = sin límite)
requests_per_minute   = 60        # llamadas API por minuto (-1 = sin límite)
verify_ssl            = true      # verificar certificados SSL
max_retries           = 3         # reintentos antes de abandonar (0 = sin reintentos)
retry_delay           = 2.0       # segundos de espera inicial (se dobla en cada intento)
max_wait              = 60.0      # espera máxima entre reintentos en segundos
```

### Sección `[qobuz]`

```toml
[qobuz]
quality          = 3      # 1=MP3 320 | 2=FLAC 16/44.1 | 3=FLAC 24/≤96 | 4=FLAC 24/≥96
download_booklets = true  # descargar PDFs incluidos con algunos álbumes
use_auth_token   = false  # true = usar token, false = usar email+contraseña
email_or_userid  = ""
password_or_token = ""    # hash MD5 de la contraseña si use_auth_token=false
```

### Sección `[tidal]`

```toml
[tidal]
quality         = 3     # 0=AAC 256 | 1=AAC 320 | 2=FLAC 16/44.1 | 3=FLAC 24/44.1 MQA
download_videos = true  # descargar álbumes de video
# Los campos siguientes se rellenan automáticamente al autenticarte
user_id       = ""
country_code  = ""
access_token  = ""
refresh_token = ""
token_expiry  = ""
```

### Sección `[deezer]`

```toml
[deezer]
quality             = 2     # 0=MP3 128 | 1=MP3 320 | 2=FLAC
arl                 = ""    # cookie ARL de tu cuenta Deezer
use_deezloader      = true  # habilitar descargas gratuitas a 320kbps
deezloader_warnings = true  # avisar cuando no hay cuenta activa
```

> Para obtener el ARL: abre Deezer en el navegador → Herramientas de desarrollador → Aplicación → Cookies → busca `arl`.

### Sección `[soundcloud]`

```toml
[soundcloud]
quality     = 0   # único valor disponible
client_id   = ""  # se actualiza periódicamente
app_version = ""
```

### Sección `[conversion]`

```toml
[conversion]
enabled       = false   # activar conversión automática tras la descarga
codec         = "ALAC"  # FLAC | ALAC | MP3 | AAC | OGG | OPUS
sampling_rate = 48000   # Hz (el track se downsamplea si supera este valor)
bit_depth     = 24      # solo 16 y 24 disponibles
lossy_bitrate = 320     # kbps (solo para codecs con pérdida)
```

### Sección `[artwork]`

```toml
[artwork]
embed          = true      # embeber carátula en el archivo de audio
embed_size     = "large"   # thumbnail | small | large | original
embed_max_width = -1       # px máximo de la carátula embebida (-1 = sin límite)
save_artwork   = true      # guardar carátula como archivo JPG separado
saved_max_width = -1       # px máximo de la carátula guardada (-1 = sin límite)
```

### Sección `[metadata]`

```toml
[metadata]
set_playlist_to_album    = true   # usar nombre de playlist como campo ALBUM
renumber_playlist_tracks = true   # usar posición en playlist como número de track
exclude                  = []     # lista de tags a excluir (p.ej. ["lyrics", "isrc"])
artist_separator         = ", "   # separador entre artistas: ", " | " & " | " / " | "; "
```

### Sección `[filepaths]`

```toml
[filepaths]
add_singles_to_folder = false   # crear carpeta incluso para un único track
folder_format = "{albumartist} - {title} ({year}) [{container}] [{bit_depth}B-{sampling_rate}kHz]"
track_format  = "{tracknumber:02}. {artist} - {title}{explicit}"
restrict_characters = false     # solo ASCII imprimible en nombres de archivo
truncate_to         = 120       # longitud máxima del nombre de archivo
```

### Sección `[qobuz_filters]` (Discografías)

```toml
[qobuz_filters]
extras          = false   # excluir ediciones de coleccionista, grabaciones en vivo, etc.
repeats         = false   # solo la versión de mayor calidad cuando hay títulos duplicados
non_albums      = false   # excluir EPs y singles
features        = false   # excluir álbumes donde el artista es colaborador
non_studio_albums = false # excluir álbumes en vivo
non_remaster    = false   # solo álbumes remasterizados
```

### Sección `[lastfm]`

```toml
[lastfm]
source          = "qobuz"   # fuente principal para buscar tracks de Last.fm
fallback_source = ""        # fuente alternativa (deezer, tidal, etc.)
```

### Sección `[cli]`

```toml
[cli]
text_output      = true   # mostrar mensajes de estado
progress_bars    = true   # mostrar barras de progreso
max_search_results = 100  # resultados máximos en el menú interactivo
```

---

## Separador de artistas

Cuando un track tiene varios artistas, puedes controlar cómo se unen tanto en el nombre del archivo como en el tag `ARTIST` / `ALBUMARTIST` embebido:

```toml
[metadata]
artist_separator = " & "   # p.ej.: "Calvin Harris & Dua Lipa"
```

| Valor | Resultado |
|-------|-----------|
| `", "` (por defecto) | `Calvin Harris, Dua Lipa` |
| `" & "` | `Calvin Harris & Dua Lipa` |
| `" / "` | `Calvin Harris / Dua Lipa` |
| `"; "` | `Calvin Harris; Dua Lipa` |

---

## Plantillas de rutas

### Variables para `folder_format`

| Variable | Descripción | Ejemplo |
|----------|-------------|---------|
| `{albumartist}` | Artista del álbum | `Daft Punk` |
| `{title}` | Título del álbum | `Random Access Memories` |
| `{year}` | Año de lanzamiento | `2013` |
| `{container}` | Formato del archivo | `FLAC` |
| `{bit_depth}` | Profundidad de bits | `24` |
| `{sampling_rate}` | Frecuencia de muestreo en kHz | `44.1` |
| `{id}` | ID interno de la fuente | `0060254728697` |
| `{albumcomposer}` | Compositor del álbum | `Thomas Bangalter` |
| `{artist_initials}` | Primera letra del artista | `D` |
| `{release_date}` | Fecha completa de lanzamiento | `2013-05-17` |

### Variables para `track_format`

| Variable | Descripción | Ejemplo |
|----------|-------------|---------|
| `{tracknumber}` | Número de track | `1` ó `{tracknumber:02}` → `01` |
| `{artist}` | Artista(s) del track | `Daft Punk` |
| `{albumartist}` | Artista del álbum | `Daft Punk` |
| `{title}` | Título del track | `Get Lucky` |
| `{composer}` | Compositor | `Thomas Bangalter` |
| `{albumcomposer}` | Compositor del álbum | `Thomas Bangalter` |
| `{explicit}` | `(explicit)` o vacío | `(explicit)` |

### Ejemplos de configuración

```toml
# Organización simple por artista/álbum
folder_format = "{albumartist}/{title} ({year})"
track_format  = "{tracknumber:02}. {title}"

# Con calidad en el nombre de carpeta
folder_format = "{albumartist} - {title} ({year}) [{container}]"
track_format  = "{tracknumber:02}. {artist} - {title}"

# Organización por inicial (A/, B/, C/, …)
folder_format = "{artist_initials}/{albumartist}/{title} ({year})"
track_format  = "{tracknumber:02}. {title}{explicit}"
```

---

## Autenticación por fuente

### Qobuz

1. Ejecuta `rip config open`
2. Rellena `email_or_userid` y `password_or_token` (MD5 del password)
3. O usa `use_auth_token = true` y pon tu token en `password_or_token`

### Tidal

Las credenciales se auto-rellenan al autenticarte. También puedes usar variables de entorno:

```bash
export TIDAL_CLIENT_ID="tu_client_id"
export TIDAL_CLIENT_SECRET="tu_client_secret"
```

Los tokens expiran aproximadamente cada semana. Si ves errores de autenticación, puede que necesites renovar el token.

### Deezer

1. Abre [deezer.com](https://deezer.com) en tu navegador
2. Abre las Herramientas de desarrollador (F12)
3. Ve a **Aplicación → Cookies → deezer.com**
4. Copia el valor de la cookie `arl`
5. Pégalo en `config.toml`:

```toml
[deezer]
arl = "TU_COOKIE_ARL_AQUÍ"
```

### SoundCloud

SoundCloud no requiere cuenta para descargar. El `client_id` y `app_version` se obtienen automáticamente o puedes extraerlos manualmente del código fuente de la web si caducan.

---

## Pruebas

```bash
pip install -e ".[dev]"
pytest              # todos los tests
pytest -v           # verbose
pytest tests/test_config.py  # un módulo específico
```

**Módulos de test:**

| Archivo | Qué prueba |
|---------|-----------|
| `test_config.py` | Carga, validación y actualización del config |
| `test_db.py` | Base de datos de descargas y fallidas |
| `test_filepath_utils.py` | Limpieza y truncado de rutas |
| `test_semaphore_behavior.py` | Semáforo de concurrencia |
| `test_track_retry_behavior.py` | Lógica de reintentos y backoff exponencial |

---

## Documentación adicional

| Documento | Contenido |
|-----------|-----------|
| [`docs/COMMANDS.md`](docs/COMMANDS.md) | Referencia completa de todos los comandos |
| [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) | Referencia completa de todas las opciones de configuración |
| [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) | Solución de problemas comunes |
| [`CHANGELOG.md`](CHANGELOG.md) | Historial de cambios |

---

## Aviso legal

Este software es solo para **uso educativo y privado**.
Los usuarios son responsables de cumplir con los términos de uso de cada servicio.
Por favor, apoya a los artistas comprando su música.

---

## Créditos

- Proyecto original: [nathom/streamrip](https://github.com/nathom/streamrip) — GPL-3.0
- Este fork: ElVigilante — GPL-3.0
