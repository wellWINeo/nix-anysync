# Build each declared package locally. This target needs no AWS credentials.
build-all:
	python3 scripts/build-all.py

# Publishing is intentionally performed only by the trusted GitHub Actions
# workflow, which uses IAM-user credentials stored as repository secrets.
