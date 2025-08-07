"""Update command for SPEC CPU 2017 installation."""

from pathlib import Path
from typing import Annotated, Optional

import typer

from specer.utils import (
    build_runcpu_command,
    execute_runcpu,
    validate_and_get_spec_root,
)


def update_command(
    spec_root: Annotated[
        Optional[Path],
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

    # Execute the command
    execute_runcpu(cmd, verbose=verbose)
