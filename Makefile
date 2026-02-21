.PHONY: help setup setup-dev run app build clean icon loc version bump-patch bump-minor bump-major tag tag-push test test-cov test-unit test-gui test-watch

# awk helper: format "LABEL  NUMBER lines" with right-aligned thousands-separated number
# Usage: echo COUNT | awk -v lbl="Python:" '$(FMT_LINE)'
define FMT_LINE
{n=$$1; s=""; while(n>999){s=sprintf(",%03d%s",n%1000,s); n=int(n/1000)} v=sprintf("%d%s",n,s); printf "%-10s%10s lines\n",lbl,v}
endef

help: ## Show this help message
	@echo "Greeting Cards - Available make commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'
	@echo ""

setup: ## Install production dependencies (creates venv automatically)
	uv sync --no-dev
	@echo ""
	@echo "✓ Setup complete! Production dependencies installed."
	@echo "  Run 'make setup-dev' to install development/testing tools."

setup-dev: ## Install all dependencies including dev/testing tools
	uv sync
	@echo ""
	@echo "✓ Development setup complete!"
	@echo "  Run 'make test' to run tests."

run: ## Run the app from source
	@if [ -z "$$ANTHROPIC_API_KEY" ]; then \
		echo "INFO: ANTHROPIC_API_KEY not set in environment"; \
		echo "      Set via: export ANTHROPIC_API_KEY=sk-ant-..."; \
		echo "      Or enter it in Settings (Cmd+,)"; \
		echo ""; \
	fi
	uv run python main.py

test: ## Run all tests
	uv run pytest -v

test-cov: ## Run tests with coverage report
	uv run pytest --cov=app --cov-report=html --cov-report=term-missing
	@echo ""
	@echo "Coverage report generated: htmlcov/index.html"

test-unit: ## Run unit tests only (fast)
	uv run pytest -v -m unit

test-gui: ## Run GUI tests only
	uv run pytest -v -m gui

test-watch: ## Run tests on file changes (requires pytest-watch)
	uv run ptw -- -v

build: app ## Build the macOS .app bundle (alias for 'app')

LSREGISTER := /System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister

app: icon ## Build the macOS .app bundle
	@$(LSREGISTER) -u "dist/Greeting Cards.app" 2>/dev/null || true
	uv run pyinstaller -y "Greeting Cards.spec"

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
	@find . -name "*.py" -not -path "./.venv/*" -not -path "./build/*" -not -path "./dist/*" -not -path "*/__pycache__/*" -exec cat {} + | wc -l | awk -v lbl="Python:" '$(FMT_LINE)'
	@(find ./app -name "*.py" -not -path "*/gui/*" -not -path "*/__pycache__/*" -exec cat {} + ; cat main.py) | wc -l | awk -v lbl="  Core:" '$(FMT_LINE)'
	@find ./app/gui -name "*.py" -not -path "*/__pycache__/*" -exec cat {} + | wc -l | awk -v lbl="  GUI:" '$(FMT_LINE)'
	@find ./tests -name "*.py" -not -path "*/__pycache__/*" -exec cat {} + | wc -l | awk -v lbl="  Tests:" '$(FMT_LINE)'
	@echo ""
	@find ./help \( -name "*.html" -o -name "*.css" \) -exec cat {} + | wc -l | awk -v lbl="HTML/CSS:" '$(FMT_LINE)'
	@echo ""
	@wc -l Makefile "Greeting Cards.spec" 2>/dev/null | tail -1 | awk -v lbl="Config:" '$(FMT_LINE)'
	@echo ""
	@(find . -name "*.py" -not -path "./.venv/*" -not -path "./build/*" -not -path "./dist/*" -not -path "*/__pycache__/*" -exec cat {} + ; find ./help \( -name "*.html" -o -name "*.css" \) -exec cat {} + ; cat Makefile "Greeting Cards.spec") | wc -l | awk -v lbl="Total:" '$(FMT_LINE)'

version: ## Show current version
	@uv run python -c "from app.version import __version__; print(__version__)"

bump-patch: ## Bump patch version (0.5.0 → 0.5.1)
	@uv run python -c "\
	p='app/version.py'; v=open(p).read().split('\"')[1].split('.'); \
	v=[int(x) for x in v]; v[2]+=1; nv='.'.join(map(str,v)); \
	open(p,'w').write(f'__version__ = \"{nv}\"\n'); print(nv)"

bump-minor: ## Bump minor version (0.5.1 → 0.6.0)
	@uv run python -c "\
	p='app/version.py'; v=open(p).read().split('\"')[1].split('.'); \
	v=[int(x) for x in v]; v[1]+=1; v[2]=0; nv='.'.join(map(str,v)); \
	open(p,'w').write(f'__version__ = \"{nv}\"\n'); print(nv)"

bump-major: ## Bump major version (0.6.0 → 1.0.0)
	@uv run python -c "\
	p='app/version.py'; v=open(p).read().split('\"')[1].split('.'); \
	v=[int(x) for x in v]; v[0]+=1; v[1]=0; v[2]=0; nv='.'.join(map(str,v)); \
	open(p,'w').write(f'__version__ = \"{nv}\"\n'); print(nv)"

tag: ## Create git tag vX.Y.Z from current version
	@v=$$(uv run python -c "from app.version import __version__; print(__version__)"); \
	git tag "v$$v" && echo "Tagged v$$v"

tag-push: ## Push all tags to remote
	@git push --tags && echo "Tags pushed"

clean: ## Remove build artifacts
	@$(LSREGISTER) -u "dist/Greeting Cards.app" 2>/dev/null || true
	rm -rf build dist icon.iconset
