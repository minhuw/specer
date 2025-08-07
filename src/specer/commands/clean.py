"""Clean command for SPEC CPU 2017 benchmarks."""

import contextlib
from pathlib import Path
from typing import Annotated

import typer

from specer.utils import (
    build_runcpu_command,
    convert_benchmark_names,
    detect_suite_preference,
    execute_runcpu,
    generate_config_from_template,
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
        str | None,
        typer.Option(
            "--config",
            "-c",
            help="Configuration file to use (auto-generated from template if not specified)",
        ),
    ] = None,
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
    cores: Annotated[
        int | None,
        typer.Option(
            "--cores",
            help="Number of CPU cores to use (affects auto-generated config)",
        ),
    ] = None,
    tune: Annotated[
        str | None,
        typer.Option(
            "--tune",
            "-t",
            help="Tuning level (base, peak, all)",
        ),
    ] = "base",
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

    # Resolve the effective spec_root early since it's needed for config generation
    effective_spec_root = validate_and_get_spec_root(spec_root)

    # Handle config generation and validation
    effective_config = config
    generated_config_path = None

    # Always auto-generate config if no config is provided
    if config is None:
        # Automatically generate config from template
        generated_config_path = generate_config_from_template(
            cores, effective_spec_root, tune
        )
        if generated_config_path:
            effective_config = generated_config_path
            if dry_run:
                if cores is not None:
                    typer.echo(
                        f"Auto-generated config file with {cores} cores: {generated_config_path}"
                    )
                else:
                    typer.echo(f"Auto-generated config file: {generated_config_path}")
        else:
            typer.echo(
                "Error: Could not auto-generate config file from template", err=True
            )
            raise typer.Exit(1)

    if effective_config is None:
        typer.echo(
            "Error: Failed to create config file. Please check template file exists.",
            err=True,
        )
        raise typer.Exit(1)

    # Build the runcpu command
    cmd = build_runcpu_command(
        action="clean",
        benchmarks=converted_benchmarks,
        config=effective_config,
        spec_root=effective_spec_root,
        verbose=verbose,
    )

    if dry_run:
        typer.echo(f"Would execute: {' '.join(cmd)}")
        # Clean up generated config file if in dry-run mode
        if generated_config_path:
            Path(generated_config_path).unlink()
        return

    # Execute the command
    execute_runcpu(cmd, verbose=verbose)

    # Clean up generated config file after execution
    if generated_config_path:
        with contextlib.suppress(OSError):
            Path(generated_config_path).unlink()
