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

  configPaths = imap1 (
    i: replica: pkgs.writeText "any-sync-node-${toString i}.yml" (builtins.toJSON replica.config)
  ) cfg.replicas;

  getConfigPath =
    i:
    let
      replicaOpts = elemAt cfg.replicas (i - 1);
    in
    if replicaOpts.configPath != null then replicaOpts.configPath else elemAt configPaths (i - 1);

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
      ];

      users.users.${user} = {
        isSystemUser = true;
        group = group;
        createHome = false;
      };

      users.groups.${group} = { };

      # create systemd service unit for each replica
      systemd.services = listToAttrs (
        map (
          i:
          nameValuePair "any-sync-node-${toString i}" {
            after = [ "network.target" ];
            wants = [
              "any-sync-filenode.service"
              "any-sync-consensus.service"
              "any-sync-coordinator.service"
            ];
            wantedBy = [ "multi-user.target" ];

            path = [ pkgs.any-sync-node ];

            unitConfig = {
              StartLimitBurst = 3;
            };

            serviceConfig = {
              ExecStart = "${pkgs.any-sync-node}/bin/any-sync-node -c ${getConfigPath i}";
              User = user;
              Group = group;
              Restart = "no";
              # ReadWritePaths = [ "/var/lib/network-store/any-sync-node-${toString i}" ];
              # Restart = "on-failure";
              # RestartSec = "5s";
              # StateDirectory = "any-sync-${toString i}";
              # WorkingDirectory = "/var/lib/any-sync";
              # PrivateTmp = true;
              # ProtectSystem = "full";
              # NoNewPrivileges = true;
              # LimitNOFILE = 65536;
            };
          }
        ) (range 1 (length cfg.replicas))
      );
    }
    // (common.addUserAndGroup cfg user group);
}
