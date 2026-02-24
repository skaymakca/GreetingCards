.PHONY: help setup setup-dev run app build clean icon html-content licenses-sync loc version bump-patch bump-minor bump-major tag tag-push test test-cov test-unit test-gui test-watch tessdata pyright mypy show-scripts

# awk helper: format "LABEL  NUMBER lines" with right-aligned thousands-separated number
# Usage: echo COUNT | awk -v lbl="Python:" '$(FMT_LINE)'
define FMT_LINE
{n=$$1; s=""; while(n>999){s=sprintf(",%03d%s",n%1000,s); n=int(n/1000)} v=sprintf("%d%s",n,s); printf "%-10s%10s lines\n",lbl,v}
endef

help: ## Show this help message
	@echo "Greeting Cards - Available make commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'
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

TESSDATA_DIR := _runtime_content/tessdata/fast
TESSDATA_ENG := $(TESSDATA_DIR)/eng.traineddata
TESSDATA_URL := https://github.com/tesseract-ocr/tessdata_fast/raw/main/eng.traineddata

tessdata: $(TESSDATA_ENG) ## Download tessdata (eng.traineddata)
$(TESSDATA_ENG):
	@mkdir -p $(TESSDATA_DIR)
	@curl -sL -o $@ $(TESSDATA_URL)

run: html-content tessdata ## Run the app from source
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

pyright: ## Run pyright type checking on app/ and scripts/
	uv run pyright app/ scripts/

mypy: ## Run mypy type checking on app/ and scripts/
	uv run mypy app/ scripts/

build: app ## Build the macOS .app bundle (alias for 'app')

LSREGISTER := /System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister

html-content: ## Generate all HTML content (help, changelog, licenses)
	@mkdir -p _runtime_content/html/common/css _runtime_content/html/common/js _runtime_content/images
	@cp content/html/common/css/viewer.css _runtime_content/html/common/css/viewer.css
	@cp content/html/common/js/search.js _runtime_content/html/common/js/search.js
	@cp content/images/drop-target-background.png _runtime_content/images/drop-target-background.png
	uv run python -c "from app.core.help_builder import generate_help_html; generate_help_html()"
	uv run python -c "from app.core.changelog import generate_changelog_html; generate_changelog_html()"
	uv run python -c "from app.core.license_discovery import generate_licenses_html; generate_licenses_html()"

licenses-sync: ## Sync license registry from uv.lock + .dist-info
	uv run python -c "from app.core.license_discovery import sync_registry; sync_registry()"

app: icon html-content tessdata ## Build the macOS .app bundle
	@$(LSREGISTER) -u "dist/Greeting Cards.app" 2>/dev/null || true
	uv run pyinstaller -y "Greeting Cards.spec"

icon: content/images/icon.png ## Generate icon.icns from icon.png
	@mkdir -p _runtime_content icon.iconset
	@sips -z 16 16 content/images/icon.png --out icon.iconset/icon_16x16.png > /dev/null
	@sips -z 32 32 content/images/icon.png --out icon.iconset/icon_16x16@2x.png > /dev/null
	@sips -z 32 32 content/images/icon.png --out icon.iconset/icon_32x32.png > /dev/null
	@sips -z 64 64 content/images/icon.png --out icon.iconset/icon_32x32@2x.png > /dev/null
	@sips -z 128 128 content/images/icon.png --out icon.iconset/icon_128x128.png > /dev/null
	@sips -z 256 256 content/images/icon.png --out icon.iconset/icon_128x128@2x.png > /dev/null
	@sips -z 256 256 content/images/icon.png --out icon.iconset/icon_256x256.png > /dev/null
	@sips -z 512 512 content/images/icon.png --out icon.iconset/icon_256x256@2x.png > /dev/null
	@sips -z 512 512 content/images/icon.png --out icon.iconset/icon_512x512.png > /dev/null
	@sips -z 1024 1024 content/images/icon.png --out icon.iconset/icon_512x512@2x.png > /dev/null
	@iconutil -c icns icon.iconset -o _runtime_content/icon.icns
	@rm -rf icon.iconset
	@echo "Generated _runtime_content/icon.icns"

