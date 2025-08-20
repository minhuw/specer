{
  description = "Specer - A CLI wrapper for SPEC CPU 2017 benchmark suite";

  inputs = {
    dream2nix.url = "github:nix-community/dream2nix";
    nixpkgs.follows = "dream2nix/nixpkgs";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = {
    self,
    dream2nix,
    nixpkgs,
    flake-utils,
  }:
    flake-utils.lib.eachDefaultSystem (system: let
      pkgs = nixpkgs.legacyPackages.${system};
      pyproject = pkgs.lib.importTOML ./pyproject.toml;

      # Inline the dream2nix module definition
      specerModule = {
        config,
        lib,
        dream2nix,
        ...
      }: {
        imports = [
          dream2nix.modules.dream2nix.pip
        ];

        deps = {nixpkgs, ...}: {
          python = nixpkgs.python3;
        };

        inherit (pyproject.project) name version;

        mkDerivation = {
          src = lib.cleanSourceWith {
            src = lib.cleanSource ./.;
            filter = name: type:
              !(builtins.any (x: x) [
                (lib.hasSuffix ".nix" name)
                (lib.hasPrefix "." (builtins.baseNameOf name))
                (lib.hasSuffix "flake.lock" name)
              ]);
          };
        };

        buildPythonPackage = {
          pyproject = true;
          pythonImportsCheck = [
            "specer"
          ];
        };

        paths.lockFile = "lock.${config.deps.stdenv.system}.json";
        pip = {
          requirementsList =
            pyproject.build-system.requires
            or []
            ++ pyproject.project.dependencies;
          flattenDependencies = true;
        };
      };

      makeSpecer = {}: dream2nix.lib.evalModules {
        packageSets.nixpkgs = pkgs;
        modules = [
          specerModule
          {
            paths.projectRoot = ./.;
            paths.projectRootFile = "flake.nix";
            paths.package = ./.;
          }
        ];
      };
    in {
      packages.default = makeSpecer {};
      lib.make = makeSpecer;

      devShells.default = pkgs.mkShell {
        packages = [
          pkgs.uv
        ];
        shellHook = ''
          echo "🚀 Specer Development Environment"
          echo "Python: $(python3 --version)"
          echo ""

          # Prioritize system compilers over nix compilers
          export PATH="/usr/bin:$PATH"

          # Load local environment variables if env.local exists
          if [ -f env.local ]; then
              echo "Loading environment from env.local"
              set -a
              source env.local
              set +a
          fi

          echo "Development environment ready!"
        '';
      };
    }) // {
      flake = "github:minhuw/specer";
    };
}
