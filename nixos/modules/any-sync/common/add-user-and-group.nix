{
  lib,
  user,
  group,
}:
with lib;

{
  users.users.${user} =
    mkIf cfg.user == user {
      isSystemUser = true;
      group = group;
      createHome = false;
    };

  users.groups.${group} = mkIf cfg.group == group { };
}
