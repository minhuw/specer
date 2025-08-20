"""Unified logging system for specer using Rich as loguru handler.

This module provides a beautiful logging system that integrates Rich formatting
with loguru's powerful logging capabilities. It allows you to distinguish between
specer operations and SPEC CPU output using different styling.

Usage:
    from specer.logging import setup_logging, logger

    setup_logging(verbose=True)
    logger.info("ℹ️  This is a specer info message")
    logger.warning("⚠️  This is a specer warning message")
    logger.error("❌ This is a specer error message")
    logger.debug("🐛 This is a debug message")
    logger.info("[dim]This is SPEC output (dimmed)[/dim]")

The system automatically:
- Uses Rich formatting for beautiful output
- Distinguishes specer vs SPEC messages with different styles
- Respects verbose/quiet flags
- Shows timestamps, levels, and paths in verbose mode
"""

from typing import Any

from loguru import logger
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.theme import Theme

# Custom theme for specer
SPECR_THEME = Theme(
    {
        "specer.info": "cyan",
        "specer.success": "green",
        "specer.warning": "yellow",
        "specer.error": "red",
        "specer.debug": "dim cyan",
        "spec": "magenta",
        "spec.output": "dim white",
        "spec.error": "red",
        "spec.warning": "yellow",
    }
)

console = Console(theme=SPECR_THEME, stderr=True)


def setup_logging(verbose: bool = False, quiet: bool = False) -> None:
    """Set up unified logging with rich and loguru.

    Args:
        verbose: Enable verbose logging
        quiet: Suppress non-essential output
    """
    # Remove default logger
    logger.remove()

    # Determine log level
    if quiet:
        log_level = "ERROR"
    elif verbose:
        log_level = "DEBUG"
    else:
        log_level = "INFO"

    # Add rich handler to loguru
    logger.add(
        RichHandler(
            console=console,
            rich_tracebacks=True,
            tracebacks_show_locals=verbose,
            show_time=verbose,
            show_level=verbose,
            show_path=verbose,
        ),
        level=log_level,
        format="{message}",
    )


def specer_info(message: str, **kwargs: Any) -> None:
    """Log info message for specer operations."""
    if not getattr(logger, "_specer_quiet", False):
        logger.info(f"ℹ️  {message}", **kwargs)


def specer_success(message: str, **kwargs: Any) -> None:
    """Log success message for specer operations."""
    if not getattr(logger, "_specer_quiet", False):
        logger.info(f"✅ {message}", **kwargs)


def specer_warning(message: str, **kwargs: Any) -> None:
    """Log warning message for specer operations."""
    logger.warning(f"⚠️  {message}", **kwargs)


def specer_error(message: str, **kwargs: Any) -> None:
    """Log error message for specer operations."""
    logger.error(f"❌ {message}", **kwargs)


def specer_debug(message: str, **kwargs: Any) -> None:
    """Log debug message for specer operations."""
    if getattr(logger, "_specer_verbose", False):
        logger.debug(f"🐛 {message}", **kwargs)


def spec_output(message: str, **kwargs: Any) -> None:
    """Log SPEC CPU output (distinguished from specer output)."""
    if getattr(logger, "_specer_verbose", False):
        logger.info(f"[dim]{message}[/dim]", **kwargs)


def spec_error(message: str, **kwargs: Any) -> None:
    """Log SPEC CPU error output."""
    logger.error(f"SPEC Error: {message}", **kwargs)


def spec_warning(message: str, **kwargs: Any) -> None:
    """Log SPEC CPU warning output."""
    logger.warning(f"SPEC Warning: {message}", **kwargs)


def create_panel(
    title: str, content: str, border_style: str = "blue", **kwargs: Any
) -> Panel:
    """Create a rich panel with consistent styling."""
    return Panel(
        content, title=f"[bold]{title}[/bold]", border_style=border_style, **kwargs
    )


def log_command_start(
    command: str, args: list[str] | None = None, **kwargs: Any
) -> None:
    """Log the start of a command execution."""
    cmd_str = f"{' '.join([command] + (args or []))}"
    specer_info(f"Starting command: [bold]{cmd_str}[/bold]", **kwargs)


def log_command_complete(command: str, return_code: int, **kwargs: Any) -> None:
    """Log the completion of a command execution."""
    if return_code == 0:
        specer_success(
            f"Command completed successfully: [bold]{command}[/bold]", **kwargs
        )
    else:
        specer_error(
            f"Command failed with code {return_code}: [bold]{command}[/bold]", **kwargs
        )


# Export console for direct use
__all__ = [
    "setup_logging",
    "specer_info",
    "specer_success",
    "specer_warning",
    "specer_error",
    "specer_debug",
    "spec_output",
    "spec_error",
    "spec_warning",
    "create_panel",
    "log_command_start",
    "log_command_complete",
    "console",
    "logger",
]
