# Contributing to VeriClaim

First off, thank you for considering contributing to VeriClaim!

## How to Contribute

### Reporting Bugs
If you find a bug, please create an issue on GitHub and provide as much detail as possible, including:
* A clear and descriptive title.
* Steps to reproduce the issue.
* Expected behavior vs. actual behavior.
* Environment details (Docker, macOS/Linux/Windows).

### Suggesting Enhancements
We welcome suggestions for new features or improvements. When suggesting an enhancement, please include:
* A clear description of the feature and why it would be useful.
* Any potential alternatives you've considered.

### Pull Requests
1. Fork the repository and create your branch from `main`.
2. Ensure you have followed the setup instructions in the `README.md` and that the application runs locally.
3. Make your code changes.
4. If you've added code that should be tested, please add tests in the `tests/` directory.
5. Ensure your code passes all linting and test checks.
6. Issue that pull request!

## Development Setup

We recommend using `uv` for local development.

```bash
# create .venv and install all deps from uv.lock
uv sync --dev              

# Run the dev server
uv run uvicorn app.main:app --reload

# Run tests
uv run pytest
```

Alternatively, use the provided Docker Compose setup:
```bash
make dev
make migrate
make seed
```

## Code Style
* Please follow standard Python formatting (e.g., using `black` or `ruff`).
* Ensure Type Hints are used for all new functions and methods.

## License
By contributing, you agree that your contributions will be licensed under the MIT License.
