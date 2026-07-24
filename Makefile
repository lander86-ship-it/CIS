# Handy shortcuts for the CIS Benchmark app (CLI + Web UI).
# `make help` lists everything.

IMAGE ?= cis-bench:local
COMPOSE ?= docker compose

.DEFAULT_GOAL := help

.PHONY: help build rebuild up down logs login auth-status version shell local clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

build: ## Build the container image
	$(COMPOSE) build

rebuild: ## Rebuild the image from scratch (no cache)
	$(COMPOSE) build --no-cache

up: ## Start the Web UI at http://localhost:8000
	$(COMPOSE) up ui

down: ## Stop the Web UI
	$(COMPOSE) down

logs: ## Tail the Web UI logs
	$(COMPOSE) logs -f ui

login: ## CLI: headless login with ./data/cookies.txt
	$(COMPOSE) run --rm cli auth login --cookies /data/cookies.txt

auth-status: ## CLI: show authentication status
	$(COMPOSE) run --rm cli auth status

version: ## CLI: print the cis-bench version
	$(COMPOSE) run --rm cli --version

shell: ## Open a shell inside the image (debugging)
	$(COMPOSE) run --rm --entrypoint /bin/bash cli

local: ## Run the Web UI natively (no Docker) via ./run-local.sh
	./run-local.sh

clean: ## Remove the built image (keeps ./data and ./work)
	-docker image rm $(IMAGE)
