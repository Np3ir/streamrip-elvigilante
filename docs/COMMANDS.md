# Referencia de comandos

Streamrip se usa a través del comando `rip`. Todos los subcomandos y opciones están documentados aquí.

---

## Estructura general

```
rip [OPCIONES GLOBALES] COMANDO [ARGUMENTOS Y OPCIONES DEL COMANDO]
```

---

## Opciones globales

Estas opciones están disponibles en **todos** los comandos:

| Opción | Abreviación | Descripción |
|--------|-------------|-------------|
| `--config-path PATH` | — | Ruta a un archivo `config.toml` alternativo. |
| `--folder PATH` | `-f` | Carpeta de descarga (sobreescribe `downloads.folder` del config). |
| `--no-db` | `-ndb` | Ignorar la base de datos. Re-descarga aunque el track ya esté registrado. |
| `--quality 0-4` | `-q` | Calidad máxima (aplica a todas las fuentes simultáneamente). |
| `--codec CODEC` | `-c` | Convertir archivos descargados. Valores: `ALAC`, `FLAC`, `MP3`, `AAC`, `OGG`. Activa `conversion.enabled = true` temporalmente. |
| `--no-progress` | — | No mostrar barras de progreso. |
| `--no-ssl-verify` | — | Desactivar verificación de certificados SSL. Usar si hay errores de certificado. |
| `--verbose` | `-v` | Modo debug: muestra logs detallados y trazas de error completas. |
| `--version` | — | Muestra la versión de streamrip instalada. |
| `--help` | — | Muestra la ayuda del comando. |

---

## `rip url`

Descarga contenido directamente desde una o más URLs.

```bash
rip url URL [URL ...]
```

### Descripción

Acepta URLs de Qobuz, Tidal, Deezer y SoundCloud. El tipo de contenido
(track, álbum, artista, playlist) se detecta automáticamente desde la URL.

### Ejemplos

```bash
# Un álbum de Tidal
rip url "https://tidal.com/browse/album/12345678"

# Un track de Qobuz
rip url "https://open.qobuz.com/track/abc123"

# Un artista completo de Deezer (descarga toda su discografía)
rip url "https://www.deezer.com/artist/456"

# Una playlist de SoundCloud
rip url "https://soundcloud.com/usuario/sets/mi-playlist"

# Varias URLs en un solo comando
rip url "https://tidal.com/browse/album/111" \
        "https://open.qobuz.com/album/222" \
        "https://www.deezer.com/album/333"

# Con opciones globales: calidad 2, sin base de datos, a una carpeta específica
rip -q 2 -ndb -f /tmp/musica url "https://tidal.com/browse/album/12345678"

# Convertir a ALAC tras la descarga
rip -c ALAC url "https://open.qobuz.com/album/abc123"
```

### URLs soportadas

**Qobuz**

```
https://open.qobuz.com/track/{id}
https://open.qobuz.com/album/{id}
https://open.qobuz.com/artist/{id}
https://open.qobuz.com/playlist/{id}
https://www.qobuz.com/*/album/*/{id}
```

**Tidal**

```
https://tidal.com/browse/track/{id}
https://tidal.com/browse/album/{id}
https://tidal.com/browse/artist/{id}
https://tidal.com/browse/playlist/{uuid}
https://tidal.com/browse/video/{id}
https://listen.tidal.com/album/{id}
```

**Deezer**

```
https://www.deezer.com/track/{id}
https://www.deezer.com/album/{id}
https://www.deezer.com/artist/{id}
https://www.deezer.com/playlist/{id}
```

**SoundCloud**

```
https://soundcloud.com/{usuario}/{track-slug}
https://soundcloud.com/{usuario}/sets/{playlist-slug}
```

---

## `rip file`

Descarga contenido desde URLs o IDs en un archivo de texto o JSON.

```bash
rip file RUTA_ARCHIVO
```

### Formatos de archivo soportados

**Archivo de texto** (`.txt`) — una URL por línea:

```
https://tidal.com/browse/album/12345678
https://open.qobuz.com/album/abc123
https://www.deezer.com/album/456789
# Las líneas vacías y duplicadas se ignoran automáticamente
```

**Archivo JSON** (`.json`) — lista de objetos con `source`, `media_type` e `id`:

