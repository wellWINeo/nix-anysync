{
  config,
  lib,
  pkgs,
  ...
}:
with lib;

let
  common = import ./common.nix {
    inherit pkgs;
    inherit lib;
  };

  cfg = config.services.any-sync-coordinator;
  user = "any-sync";
  group = "any-sync";

  configPath = common.getConfigPath cfg "any-sync-coordinator";
in
{
  options.services.any-sync-coordinator =
    with types;
    {
      enable = mkEnableOption "any-sync-coordinator";

      config = mkOption {
        type = nullOr attrs;
        default = null;
        description = ''
          Config for any-sync-coordinator.
          Reference https://github.com/anyproto/any-sync-coordinator/blob/main/etc/any-sync-coordinator.yml 
        '';
      };

      configPath = mkOption {
        type = nullOr path;
        default = null;
        description = ''
          Config for any-sync-coordinator's config path.
          Reference: https://github.com/anyproto/any-sync-coordinator/blob/main/etc/any-sync-coordinator.yml 
        '';
      };
    }
    // (common.userGroupOptions user group);

  config =
    mkIf cfg.enable {
      assertions = [ (common.assertConfig cfg) ];

      systemd.services.any-sync-coordinator = {
        serviceConfig = {
          ExecStart = "${pkgs.any-sync-coordinator}/bin/any-sync-coordinator -c ${configPath}";
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
    }
    // (common.addUserAndGroup cfg user group);
}
