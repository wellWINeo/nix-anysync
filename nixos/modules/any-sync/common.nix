{ pkgs, lib }:
with lib;

{
  # Helper function add default user and group if needed
  addUserAndGroup = cfg: user: group: {
    users.users.${user} =
      mkIf cfg.user == user {
        isSystemUser = true;
        group = group;
        createHome = false;
      };

    users.groups.${group} = mkIf cfg.group == group { };
  };

  userGroupOptions = user: group: {
    user = mkOption {
      type = types.string;
      description = "User";
      default = user;
    };

    group = mkOption {
      type = types.string;
      description = "Group";
      default = group;
    };
  };

  # config assertion helper
  assertConfig = cfg: {
    assertion = cfg.config != null || cfg.configPath != null;
    message = "config or configPath must be set";
  };

  getConfigPath =
    cfg: name:
    if cfg.configPath != null then
      cfg.configPath
    else
      pkgs.writeText "${name}.yml" (builtins.toJSON cfg.config);
}
