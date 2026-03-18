import os
import sys
import subprocess
import typer
from rich.console import Console
from rich.panel import Panel

app = typer.Typer()
console = Console()

@app.command()
def start(
    host: str = "0.0.0.0",
    port: int = 8000,
    reload: bool = True,
    workers: int = 1
):
    """
    Start the FastAPI server using Uvicorn.
    """
    console.print(Panel(f"[bold green]Starting Server...[/bold green]\nHost: {host}\nPort: {port}\nReload: {reload}", title="Menu Zen Back"))
    
    # We use subprocess to run uvicorn to ensure it picks up the environment correctly
    # and simplifies reloading behavior if run from a script
    cmd = [
        sys.executable, "-m", "uvicorn", 
        "app.main:app", 
        "--host", host, 
        "--port", str(port)
    ]
    
    if reload:
        cmd.append("--reload")
    else:
        cmd.extend(["--workers", str(workers)])
        
    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        console.print("[bold yellow]Server stopped by user.[/bold yellow]")
    except Exception as e:
        console.print(f"[bold red]Error starting server: {e}[/bold red]")

@app.command()
def bootstrap():
    """
    Initialize the environment (install dependencies).
    """
    console.print("[bold blue]Checking dependencies...[/bold blue]")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)
        console.print("[bold green]Dependencies installed successfully![/bold green]")
    except subprocess.CalledProcessError:
        console.print("[bold red]Failed to install dependencies.[/bold red]")

if __name__ == "__main__":
    app()
