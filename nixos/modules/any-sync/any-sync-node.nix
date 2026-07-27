{
  config,
  lib,
  pkgs,
  ...
}:
with lib;

let
  cfg = config.services.any-sync-node;
  user = "any-sync";
  group = "any-sync";

  # Helper to generate config with storage defaults injected from state directory
  getConfigPath = i: let
    r = elemAt cfg.replicas (i - 1);
    stateDir = "/var/lib/any-sync/node-${toString i}";
    r_mod = recursiveUpdate r {
      config = {
        storage = {
          path = stateDir + "/storage";
          anyStorePath = stateDir + "/anyStorage";
        };
      };
    };
  in common.getConfigPath r_mod "any-sync-filenode-${toString i}";

  common = import ./common.nix {
    inherit pkgs;
    inherit lib;
  };
in
{
  options.services.any-sync-node =
    with types;
    {
      enable = mkEnableOption "any-sync-node";

      replicas = mkOption {
        type = listOf (submodule {
          options = {
            config = mkOption {
              type = nullOr attrs;
              default = null;
              description = ''
                any-sync-node configuration
                Reference: https://github.com/anyproto/any-sync-node/blob/main/etc/any-sync-node.yml
              '';
            };

            configPath = mkOption {
              type = nullOr path;
              default = null;
              description = ''
                any-sync-node configuration path
                Reference: https://github.com/anyproto/any-sync-node/blob/main/etc/any-sync-node.yml
              '';
            };
          };
        });
        description = ''
          Options for each any-sync-node replica.
          Will create systemd unit service for each replica
          according to provided options count.
        '';
      };
    }
    // (common.userGroupOptions user group);

  config =
    mkIf cfg.enable {
      assertions = [
        {
          # Ensures that all replicas has config or config path
          assertion = lists.all (cfg: cfg.config != null || cfg.configPath != null) cfg.replicas;
          message = "One of any-sync-node replica hasn't config or configPath";
        }
      ] ++ (imap1 (
        i: r: {
          assertion = !(r.config != null && (r.config ? storage));
          message = ''
            Storage configuration in replica ${toString i} will be overridden by systemd StateDirectory defaults.
            Storage path and anyStorePath are automatically set to:
              path: /var/lib/any-sync/node-${toString i}/storage
              anyStorePath: /var/lib/any-sync/node-${toString i}/anyStorage
            To use custom storage paths, provide a configPath to your own yaml file instead of inline config.
          '';
        }
      ) cfg.replicas);

      # create systemd service unit for each replica
      systemd.services = listToAttrs (
        map (
          i:
          nameValuePair "any-sync-node-${toString i}" {
            serviceConfig = {
              ExecStart = "${pkgs.any-sync-node}/bin/any-sync-node -c ${getConfigPath i}";
              User = user;
              Group = group;
              Restart = "on-failure";
              RestartSec = "5s";
              StateDirectory = "any-sync-${toString i}";
              StateDirectory = "any-sync/node-${toString i}";
              WorkingDirectory = "/var/lib/any-sync";
              PrivateTmp = true;
              ProtectSystem = "full";
              NoNewPrivileges = true;
              LimitNOFILE = 65536;
            };
          }
        ) (range 1 (length cfg.replicas))
      );
    }
    // (common.addUserAndGroup cfg user group);
}
