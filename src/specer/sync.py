"""EvalSync integration for specer."""

import os
import socket

from evalsync import ExperimentWorker
from loguru import logger
from rich.console import Console
from rich.panel import Panel

console = Console()


class SpecerEvalSyncWorker:
    """Wrapper for EvalSync worker with specer-specific functionality."""

    def __init__(self, verbose: bool = False):
        """Initialize the EvalSync worker using environment variables.

        Args:
            verbose: Whether to enable verbose logging

        Raises:
            ImportError: If evalsync is not available
            ValueError: If required environment variables are not set
        """

        # Always read from environment variables
        self.experiment_id = os.environ.get("EVALSYNC_EXPERIMENT_ID")
        self.client_id = os.environ.get("EVALSYNC_CLIENT_ID")

        # If no client_id is provided, use hostname as default
        if not self.client_id:
            self.client_id = socket.gethostname()

        if not self.experiment_id:
            raise ValueError(
                "EVALSYNC_EXPERIMENT_ID environment variable is required when using --sync"
            )

        self.verbose = verbose
        self.worker: ExperimentWorker | None = None

        if self.verbose:
            logger.info(
                f"Initializing EvalSync worker - Experiment: {self.experiment_id}, Client: {self.client_id}"
            )

    def initialize(self) -> None:
        """Initialize the EvalSync worker connection."""

        try:
            self.worker = ExperimentWorker(
                self.experiment_id, self.client_id, self.verbose
            )
            if self.verbose:
                console.print(
                    Panel(
                        f"✅ EvalSync worker initialized\n"
                        f"Experiment ID: {self.experiment_id}\n"
                        f"Client ID: {self.client_id}",
                        title="EvalSync Integration",
                        border_style="green",
                    )
                )
            else:
                console.print(
                    f"🔄 EvalSync worker connected (experiment: {self.experiment_id})"
                )
        except Exception as e:
            logger.error(f"Failed to initialize EvalSync worker: {e}")
            raise

    def ready(self) -> None:
        """Signal that the worker is ready (e.g., compilation complete)."""
        if not self.worker:
            return

        try:
            self.worker.ready()
            if self.verbose:
                console.print("📡 Sent READY signal to EvalSync manager", style="green")
            else:
                console.print("🟢 Ready - waiting for start signal...")
        except Exception as e:
            logger.error(f"Failed to send ready signal: {e}")
            raise

    def wait_for_start(self) -> None:
        """Wait for the start signal from the manager."""
        if not self.worker:
            return

        try:
            console.print("⏳ Waiting for start signal from EvalSync manager...")
            self.worker.wait_for_start()
            console.print(
                "🚀 Received start signal - beginning benchmark execution",
                style="green bold",
            )
        except Exception as e:
            logger.error(f"Failed to wait for start signal: {e}")
            raise

    def wait_for_stop(self) -> None:
        """Wait for the stop signal from the manager."""
        if not self.worker:
            return

        try:
            console.print("⏳ Waiting for stop signal from EvalSync manager...")
            self.worker.wait_for_stop()
            console.print(
                "🛑 Received stop signal - benchmark execution complete",
                style="green bold",
            )
        except Exception as e:
            logger.error(f"Failed to wait for stop signal: {e}")
            raise

    def cleanup(self) -> None:
        """Clean up the EvalSync worker connection."""
        if not self.worker:
            return

        try:
            self.worker.cleanup()
            if self.verbose:
                console.print("🧹 EvalSync worker cleaned up", style="dim")
        except Exception as e:
            logger.warning(f"Failed to cleanup EvalSync worker: {e}")


def create_evalsync_worker(
    verbose: bool = False,
) -> SpecerEvalSyncWorker | None:
    """Create an EvalSync worker if evalsync is available.

    Args:
        experiment_id: Ignored (kept for API compatibility)
        client_id: Ignored (kept for API compatibility)
        verbose: Whether to enable verbose logging

    Returns:
        SpecerEvalSyncWorker instance if evalsync is available and environment variables are set, None otherwise
    """

    try:
        worker = SpecerEvalSyncWorker(verbose)
        worker.initialize()
        return worker
    except Exception as e:
        logger.error(f"Failed to create EvalSync worker: {e}")
        return None
