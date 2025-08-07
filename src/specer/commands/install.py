"""Install command for SPEC CPU 2017 from ISO."""

import subprocess
import tempfile
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn


def install_command(
    iso_path: Annotated[
        Path,
        typer.Argument(help="Path to SPEC CPU 2017 ISO file (e.g., cpu2017-1.1.9.iso)"),
    ],
    install_dir: Annotated[
        Path,
        typer.Option(
            "--install-dir",
            "-d",
            help="Installation directory (default: /opt/spec2017)",
        ),
    ] = Path("/opt/spec2017"),
    mount_point: Annotated[
        Optional[Path],
        typer.Option(
            "--mount-point",
            "-m",
            help="Temporary mount point for ISO (auto-created if not specified)",
        ),
    ] = None,
    accept_license: Annotated[
        bool,
        typer.Option(
            "--accept-license",
            "-y",
            help="Accept SPEC license agreement automatically",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Show commands that would be executed without running them",
        ),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Enable verbose output during installation",
        ),
    ] = False,
    cleanup: Annotated[
        bool,
        typer.Option(
            "--cleanup/--no-cleanup",
            help="Clean up temporary files and mount points after installation (default: True)",
        ),
    ] = True,
    sudo_password: Annotated[
        Optional[str],
        typer.Option(
            "--sudo-password",
            help="Sudo password for mount operations (will prompt if not provided and needed)",
        ),
    ] = None,
) -> None:
    """Install SPEC CPU 2017 from ISO file to a complete working installation.

    This command handles the complete installation process:
    1. Validates the ISO file and system requirements
    2. Creates and mounts the ISO (requires sudo for mount operations)
    3. Runs SPEC's install.sh script
    4. Sets up the environment and validates the installation
    5. Runs initial setup and validation tests

    Examples:
        # Basic installation
        specer install /path/to/cpu2017-1.1.9.iso

        # Custom installation directory
        specer install /path/to/cpu2017-1.1.9.iso --install-dir /home/user/spec2017

        # Accept license automatically (for automation)
        specer install /path/to/cpu2017-1.1.9.iso --accept-license

        # Dry run to see what would happen
        specer install /path/to/cpu2017-1.1.9.iso --dry-run

        # Verbose installation with custom mount point
        specer install /path/to/cpu2017-1.1.9.iso --mount-point /tmp/spec_mount --verbose
    """
    console = Console()

    # Validate inputs
    if not iso_path.exists():
        console.print(f"❌ [red]Error: ISO file not found: {iso_path}[/red]")
        raise typer.Exit(1)

    if iso_path.suffix.lower() != ".iso":
        console.print("⚠️  [yellow]Warning: File doesn't have .iso extension[/yellow]")
        if not typer.confirm("Continue anyway?"):
            raise typer.Exit(1)

    # Check if install directory already exists
    if install_dir.exists() and any(install_dir.iterdir()):
        console.print(
            f"⚠️  [yellow]Warning: Installation directory already exists and is not empty: {install_dir}[/yellow]"
        )
        if not dry_run and not typer.confirm(
            "Continue with installation? This may overwrite existing files."
        ):
            raise typer.Exit(1)

    # Create temporary mount point if not specified
    if mount_point is None:
        temp_dir = tempfile.mkdtemp(prefix="spec_mount_")
        mount_point = Path(temp_dir)
    elif not mount_point.exists():
        mount_point.mkdir(parents=True, exist_ok=True)

    console.print()
    console.print(
        Panel.fit(
            "[bold blue]🚀 SPEC CPU 2017 Installation[/bold blue]", border_style="blue"
        )
    )

    console.print(f"📁 ISO File: [cyan]{iso_path}[/cyan]")
    console.print(f"📁 Install Directory: [cyan]{install_dir}[/cyan]")
    console.print(f"📁 Mount Point: [cyan]{mount_point}[/cyan]")
    console.print()

    if dry_run:
        console.print(
            "[bold yellow]🔍 DRY RUN MODE - No actual changes will be made[/bold yellow]"
        )
        console.print()

    try:
        # Step 1: Mount the ISO
        _install_mount_iso(
            iso_path, mount_point, dry_run, verbose, console, sudo_password
        )

        # Step 2: Run SPEC installation
        _install_run_spec_installer(
            mount_point, install_dir, accept_license, dry_run, verbose, console
        )

        # Step 3: Set up environment and validate
        if not dry_run:
            _install_setup_environment(install_dir, console)

        # Step 4: Validate installation
        if not dry_run:
            _install_validate_installation(install_dir, console)

        console.print()
        console.print(
            Panel.fit(
                "[bold green]✅ SPEC CPU 2017 Installation Complete![/bold green]",
                border_style="green",
            )
        )

        if not dry_run:
            console.print("\n📝 [bold]Next Steps:[/bold]")
            console.print(
                f"   1. Set environment: [cyan]export SPEC_PATH={install_dir}[/cyan]"
            )
            console.print(
                "   2. Test installation: [cyan]specer run gcc --cores 4 --dry-run[/cyan]"
            )
            console.print(
                "   3. Run your first benchmark: [cyan]specer run gcc --cores 4[/cyan]"
            )

    except Exception as e:
        console.print(f"\n❌ [red]Installation failed: {e}[/red]")
        raise typer.Exit(1) from e

    finally:
        # Cleanup
        if cleanup and not dry_run:
            _install_cleanup(mount_point, verbose, console)


