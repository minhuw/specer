"""Shared utility functions for specer CLI."""

import json
import os
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from specer.logging import logger

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


class ProcessResult:
    """Simple result object compatible with subprocess.run."""

    def __init__(self, returncode: int, stdout: str, stderr: str):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def validate_and_get_spec_root(spec_root: Path | None) -> Path:
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
        typer.echo("Please specify the path to your SPEC CPU 2017 installation:", err=True)
        typer.echo("  specer <command> --spec-root /path/to/spec2017", err=True)
        typer.echo("Or set the SPEC_PATH environment variable:", err=True)
        typer.echo("  export SPEC_PATH=/path/to/spec2017", err=True)
        raise typer.Exit(1)

    return spec_root


def convert_benchmark_names(benchmarks: list[str], prefer_speed: bool = False, prefer_rate: bool = False) -> list[str]:
    """Convert simple benchmark names to full SPEC CPU 2017 names.

    Args:
        benchmarks: List of benchmark names (simple or full SPEC names)
        prefer_speed: If True, prefer speed versions for ambiguous names
        prefer_rate: If True, prefer rate versions for ambiguous names

    Returns:
        List of converted benchmark names

    Examples:
        convert_benchmark_names(["gcc"], prefer_speed=True) -> ["602.gcc_s"]
        convert_benchmark_names(["gcc"], prefer_rate=True) -> ["502.gcc_r"]
        convert_benchmark_names(["602.gcc_s"]) -> ["602.gcc_s"]  # unchanged
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


def detect_suite_preference(benchmarks: list[str]) -> tuple[bool, bool]:
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


def detect_gcc_version() -> int | None:
    """Detect the GCC version using 'which gcc' and '--version'.

    Returns:
        The major version number of GCC, or None if detection fails
    """
    # First check if gcc is available
    which_result = subprocess.run(["which", "gcc"], capture_output=True, text=True, timeout=5)

    if which_result.returncode != 0:
        return None

    # Get GCC version
    version_result = subprocess.run(["gcc", "--version"], capture_output=True, text=True, timeout=5)

    if version_result.returncode != 0:
        return None

    # Parse version from output like "gcc (GCC) 11.2.0"
    # or "gcc (Ubuntu 9.4.0-1ubuntu1~20.04.1) 9.4.0"
    version_output = version_result.stdout.strip()

    # Look for patterns like "gcc (...) X.Y.Z" or "gcc (GCC) X.Y.Z"
    match = re.search(r"gcc.*?(\d+)\.(\d+)\.(\d+)", version_output, re.IGNORECASE)
    if match:
        major_version = int(match.group(1))
        return major_version

    return None


def detect_gcc_path() -> str | None:
    """Detect the GCC installation path using 'which gcc'.

    This function finds the GCC installation directory through a 4-step process:

    1. **Step 1**: Run 'which gcc' to find the location of the gcc binary
       - This uses the system's PATH to locate the gcc executable
       - Returns the full path to the gcc binary (e.g., /usr/bin/gcc)

    2. **Step 2**: Extract the binary path from the 'which' output
       - Strips whitespace and validates the path exists
       - Example: /nix/store/.../bin/gcc

    3. **Step 3**: Calculate the installation directory
       - Takes the parent directory (removes 'gcc'): /path/bin/
       - Takes the parent directory again (removes 'bin'): /path/
       - This gives us the root of the GCC installation

    4. **Step 4**: Return the final installation path
       - This path contains bin/, lib/, include/, etc. subdirectories
       - SPEC CPU uses this path to locate GCC libraries and headers

    Examples:
        /usr/bin/gcc -> /usr
        /opt/gcc-11.2.0/bin/gcc -> /opt/gcc-11.2.0
        /nix/store/...-gcc-wrapper/bin/gcc -> /nix/store/...-gcc-wrapper

    Returns:
        The parent directory of the GCC binary (without /bin), or None if detection fails
    """
    # First check if gcc is available
    which_result = subprocess.run(["which", "gcc"], capture_output=True, text=True, timeout=5)

    if which_result.returncode != 0:
        logger.debug("🐛 GCC not found in PATH")
        return None

    gcc_path = which_result.stdout.strip()
    if not gcc_path:
        logger.debug("🐛 'which gcc' returned empty result")
        return None

    logger.debug(f"🐛 Found GCC binary at: {gcc_path}")

    # Get the parent directory (remove /bin/gcc -> /bin -> parent)
    # For /usr/bin/gcc -> /usr
    # For /opt/rh/devtoolset-9/root/usr/bin/gcc -> /opt/rh/devtoolset-9/root/usr
    bin_dir = Path(gcc_path).parent
    gcc_dir = bin_dir.parent

    detected_path = str(gcc_dir)

    logger.debug(f"🐛 GCC installation path: {detected_path}")

    return detected_path


def detect_intel_oneapi_path() -> str | None:
    """Detect Intel oneAPI installation path and validate compiler availability.

    This function attempts to locate Intel oneAPI compilers (icx, icpx, ifx) and
    returns the oneAPI installation root directory.

    Detection strategy:
    1. Check for ICX (Intel C compiler) in PATH
    2. Check for ONEAPI_ROOT environment variable
    3. Check common installation paths (/opt/intel/oneapi)
    4. Validate that setvars.sh exists for environment setup

    Returns:
        Path to oneAPI installation root, or None if not found
    """

    # Strategy 1: Check if icx is available in PATH
    try:
        which_result = subprocess.run(["which", "icx"], capture_output=True, text=True, timeout=5)

        if which_result.returncode == 0:
            icx_path = which_result.stdout.strip()
            if icx_path:
                logger.info(f"✅ Found ICX binary at: {icx_path}")

                # Try to derive oneAPI root from icx path
                # /opt/intel/oneapi/compiler/latest/linux/bin/icx -> /opt/intel/oneapi
                current_path = Path(icx_path).parent

                for _ in range(6):  # Reasonable limit to avoid infinite loops
                    if current_path.name == "oneapi" and (current_path / "setvars.sh").exists():
                        logger.info(f"✅ Intel oneAPI root found via icx: {current_path}")
                        return str(current_path)
                    current_path = current_path.parent
                    if current_path == current_path.parent:  # Reached filesystem root
                        break
    except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
        logger.warning(f"⚠️  Error running 'which icx': {e}")

    # Strategy 2: Check ONEAPI_ROOT environment variable
    oneapi_root = os.environ.get("ONEAPI_ROOT")

    if oneapi_root:
        oneapi_path = Path(oneapi_root)
        setvars_path = oneapi_path / "setvars.sh"

        if oneapi_path.exists() and setvars_path.exists():
            logger.info(f"✅ Intel oneAPI root found via ONEAPI_ROOT: {oneapi_path}")
            return str(oneapi_path)

        # Strategy 3: Check common installation paths
    common_paths = [
        Path("/opt/intel/oneapi"),
        Path("/intel/oneapi"),
        Path.home() / "intel" / "oneapi",
    ]

    for path in common_paths:
        oneapi_path = path
        if oneapi_path.exists():
            setvars_path = oneapi_path / "setvars.sh"
            if setvars_path.exists():
                logger.info(f"✅ Intel oneAPI root found at: {oneapi_path}")
                return str(oneapi_path)

    # Strategy 4: Check current environment for Intel variables
    intel_env_vars = {k: v for k, v in os.environ.items() if "INTEL" in k.upper() or "ONEAPI" in k.upper()}
    if intel_env_vars:
        for var, value in intel_env_vars.items():
            logger.debug(f"🐛   {var}={value}")

    # Strategy 5: Check PATH for Intel directories
    path_env = os.environ.get("PATH", "")
    intel_paths = [p for p in path_env.split(":") if "intel" in p.lower() or "oneapi" in p.lower()]
    if intel_paths:
        for intel_path in intel_paths:
            # Try to find oneAPI root from these paths
            current_path = Path(intel_path)
            for _ in range(5):
                if current_path.name == "oneapi" and (current_path / "setvars.sh").exists():
                    logger.info(f"✅ Intel oneAPI root found via PATH analysis: {current_path}")
                    return str(current_path)
                current_path = current_path.parent
                if current_path == current_path.parent:
                    break

    logger.warning("⚠️  Intel oneAPI not found using any detection strategy")
    return None


def setup_intel_oneapi_environment(oneapi_path: str) -> dict[str, str]:
    """Set up Intel oneAPI environment variables by sourcing setvars.sh.

    Args:
        oneapi_path: Path to Intel oneAPI installation root

    Returns:
        Dictionary of environment variables to be set
    """
    logger.info(f"🔧 Setting up Intel oneAPI environment from: {oneapi_path}")
    env_vars: dict[str, str] = {}

    try:
        # Source the setvars.sh script and capture environment variables
        setvars_script = Path(oneapi_path) / "setvars.sh"
        logger.debug(f"🐛 Looking for setvars.sh at: {setvars_script}")

        if not setvars_script.exists():
            logger.warning(f"⚠️  setvars.sh not found at {setvars_script}")
            return env_vars

        logger.info(f"✅ Found setvars.sh at: {setvars_script}")

        # Run a shell command that sources setvars.sh and prints environment
        # Use --force to override existing vars, no config file needed
        cmd = f'source "{setvars_script}" --force 2>/dev/null && env'

        logger.debug(f"🐛 Running command: {cmd}")

        result = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=30)

        logger.debug(f"🐛 setvars.sh command return code: {result.returncode}")

        if result.returncode == 0:
            logger.info("✅ Successfully sourced setvars.sh")

            # Parse environment variables from output
            env_lines = result.stdout.strip().split("\n")
            logger.debug(f"🐛 Got {len(env_lines)} environment lines")

            for line in env_lines:
                if "=" in line:
                    key, value = line.split("=", 1)
                    # Capture Intel-related and important PATH variables
                    if any(
                        intel_prefix in key.upper()
                        for intel_prefix in [
                            "INTEL",
                            "ONEAPI",
                            "MKLROOT",
                            "TBBROOT",
                            "DAALROOT",
                            "IPPROOT",
                            "CPATH",
                            "LIBRARY_PATH",
                            "LD_LIBRARY_PATH",
                            "PATH",
                        ]
                    ):
                        env_vars[key] = value
                        logger.debug(f"🐛 Captured env var: {key}={value[:100]}...")

            logger.info(f"✅ Captured {len(env_vars)} Intel oneAPI environment variables")

            # Specifically log PATH to see if Intel compilers are included
            if "PATH" in env_vars:
                path_dirs = env_vars["PATH"].split(":")
                intel_path_dirs = [p for p in path_dirs if "intel" in p.lower() or "oneapi" in p.lower()]
                logger.info(f"🔍 Intel paths in PATH: {intel_path_dirs}")

        else:
            logger.warning(f"⚠️  Failed to source setvars.sh with return code {result.returncode}")
            logger.debug(f"🐛 setvars.sh stderr: {result.stderr}")

    except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
        logger.warning(f"⚠️  Error setting up Intel oneAPI environment: {e}")

    return env_vars


def validate_intel_oneapi_setup() -> bool:
    """Validate that Intel oneAPI compilers are properly set up and accessible.

    Returns:
        True if at least C/C++ compilers are available and working, False otherwise
    """
    logger.info("🔍 Validating Intel oneAPI compiler setup...")

    # Essential compilers (C and C++) - these must work
    essential_compilers = ["icx", "icpx"]
    # Optional compilers (Fortran) - nice to have but not required
    optional_compilers = ["ifx"]

    essential_working = 0

    for compiler in essential_compilers + optional_compilers:
        is_essential = compiler in essential_compilers
        logger.debug(f"🐛 Checking {compiler} compiler ({'essential' if is_essential else 'optional'})...")

        try:
            # First check if compiler is in PATH
            which_result = subprocess.run(["which", compiler], capture_output=True, text=True, timeout=5)

            logger.debug(f"🐛 'which {compiler}' return code: {which_result.returncode}")
            logger.debug(f"🐛 'which {compiler}' stdout: '{which_result.stdout.strip()}'")

            if which_result.returncode != 0:
                if is_essential:
                    logger.warning(f"⚠️  {compiler} not found in PATH")
                    return False
                else:
                    logger.info(f"ℹ️  {compiler} not found in PATH (optional)")
                    continue

            compiler_path = which_result.stdout.strip()
            logger.debug(f"🐛 {compiler} found at: {compiler_path}")

            # Check if the binary is executable
            if not (Path(compiler_path).is_file() and os.access(compiler_path, os.X_OK)):
                if is_essential:
                    logger.warning(f"⚠️  {compiler} found but not executable: {compiler_path}")
                    return False
                else:
                    logger.info(f"ℹ️  {compiler} found but not executable (optional): {compiler_path}")
                    continue

            # Test compiler version
            result = subprocess.run([compiler, "--version"], capture_output=True, text=True, timeout=10)

            logger.debug(f"🐛 '{compiler} --version' return code: {result.returncode}")
            logger.debug(f"🐛 '{compiler} --version' stdout: '{result.stdout.strip()[:100]}...'")

            if result.returncode != 0:
                if is_essential:
                    logger.warning(f"⚠️  {compiler} --version failed with return code {result.returncode}")
                    logger.debug(f"🐛 {compiler} stderr: {result.stderr.strip()}")
                    return False
                else:
                    logger.info(f"ℹ️  {compiler} --version failed (optional)")
                    continue

            logger.info(f"✅ {compiler} compiler validated successfully")
            if is_essential:
                essential_working += 1

        except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
            if is_essential:
                logger.warning(f"⚠️  Error checking {compiler}: {e}")
                return False
            else:
                logger.info(f"ℹ️  Error checking {compiler} (optional): {e}")

    if essential_working == len(essential_compilers):
        logger.info("✅ Intel oneAPI C/C++ compilers validated successfully")
        return True
    else:
        logger.warning(f"⚠️  Only {essential_working}/{len(essential_compilers)} essential Intel compilers working")
        return False


def detect_intel_compiler_version() -> str | None:
    """Detect Intel compiler version using icx --version.

    Returns:
        Version string (e.g., "2024.0.0"), or None if detection fails
    """
    try:
        version_result = subprocess.run(["icx", "--version"], capture_output=True, text=True, timeout=10)

        if version_result.returncode == 0:
            version_output = version_result.stdout.strip()
            # Parse version from output like "Intel(R) oneAPI DPC++/C++ Compiler 2024.0.0"
            import re

            version_match = re.search(r"(\d+\.\d+\.\d+)", version_output)
            if version_match:
                version = version_match.group(1)
                logger.debug(f"🐛 Intel compiler version: {version}")
                return version
    except (subprocess.TimeoutExpired, subprocess.SubprocessError):
        logger.debug("🐛 Could not detect Intel compiler version")

    return None


def generate_intel_config_additions(oneapi_path: str) -> list[str]:
    """Generate Intel oneAPI-specific configuration additions.

    Args:
        oneapi_path: Path to Intel oneAPI installation root

    Returns:
        List of config additions in 'section:key=value' format
    """
    logger.info(f"🔧 Generating Intel oneAPI config additions for: {oneapi_path}")
    config_additions = []

    # Find the actual compiler paths - try multiple possible locations
    possible_compiler_paths = [
        Path(oneapi_path) / "compiler" / "latest" / "bin",  # Direct bin (newer versions)
        Path(oneapi_path) / "compiler" / "latest" / "linux" / "bin",  # Linux-specific bin (older versions)
    ]

    # Also check for version-specific paths
    compiler_dir = Path(oneapi_path) / "compiler"
    if compiler_dir.exists():
        for version_dir in compiler_dir.iterdir():
            if version_dir.is_dir() and version_dir.name != "latest":
                possible_compiler_paths.extend(
                    [
                        version_dir / "bin",
                        version_dir / "linux" / "bin",
                    ]
                )

    # Find the first path that contains icx
    compiler_base_path = None
    for path in possible_compiler_paths:
        if (path / "icx").exists():
            compiler_base_path = path
            logger.debug(f"🐛 Found compiler path: {compiler_base_path}")
            break

    if not compiler_base_path:
        logger.warning("⚠️  Could not find Intel compilers in any expected location")
        # Fallback to the standard path
        compiler_base_path = Path(oneapi_path) / "compiler" / "latest" / "bin"

    # Check if compilers exist at expected locations
    icx_path = compiler_base_path / "icx"
    icpx_path = compiler_base_path / "icpx"
    ifx_path = compiler_base_path / "ifx"

    logger.debug("🐛 Looking for compilers at:")
    logger.debug(f"🐛   ICX: {icx_path} (exists: {icx_path.exists()})")
    logger.debug(f"🐛   ICPX: {icpx_path} (exists: {icpx_path.exists()})")
    logger.debug(f"🐛   IFX: {ifx_path} (exists: {ifx_path.exists()})")

    # Use full paths if available, otherwise use simple names (assuming PATH is set)
    cc_compiler = str(icx_path) if icx_path.exists() else "icx"
    cxx_compiler = str(icpx_path) if icpx_path.exists() else "icpx"

    # Handle Fortran compiler - it might not be installed
    if ifx_path.exists():
        fc_compiler = str(ifx_path)
        logger.info(f"🔧 Using compilers: CC={cc_compiler}, CXX={cxx_compiler}, FC={fc_compiler}")
    else:
        fc_compiler = None
        logger.warning("⚠️  Fortran compiler (ifx) not found, skipping Fortran configuration")
        logger.info(f"🔧 Using compilers: CC={cc_compiler}, CXX={cxx_compiler}")

    # Set Intel compilers for all benchmark suites
    suites = ["intrate", "intspeed", "fprate", "fpspeed"]

    # Get Intel oneAPI environment for additional paths
    # Note: We call this to ensure environment is set up, but don't use the return value here
    setup_intel_oneapi_environment(oneapi_path)

    # Build library and include paths
    lib_paths = []
    include_paths = []

    # Standard Intel oneAPI library paths - check multiple possible locations
    standard_lib_paths = [
        f"{oneapi_path}/compiler/latest/lib",
        f"{oneapi_path}/compiler/latest/linux/lib",
        f"{oneapi_path}/compiler/latest/linux/lib/x64",
        f"{oneapi_path}/mkl/latest/lib/intel64",
        f"{oneapi_path}/tbb/latest/lib/intel64/gcc4.8",
    ]

    # Also add version-specific library paths
    if compiler_base_path:
        version_lib_paths = [
            str(compiler_base_path.parent / "lib"),
            str(compiler_base_path.parent / "lib" / "x64"),
        ]
        standard_lib_paths.extend(version_lib_paths)

    for lib_path in standard_lib_paths:
        if Path(lib_path).exists():
            lib_paths.append(lib_path)
            logger.debug(f"🐛 Added library path: {lib_path}")

    # Standard Intel oneAPI include paths - check multiple possible locations
    standard_include_paths = [
        f"{oneapi_path}/compiler/latest/include",
        f"{oneapi_path}/compiler/latest/linux/include",
        f"{oneapi_path}/mkl/latest/include",
        f"{oneapi_path}/tbb/latest/include",
    ]

    # Also add version-specific include paths
    if compiler_base_path:
        version_include_paths = [
            str(compiler_base_path.parent / "include"),
        ]
        standard_include_paths.extend(version_include_paths)

    for include_path in standard_include_paths:
        if Path(include_path).exists():
            include_paths.append(include_path)
            logger.debug(f"🐛 Added include path: {include_path}")

    # Build LDFLAGS and CPPFLAGS
    ldflags = " ".join([f"-L{path}" for path in lib_paths])
    cppflags = " ".join([f"-I{path}" for path in include_paths])

    logger.info(f"🔧 Generated LDFLAGS: {ldflags}")
    logger.info(f"🔧 Generated CPPFLAGS: {cppflags}")

    # Restrict Intel compiler to floating-point suites only due to C++ compatibility issues in integer suites
    fp_suites = [suite for suite in suites if suite in ["fprate", "fpspeed"]]

    if len(fp_suites) < len(suites):
        excluded_suites = [suite for suite in suites if suite not in fp_suites]
        logger.info(f"🔧 Intel compiler restricted to floating-point suites only. Excluded suites: {excluded_suites}")
        logger.info(f"🔧 Processing floating-point suites: {fp_suites}")

    for suite in fp_suites:
        # Floating-point suites only: Use aggressive optimization where Intel compiler excels
        base_configs = [
            f"{suite}=base:CC={cc_compiler}",
            f"{suite}=base:CXX={cxx_compiler}",
            f"{suite}=base:OPTIMIZE=-w -m64 -Wl,-z,muldefs -xHost -Ofast -ffast-math -flto -mfpmath=sse -funroll-loops -qopt-mem-layout-trans=4 -mprefer-vector-width=512",
            f"{suite}=base:COPTIMIZE=-w -std=c11 -m64 -Wl,-z,muldefs -xHost -Ofast -ffast-math -flto -mfpmath=sse -funroll-loops -qopt-mem-layout-trans=4 -Wno-implicit-int -mprefer-vector-width=512",
            f"{suite}=base:CXXOPTIMIZE=-w -std=c++14 -m64 -Wl,-z,muldefs -xHost -Ofast -ffast-math -flto -mfpmath=sse -funroll-loops -qopt-mem-layout-trans=4 -mprefer-vector-width=512",
        ]

        # Add Fortran compiler and optimization if available
        if fc_compiler:
            # Floating-point suites: Aggressive Fortran optimization
            base_configs.extend(
                [
                    f"{suite}=base:FC={fc_compiler}",
                    f"{suite}=base:FOPTIMIZE=-w -m64 -Wl,-z,muldefs -xHost -Ofast -ffast-math -flto -mfpmath=sse -funroll-loops -qopt-mem-layout-trans=4 -nostandard-realloc-lhs -align array32byte -auto",
                ]
            )

        # Add library and include paths if available
        if ldflags:
            base_configs.append(f"{suite}=base:LDFLAGS={ldflags}")
        if cppflags:
            base_configs.append(f"{suite}=base:CPPFLAGS={cppflags}")

        config_additions.extend(base_configs)

        # Use basepeak for floating-point suites - reuse base configuration for peak runs
        # This simplifies configuration and avoids potential peak-specific compilation issues
        config_additions.append(f"{suite}=peak: basepeak = yes")

    logger.info(f"✅ Generated {len(config_additions)} Intel oneAPI configuration entries")
    return config_additions


def generate_config_from_template(
    cores: int | None = None,
    spec_root: Path | None = None,
    tune: str | None = None,
    config_add: list[str] | None = None,
    compiler: str | None = None,
) -> str | None:
    """Generate a SPEC CPU 2017 config file from SPEC's official template.

    Uses the Example-gcc-linux-x86.cfg template from the SPEC installation
    and modifies the copies value for rate benchmarks, tune setting, and
    adds custom configuration sections. Supports both GCC and Intel oneAPI compilers.

    Args:
        cores: Number of cores to use (for copies in rate benchmarks)
        spec_root: Path to SPEC installation directory
        tune: Tuning level (base, peak, all)
        config_add: List of custom config additions in format 'section:key=value'
        compiler: Compiler to use ('gcc', 'intel', 'oneapi', or None for auto-detection)

    Returns:
        Path to the generated config file, or None if template not found
    """
    try:
        # Find SPEC installation path
        if spec_root:
            spec_path = str(spec_root)
        else:
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

        # Determine which compiler to use
        effective_compiler = compiler
        if not effective_compiler:
            # Auto-detect available compilers
            oneapi_path = detect_intel_oneapi_path()
            gcc_path = detect_gcc_path()

            if oneapi_path:
                effective_compiler = "intel"
                logger.debug("🐛 Auto-detected Intel oneAPI compiler")
            elif gcc_path:
                effective_compiler = "gcc"
                logger.debug("🐛 Auto-detected GCC compiler")
            else:
                effective_compiler = "gcc"  # Fallback to GCC template
                logger.warning("⚠️  No compiler detected, using GCC template as fallback")

        # Handle Intel oneAPI compiler configuration
        if effective_compiler in ["intel", "oneapi"]:
            oneapi_path = detect_intel_oneapi_path()
            if oneapi_path:
                logger.info(f"🔧 Configuring Intel oneAPI at: {oneapi_path}")

                # Set up Intel oneAPI environment
                intel_env_vars = setup_intel_oneapi_environment(oneapi_path)

                # Validate that Intel compilers are available after environment setup
                if intel_env_vars and "PATH" in intel_env_vars:
                    # Temporarily update environment to test compiler availability
                    original_path = os.environ.get("PATH", "")
                    try:
                        os.environ["PATH"] = intel_env_vars["PATH"]
                        if validate_intel_oneapi_setup():
                            logger.info("✅ Intel oneAPI compilers validated successfully")
                        else:
                            logger.warning("⚠️  Intel oneAPI validation failed, falling back to GCC")
                            effective_compiler = "gcc"
                    finally:
                        os.environ["PATH"] = original_path
                else:
                    logger.warning("⚠️  Failed to set up Intel oneAPI environment, falling back to GCC")
                    effective_compiler = "gcc"

                if effective_compiler in ["intel", "oneapi"]:
                    # Generate Intel-specific config additions
                    intel_additions = generate_intel_config_additions(oneapi_path)

                    # Merge with user-provided config additions
                    if config_add is None:
                        config_add = []
                    config_add.extend(intel_additions)

                    logger.info(f"✅ Added {len(intel_additions)} Intel oneAPI config entries")
            else:
                logger.warning("⚠️  Intel compiler requested but oneAPI not found, falling back to GCC")
                effective_compiler = "gcc"

        # Handle GCC compiler configuration (default behavior)
        if effective_compiler == "gcc":
            # Auto-detect GCC version and uncomment GCCge10 if needed
            gcc_version = detect_gcc_version()
            if gcc_version and gcc_version >= 10:
                # Uncomment the GCCge10 define for GCC 10+
                old_line = "#%define GCCge10  # EDIT: remove the '#' from column 1 if using GCC 10 or later"
                new_line = (
                    "%define GCCge10  # EDIT: remove the '#' from column 1 if using GCC 10 or later (auto-detected)"
                )
                template_content = template_content.replace(old_line, new_line)

            # Auto-detect GCC path and update gcc_dir
            gcc_path = detect_gcc_path()
            if gcc_path:
                logger.debug(f"🐛 Detected GCC path: {gcc_path}")
                # Replace the gcc_dir define (this handles both the main and conditional cases)
                old_line = '%   define  gcc_dir        "/opt/rh/devtoolset-9/root/usr"  # EDIT (see above)'
                new_line = f'%   define  gcc_dir        "{gcc_path}"  # EDIT (see above) (auto-detected)'
                template_content = template_content.replace(old_line, new_line, 1)
                logger.debug("🐛 Updated GCC directory in config template")
            else:
                logger.warning("⚠️  Could not detect GCC path, using default in template")

        # Update tune setting based on CLI parameter
        if tune is not None:
            # Map tune values and update the tune line
            tune_mapping = {"base": "base", "peak": "peak", "all": "base,peak"}
            tune_value = tune_mapping.get(tune, tune)  # Use mapping or original value
            template_content = template_content.replace(
                'tune                 = base,peak  # EDIT if needed: set to "base" for old GCC.',
                f'tune                 = {tune_value}  # EDIT if needed: set to "base" for old GCC. (auto-set)',
            )

        # Process custom config additions
        if config_add:
            for addition in config_add:
                try:
                    # Parse the format: "section:key=value"
                    if ":" not in addition:
                        logger.warning(f"⚠️  Invalid config addition format: {addition}. Expected 'section:key=value'")
                        continue

                    section_part, config_part = addition.split(":", 1)

                    if "=" not in config_part:
                        logger.warning(f"⚠️  Invalid config addition format: {addition}. Expected 'section:key=value'")
                        continue

                    key, value = config_part.split("=", 1)

                    # Clean up whitespace
                    section_part = section_part.strip()
                    key = key.strip()
                    value = value.strip()

                    # Create the config section content
                    section_header = f"{section_part}:"
                    config_line = f"      {key:<15} = {value}"
                    section_content = f"{section_header}\n{config_line}"

                    # Check if the section already exists
                    if section_header in template_content:
                        # Find the section and add the config line after it
                        # Look for the section header followed by a newline
                        section_index = template_content.find(section_header)
                        if section_index != -1:
                            # Find the end of the line
                            line_end = template_content.find("\n", section_index)
                            if line_end != -1:
                                # Insert the config line after the section header
                                template_content = (
                                    template_content[:line_end] + f"\n{config_line}" + template_content[line_end:]
                                )
                    else:
                        # Section doesn't exist, add it before the benchmark sections
                        # Find a good insertion point (typically before the first benchmark section)
                        insertion_patterns = [
                            "intrate=base:",
                            "intspeed=base:",
                            "fprate=base:",
                            "fpspeed=base:",
                            "intrate,fprate=base:",
                            "intspeed,fpspeed=base:",
                        ]

                        inserted = False
                        for pattern in insertion_patterns:
                            if pattern in template_content:
                                template_content = template_content.replace(pattern, section_content + "\n\n" + pattern)
                                inserted = True
                                break

                        if not inserted:
                            # Fallback: add at the end of the file
                            template_content += f"\n\n{section_content}\n"

                    logger.debug(f"🐛 Added config: {section_part} -> {key} = {value}")

                except ValueError as e:
                    logger.warning(f"⚠️  Error processing config addition '{addition}': {e}")
                    continue

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


def build_runcpu_command(
    action: str,
    benchmarks: list[str],
    config: str,
    tune: str | None = None,
    spec_root: Path | None = None,
    verbose: bool = False,
    rebuild: bool = False,
    parallel_test: int | None = None,
    ignore_errors: bool = False,
    size: str | None = None,
    copies: int | None = None,
    threads: int | None = None,
    iterations: int | None = None,
    reportable: bool = False,
    noreportable: bool = False,
    output_formats: str | None = None,
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

    # Add output formats (default to rsf,pdf for speed, allow all for compatibility)
    # IMPORTANT: Must come before --verbose since --verbose can take a numeric parameter
    if output_formats is not None:
        if output_formats.lower() == "all":
            # Use SPEC default (all formats: rsf, html, pdf, txt, ps)
            pass  # Don't add --output_format to use SPEC defaults
        else:
            # Use specified formats
            cmd.extend(["--output_format", output_formats])
    else:
        # Default: only rsf and pdf for speed and efficiency
        cmd.extend(["--output_format", "rsf,pdf"])

    # Add verbose (must be after --output_format to avoid conflicts)
    if verbose:
        cmd.append("--verbose=5")  # Use verbosity level 5 for detailed output

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


def validate_numa_topology() -> dict[str, Any] | None:
    """Validate NUMA topology and return available nodes and CPUs.

    Returns:
        Dictionary with NUMA topology information, or None if NUMA not available
    """
    # Try to get NUMA topology using numactl --hardware
    result = subprocess.run(["numactl", "--hardware"], capture_output=True, text=True, timeout=10)

    if result.returncode != 0:
        return None

    topology: dict[str, Any] = {"nodes": [], "node_cpus": {}, "total_cpus": 0}
    nodes_list: list[int] = topology["nodes"]
    node_cpus_dict: dict[int, list[int]] = topology["node_cpus"]

    lines = result.stdout.strip().split("\n")

    for line in lines:
        line = line.strip()
        if line.startswith("node ") and " cpus:" in line:
            # Parse line like "node 0 cpus: 0 1 2 3 4 5"
            parts = line.split()
            if len(parts) >= 3 and parts[1].isdigit():
                node_id = int(parts[1])
                nodes_list.append(node_id)
                cpu_list: list[int] = []
                # Extract CPU numbers after "cpus:"
                cpus_start = False
                for part in parts:
                    if cpus_start and part.isdigit():
                        cpu_list.append(int(part))
                    elif part == "cpus:":
                        cpus_start = True
                node_cpus_dict[node_id] = cpu_list
                if cpu_list:
                    topology["total_cpus"] = max(topology["total_cpus"], max(cpu_list) + 1)

    return topology if nodes_list else None


def build_affinity_command(
    base_cmd: list[str],
    numa_node: int | None = None,
    cpu_cores: str | None = None,
    numa_memory: bool | None = None,
) -> list[str]:
    """Build command with NUMA/CPU affinity using numactl or taskset.

    Args:
        base_cmd: The base command to wrap
        numa_node: NUMA node to bind to (uses numactl --cpunodebind and --membind)
        cpu_cores: CPU cores to bind to (uses numactl --physcpubind or taskset)
        numa_memory: Whether to bind memory to the same NUMA node as CPU

    Returns:
        Modified command with affinity bindings
    """
    if not numa_node and not cpu_cores:
        return base_cmd

    # Prefer numactl for comprehensive NUMA management
    try:
        # Check if numactl is available
        subprocess.run(["numactl", "--version"], capture_output=True, check=True)
        use_numactl = True
    except (subprocess.SubprocessError, FileNotFoundError):
        use_numactl = False

    if use_numactl:
        # Use numactl for both NUMA node and CPU core binding
        affinity_cmd = ["numactl"]

        if numa_node is not None:
            # Bind to specific NUMA node
            affinity_cmd.extend(["--cpunodebind", str(numa_node)])
            if numa_memory is None or numa_memory:  # Default to binding memory
                affinity_cmd.extend(["--membind", str(numa_node)])

        if cpu_cores:
            # Bind to specific CPU cores
            affinity_cmd.extend(["--physcpubind", cpu_cores])

        return affinity_cmd + ["--"] + base_cmd

    elif cpu_cores:
        # Fall back to taskset for CPU binding only
        try:
            subprocess.run(["taskset", "--version"], capture_output=True, check=True)
            return ["taskset", "-c", cpu_cores] + base_cmd
        except (subprocess.SubprocessError, FileNotFoundError):
            # No affinity tools available, return original command
            typer.echo(
                "Warning: Neither numactl nor taskset available for CPU affinity",
                err=True,
            )
            return base_cmd

    return base_cmd


def parse_benchmark_from_output(line: str) -> str | None:
    """Parse benchmark name from SPEC output line.

    Args:
        line: A line of SPEC output

    Returns:
        Benchmark name if found, None otherwise
    """
    # Common patterns in SPEC output
    patterns = [
        r"Running.*?(\d{3}\.\w+(?:_[rs])?)",  # "Running 500.perlbench_r"
        r"Building.*?(\d{3}\.\w+(?:_[rs])?)",  # "Building 502.gcc_r"
        r"(\d{3}\.\w+(?:_[rs])?)\s*(?:base|peak)",  # "500.perlbench_r base"
        r"runcpu.*?(\d{3}\.\w+(?:_[rs])?)",  # "runcpu ... 519.lbm_r"
        r"specinvoke.*?(\d{3}\.\w+(?:_[rs])?)",  # "specinvoke ... 525.x264_r"
        r"^(\d{3}\.\w+(?:_[rs])?):\s",  # "500.perlbench_r: "
    ]

    for pattern in patterns:
        match = re.search(pattern, line, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


def execute_runcpu(
    cmd: list[str],
    verbose: bool = False,
    parse_results: bool = False,
    spec_root: Path | None = None,
    hide_logs: bool = False,
    show_progress: bool = True,
    numa_node: int | None = None,
    cpu_cores: str | None = None,
    numa_memory: bool | None = None,
) -> dict[str, Any] | None:
    """Execute the runcpu command and optionally parse results.

    Args:
        cmd: Command to execute
        verbose: Whether to show verbose output
        parse_results: Whether to parse output for result files and scores
        spec_root: Path to SPEC installation (needed for result parsing)
        hide_logs: Whether to hide the original SPEC logs during execution
        show_progress: Whether to show a progress spinner when hiding logs
        numa_node: NUMA node to bind process to
        cpu_cores: CPU cores to bind process to
        numa_memory: Whether to bind memory to the same NUMA node

    Returns:
        Dictionary containing result information if parse_results=True, otherwise None
    """
    # Apply NUMA/CPU affinity if specified
    final_cmd = build_affinity_command(cmd, numa_node, cpu_cores, numa_memory)

    if verbose:
        logger.info(f"ℹ️  Executing: [bold]{' '.join(final_cmd)}[/bold]")
        if final_cmd != cmd:
            affinity_part = final_cmd[: final_cmd.index("--") if "--" in final_cmd else len(final_cmd) - len(cmd)]
            logger.info(f"ℹ️  Applied affinity binding: [bold]{' '.join(affinity_part)}[/bold]")

    try:
        if parse_results or hide_logs:
            # Capture output for parsing or when hiding logs
            if hide_logs and show_progress:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    TimeElapsedColumn(),
                    transient=True,
                ) as progress:
                    task = progress.add_task(description="Running SPEC benchmarks...", total=None)

                    # Use Popen for real-time output monitoring
                    process = subprocess.Popen(
                        final_cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        universal_newlines=True,
                        bufsize=1,
                    )

                    current_benchmark = None
                    output_lines = []

                    # Monitor output in real-time
                    if process.stdout:
                        for line in iter(process.stdout.readline, ""):
                            output_lines.append(line)

                            # Try to detect current benchmark
                            detected_benchmark = parse_benchmark_from_output(line)
                            if detected_benchmark and detected_benchmark != current_benchmark:
                                current_benchmark = detected_benchmark
                                progress.update(task, description=f"Running {current_benchmark}...")

                    # Wait for process to complete
                    process.wait()

                    result = ProcessResult(
                        returncode=process.returncode,
                        stdout="".join(output_lines),
                        stderr="",
                    )
            else:
                subprocess_result = subprocess.run(
                    final_cmd,
                    check=False,
                    text=True,
                    capture_output=True,
                )
                result = ProcessResult(
                    returncode=subprocess_result.returncode,
                    stdout=subprocess_result.stdout,
                    stderr=subprocess_result.stderr,
                )

            # Show output only if not hiding logs or in verbose mode
            if not hide_logs or verbose:
                if result.stdout:
                    typer.echo(result.stdout)
                if result.stderr:
                    typer.echo(result.stderr, err=True)

            output = result.stdout + result.stderr
        else:
            # Normal execution without capturing output
            subprocess_result = subprocess.run(
                final_cmd,
                check=False,
                text=True,
                capture_output=False,
            )
            result = ProcessResult(returncode=subprocess_result.returncode, stdout="", stderr="")
            output = ""

        if result.returncode != 0:
            logger.error(f"❌ Command failed with exit code {result.returncode}")
            raise typer.Exit(result.returncode)

        # Parse results if requested and we have output to parse
        if parse_results and spec_root and output:
            from specer.result_parser import parse_result_files  # Import when needed

            parsed_results = parse_result_files(output)
            if parsed_results:
                return parsed_results

        return None

    except FileNotFoundError as err:
        logger.error(
            "❌ 'runcpu' command not found. Please ensure SPEC CPU 2017 is installed "
            "and the 'runcpu' command is in your PATH, or use --spec-root to specify "
            "the SPEC installation directory."
        )
        raise typer.Exit(1) from err
    except KeyboardInterrupt as err:
        logger.warning("⚠️  Operation cancelled by user")
        raise typer.Exit(130) from err


def display_results_with_rich(
    result_info: dict[str, Any],
    console: Console | None = None,
    show_timing: bool = False,
) -> None:
    """Display benchmark results using Rich formatting.

    Args:
        result_info: Parsed result information
        console: Rich console instance (uses specer console if None)
        show_timing: Whether to display execution timing information
    """
    if console is None:
        console = Console()

    # Create main results panel
    console.print()
    console.print(
        Panel.fit(
            "[bold blue]🎯 SPEC CPU 2017 Benchmark Results[/bold blue]",
            border_style="blue",
        )
    )

    # Display overall scores
    if result_info.get("scores"):
        scores_table = Table(title="📊 Overall Scores", show_header=True)
        scores_table.add_column("Metric", style="cyan", width=30)
        scores_table.add_column("Score", style="green", justify="right")

        for metric, score in result_info["scores"].items():
            scores_table.add_row(metric, f"{score:.2f}")

        console.print(scores_table)
        console.print()

    # Display suite metrics
    if result_info.get("metrics"):
        metrics_table = Table(title="📈 Suite Metrics", show_header=True)
        metrics_table.add_column("Metric", style="cyan", width=30)
        metrics_table.add_column("Value", style="yellow", justify="right")

        for metric, value in result_info["metrics"].items():
            metrics_table.add_row(metric, f"{value:.2f}")

        console.print(metrics_table)
        console.print()

    # Display individual benchmark results
    if result_info.get("benchmark_results"):
        bench_table = Table(title="🔬 Individual Benchmark Results", show_header=True)
        bench_table.add_column("Benchmark", style="cyan", width=18)
        bench_table.add_column("Status", style="yellow", width=10)
        bench_table.add_column("Ratio", style="green", justify="right", width=8)
        bench_table.add_column("Time (s)", style="blue", justify="right", width=8)
        bench_table.add_column("Reference", style="magenta", justify="right", width=9)
        bench_table.add_column("Copies", style="white", justify="center", width=7)
        bench_table.add_column("Threads", style="white", justify="center", width=8)

        for benchmark, data in result_info["benchmark_results"].items():
            # Check if benchmark failed
            if data.get("status") == "failed":
                status = "[red]Failed[/red]"
                ratio = "N/A"
                time = "N/A"
                reference = "N/A"
                copies = "N/A"
                threads = "N/A"
            elif data.get("warning"):
                # Has results but SPEC flagged it
                status = "[yellow]Warning[/yellow]"
                ratio = f"{data.get('ratio', 'N/A'):.2f}" if isinstance(data.get("ratio"), int | float) else "N/A"
                time = f"{data.get('time', 'N/A'):.1f}" if isinstance(data.get("time"), int | float) else "N/A"
                reference = (
                    f"{data.get('reference', 'N/A'):.0f}" if isinstance(data.get("reference"), int | float) else "N/A"
                )
                copies = f"{data.get('copies', 'N/A')}" if data.get("copies") is not None else "N/A"
                threads = f"{data.get('threads', 'N/A')}" if data.get("threads") is not None else "N/A"
            else:
                status = "[green]Success[/green]"
                ratio = f"{data.get('ratio', 'N/A'):.2f}" if isinstance(data.get("ratio"), int | float) else "N/A"
                time = f"{data.get('time', 'N/A'):.1f}" if isinstance(data.get("time"), int | float) else "N/A"
                reference = (
                    f"{data.get('reference', 'N/A'):.0f}" if isinstance(data.get("reference"), int | float) else "N/A"
                )
                copies = f"{data.get('copies', 'N/A')}" if data.get("copies") is not None else "N/A"
                threads = f"{data.get('threads', 'N/A')}" if data.get("threads") is not None else "N/A"

            bench_table.add_row(benchmark, status, ratio, time, reference, copies, threads)

        console.print(bench_table)
        console.print()

    # Display result files
    if result_info.get("result_files"):
        files_table = Table(title="📄 Result Files", show_header=True)
        files_table.add_column("File Path", style="cyan")
        files_table.add_column("Type", style="magenta")

        for file_info in result_info["result_files"]:
            files_table.add_row(file_info["path"], file_info["type"])

        console.print(files_table)
        console.print()

    # Display log file location
    if result_info.get("log_file"):
        console.print(
            Panel(
                f"[yellow]📝 Log File:[/yellow] [cyan]{result_info['log_file']}[/cyan]",
                border_style="yellow",
            )
        )

    # Display execution timing if available and requested
    if show_timing and result_info.get("execution_time"):
        elapsed_time = result_info["execution_time"]
        minutes = int(elapsed_time // 60)
        seconds = elapsed_time % 60

        time_str = f"{minutes}m {seconds:.1f}s" if minutes > 0 else f"{seconds:.1f}s"

        console.print(
            Panel(
                f"[green]⏱️  Execution Time:[/green] [bold cyan]{time_str}[/bold cyan]",
                border_style="green",
            )
        )


def save_results_to_json(
    result_info: dict[str, Any],
    output_file: str | None = None,
    benchmarks: list[str] | None = None,
    config: str | None = None,
) -> str:
    """Save benchmark results to JSON file.

    Args:
        result_info: Parsed result information
        output_file: Custom output file path (auto-generated if None)
        benchmarks: List of benchmarks that were run
        config: Configuration file used

    Returns:
        Path to the generated JSON file
    """
    # Generate filename if not provided
    if output_file is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"specer_results_{timestamp}.json"

    # Read config file contents if config path is provided
    config_data = None
    if config and Path(config).exists():
        try:
            with Path(config).open("r") as f:
                config_data = {
                    "path": config,
                    "contents": f.read(),
                }
        except OSError as e:
            logger.warning(f"Could not read config file {config}: {e}")
            # Fallback to just storing the path
            config_data = {"path": config, "contents": ""}
    elif config:
        # Config path provided but file doesn't exist (e.g., already cleaned up)
        config_data = {"path": config, "contents": ""}

    # Prepare output data
    output_data = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "specer_version": "0.1.0",  # Could import from __version__ if needed
            "benchmarks": benchmarks or [],
            "config": config_data,
        },
        "results": result_info,
    }

    # Write to JSON file
    output_path = Path(output_file)
    with output_path.open("w") as f:
        json.dump(output_data, f, indent=2, default=str)

    return str(output_path)
