# This file provides backward compatibility and can be used with nix-shell
{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = [
    # Python and build tools
    pkgs.python3
    pkgs.python3Packages.hatchling
    pkgs.python3Packages.pip
    pkgs.uv

    # Development tools
    pkgs.python3Packages.pytest
    pkgs.python3Packages.pytest-cov
    pkgs.python3Packages.pytest-xdist
    pkgs.python3Packages.ruff
    pkgs.python3Packages.mypy
    pkgs.pre-commit
    pkgs.python3Packages.bandit
    pkgs.python3Packages.safety
    pkgs.python3Packages.virtualenv
    pkgs.python3Packages.twine

    # System dependencies that SPEC CPU 2017 might need
    pkgs.gcc
    pkgs.gnumake
    pkgs.which
    pkgs.procps

    # For development
    pkgs.git
    pkgs.curl
  ];

  shellHook = ''
    echo "🚀 Specer Development Environment (via shell.nix)"
    echo "Python: $(python3 --version)"
    echo ""

    # Set up environment variables
    export PYTHONPATH="$PWD/src:$PYTHONPATH"
    export SPEC_ROOT="$HOME/spec2017"

    # Create virtual environment if it doesn't exist
    if [ ! -d .venv ]; then
      echo "Creating virtual environment..."
      python3 -m venv .venv
      source .venv/bin/activate
      pip install -e .
    else
      source .venv/bin/activate
    fi

    echo "Virtual environment activated: $VIRTUAL_ENV"
    echo ""
    echo "Note: Consider using 'direnv' and 'nix develop' for a better experience"
  '';

  # Environment variables
  SPEC_ROOT = "$HOME/spec2017";
}
