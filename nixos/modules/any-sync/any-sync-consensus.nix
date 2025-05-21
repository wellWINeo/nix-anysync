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

  cfg = config.services.any-sync-consensus;
  user = "any-sync";
  group = "any-sync";

  configPath = common.getConfigPath cfg "any-sync-consensus";
in
{
  options.services.any-sync-consensus =
    with types;
    {
      enable = mkEnableOption "any-sync-consensus";

      config = mkOption {
        type = nullOr attrs;
        default = null;
        description = ''
          any-sync-consensus configuration
          Reference: https://github.com/anyproto/any-sync-consensusnode/blob/main/etc/any-sync-consensusnode.yml
        '';
      };

      configPath = mkOption {
        type = nullOr path;
        default = null;
        description = ''
          any-sync-consensus configuration's path
          Reference: https://github.com/anyproto/any-sync-consensusnode/blob/main/etc/any-sync-consensusnode.yml
        '';
        example = "/etc/any-sync-consensus.yml";
      };
    }
    // (common.userGroupOptions user group);

  config =
    mkIf cfg.enable {

      assertions = [ (common.assertConfig cfg) ];

      systemd.services.any-sync-consensus = {
        serviceConfig = {
          ExecStart = "${pkgs.any-sync-consensus}/bin/any-sync-consensus -c ${configPath}";
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