loc: ## Count lines of code (excludes dependencies)
	@echo "Lines of code (project files only):"
	@echo ""
	@find . -name "*.py" -not -path "./.venv/*" -not -path "./build/*" -not -path "./dist/*" -not -path "*/__pycache__/*" -exec cat {} + | wc -l | awk -v lbl="Python:" '$(FMT_LINE)'
	@(find ./app -name "*.py" -not -path "*/gui/*" -not -path "*/__pycache__/*" -exec cat {} + ; cat main.py) | wc -l | awk -v lbl="  Core:" '$(FMT_LINE)'
	@find ./app/gui -name "*.py" -not -path "*/__pycache__/*" -exec cat {} + | wc -l | awk -v lbl="  GUI:" '$(FMT_LINE)'
	@find ./scripts -name "*.py" -not -path "*/__pycache__/*" -exec cat {} + | wc -l | awk -v lbl="  Scripts:" '$(FMT_LINE)'
	@find ./tests -name "*.py" -not -path "*/__pycache__/*" -exec cat {} + | wc -l | awk -v lbl="  Tests:" '$(FMT_LINE)'
	@echo ""
	@find ./content/html/help \( -name "*.md" \) -exec cat {} + 2>/dev/null | wc -l | awk -v lbl="Help MD:" '$(FMT_LINE)'
	@find ./content \( -name "*.css" -o -name "*.js" -o -name "*.j2" \) -exec cat {} + 2>/dev/null | wc -l | awk -v lbl="Web:" '$(FMT_LINE)'
	@echo ""
	@wc -l Makefile "Greeting Cards.spec" 2>/dev/null | tail -1 | awk -v lbl="Config:" '$(FMT_LINE)'
	@echo ""
	@(find . -name "*.py" -not -path "./.venv/*" -not -path "./build/*" -not -path "./dist/*" -not -path "*/__pycache__/*" -exec cat {} + ; find ./content/html/help -name "*.md" -exec cat {} + 2>/dev/null; find ./content \( -name "*.css" -o -name "*.js" -o -name "*.j2" \) -exec cat {} + 2>/dev/null; cat Makefile "Greeting Cards.spec") | wc -l | awk -v lbl="Total:" '$(FMT_LINE)'

version: ## Show current version
	@uv run python -c "from app.version import __version__; print(__version__)"

bump-patch: ## Bump patch version (0.5.0 → 0.5.1)
	@uv run python -c "\
	p='app/version.py'; v=open(p).read().split('\"')[1].split('.'); \
	v=[int(x) for x in v]; v[2]+=1; nv='.'.join(map(str,v)); \
	open(p,'w').write(f'__version__ = \"{nv}\"\n'); print(nv)"
	@sed -i '' 's/^version = ".*"/version = "'$$(uv run python -c "from app.version import __version__; print(__version__)")'"/' pyproject.toml

bump-minor: ## Bump minor version (0.5.1 → 0.6.0)
	@uv run python -c "\
	p='app/version.py'; v=open(p).read().split('\"')[1].split('.'); \
	v=[int(x) for x in v]; v[1]+=1; v[2]=0; nv='.'.join(map(str,v)); \
	open(p,'w').write(f'__version__ = \"{nv}\"\n'); print(nv)"
	@sed -i '' 's/^version = ".*"/version = "'$$(uv run python -c "from app.version import __version__; print(__version__)")'"/' pyproject.toml

bump-major: ## Bump major version (0.6.0 → 1.0.0)
	@uv run python -c "\
	p='app/version.py'; v=open(p).read().split('\"')[1].split('.'); \
	v=[int(x) for x in v]; v[0]+=1; v[1]=0; v[2]=0; nv='.'.join(map(str,v)); \
	open(p,'w').write(f'__version__ = \"{nv}\"\n'); print(nv)"
	@sed -i '' 's/^version = ".*"/version = "'$$(uv run python -c "from app.version import __version__; print(__version__)")'"/' pyproject.toml

tag: ## Create git tag vX.Y.Z from current version
	@v=$$(uv run python -c "from app.version import __version__; print(__version__)"); \
	git tag "v$$v" && echo "Tagged v$$v"

tag-push: ## Push all tags to remote
	@git push --tags && echo "Tags pushed"

visual-test: html-content ## Run visual test harness from source
	uv run python scripts/visual_test.py

visual-test-app: icon html-content tessdata ## Build visual test harness as .app bundle
	uv run pyinstaller -y "scripts/Visual Test.spec"

show-scripts: ## Show available script invocations (does not run them)
	@echo "Available scripts (run with uv run python -m scripts.<name>):"
	@echo ""
	@echo "  \033[36mgenerate_sample_cards\033[0m        Generate sample greeting card PDFs for testing"
	@echo "    uv run python -m scripts.generate_sample_cards --layout-cards=5"
	@echo "    uv run python -m scripts.generate_sample_cards --full-image-cards=5"
	@echo "    uv run python -m scripts.generate_sample_cards --layout-cards=5 --no-images"
	@echo ""
	@echo "  \033[36mbenchmark.ocr_configuration_quality\033[0m  Benchmark Tesseract config space (192 configs)"
	@echo "    uv run python -m scripts.benchmark.ocr_configuration_quality ~/Desktop/Cards"
	@echo ""
	@echo "  \033[36mbenchmark.pre_processing_concurrency\033[0m Benchmark preprocessing concurrency models"
	@echo "    uv run python -m scripts.benchmark.pre_processing_concurrency ~/Desktop/Cards"
	@echo ""
	@echo "  \033[36mbenchmark.ocr_concurrency\033[0m    Benchmark OCR concurrency (sequential/threads/processes)"
	@echo "    uv run python -m scripts.benchmark.ocr_concurrency ~/Desktop/Cards"
	@echo ""
	@echo "  All scripts support --help, --no-open, and -o <output_dir>."
	@echo "  Output goes to _script_output/ with timestamped directories."

clean: ## Remove build artifacts
	@$(LSREGISTER) -u "dist/Greeting Cards.app" 2>/dev/null || true
	rm -rf build dist _runtime_content
