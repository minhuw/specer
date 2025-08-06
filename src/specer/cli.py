"""CLI interface for SPEC CPU 2017 benchmark wrapper."""

import subprocess
import tempfile
from pathlib import Path
from typing import Annotated, Any, Optional

import typer

app = typer.Typer(
    name="specer",
    help="A CLI wrapper for SPEC CPU 2017 benchmark suite",
    add_completion=False,
)

# Mapping of simple benchmark names to their SPEC CPU 2017 identifiers
# Format: "simple_name": ("speed_version", "rate_version")
BENCHMARK_MAPPING: dict[str, tuple[str, str]] = {
    "perlbench": ("600.perlbench_s", "500.perlbench_r"),
    "gcc": ("602.gcc_s", "502.gcc_r"),
    "mcf": ("605.mcf_s", "505.mcf_r"),
    "omnetpp": ("620.omnetpp_s", "520.omnetpp_r"),
    "xalancbmk": ("623.xalancbmk_s", "523.xalancbmk_r"),
    "x264": ("625.x264_s", "525.x264_r"),
    "deepsjeng": ("631.deepsjeng_s", "531.deepsjeng_r"),
    "leela": ("641.leela_s", "541.leela_r"),
    "exchange2": ("648.exchange2_s", "548.exchange2_r"),
    "xz": ("657.xz_s", "557.xz_r"),
    "bwaves": ("603.bwaves_s", "503.bwaves_r"),
    "cactuBSSN": ("607.cactuBSSN_s", "507.cactuBSSN_r"),
    "lbm": ("619.lbm_s", "519.lbm_r"),
    "wrf": ("621.wrf_s", "521.wrf_r"),
    "cam4": ("627.cam4_s", "527.cam4_r"),
    "pop2": ("628.pop2_s", "528.pop2_r"),
    "imagick": ("638.imagick_s", "538.imagick_r"),
    "nab": ("644.nab_s", "544.nab_r"),
    "fotonik3d": ("649.fotonik3d_s", "549.fotonik3d_r"),
    "roms": ("654.roms_s", "554.roms_r"),
}


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        from specer import __version__

        typer.echo(f"specer {__version__}")
        raise typer.Exit()


def _validate_and_get_spec_root(spec_root: Optional[Path]) -> Path:
    """Validate spec_root argument and return effective path.

    Args:
        spec_root: The spec_root argument from command line

    Returns:
        Effective spec root path

    Raises:
        typer.Exit: If spec_root is None and SPEC_PATH environment variable is not set
    """
    if spec_root is None:
        # Try to get from SPEC_PATH environment variable
        import os

        env_spec_path = os.environ.get("SPEC_PATH")
        if env_spec_path:
            return Path(env_spec_path)

        typer.echo("Error: --spec-root is required", err=True)
        typer.echo(
            "Please specify the path to your SPEC CPU 2017 installation:", err=True
        )
        typer.echo("  specer <command> --spec-root /path/to/spec2017", err=True)
        typer.echo("Or set the SPEC_PATH environment variable:", err=True)
        typer.echo("  export SPEC_PATH=/path/to/spec2017", err=True)
        raise typer.Exit(1)

    return spec_root


def _convert_benchmark_names(
    benchmarks: list[str], prefer_speed: bool = False, prefer_rate: bool = False
) -> list[str]:
    """Convert simple benchmark names to full SPEC CPU 2017 names.

    Args:
        benchmarks: List of benchmark names (simple or full SPEC names)
        prefer_speed: If True, prefer speed versions for ambiguous names
        prefer_rate: If True, prefer rate versions for ambiguous names

    Returns:
        List of converted benchmark names

    Examples:
        _convert_benchmark_names(["gcc"], prefer_speed=True) -> ["602.gcc_s"]
        _convert_benchmark_names(["gcc"], prefer_rate=True) -> ["502.gcc_r"]
        _convert_benchmark_names(["602.gcc_s"]) -> ["602.gcc_s"]  # unchanged
    """
    converted = []

    for benchmark in benchmarks:
        # If it's already a full SPEC name (contains a dot and number), keep it as-is
        if "." in benchmark and any(char.isdigit() for char in benchmark.split(".")[0]):
            converted.append(benchmark)
            continue

        # Handle standard suite names
        if benchmark.lower() in [
            "intspeed",
            "fpspeed",
            "specspeed",
            "intrate",
            "fprate",
            "specrate",
            "all",
        ]:
            converted.append(benchmark)
            continue

        # Check if it's a simple benchmark name
        simple_name = benchmark.lower()
        if simple_name in BENCHMARK_MAPPING:
            speed_version, rate_version = BENCHMARK_MAPPING[simple_name]

            if prefer_speed:
                converted.append(speed_version)
            elif prefer_rate:
                converted.append(rate_version)
            else:
                # Default behavior: try to infer from existing pattern or use speed
                # For now, default to speed version
                converted.append(speed_version)
        else:
            # Unknown name, keep as-is and let runcpu handle the error
            converted.append(benchmark)

    return converted


