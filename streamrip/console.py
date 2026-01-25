from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.style import Style

console = Console()

def print_banner():
    banner_text = """
  _______ _   _  _____   _____  _
 |__   __| | | ||  __ \ |  __ \| |
    | |  | | | || |  | || |  | | |
    | |  | | | || |  | || |  | | |
    | |  | |_| || |__| || |__| | |
    |_|   \___/ |_____/ |_____/|_|
    """
    # Create a cyan panel with the banner
    grid = Text(banner_text, style="bold cyan")
    console.print(grid)
    console.print("[bold cyan]Streamrip[/bold cyan] [white]styled as[/white] [bold cyan]TiDDL[/bold cyan]\n")
