import logging
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
    TaskID
)

logger = logging.getLogger("streamrip")


# --- CONFIGURACIÓN VISUAL (ESTILO CYBERPUNK) ---
def get_progress() -> Progress:
    return Progress(
        # 1. Spinner Animado
        SpinnerColumn(spinner_name="dots", style="bold magenta"),

        # 2. Nombre del Archivo (Cyan Negrita)
        TextColumn("[bold cyan]{task.fields[filename]}", justify="right"),

        # 3. Barra de Progreso
        BarColumn(
            bar_width=40,
            style="dim white",
            complete_style="cyan",
            finished_style="bold green"
        ),

        # 4. Porcentaje
        "[progress.percentage]{task.percentage:>3.0f}%",
        "•",

        # 5. Tamaño
        DownloadColumn(),
        "•",

        # 6. Velocidad
        TransferSpeedColumn(),
        "•",

        # 7. Tiempo Restante
        TimeRemainingColumn(),

        transient=True,
        expand=True,
    )


# --- MAQUINARIA INTERNA ---
_progress = get_progress()


def add_title(filename: str) -> TaskID:
    """Añade una tarea de descarga a la barra y la inicia si es necesario."""
    if not _progress.live:
        _progress.start()

    # Añadimos la tarea con el campo 'filename' para el estilo visual
    task_id = _progress.add_task("download", filename=filename, total=None)
    return task_id


def remove_title(task_id: TaskID):
    """Elimina una tarea de la barra al terminar."""
    try:
        _progress.remove_task(task_id)
    except KeyError:
        pass

    if not _progress.tasks:
        _progress.stop()


# --- CORRECCIÓN AQUÍ: AÑADIDO TERCER ARGUMENTO ---
def get_progress_callback(task_id: TaskID, total_size: int, description: str = ""):
    """
    Devuelve la función callback.
    Aceptamos 'description' para evitar el error '3 arguments given',
    aunque no lo usemos (ya que usamos add_title para el nombre).
    """

    if total_size:
        _progress.update(task_id, total=total_size)

    def callback(current_bytes_read):
        _progress.update(task_id, completed=current_bytes_read)

    return callback


def clear_progress():
    """Limpia forzosamente la barra de progreso."""
    if _progress.live:
        _progress.stop()