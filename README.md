# Specer

A CLI wrapper for SPEC CPU 2017 benchmark suite.

## Installation

### From PyPI
```bash
pip install specer
```

### For Development
```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and install
git clone https://github.com/minhuw/specer
cd specer
uv sync
```

## Usage

```bash
# Auto-generates config files from SPEC's example
specer run gcc --cores 8 --spec-root /opt/spec2017
specer compile gcc --config myconfig.cfg --spec-root /opt/spec2017
specer setup gcc --config myconfig.cfg --spec-root /opt/spec2017

# Use environment variable to avoid typing --spec-root
export SPEC_PATH=/opt/spec2017
specer run gcc --cores 8

# Skip compilation for faster execution (benchmarks must be pre-compiled)
specer compile gcc --cores 8          # Compile once
specer run gcc --skip-compile --cores 8  # Run without recompiling (faster)

# Synchronized execution with EvalSync (requires environment variables)
export EVALSYNC_EXPERIMENT_ID=my_experiment
export EVALSYNC_CLIENT_ID=client1
specer run gcc --sync --cores 8      # Wait for start, run, wait for stop
```

## Commands

- `compile`: Build benchmarks
- `run`: Execute benchmarks
- `setup`: Extract benchmark source code
- `clean`: Clean build directories
- `update`: Update SPEC installation
