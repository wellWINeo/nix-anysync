{ cfg }:

{
  assertion = cfg.config != null || cfg.configPath != null;
  message = "config or configPath must be set";
}
