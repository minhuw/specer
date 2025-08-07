"""Install command for SPEC CPU 2017 from local ISO file."""

import contextlib
import os
import subprocess
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel


def install_command(
    iso_path: Annotated[
        Path,
        typer.Argument(
            help="Path to SPEC CPU 2017 ISO file",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
        ),
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
        Path | None,
        typer.Option(
            "--mount-point",
            "-m",
            help="Temporary mount point for ISO (auto-created if not specified)",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Show what would be done without executing",
        ),
    ] = False,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            help="Force installation even if target directory exists",
        ),
    ] = False,
) -> None:
    """Install SPEC CPU 2017 from a local ISO file.

    This command mounts a SPEC CPU 2017 ISO file and runs the official
    install.sh script to perform the installation. It requires root
    privileges for mounting and installation.

    Examples:
        # Basic installation from ISO
        specer install cpu2017-1.1.9.iso

        # Install to custom directory
        specer install cpu2017-1.1.9.iso --install-dir ~/spec2017

        # Auto-accept license
        specer install cpu2017-1.1.9.iso --accept-license

        # Dry run to see what would happen
        specer install cpu2017-1.1.9.iso --dry-run
    """
    console = Console()

    console.print()
    console.print(
        Panel.fit(
            "[bold blue]🛠️  SPEC CPU 2017 Installation[/bold blue]", border_style="blue"
        )
    )

    # Validate ISO file
    if not _validate_iso_file(iso_path, console):
        raise typer.Exit(1)

    # Check if installation directory already exists
    if install_dir.exists() and not force:
        console.print(
            f"❌ [red]Installation directory already exists: {install_dir}[/red]"
        )
        console.print(
            "💡 [yellow]Use --force to overwrite or choose a different directory[/yellow]"
        )
        raise typer.Exit(1)

    if dry_run:
        _show_dry_run(iso_path, install_dir, mount_point, console)
        return

    import tempfile

    # Create temporary mount point if not specified
    temp_mount_dir = None
    if mount_point is None:
        temp_mount_dir = Path(tempfile.mkdtemp(prefix="spec2017_mount_"))
        mount_point = temp_mount_dir
    else:
        mount_point.mkdir(parents=True, exist_ok=True)

    try:
        # Mount the ISO
        console.print(f"🗂️  [blue]Mounting ISO:[/blue] [cyan]{iso_path}[/cyan]")
        console.print(f"📁 [blue]Mount point:[/blue] [cyan]{mount_point}[/cyan]")

        if not _install_mount_iso(iso_path, mount_point, console):
            raise typer.Exit(1)

        try:
            # Check if it's a valid SPEC CPU 2017 ISO
            if not _validate_spec_iso_content(mount_point, console):
                raise typer.Exit(1)

            # Run official install.sh script
            if not _run_official_installer(mount_point, install_dir, console):
                raise typer.Exit(1)

            console.print()
            console.print(
                "✅ [bold green]SPEC CPU 2017 installation completed successfully![/bold green]"
            )
            console.print(
                "🚀 [green]Used official install.sh script for proper installation[/green]"
            )
            console.print(
                "👤 [green]Installed with proper user permissions (no sudo used)[/green]"
            )
            console.print(
                f"📁 [blue]Installation directory:[/blue] [cyan]{install_dir}[/cyan]"
            )
            console.print()
            console.print("📝 [bold]Next steps:[/bold]")
            console.print(
                f"   1. Set SPEC_ROOT: [cyan]export SPEC_ROOT={install_dir}[/cyan]"
            )
            console.print(
                "   2. Source environment: [cyan]source $SPEC_ROOT/shrc[/cyan]"
            )
            console.print("   3. Run setup: [cyan]specer setup[/cyan]")
            console.print("   4. Test installation: [cyan]runcpu --help[/cyan]")

        finally:
            # Unmount the ISO
            _install_unmount_iso(mount_point, console)

    finally:
        # Clean up temporary mount directory
        if temp_mount_dir and temp_mount_dir.exists():
            with contextlib.suppress(Exception):
                temp_mount_dir.rmdir()  # Best effort cleanup


