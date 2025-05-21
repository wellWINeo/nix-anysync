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

  cfg = config.services.any-sync-filenode;
  user = "any-sync";
  group = "any-sync";

  configPath = common.getConfigPath cfg "any-sync-filenode";
in
{
  options.services.any-sync-filenode =
    with types;
    {
      enable = lib.mkEnableOption "any-sync-filenode";

      config = mkOption {
        type = nullOr attrs;
        default = null;
        description = ''
          any-sync-filenode configuration
          Reference https://github.com/anyproto/any-sync-filenode/blob/main/etc/any-sync-filenode.yml 
        '';
      };

      configPath = mkOption {
        type = nullOr path;
        default = null;
        description = ''
          any-sync-filenode configuration's path
          Reference https://github.com/anyproto/any-sync-filenode/blob/main/etc/any-sync-filenode.yml 
        '';
      };
    }
    // (common.userGroupOptions user group);

  config =
    mkIf cfg.enable {

      assertions = [ (common.assertConfig cfg) ];

      systemd.services.any-sync-filenode = {
        serviceConfig = {
          ExecStart = "${pkgs.any-sync-filenode}/bin/any-sync-filenode -c ${configPath}";
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
