"""Compile command for SPEC CPU 2017 benchmarks."""

import contextlib
import re
from pathlib import Path
from typing import Annotated

import typer

from specer.utils import (
    build_affinity_command,
    build_runcpu_command,
    convert_benchmark_names,
    detect_suite_preference,
    execute_runcpu,
    generate_config_from_template,
    validate_and_get_spec_root,
    validate_numa_topology,
)


def compile_command(
    benchmarks: Annotated[
        list[str],
        typer.Argument(
            help="Benchmarks to compile (e.g., 519.lbm_r, 500.perlbench_r, intspeed, fprate, all)"
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
    tune: Annotated[
        str | None,
        typer.Option(
            "--tune",
            "-t",
            help="Tuning level (base, peak, all)",
        ),
    ] = "base",
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
    rebuild: Annotated[
        bool,
        typer.Option(
            "--rebuild",
            help="Force rebuild of binaries",
        ),
    ] = False,
    parallel_test: Annotated[
        int | None,
        typer.Option(
            "--parallel-test",
            help="Number of parallel test processes",
        ),
    ] = None,
    ignore_errors: Annotated[
        bool,
        typer.Option(
            "--ignore-errors",
            help="Continue building other benchmarks if one fails",
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
            help="Number of CPU cores to use for compilation (affects auto-generated config)",
        ),
    ] = None,
    numa_node: Annotated[
        int | None,
        typer.Option(
            "--numa-node",
            help="Bind compilation processes to specific NUMA node (also binds memory allocation)",
        ),
    ] = None,
    cpu_cores: Annotated[
        str | None,
        typer.Option(
            "--cpu-cores",
            help="Bind compilation processes to specific CPU cores (e.g., '0-3', '0,2,4', '0-3,8-11')",
        ),
    ] = None,
    numa_memory: Annotated[
        bool | None,
        typer.Option(
            "--numa-memory/--no-numa-memory",
            help="Whether to bind memory allocation to the same NUMA node as CPU (default: True when --numa-node is specified)",
        ),
    ] = None,
) -> None:
    """Compile SPEC CPU 2017 benchmarks.

    This command wraps the 'runcpu --action=build' functionality, allowing you to
    compile benchmarks without running them.

    Examples:
        specer compile 519.lbm_r --config myconfig.cfg
        specer compile gcc --config myconfig.cfg --speed
        specer compile intspeed --config myconfig.cfg --tune all
        specer compile gcc lbm --config myconfig.cfg --rate --rebuild
        specer compile gcc --numa-node 0 --cpu-cores 0-7  # Compile on NUMA node 0
    """
    # Validate mutually exclusive options
    if speed and rate:
        typer.echo("Error: --speed and --rate options are mutually exclusive", err=True)
        raise typer.Exit(1)

    # Validate NUMA/CPU affinity options
    if numa_node is not None or cpu_cores is not None:
        # Validate NUMA topology if NUMA node specified
        if numa_node is not None:
            topology = validate_numa_topology()
            if topology is None:
                typer.echo(
                    "Error: NUMA topology not available or numactl not installed",
                    err=True,
                )
                raise typer.Exit(1)

            if numa_node not in topology["nodes"]:
                typer.echo(
                    f"Error: NUMA node {numa_node} not available. Available nodes: {topology['nodes']}",
                    err=True,
                )
                raise typer.Exit(1)

            if dry_run:
                typer.echo(
                    f"NUMA node {numa_node} validated (CPUs: {topology['node_cpus'][numa_node]})"
                )

        # Basic validation for CPU cores format
        if cpu_cores is not None:
            # Simple validation - more detailed validation would happen in numactl/taskset
            if (
                not cpu_cores.replace("-", "")
                .replace(",", "")
                .replace(" ", "")
                .isdigit()
            ):
                # Allow ranges and lists
                if not re.match(r"^[\d\-,\s]+$", cpu_cores):
                    typer.echo(
                        "Error: Invalid CPU cores format. Use formats like '0-3', '0,2,4', or '0-3,8-11'",
                        err=True,
                    )
                    raise typer.Exit(1)

            if dry_run:
                typer.echo(f"CPU cores binding: {cpu_cores}")

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
        action="build",
        benchmarks=converted_benchmarks,
        config=effective_config,
        tune=tune,
        spec_root=effective_spec_root,
        verbose=verbose,
        rebuild=rebuild,
        parallel_test=parallel_test,
        ignore_errors=ignore_errors,
    )

    if dry_run:
        # Show what the final command would look like with affinity
        if numa_node is not None or cpu_cores is not None:
            final_cmd = build_affinity_command(cmd, numa_node, cpu_cores, numa_memory)
            typer.echo(f"Would execute: {' '.join(final_cmd)}")
            if final_cmd != cmd:
                typer.echo(
                    f"  (with affinity wrapper: {' '.join(final_cmd[: final_cmd.index('--') if '--' in final_cmd else len(final_cmd) - len(cmd)])})"
                )
        else:
            typer.echo(f"Would execute: {' '.join(cmd)}")
        # Clean up generated config file if in dry-run mode
        if generated_config_path:
            Path(generated_config_path).unlink()
        return

    # Execute the command
    execute_runcpu(
        cmd,
        verbose=verbose,
        numa_node=numa_node,
        cpu_cores=cpu_cores,
        numa_memory=numa_memory,
    )

    # Clean up generated config file after execution
    if generated_config_path:
        with contextlib.suppress(OSError):
            Path(generated_config_path).unlink()
