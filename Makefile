.PHONY: help install dev upstream test lint clean check

help:            ## Show this help
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install:         ## Install the package
	pip install -e .

dev:             ## Install with dev dependencies
	pip install -e ".[dev]"

upstream:        ## Vendor youtube-deepsummary
	./scripts/install_upstream.sh

test:            ## Run the test suite (offline)
	pytest -q

lint:            ## Check shell scripts parse
	@for f in scripts/*.sh; do bash -n "$$f" && echo "ok $$f"; done

check:           ## Fact-check a video: make check URL=https://...
	@test -n "$(URL)" || (echo "usage: make check URL=https://youtube.com/watch?v=..." && exit 1)
	deepcheck check "$(URL)" -f md,html

clean:           ## Remove build artifacts and caches
	rm -rf build dist *.egg-info .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
