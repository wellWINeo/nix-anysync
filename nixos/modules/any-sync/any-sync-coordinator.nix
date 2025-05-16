{
  config,
  lib,
  pkgs,
}:
with lib;

let
  cfg = config.services.any-sync-coordinator;
  user = "any-sync";
  group = "any-sync";

  configFile = pkgs.writeText "any-sync-coordinator-config.yml" (builtins.toJSON cfg.config);
in
{
  options.services.any-sync-coordinator = {
    enable = lib.mkEnableOption "any-sync-coordinator";

    options.services.any-sync-coordinator = {
      enable = mkEnableOption "any-sync-coordinator";

      config = mkOption {
        type = types.attrsOf types.inferred;
        description = ''
          Config for any-sync-coordinator.
          Reference https://github.com/anyproto/any-sync-coordinator/blob/main/etc/any-sync-coordinator.yml 
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

      systemd.service.any-sync-coordinator = {
        ExecStart = "${pkgs.any-sync-coordinator}/bin/any-sync-coordinator -c ${configFile}";
        User = user;
        Group = group;
        Restart = "on-failure";
        RestartSec = "5s";
        StateDirectory = "any-sync";
        WorkingDirectory = "/var/lib/any-sync";
        PrivateTmp = true;
        ProtectSystem = "full";
        NoNewPrivileges = true;
        LimitNOFILE = 65536;
      };
    };
  };
}
