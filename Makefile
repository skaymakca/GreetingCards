.PHONY: help run app build clean icon loc

help: ## Show this help message
	@echo "Greeting Cards - Available make commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'
	@echo ""

run: ## Run the app from source
	@if [ -z "$$ANTHROPIC_API_KEY" ]; then \
		echo "INFO: ANTHROPIC_API_KEY not set in environment"; \
		echo "      AI features will prompt for API key or read from .env file"; \
		echo ""; \
	fi
	.venv/bin/python main.py

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

clean: ## Remove build artifacts
	rm -rf build dist icon.iconset
