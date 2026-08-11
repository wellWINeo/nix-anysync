{ pkgs, lib }:
with lib;

{
  # Helper function to add the configured user and group
  addUserAndGroup = cfg: _defaultUser: _defaultGroup: {
    users.users.${cfg.user} = {
      isSystemUser = true;
      group = cfg.group;
      createHome = false;
    };

    users.groups.${cfg.group} = { };
  };

  userGroupOptions = user: group: {
    user = mkOption {
      type = types.str;
      description = "User";
      default = user;
    };

    group = mkOption {
      type = types.str;
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