def _install_mount_iso(
    iso_path: Path,
    mount_point: Path,
    dry_run: bool,
    verbose: bool,
    console: Console,
    sudo_password: Optional[str] = None,
) -> None:
    """Mount the SPEC CPU 2017 ISO file."""
    console.print("🔧 [bold blue]Step 1: Mounting ISO file...[/bold blue]")

    # Check if already mounted
    try:
        result = subprocess.run(["mount"], capture_output=True, text=True, check=True)
        if str(iso_path) in result.stdout and str(mount_point) in result.stdout:
            console.print(f"✅ ISO already mounted at {mount_point}")
            return
    except subprocess.SubprocessError:
        pass

    mount_cmd = ["sudo", "mount", "-o", "loop", str(iso_path), str(mount_point)]

    if dry_run:
        console.print(f"Would execute: [cyan]{' '.join(mount_cmd)}[/cyan]")
        return

    if verbose:
        console.print(f"Executing: [cyan]{' '.join(mount_cmd)}[/cyan]")

    try:
        # Create mount point if it doesn't exist
        mount_point.mkdir(parents=True, exist_ok=True)

        # Use sudo to mount the ISO
        if sudo_password:
            # Use sudo with password
            mount_process = subprocess.Popen(
                mount_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            stdout, stderr = mount_process.communicate(input=sudo_password + "\n")

            if mount_process.returncode != 0:
                raise subprocess.SubprocessError(f"Mount failed: {stderr}")
        else:
            # Let sudo prompt for password
            subprocess.run(mount_cmd, check=True)

        console.print(f"✅ ISO mounted successfully at [cyan]{mount_point}[/cyan]")

        # Verify mount
        if not (mount_point / "install.sh").exists():
            raise FileNotFoundError(
                "install.sh not found in mounted ISO - this may not be a valid SPEC CPU 2017 ISO"
            )

    except subprocess.SubprocessError as e:
        raise Exception(f"Failed to mount ISO: {e}") from e
    except FileNotFoundError as e:
        raise Exception(f"Invalid SPEC ISO: {e}") from e


def _install_run_spec_installer(
    mount_point: Path,
    install_dir: Path,
    accept_license: bool,
    dry_run: bool,
    verbose: bool,
    console: Console,
) -> None:
    """Run the SPEC CPU 2017 installer script."""
    console.print("🔧 [bold blue]Step 2: Running SPEC installer...[/bold blue]")

    install_script = mount_point / "install.sh"
    if not install_script.exists():
        raise FileNotFoundError(f"SPEC installer not found: {install_script}")

    # Prepare installation command
    install_cmd = ["bash", str(install_script), "-d", str(install_dir)]

    if accept_license:
        install_cmd.append("-f")  # Force/accept license

    if dry_run:
        console.print(f"Would execute: [cyan]{' '.join(install_cmd)}[/cyan]")
        console.print(f"Would install SPEC to: [cyan]{install_dir}[/cyan]")
        return

    if verbose:
        console.print(f"Executing: [cyan]{' '.join(install_cmd)}[/cyan]")

    try:
        # Create install directory if it doesn't exist
        install_dir.parent.mkdir(parents=True, exist_ok=True)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=console,
            transient=False,
        ) as progress:
            task = progress.add_task(
                description="Installing SPEC CPU 2017...", total=None
            )

            # Run installer
            process = subprocess.Popen(
                install_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(mount_point),
            )

            output_lines = []
            if process.stdout:
                for line in iter(process.stdout.readline, ""):
                    output_lines.append(line)
                    if verbose:
                        console.print(line.rstrip())

                    # Update progress based on installer output
                    if "extracting" in line.lower() or "installing" in line.lower():
                        progress.update(
                            task, description=f"Installing: {line.strip()[:50]}..."
                        )

            process.wait()

            if process.returncode != 0:
                console.print("\n❌ [red]Installation failed. Output:[/red]")
                for line in output_lines[-20:]:  # Show last 20 lines
                    console.print(line.rstrip())
                raise subprocess.SubprocessError(
                    f"SPEC installer failed with exit code {process.returncode}"
                )

        console.print("✅ SPEC CPU 2017 installed successfully")

    except subprocess.SubprocessError as e:
        raise Exception(f"SPEC installation failed: {e}") from e


