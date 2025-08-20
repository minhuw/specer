"""CLI interface for SPEC CPU 2017 benchmark wrapper."""

from typing import Annotated

import typer

from specer.commands import (
    clean_command,
    compile_command,
    install_command,
    run_command,
    setup_command,
    topology_command,
    update_command,
)
from specer.logging import setup_logging

app = typer.Typer(
    name="specer",
    help="A CLI wrapper for SPEC CPU 2017 benchmark suite",
    add_completion=False,
)


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        from specer import __version__

        typer.echo(f"specer {__version__}")
        raise typer.Exit()


@app.callback()  # type: ignore[misc]
def main(
    _version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            "-V",
            callback=version_callback,
            help="Show version and exit",
        ),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Enable verbose output and detailed logging",
        ),
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            "-q",
            help="Suppress non-essential output",
        ),
    ] = False,
) -> None:
    """A CLI wrapper for SPEC CPU 2017 benchmark suite.

    You can set the SPEC CPU 2017 installation directory using the --spec-root option
    on individual commands or by setting the SPEC_ROOT environment variable.

    Logging Options:
    - Use --verbose for detailed output and debugging information
    - Use --quiet to suppress non-essential messages
    - Specer messages are clearly distinguished from SPEC CPU output
    """
    # Set up unified logging system
    setup_logging(verbose=verbose, quiet=quiet)


# Register commands
app.command(name="compile")(compile_command)
app.command(name="run")(run_command)
app.command(name="setup")(setup_command)
app.command(name="clean")(clean_command)
app.command(name="install")(install_command)
app.command(name="topology")(topology_command)
app.command(name="update")(update_command)


def cli_main() -> None:
    """Main entry point for the CLI."""
    app()


if __name__ == "__main__":
    cli_main()
