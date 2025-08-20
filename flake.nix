{
  description = "Specer - A CLI wrapper for SPEC CPU 2017 benchmark suite";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    dream2nix.url = "github:nix-community/dream2nix";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, dream2nix, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};

        # For now, let's create a simpler package that uses the existing dependencies
        # and handles evalsync in the development environment
        specerPackage = pkgs.python3Packages.buildPythonPackage rec {
          pname = "specer";
          version = "0.1.0";
          src = ./.;

          pyproject = true;
          build-system = [ pkgs.python3Packages.hatchling ];

          dependencies = [
            pkgs.python3Packages.typer
            pkgs.python3Packages.rich
            pkgs.python3Packages.loguru
            # evalsync will be handled in the development environment
          ];

          # Disable runtime dependency check for now since evalsync is not in nixpkgs
          dontCheckRuntimeDeps = true;

          # Ensure entry points are created properly
          postInstall = ''
            mkdir -p $out/bin
            cat > $out/bin/specer << 'EOF'
#!/usr/bin/env python3
from specer.cli import cli_main
if __name__ == '__main__':
    cli_main()
EOF
            chmod +x $out/bin/specer
          '';

          meta = with pkgs.lib; {
            description = "A CLI wrapper for SPEC CPU 2017 benchmark suite";
            homepage = "https://github.com/minhuw/specer";
            license = licenses.mit;
            maintainers = with maintainers; [ ];
          };
        };

        # Create a Python environment with all dependencies
        pythonEnv = pkgs.python3.withPackages (ps: [
          ps.hatchling
          ps.typer
          ps.rich
          ps.loguru
        ]);

        # Create a development environment that includes evalsync from PyPI
        devPythonEnv = pkgs.python3.withPackages (ps: [
          ps.hatchling
          ps.typer
          ps.rich
          ps.loguru
          ps.pip
        ]);

      in
      {
        # Build the package
        packages.default = specerPackage;

        # Development shell
        devShells.default = pkgs.mkShell {
          buildInputs = [
            # Python environment with dependencies
            devPythonEnv

            # Build tools
            pkgs.python3Packages.hatchling

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
            pkgs.uv  # Since the project uses uv
          ];

          shellHook = ''
            echo "🚀 Specer Development Environment"
            echo "Python: $(python3 --version)"
            echo "Available commands: specer"
            echo ""

            # Set up environment variables
            export PYTHONPATH="$PWD/src:$PYTHONPATH"

            # Load local environment variables if env.local exists
            if [ -f env.local ]; then
                echo "Loading environment from env.local"
                set -a  # automatically export all variables
                source env.local
                set +a  # stop auto-exporting
            else
                echo "env.local not found, using default SPEC paths"
                export SPEC_PATH="''${SPEC_PATH:-$HOME/spec2017}"
                export TEST_SPEC_PATH="''${TEST_SPEC_PATH:-$HOME/spec2017}"
            fi

            # Use SPEC_PATH from env.local if available, otherwise use default
            export SPEC_ROOT="''${SPEC_PATH:-$HOME/spec2017}"
            echo "Using SPEC_ROOT: $SPEC_ROOT"

            # Install evalsync and other dependencies
            echo "Installing evalsync..."
            python3 -m pip install --user evalsync>=0.3.1

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
            echo "To build the package: nix build"
            echo "To run specer: nix run"
            echo "To enter dev shell: nix develop"
          '';
        };

        # Apps for easy running
        apps.default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/specer";
        };

        # Formatter
        formatter = pkgs.nixpkgs-fmt;
      }
    );
}
