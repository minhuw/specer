# Specer

[![CI](https://github.com/minhuw/specer/workflows/CI/badge.svg)](https://github.com/minhuw/specer/actions)
[![codecov](https://codecov.io/gh/minhuw/specer/branch/main/graph/badge.svg)](https://codecov.io/gh/minhuw/specer)
[![PyPI version](https://badge.fury.io/py/specer.svg)](https://badge.fury.io/py/specer)
[![Python versions](https://img.shields.io/pypi/pyversions/specer.svg)](https://pypi.org/project/specer/)
[![License](https://img.shields.io/github/license/minhuw/specer.svg)](https://github.com/minhuw/specer/blob/main/LICENSE)

A modern Python project built with the latest tools and best practices.

## Features

- 🚀 Modern Python package structure with `src/` layout
- 📦 Built with [rye](https://rye-up.com/) and [uv](https://github.com/astral-sh/uv) for fast dependency management
- 🧪 Comprehensive testing with [pytest](https://pytest.org/)
- 🔧 Pre-commit hooks with modern linting and formatting tools
- 🏗️ GitHub Actions CI/CD pipeline
- 📝 Type hints with [mypy](https://mypy.readthedocs.io/)
- 🎨 Code formatting with [black](https://black.readthedocs.io/) and [ruff](https://docs.astral.sh/ruff/)
- 🛡️ Security scanning with [bandit](https://bandit.readthedocs.io/) and [safety](https://pyup.io/safety/)

## Installation

```bash
pip install specer
```

## Development

This project uses [rye](https://rye-up.com/) for dependency management. To get started:

```bash
# Clone the repository
git clone https://github.com/minhuw/specer.git
cd specer

# Install dependencies
rye sync

# Install pre-commit hooks
rye run pre-commit install

# Run tests
rye run pytest

# Run linting
rye run ruff check src/ tests/
rye run mypy src/

# Format code
rye run black src/ tests/
rye run ruff format src/ tests/
```

## Usage

```python
from specer import hello

print(hello())  # "Hello from specer!"
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting
5. Submit a pull request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
