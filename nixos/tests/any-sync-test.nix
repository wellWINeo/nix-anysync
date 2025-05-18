{ pkgs, ... }:

let
  networkConfig = {
    id = "6820862ae79bd90018ae22d0";
    networkId = "N4rNdGGdRB2Erg8xfh3ZmbkZyDF6kV2aRSsKUahiHRv1BPPT";
    nodes = [
      {
        # any-sync-node 1
        addresses = [
          "192.168.0.1:1001"
          "quic://192.168.0.1:1011"
          "127.0.0.1:1001"
          "quic://127.0.0.1:1011"
        ];
        peerId = "12D3KooWQFamdVnYhGqda7un21XtQcZu8fPnmU5ARgDvuJiRGgNq";
        types = [ "tree" ];
      }
      {
        # any-sync-node 2
        addresses = [
          "192.168.0.1:1002"
          "quic://192.168.0.1:1012"
          "127.0.0.1:1002"
          "quic://127.0.0.1:1012"
        ];
        peerId = "12D3KooWDRVzZ1zeoHb6gS8Pez33mYUNxdmzVfE6R6mUruXSCB6s";
        types = [ "tree" ];
      }
      {
        # any-sync-node 3
        addresses = [
          "192.168.0.1:1003"
          "quic://192.168.0.1:1013"
          "127.0.0.1:1003"
          "quic://127.0.0.1:1013"
        ];
        peerId = "12D3KooWKhZoPy68FJAcmnm6YjetxvAfndgfcrqgcyq7NCnEJ3Zn";
        types = [ "tree" ];
      }
      {
        # any-sync-coordinator
        addresses = [
          "192.168.0.1:1004"
          "quic://192.168.0.1:1014"
          "127.0.0.1:1004"
          "quic://127.0.0.1:1014"
        ];
        peerId = "12D3KooWQ8nLTT4VTWNwZPJ7p9KCiFMLWriVzivKjMt87g5WwvEP";
        types = [ "coordinator" ];
      }
      {
        # any-sync-filenode
        addresses = [
          "192.168.0.1:1005"
          "quic://192.168.0.1:1015"
          "127.0.0.1:1005"
          "quic://127.0.0.1:1015"
        ];
        peerId = "12D3KooWNLZmGeHbWVJsVMmBCwdrsyEdTBj6HydakagT7sRgDBtH";
        types = [ "file" ];
      }
      {
        # any-sync-consensusnode
        addresses = [
          "192.168.0.1:1006"
          "quic://192.168.0.1:1016"
          "127.0.0.1:1006"
          "quic://127.0.0.1:1016"
        ];
        peerId = "12D3KooWDA4TWKJg2M3sosfTNx2RSaeM7wr4rfcVzpDbtX3sezqP";
        types = [ "consensus" ];
      }
    ];
  };
  getCommonOptions =
    port:
    let
      listenOptions = listenPort: {
        listenAddrs = [ "0.0.0.0:${listenPort}" ];
        writeTimeoutSec = 10;
        dialTimeoutSec = 10;
      };
    in
    {
      metric.addr = "0.0.0.0:8000";
      log = {
        defaultLevel = "";
        namedLevels = { };
        production = false;
      };
      networkStorePath = "/networkStore";
      drpc.stream = {
        timeoutMilliseconds = 1000;
        maxMsgSizeMb = 256;
      };
      yamux = listenOptions port;
      quic = listenOptions (port + 10);
    };

  clientConfigPath = pkgs.writeText "client.yml" (builtins.toJSON networkConfig);
