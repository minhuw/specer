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
        makeSpecerPackage = {}: pkgs.python3Packages.buildPythonPackage rec {
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
        packages = {
          default = makeSpecerPackage {};
        };

        devShells.default = pkgs.mkShell {

          shellHook = ''
            echo "🚀 Specer Development Environment"
            echo "Python: $(python3 --version)"
            echo "Available commands: specer"
            echo ""

            # Prioritize system compilers over nix compilers
            export PATH="/usr/bin:$PATH"

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

            # Install dependencies using uv sync
            echo "Installing dependencies with uv sync..."
            uv sync

            # Verify compiler availability
            echo "Checking compiler availability:"
            echo "  GCC: $(which gcc 2>/dev/null || echo 'NOT FOUND') (prioritizing system)"
            echo "  GFortran: $(which gfortran 2>/dev/null || echo 'NOT FOUND') (prioritizing system)"
            echo ""
          '';
        };

        # Apps for easy running
        apps.default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/specer";
        };

        lib.make = makeSpecerPackage;

        # Formatter
        formatter = pkgs.nixpkgs-fmt;
      }
    ) // {
      flake = "github:minhuw/specer";
    };
}
