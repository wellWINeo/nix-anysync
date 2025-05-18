{ lib, user, group }:
with lib;

{
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
}
