.PHONY: help setup setup-dev run app build clean icon loc version bump-patch bump-minor bump-major tag tag-push test test-cov test-unit test-gui test-watch

help: ## Show this help message
	@echo "Greeting Cards - Available make commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'
	@echo ""

setup: ## Create venv and install production dependencies
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt
	@echo ""
	@echo "✓ Setup complete! Production dependencies installed."
	@echo "  Run 'make setup-dev' to install development/testing tools."

setup-dev: ## Install development dependencies (includes testing tools)
	@if [ ! -d .venv ]; then \
		echo "Error: .venv not found. Run 'make setup' first."; \
		exit 1; \
	fi
	.venv/bin/pip install -r requirements-dev.txt
	@echo ""
	@echo "✓ Development setup complete!"
	@echo "  Run 'make test' to run tests."

run: ## Run the app from source
	@if [ -z "$$ANTHROPIC_API_KEY" ]; then \
		echo "INFO: ANTHROPIC_API_KEY not set in environment"; \
		echo "      AI features will prompt for API key or read from .env file"; \
		echo ""; \
	fi
	.venv/bin/python main.py

test: ## Run all tests
	.venv/bin/python -m pytest -v

test-cov: ## Run tests with coverage report
	.venv/bin/python -m pytest --cov=app --cov-report=html --cov-report=term-missing
	@echo ""
	@echo "Coverage report generated: htmlcov/index.html"

test-unit: ## Run unit tests only (fast)
	.venv/bin/python -m pytest -v -m unit

test-gui: ## Run GUI tests only
	.venv/bin/python -m pytest -v -m gui

test-watch: ## Run tests on file changes (requires pytest-watch)
	.venv/bin/ptw -- -v

build: app ## Build the macOS .app bundle (alias for 'app')

app: icon ## Build the macOS .app bundle
	.venv/bin/pyinstaller -y "Greeting Cards.spec"

icon: icon.png ## Generate icon.icns from icon.png
	@mkdir -p icon.iconset
	@sips -z 16 16 icon.png --out icon.iconset/icon_16x16.png > /dev/null
	@sips -z 32 32 icon.png --out icon.iconset/icon_16x16@2x.png > /dev/null
	@sips -z 32 32 icon.png --out icon.iconset/icon_32x32.png > /dev/null
	@sips -z 64 64 icon.png --out icon.iconset/icon_32x32@2x.png > /dev/null
	@sips -z 128 128 icon.png --out icon.iconset/icon_128x128.png > /dev/null
	@sips -z 256 256 icon.png --out icon.iconset/icon_128x128@2x.png > /dev/null
	@sips -z 256 256 icon.png --out icon.iconset/icon_256x256.png > /dev/null
	@sips -z 512 512 icon.png --out icon.iconset/icon_256x256@2x.png > /dev/null
	@sips -z 512 512 icon.png --out icon.iconset/icon_512x512.png > /dev/null
	@sips -z 1024 1024 icon.png --out icon.iconset/icon_512x512@2x.png > /dev/null
	@iconutil -c icns icon.iconset -o icon.icns
	@rm -rf icon.iconset
	@echo "Generated icon.icns"

loc: ## Count lines of code (excludes dependencies)
	@echo "Lines of code (project files only):"
	@echo ""
	@echo "Python files:"
	@find . -name "*.py" -not -path "./.venv/*" -not -path "./build/*" -not -path "./dist/*" -not -path "*/__pycache__/*" -exec wc -l {} + | tail -1 | awk '{print "  " $$1 " lines"}'
	@echo ""
	@echo "Other project files:"
	@wc -l Makefile "Greeting Cards.spec" 2>/dev/null | tail -1 | awk '{print "  " $$1 " lines"}'
	@echo ""
	@echo "Total project LOC:"
	@(find . -name "*.py" -not -path "./.venv/*" -not -path "./build/*" -not -path "./dist/*" -not -path "*/__pycache__/*" -exec cat {} + ; cat Makefile "Greeting Cards.spec") | wc -l | awk '{print "  " $$1 " lines"}'

version: ## Show current version
	@python3 -c "from app.version import __version__; print(__version__)"

bump-patch: ## Bump patch version (0.5.0 → 0.5.1)
	@python3 -c "\
	p='app/version.py'; v=open(p).read().split('\"')[1].split('.'); \
	v=[int(x) for x in v]; v[2]+=1; nv='.'.join(map(str,v)); \
	open(p,'w').write(f'__version__ = \"{nv}\"\n'); print(nv)"

bump-minor: ## Bump minor version (0.5.1 → 0.6.0)
	@python3 -c "\
	p='app/version.py'; v=open(p).read().split('\"')[1].split('.'); \
	v=[int(x) for x in v]; v[1]+=1; v[2]=0; nv='.'.join(map(str,v)); \
	open(p,'w').write(f'__version__ = \"{nv}\"\n'); print(nv)"

bump-major: ## Bump major version (0.6.0 → 1.0.0)
	@python3 -c "\
	p='app/version.py'; v=open(p).read().split('\"')[1].split('.'); \
	v=[int(x) for x in v]; v[0]+=1; v[1]=0; v[2]=0; nv='.'.join(map(str,v)); \
	open(p,'w').write(f'__version__ = \"{nv}\"\n'); print(nv)"

tag: ## Create git tag vX.Y.Z from current version
	@v=$$(python3 -c "from app.version import __version__; print(__version__)"); \
	git tag "v$$v" && echo "Tagged v$$v"

tag-push: ## Push all tags to remote
	@git push --tags && echo "Tags pushed"

clean: ## Remove build artifacts
	rm -rf build dist icon.iconset
