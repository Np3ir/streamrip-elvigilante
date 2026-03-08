# Troubleshooting

This guide covers the most common errors and how to resolve them.

---

## Table of contents

- [Authentication errors](#authentication-errors)
- [SSL errors](#ssl-errors)
- [Download and retry errors](#download-and-retry-errors)
- [File and path errors](#file-and-path-errors)
- [Conversion errors](#conversion-errors)
- [Configuration problems](#configuration-problems)
- [Database problems](#database-problems)
- [Metadata and artwork problems](#metadata-and-artwork-problems)
- [Performance problems](#performance-problems)
- [General diagnostics](#general-diagnostics)

---

## Authentication errors

### Qobuz: "Invalid credentials" or "Authentication failed"

**Cause:** Incorrect email/password or a wrongly computed MD5 hash.

**Solution:**

1. Verify the email is correct in `config.toml`
2. Recompute the MD5 hash of your password:

```bash
python3 -c "import hashlib; print(hashlib.md5('YOUR_PASSWORD'.encode()).hexdigest())"
```

3. Copy the result into `password_or_token` in the config.

If you use a token (`use_auth_token = true`), verify that the token has not expired.

---

### Tidal: "Token expired" or "Unauthorized"

**Cause:** The Tidal access token expires roughly every week.

**Solution:**

Tokens are renewed automatically if `refresh_token` is stored in the config.
If the error persists:

1. Delete the `access_token`, `refresh_token` and `token_expiry` fields from the config
2. Re-authenticate

Alternatively, use environment variables that do not expire:

```bash
export TIDAL_CLIENT_ID="your_client_id"
export TIDAL_CLIENT_SECRET="your_client_secret"
```

---

### Deezer: "Invalid ARL" or no FLAC quality

**Cause:** The ARL has expired or is incorrect.

**Solution:**

1. Open [deezer.com](https://www.deezer.com) in your browser and log in
2. Developer Tools (`F12`) → **Application → Cookies → deezer.com**
3. Copy the value of the `arl` cookie (a long string)
4. Update the config:

```toml
[deezer]
arl = "NEW_ARL_COOKIE"
```

> ARLs typically last several months but can be invalidated if you change your password or log out of all devices.

---

### "403 Forbidden" or "Not streamable"

**Cause:** The track is not available in your region, your subscription does not cover that quality level, or the content has been removed.

**Solution:**

- Try a lower quality (`-q 2` or `-q 1`)
- Verify that your subscription includes the requested quality level
- The track may not be available in your country

---

## SSL errors

### "SSL Certificate verification error"

```
SSL Certificate verification error: Cannot connect to host ... certificate verify failed
```

**Cause:** The server's SSL certificate is invalid or a proxy is intercepting the connection.

**Temporary fix (one download):**

```bash
rip --no-ssl-verify url "https://..."
```

**Permanent fix (in config.toml):**

```toml
[downloads]
verify_ssl = false
```

> Use this option only on trusted networks. Disabling SSL can expose you to man-in-the-middle attacks.

---

## Download and retry errors

### "Download failed after N retries"

**Cause:** The server is not responding, there is a temporary network issue, or the track is being rate-limited.

**Solution:**

1. Increase retries and wait time:

```toml
[downloads]
max_retries = 5
retry_delay = 5.0
max_wait    = 120.0
```

2. Reduce simultaneous connections:

```toml
[downloads]
max_connections     = 2
requests_per_minute = 30
```

3. Wait a few minutes and retry (may be API throttling)

---

### "Track was not downloaded after all retries; skipping post-processing"

**Cause:** The file was not created on disk after exhausting all retries. The log includes the track ID to help identify it.

**Solution:**

- Verify that you have enough disk space
- Check the permissions on the download folder
- Use `rip -v` to see detailed logs for the specific error
- Check the failed downloads database:

```bash
rip database browse failed
```

---

### Download stops halfway and does not resume

**Cause:** Streamrip does not have built-in resumable downloads. If the process is interrupted, a partial file may remain on disk.

**Solution:**

1. Delete any `.tmp` or partial files in the download folder
2. Use `-ndb` if the track was marked as downloaded in the database but the file is incomplete:

```bash
rip -ndb url "https://..."
```

---

### "Too many requests" / Rate limiting

**Cause:** Too many API calls are being made in a short period.

**Solution:**

```toml
[downloads]
requests_per_minute = 30   # reduce the limit
max_connections     = 3    # fewer simultaneous connections
```

---

## File and path errors

### "Filename too long" / Error creating file

**Cause:** The generated file name exceeds the filesystem limit (260 characters on Windows, 255 on Linux/macOS for the file name component).

**Solution:**

```toml
[filepaths]
truncate_to         = 80              # reduce maximum length
restrict_characters = true            # ASCII only (avoids issues with special characters)

# Simplify templates
folder_format = "{albumartist}/{title} ({year})"
track_format  = "{tracknumber:02}. {title}"
```

---

### Files download but don't appear where expected

**Cause:** The download folder is not configured or points to the wrong location.

**Solution:**

```bash
# See the configured folder
rip config path
# Then open the config and check `folder`

# Or specify the folder directly
rip -f /path/to/my/music url "https://..."
```

---

### Strange characters in file names (`?`, `:`, `*`, etc.)

**Cause:** Metadata contains characters that are invalid on the filesystem (especially on Windows).

**Solution:**

```toml
[filepaths]
restrict_characters = true   # printable ASCII only
```

> Streamrip automatically replaces `:` with `：` (full-width colon) and other problematic characters. If issues persist, enable `restrict_characters`.

---

## Conversion errors

### "ffmpeg not found" or "Conversion failed"

**Cause:** FFmpeg is not installed or is not in the PATH.

**Verify:**

```bash
ffmpeg -version
```

**Install FFmpeg:**

- **Windows:** `winget install ffmpeg` or from [ffmpeg.org](https://ffmpeg.org/download.html)
- **macOS:** `brew install ffmpeg`
- **Ubuntu/Debian:** `sudo apt install ffmpeg`
- **Fedora:** `sudo dnf install ffmpeg`

---

### The converted file does not have the expected quality

**Cause:** The configured frequency or bit depth is higher than the original file's; conversion cannot improve quality, only maintain or reduce it.

**Review:**

```toml
[conversion]
# Only applied if the original has HIGHER resolution than this
sampling_rate = 44100   # does not down-sample FLAC 44.1 kHz
bit_depth     = 16      # does not reduce from 16-bit (no change)
```

---

## Configuration problems

### "Error loading config" on startup

```
Error loading config from /path/config.toml: ...
Try running rip config reset
```

**Cause:** The config file is corrupt or has invalid TOML syntax.

**Solution:**

```bash
# Reset to default values
rip config reset

# Or use an alternative config
rip --config-path /path/to/config.toml url "..."
```

---

### "Outdated config" / Config out of date

**Cause:** You are using a `config.toml` from an older version.

**Solution:** Streamrip updates the config automatically. If the error persists:

```bash
rip config reset
```

Then re-enter your credentials and preferences.

---

### Config changes have no effect

**Cause:** There are multiple config files and you are editing the wrong one.

**Solution:**

```bash
# See which config is being used
rip config path
```

Edit the file shown at that path.

---

## Database problems

### A track you already have is downloaded again

**Cause:** The track was not in the database (downloaded with `--no-db`, the database was deleted, or the ID changed).

**Expected behaviour:** Streamrip checks by ID, not by file name.

**Diagnosis:**

```bash
rip database browse downloads
```

If the ID does not appear, add it manually or simply let it download again.

---

### A track is not downloaded and does not appear in the failed database

**Cause:** The track was skipped as unavailable (`NonStreamableError`), which is not considered a "failure" but an expected exclusion.

**Solution:** Verify content availability in your region and with your subscription.

---

### "Database is locked"

**Cause:** Another streamrip instance is running simultaneously or the database file is locked.

**Solution:**

1. Make sure no other `rip` process is running
2. If it persists, delete the `.db` file (you lose the history):

```bash
# Find the path
rip config path
# The .db file is in the same directory as the config
```

---

## Metadata and artwork problems

### Cover art is not embedded

**Cause:** Image too large with `embed_size = "original"`, or the target codec does not support embedded covers.

**Solution:**

```toml
[artwork]
embed_size      = "large"    # instead of "original"
embed_max_width = 600        # limit to 600 px
```

---

### Artist name uses `, ` but I want `&`

Configure the artist separator:

```toml
[metadata]
artist_separator = " & "
```

This affects both the file name and the embedded `ARTIST` tag.

---

### Playlist tracks have incorrect track numbers

**Cause:** `renumber_playlist_tracks = false` uses the original album number instead of the position in the playlist.

**Solution:**

```toml
[metadata]
renumber_playlist_tracks = true
```

---

### The ALBUM field of playlist tracks shows the original album, not the playlist

**Solution:**

```toml
[metadata]
set_playlist_to_album = true
```

---

## Performance problems

### Downloads are very slow

1. **Enable concurrency:**

```toml
[downloads]
concurrency     = true
max_connections = 6
```

2. **Check your internet speed:** streamrip may be limited by your connection or the service's API.

3. **Reduce request rate if throttling occurs:**

```toml
[downloads]
requests_per_minute = 30
```

---

### High CPU usage during downloads

**Probable cause:** Audio conversion is enabled.

```toml
[conversion]
enabled = false   # disable if you do not need conversion
```

---

## General diagnostics

### Enable verbose mode

The `-v` flag shows all internal logs, very useful for identifying the source of an error:

```bash
rip -v url "https://..."
rip -v search qobuz album "..."
```

### Check the installed version

```bash
rip --version
```

### Verify the dependency installation

```bash
python3 -c "import streamrip; print('OK')"
ffmpeg -version
```

### Step-by-step diagnostic flow

```bash
# 1. See which config is being used
rip config path

# 2. See detailed logs
rip -v url "https://..."

# 3. Check the failed downloads database
rip database browse failed

# 4. Retry without the database
rip -ndb url "https://..."

# 5. Reset config if all else fails
rip config reset
```

---

## Reporting a bug

If the problem persists after following this guide:

1. Run with `-v` and copy the full log
2. Include the version: `rip --version`
3. Include the OS and Python version: `python3 --version`
4. Open an issue at [github.com/Np3ir/streamrip-elvigilante](https://github.com/Np3ir/streamrip-elvigilante/issues)

> **Never include credentials (ARL, tokens, passwords) when reporting a bug.**
