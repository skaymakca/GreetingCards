# Coverage: excluded (runtime profiler, instruments live app) — see [tool.coverage.run] omit in pyproject.toml
from scripts.profiling.cli import main

if __name__ == "__main__":
    main()
