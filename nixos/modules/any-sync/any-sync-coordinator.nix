{
  config,
  lib,
  pkgs,
}:
with lib;

let
  userGroupOptions = import ./common/user-group.nix;
  assertConfig = import ./common/assert-config.nix;
  addUserAndGroup = import ./common/add-user-and-group.nix;
  getConfigPath = import ./common/get-config-path.nix;
  
  cfg = config.services.any-sync-coordinator;
  user = "any-sync";
  group = "any-sync";

  configPath = getConfigPath pkgs "any-sync-coordinator" cfg;
in
{
  options.services.any-sync-coordinator = {
    enable = lib.mkEnableOption "any-sync-coordinator";

    options.services.any-sync-coordinator = {
      enable = mkEnableOption "any-sync-coordinator";

      config = mkOption {
        type = types.attrsOf;
        default = null;
        description = ''
          Config for any-sync-coordinator.
          Reference https://github.com/anyproto/any-sync-coordinator/blob/main/etc/any-sync-coordinator.yml 
        '';
      };

      configPath = mkOption {
        type = types.path;
        default = null;
        description = ''
          Config for any-sync-coordinator's config path.
          Reference: https://github.com/anyproto/any-sync-coordinator/blob/main/etc/any-sync-coordinator.yml 
        '';
      };
    };
  } // userGroupOptions lib user group;

  config =
    mkIf cfg.enable {
      assertions = [ (assertConfig cfg) ];

      systemd.service.any-sync-coordinator = {
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
    }
    // addUserAndGroup lib user group;
}
