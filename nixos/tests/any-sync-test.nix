{
  nixosModules,
  pkgs,
  lib,
  ...
}:

let
  maintainers = import ../../maintainers/maintainer-list.nix;

  networkConfig = {
    id = "6820862ae79bd90018ae22d0";
    networkId = "N4rNdGGdRB2Erg8xfh3ZmbkZyDF6kV2aRSsKUahiHRv1BPPT";
    nodes = [
      {
        # any-sync-node 1
        addresses = [
          "192.168.0.1:1101"
          "quic://192.168.0.1:1111"
          "127.0.0.1:1101"
          "quic://127.0.0.1:1111"
        ];
        peerId = "12D3KooWQFamdVnYhGqda7un21XtQcZu8fPnmU5ARgDvuJiRGgNq";
        types = [ "tree" ];
      }
      {
        # any-sync-node 2
        addresses = [
          "192.168.0.1:1102"
          "quic://192.168.0.1:1112"
          "127.0.0.1:1102"
          "quic://127.0.0.1:1112"
        ];
        peerId = "12D3KooWDRVzZ1zeoHb6gS8Pez33mYUNxdmzVfE6R6mUruXSCB6s";
        types = [ "tree" ];
      }
      {
        # any-sync-node 3
        addresses = [
          "192.168.0.1:1103"
          "quic://192.168.0.1:1113"
          "127.0.0.1:1103"
          "quic://127.0.0.1:1113"
        ];
        peerId = "12D3KooWKhZoPy68FJAcmnm6YjetxvAfndgfcrqgcyq7NCnEJ3Zn";
        types = [ "tree" ];
      }
      {
        # any-sync-coordinator
        addresses = [
          "192.168.0.1:1104"
          "quic://192.168.0.1:1114"
          "127.0.0.1:1104"
          "quic://127.0.0.1:1114"
        ];
        peerId = "12D3KooWQ8nLTT4VTWNwZPJ7p9KCiFMLWriVzivKjMt87g5WwvEP";
        types = [ "coordinator" ];
      }
      {
        # any-sync-filenode
        addresses = [
          "192.168.0.1:1105"
          "quic://192.168.0.1:1115"
          "127.0.0.1:1105"
          "quic://127.0.0.1:1115"
        ];
        peerId = "12D3KooWNLZmGeHbWVJsVMmBCwdrsyEdTBj6HydakagT7sRgDBtH";
        types = [ "file" ];
      }
      {
        # any-sync-consensusnode
        addresses = [
          "192.168.0.1:1106"
          "quic://192.168.0.1:1116"
          "127.0.0.1:1106"
          "quic://127.0.0.1:1116"
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
        listenAddrs = [ "0.0.0.0:${toString listenPort}" ];
        writeTimeoutSec = 10;
        dialTimeoutSec = 10;
      };
    in
    {
      metric.addr = "";
      log = {
        defaultLevel = "warn";
        namedLevels = { };
        production = false;
      };
      drpc.stream = {
        timeoutMilliseconds = 1000;
        maxMsgSizeMb = 256;
      };
      yamux = listenOptions port;
      quic = listenOptions (port + 10);
    };

  clientConfigPath = pkgs.writeText "client.yml" (builtins.toJSON networkConfig);
  unreachableClientConfigPath = pkgs.writeText "unreachable-client.yml" (
    builtins.toJSON {
      inherit (networkConfig) id networkId;
      nodes = [
        {
          addresses = [ "127.0.0.1:1" ];
          peerId = "12D3KooWQ8nLTT4VTWNwZPJ7p9KCiFMLWriVzivKjMt87g5WwvEP";
          types = [ "coordinator" ];
        }
      ];
    }
  );
in
pkgs.testers.nixosTest {

  name = "any-sync-test";

  meta = {
    maintainers = [ maintainers.wellWINeo ];
  };

  nodes = {
    server = {

      imports = with nixosModules; [
        any-sync-consensus
        any-sync-coordinator
        any-sync-filenode
        any-sync-node
      ];

      networking = {
        useDHCP = false;
        interfaces.eth1.ipv4.addresses = [
          {
            address = "192.168.0.1";
            prefixLength = 24;
          }
        ];
      };

      services.mongodb = {
        enable = true;
        package = pkgs.mongodb-ce;
        quiet = true;
        replSetName = "rs0";
        initialScript = pkgs.writeText "mongod-init-rs.js" ''
          rs.initiate({_id: "rs0", members: [{_id: 0, host: "127.0.0.1:27017"}]});
        '';
      };

      # Needs to load bloom filter module
      services.redis.package = pkgs.valkey.overrideAttrs (oldAttrs: {
        doCheck = false;
        nativeBuildInputs = oldAttrs.nativeBuildInputs or [ ] ++ [ pkgs.makeWrapper ];
        postInstall = ''
          wrapProgram $out/bin/valkey-server \
            --add-flags "--loadmodule ${pkgs.valkey-bloom}/lib/libvalkey_bloom.so"
        '';
      });
      services.redis.servers.anysync-files = {
        enable = true;
        port = 6379;
      };

      services.minio = {
        enable = true;
        browser = false;
        rootCredentialsFile = pkgs.writeText "minio-root-credentials" ''
          MINIO_ROOT_USER=minioAccess
          MINIO_ROOT_PASSWORD=minioSecret
        '';
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
              connect = "mongodb://127.0.0.1:27017/?replicaSet=rs0";
              database = "consensus";
              logCollection = "log";
            };
            networkStorePath = ".";
          }
          // getCommonOptions 1106;
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
              connect = "mongodb://127.0.0.1:27017/?replicaSet=rs0";
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
            networkStorePath = ".";
          }
          // getCommonOptions 1104;
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
              endpoint = "http://127.0.0.1:9000";
              forcePathStyle = true;
              credentials = {
                accessKey = "minioAccess";
                secretKey = "minioSecret";
              };
            };

            redis = {
              isCluster = false;
              url = "redis://127.0.0.1:6379?dial_timeout=3&read_timeout=6s";
            };

            networkStorePath = ".";
          }
          // getCommonOptions 1105;
      };

      services.any-sync-node = {
        enable = true;
        replicas =
          lib.imap1
            (i: opts: {
              config =
                networkConfig
                // {
                  account = {
                    peerId = opts.peerId;
                    peerKey = opts.peerKey;
                    signingKey = opts.signingKey;
                  };
                  apiServer.listenAddr = "0.0.0.0:808${toString i}";
                  space = {
                    gcTTL = 60;
                    syncPeriod = 600;
                  };
                  nodeSync = {
                    periodicSyncHours = 2;
                    syncOnStart = true;
                  };

                  networkStorePath = ".";
                }
                // getCommonOptions opts.port;
            })
            [
              {
                peerId = "12D3KooWQFamdVnYhGqda7un21XtQcZu8fPnmU5ARgDvuJiRGgNq";
                peerKey = "MOSek7QTbMbS0D56judvhLM1C8IWASbobszsX+AEKmDWeWK/N9PXEn+SOdFtMvSkkq3Ivg2AeXQgqJp1DEJDJg==";
                signingKey = "MOSek7QTbMbS0D56judvhLM1C8IWASbobszsX+AEKmDWeWK/N9PXEn+SOdFtMvSkkq3Ivg2AeXQgqJp1DEJDJg==";
                port = 1101;
              }
              {
                peerId = "12D3KooWDRVzZ1zeoHb6gS8Pez33mYUNxdmzVfE6R6mUruXSCB6s";
                peerKey = "NlqXQj7RyEd/SlW3q3V9mfwYnrMHadxGIfbvf7UtdEo1kzxtMUAMfP/wWxP/4gqiwCNrVdgii5sUku5GbwWyRA==";
                signingKey = "NlqXQj7RyEd/SlW3q3V9mfwYnrMHadxGIfbvf7UtdEo1kzxtMUAMfP/wWxP/4gqiwCNrVdgii5sUku5GbwWyRA==";
                port = 1102;
              }
              {
                peerId = "12D3KooWKhZoPy68FJAcmnm6YjetxvAfndgfcrqgcyq7NCnEJ3Zn";
                peerKey = "pgOqz9EL+eVvKn/V54Bg7xfcUkRF0D3HgM3eJEL7kw2S1vS0GtqMWlp/zYd6YIq+Do6EWGBapzGy68VQUd3EjQ==";
                signingKey = "pgOqz9EL+eVvKn/V54Bg7xfcUkRF0D3HgM3eJEL7kw2S1vS0GtqMWlp/zYd6YIq+Do6EWGBapzGy68VQUd3EjQ==";
                port = 1103;
              }
            ];
      };

      environment.systemPackages = [
        pkgs.mongodb-ce
        pkgs.valkey
        pkgs.minio-client
      ];
    };

    client = {
      imports = [ nixosModules.any-sync-consensus ];
      users.groups.any-sync-test = { };
      users.users.any-sync-test = {
        isNormalUser = true;
        group = "any-sync-test";
      };
      services.any-sync-consensus = {
        enable = true;
        user = "any-sync-test";
        group = "any-sync-test";
        config = { };
      };
      systemd.services.any-sync-consensus.wantedBy = lib.mkForce [ ];

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

    # Wait for MongoDB to be ready with replica set
    server.wait_for_unit("mongodb.service");
    server.wait_for_open_port(27017);

    # Wait for replica set to be initialized (change streams need replica set)
    server.succeed("for i in $(seq 1 30); do mongosh --host 127.0.0.1:27017 --quiet --eval 'rs.status()' 2>/dev/null | grep -q PRIMARY && exit 0; sleep 1; done; exit 1")
    server.succeed("mongosh --host 127.0.0.1:27017 --quiet --eval 'rs.status()' | grep -q 'rs0'")
    server.wait_for_unit("redis-anysync-files.service")
    server.wait_for_open_port(6379)
    server.succeed("valkey-cli -p 6379 PING | grep -qx PONG")
    server.succeed("valkey-cli -p 6379 BF.ADD anysync-test-bloom probe | grep -qx 1")
    server.succeed("valkey-cli -p 6379 BF.EXISTS anysync-test-bloom probe | grep -qx 1")
    server.wait_for_unit("minio.service")
    server.wait_for_open_port(9000)
    server.succeed("export MC_CONFIG_DIR=/tmp/mc; mc alias set local http://127.0.0.1:9000 minioAccess minioSecret; mc mb --ignore-existing local/minio-bucket; printf any-sync-test | mc pipe local/minio-bucket/probe; test \\\"$(mc cat local/minio-bucket/probe)\\\" = any-sync-test")

    client.copy_from_host("${clientConfigPath}", "/tmp/any-sync-client.yml")
    client.copy_from_host("${unreachableClientConfigPath}", "/tmp/unreachable-client.yml")
    client.succeed("getent passwd any-sync-test | grep -q '/home/any-sync-test'")
    client.succeed("systemctl show --property=User --value any-sync-consensus.service | grep -qx any-sync-test")
    client.succeed("systemctl show --property=Group --value any-sync-consensus.service | grep -qx any-sync-test")

    # Wait for services to be up
    server.wait_for_unit("any-sync-consensus.service");
    server.wait_for_unit("any-sync-coordinator.service");
    server.wait_for_unit("any-sync-filenode.service");
    server.wait_for_unit("any-sync-node-1.service");
    server.wait_for_unit("any-sync-node-2.service");
    server.wait_for_unit("any-sync-node-3.service");

    # node-1
    server.wait_for_open_port(1101);  # tcp yamux
    server.wait_until_succeeds("ss -unl | grep -q :1111");  # quic
    # node-2
    server.wait_for_open_port(1102);  # tcp yamux
    server.wait_until_succeeds("ss -unl | grep -q :1112");  # quic
    # node-3
    server.wait_for_open_port(1103);  # tcp yamux
    server.wait_until_succeeds("ss -unl | grep -q :1113");  # quic
    # coordinator
    server.wait_for_open_port(1104);  # tcp yamux
    server.wait_until_succeeds("ss -unl | grep -q :1114")  # quic
    # filenode
    server.wait_for_open_port(1105);  # tcp yamux
    server.wait_until_succeeds("ss -unl | grep -q :1115");  # quic
    # consesus
    server.wait_for_open_port(1106);  # tcp yamux
    server.wait_until_succeeds("ss -unl | grep -q :1116")  # quic

    server.succeed("systemctl show -p After any-sync-filenode.service | grep -q 'redis-anysync-files.service'")
    server.succeed("systemctl show -p After any-sync-filenode.service | grep -q 'minio.service'")
    server.succeed("systemctl show -p After any-sync-node-1.service | grep -q 'any-sync-filenode.service'")
    server.succeed("for dir in consensus coordinator file-node node-1 node-2 node-3; do su -s /bin/sh any-sync -c \"test -w /var/lib/any-sync/$dir\"; done")
    client.fail("any-sync-netcheck -c /tmp/unreachable-client.yml")
    client.succeed("any-sync-netcheck -c /tmp/any-sync-client.yml");
  '';
}
