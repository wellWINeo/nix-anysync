{
  config,
  lib,
  pkgs,
}:
with lib;

let
  cfg = config.services.any-sync-filenode;
  user = "any-sync";
  group = "any-sync";

  configFile = pkgs.writeText "any-sync-filenode-config.yml" (builtins.toJSON cfg.config);
  
  userGroupOptions = import ./common/user-group.nix;
  assertConfig = import ./common/assert-config.nix;
  addUserAndGroup = import ./common/add-user-and-group.nix;
in
{
  options.services.any-sync-filenode = {
    enable = lib.mkEnableOption "any-sync-filenode";

    config = mkOption {
      type = types.attrs;
      default = null;
      description = ''
        any-sync-filenode configuration
        Reference https://github.com/anyproto/any-sync-filenode/blob/main/etc/any-sync-filenode.yml 
      '';
    };

    configPath = mkOption {
      type = types.path;
      default = null;
      description = ''
        any-sync-filenode configuration's path
        Reference https://github.com/anyproto/any-sync-filenode/blob/main/etc/any-sync-filenode.yml 
      '';
    };
  } // userGroupOptions lib user group;

  config =
    mkIf cfg.enable {

      assertions = [ (assertConfig cfg) ];

      systemd.service.any-sync-filenode = {
        ExecStart = "${pkgs.any-sync-filenode}/bin/any-sync-filenode -c ${configFile}";
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
