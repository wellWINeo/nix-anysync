# Build each declared package locally. This target needs no AWS credentials.
build-all:
	python3 scripts/build-all.py

# Publishing is intentionally performed only by the trusted GitHub Actions
# workflow, which obtains short-lived AWS credentials via OIDC.