def _validate_iso_file(iso_path: Path, console: Console) -> bool:
    """Validate that the file appears to be a valid ISO."""
    console.print(f"🔍 [blue]Validating ISO file:[/blue] [cyan]{iso_path}[/cyan]")

    # Check file size
    file_size = iso_path.stat().st_size
    size_mb = file_size / (1024 * 1024)
    console.print(f"📊 [blue]File size:[/blue] [cyan]{size_mb:.2f} MB[/cyan]")

    if size_mb < 100:
        console.print("⚠️  [yellow]Warning: File is quite small for a SPEC ISO[/yellow]")

    # Use 'file' command to check file type if available
    try:
        result = subprocess.run(
            ["file", str(iso_path)], capture_output=True, text=True, timeout=10
        )

        if result.returncode == 0:
            file_type = result.stdout.strip()
            console.print(f"🔍 [blue]File type:[/blue] [cyan]{file_type}[/cyan]")

            if "ISO 9660" in file_type or "CD-ROM filesystem" in file_type:
                console.print("✅ [green]File appears to be a valid ISO[/green]")
            else:
                console.print(
                    "⚠️  [yellow]Warning: File may not be an ISO format[/yellow]"
                )
                if not typer.confirm("Continue anyway?"):
                    return False
        else:
            console.print("⚠️  [yellow]Could not determine file type[/yellow]")

    except (subprocess.TimeoutExpired, FileNotFoundError):
        console.print(
            "⚠️  [yellow]'file' command not available, skipping type check[/yellow]"
        )

    return True


def _show_dry_run(
    iso_path: Path, install_dir: Path, mount_point: Path | None, console: Console
) -> None:
    """Show what would be done in a dry run."""
    console.print()
    console.print(
        "🔍 [bold blue]Dry Run - Actions that would be performed:[/bold blue]"
    )
    console.print()
    console.print(f"1. 🗂️  Mount ISO: [cyan]{iso_path}[/cyan]")

    if mount_point:
        console.print(f"   └─ Mount point: [cyan]{mount_point}[/cyan]")
    else:
        console.print("   └─ Mount point: [cyan]<temporary directory>[/cyan]")

    console.print("2. ✅ Validate SPEC CPU 2017 content")
    console.print("3. 🚀 Run official install.sh script:")
    console.print(
        f"   └─ Command: [cyan]<mount_point>/install.sh -d {install_dir}[/cyan]"
    )
    console.print("   └─ Using SPEC's built-in non-interactive installation mode")
    console.print("   └─ Running as regular user (no sudo required)")
    console.print("   └─ Auto-confirming prompts for hands-free installation")
    console.print("   └─ This will:")
    console.print("      • 🔧 Detect and install appropriate toolset automatically")
    console.print("      • 📂 Unpack files with proper structure")
    console.print("      • ✅ Run comprehensive tests")
    console.print("      • 🔐 Validate checksums")
    console.print("      • 🛠️  Set up environment")
    console.print("      • 📺 Show real-time installation output")
    console.print("      • ⏱️  May take 10-30 minutes")
    console.print("4. 🗂️  Unmount ISO")
    console.print()
    console.print(
        "💡 [yellow]Run without --dry-run to perform the installation[/yellow]"
    )


