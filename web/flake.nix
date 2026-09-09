{
  description = "forge — Effect v4 monorepo";

  # Pinned to the same nixpkgs revision as flake.lock. Bump both together with
  # `nix flake update`; the package set below must exist in the pinned rev.
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/b62d2a9";
  };

  outputs =
    { nixpkgs, ... }:
    let
      forAllSystems =
        function:
        nixpkgs.lib.genAttrs nixpkgs.lib.systems.flakeExposed (
          system: function nixpkgs.legacyPackages.${system}
        );
    in
    {
      formatter = forAllSystems (pkgs: pkgs.alejandra);

      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          packages = with pkgs; [
            corepack
            nodejs_22
            nodePackages.pnpm
            postgresql
            git
          ];

          shellHook = ''
            corepack enable 2>/dev/null || true

            echo "forge dev shell"
            echo "  node    $(node --version)"
            echo "  pnpm    $(pnpm --version 2>/dev/null || echo '(run: corepack enable)')"
            echo "  psql    $(psql --version | cut -d' ' -f3)"
            echo ""
            echo "  postgres server: docker compose up -d"
          '';
        };
      });
    };
}