def _install_setup_environment(
    install_dir: Path,
    console: Console,
) -> None:
    """Set up the SPEC environment and perform initial setup."""
    console.print("🔧 [bold blue]Step 3: Setting up environment...[/bold blue]")

    # Check if SPEC installation looks correct
    runcpu_path = install_dir / "bin" / "runcpu"
    if not runcpu_path.exists():
        raise FileNotFoundError(
            f"runcpu not found at {runcpu_path} - installation may have failed"
        )

    # Source the SPEC environment
    shrc_path = install_dir / "shrc"
    if not shrc_path.exists():
        console.print(
            "⚠️  [yellow]Warning: shrc file not found - environment may not be properly set up[/yellow]"
        )
    else:
        console.print(f"✅ Found SPEC environment file: [cyan]{shrc_path}[/cyan]")

    console.print("✅ Environment setup complete")


def _install_validate_installation(
    install_dir: Path,
    console: Console,
) -> None:
    """Validate the SPEC installation by running basic tests."""
    console.print("🔧 [bold blue]Step 4: Validating installation...[/bold blue]")

    runcpu_path = install_dir / "bin" / "runcpu"

    # Test 1: Check if runcpu is executable
    try:
        result = subprocess.run(
            [str(runcpu_path), "--help"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(install_dir),
        )

        if result.returncode != 0:
            raise subprocess.SubprocessError(f"runcpu --help failed: {result.stderr}")

        console.print("✅ runcpu executable test passed")

    except subprocess.SubprocessError as e:
        raise Exception(f"runcpu validation failed: {e}") from e
    except subprocess.TimeoutExpired as e:
        raise Exception(
            "runcpu --help timed out - installation may be incomplete"
        ) from e

    # Test 2: Check for basic benchmark directories
    benchmarks_dir = install_dir / "benchspec" / "CPU"
    if not benchmarks_dir.exists():
        raise FileNotFoundError(f"Benchmarks directory not found: {benchmarks_dir}")

    # Count available benchmarks
    try:
        benchmark_dirs = [
            d
            for d in benchmarks_dir.iterdir()
            if d.is_dir() and d.name.startswith(("5", "6"))
        ]
        console.print(f"✅ Found {len(benchmark_dirs)} benchmark suites")

        if len(benchmark_dirs) < 20:  # SPEC CPU 2017 should have 23 benchmarks
            console.print(
                "⚠️  [yellow]Warning: Expected ~23 benchmarks, installation may be incomplete[/yellow]"
            )

    except Exception as e:
        console.print(
            f"⚠️  [yellow]Warning: Could not validate benchmarks: {e}[/yellow]"
        )

    # Test 3: Check for example config files
    config_dir = install_dir / "config"
    if config_dir.exists():
        example_configs = list(config_dir.glob("Example-*.cfg"))
        if example_configs:
            console.print(f"✅ Found {len(example_configs)} example config files")
        else:
            console.print("⚠️  [yellow]Warning: No example config files found[/yellow]")

    console.print("✅ Installation validation complete")


def _install_cleanup(
    mount_point: Path,
    verbose: bool,
    console: Console,
) -> None:
    """Clean up temporary files and unmount the ISO."""
    console.print("🧹 [bold blue]Cleaning up...[/bold blue]")

    try:
        # Unmount the ISO
        umount_cmd = ["sudo", "umount", str(mount_point)]

        if verbose:
            console.print(f"Executing: [cyan]{' '.join(umount_cmd)}[/cyan]")

        subprocess.run(umount_cmd, check=True, capture_output=True)
        console.print(f"✅ Unmounted ISO from [cyan]{mount_point}[/cyan]")

        # Remove temporary mount point if we created it
        if mount_point.name.startswith("spec_mount_"):
            mount_point.rmdir()
            console.print("✅ Removed temporary mount point")

    except subprocess.SubprocessError as e:
        console.print(f"⚠️  [yellow]Warning: Could not unmount ISO: {e}[/yellow]")
        console.print(
            f"You may need to manually unmount: [cyan]sudo umount {mount_point}[/cyan]"
        )
    except OSError as e:
        console.print(f"⚠️  [yellow]Warning: Could not remove mount point: {e}[/yellow]")
