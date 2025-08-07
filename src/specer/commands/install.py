"""Install command for SPEC CPU 2017 from local ISO file."""

import contextlib
import subprocess
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn


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

    This command mounts a SPEC CPU 2017 ISO file and copies its contents
    to the installation directory. It requires root privileges for mounting
    and installation.

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

            # Show license agreement
            if not accept_license:
                if not _show_license_agreement(mount_point, console):
                    raise typer.Exit(1)

            # Copy files to installation directory
            if not _install_copy_files(mount_point, install_dir, console):
                raise typer.Exit(1)

            # Set up environment
            _install_setup_environment(install_dir, console)

            console.print()
            console.print(
                "✅ [bold green]Installation completed successfully![/bold green]"
            )
            console.print(
                f"📁 [blue]Installation directory:[/blue] [cyan]{install_dir}[/cyan]"
            )
            console.print()
            console.print("📝 [bold]Next steps:[/bold]")
            console.print(
                f"   1. Add to PATH: [cyan]export PATH={install_dir}/bin:$PATH[/cyan]"
            )
            console.print(
                f"   2. Set SPEC_ROOT: [cyan]export SPEC_ROOT={install_dir}[/cyan]"
            )
            console.print(
                "   3. Source environment: [cyan]source $SPEC_ROOT/shrc[/cyan]"
            )
            console.print("   4. Run setup: [cyan]specer setup[/cyan]")

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
    console.print("3. 📜 Show license agreement (unless --accept-license)")
    console.print(f"4. 📂 Copy files to: [cyan]{install_dir}[/cyan]")
    console.print("5. 🔧 Set up environment files")
    console.print("6. 🗂️  Unmount ISO")
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


def _install_copy_files(mount_point: Path, install_dir: Path, console: Console) -> bool:
    """Copy files from mounted ISO to installation directory."""
    console.print(f"📂 [blue]Copying files to:[/blue] [cyan]{install_dir}[/cyan]")

    # Create installation directory
    install_dir.mkdir(parents=True, exist_ok=True)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Copying SPEC CPU 2017 files...", total=None)

        try:
            # Use rsync if available for better progress, otherwise use cp
            try:
                copy_cmd = [
                    "sudo",
                    "rsync",
                    "-av",
                    "--progress",
                    f"{mount_point}/",
                    str(install_dir),
                ]
                result = subprocess.run(copy_cmd, capture_output=True, text=True)
            except FileNotFoundError:
                # Fallback to cp if rsync is not available
                copy_cmd = ["sudo", "cp", "-r", f"{mount_point}/.", str(install_dir)]
                result = subprocess.run(copy_cmd, capture_output=True, text=True)

            progress.update(task, completed=True)

            if result.returncode == 0:
                console.print("✅ [green]Files copied successfully[/green]")
                return True
            else:
                console.print(f"❌ [red]Copy failed:[/red] {result.stderr}")
                return False

        except Exception as e:
            progress.update(task, completed=True)
            console.print(f"❌ [red]Error copying files: {e}[/red]")
            return False


def _install_setup_environment(install_dir: Path, console: Console) -> None:
    """Set up SPEC environment files."""
    console.print("🔧 [blue]Setting up environment...[/blue]")

    # Make scripts executable
    bin_dir = install_dir / "bin"
    if bin_dir.exists():
        try:
            subprocess.run(["sudo", "chmod", "+x", "-R", str(bin_dir)], check=True)
            console.print("✅ [green]Made bin scripts executable[/green]")
        except subprocess.CalledProcessError:
            console.print("⚠️  [yellow]Could not make bin scripts executable[/yellow]")

    # Set ownership to current user if possible
    import os

    current_user = os.getenv("USER")
    if current_user:
        try:
            subprocess.run(
                [
                    "sudo",
                    "chown",
                    "-R",
                    f"{current_user}:{current_user}",
                    str(install_dir),
                ],
                check=True,
            )
            console.print(f"✅ [green]Changed ownership to {current_user}[/green]")
        except subprocess.CalledProcessError:
            console.print("⚠️  [yellow]Could not change ownership[/yellow]")
