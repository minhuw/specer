"""Run command for SPEC CPU 2017 benchmarks."""

import contextlib
import re
import time
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel

from specer.logging import logger
from specer.result_parser import read_result_file
from specer.sync import create_evalsync_worker
from specer.utils import (
    build_affinity_command,
    build_runcpu_command,
    convert_benchmark_names,
    detect_suite_preference,
    display_results_with_rich,
    execute_runcpu,
    generate_config_from_template,
    save_results_to_json,
    validate_and_get_spec_root,
    validate_numa_topology,
)


def run_command(
    benchmarks: Annotated[
        list[str],
        typer.Argument(
            help="Benchmarks to run (e.g., 519.lbm_r, 500.perlbench_r, intspeed, fprate, all)"
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
    tune: Annotated[
        str | None,
        typer.Option(
            "--tune",
            "-t",
            help="Tuning level (base, peak, all)",
        ),
    ] = "base",
    size: Annotated[
        str | None,
        typer.Option(
            "--size",
            "-i",
            help="Workload size (test, train, ref)",
        ),
    ] = "ref",
    copies: Annotated[
        int | None,
        typer.Option(
            "--copies",
            help="Number of copies for rate benchmarks",
        ),
    ] = None,
    threads: Annotated[
        int | None,
        typer.Option(
            "--threads",
            help="Number of threads for speed benchmarks",
        ),
    ] = None,
    iterations: Annotated[
        int | None,
        typer.Option(
            "--iterations",
            help="Number of iterations (2 or 3 for reportable runs)",
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
            help="Show original SPEC logs and detailed output",
        ),
    ] = False,
    reportable: Annotated[
        bool,
        typer.Option(
            "--reportable",
            help="Run in reportable mode",
        ),
    ] = False,
    noreportable: Annotated[
        bool,
        typer.Option(
            "--noreportable",
            help="Run in non-reportable mode",
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
            help="Continue running other benchmarks if one fails",
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
            help="Number of CPU cores to use (for SPECrate: copies, for SPECspeed: threads)",
        ),
    ] = None,
    parse_results: Annotated[
        bool,
        typer.Option(
            "--parse-results",
            help="Parse runcpu output to find and display result file locations and scores",
        ),
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            "-q",
            help="(Deprecated: now default behavior) Hide original SPEC logs and show only clean results",
        ),
    ] = False,
    rich_output: Annotated[
        bool,
        typer.Option(
            "--rich",
            help="Force Rich library output (now default unless --verbose or --parse-results)",
        ),
    ] = False,
    json_output: Annotated[
        str | None,
        typer.Option(
            "--json",
            help="Save results to JSON file (auto-named if no path provided)",
        ),
    ] = None,
    output_formats: Annotated[
        str | None,
        typer.Option(
            "--output-formats",
            help="SPEC output formats (default: 'rsf,pdf' for speed). Use 'all' for full compatibility with legacy tools.",
        ),
    ] = None,
    numa_node: Annotated[
        int | None,
        typer.Option(
            "--numa-node",
            help="Bind benchmark processes to specific NUMA node (also binds memory allocation)",
        ),
    ] = None,
    cpu_cores: Annotated[
        str | None,
        typer.Option(
            "--cpu-cores",
            help="Bind benchmark processes to specific CPU cores (e.g., '0-3', '0,2,4', '0-3,8-11')",
        ),
    ] = None,
    numa_memory: Annotated[
        bool | None,
        typer.Option(
            "--numa-memory/--no-numa-memory",
            help="Whether to bind memory allocation to the same NUMA node as CPU (default: True when --numa-node is specified)",
        ),
    ] = None,
    sync: Annotated[
        bool,
        typer.Option(
            "--sync",
            help="Enable EvalSync integration for synchronized benchmark execution with external manager (requires EVALSYNC_EXPERIMENT_ID and EVALSYNC_CLIENT_ID environment variables)",
        ),
    ] = False,
) -> None:
    """Run SPEC CPU 2017 benchmarks.

    This command wraps the 'runcpu --action=run' functionality for running benchmarks.
    Config files are automatically generated from template when not specified.

    🎯 NEW: Clean Rich output is now the default! Use --verbose to see original SPEC logs.

    📄 OUTPUT FORMATS: By default, only RSF and PDF formats are generated for speed.
    Use --output-formats=all for full compatibility with legacy analysis tools.

    Examples:
        specer run 519.lbm_r --config myconfig.cfg     # Use specific config
        specer run gcc --speed --dry-run               # Auto-generate config
        specer run intrate --cores 16 --dry-run        # Auto-generate with 16 cores
        specer run gcc --cores 8 --speed --reportable  # Auto-generate and run
        specer run intrate --threads 8 --copies 4      # Auto-generate with custom settings

        # Rich output and JSON features (Rich output is now default):
        specer run gcc --json results.json             # Beautiful output + JSON (default)
        specer run intrate --verbose                    # Show original SPEC logs
        specer run gcc --json                          # Auto-named JSON output

        # Output format control:
        specer run gcc --output-formats=rsf,pdf        # Default (fast)
        specer run gcc --output-formats=all            # All formats (compatible)
        specer run gcc --output-formats=rsf,html       # Custom selection

        # NUMA and CPU affinity control:
        specer run gcc --numa-node 0                   # Bind to NUMA node 0
        specer run gcc --cpu-cores 0-3                 # Bind to CPU cores 0-3
        specer run gcc --cpu-cores 0,2,4,6             # Bind to specific cores
        specer run intrate --numa-node 1 --cpu-cores 8-15  # NUMA node 1, cores 8-15
        specer run gcc --numa-node 0 --no-numa-memory  # NUMA node 0, but don't bind memory
    """
    # Validate mutually exclusive options
    if speed and rate:
        typer.echo("Error: --speed and --rate options are mutually exclusive", err=True)
        raise typer.Exit(1)

    # Validate reportable mode requirements
    if reportable:
        # SPEC reportable runs require full benchmark suites, not individual benchmarks
        valid_suites = {"intspeed", "intrate", "fpspeed", "fprate", "all"}
        if not any(bench.lower() in valid_suites for bench in benchmarks):
            typer.echo("Error: --reportable requires a full benchmark suite", err=True)
            typer.echo("", err=True)
            typer.echo("Valid suites for reportable runs:", err=True)
            typer.echo("  intspeed   - Integer speed benchmarks", err=True)
            typer.echo("  intrate    - Integer rate benchmarks", err=True)
            typer.echo("  fpspeed    - Floating-point speed benchmarks", err=True)
            typer.echo("  fprate     - Floating-point rate benchmarks", err=True)
            typer.echo("  all        - All benchmark suites", err=True)
            typer.echo("", err=True)
            typer.echo(
                "For individual benchmarks, use --noreportable instead:", err=True
            )
            typer.echo(f"  specer run {' '.join(benchmarks)} --noreportable", err=True)
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

    # Resolve the effective spec_root early since it's needed for config generation
    effective_spec_root = validate_and_get_spec_root(spec_root)

    # Handle config generation and validation
    effective_config = config
    generated_config_path = None

    # Always auto-generate config if no config is provided
    if config is None:
        # Automatically generate config from template
        logger.debug("🐛 Generating config from template")

        generated_config_path = generate_config_from_template(
            cores, effective_spec_root, tune
        )

        if generated_config_path:
            logger.debug(f"🐛 Config generated: {generated_config_path}")
        else:
            logger.warning("⚠️  Failed to generate config file from template")

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

    # Convert simple benchmark names to full SPEC names
    if not speed and not rate:
        # Auto-detect preference from existing benchmarks
        prefer_speed, prefer_rate = detect_suite_preference(benchmarks)
    else:
        prefer_speed, prefer_rate = speed, rate

    logger.debug(f"🐛 Converting benchmarks: {benchmarks}")
    converted_benchmarks = convert_benchmark_names(
        benchmarks, prefer_speed, prefer_rate
    )
    logger.debug(f"🐛 Converted benchmarks: {converted_benchmarks}")

    if dry_run and converted_benchmarks != benchmarks:
        typer.echo(f"Converted benchmark names: {benchmarks} -> {converted_benchmarks}")

    # Handle cores argument - intelligently set copies or threads based on benchmark type
    effective_copies = copies
    effective_threads = threads

    if cores is not None:
        # Detect if we're running rate or speed benchmarks
        is_rate_benchmark = any(
            bench
            for bench in converted_benchmarks
            if bench.endswith("_r") or bench in ["intrate", "fprate", "specrate"]
        )
        is_speed_benchmark = any(
            bench
            for bench in converted_benchmarks
            if bench.endswith("_s") or bench in ["intspeed", "fpspeed", "specspeed"]
        )

        if is_rate_benchmark and not is_speed_benchmark:
            # Pure rate benchmarks - use cores as copies
            effective_copies = cores
            if dry_run:
                typer.echo(f"Using --cores={cores} as copies for rate benchmarks")
        elif is_speed_benchmark and not is_rate_benchmark:
            # Pure speed benchmarks - use cores as threads
            effective_threads = cores
            if dry_run:
                typer.echo(f"Using --cores={cores} as threads for speed benchmarks")
        elif is_rate_benchmark and is_speed_benchmark:
            # Mixed benchmarks - warn user to be specific
            typer.echo(
                "Warning: Mixed rate and speed benchmarks detected. "
                "--cores will be used as both copies and threads. "
                "Consider using --copies and --threads explicitly.",
                err=True,
            )
            effective_copies = cores
            effective_threads = cores
        else:
            # Neither rate nor speed detected, default to threads
            effective_threads = cores
            if dry_run:
                typer.echo(f"Using --cores={cores} as threads (default behavior)")

    # Build the runcpu command
    # (spec_root was already resolved earlier for config generation)
    logger.debug("🐛 Building runcpu command")

    cmd = build_runcpu_command(
        action="run",
        benchmarks=converted_benchmarks,
        config=effective_config,
        tune=tune,
        spec_root=effective_spec_root,
        verbose=verbose,
        rebuild=rebuild,
        parallel_test=parallel_test,
        ignore_errors=ignore_errors,
        size=size,
        copies=effective_copies,
        threads=effective_threads,
        iterations=iterations,
        reportable=reportable,
        noreportable=noreportable,
        output_formats=output_formats,
    )

    logger.debug(f"🐛 Built runcpu command: {' '.join(cmd)}")

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

    # Determine if we should use rich output and parse results
    # Rich output is default unless explicitly disabled or verbose mode
    use_rich = rich_output or (not verbose and not parse_results)
    should_parse = parse_results or use_rich or json_output is not None

    # Hide logs by default unless verbose mode is enabled
    # Also respect the deprecated --quiet flag for backward compatibility
    hide_logs = not verbose or quiet

    # Initialize EvalSync worker if sync is enabled
    evalsync_worker = None
    if sync:
        evalsync_worker = create_evalsync_worker(verbose=verbose)
        if not evalsync_worker:
            typer.echo(
                "Warning: EvalSync integration requested but evalsync is not available",
                err=True,
            )

    try:
        # Send ready signal - tasks are compiled and ready to run
        if evalsync_worker:
            logger.debug("🐛 Sending ready signal to EvalSync")
            evalsync_worker.ready()
            logger.debug("🐛 Waiting for start signal from EvalSync")
            evalsync_worker.wait_for_start()

        # Execute the command with optional result parsing and time tracking
        logger.debug("🐛 Executing runcpu command")
        start_time = time.time()
        result_info = execute_runcpu(
            cmd,
            verbose=verbose,
            parse_results=should_parse,
            spec_root=effective_spec_root,
            hide_logs=hide_logs,
            show_progress=hide_logs,
            numa_node=numa_node,
            cpu_cores=cpu_cores,
            numa_memory=numa_memory,
        )
        end_time = time.time()
        total_elapsed = end_time - start_time
        logger.debug(f"🐛 Execution completed in {total_elapsed:.2f}s")

    except Exception:
        # Clean up EvalSync worker on error
        if evalsync_worker:
            evalsync_worker.cleanup()
        raise

    # Display parsed results if available
    if result_info:
        # Enrich result_info with detailed benchmark data
        enriched_results = dict(result_info)
        if result_info.get("result_files"):
            all_benchmark_results = {}

            # Prioritize RSF files for parsing (most accurate and complete data)
            rsf_files = [
                f for f in result_info["result_files"] if f["path"].endswith(".rsf")
            ]
            other_files = [
                f for f in result_info["result_files"] if not f["path"].endswith(".rsf")
            ]

            # Process RSF files first (they have the most complete data)
            for file_info in rsf_files:
                detailed_results = read_result_file(
                    file_info["path"], effective_spec_root
                )
                if detailed_results and detailed_results.get("benchmark_results"):
                    all_benchmark_results.update(detailed_results["benchmark_results"])

            # Only process other files if no RSF data was found
            if not all_benchmark_results:
                for file_info in other_files:
                    detailed_results = read_result_file(
                        file_info["path"], effective_spec_root
                    )
                    if detailed_results and detailed_results.get("benchmark_results"):
                        all_benchmark_results.update(
                            detailed_results["benchmark_results"]
                        )

            if all_benchmark_results:
                enriched_results["benchmark_results"] = all_benchmark_results

        # Add timing information
        enriched_results["execution_time"] = total_elapsed

        # Display results based on output preference
        if use_rich:
            display_results_with_rich(enriched_results, show_timing=True)
        elif parse_results:
            # Legacy text display for backward compatibility
            typer.echo("\n" + "=" * 60)
            typer.echo("RESULT PARSING SUMMARY")
            typer.echo("=" * 60)

            if enriched_results.get("scores"):
                typer.echo("\n📊 Overall Scores:")
                for metric, score in enriched_results["scores"].items():
                    typer.echo(f"  {metric}: {score}")

            if enriched_results.get("metrics"):
                typer.echo("\n📈 Suite Metrics:")
                for metric, score in enriched_results["metrics"].items():
                    typer.echo(f"  {metric}: {score}")

            if enriched_results.get("result_files"):
                typer.echo("\n📄 Result Files Found:")
                for file_info in enriched_results["result_files"]:
                    typer.echo(f"  {file_info['path']} ({file_info['type']})")

            if enriched_results.get("benchmark_results"):
                typer.echo("\n🔬 Individual Benchmark Results:")
                for benchmark, data in enriched_results["benchmark_results"].items():
                    if "ratio" in data and "time" in data:
                        typer.echo(
                            f"  {benchmark}: ratio={data['ratio']}, time={data['time']}s"
                        )
                    elif "ratio" in data:
                        typer.echo(f"  {benchmark}: ratio={data['ratio']}")

            if enriched_results.get("log_file"):
                typer.echo(f"\n📝 Log File: {enriched_results['log_file']}")

            if enriched_results.get("execution_time"):
                elapsed_time = enriched_results["execution_time"]
                minutes = int(elapsed_time // 60)
                seconds = elapsed_time % 60

                if minutes > 0:
                    time_str = f"{minutes}m {seconds:.1f}s"
                else:
                    time_str = f"{seconds:.1f}s"

                typer.echo(f"\n⏱️  Execution Time: {time_str}")

        # Save to JSON if requested
        if json_output is not None:
            json_path = save_results_to_json(
                enriched_results,
                output_file=json_output if json_output else None,
                benchmarks=converted_benchmarks,
                config=effective_config,
            )
            if use_rich:
                console = Console()
                console.print(
                    Panel(
                        f"[green]💾 Results saved to:[/green] [cyan]{json_path}[/cyan]",
                        border_style="green",
                    )
                )
            else:
                typer.echo(f"\n💾 Results saved to: {json_path}")

    # Clean up generated config file after execution
    if generated_config_path:
        with contextlib.suppress(OSError):
            Path(generated_config_path).unlink()

    # Clean up EvalSync worker
    if evalsync_worker:
        evalsync_worker.cleanup()
