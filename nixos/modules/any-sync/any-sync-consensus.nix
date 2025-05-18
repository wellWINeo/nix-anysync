{
  config,
  lib,
  pkgs,
  ...
}:
with lib;

let
  userGroupOptions = import ./common/user-group.nix;
  assertConfig = import ./common/assert-config.nix;
  addUserAndGroup = import ./common/add-user-and-group.nix;
  getConfigPath = import ./common/get-config-path.nix;

  cfg = config.services.any-sync-consensus;
  user = "any-sync";
  group = "any-sync";

  configPath = getConfigPath pkgs "any-sync-consensus" cfg;
in
{
  options.services.any-sync-consensus = {
    enable = mkEnableOption "any-sync-consensus";

    config = mkOption {
      type = types.attrs;
      default = null;
      description = ''
        any-sync-consensus configuration
        Reference: https://github.com/anyproto/any-sync-consensusnode/blob/main/etc/any-sync-consensusnode.yml
      '';
    };

    configPath = mkOption {
      type = types.path;
      default = null;
      description = ''
        any-sync-consensus configuration's path
        Reference: https://github.com/anyproto/any-sync-consensusnode/blob/main/etc/any-sync-consensusnode.yml
      '';
      example = "/etc/any-sync-consensus.yml";
    };
  } // userGroupOptions lib user group;

  config =
    mkIf cfg.enable {

      assertions = [ (assertConfig cfg) ];

      systemd.service.any-sync-coordinator = {
        ExecStart = "${pkgs.any-sync-coordinator}/bin/any-sync-consensus -c ${configPath}";
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
