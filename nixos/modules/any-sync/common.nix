{ pkgs, lib }:
with lib;

{
  # Create only the module's default account; custom accounts are caller-owned.
  addUserAndGroup = cfg: defaultUser: defaultGroup: {
    users.users.${defaultUser} = mkIf (cfg.user == defaultUser) {
      isSystemUser = true;
      group = cfg.group;
      createHome = false;
    };

    users.groups.${defaultGroup} = mkIf (cfg.group == defaultGroup) { };
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
