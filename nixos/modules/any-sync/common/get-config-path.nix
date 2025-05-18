{
  pkgs,
  name,
  cfg,
}:

if cfg.config != null then cfg.config else pkgs.writeText "${name}.yml" (builtins.toJSON cfg.config)