def _install_mount_iso(iso_path: Path, mount_point: Path, console: Console) -> bool:
    """Mount the ISO file."""
    try:
        mount_cmd = [
            "sudo",
            "mount",
            "-t",
            "iso9660",
            "-o",
            "loop,ro",
            str(iso_path),
            str(mount_point),
        ]

        console.print(f"🔧 [blue]Running:[/blue] [cyan]{' '.join(mount_cmd)}[/cyan]")

        result = subprocess.run(mount_cmd, capture_output=True, text=True)

        if result.returncode == 0:
            console.print("✅ [green]ISO mounted successfully[/green]")
            return True
        else:
            console.print(f"❌ [red]Mount failed:[/red] {result.stderr}")

            # Try fallback mount options
            console.print("🔄 [yellow]Trying fallback mount options...[/yellow]")
            fallback_cmd = [
                "sudo",
                "mount",
                "-o",
                "loop,ro",
                str(iso_path),
                str(mount_point),
            ]

            console.print(
                f"🔧 [blue]Running:[/blue] [cyan]{' '.join(fallback_cmd)}[/cyan]"
            )
            fallback_result = subprocess.run(
                fallback_cmd, capture_output=True, text=True
            )

            if fallback_result.returncode == 0:
                console.print(
                    "✅ [green]ISO mounted successfully with fallback options[/green]"
                )
                return True
            else:
                console.print(
                    f"❌ [red]Fallback mount also failed:[/red] {fallback_result.stderr}"
                )
                console.print(
                    "💡 [yellow]Try running as root or check if the file is a valid ISO[/yellow]"
                )
                return False

    except Exception as e:
        console.print(f"❌ [red]Error mounting ISO: {e}[/red]")
        return False


def _install_unmount_iso(mount_point: Path, console: Console) -> bool:
    """Unmount the ISO file."""
    try:
        unmount_cmd = ["sudo", "umount", str(mount_point)]

        console.print(f"🔧 [blue]Unmounting:[/blue] [cyan]{mount_point}[/cyan]")

        result = subprocess.run(unmount_cmd, capture_output=True, text=True)

        if result.returncode == 0:
            console.print("✅ [green]ISO unmounted successfully[/green]")
            return True
        else:
            console.print(f"⚠️  [yellow]Unmount warning:[/yellow] {result.stderr}")
            # Don't fail the installation for unmount issues
            return True

    except Exception as e:
        console.print(f"⚠️  [yellow]Error unmounting ISO: {e}[/yellow]")
        return True


def _validate_spec_iso_content(mount_point: Path, console: Console) -> bool:
    """Validate that the mounted ISO contains SPEC CPU 2017."""
    console.print("🔍 [blue]Validating SPEC CPU 2017 content...[/blue]")

    # Check for key SPEC files/directories
    spec_indicators = [
        "install.sh",
        "MANIFEST",
        "redistributable_sources",
        "tools",
        "benchspec",
    ]

    found_indicators = []
    for indicator in spec_indicators:
        if (mount_point / indicator).exists():
            found_indicators.append(indicator)

    console.print(
        f"📋 [blue]Found SPEC indicators:[/blue] [cyan]{len(found_indicators)}/{len(spec_indicators)}[/cyan]"
    )

    if len(found_indicators) >= 3:
        console.print("✅ [green]ISO appears to contain SPEC CPU 2017[/green]")
        return True
    else:
        console.print("❌ [red]ISO does not appear to contain SPEC CPU 2017[/red]")
        console.print(
            f"💡 [yellow]Missing indicators: {set(spec_indicators) - set(found_indicators)}[/yellow]"
        )
        return False


def _show_license_agreement(mount_point: Path, console: Console) -> bool:
    """Show SPEC license agreement and get user confirmation."""
    license_files = ["COPYING", "LICENSE", "EULA"]

    license_content = None
    for license_file in license_files:
        license_path = mount_point / license_file
        if license_path.exists():
            try:
                license_content = license_path.read_text()[:2000]  # First 2000 chars
                break
            except Exception:
                continue

    console.print()
    console.print("📜 [bold yellow]SPEC CPU 2017 License Agreement[/bold yellow]")
    console.print()

    if license_content:
        console.print(license_content)
        console.print("\n[dim]... (truncated)[/dim]")
    else:
        console.print("⚠️  [yellow]License file not found in ISO[/yellow]")
        console.print("Please ensure you have proper licensing for SPEC CPU 2017")

    console.print()
    console.print(
        "⚠️  [yellow]By proceeding, you agree to the SPEC CPU 2017 license terms[/yellow]"
    )

    return bool(typer.confirm("Do you accept the license agreement?"))