def _detect_suite_preference(benchmarks: list[str]) -> tuple[bool, bool]:
    """Detect if benchmarks suggest speed or rate preference.

    Returns:
        Tuple of (prefer_speed, prefer_rate)
    """
    speed_count = 0
    rate_count = 0

    for benchmark in benchmarks:
        if "_s" in benchmark or "speed" in benchmark.lower():
            speed_count += 1
        elif "_r" in benchmark or "rate" in benchmark.lower():
            rate_count += 1

    return speed_count > rate_count, rate_count > speed_count


def _detect_gcc_version() -> Optional[int]:
    """Detect the GCC version using 'which gcc' and '--version'.

    Returns:
        The major version number of GCC, or None if detection fails
    """
    try:
        import subprocess

        # First check if gcc is available
        which_result = subprocess.run(
            ["which", "gcc"], capture_output=True, text=True, timeout=5
        )

        if which_result.returncode != 0:
            return None

        # Get GCC version
        version_result = subprocess.run(
            ["gcc", "--version"], capture_output=True, text=True, timeout=5
        )

        if version_result.returncode != 0:
            return None

        # Parse version from output like "gcc (GCC) 11.2.0"
        # or "gcc (Ubuntu 9.4.0-1ubuntu1~20.04.1) 9.4.0"
        version_output = version_result.stdout.strip()

        # Look for patterns like "gcc (...) X.Y.Z" or "gcc (GCC) X.Y.Z"
        import re

        match = re.search(r"gcc.*?(\d+)\.(\d+)\.(\d+)", version_output, re.IGNORECASE)
        if match:
            major_version = int(match.group(1))
            return major_version

        return None

    except (
        subprocess.TimeoutExpired,
        subprocess.SubprocessError,
        ValueError,
        AttributeError,
    ):
        return None


def _generate_config_from_template(
    cores: Optional[int] = None,
    spec_root: Optional[Path] = None,
    tune: Optional[str] = None,
) -> Optional[str]:
    """Generate a SPEC CPU 2017 config file from SPEC's official template.

    Uses the Example-gcc-linux-x86.cfg template from the SPEC installation
    and modifies the copies value for rate benchmarks and tune setting.

    Args:
        cores: Number of cores to use (for copies in rate benchmarks)
        spec_root: Path to SPEC installation directory
        tune: Tuning level (base, peak, all)

    Returns:
        Path to the generated config file, or None if template not found
    """
    try:
        # Find SPEC installation path
        if spec_root:
            spec_path = str(spec_root)
        else:
            import os

            spec_path_env = os.environ.get("SPEC_PATH")
            if not spec_path_env:
                return None
            spec_path = spec_path_env

        # Path to SPEC's official template
        template_path = Path(spec_path) / "config" / "Example-gcc-linux-x86.cfg"

        if not template_path.exists():
            return None

        # Read the template content
        template_content = template_path.read_text()

        # Update label to "specer"
        template_content = template_content.replace(
            '%   define label "mytest"           # (2)      Use a label meaningful to *you*.',
            '%   define label "specer"           # (2)      Use a label meaningful to *you*.',
        )

        # Auto-detect GCC version and uncomment GCCge10 if needed
        gcc_version = _detect_gcc_version()
        if gcc_version and gcc_version >= 10:
            # Uncomment the GCCge10 define for GCC 10+
            template_content = template_content.replace(
                "#%define GCCge10  # EDIT: remove the '#' from column 1 if using GCC 10 or later",
                "%define GCCge10  # EDIT: remove the '#' from column 1 if using GCC 10 or later (auto-detected)",
            )

        # Update tune setting based on CLI parameter
        if tune is not None:
            # Map tune values and update the tune line
            tune_mapping = {"base": "base", "peak": "peak", "all": "base,peak"}
            tune_value = tune_mapping.get(tune, tune)  # Use mapping or original value
            template_content = template_content.replace(
                'tune                 = base,peak  # EDIT if needed: set to "base" for old GCC.',
                f'tune                 = {tune_value}  # EDIT if needed: set to "base" for old GCC. (auto-set)',
            )

        # Modify the copies value for rate benchmarks
        # Find the line with "copies = 1" and replace it
        if cores is not None:
            # Replace the copies line in the intrate,fprate section
            template_content = template_content.replace(
                "   copies           = 1   # EDIT to change number of copies (see above)",
                f"   copies           = {cores}   # EDIT to change number of copies (see above)",
            )
        else:
            # Default to a reasonable number if not specified
            import os

            default_cores = os.cpu_count() or 4
            template_content = template_content.replace(
                "   copies           = 1   # EDIT to change number of copies (see above)",
                f"   copies           = {default_cores}   # EDIT to change number of copies (see above)",
            )

        # Create a temporary config file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".cfg", prefix="specer_generated_", delete=False
        ) as temp_file:
            temp_file.write(template_content)
            temp_file_name = temp_file.name

        return temp_file_name

    except Exception:
        # If anything goes wrong, return None
        return None


