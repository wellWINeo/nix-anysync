{
  config,
  lib,
  pkgs,
}:
with lib;

let
  cfg = config.services.any-sync-node;
  user = "any-sync";
  group = "any-sync";

  configPaths = imap1 (
    i: replica: pkgs.writeText "any-sync-node-${i}.yml" (builtins.toJSON replica.config)
  ) cfg.replicas;

  getConfigPath =
    i:
    let
      replicaOpts = elemAt cfg.replicas i;
    in
    if replicaOpts.configPath != null then replicaOpts.configPath else elemAt configPaths i;

  userGroupOptions = import ./common/user-group.nix;
  assertConfig = import ./common/assert-config.nix;
  addUserAndGroup = import ./common/add-user-and-group.nix;
in
{
  options.services.any-sync-node = {
    enable = mkEnableOption "any-sync-node";

    replicas = mkOption {
      type = types.listOf types.submodule {
        options = {
          config = mkOption {
            type = types.attrs;
            default = null;
            description = ''
              any-sync-node configuration
              Reference: https://github.com/anyproto/any-sync-node/blob/main/etc/any-sync-node.yml
            '';
          };

          configPath = mkOption {
            type = types.path;
            default = null;
            description = ''
              any-sync-node configuration path
              Reference: https://github.com/anyproto/any-sync-node/blob/main/etc/any-sync-node.yml
            '';
          };
        };
      };
      description = ''
        Options for each any-sync-node replica.
        Will create systemd unit service for each replica
        according to provided options count.
      '';
    };
  } // userGroupOptions lib user group;

  config =
    mkIf cfg.enable {
      assertions = [
        {
          # Ensures that all replicas has config or config path
          assertion = lists.all assertConfig cfg.replicas;
          message = "One of any-sync-node replica hasn't config or configPath";
        }
      ];

      # create systemd service unit for each replica
      systemd.services = listToAttrs (
        map (
          i:
          nameValuePair "any-sync-node-${i}" {
            ExecStart = "${pkgs.any-sync-node}/bin/any-sync-node -c ${getConfigPath i}";
            User = user;
            Group = group;
            Restart = "on-failure";
            RestartSec = "5s";
            StateDirectory = "any-sync-${i}";
            WorkingDirectory = "/var/lib/any-sync";
            PrivateTmp = true;
            ProtectSystem = "full";
            NoNewPrivileges = true;
            LimitNOFILE = 65536;
          }
        ) range 1 (length cfg.replicas)
      );
    }
    // addUserAndGroup lib user group;
}
