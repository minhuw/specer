"""Tests for the CLI module."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from specer.cli import _build_runcpu_command, app

# Get SPEC path from TEST_SPEC_PATH environment variable (set by direnv/env.local)
TEST_SPEC_PATH = os.environ.get("TEST_SPEC_PATH")


def get_test_spec_path() -> str:
    """Get the spec path for testing from TEST_SPEC_PATH environment variable."""
    if not TEST_SPEC_PATH:
        raise RuntimeError(
            "TEST_SPEC_PATH environment variable not set. "
            "Please set TEST_SPEC_PATH in your env.local file."
        )
    return TEST_SPEC_PATH


class TestCLIApp:
    """Test class for CLI application."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_spec_path_environment_variable(self) -> None:
        """Test that SPEC_PATH environment variable is used as fallback."""
        import os
        from pathlib import Path

        from specer.cli import _validate_and_get_spec_root

        # Test with SPEC_PATH set
        old_spec_path = os.environ.get("SPEC_PATH")
        try:
            os.environ["SPEC_PATH"] = "/test/spec/path"
            result = _validate_and_get_spec_root(None)
            assert result == Path("/test/spec/path")
        finally:
            # Restore original value
            if old_spec_path is not None:
                os.environ["SPEC_PATH"] = old_spec_path
            else:
                os.environ.pop("SPEC_PATH", None)

    def test_cli_help(self) -> None:
        """Test that CLI help works."""
        result = self.runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "A CLI wrapper for SPEC CPU 2017 benchmark suite" in result.stdout

    def test_cli_version(self) -> None:
        """Test that CLI version works."""
        result = self.runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "specer 0.1.0" in result.stdout

    def test_compile_help(self) -> None:
        """Test compile command help."""
        result = self.runner.invoke(app, ["compile", "--help"])
        assert result.exit_code == 0
        assert "Compile SPEC CPU 2017 benchmarks" in result.stdout

    def test_run_help(self) -> None:
        """Test run command help."""
        result = self.runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "Run SPEC CPU 2017 benchmarks" in result.stdout

    def test_setup_help(self) -> None:
        """Test setup command help."""
        result = self.runner.invoke(app, ["setup", "--help"])
        assert result.exit_code == 0
        assert "Setup SPEC CPU 2017 benchmarks" in result.stdout

    def test_clean_help(self) -> None:
        """Test clean command help."""
        result = self.runner.invoke(app, ["clean", "--help"])
        assert result.exit_code == 0
        assert "Clean SPEC CPU 2017 benchmark build directories" in result.stdout


