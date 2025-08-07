"""Result parsing functionality for SPEC CPU 2017 output."""

import re
from pathlib import Path
from typing import Any

import typer


def parse_result_files(output: str) -> dict[str, Any] | None:
    """Parse runcpu output to find result files and extract scores.

    Args:
        output: The stdout/stderr output from runcpu command

    Returns:
        Dictionary containing result information, or None if parsing fails
    """
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


def read_result_file(file_path: str, spec_root: Path) -> dict[str, Any] | None:
    """Read and parse a SPEC result file to extract scores.

    Args:
        file_path: Path to the result file
        spec_root: Path to SPEC installation directory

    Returns:
        Dictionary containing extracted scores and metrics
    """
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

        # Determine file type and parse accordingly
        # Prioritize RSF format for most accurate and complete data
        is_rsf_file = file_path.endswith(".rsf")

        if is_rsf_file:
            # RSF (Raw Spec File) format parsing
            patterns = {
                # Suite-level scores in RSF format
                "suite_base_mean": r"spec\.cpu2017\.basemean:\s*([\d.]+)",
                "suite_peak_mean": r"spec\.cpu2017\.peakmean:\s*([\d.]+)",
                "suite_base_energy": r"spec\.cpu2017\.baseenergymean:\s*([\d.]+)",
                "suite_peak_energy": r"spec\.cpu2017\.peakenergymean:\s*([\d.]+)",
                # Individual benchmark results in RSF format - detailed results structure
                # Format: spec.cpu2017.results.648_exchange2_s.base.000.ratio: 12.380557
                "detailed_ratio": r"spec\.cpu2017\.results\.(\d{3}_\w+(?:_[rs])?)\.(?:base|peak)\.000\.ratio:\s*([\d.]+)",
                "detailed_time": r"spec\.cpu2017\.results\.(\d{3}_\w+(?:_[rs])?)\.(?:base|peak)\.000\.reported_sec:\s*([\d.]+)",
                "detailed_reference": r"spec\.cpu2017\.results\.(\d{3}_\w+(?:_[rs])?)\.(?:base|peak)\.000\.reference:\s*([\d.]+)",
                "detailed_copies": r"spec\.cpu2017\.results\.(\d{3}_\w+(?:_[rs])?)\.(?:base|peak)\.000\.copies:\s*([\d.]+)",
                "detailed_threads": r"spec\.cpu2017\.results\.(\d{3}_\w+(?:_[rs])?)\.(?:base|peak)\.000\.threads:\s*([\d.]+)",
                # Legacy format fallbacks (for other RSF variations)
                "benchmark_ratio": r"spec\.cpu2017\.(\d{3}\.\w+(?:_[rs])?)\.(?:base|peak)\.ratio:\s*([\d.]+)",
                "benchmark_time": r"spec\.cpu2017\.(\d{3}\.\w+(?:_[rs])?)\.(?:base|peak)\.time:\s*([\d.]+)",
                "benchmark_result": r"spec\.cpu2017\.(\d{3}\.\w+(?:_[rs])?)\.(?:base|peak)\.result:\s*([\d.]+)",
                # Error patterns (failed benchmarks)
                "benchmark_error": r"spec\.cpu2017\.errors\d+:\s*(\d{3}\.\w+(?:_[rs])?)\s*\([^)]+\)\s*(.+)",
            }
        else:
            # Text/HTML format parsing for other result file types
            patterns = {
                # Overall suite scores (common in text reports)
                "overall_score": r"Est\.\s+(SPEC\w+\d+_\w+_\w+)\s*=\s*([\d.]+)",
                "suite_metric": r"Est\.\s+(SPEC\w+\d+_\w+)\s*=\s*([\d.]+)",
                # Table format results (common in text/HTML)
                "table_result": r"(\d{3}\.\w+(?:_[rs])?)\s+[\w\s]+\s+([\d.]+)\s+([\d.]+)",
                # HTML table patterns
                "html_result": r"<td[^>]*>(\d{3}\.\w+(?:_[rs])?)</td>.*?<td[^>]*>([\d.]+)</td>.*?<td[^>]*>([\d.]+)</td>",
            }

        for pattern_name, pattern in patterns.items():
            matches = re.findall(pattern, content, re.IGNORECASE | re.MULTILINE)

            for match in matches:
                if is_rsf_file:
                    # Handle RSF format patterns
                    if pattern_name in ["suite_base_mean", "suite_peak_mean"]:
                        score = float(match)
                        metric_name = f"SPEC{'int' if 'intspeed' in file_path or 'intrate' in file_path else 'fp'}2017_{'rate' if 'rate' in file_path else 'speed'}_{'base' if 'base' in pattern_name else 'peak'}"
                        scores_data[metric_name] = score

                    elif pattern_name in ["suite_base_energy", "suite_peak_energy"]:
                        if match != "--":  # Skip "no data" entries
                            score = float(match)
                            metric_name = (
                                f"Energy_{'base' if 'base' in pattern_name else 'peak'}"
                            )
                            metrics_data[metric_name] = score

                    elif pattern_name.startswith("detailed_"):
                        # Handle detailed benchmark results (spec.cpu2017.results.XXX.base.000.YYY)
                        benchmark_name = match[
                            0
                        ].replace(
                            "_", ".", 1
                        )  # Convert 648_exchange2_s to 648.exchange2_s (only first underscore)
                        value = float(match[1])
                        if benchmark_name not in benchmark_results:
                            benchmark_results[benchmark_name] = {}

                        metric_type = pattern_name.split("_", 1)[
                            1
                        ]  # ratio, time, reference, copies, threads
                        if metric_type == "time":
                            benchmark_results[benchmark_name]["time"] = value
                        elif metric_type == "ratio":
                            benchmark_results[benchmark_name]["ratio"] = value
                        elif metric_type == "reference":
                            benchmark_results[benchmark_name]["reference"] = value
                        elif metric_type == "copies":
                            benchmark_results[benchmark_name]["copies"] = int(value)
                        elif metric_type == "threads":
                            benchmark_results[benchmark_name]["threads"] = int(value)

                    elif pattern_name in [
                        "benchmark_ratio",
                        "benchmark_time",
                        "benchmark_result",
                    ]:
                        # Legacy format fallback
                        benchmark = match[0]
                        value = float(match[1])
                        if benchmark not in benchmark_results:
                            benchmark_results[benchmark] = {}

                        metric_type = pattern_name.split("_")[
                            1
                        ]  # ratio, time, or result
                        benchmark_results[benchmark][metric_type] = value

                    elif pattern_name == "benchmark_error":
                        benchmark = match[0]
                        error_msg = match[1]
                        # Only record error info for benchmarks that actually have results
                        # Skip benchmarks that didn't run at all
                        if benchmark in benchmark_results and benchmark_results[
                            benchmark
                        ].get("ratio"):
                            # Benchmark has results but SPEC flagged it - add warning
                            benchmark_results[benchmark]["warning"] = error_msg
                        # If benchmark has no results, don't add it to the results at all

                else:
                    # Handle text/HTML format patterns
                    if pattern_name in ["overall_score", "suite_metric"]:
                        metric_name = match[0]
                        score = float(match[1])
                        if "base" in metric_name or "peak" in metric_name:
                            scores_data[metric_name] = score
                        else:
                            metrics_data[metric_name] = score

                    elif pattern_name in ["table_result", "html_result"]:
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

        return result_data

    except Exception as e:
        typer.echo(f"Warning: Could not parse result file {file_path}: {e}", err=True)
        return None