in
{
  name = "any-sync-test";

  meta = with pkgs.stdenv.lib.maintainers; {
    maintainers = [ wellWINeo ];
  };

  nodes = {
    server = {
      networking = {
        useDHCP = false;
        interfaces.eth1.ipv4.addresses = [
          {
            address = "192.168.0.1";
            prefixLength = 24;
          }
        ];
      };

      services.any-sync-consensus = {
        enable = true;
        config =
          networkConfig
          // {
            account = {
              peerId = "12D3KooWDA4TWKJg2M3sosfTNx2RSaeM7wr4rfcVzpDbtX3sezqP";
              peerKey = "yqZlxIagQGpW1pt67uda/aTyuw1lbV+cE4eJqMONvsgxnqasNtJhXrAEVKwGe87kladaCYHVrYf/9383fDmJIg==";
              signingKey = "sg2O8EAvfsPI36RT4uqevZLD1XLG7b3k6O6g7mQMc9Ig8N4vZuiM/8xkhk852dZebLGx7VqEwgCrl4aMCi/whw==";
            };
            mongo = {
              connect = "mongodb://mongo:27001/?w=majority";
              database = "consensus";
              logCollection = "log";
            };
          }
          // getCommonOptions 1006;
      };

      services.any-sync-coordinator = {
        enable = true;
        config =
          networkConfig
          // {
            account = {
              peerId = "12D3KooWQ8nLTT4VTWNwZPJ7p9KCiFMLWriVzivKjMt87g5WwvEP";
              peerKey = "y6gg83SYkymzrIV1h4fE724rzB0TdHKRCEdbHtJvYo3Uu2XTpkH/Y97IXS1bKleYKe5Hoh/QjMWKIagMr8nY/A==";
              signingKey = "sg2O8EAvfsPI36RT4uqevZLD1XLG7b3k6O6g7mQMc9Ig8N4vZuiM/8xkhk852dZebLGx7VqEwgCrl4aMCi/whw==";
            };
            mongo = {
              connect = "mongodb://mongo:27001";
              database = "coordinator";
              log = "log";
              spaces = "spaces";
            };
            spaceStatus = {
              runSeconds = 5;
              deletionPeriodDays = 0;
            };
            defaultLimits = {
              spaceMembersRead = 1000;
              spaceMembersWrite = 1000;
              sharedSpacesLimit = 1000;
            };
          }
          // getCommonOptions 1004;
      };

      services.any-sync-filenode = {
        enable = true;
        config =
          networkConfig
          // {
            account = {
              peerId = "12D3KooWNLZmGeHbWVJsVMmBCwdrsyEdTBj6HydakagT7sRgDBtH";
              peerKey = "unpzbfaBBAY+HcxyQBCg0AVtGoMyqR4bsMOm1fU/GCa6CMc4xsqWoIydrk1T9OqiEU5UHr4IIXqN95O4X2iA1g==";
              signingKey = "unpzbfaBBAY+HcxyQBCg0AVtGoMyqR4bsMOm1fU/GCa6CMc4xsqWoIydrk1T9OqiEU5UHr4IIXqN95O4X2iA1g==";
            };

            s3Store = {
              bucket = "minio-bucket";
              indexBucket = "minio-bucket";
              maxThreads = 16;
              profile = "default";
              region = "us-east-1";
              endpoint = "http://minio:9000";
              forcePathStyle = true; # 'true' for self-hosted S3 Object Storage
            };

            redis = {
              isCluster = false;
              url = "redis://redis:6379?dial_timeout=3&read_timeout=6s";
            };
          }
          // getCommonOptions 1005;
      };

      services.any-sync-node = {
        enable = true;
        replicas =
          map
            (
              opts:
              networkConfig
              // {
                account = {
                  peerId = opts.peerId;
                  peerKey = opts.peerKey;
                  signingKey = opts.signingKey;
                };
                apiServer.listenAddr = "0.0.0.0:8080";
                space = {
                  gcTTL = 60;
                  syncPeriod = 600;
                };
                storage = {
                  path = "/storage";
                  anyStorePath = "/anyStorage";
                };
                nodeSync = {
                  periodicSyncHours = 2;
                  syncOnStart = true;
                };
              }
              // getCommonOptions opts.port
            )
            [
              {
                peerId = "12D3KooWQFamdVnYhGqda7un21XtQcZu8fPnmU5ARgDvuJiRGgNq";
                peerKey = "MOSek7QTbMbS0D56judvhLM1C8IWASbobszsX+AEKmDWeWK/N9PXEn+SOdFtMvSkkq3Ivg2AeXQgqJp1DEJDJg==";
                signingKey = "MOSek7QTbMbS0D56judvhLM1C8IWASbobszsX+AEKmDWeWK/N9PXEn+SOdFtMvSkkq3Ivg2AeXQgqJp1DEJDJg==";
                port = 1001;
              }
              {
                peerId = "12D3KooWDRVzZ1zeoHb6gS8Pez33mYUNxdmzVfE6R6mUruXSCB6s";
                peerKey = "NlqXQj7RyEd/SlW3q3V9mfwYnrMHadxGIfbvf7UtdEo1kzxtMUAMfP/wWxP/4gqiwCNrVdgii5sUku5GbwWyRA==";
                signingKey = "NlqXQj7RyEd/SlW3q3V9mfwYnrMHadxGIfbvf7UtdEo1kzxtMUAMfP/wWxP/4gqiwCNrVdgii5sUku5GbwWyRA==";
                port = 1002;
              }
              {
                peerId = "12D3KooWKhZoPy68FJAcmnm6YjetxvAfndgfcrqgcyq7NCnEJ3Zn";
                peerKey = "pgOqz9EL+eVvKn/V54Bg7xfcUkRF0D3HgM3eJEL7kw2S1vS0GtqMWlp/zYd6YIq+Do6EWGBapzGy68VQUd3EjQ==";
                signingKey = "pgOqz9EL+eVvKn/V54Bg7xfcUkRF0D3HgM3eJEL7kw2S1vS0GtqMWlp/zYd6YIq+Do6EWGBapzGy68VQUd3EjQ==";
                port = 1003;
              }
            ];
      };
    };

    client = {
      networking = {
        useDHCP = false;
        interfaces.eth1.ipv4.addresses = [
          {
            address = "192.168.0.2";
            prefixLength = 24;
          }
        ];
      };

      environment.systemPackages = [ pkgs.any-sync-tools ];
    };
  };

  testScript = ''
    start_all()

    # Copy client.yml to client node
    client.copy_from_host("${clientConfigPath}", "/tmp/any-sync-client.yml")

    # Wait for services to be up
    server.waitForUnit("any-sync-node-1.service");
    server.waitForUnit("any-sync-node-2.service");
    server.waitForUnit("any-sync-node-3.service");
    server.waitForUnit("any-sync-filenode.service");
    server.waitForUnit("any-sync-coordinator.service");
    server.waitForUnit("any-sync-consensus.service");

    # netcheck from client
    client.succeed("any-sync-netcheck -c /tmp/any-sync-client.yml");
  '';
}