@app.callback()  # type: ignore[misc]
def main(
    _version: Annotated[
        Optional[bool],
        typer.Option(
            "--version",
            "-V",
            callback=version_callback,
            help="Show version and exit",
        ),
    ] = None,
) -> None:
    """A CLI wrapper for SPEC CPU 2017 benchmark suite.

    You can set the SPEC CPU 2017 installation directory using the --spec-root option
    on individual commands or by setting the SPEC_ROOT environment variable.
    """
    pass


@app.command()  # type: ignore[misc]
def compile(
    benchmarks: Annotated[
        list[str],
        typer.Argument(
            help="Benchmarks to compile (e.g., 519.lbm_r, 500.perlbench_r, intspeed, fprate, all)"
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
        Optional[Path],
        typer.Option(
            "--spec-root",
            "-s",
            help="SPEC CPU 2017 installation directory (required)",
        ),
    ] = None,
    tune: Annotated[
        Optional[str],
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
        Optional[int],
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
    _cores: Annotated[
        Optional[int],
        typer.Option(
            "--cores",
            help="Number of CPU cores to use for compilation (parallel build processes)",
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
    """
    # Validate mutually exclusive options
    if speed and rate:
        typer.echo("Error: --speed and --rate options are mutually exclusive", err=True)
        raise typer.Exit(1)

    # Convert simple benchmark names to full SPEC names
    if not speed and not rate:
        # Auto-detect preference from existing benchmarks
        prefer_speed, prefer_rate = _detect_suite_preference(benchmarks)
    else:
        prefer_speed, prefer_rate = speed, rate

    converted_benchmarks = _convert_benchmark_names(
        benchmarks, prefer_speed, prefer_rate
    )

    if dry_run and converted_benchmarks != benchmarks:
        typer.echo(f"Converted benchmark names: {benchmarks} -> {converted_benchmarks}")

    # Resolve the effective spec_root
    effective_spec_root = _validate_and_get_spec_root(spec_root)

    # Build the runcpu command
    cmd = _build_runcpu_command(
        action="build",
        benchmarks=converted_benchmarks,
        config=config,
        tune=tune,
        spec_root=effective_spec_root,
        verbose=verbose,
        rebuild=rebuild,
        parallel_test=parallel_test,
        ignore_errors=ignore_errors,
    )

    if dry_run:
        typer.echo(f"Would execute: {' '.join(cmd)}")
        return

    # Execute the command
    _execute_runcpu(cmd, verbose=verbose)


@app.command()  # type: ignore[misc]
def run(
    benchmarks: Annotated[
        list[str],
        typer.Argument(
            help="Benchmarks to run (e.g., 519.lbm_r, 500.perlbench_r, intspeed, fprate, all)"
        ),
    ],
    config: Annotated[
        Optional[str],
        typer.Option(
            "--config",
            "-c",
            help="Configuration file to use (auto-generated from template if not specified)",
        ),
    ] = None,
    tune: Annotated[
        Optional[str],
        typer.Option(
            "--tune",
            "-t",
            help="Tuning level (base, peak, all)",
        ),
    ] = "base",
    size: Annotated[
        Optional[str],
        typer.Option(
            "--size",
            "-i",
            help="Workload size (test, train, ref)",
        ),
    ] = "ref",
    copies: Annotated[
        Optional[int],
        typer.Option(
            "--copies",
            help="Number of copies for rate benchmarks",
        ),
    ] = None,
    threads: Annotated[
        Optional[int],
        typer.Option(
            "--threads",
            help="Number of threads for speed benchmarks",
        ),
    ] = None,
    iterations: Annotated[
        Optional[int],
        typer.Option(
            "--iterations",
            help="Number of iterations (2 or 3 for reportable runs)",
        ),
    ] = None,
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
        Optional[int],
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
        Optional[int],
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
) -> None:
    """Run SPEC CPU 2017 benchmarks.

    This command wraps the 'runcpu --action=run' functionality for running benchmarks.
    Config files are automatically generated from template when not specified.

    Examples:
        specer run 519.lbm_r --config myconfig.cfg     # Use specific config
        specer run gcc --speed --dry-run               # Auto-generate config
        specer run intrate --cores 16 --dry-run        # Auto-generate with 16 cores
        specer run gcc --cores 8 --speed --reportable  # Auto-generate and run
        specer run intrate --threads 8 --copies 4      # Auto-generate with custom settings
    """
    # Validate mutually exclusive options
    if speed and rate:
        typer.echo("Error: --speed and --rate options are mutually exclusive", err=True)
        raise typer.Exit(1)

    # Resolve the effective spec_root early since it's needed for config generation
    effective_spec_root = _validate_and_get_spec_root(spec_root)

    # Handle config generation and validation
    effective_config = config
    generated_config_path = None

    # Always auto-generate config if no config is provided
    if config is None:
        # Automatically generate config from template
        generated_config_path = _generate_config_from_template(
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

    # Convert simple benchmark names to full SPEC names
    if not speed and not rate:
        # Auto-detect preference from existing benchmarks
        prefer_speed, prefer_rate = _detect_suite_preference(benchmarks)
    else:
        prefer_speed, prefer_rate = speed, rate

    converted_benchmarks = _convert_benchmark_names(
        benchmarks, prefer_speed, prefer_rate
    )

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
    cmd = _build_runcpu_command(
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
    )

    if dry_run:
        typer.echo(f"Would execute: {' '.join(cmd)}")
        # Clean up generated config file if in dry-run mode
        if generated_config_path:
            Path(generated_config_path).unlink()
        return

    # Execute the command with optional result parsing
    result_info = _execute_runcpu(
        cmd, verbose=verbose, parse_results=parse_results, spec_root=effective_spec_root
    )

    # Display parsed results if available
    if result_info and parse_results:
        typer.echo("\n" + "=" * 60)
        typer.echo("RESULT PARSING SUMMARY")
        typer.echo("=" * 60)

        if result_info.get("scores"):
            typer.echo("\n📊 Overall Scores:")
            for metric, score in result_info["scores"].items():
                typer.echo(f"  {metric}: {score}")

        if result_info.get("metrics"):
            typer.echo("\n📈 Suite Metrics:")
            for metric, score in result_info["metrics"].items():
                typer.echo(f"  {metric}: {score}")

        if result_info.get("result_files"):
            typer.echo("\n📄 Result Files Found:")
            for file_info in result_info["result_files"]:
                typer.echo(f"  {file_info['path']} ({file_info['type']})")

                # Try to parse the result file for detailed scores
                detailed_results = _read_result_file(
                    file_info["path"], effective_spec_root
                )
                if detailed_results:
                    if detailed_results.get("benchmark_results"):
                        typer.echo("    Individual benchmark results:")
                        for benchmark, data in detailed_results[
                            "benchmark_results"
                        ].items():
                            if "ratio" in data and "time" in data:
                                typer.echo(
                                    f"      {benchmark}: ratio={data['ratio']}, time={data['time']}s"
                                )
                            elif "ratio" in data:
                                typer.echo(f"      {benchmark}: ratio={data['ratio']}")

        if result_info.get("log_file"):
            typer.echo(f"\n📝 Log File: {result_info['log_file']}")

    # Clean up generated config file after execution
    if generated_config_path:
        import contextlib

        with contextlib.suppress(OSError):
            Path(generated_config_path).unlink()


@app.command()  # type: ignore[misc]
def setup(
    benchmarks: Annotated[
        list[str],
        typer.Argument(
            help="Benchmarks to setup (e.g., 519.lbm_r, 500.perlbench_r, intspeed, fprate, all)"
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
    tune: Annotated[
        Optional[str],
        typer.Option(
            "--tune",
            "-t",
            help="Tuning level (base, peak, all)",
        ),
    ] = "base",
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
    """Setup SPEC CPU 2017 benchmarks (extract and prepare source code).

    Examples:
        specer setup 519.lbm_r --config myconfig.cfg
        specer setup gcc --config myconfig.cfg --speed
        specer setup intspeed --config myconfig.cfg
    """
    # Validate mutually exclusive options
    if speed and rate:
        typer.echo("Error: --speed and --rate options are mutually exclusive", err=True)
        raise typer.Exit(1)

    # Convert simple benchmark names to full SPEC names
    if not speed and not rate:
        # Auto-detect preference from existing benchmarks
        prefer_speed, prefer_rate = _detect_suite_preference(benchmarks)
    else:
        prefer_speed, prefer_rate = speed, rate

    converted_benchmarks = _convert_benchmark_names(
        benchmarks, prefer_speed, prefer_rate
    )

    if dry_run and converted_benchmarks != benchmarks:
        typer.echo(f"Converted benchmark names: {benchmarks} -> {converted_benchmarks}")

    # Resolve the effective spec_root
    effective_spec_root = _validate_and_get_spec_root(spec_root)

    # Build the runcpu command
    cmd = _build_runcpu_command(
        action="setup",
        benchmarks=converted_benchmarks,
        config=config,
        tune=tune,
        spec_root=effective_spec_root,
        verbose=verbose,
    )

    if dry_run:
        typer.echo(f"Would execute: {' '.join(cmd)}")
        return

    # Execute the command
    _execute_runcpu(cmd, verbose=verbose)


@app.command()  # type: ignore[misc]
def clean(
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
        prefer_speed, prefer_rate = _detect_suite_preference(benchmarks)
    else:
        prefer_speed, prefer_rate = speed, rate

    converted_benchmarks = _convert_benchmark_names(
        benchmarks, prefer_speed, prefer_rate
    )

    if dry_run and converted_benchmarks != benchmarks:
        typer.echo(f"Converted benchmark names: {benchmarks} -> {converted_benchmarks}")

    # Resolve the effective spec_root
    effective_spec_root = _validate_and_get_spec_root(spec_root)

    # Build the runcpu command
    cmd = _build_runcpu_command(
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
    _execute_runcpu(cmd, verbose=verbose)


@app.command()  # type: ignore[misc]
def update(
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
    effective_spec_root = _validate_and_get_spec_root(spec_root)

    # Build the runcpu command
    cmd = _build_runcpu_command(
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
    _execute_runcpu(cmd, verbose=verbose)


def _build_runcpu_command(
    action: str,
    benchmarks: list[str],
    config: str,
    tune: Optional[str] = None,
    spec_root: Optional[Path] = None,
    verbose: bool = False,
    rebuild: bool = False,
    parallel_test: Optional[int] = None,
    ignore_errors: bool = False,
    size: Optional[str] = None,
    copies: Optional[int] = None,
    threads: Optional[int] = None,
    iterations: Optional[int] = None,
    reportable: bool = False,
    noreportable: bool = False,
) -> list[str]:
    """Build the runcpu command with the given parameters."""
    # Start with the base command
    if spec_root:
        runcpu_path = spec_root / "bin" / "runcpu"
        if not runcpu_path.exists():
            typer.echo(f"Error: runcpu not found at {runcpu_path}", err=True)
            raise typer.Exit(1)
        cmd = [str(runcpu_path)]
    else:
        # Assume runcpu is in PATH
        cmd = ["runcpu"]

    # Handle update action specially
    if action == "update":
        cmd.append("--update")
    else:
        # Add action and config for normal commands
        cmd.extend(["--action", action])

        # Add config
        cmd.extend(["--config", config])

    # Add tuning level
    if tune:
        cmd.extend(["--tune", tune])

    # Add size (for run command)
    if size:
        cmd.extend(["--size", size])

    # Add copies (for rate benchmarks)
    if copies is not None:
        cmd.extend(["--copies", str(copies)])

    # Add threads (for speed benchmarks)
    if threads is not None:
        cmd.extend(["--threads", str(threads)])

    # Add iterations
    if iterations is not None:
        cmd.extend(["--iterations", str(iterations)])

    # Add reportable/noreportable
    if reportable:
        cmd.append("--reportable")
    elif noreportable:
        cmd.append("--noreportable")

    # Add verbose
    if verbose:
        cmd.append("--verbose")

    # Add rebuild
    if rebuild:
        cmd.append("--rebuild")

    # Add parallel test
    if parallel_test is not None:
        cmd.extend(["--parallel_test", str(parallel_test)])

    # Add ignore errors
    if ignore_errors:
        cmd.append("--ignore_errors")

    # Add benchmarks (skip for update action)
    if action != "update":
        cmd.extend(benchmarks)

    return cmd


def _parse_result_files(output: str, _spec_root: Path) -> Optional[dict[str, Any]]:
    """Parse runcpu output to find result files and extract scores.

    Args:
        output: The stdout/stderr output from runcpu command
        spec_root: Path to SPEC installation directory

    Returns:
        Dictionary containing result information, or None if parsing fails
    """
    import re

    result_info: dict[str, Any] = {
        "result_files": [],
        "scores": {},
        "metrics": {},
        "log_file": None,
    }
    # Type hints for mypy
    result_files: list[dict[str, str]] = result_info["result_files"]
    scores: dict[str, float] = result_info["scores"]
    metrics: dict[str, float] = result_info["metrics"]

    # Common patterns to find result files and scores
    patterns = {
        "result_file": r"The result.*?is in (.*?)(?:\s|$)",
        "score_line": r"Est\. (SPEC\w+\d+_\w+_\w+)\s*=\s*([\d.]+)",
        "metric_line": r"Est\. (SPEC\w+\d+_\w+)\s*=\s*([\d.]+)",
        "log_file": r"The log for this run is in (.*?)(?:\s|$)",
        "report_location": r"(?:format to|reports are in) (.*?)(?:\s|$)",
        "rawfile": r".*\.rsf",
        "formatted_result": r".*\.(html|pdf|txt|ps)$",
    }

    lines = output.split("\n")

    for line in lines:
        line = line.strip()

        # Look for result file paths
        for pattern_name, pattern in patterns.items():
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                if pattern_name == "result_file" or pattern_name == "report_location":
                    file_path = match.group(1).strip()
                    if file_path and file_path not in [
                        item.get("path") for item in result_files
                    ]:
                        result_files.append({"path": file_path, "type": "result"})
                elif pattern_name == "score_line":
                    metric_name = match.group(1)
                    score = float(match.group(2))
                    scores[metric_name] = score
                elif pattern_name == "metric_line":
                    metric_name = match.group(1)
                    score = float(match.group(2))
                    metrics[metric_name] = score
                elif pattern_name == "log_file":
                    result_info["log_file"] = match.group(1).strip()

        # Look for lines that mention specific result files
        if any(ext in line.lower() for ext in [".rsf", ".html", ".pdf", ".txt", ".ps"]):
            # Extract potential file paths
            words = line.split()
            for word in words:
                if any(
                    word.endswith(ext)
                    for ext in [".rsf", ".html", ".pdf", ".txt", ".ps"]
                ):
                    if word not in [item.get("path") for item in result_files]:
                        result_files.append({"path": word, "type": "result_file"})

    return (
        result_info
        if result_info["result_files"]
        or result_info["scores"]
        or result_info["log_file"]
        else None
    )


def _read_result_file(file_path: str, spec_root: Path) -> Optional[dict[str, Any]]:
    """Read and parse a SPEC result file to extract scores.

    Args:
        file_path: Path to the result file
        spec_root: Path to SPEC installation directory

    Returns:
        Dictionary containing extracted scores and metrics
    """
    import re
    from pathlib import Path as PathLib

    # Convert relative paths to absolute paths
    if not file_path.startswith("/"):
        # Try common locations for result files
        possible_paths = [
            spec_root / file_path,
            spec_root / "result" / file_path,
            spec_root / "result" / PathLib(file_path).name,
        ]

        actual_path = None
        for path in possible_paths:
            if path.exists():
                actual_path = path
                break

        if not actual_path:
            return None
        file_path = str(actual_path)

    result_data: dict[str, Any] = {
        "file_path": file_path,
        "scores": {},
        "metrics": {},
        "benchmark_results": {},
    }
    # Type hints for mypy
    scores_data: dict[str, float] = result_data["scores"]
    metrics_data: dict[str, float] = result_data["metrics"]
    benchmark_results: dict[str, dict[str, float]] = result_data["benchmark_results"]

    try:
        with Path(file_path).open(encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # Patterns for different result file formats
        patterns = {
            # Overall suite scores
            "overall_score": r"Est\.\s+(SPEC\w+\d+_\w+_\w+)\s*=\s*([\d.]+)",
            "suite_metric": r"Est\.\s+(SPEC\w+\d+_\w+)\s*=\s*([\d.]+)",
            # Individual benchmark results (common in text and HTML)
            "benchmark_result": r"(\d+\.\w+(?:_[rs])?)\s+.*?(\d+(?:\.\d+)?)\s+.*?(\d+(?:\.\d+)?)",
            # Raw file patterns (if it's a .rsf file)
            "raw_result": r"spec\.(\w+)\.result\.(\w+):\s*([\d.]+)",
            "raw_ratio": r"spec\.(\w+)\.ratio:\s*([\d.]+)",
            "raw_time": r"spec\.(\w+)\.time:\s*([\d.]+)",
            # HTML table patterns
            "html_result": r"<td[^>]*>(\d+\.\w+(?:_[rs])?)</td>.*?<td[^>]*>([\d.]+)</td>",
        }

        for pattern_name, pattern in patterns.items():
            matches = re.findall(pattern, content, re.IGNORECASE | re.MULTILINE)

            for match in matches:
                if pattern_name in ["overall_score", "suite_metric"]:
                    metric_name = match[0]
                    score = float(match[1])
                    if "base" in metric_name or "peak" in metric_name:
                        scores_data[metric_name] = score
                    else:
                        metrics_data[metric_name] = score

                elif pattern_name == "benchmark_result":
                    benchmark = match[0]
                    try:
                        ratio = float(match[1])
                        time = float(match[2])
                        benchmark_results[benchmark] = {
                            "ratio": ratio,
                            "time": time,
                        }
                    except (ValueError, IndexError):
                        continue

                elif pattern_name in ["raw_result", "raw_ratio", "raw_time"]:
                    benchmark = match[0]
                    value = float(match[1])
                    if benchmark not in benchmark_results:
                        benchmark_results[benchmark] = {}

                    metric_type = pattern_name.split("_")[1]  # result, ratio, or time
                    benchmark_results[benchmark][metric_type] = value

        return result_data

    except Exception as e:
        typer.echo(f"Warning: Could not parse result file {file_path}: {e}", err=True)
        return None


def _execute_runcpu(
    cmd: list[str],
    verbose: bool = False,
    parse_results: bool = False,
    spec_root: Optional[Path] = None,
) -> Optional[dict[str, Any]]:
    """Execute the runcpu command and optionally parse results.

    Args:
        cmd: Command to execute
        verbose: Whether to show verbose output
        parse_results: Whether to parse output for result files and scores
        spec_root: Path to SPEC installation (needed for result parsing)

    Returns:
        Dictionary containing result information if parse_results=True, otherwise None
    """
    if verbose:
        typer.echo(f"Executing: {' '.join(cmd)}")

    try:
        if parse_results:
            # Capture output for parsing when parse_results is True
            result = subprocess.run(
                cmd,
                check=False,
                text=True,
                capture_output=True,
            )
            # Print output to terminal even when capturing
            if result.stdout:
                typer.echo(result.stdout)
            if result.stderr:
                typer.echo(result.stderr, err=True)
            output = result.stdout + result.stderr
        else:
            # Normal execution without capturing output
            result = subprocess.run(
                cmd,
                check=False,
                text=True,
                capture_output=False,
            )
            output = ""

        if result.returncode != 0:
            typer.echo(f"Command failed with exit code {result.returncode}", err=True)
            raise typer.Exit(result.returncode)

        # Parse results if requested and we have output to parse
        if parse_results and spec_root and output:
            parsed_results = _parse_result_files(output, spec_root)
            if parsed_results:
                return parsed_results

        return None

    except FileNotFoundError as err:
        typer.echo(
            "Error: 'runcpu' command not found. Please ensure SPEC CPU 2017 is installed "
            "and the 'runcpu' command is in your PATH, or use --spec-root to specify "
            "the SPEC installation directory.",
            err=True,
        )
        raise typer.Exit(1) from err
    except KeyboardInterrupt as err:
        typer.echo("\nOperation cancelled by user.", err=True)
        raise typer.Exit(130) from err


def cli_main() -> None:
    """Main entry point for the CLI."""
    app()


if __name__ == "__main__":
    cli_main()
