.PHONY: help setup setup-dev tessdata run test test-everything check pyright mypy lint lint-fix format format-check security pycharm-inspect content licenses-sync icon app app-run dmg release-publish configure-release shellcheck version bump-patch bump-minor bump-major tag tag-push visual-test visual-test-app show-scripts loc docker-build docker-test docker-shell clean

# awk helper: format "LABEL  NUMBER lines" with right-aligned thousands-separated number
# Usage: echo COUNT | awk -v lbl="Python:" '$(FMT_LINE)'
define FMT_LINE
{n=$$1; s=""; while(n>999){s=sprintf(",%03d%s",n%1000,s); n=int(n/1000)} v=sprintf("%d%s",n,s); printf "%-10s%10s lines\n",lbl,v}
endef

# Banner macro for section headers in `make check` output (fixed 64-char width)
define banner
	@label="$(1)"; n=$$(( 60 - $${#label} )); \
	trail=$$(printf '%*s' "$$n" '' | sed 's/ /─/g'); \
	printf '\n\033[1m── %s %s\033[0m\n\n' "$$label" "$$trail"
endef

TESSDATA_DIR := _build/runtime_content/tessdata/fast
TESSDATA_ENG := $(TESSDATA_DIR)/eng.traineddata
TESSDATA_URL := https://github.com/tesseract-ocr/tessdata_fast/raw/main/eng.traineddata
INSPECT_OUT := /tmp/pycharm-inspect-out
PYCHARM_APP ?= $(firstword $(wildcard $(HOME)/Applications/PyCharm.app $(HOME)/Applications/PyCharm\ CE.app /Applications/PyCharm.app /Applications/PyCharm\ CE.app))
LSREGISTER := /System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister

help: # Show this help message
	@echo "Greeting Cards - Available make commands:"
	@echo ""
	@awk '/^##@/{printf "\n  \033[1m%s\033[0m\n",substr($$0,5)} /^[a-zA-Z_-]+:.*## /{t=$$0;sub(/:.*/, "",t);d=$$0;sub(/^[^#]*## /,"",d);printf "  \033[36m%-18s\033[0m %s\n",t,d}' $(MAKEFILE_LIST)
	@echo ""

##@ Setup

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

tessdata: $(TESSDATA_ENG) ## Download tessdata (eng.traineddata)
$(TESSDATA_ENG):
	@mkdir -p $(TESSDATA_DIR)
	@curl -sL -o $@ $(TESSDATA_URL)

##@ Development

run: content tessdata ## Run the app from source
	uv run python main.py

test: ## Run tests (no args shows help; make test T="core --cov -x")
	@uv run python scripts/run_tests.py $(T)

test-everything: ## Run all tests with coverage and open reports
	@uv run python scripts/run_tests.py all --cov --open

##@ Code Quality

check: pyright mypy lint format-check security ## Run all static checks

pyright: ## Run pyright type checking
	$(call banner,Pyright)
	pyright app/ scripts/ main.py

mypy: ## Run mypy type checking
	$(call banner,Mypy)
	uv run mypy app/ scripts/ main.py

lint: ## Run ruff linter
	$(call banner,Ruff Lint)
	uv run ruff check app/ scripts/ tests/ main.py

lint-fix: ## Run ruff linter with auto-fix
	uv run ruff check --fix app/ scripts/ tests/ main.py

format: ## Format code with ruff
	uv run ruff format app/ scripts/ tests/ main.py

format-check: ## Check formatting (no changes)
	$(call banner,Ruff Format Check)
	uv run ruff format --check app/ scripts/ tests/ main.py

security: ## Run bandit security scan
	$(call banner,Bandit Security)
	uv run bandit -r app/ scripts/ -c pyproject.toml

pycharm-inspect: ## Run PyCharm inspections (requires PyCharm; skipped if not installed)
	@if [ -z "$(PYCHARM_APP)" ] || [ ! -x "$(PYCHARM_APP)/Contents/bin/inspect.sh" ]; then \
		echo "PyCharm not found — skipping pycharm-inspect (set PYCHARM_APP to override)"; \
	else \
		echo "Using $(PYCHARM_APP)"; \
		rm -rf "$(INSPECT_OUT)"; \
		"$(PYCHARM_APP)/Contents/bin/inspect.sh" "$(CURDIR)" \
			.idea/inspectionProfiles/Project_Default.xml \
			"$(INSPECT_OUT)" -v2; \
		echo ""; \
		echo "Results written to $(INSPECT_OUT)/"; \
		xml_count=$$(find "$(INSPECT_OUT)" -name "*.xml" 2>/dev/null | wc -l | tr -d ' '); \
		if [ "$$xml_count" = "0" ]; then \
			echo "No inspection findings."; \
		else \
			echo "$$xml_count inspection result file(s). Open in PyCharm: Code > Inspect Code > Load Results."; \
		fi; \
	fi

##@ Build

content: ## Generate runtime content (HTML, data files, images)
	@mkdir -p _build/runtime_content/html/common/css _build/runtime_content/html/common/js _build/runtime_content/images _build/runtime_content/data
	@cp content/html/common/css/viewer.css _build/runtime_content/html/common/css/viewer.css
	@cp content/html/common/js/search.js _build/runtime_content/html/common/js/search.js
	@cp content/html/common/css/highlight.css _build/runtime_content/html/common/css/highlight.css
	@cp content/html/common/js/highlight.min.js _build/runtime_content/html/common/js/highlight.min.js
	@cp content/images/drop-target-background.png _build/runtime_content/images/drop-target-background.png
	@gzip -c content/data/family_name_database.tsv > _build/runtime_content/data/family_name_database.tsv.gz
	uv run python -c "from app.core.content.help_builder import generate_help_html; generate_help_html()"
	uv run python -c "from app.core.content.changelog import generate_changelog_html; generate_changelog_html()"
	uv run python -c "from app.core.content.license_html import generate_licenses_html; generate_licenses_html()"

licenses-sync: ## Sync license registry from uv.lock + .dist-info
	uv run python -c "from app.core.content.license_sync import sync_registry; sync_registry()"

icon: content/images/icon.png ## Generate icon.icns from icon.png
	@mkdir -p _build/runtime_content icon.iconset
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
	@iconutil -c icns icon.iconset -o _build/runtime_content/icon.icns
	@rm -rf icon.iconset
	@echo "Generated _build/runtime_content/icon.icns"

app: icon content tessdata ## Build the macOS .app bundle
	@$(LSREGISTER) -u "dist/Greeting Cards.app" 2>/dev/null || true
	uv run pyinstaller --workpath _build/pyinstaller_build -y "packaging/Greeting Cards.spec"
	@rm -rf "dist/Greeting Cards"

app-run: app ## Build and run the .app bundle (logs visible in terminal)
	"dist/Greeting Cards.app/Contents/MacOS/Greeting Cards"

dmg: app ## Build the distributable DMG installer
	uv run python -m scripts.dmg

##@ Version & Release

version: ## Show current version
	@uv run python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"

bump-patch: ## Bump patch version (0.5.0 → 0.5.1)
	@uv run python -c "\
	import tomllib; p='pyproject.toml'; \
	v=tomllib.load(open(p,'rb'))['project']['version'].split('.'); \
	v=[int(x) for x in v]; v[2]+=1; nv='.'.join(map(str,v)); \
	t=open(p).read().replace('version = \"'+'.'.join(map(str,[v[0],v[1],v[2]-1]))+'\"\n','version = \"'+nv+'\"\n',1); \
	open(p,'w').write(t); print(nv)"

bump-minor: ## Bump minor version (0.5.1 → 0.6.0)
	@uv run python -c "\
	import tomllib; p='pyproject.toml'; \
	old=tomllib.load(open(p,'rb'))['project']['version']; \
	v=[int(x) for x in old.split('.')]; v[1]+=1; v[2]=0; nv='.'.join(map(str,v)); \
	t=open(p).read().replace('version = \"'+old+'\"','version = \"'+nv+'\"',1); \
	open(p,'w').write(t); print(nv)"

bump-major: ## Bump major version (0.6.0 → 1.0.0)
	@uv run python -c "\
	import tomllib; p='pyproject.toml'; \
	old=tomllib.load(open(p,'rb'))['project']['version']; \
	v=[int(x) for x in old.split('.')]; v[0]+=1; v[1]=0; v[2]=0; nv='.'.join(map(str,v)); \
	t=open(p).read().replace('version = \"'+old+'\"','version = \"'+nv+'\"',1); \
	open(p,'w').write(t); print(nv)"

release-publish: ## Publish the latest draft release
	uv run python -m scripts.release publish

configure-release: ## Configure local signing identity & profile (generates release-local.sh)
	uv run python -m scripts.configure_release

shellcheck: ## Run shellcheck on release-local.sh (if it exists)
	@if [ -f release-local.sh ]; then shellcheck release-local.sh; else echo "No release-local.sh found. Run 'make configure-release' first."; fi

tag: ## Create git tag vX.Y.Z from current version
	@v=$$(uv run python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"); \
	git tag "v$$v" && echo "Tagged v$$v"

tag-push: ## Push all tags to remote
	@git push --tags && echo "Tags pushed"

##@ Tools

visual-test: content ## Run visual test harness from source
	uv run python scripts/visual_test.py

visual-test-app: icon content tessdata ## Build and run visual test harness as .app bundle (logs visible)
	uv run pyinstaller --workpath _build/pyinstaller_build -y "packaging/Visual Test.spec"
	@rm -rf "dist/Visual Test"
	"dist/Visual Test.app/Contents/MacOS/Visual Test"

show-scripts: ## Show available script invocations (does not run them)
	@echo "Available scripts (run with uv run python -m scripts.<name>):"
	@echo ""
	@echo "  \033[36mbenchmark.ocr_concurrency\033[0m    Benchmark OCR concurrency (sequential/threads/processes)"
	@echo "    uv run python -m scripts.benchmark.ocr_concurrency ~/Desktop/Cards"
	@echo ""
	@echo "  \033[36mbenchmark.ocr_configuration_quality\033[0m  Benchmark Tesseract config space (192 configs)"
	@echo "    uv run python -m scripts.benchmark.ocr_configuration_quality ~/Desktop/Cards"
	@echo ""
	@echo "  \033[36mbenchmark.pre_processing_concurrency\033[0m Benchmark preprocessing concurrency models"
	@echo "    uv run python -m scripts.benchmark.pre_processing_concurrency ~/Desktop/Cards"
	@echo ""
	@echo "  \033[36mbuild_family_name_db\033[0m         Build master family name database from Census + Faker + smashew"
	@echo "    uv run python -m scripts.build_family_name_db"
	@echo "    uv run python -m scripts.build_family_name_db --no-smashew"
	@echo ""
	@echo "  \033[36mbuild_family_name_db.benchmark_compression\033[0m  Benchmark compression formats for the name database"
	@echo "    uv run python -m scripts.build_family_name_db.benchmark_compression"
	@echo ""
	@echo "  \033[36mdark_mode_cycler\033[0m             Toggle macOS dark/light mode every 5s (Ctrl-C to stop)"
	@echo "    uv run python -m scripts.dark_mode_cycler"
	@echo ""
	@echo "  \033[36mgenerate_diagnostic_cards\033[0m    Generate diagnostic PDFs with fixed family name text"
	@echo "    uv run python -m scripts.generate_diagnostic_cards --names \"Smith,O'Brien,Van Dyke\""
	@echo ""
	@echo "  \033[36mgenerate_sample_cards\033[0m        Generate sample greeting card PDFs for testing"
	@echo "    uv run python -m scripts.generate_sample_cards --count=5"
	@echo "    uv run python -m scripts.generate_sample_cards --names \"Smith,O'Brien,Van Dyke\""
	@echo ""
	@echo "  \033[36mprofiling\033[0m                    Profile the PDF processing pipeline (render, OCR, names, AI mock)"
	@echo "    uv run python -m scripts.profiling ~/Desktop/Cards"
	@echo "    uv run python -m scripts.profiling ~/Desktop/Cards --limit 10"
	@echo ""
	@echo "  \033[36mreformat_md_tables\033[0m           Reformat markdown tables for PyCharm"
	@echo "    uv run python -m scripts.reformat_md_tables docs/**/*.md README.md CLAUDE.md"
	@echo ""
	@echo "  \033[36mdmg\033[0m                          Build the distributable DMG installer"
	@echo "    uv run python -m scripts.dmg"
	@echo ""
	@echo "  \033[36msign\033[0m                         Sign the app bundle for distribution"
	@echo "    uv run python -m scripts.sign"
	@echo "    uv run python -m scripts.sign --identity \"-\" --dry-run"
	@echo ""
	@echo "  \033[36mnotarize\033[0m                     Apple notarization (async workflow)"
	@echo "    uv run python -m scripts.notarize submit          # submit to notary"
	@echo "    uv run python -m scripts.notarize status          # check status"
	@echo "    uv run python -m scripts.notarize log             # fetch log"
	@echo "    uv run python -m scripts.notarize staple          # staple + verify"
	@echo "    uv run python -m scripts.notarize --dry-run submit"
	@echo ""
	@echo "  \033[36mrelease\033[0m                      Release automation (changelog, checksum, GitHub release)"
	@echo "    uv run python -m scripts.release changelog"
	@echo "    uv run python -m scripts.release checksum"
	@echo "    uv run python -m scripts.release draft"
	@echo "    uv run python -m scripts.release publish"
	@echo ""
	@echo "  \033[36mconfigure_release\033[0m            Configure local signing identity & notarization profile"
	@echo "    uv run python -m scripts.configure_release"
	@echo ""
	@echo "  All scripts support --help."
	@echo "  Output goes to _build/script_output/ with timestamped directories."

loc: ## Count lines of code (excludes dependencies)
	@echo "Lines of code (project files only):"
	@echo ""
	@find . -name "*.py" -not -path "./.venv/*" -not -path "./_build/*" -not -path "./dist/*" -not -path "./.claude/*" -not -path "*/__pycache__/*" -exec cat {} + | wc -l | awk -v lbl="Python:" '$(FMT_LINE)'
	@(find ./app -name "*.py" -not -path "*/gui/*" -not -path "*/__pycache__/*" -exec cat {} + ; cat main.py) | wc -l | awk -v lbl="  Core:" '$(FMT_LINE)'
	@find ./app/gui -name "*.py" -not -path "*/__pycache__/*" -exec cat {} + | wc -l | awk -v lbl="  GUI:" '$(FMT_LINE)'
	@find ./scripts -name "*.py" -not -path "*/__pycache__/*" -exec cat {} + | wc -l | awk -v lbl="  Scripts:" '$(FMT_LINE)'
	@find ./tests -name "*.py" -not -path "*/__pycache__/*" -exec cat {} + | wc -l | awk -v lbl="  Tests:" '$(FMT_LINE)'
	@echo ""
	@find ./content/html/help \( -name "*.md" \) -exec cat {} + 2>/dev/null | wc -l | awk -v lbl="Help MD:" '$(FMT_LINE)'
	@find ./content \( -name "*.css" -o -name "*.js" -o -name "*.j2" \) -exec cat {} + 2>/dev/null | wc -l | awk -v lbl="Web:" '$(FMT_LINE)'
	@echo ""
	@wc -l Makefile "packaging/Greeting Cards.spec" 2>/dev/null | tail -1 | awk -v lbl="Config:" '$(FMT_LINE)'
	@echo ""
	@(find . -name "*.py" -not -path "./.venv/*" -not -path "./_build/*" -not -path "./dist/*" -not -path "./.claude/*" -not -path "*/__pycache__/*" -exec cat {} + ; find ./content/html/help -name "*.md" -exec cat {} + 2>/dev/null; find ./content \( -name "*.css" -o -name "*.js" -o -name "*.j2" \) -exec cat {} + 2>/dev/null; cat Makefile "packaging/Greeting Cards.spec") | wc -l | awk -v lbl="Total:" '$(FMT_LINE)'

##@ Docker

docker-build: ## Build the Linux test image
	docker build -t greeting-cards-test -f docker/Dockerfile .

docker-test: ## Run tests in Linux container
	docker compose -f docker/docker-compose.yml run --rm test-linux

docker-shell: ## Interactive shell in Linux container
	docker compose -f docker/docker-compose.yml run --rm test-linux /bin/bash

##@ Cleanup

clean: ## Remove build artifacts
	@$(LSREGISTER) -u "dist/Greeting Cards.app" 2>/dev/null || true
	rm -rf _build dist
