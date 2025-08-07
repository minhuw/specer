"""Clean command for SPEC CPU 2017 benchmarks."""

from pathlib import Path
from typing import Annotated

import typer

from specer.utils import (
    build_runcpu_command,
    convert_benchmark_names,
    detect_suite_preference,
    execute_runcpu,
    validate_and_get_spec_root,
)


def clean_command(
    benchmarks: Annotated[
        list[str],
        typer.Argument(
            help="Benchmarks to clean (e.g., 519.lbm_r, 500.perlbench_r, intspeed, fprate, all)"
        ),
    ],
    config: Annotated[
        str,
        typer.Option(
            "--config",
            "-c",
            help="Configuration file to use",
        ),
    ],
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
    speed: Annotated[
        bool,
        typer.Option(
            "--speed",
            help="Prefer speed versions for simple benchmark names (e.g., gcc -> 602.gcc_s)",
        ),
    ] = False,
    rate: Annotated[
        bool,
        typer.Option(
            "--rate",
            help="Prefer rate versions for simple benchmark names (e.g., gcc -> 502.gcc_r)",
        ),
    ] = False,
) -> None:
    """Clean SPEC CPU 2017 benchmark build directories.

    Examples:
        specer clean 519.lbm_r --config myconfig.cfg
        specer clean gcc --config myconfig.cfg --speed
        specer clean all --config myconfig.cfg
    """
    # Validate mutually exclusive options
    if speed and rate:
        typer.echo("Error: --speed and --rate options are mutually exclusive", err=True)
        raise typer.Exit(1)

    # Convert simple benchmark names to full SPEC names
    if not speed and not rate:
        # Auto-detect preference from existing benchmarks
        prefer_speed, prefer_rate = detect_suite_preference(benchmarks)
    else:
        prefer_speed, prefer_rate = speed, rate

    converted_benchmarks = convert_benchmark_names(
        benchmarks, prefer_speed, prefer_rate
    )

    if dry_run and converted_benchmarks != benchmarks:
        typer.echo(f"Converted benchmark names: {benchmarks} -> {converted_benchmarks}")

    # Resolve the effective spec_root
    effective_spec_root = validate_and_get_spec_root(spec_root)

    # Build the runcpu command
    cmd = build_runcpu_command(
        action="clean",
        benchmarks=converted_benchmarks,
        config=config,
        spec_root=effective_spec_root,
        verbose=verbose,
    )

    if dry_run:
        typer.echo(f"Would execute: {' '.join(cmd)}")
        return

    # Execute the command
    execute_runcpu(cmd, verbose=verbose)
