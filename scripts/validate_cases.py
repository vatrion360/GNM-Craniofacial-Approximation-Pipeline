"""Source checkout entry point; installed users can run python -m cranio.validation_cases."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cranio.validation_cases import main

if __name__ == '__main__':
    raise SystemExit(main())
