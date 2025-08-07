"""Topology command for displaying NUMA topology information."""

from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from specer.utils import validate_numa_topology


def topology_command(
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Show detailed topology information",
        ),
    ] = False,
) -> None:
    """Display NUMA topology and CPU information.

    This command shows available NUMA nodes, CPU cores, and their mapping.
    Useful for determining appropriate values for --numa-node and --cpu-cores options.

    Examples:
        specer topology                    # Show basic NUMA topology
        specer topology --verbose          # Show detailed information
    """
    console = Console()

    # Try to get NUMA topology
    topology = validate_numa_topology()

    if topology is None:
        console.print("❌ [red]NUMA topology not available[/red]")
        console.print("Possible reasons:")
        console.print("  • numactl is not installed")
        console.print("  • System does not support NUMA")
        console.print("  • No NUMA nodes configured")
        console.print()
        console.print("To install numactl:")
        console.print("  • Ubuntu/Debian: [cyan]sudo apt install numactl[/cyan]")
        console.print("  • RHEL/CentOS: [cyan]sudo yum install numactl[/cyan]")
        console.print("  • Fedora: [cyan]sudo dnf install numactl[/cyan]")
        raise typer.Exit(1)

    # Display topology information
    console.print()
    console.print(
        Panel.fit(
            "[bold blue]🖥️  NUMA Topology Information[/bold blue]", border_style="blue"
        )
    )

    # Summary table
    summary_table = Table(title="📊 System Summary", show_header=True)
    summary_table.add_column("Property", style="cyan")
    summary_table.add_column("Value", style="green")

    summary_table.add_row("Total NUMA Nodes", str(len(topology["nodes"])))
    summary_table.add_row("Available Nodes", ", ".join(map(str, topology["nodes"])))
    summary_table.add_row("Total CPU Cores", str(topology["total_cpus"]))

    console.print(summary_table)
    console.print()

    # NUMA nodes detail table
    if verbose:
        numa_table = Table(title="🔍 NUMA Nodes Detail", show_header=True)
        numa_table.add_column("NUMA Node", style="cyan", width=12)
        numa_table.add_column("CPU Cores", style="yellow")
        numa_table.add_column("Core Count", style="green", justify="center")

        for node_id in sorted(topology["nodes"]):
            cpus = topology["node_cpus"][node_id]
            cpu_str = (
                ", ".join(map(str, cpus)) if len(cpus) <= 8 else f"{cpus[0]}-{cpus[-1]}"
            )
            numa_table.add_row(str(node_id), cpu_str, str(len(cpus)))

        console.print(numa_table)
        console.print()

    # Usage examples
    examples_table = Table(title="💡 Usage Examples", show_header=True)
    examples_table.add_column("Command", style="cyan")
    examples_table.add_column("Description", style="white")

    if topology["nodes"]:
        node0 = topology["nodes"][0]
        node0_cpus = topology["node_cpus"][node0]
        cpu_range = (
            f"{node0_cpus[0]}-{node0_cpus[-1]}"
            if len(node0_cpus) > 1
            else str(node0_cpus[0])
        )

        examples_table.add_row(
            f"specer run gcc --numa-node {node0}",
            f"Bind to NUMA node {node0} (CPUs & memory)",
        )
        examples_table.add_row(
            f"specer run gcc --cpu-cores {cpu_range}", f"Bind to CPU cores {cpu_range}"
        )
        examples_table.add_row(
            f"specer run gcc --numa-node {node0} --cpu-cores {cpu_range}",
            f"Bind to NUMA node {node0} with specific cores",
        )

    console.print(examples_table)