class TestCompileCommand:
    """Test class for compile command."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_compile_missing_config(self) -> None:
        """Test compile command without config file."""
        result = self.runner.invoke(app, ["compile", "519.lbm_r"])
        assert result.exit_code == 2
        assert "Missing option '--config'" in result.stderr

    def test_compile_missing_benchmarks(self) -> None:
        """Test compile command without benchmarks."""
        result = self.runner.invoke(app, ["compile", "--config", "test.cfg"])
        assert result.exit_code == 2
        assert "Missing argument 'BENCHMARKS...'" in result.stderr

    @patch("specer.cli._execute_runcpu")
    @patch("pathlib.Path.exists")
    def test_compile_basic(
        self, mock_exists: MagicMock, mock_execute: MagicMock
    ) -> None:
        """Test basic compile command."""
        mock_exists.return_value = True  # Mock runcpu path exists
        spec_path = get_test_spec_path()
        result = self.runner.invoke(
            app,
            [
                "compile",
                "519.lbm_r",
                "--config",
                "test.cfg",
                "--spec-root",
                spec_path,
            ],
        )
        assert result.exit_code == 0
        mock_execute.assert_called_once()

    @patch("pathlib.Path.exists")
    def test_compile_dry_run(self, mock_exists: MagicMock) -> None:
        """Test compile command with dry run."""
        mock_exists.return_value = True  # Mock runcpu path exists
        spec_path = get_test_spec_path()
        result = self.runner.invoke(
            app,
            [
                "compile",
                "519.lbm_r",
                "--config",
                "test.cfg",
                "--spec-root",
                spec_path,
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "Would execute:" in result.stdout
        assert (
            f"{spec_path}/bin/runcpu --action build --config test.cfg --tune base 519.lbm_r"
            in result.stdout
        )

    def test_compile_with_options(self) -> None:
        """Test compile command with various options using environment SPEC path."""
        spec_path = get_test_spec_path()

        result = self.runner.invoke(
            app,
            [
                "compile",
                "intspeed",
                "--config",
                "test.cfg",
                "--spec-root",
                spec_path,
                "--tune",
                "all",
                "--rebuild",
                "--verbose",
                "--parallel-test",
                "4",
                "--ignore-errors",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        expected_cmd = (
            f"{spec_path}/bin/runcpu --action build --config test.cfg --tune all --verbose "
            "--rebuild --parallel_test 4 --ignore_errors intspeed"
        )
        assert expected_cmd in result.stdout

    def test_compile_with_spec_root(self) -> None:
        """Test compile command with spec root."""
        result = self.runner.invoke(
            app,
            [
                "compile",
                "519.lbm_r",
                "--config",
                "test.cfg",
                "--spec-root",
                "/nonexistent/spec/path",
                "--dry-run",
            ],
        )
        assert result.exit_code == 1  # Should fail because path doesn't exist
        assert "runcpu not found at" in result.stderr


class TestRunCommand:
    """Test class for run command."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_run_dry_run_basic(self) -> None:
        """Test basic run command with dry run using environment SPEC path."""
        spec_path = get_test_spec_path()

        result = self.runner.invoke(
            app,
            [
                "run",
                "519.lbm_r",
                "--config",
                "test.cfg",
                "--spec-root",
                spec_path,
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "Would execute:" in result.stdout
        assert (
            f"{spec_path}/bin/runcpu --action run --config test.cfg --tune base --size ref 519.lbm_r"
            in result.stdout
        )

    def test_run_with_rate_options(self) -> None:
        """Test run command with rate benchmark options."""
        result = self.runner.invoke(
            app,
            [
                "run",
                "intrate",
                "--config",
                "test.cfg",
                "--copies",
                "16",
                "--reportable",
                "--iterations",
                "3",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        expected_cmd = (
            "runcpu --action run --config test.cfg --tune base --size ref "
            "--copies 16 --iterations 3 --reportable intrate"
        )
        assert expected_cmd in result.stdout

    def test_run_with_speed_options(self) -> None:
        """Test run command with speed benchmark options."""
        result = self.runner.invoke(
            app,
            [
                "run",
                "fpspeed",
                "--config",
                "test.cfg",
                "--threads",
                "8",
                "--noreportable",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        expected_cmd = (
            "runcpu --action run --config test.cfg --tune base --size ref "
            "--threads 8 --noreportable fpspeed"
        )
        assert expected_cmd in result.stdout


class TestBuildRuncpuCommand:
    """Test class for _build_runcpu_command function."""

    def test_build_basic_command(self) -> None:
        """Test building basic runcpu command."""
        cmd = _build_runcpu_command(
            action="build",
            benchmarks=["519.lbm_r"],
            config="test.cfg",
        )
        expected = ["runcpu", "--action", "build", "--config", "test.cfg", "519.lbm_r"]
        assert cmd == expected

    def test_build_command_with_spec_root(self) -> None:
        """Test building command with spec root."""
        spec_path = get_test_spec_path()
        spec_root = Path(spec_path)
        with patch.object(Path, "exists", return_value=True):
            cmd = _build_runcpu_command(
                action="build",
                benchmarks=["519.lbm_r"],
                config="test.cfg",
                spec_root=spec_root,
            )
        expected = [
            f"{spec_path}/bin/runcpu",
            "--action",
            "build",
            "--config",
            "test.cfg",
            "519.lbm_r",
        ]
        assert cmd == expected

    def test_build_command_with_all_options(self) -> None:
        """Test building command with all possible options."""
        cmd = _build_runcpu_command(
            action="run",
            benchmarks=["intrate"],
            config="test.cfg",
            tune="all",
            verbose=True,
            rebuild=True,
            parallel_test=4,
            ignore_errors=True,
            size="ref",
            copies=16,
            threads=8,
            iterations=3,
            reportable=True,
        )
        expected = [
            "runcpu",
            "--action",
            "run",
            "--config",
            "test.cfg",
            "--tune",
            "all",
            "--size",
            "ref",
            "--copies",
            "16",
            "--threads",
            "8",
            "--iterations",
            "3",
            "--reportable",
            "--verbose",
            "--rebuild",
            "--parallel_test",
            "4",
            "--ignore_errors",
            "intrate",
        ]
        assert cmd == expected

    def test_build_command_multiple_benchmarks(self) -> None:
        """Test building command with multiple benchmarks."""
        cmd = _build_runcpu_command(
            action="build",
            benchmarks=["519.lbm_r", "500.perlbench_r", "502.gcc_r"],
            config="test.cfg",
        )
        expected = [
            "runcpu",
            "--action",
            "build",
            "--config",
            "test.cfg",
            "519.lbm_r",
            "500.perlbench_r",
            "502.gcc_r",
        ]
        assert cmd == expected

    def test_build_update_command(self) -> None:
        """Test building update command."""
        cmd = _build_runcpu_command(
            action="update",
            benchmarks=[],
            config="",
        )
        expected = ["runcpu", "--update"]
        assert cmd == expected

    def test_build_update_command_with_spec_root(self) -> None:
        """Test building update command with spec_root."""

        # Create a fake spec_root directory structure for testing
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as temp_dir:
            spec_root = Path(temp_dir)
            bin_dir = spec_root / "bin"
            bin_dir.mkdir(parents=True)
            runcpu_path = bin_dir / "runcpu"
            runcpu_path.touch()

            cmd = _build_runcpu_command(
                action="update",
                benchmarks=[],
                config="",
                spec_root=spec_root,
                verbose=True,
            )
            expected = [str(runcpu_path), "--update", "--verbose"]
            assert cmd == expected


class TestSetupAndCleanCommands:
    """Test class for setup and clean commands."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_setup_dry_run(self) -> None:
        """Test setup command with dry run."""
        spec_path = get_test_spec_path()
        result = self.runner.invoke(
            app,
            [
                "setup",
                "519.lbm_r",
                "--config",
                "test.cfg",
                "--spec-root",
                spec_path,
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "Would execute:" in result.stdout
        assert (
            f"{spec_path}/bin/runcpu --action setup --config test.cfg --tune base 519.lbm_r"
            in result.stdout
        )

    def test_clean_dry_run(self) -> None:
        """Test clean command with dry run."""
        spec_path = get_test_spec_path()
        result = self.runner.invoke(
            app,
            [
                "clean",
                "all",
                "--config",
                "test.cfg",
                "--spec-root",
                spec_path,
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "Would execute:" in result.stdout
        assert (
            f"{spec_path}/bin/runcpu --action clean --config test.cfg all"
            in result.stdout
        )


# TestSpecRootResolution class removed since spec_root is now mandatory


class TestUpdateCommand:
    """Test class for update command."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_update_help(self) -> None:
        """Test update command help."""
        result = self.runner.invoke(app, ["update", "--help"])
        assert result.exit_code == 0
        assert "Update SPEC CPU 2017 installation" in result.stdout

    def test_update_dry_run(self) -> None:
        """Test update command with dry-run using environment SPEC path."""
        spec_path = get_test_spec_path()

        result = self.runner.invoke(
            app, ["update", "--spec-root", spec_path, "--dry-run"]
        )
        assert result.exit_code == 0
        assert "Would execute:" in result.stdout
        assert f"{spec_path}/bin/runcpu --update" in result.stdout

    def test_update_with_spec_root_dry_run(self) -> None:
        """Test update command with spec-root and dry-run."""
        result = self.runner.invoke(
            app,
            [
                "update",
                "--spec-root",
                "/nonexistent/spec/path",
                "--dry-run",
            ],
        )
        # Should fail because path doesn't exist, but it's in dry-run mode
        assert result.exit_code == 1
        assert "runcpu not found at /nonexistent/spec/path/bin/runcpu" in result.stderr

    def test_update_with_verbose_dry_run(self) -> None:
        """Test update command with verbose and dry-run using environment SPEC path."""
        spec_path = get_test_spec_path()

        result = self.runner.invoke(
            app,
            [
                "update",
                "--spec-root",
                spec_path,
                "--verbose",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "Would execute:" in result.stdout
        assert f"{spec_path}/bin/runcpu --update --verbose" in result.stdout


class TestBenchmarkNameConversion:
    """Test class for benchmark name conversion functionality."""

    def test_convert_simple_names_speed(self) -> None:
        """Test converting simple names to speed versions."""
        from specer.cli import _convert_benchmark_names

        result = _convert_benchmark_names(["gcc", "lbm"], prefer_speed=True)
        assert result == ["602.gcc_s", "619.lbm_s"]

    def test_convert_simple_names_rate(self) -> None:
        """Test converting simple names to rate versions."""
        from specer.cli import _convert_benchmark_names

        result = _convert_benchmark_names(["gcc", "lbm"], prefer_rate=True)
        assert result == ["502.gcc_r", "519.lbm_r"]

    def test_convert_mixed_names(self) -> None:
        """Test converting mix of simple and full names."""
        from specer.cli import _convert_benchmark_names

        result = _convert_benchmark_names(
            ["gcc", "519.lbm_r", "perlbench"], prefer_speed=True
        )
        assert result == ["602.gcc_s", "519.lbm_r", "600.perlbench_s"]

    def test_convert_suite_names_preserved(self) -> None:
        """Test that suite names are preserved."""
        from specer.cli import _convert_benchmark_names

        result = _convert_benchmark_names(
            ["intspeed", "fprate", "all"], prefer_speed=True
        )
        assert result == ["intspeed", "fprate", "all"]

    def test_convert_unknown_names_preserved(self) -> None:
        """Test that unknown names are preserved."""
        from specer.cli import _convert_benchmark_names

        result = _convert_benchmark_names(["unknown_benchmark"], prefer_speed=True)
        assert result == ["unknown_benchmark"]

    def test_detect_suite_preference_speed(self) -> None:
        """Test detecting speed preference from benchmarks."""
        from specer.cli import _detect_suite_preference

        prefer_speed, prefer_rate = _detect_suite_preference(["602.gcc_s", "intspeed"])
        assert prefer_speed is True
        assert prefer_rate is False

    def test_detect_suite_preference_rate(self) -> None:
        """Test detecting rate preference from benchmarks."""
        from specer.cli import _detect_suite_preference

        prefer_speed, prefer_rate = _detect_suite_preference(["502.gcc_r", "fprate"])
        assert prefer_speed is False
        assert prefer_rate is True

    def test_detect_suite_preference_mixed(self) -> None:
        """Test detecting preference with mixed benchmarks."""
        from specer.cli import _detect_suite_preference

        prefer_speed, prefer_rate = _detect_suite_preference(["602.gcc_s", "519.lbm_r"])
        assert prefer_speed is False
        assert prefer_rate is False

    def test_convert_default_to_speed(self) -> None:
        """Test that default conversion uses speed versions."""
        from specer.cli import _convert_benchmark_names

        result = _convert_benchmark_names(["gcc", "lbm"])
        assert result == ["602.gcc_s", "619.lbm_s"]


class TestBenchmarkNameOptions:
    """Test class for --speed and --rate options in commands."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_compile_with_speed_option(self) -> None:
        """Test compile command with --speed option."""
        result = self.runner.invoke(
            app, ["compile", "gcc", "--config", "test.cfg", "--speed", "--dry-run"]
        )
        assert result.exit_code == 0
        assert "602.gcc_s" in result.stdout
        assert "Converted benchmark names" in result.stdout

    def test_compile_with_rate_option(self) -> None:
        """Test compile command with --rate option."""
        result = self.runner.invoke(
            app, ["compile", "gcc", "--config", "test.cfg", "--rate", "--dry-run"]
        )
        assert result.exit_code == 0
        assert "502.gcc_r" in result.stdout
        assert "Converted benchmark names" in result.stdout

    def test_compile_speed_rate_mutually_exclusive(self) -> None:
        """Test that --speed and --rate are mutually exclusive."""
        result = self.runner.invoke(
            app, ["compile", "gcc", "--config", "test.cfg", "--speed", "--rate"]
        )
        assert result.exit_code == 1
        assert "mutually exclusive" in result.stderr

    def test_run_with_speed_option(self) -> None:
        """Test run command with --speed option."""
        result = self.runner.invoke(
            app, ["run", "gcc", "--config", "test.cfg", "--speed", "--dry-run"]
        )
        assert result.exit_code == 0
        assert "602.gcc_s" in result.stdout

    def test_setup_with_rate_option(self) -> None:
        """Test setup command with --rate option."""
        result = self.runner.invoke(
            app, ["setup", "gcc", "--config", "test.cfg", "--rate", "--dry-run"]
        )
        assert result.exit_code == 0
        assert "502.gcc_r" in result.stdout

    def test_clean_with_speed_option(self) -> None:
        """Test clean command with --speed option."""
        result = self.runner.invoke(
            app, ["clean", "gcc", "--config", "test.cfg", "--speed", "--dry-run"]
        )
        assert result.exit_code == 0
        assert "602.gcc_s" in result.stdout

    def test_auto_detection_with_rate_benchmark(self) -> None:
        """Test auto-detection when rate benchmark is present."""
        result = self.runner.invoke(
            app, ["compile", "gcc", "519.lbm_r", "--config", "test.cfg", "--dry-run"]
        )
        assert result.exit_code == 0
        assert "502.gcc_r" in result.stdout
        assert "519.lbm_r" in result.stdout

    def test_full_spec_names_preserved(self) -> None:
        """Test that full SPEC names are preserved even with options."""
        result = self.runner.invoke(
            app,
            ["compile", "502.gcc_r", "--config", "test.cfg", "--speed", "--dry-run"],
        )
        assert result.exit_code == 0
        assert "502.gcc_r" in result.stdout
        assert "Converted benchmark names" not in result.stdout

    def test_mixed_simple_and_full_names(self) -> None:
        """Test mixed simple and full benchmark names."""
        result = self.runner.invoke(
            app,
            [
                "compile",
                "gcc",
                "519.lbm_r",
                "perlbench",
                "--config",
                "test.cfg",
                "--speed",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "602.gcc_s" in result.stdout
        assert "519.lbm_r" in result.stdout
        assert "600.perlbench_s" in result.stdout


class TestCoresAndConfigGeneration:
    """Test class for --cores argument and config generation functionality."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_run_with_cores_speed_benchmark(self) -> None:
        """Test run command with --cores for speed benchmarks."""
        result = self.runner.invoke(
            app,
            [
                "run",
                "gcc",
                "--config",
                "test.cfg",
                "--speed",
                "--cores",
                "8",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "602.gcc_s" in result.stdout
        assert "Using --cores=8 as threads for speed benchmarks" in result.stdout
        assert "--threads 8" in result.stdout

    def test_run_with_cores_rate_benchmark(self) -> None:
        """Test run command with --cores for rate benchmarks."""
        result = self.runner.invoke(
            app,
            [
                "run",
                "gcc",
                "--config",
                "test.cfg",
                "--rate",
                "--cores",
                "16",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "502.gcc_r" in result.stdout
        assert "Using --cores=16 as copies for rate benchmarks" in result.stdout
        assert "--copies 16" in result.stdout

    def test_run_with_cores_mixed_benchmarks(self) -> None:
        """Test run command with --cores for mixed speed/rate benchmarks."""
        result = self.runner.invoke(
            app,
            [
                "run",
                "602.gcc_s",
                "502.gcc_r",
                "--config",
                "test.cfg",
                "--cores",
                "8",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "Warning: Mixed rate and speed benchmarks detected" in result.stderr
        assert "--copies 8" in result.stdout
        assert "--threads 8" in result.stdout

    def test_auto_generate_config_with_cores(self) -> None:
        """Test automatic config generation with --cores (no --generate-config needed)."""
        result = self.runner.invoke(app, ["run", "gcc", "--cores", "12", "--dry-run"])
        assert result.exit_code == 0
        assert "Auto-generated config file with 12 cores:" in result.stdout
        assert "602.gcc_s" in result.stdout

    def test_generate_config_with_cores(self) -> None:
        """Test config generation with specific cores (default behavior)."""
        result = self.runner.invoke(app, ["run", "gcc", "--cores", "12", "--dry-run"])
        assert result.exit_code == 0
        assert "Auto-generated config file with 12 cores:" in result.stdout
        assert "602.gcc_s" in result.stdout

    def test_generate_config_without_cores(self) -> None:
        """Test that config is auto-generated without explicit cores."""
        result = self.runner.invoke(app, ["run", "gcc", "--dry-run"])
        assert result.exit_code == 0
        assert "Auto-generated config file:" in result.stdout

    def test_spec_root_from_environment(self) -> None:
        """Test that spec_root is taken from environment variables when not provided."""
        result = self.runner.invoke(app, ["run", "gcc", "--cores", "8", "--dry-run"])
        assert (
            result.exit_code == 0
        )  # Should work because SPEC_PATH is set in environment
        assert "Auto-generated config file with 8 cores:" in result.stdout
        assert "602.gcc_s" in result.stdout

    def test_config_auto_generated(self) -> None:
        """Test that config is automatically generated when not provided."""
        spec_path = get_test_spec_path()

        result = self.runner.invoke(
            app, ["run", "gcc", "--spec-root", spec_path, "--dry-run"]
        )
        assert result.exit_code == 0  # Should work because config is auto-generated
        assert "Auto-generated config file:" in result.stdout
        assert "602.gcc_s" in result.stdout

    def test_explicit_config_skips_auto_generation(self) -> None:
        """Test that providing --config skips auto-generation."""
        spec_path = get_test_spec_path()
        result = self.runner.invoke(
            app,
            [
                "run",
                "gcc",
                "--config",
                "test.cfg",
                "--spec-root",
                spec_path,
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "Auto-generated config file:" not in result.stdout
        assert "--config test.cfg" in result.stdout

    def test_cores_auto_detection_speed(self) -> None:
        """Test that --cores auto-detects speed benchmark without explicit --speed."""
        result = self.runner.invoke(
            app,
            ["run", "602.gcc_s", "--config", "test.cfg", "--cores", "4", "--dry-run"],
        )
        assert result.exit_code == 0
        assert "Using --cores=4 as threads for speed benchmarks" in result.stdout

    def test_cores_auto_detection_rate(self) -> None:
        """Test that --cores auto-detects rate benchmark without explicit --rate."""
        result = self.runner.invoke(
            app,
            ["run", "502.gcc_r", "--config", "test.cfg", "--cores", "8", "--dry-run"],
        )
        assert result.exit_code == 0
        assert "Using --cores=8 as copies for rate benchmarks" in result.stdout

    def test_cores_default_behavior(self) -> None:
        """Test that --cores defaults to threads for unknown benchmark types."""
        result = self.runner.invoke(
            app,
            [
                "run",
                "unknown_bench",
                "--config",
                "test.cfg",
                "--cores",
                "6",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "Using --cores=6 as threads (default behavior)" in result.stdout

    def test_explicit_config_overrides_auto_generation(self) -> None:
        """Test that explicit --config takes precedence over auto-generation."""
        result = self.runner.invoke(
            app, ["run", "gcc", "--config", "test.cfg", "--cores", "8", "--dry-run"]
        )
        assert result.exit_code == 0
        assert "Auto-generated config file" not in result.stdout
        assert "--config test.cfg" in result.stdout
        assert "Using --cores=8 as threads" in result.stdout


class TestConfigTemplateGeneration:
    """Test class for config template generation functionality."""

    def test_detect_gcc_version(self) -> None:
        """Test GCC version detection."""
        from specer.cli import _detect_gcc_version

        version = _detect_gcc_version()
        # Should either return an integer >= 4 (reasonable GCC versions) or None
        if version is not None:
            assert isinstance(version, int)
            assert version >= 4  # Oldest supported GCC versions
            assert version <= 20  # Reasonable upper bound

    def test_generate_config_from_template_with_cores(self) -> None:
        """Test config generation function with cores parameter."""
        from pathlib import Path

        from specer.cli import _generate_config_from_template

        spec_path = get_test_spec_path()
        config_path = _generate_config_from_template(
            cores=16, spec_root=Path(spec_path), tune="base"
        )

        if config_path:  # Only test if template exists
            assert config_path.endswith(".cfg")
            with Path(config_path).open() as f:
                content = f.read()
            assert "16" in content  # Should contain the cores value

            # Test that label was updated to "specer"
            assert 'define label "specer"' in content

            # Test that tune setting was updated correctly
            assert "tune                 = base" in content and "(auto-set)" in content

            # Test GCC version detection - if we have GCC 10+, GCCge10 should be uncommented
            from specer.cli import _detect_gcc_version

            gcc_version = _detect_gcc_version()
            if gcc_version and gcc_version >= 10:
                assert (
                    "%define GCCge10" in content and "#%define GCCge10" not in content
                )
                assert "(auto-detected)" in content

            # Clean up
            Path(config_path).unlink()

    def test_generate_config_from_template_default_cores(self) -> None:
        """Test config generation function with default cores."""
        from pathlib import Path

        from specer.cli import _generate_config_from_template

        spec_path = get_test_spec_path()
        config_path = _generate_config_from_template(
            spec_root=Path(spec_path), tune="base"
        )

        if config_path:  # Only test if template exists
            assert config_path.endswith(".cfg")

            # Clean up
            Path(config_path).unlink()

    def test_generate_config_tune_settings(self) -> None:
        """Test config generation with different tune settings."""
        from pathlib import Path

        from specer.cli import _generate_config_from_template

        spec_path = get_test_spec_path()

        # Test different tune values
        tune_tests = [
            ("base", "tune                 = base"),
            ("peak", "tune                 = peak"),
            ("all", "tune                 = base,peak"),
        ]

        for tune_value, expected_line in tune_tests:
            config_path = _generate_config_from_template(
                cores=4, spec_root=Path(spec_path), tune=tune_value
            )

            if config_path:  # Only test if template exists
                with Path(config_path).open() as f:
                    content = f.read()
                assert expected_line in content
                assert "(auto-set)" in content

                # Clean up
                Path(config_path).unlink()


class TestResultParsing:
    """Test class for result parsing functionality."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_parse_results_integration(self) -> None:
        """Integration test for result parsing using environment SPEC path."""
        spec_path = get_test_spec_path()

        result = self.runner.invoke(
            app,
            [
                "run",
                "gcc",
                "--spec-root",
                spec_path,
                "--cores",
                "4",
                "--parse-results",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "Auto-generated config file" in result.stdout
        assert "Using --cores=4 as threads" in result.stdout
        assert f"{spec_path}/bin/runcpu" in result.stdout

    def test_parse_result_files_with_scores(self) -> None:
        """Test parsing runcpu output with scores."""
        from pathlib import Path

        from specer.cli import _parse_result_files

        sample_output = """
        Running 602.gcc_s refspeed (ref) base test-label (4 threads) [2023-01-01 12:00:00]
        Est. SPECspeed2017_int_base = 123.45
        Est. SPECspeed2017_int_peak = 145.67
        The result is in result/CPU2017.001.test.rsf
        The log for this run is in result/CPU2017.001.log
        Reports are in result/CPU2017.001.test.txt
        """

        spec_path = get_test_spec_path()
        result = _parse_result_files(sample_output, Path(spec_path))

        assert result is not None
        scores = result["scores"]
        assert "SPECspeed2017_int_base" in scores
        assert scores["SPECspeed2017_int_base"] == 123.45
        assert "SPECspeed2017_int_peak" in scores
        assert scores["SPECspeed2017_int_peak"] == 145.67
        assert result["log_file"] == "result/CPU2017.001.log"
        result_files = result["result_files"]
        assert len(result_files) >= 1
        assert any("CPU2017.001.test.rsf" in rf["path"] for rf in result_files)

    def test_parse_result_files_no_scores(self) -> None:
        """Test parsing runcpu output without scores."""
        from pathlib import Path

        from specer.cli import _parse_result_files

        sample_output = """
        Building 602.gcc_s base test-label
        Build successful
        """

        spec_path = get_test_spec_path()
        result = _parse_result_files(sample_output, Path(spec_path))

        # Should return None when no result files or scores found
        assert result is None

    def test_parse_result_files_with_result_files_only(self) -> None:
        """Test parsing runcpu output with only result files."""
        from pathlib import Path

        from specer.cli import _parse_result_files

        sample_output = """
        Build completed successfully
        The result is in result/CPU2017.002.ref.rsf
        Output written to result/CPU2017.002.ref.html
        """

        spec_path = get_test_spec_path()
        result = _parse_result_files(sample_output, Path(spec_path))

        assert result is not None
        assert len(result["result_files"]) >= 1
        assert result["scores"] == {}  # No scores in this output

    def test_read_result_file_text_format(self) -> None:
        """Test reading a text result file."""
        import tempfile
        from pathlib import Path

        from specer.cli import _read_result_file

        # Create a mock result file
        sample_content = """
        Est. SPECrate2017_fp_base = 67.8
        Est. SPECrate2017_fp_peak = 89.1

        Benchmark                   Copies  Seconds  Ratio
        503.bwaves_r                   16      234   123.4
        507.cactuBSSN_r                16      567   89.2
        """

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(sample_content)
            temp_path = f.name

        try:
            spec_path = get_test_spec_path()
            result = _read_result_file(temp_path, Path(spec_path))

            assert result is not None
            scores = result["scores"]
            assert "SPECrate2017_fp_base" in scores
            assert scores["SPECrate2017_fp_base"] == 67.8
            assert "SPECrate2017_fp_peak" in scores
            assert scores["SPECrate2017_fp_peak"] == 89.1
        finally:
            Path(temp_path).unlink()

    def test_read_result_file_not_found(self) -> None:
        """Test reading a non-existent result file."""
        from pathlib import Path

        from specer.cli import _read_result_file

        spec_path = get_test_spec_path()
        result = _read_result_file("/nonexistent/path/file.txt", Path(spec_path))

        assert result is None

    @patch("pathlib.Path.exists")
    def test_parse_results_option_in_run_command(self, mock_exists: MagicMock) -> None:
        """Test that run command accepts --parse-results option."""
        mock_exists.return_value = True  # Mock runcpu path exists

        spec_path = get_test_spec_path()
        result = self.runner.invoke(
            app,
            [
                "run",
                "gcc",
                "--spec-root",
                spec_path,
                "--cores",
                "4",
                "--parse-results",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "Auto-generated config file" in result.stdout


class TestExecuteRuncpu:
    """Test class for _execute_runcpu function."""

    @patch("specer.cli.subprocess.run")
    def test_execute_success(self, mock_run: MagicMock) -> None:
        """Test successful command execution."""
        from specer.cli import _execute_runcpu

        mock_run.return_value.returncode = 0

        _execute_runcpu(["runcpu", "--help"])

        mock_run.assert_called_once_with(
            ["runcpu", "--help"],
            check=False,
            text=True,
            capture_output=False,
        )

    @patch("specer.cli.subprocess.run")
    def test_execute_failure(self, mock_run: MagicMock) -> None:
        """Test failed command execution."""
        import typer

        from specer.cli import _execute_runcpu

        mock_run.return_value.returncode = 1

        with pytest.raises(typer.Exit) as exc_info:
            _execute_runcpu(["runcpu", "--invalid"])

        assert exc_info.value.exit_code == 1

    @patch("specer.cli.subprocess.run")
    def test_execute_file_not_found(self, mock_run: MagicMock) -> None:
        """Test command execution when file not found."""
        import typer

        from specer.cli import _execute_runcpu

        mock_run.side_effect = FileNotFoundError()

        with pytest.raises(typer.Exit) as exc_info:
            _execute_runcpu(["nonexistent_command"])

        assert exc_info.value.exit_code == 1

    @patch("specer.cli.subprocess.run")
    def test_execute_keyboard_interrupt(self, mock_run: MagicMock) -> None:
        """Test command execution with keyboard interrupt."""
        import typer

        from specer.cli import _execute_runcpu

        mock_run.side_effect = KeyboardInterrupt()

        with pytest.raises(typer.Exit) as exc_info:
            _execute_runcpu(["runcpu", "--help"])

        assert exc_info.value.exit_code == 130
