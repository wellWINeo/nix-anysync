build-and-upload-all:
	for pkg in consensus coordinator filenode node tools; do \
		nix build "path:.#any-sync-$$pkg" ; \
		$(MAKE) upload-result ; \
	done

upload-result:
	nix copy $(shell readlink result) \
		--to 's3://nix-cache?endpoint=https://storage.yandexcloud.net&region=ru-central1&secret-key=$(NIX_CACHE_PRIVATE_KEYFILE)'
