# Solución de problemas

Esta guía cubre los errores más comunes y cómo resolverlos.

---

## Índice

- [Errores de autenticación](#errores-de-autenticación)
- [Errores de SSL](#errores-de-ssl)
- [Errores de descarga y reintentos](#errores-de-descarga-y-reintentos)
- [Errores de archivo y rutas](#errores-de-archivo-y-rutas)
- [Errores de conversión](#errores-de-conversión)
- [Problemas de configuración](#problemas-de-configuración)
- [Problemas de base de datos](#problemas-de-base-de-datos)
- [Problemas de metadatos y carátulas](#problemas-de-metadatos-y-carátulas)
- [Problemas de rendimiento](#problemas-de-rendimiento)
- [Diagnóstico general](#diagnóstico-general)

---

## Errores de autenticación

### Qobuz: "Invalid credentials" o "Authentication failed"

**Causa:** Email/contraseña incorrectos o el hash MD5 mal calculado.

**Solución:**

1. Verifica que el email es correcto en `config.toml`
2. Recalcula el hash MD5 del password:

```bash
python3 -c "import hashlib; print(hashlib.md5('TU_PASSWORD'.encode()).hexdigest())"
```

3. Copia el resultado en `password_or_token` del config.

Si usas token (`use_auth_token = true`), verifica que el token no haya caducado.

---

### Tidal: "Token expired" o "Unauthorized"

**Causa:** El access token de Tidal caduca aproximadamente cada semana.

**Solución:**

Los tokens se renuevan automáticamente si `refresh_token` está guardado en el config.
Si el error persiste:

1. Borra los campos `access_token`, `refresh_token` y `token_expiry` del config
2. Vuelve a autenticarte

Alternativamente, usa variables de entorno que no caducan:

```bash
export TIDAL_CLIENT_ID="tu_client_id"
export TIDAL_CLIENT_SECRET="tu_client_secret"
```

---

### Deezer: "Invalid ARL" o sin calidad FLAC

**Causa:** El ARL ha caducado o es incorrecto.

**Solución:**

1. Abre [deezer.com](https://www.deezer.com) en tu navegador e inicia sesión
2. Herramientas de desarrollador (`F12`) → **Aplicación → Cookies → deezer.com**
3. Copia el valor de la cookie `arl` (es una cadena larga)
4. Actualiza el config:

```toml
[deezer]
arl = "NUEVA_COOKIE_ARL"
```

> Los ARL suelen durar varios meses pero pueden invalidarse si cambias la contraseña o cierras sesión en todos los dispositivos.

---

### "403 Forbidden" o "Not streamable"

**Causa:** El track no está disponible en tu región, tu suscripción no cubre esa calidad, o el contenido ha sido eliminado.

**Solución:**

- Prueba una calidad inferior (`-q 2` o `-q 1`)
- Verifica que tu suscripción incluye el nivel de calidad solicitado
- El track puede no estar disponible en tu país

---

## Errores de SSL

### "SSL Certificate verification error"

```
SSL Certificate verification error: Cannot connect to host ... certificate verify failed
```

**Causa:** El certificado SSL del servidor no es válido o hay un proxy interceptando la conexión.

**Solución temporal (una descarga):**

```bash
rip --no-ssl-verify url "https://..."
```

**Solución permanente (en config.toml):**

```toml
[downloads]
verify_ssl = false
```

> Usa esta opción solo si confías en tu red. Desactivar SSL puede exponerte a ataques de intermediario.

---

## Errores de descarga y reintentos

### "Download failed after N retries"

**Causa:** El servidor no responde, hay un problema de red temporal, o el track está siendo limitado.

**Solución:**

1. Aumenta los reintentos y la espera:

```toml
[downloads]
max_retries = 5
retry_delay = 5.0
max_wait    = 120.0
```

2. Reduce las conexiones simultáneas:

```toml
[downloads]
max_connections = 2
requests_per_minute = 30
```

3. Espera unos minutos y reintenta (puede ser throttling de la API)

---

### "Track was not downloaded after all retries; skipping post-processing"

**Causa:** El archivo no se creó en disco tras agotar todos los reintentos. El log incluirá el ID del track para facilitar la identificación.

**Solución:**

- Verifica que tienes espacio en disco suficiente
- Comprueba los permisos de la carpeta de descarga
- Usa `rip -v` para ver los logs detallados del error específico
- Revisa la base de datos de fallidos:

```bash
rip database browse failed
```

---

### La descarga se para a mitad y no retoma

**Causa:** Streamrip no tiene descarga reanudable incorporada. Si el proceso se interrumpe, el archivo parcial puede quedar en disco.

**Solución:**

1. Borra los archivos `.tmp` o parciales en la carpeta de descarga
2. Usa `-ndb` si el track quedó marcado como descargado en la BD pero el archivo está incompleto:

```bash
rip -ndb url "https://..."
```

---

### "Too many requests" / Rate limiting

**Causa:** Se están haciendo demasiadas llamadas a la API en poco tiempo.

**Solución:**

```toml
[downloads]
requests_per_minute = 30   # reducir el límite
max_connections     = 3    # menos conexiones simultáneas
```

---

## Errores de archivo y rutas

### "Filename too long" / Error al crear el archivo

**Causa:** El nombre de archivo generado supera el límite del sistema de archivos (260 caracteres en Windows, 255 en Linux/macOS para el nombre del archivo).

**Solución:**

```toml
[filepaths]
truncate_to = 80              # reducir longitud máxima
restrict_characters = true    # solo ASCII (evita problemas con caracteres especiales)

# Simplificar plantillas
folder_format = "{albumartist}/{title} ({year})"
track_format  = "{tracknumber:02}. {title}"
```

---

### Los archivos se descargan pero no aparecen donde espero

**Causa:** La carpeta de descarga no está configurada o apunta a un lugar incorrecto.

**Solución:**

```bash
# Ver la carpeta configurada
rip config path
# Luego abrir el config y verificar `folder`

# O especificar la carpeta directamente
rip -f /ruta/a/mi/musica url "https://..."
```

---

### Caracteres extraños en nombres de archivo (`?`, `:`, `*`, etc.)

**Causa:** Los metadatos contienen caracteres no válidos en el sistema de archivos (especialmente en Windows).

**Solución:**

```toml
[filepaths]
restrict_characters = true   # solo ASCII imprimible
```

> Streamrip sustituye automáticamente `:` por `：` (coma de ancho completo) y otros caracteres problemáticos. Si aun así hay problemas, activa `restrict_characters`.

---

## Errores de conversión

### "ffmpeg not found" o "Conversion failed"

**Causa:** FFmpeg no está instalado o no está en el PATH.

**Verificar:**

```bash
ffmpeg -version
```

**Instalar FFmpeg:**

- **Windows:** `winget install ffmpeg` o desde [ffmpeg.org](https://ffmpeg.org/download.html)
- **macOS:** `brew install ffmpeg`
- **Ubuntu/Debian:** `sudo apt install ffmpeg`
- **Fedora:** `sudo dnf install ffmpeg`

---

### El archivo convertido no tiene la calidad esperada

**Causa:** La frecuencia o profundidad de bits configurada es mayor que la del archivo original; la conversión no puede mejorar la calidad, solo mantenerla o reducirla.

**Revisión:**

```toml
[conversion]
# Solo se aplica si el original tiene MAYOR resolución que esto
sampling_rate = 44100   # no downsamplea FLAC 44.1kHz
bit_depth     = 16      # no reduce de 16-bit (no hay cambio)
```

---

## Problemas de configuración

### "Error loading config" al arrancar

```
Error loading config from /ruta/config.toml: ...
Try running rip config reset
```

**Causa:** El archivo de config está corrupto o tiene sintaxis TOML incorrecta.

**Solución:**

```bash
# Resetear a los valores por defecto
rip config reset

# O usar un config alternativo
rip --config-path /ruta/a/config.toml url "..."
```

---

### "Outdated config" / Config desactualizado

**Causa:** Estás usando un `config.toml` de una versión anterior.

**Solución:** Streamrip actualiza el config automáticamente. Si el error persiste:

```bash
rip config reset
```

Luego vuelve a poner tus credenciales y preferencias.

---

### Los cambios en el config no tienen efecto

**Causa:** Hay múltiples archivos de config y estás editando el incorrecto.

**Solución:**

```bash
# Ver qué config se está usando
rip config path
```

Edita el archivo que aparece en esa ruta.

---

## Problemas de base de datos

### Un track que ya tienes se descarga otra vez

**Causa:** El track no estaba en la base de datos (fue descargado con `--no-db`, o la BD fue borrada, o el ID cambió).

**Comportamiento esperado:** Streamrip comprueba por ID, no por nombre de archivo.

**Diagnóstico:**

```bash
rip database browse downloads
```

Si el ID no aparece, añádelo manualmente o simplemente déjalo descargar de nuevo.

---

### Un track no se descarga y no aparece en la BD de fallidos

**Causa:** El track fue saltado por no estar disponible (`NonStreamableError`), lo cual no se considera un "fallo" sino una exclusión esperada.

**Solución:** Verifica la disponibilidad del contenido en tu región y con tu suscripción.

---

### "Database is locked"

**Causa:** Otra instancia de streamrip está corriendo simultáneamente o el archivo de BD está bloqueado.

**Solución:**

1. Asegúrate de que no hay otro `rip` corriendo
2. Si persiste, borra el archivo `.db` de la BD (pierdes el historial):

```bash
# Ver la ruta
rip config path
# El archivo .db está en el mismo directorio que el config
```

---

## Problemas de metadatos y carátulas

### Las carátulas no se embeben

**Causa:** Imagen demasiado grande con `embed_size = "original"`, o el codec de destino no soporta carátulas embebidas.

**Solución:**

```toml
[artwork]
embed_size     = "large"    # en vez de "original"
embed_max_width = 600       # limitar a 600px
```

---

### El nombre del artista usa `, ` pero quiero `&`

Configura el separador de artistas:

```toml
[metadata]
artist_separator = " & "
```

Esto afecta tanto al nombre del archivo como al tag `ARTIST` embebido.

---

### Los tracks de la playlist tienen números de track incorrectos

**Causa:** `renumber_playlist_tracks = false` usa el número original del álbum en vez de la posición en la playlist.

**Solución:**

```toml
[metadata]
renumber_playlist_tracks = true
```

---

### El campo ALBUM de los tracks de una playlist muestra el álbum original, no la playlist

**Solución:**

```toml
[metadata]
set_playlist_to_album = true
```

---

## Problemas de rendimiento

### Las descargas son muy lentas

1. **Activar concurrencia:**

```toml
[downloads]
concurrency     = true
max_connections = 6
```

2. **Verificar la velocidad de internet:** streamrip puede estar limitado por tu conexión o por la API del servicio.

3. **Reducir la tasa de peticiones si hay throttling:**

```toml
[downloads]
requests_per_minute = 30
```

---

### Alto uso de CPU durante las descargas

**Causa probable:** La conversión de audio está activa.

```toml
[conversion]
enabled = false   # desactivar si no necesitas convertir
```

---

## Diagnóstico general

### Activar modo verbose

El modo `-v` muestra todos los logs internos, muy útil para identificar el origen de un error:

```bash
rip -v url "https://..."
rip -v search qobuz album "..."
```

### Ver versión instalada

```bash
rip --version
```

### Verificar la instalación de dependencias

```bash
python3 -c "import streamrip; print('OK')"
ffmpeg -version
```

### Flujo de diagnóstico paso a paso

```bash
# 1. Ver qué config se usa
rip config path

# 2. Ver logs detallados
rip -v url "https://..."

# 3. Verificar la BD de fallidos
rip database browse failed

# 4. Reintentar sin base de datos
rip -ndb url "https://..."

# 5. Resetear config si todo falla
rip config reset
```

---

## Reportar un bug

Si el problema persiste después de seguir esta guía:

1. Ejecuta con `-v` y copia el log completo
2. Incluye la versión: `rip --version`
3. Incluye el sistema operativo y versión de Python: `python3 --version`
4. Abre un issue en [github.com/Np3ir/streamrip-elvigilante](https://github.com/Np3ir/streamrip-elvigilante/issues)

> **Nunca incluyas credenciales (ARL, tokens, contraseñas) al reportar un bug.**
