# Handy shortcuts for the containerized CIS Benchmark CLI.
# `make help` lists everything.

IMAGE ?= cis-bench:local
COMPOSE ?= docker compose

.DEFAULT_GOAL := help

.PHONY: help build rebuild auth-status login shell version clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

build: ## Build the container image
	$(COMPOSE) build

rebuild: ## Rebuild the image from scratch (no cache)
	$(COMPOSE) build --no-cache

login: ## Authenticate headless with a Netscape cookies file at ./data/cookies.txt
	$(COMPOSE) run --rm cis-bench auth login --cookies /data/cookies.txt

auth-status: ## Show current authentication status
	$(COMPOSE) run --rm cis-bench auth status

version: ## Print the CLI version inside the container
	$(COMPOSE) run --rm cis-bench --version

shell: ## Open a shell inside the container (debugging)
	$(COMPOSE) run --rm --entrypoint /bin/bash cis-bench

clean: ## Remove the built image (keeps ./data and ./work)
	-docker image rm $(IMAGE)