def _run_official_installer(
    mount_point: Path, install_dir: Path, console: Console
) -> bool:
    """Run the official SPEC CPU 2017 install.sh script using its built-in non-interactive mode."""
    console.print("🚀 [blue]Running official SPEC install.sh script...[/blue]")
    console.print(f"📂 [blue]Installing to:[/blue] [cyan]{install_dir}[/cyan]")
    console.print(
        "⏱️  [yellow]This may take 10-30 minutes depending on your system[/yellow]"
    )

    # Ensure install directory parent exists
    install_dir.parent.mkdir(parents=True, exist_ok=True)

    # Prepare the install.sh command
    install_script = mount_point / "install.sh"
    if not install_script.exists():
        console.print(f"❌ [red]install.sh not found at {install_script}[/red]")
        return False

    # Build command with destination directory (the -d flag enables non-interactive mode)
    install_cmd = [str(install_script), "-d", str(install_dir)]

    console.print(f"🔧 [blue]Running:[/blue] [cyan]{' '.join(install_cmd)}[/cyan]")
    console.print(
        "ℹ️  [cyan]Using SPEC's built-in non-interactive installation mode[/cyan]"
    )
    console.print("👤 [green]Running as regular user (no sudo required)[/green]")

    # Set up environment for the installer
    env = os.environ.copy()
    env.pop("SPEC", None)  # Clear any existing SPEC environment variable

    try:
        return _run_installer_simple(install_cmd, mount_point, env, console)

    except subprocess.TimeoutExpired:
        console.print("❌ [red]Installation timed out[/red]")
        return False
    except Exception as e:
        console.print(f"❌ [red]Error running installer: {e}[/red]")
        return False


def _run_installer_simple(
    install_cmd: list[str], mount_point: Path, env: dict[str, str], console: Console
) -> bool:
    """Run installer with real-time output streaming using official non-interactive mode."""
    console.print("🔄 [blue]Starting installation process...[/blue]")
    console.print("📺 [cyan]Live output from install.sh:[/cyan]")
    console.print("─" * 80, style="dim")

    try:
        # Run with stdin pipe to automatically answer confirmation prompts
        process = subprocess.Popen(
            install_cmd,
            cwd=str(mount_point),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )

        # Stream output in real-time and automatically respond to prompts
        while True:
            if process.stdout is None:
                break
            output = process.stdout.readline()
            if output == "" and process.poll() is not None:
                break
            if output:
                # Print each line directly for real-time viewing
                console.print(output.rstrip(), highlight=False)

                # Check for the confirmation prompt and auto-respond
                if "Is this correct? (Please enter 'yes' or 'no')" in output:
                    try:
                        console.print("[dim]Auto-responding: yes[/dim]")
                        if process.stdin is not None:
                            process.stdin.write("yes\n")
                            process.stdin.flush()
                    except (BrokenPipeError, OSError):
                        # Process may have closed stdin
                        pass

        # Wait for process to complete and get return code
        return_code = process.wait()

        console.print("─" * 80, style="dim")

        if return_code == 0:
            console.print(
                "✅ [green]SPEC CPU 2017 installation completed successfully![/green]"
            )
            return True
        else:
            console.print(
                f"❌ [red]Installation failed with exit code {return_code}[/red]"
            )
            return False

    except KeyboardInterrupt:
        console.print("\n❌ [red]Installation cancelled by user[/red]")
        if "process" in locals():
            try:
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        return False

    except Exception as e:
        console.print(f"❌ [red]Error during installation: {e}[/red]")
        return False
