"""Update command for SPEC CPU 2017 installation."""

import subprocess
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from specer.utils import (
    build_runcpu_command,
    validate_and_get_spec_root,
)


def update_command(
    spec_root: Annotated[
        Path | None,
        typer.Option(
            "--spec-root",
            "-s",
            help="SPEC CPU 2017 installation directory (required)",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Show the command that would be executed without running it",
        ),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Enable verbose output",
        ),
    ] = False,
) -> None:
    """Update SPEC CPU 2017 installation to the latest version.

    This command wraps the 'runcpu --update' functionality, allowing you to
    update your SPEC CPU 2017 installation with the latest patches and fixes.

    Examples:
        specer update
        specer update --spec-root /opt/spec2017
        specer update --dry-run
    """
    # Resolve the effective spec_root
    effective_spec_root = validate_and_get_spec_root(spec_root)

    # Build the runcpu command
    cmd = build_runcpu_command(
        action="update",
        benchmarks=[],  # Update doesn't need benchmarks
        config="",  # Update doesn't need a config file
        spec_root=effective_spec_root,
        verbose=verbose,
    )

    if dry_run:
        typer.echo(f"Would execute: {' '.join(cmd)}")
        return

    # Execute the command with automatic confirmation
    _execute_update_with_confirmation(cmd)


def _execute_update_with_confirmation(cmd: list[str]) -> None:
    """Execute runcpu update command with automatic confirmation."""
    console = Console()

    console.print("🔄 [blue]Starting SPEC CPU 2017 update process...[/blue]")
    console.print(f"🔧 [blue]Running:[/blue] [cyan]{' '.join(cmd)}[/cyan]")
    console.print("ℹ️  [cyan]Auto-answering 'y' to update confirmation prompt[/cyan]")
    console.print("📺 [cyan]Live output from runcpu --update:[/cyan]")
    console.print("─" * 80, style="dim")

    try:
        # Use a more reliable approach: run with echo piped to stdin
        # This ensures the 'y' response is available when the prompt appears
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )

        # Pre-feed the 'y' response to stdin immediately
        if process.stdin is not None:
            try:
                process.stdin.write("y\n")
                process.stdin.flush()
                process.stdin.close()  # Close stdin so the process knows no more input is coming
            except (BrokenPipeError, OSError):
                # Process may have closed stdin already
                pass

        # Stream output in real-time
        while True:
            if process.stdout is None:
                break
            output = process.stdout.readline()
            if output == "" and process.poll() is not None:
                break
            if output:
                # Print each line directly for real-time viewing
                console.print(output.rstrip(), highlight=False)

                # Show when the prompt appears (we've already sent the response)
                if "Proceed with update? (y/n)" in output:
                    console.print("[dim]Auto-responding: y[/dim]")

        # Wait for process to complete and get return code
        return_code = process.wait()

        console.print("─" * 80, style="dim")

        if return_code == 0:
            console.print(
                "✅ [bold green]SPEC CPU 2017 update completed successfully![/bold green]"
            )
            console.print("🚀 [green]Your SPEC installation is now up to date[/green]")
        else:
            console.print(f"❌ [red]Update failed with return code {return_code}[/red]")
            raise typer.Exit(return_code)

    except subprocess.TimeoutExpired:
        console.print("❌ [red]Update process timed out[/red]")
        raise typer.Exit(1) from None
    except Exception as e:
        console.print(f"❌ [red]Error during update: {e}[/red]")
        raise typer.Exit(1) from e
