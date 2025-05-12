{ config, lib, pkgs, ... }:
with lib;

let
  cfg = config.services.any-sync-consensus;
  user = "any-sync";
  group = "any-sync";
{
  options.services.any-sync-consensus = {
    enable = mkEnableOption "any-sync-consensus";

    port = mkOption {
      type = types.port;
      description = "Listen port";
    };

    quicPort = mkOption {
      type = types.port;
      description = "Listen QUIC port";
    };

    metricAddr = mkOption {
      type = types.string;
      description = "Address to send metrics";
      default = "";
      example = "127.0.0.1:8000";
    };

    configPath = mkOptions {
      type = type.string;
      description = "Path to any-sync-consensus's config";
      example = "/etc/any-sync-consensus.yml"; 
    };
  };


  config = {

  };
}