```json
[
  {"source": "qobuz",      "media_type": "album",    "id": "0060254728697"},
  {"source": "tidal",      "media_type": "track",    "id": "12345678"},
  {"source": "tidal",      "media_type": "playlist",  "id": "uuid-aqui"},
  {"source": "deezer",     "media_type": "artist",   "id": "456"},
  {"source": "soundcloud", "media_type": "track",    "id": "track-slug"}
]
```

Valores válidos para `media_type`: `track`, `album`, `artist`, `playlist`.

### Ejemplos

```bash
# Archivo de texto con URLs
rip file lista.txt

# Archivo JSON con IDs
rip file descargas.json

# Con opciones globales
rip -q 3 -f ~/MusicaHiRes file lista.txt
```

> Las URLs duplicadas en archivos de texto se eliminan automáticamente y se avisa cuántas había.

---

## `rip search`

Búsqueda interactiva o automática en una fuente específica.

```bash
rip search [OPCIONES] FUENTE TIPO CONSULTA
```

### Parámetros

| Parámetro | Valores | Descripción |
|-----------|---------|-------------|
| `FUENTE` | `qobuz` · `tidal` · `deezer` · `soundcloud` | Fuente donde buscar |
| `TIPO` | `track` · `album` · `artist` · `playlist` | Tipo de contenido |
| `CONSULTA` | texto libre | Términos de búsqueda |

### Opciones

| Opción | Abreviación | Descripción |
|--------|-------------|-------------|
| `--first` | `-f` | Descargar el primer resultado automáticamente sin mostrar menú. |
| `--output-file PATH` | `-o` | Guardar resultados en un archivo JSON en vez de mostrar el menú. Útil para procesamiento posterior. |
| `--num-results N` | `-n` | Número máximo de resultados (por defecto: 100). |

> `--first` y `--output-file` son mutuamente excluyentes.

### Ejemplos

```bash
# Búsqueda interactiva de álbum en Qobuz
rip search qobuz album "Rumours"

# Búsqueda de track en Tidal
rip search tidal track "Bohemian Rhapsody"

# Buscar artista en Deezer
rip search deezer artist "Radiohead"

# Descargar el primer resultado directamente
rip search --first qobuz album "Dark Side of the Moon"

# Guardar resultados en JSON para procesar después
rip search --output-file resultados.json qobuz album "Daft Punk"

# Limitar a 20 resultados
rip search -n 20 tidal album "Mozart"

# Con calidad forzada
rip -q 2 search qobuz album "Miles Davis"
```

### Menú interactivo

Al usar `rip search` sin `--first` ni `--output-file`, se muestra un menú con los
resultados. Navega con las flechas del teclado y pulsa **Enter** para seleccionar.
Puedes seleccionar múltiples resultados con **Espacio** si el modo lo permite.

---

## `rip id`

Descarga un elemento conociendo su ID interno en la fuente.

```bash
rip id FUENTE TIPO ID
```

### Parámetros

| Parámetro | Valores | Descripción |
|-----------|---------|-------------|
| `FUENTE` | `qobuz` · `tidal` · `deezer` · `soundcloud` | Fuente del elemento |
| `TIPO` | `track` · `album` · `artist` · `playlist` | Tipo de elemento |
| `ID` | string | ID del elemento en la fuente |

### Ejemplos

```bash
# Álbum de Qobuz por ID
rip id qobuz album "0060254728697"

# Track de Tidal por ID
rip id tidal track "12345678"

# Artista de Deezer
rip id deezer artist "456"

# Playlist de Tidal (el ID suele ser un UUID)
rip id tidal playlist "01234567-89ab-cdef-0123-456789abcdef"
```

> Los IDs se encuentran en las URLs de cada servicio.
> Por ejemplo, en `https://tidal.com/browse/album/12345678` el ID es `12345678`.

---

## `rip lastfm`

Descarga los tracks de una playlist pública de Last.fm buscándolos en Qobuz, Tidal o Deezer.

```bash
rip lastfm [OPCIONES] URL
```

### Descripción

Lee la lista de tracks de la URL de Last.fm y busca cada uno en la fuente configurada
(por defecto `qobuz`). Si no encuentra un track, lo busca en la fuente alternativa.

### Opciones

| Opción | Abreviación | Descripción |
|--------|-------------|-------------|
| `--source FUENTE` | `-s` | Fuente principal de búsqueda (sobreescribe `lastfm.source` del config). |
| `--fallback-source FUENTE` | `-fs` | Fuente alternativa si no hay resultados. |

### Ejemplos

