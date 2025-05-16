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

  configFile = pkgs.writeText "any-sync-node-config.yml" (builtins.toJSON cfg.config);
in
{
  options.services.any-sync-node = {
    enable = lib.mkEnableOption "any-sync-node";

    options.services.any-sync-node = {
      enable = mkEnableOption "any-sync-node";

      replicasCount = mkOptions {
        type = types.integer;
        description = ''
          Replicas count to sync nodes. Due to lack of replications
          functionality in systemd will create several services for
          each replica. 
        '';
        default = 1;
        example = 3;
      };

      config = mkOption {
        type = types.attrsOf types.inferred;
        description = ''
          Config for any-sync-node.
          Reference https://github.com/anyproto/any-sync-node/blob/main/etc/any-sync-filenode.yml 
        '';
      };
    };

    config = mkIf cfg.enable {
      users.users.${user} = {
        isSystemUser = true;
        group = group;
        createHome = false;
      };

      users.groups.${group} = { };

      systemd.services = listToAttrs (
        map (
          i:
          nameValuePair "any-sync-node-${i}" {
            ExecStart = "${pkgs.any-sync-node}/bin/any-sync-node -c ${configFile}";
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
        ) range 1 (cfg.replicasCount + 1)
      );
    };
  };
}
