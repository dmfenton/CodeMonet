.PHONY: install dev-web dev-stop server server-bg server-logs server-stop server-restart web test test-web test-ios-kit test-e2e test-e2e-sdk test-record-fixture test-replay lint format typecheck clean cli cli-turn cli-status build-shared ios-generate ios-build ios-test ios-kit-test

# Install all dependencies
install:
	cd server && uv sync
	npm install --legacy-peer-deps

# Run server only (foreground)
server:
	cd server && uv run python -m code_monet.main

# Run server in background with logging (for Claude debugging)
server-bg:
	@mkdir -p server/logs
	@if curl -s localhost:8000/debug/agent > /dev/null 2>&1; then \
		echo "Server already running"; \
	else \
		cd server && nohup uv run python -m code_monet.main > logs/server.log 2>&1 & \
		sleep 2; \
		if curl -s localhost:8000/debug/agent > /dev/null 2>&1; then \
			pgrep -f "code_monet.main" | head -1 > server/logs/server.pid; \
			echo "Server started (PID $$(cat server/logs/server.pid)). Logs: server/logs/server.log"; \
		else \
			echo "Server failed to start. Check server/logs/server.log"; \
		fi; \
	fi

# Tail server logs
server-logs:
	@tail -f server/logs/server.log

# Stop server
server-stop:
	@PID=$$(pgrep -f "code_monet.main" | head -1); \
	if [ -n "$$PID" ]; then \
		kill $$PID 2>/dev/null; \
		sleep 1; \
		echo "Server stopped (PID $$PID)"; \
	else \
		echo "Server not running"; \
	fi; \
	rm -f server/logs/server.pid

# Restart server (background mode)
server-restart: server-stop
	@sleep 1
	@$(MAKE) server-bg

# CLI commands for testing agent
cli:
	cd server && uv run python -m code_monet.cli --help

cli-turn:
	cd server && uv run python -m code_monet.cli run-turn

cli-status:
	cd server && uv run python -m code_monet.cli status

# Run web dev server only
web:
	cd web && npm run dev

# Run server + Vite web app (foreground, Ctrl+C to stop)
dev-web:
	@./scripts/dev-web.sh

# Kill any stuck dev servers by port
dev-stop:
	@./scripts/kill-dev.sh

# Run all tests: server + web + native MonetKit
test: test-server test-web test-ios-kit

test-server:
	cd server && uv run pytest

test-web:
	npm run test -w web

# Native SwiftUI app: XcodeGen project + MonetKit Swift package
ios-generate:
	cd ios && $(MAKE) generate

ios-build:
	cd ios && $(MAKE) build

ios-test:
	cd ios && $(MAKE) test-app

ios-kit-test:
	cd ios && $(MAKE) test-kit

test-ios-kit: ios-kit-test

# E2E SDK integration tests (fetches API key from SSM)
test-e2e-sdk:
	cd server && CODE_MONET_ENV=prod AWS_REGION=us-east-1 uv run pytest -m e2e tests/test_e2e_sdk.py -v

# Record WebSocket message fixtures (fetches API key from SSM)
test-record-fixture:
	cd server && CODE_MONET_ENV=prod AWS_REGION=us-east-1 uv run pytest -m e2e tests/test_e2e_websocket_recording.py -v -k "test_record"

# Run web reducer replay tests (fast, no API)
test-replay:
	npm run test -w web -- reducer.replay

# Run all integration/E2E tests (excluding iOS Simulator tests)
test-e2e: test-e2e-sdk test-replay

# Run tests with coverage
coverage:
	cd server && uv run pytest --cov=code_monet --cov-report=html

# Build shared library
build-shared:
	cd shared && npm run build

# Lint all code
lint: lint-server lint-shared lint-web

lint-server:
	cd server && uv run ruff check .

lint-shared:
	cd shared && npm run lint

lint-web:
	cd web && npm run lint

# Format all code
format: format-server format-js

format-server:
	cd server && uv run ruff format .

format-js:
	npm run format

# Check formatting without writing
format-check: format-check-server format-check-js

format-check-server:
	cd server && uv run ruff format --check .

format-check-js:
	npm run format:check

# Type checking
typecheck: typecheck-server typecheck-shared typecheck-web

typecheck-server:
	cd server && uv run python -m mypy code_monet

typecheck-shared:
	cd shared && npm run typecheck

typecheck-web:
	cd web && npm run typecheck

# Clean build artifacts
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "node_modules" -exec rm -rf {} + 2>/dev/null || true
	rm -rf server/.ruff_cache 2>/dev/null || true
	rm -rf shared/dist 2>/dev/null || true
	cd ios && $(MAKE) clean
