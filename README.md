# Specer

A CLI wrapper for SPEC CPU 2017 benchmark suite.

## Installation

```bash
pip install specer
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
```

## Commands

- `compile`: Build benchmarks
- `run`: Execute benchmarks
- `setup`: Extract benchmark source code
- `clean`: Clean build directories
- `update`: Update SPEC installation