```bash
# Con la fuente configurada en config.toml
rip lastfm "https://www.last.fm/user/usuario/playlists/12345"

# Buscar en Tidal, con Deezer como alternativa
rip lastfm -s tidal -fs deezer "https://www.last.fm/user/usuario/playlists/12345"

# Solo Qobuz, sin alternativa
rip lastfm -s qobuz "https://www.last.fm/user/usuario/playlists/12345"
```

> Las playlists de Last.fm deben ser **públicas** para que streamrip pueda acceder a ellas.

---

## `rip config`

Grupo de comandos para gestionar el archivo de configuración.

### `rip config open`

Abre `config.toml` en el editor predeterminado del sistema.

```bash
rip config open [--vim]
```

| Opción | Descripción |
|--------|-------------|
| `--vim` / `-v` | Abrir en Neovim (si está instalado) o Vim. |

```bash
# Editor predeterminado
rip config open

# Neovim / Vim
rip config open --vim
```

### `rip config path`

Muestra la ruta completa al archivo de configuración activo.

```bash
rip config path
```

Útil para saber dónde está el config en tu sistema, especialmente si usas `--config-path`.

### `rip config reset`

Resetea el archivo de configuración a los valores por defecto.

```bash
rip config reset [--yes]
```

| Opción | Descripción |
|--------|-------------|
| `--yes` / `-y` | Omitir la confirmación. |

> **¡Atención!** Esto sobreescribe tu config actual. Haz una copia de seguridad si tienes configuraciones personalizadas.

```bash
# Con confirmación interactiva
rip config reset

# Sin confirmación
rip config reset --yes
```

---

## `rip database`

Grupo de comandos para consultar las bases de datos.

### `rip database browse`

Muestra el contenido de una tabla de la base de datos en formato tabla.

```bash
rip database browse TABLA
```

| Tabla | Descripción |
|-------|-------------|
| `downloads` | Tracks descargados correctamente. |
| `failed` | Descargas que fallaron. |

```bash
# Ver tracks descargados
rip database browse downloads

# Ver descargas fallidas (fuente, tipo, ID)
rip database browse failed
```

---

## Ejemplos de flujos de trabajo

### Flujo básico: buscar y descargar

```bash
# 1. Buscar interactivamente
rip search qobuz album "Daft Punk"

# 2. O descargar directamente por URL
rip url "https://open.qobuz.com/album/0060254728697"
```

### Flujo de descarga masiva

```bash
# 1. Preparar un archivo con las URLs
cat > lista.txt << EOF
https://tidal.com/browse/album/111
https://tidal.com/browse/album/222
https://open.qobuz.com/album/333
EOF

# 2. Descargar todo
rip file lista.txt
```

### Flujo con conversión

```bash
# Descargar FLAC de Qobuz y convertir a ALAC (Apple Lossless)
rip -c ALAC url "https://open.qobuz.com/album/abc123"

# O configurar la conversión permanentemente en config.toml:
# [conversion]
# enabled = true
# codec   = "ALAC"
```

### Flujo de descarga de discografía

```bash
# Toda la discografía de un artista en Tidal
rip url "https://tidal.com/browse/artist/123456"

# Con filtros (solo álbumes de estudio, sin repetidos)
# Activar en config.toml:
# [qobuz_filters]
# non_studio_albums = true
# repeats = true
rip url "https://open.qobuz.com/artist/456789"
```

### Flujo con Last.fm

```bash
# Exportar tu playlist de Last.fm a Qobuz
rip lastfm "https://www.last.fm/user/tuusuario/playlists/12345"

# Con Tidal y fallback a Deezer
rip lastfm -s tidal -fs deezer "https://www.last.fm/user/tuusuario/playlists/12345"
```

### Flujo de depuración

```bash
# Ver todos los logs para diagnosticar un problema
rip -v url "https://tidal.com/browse/album/12345678"

# Deshabilitar base de datos y re-descargar todo
rip -ndb url "https://tidal.com/browse/album/12345678"

# Sin verificación SSL (en redes con certificados problemáticos)
rip --no-ssl-verify url "https://open.qobuz.com/album/abc123"
```

---

## Ayuda en la terminal

Todos los comandos tienen ayuda integrada:

```bash
rip --help
rip url --help
rip search --help
rip config --help
rip config open --help
rip database --help
rip database browse --help
rip lastfm --help
rip id --help
rip file --help
```
