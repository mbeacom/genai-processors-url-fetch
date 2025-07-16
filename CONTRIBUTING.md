# Contributing to genai-processors-url-fetch

Thank you for your interest in contributing to genai-processors-url-fetch! This document provides guidelines and information for contributors.

## 🛠️ Development Setup

### Prerequisites

- Python 3.11 or higher
- [uv](https://docs.astral.sh/uv/) - Fast Python package manager
- Git

### Getting Started

1. **Clone the repository**:

   ```bash
   git clone https://github.com/mbeacom/genai-processors-url-fetch.git
   cd genai-processors-url-fetch
   ```

2. **Install dependencies with uv**:

   ```bash
   uv sync --dev
   ```

3. **Install pre-commit hooks**:

   ```bash
   uv run pre-commit install
   ```

4. **Verify setup by running tests**:

   ```bash
   uv run pytest
   ```

## 🔧 Development Tools

### Package Management: uv

We use [uv](https://docs.astral.sh/uv/) as our package manager for its speed and reliability:

- **Install dependencies**: `uv sync`
- **Add new dependency**: `uv add package-name`
- **Add dev dependency**: `uv add --dev package-name`
- **Run commands**: `uv run command`
- **Build package**: `uv build`

### Task Runner: Poe the Poet

This project uses [Poe the Poet](https://poethepoet.natn.io/) as a task runner to simplify common development workflows. After running `uv sync --all-groups`, you can use `uv run poe <task>` to execute any of the following tasks:

#### View Available Tasks

```bash
# See all available tasks with descriptions
uv run poe --help

# Get help for a specific task
uv run poe --help <task_name>

# See what a task would do without running it (for individual commands)
uv run poe --dry-run <task_name>
```

> **Note**: The `--dry-run` option works with individual command tasks but not with sequence tasks (like `fix`, `check`, `security`). For sequence tasks, refer to their descriptions to see which sub-tasks they run.

#### Code Quality & Linting

```bash
# Auto-fix code issues (recommended for development)
uv run poe fix           # Run ruff --fix and black formatting

# Check code quality without making changes
uv run poe check         # Run ruff, black, and mypy checks
uv run poe check-ruff    # Check with ruff linter only
uv run poe check-black   # Check black formatting only
uv run poe check-mypy    # Check type annotations only

# Individual tools
uv run poe ruff          # Run ruff with --fix
uv run poe black         # Format code with black
```

#### Testing with Poe

```bash
# Run all tests with coverage report
uv run poe test          # Runs pytest with coverage (XML + terminal output)

# Run specific tests (bypass poe for more control)
uv run pytest genai_processors_url_fetch/tests/test_url_fetch.py -v
uv run pytest genai_processors_url_fetch/tests/ -k "test_security"
```

#### Security Analysis

```bash
# Run security analysis
uv run poe security      # Run bandit security linter
uv run poe bandit        # Run bandit directly
```

#### Build & Distribution

```bash
# Install dependencies
uv run poe install      # Equivalent to 'uv sync --all-groups'

# Build the package
uv run poe build        # Create wheel and source distribution
```

#### Pre-commit Hooks (if using)

```bash
# Update pre-commit hooks
uv run poe update-precommit-hooks

# Run all pre-commit hooks
uv run poe check-precommit-hooks
```

#### Common Development Workflows

```bash
# Before committing (recommended)
uv run poe fix && uv run poe test && uv run poe security

# Quick development cycle
uv run poe fix          # Fix formatting and linting
uv run poe test         # Run tests
# Make changes...
uv run poe check        # Verify everything looks good

# Full quality check
uv run poe check && uv run poe test && uv run poe security
```

### Code Quality: Pre-commit

Pre-commit hooks run automatically before each commit to ensure code quality:

- **Manual run**: `uv run pre-commit run --all-files`
- **Update hooks**: `uv run pre-commit autoupdate`

Our pre-commit configuration includes:

- **Ruff**: Fast Python linter and formatter (autofix enabled)
- **Black**: Code formatting
- **Bandit**: Security vulnerability scanning
- **Standard hooks**: trailing whitespace, merge conflicts, JSON/YAML validation

> **Note**: Markdown linting is handled separately due to Ruby version dependencies.

### Testing: pytest

- **Run all tests**: `uv run pytest`
- **Run with verbose output**: `uv run pytest -v`
- **Run specific test**: `uv run pytest genai_processors_url_fetch/tests/test_url_fetch.py::TestUrlFetchProcessor::test_successful_fetch_with_mocking`
- **Run with coverage**: `uv run pytest --cov=genai_processors_url_fetch`

### Code Formatting and Linting

#### Ruff (Primary Linter/Formatter)

Ruff handles most linting and some formatting:

- **Lint**: `uv run ruff check`
- **Lint with autofix**: `uv run ruff check --fix`
- **Format**: `uv run ruff format`

#### Black (Code Formatting)

Black ensures consistent code formatting:

- **Format**: `uv run black .`
- **Check formatting**: `uv run black --check .`

#### Bandit (Security Scanning)

Bandit scans for security vulnerabilities:

- **Scan**: `uv run bandit -c pyproject.toml -r genai_processors_url_fetch/`

> **Note**: We use both Ruff and Bandit because Ruff currently supports only a subset of Bandit's security checks. As Ruff's security coverage improves, we may transition fully to Ruff.

## 🚀 CI/CD Pipeline

### GitHub Actions

Our CI/CD pipeline automatically:

1. **On Pull Requests**:
   - Runs all tests across Python 3.11, 3.12, and 3.13
   - Validates code formatting and linting
   - Runs security scans
   - Checks package builds successfully

2. **On Tag/Release** (coming soon):
   - Automatically publishes to PyPI
   - Creates GitHub releases with changelog

### Local Testing

Before submitting a PR, ensure your changes pass all checks:

```bash
# Run pre-commit checks
uv run pre-commit run --all-files

# Run full test suite
uv run pytest -v

# Verify package builds
uv build

# Check security
uv run bandit -c pyproject.toml -r genai_processors_url_fetch/
```

## 📝 Contributing Guidelines

### Code Style

- Follow [PEP 8](https://peps.python.org/pep-0008/) style guidelines
- Use type hints for all function signatures
- Write comprehensive docstrings for public APIs
- Keep line length under 88 characters (Black default)

### Testing

- Write tests for all new functionality
- Maintain or improve test coverage
- Use descriptive test names that explain what is being tested
- Include both positive and negative test cases

### Documentation

- Update README.md for user-facing changes
- Update MAINTAINER_FEEDBACK.md for architectural decisions
- Include docstrings for all public functions and classes
- Add examples for new features

### Commit Messages

Use conventional commit format:

- `feat: add new validation feature`
- `fix: resolve serialization issue`
- `docs: update API documentation`
- `test: add missing test cases`
- `refactor: improve error handling`

## 🐛 Bug Reports

When reporting bugs, please include:

1. **Environment**: Python version, OS, package version
2. **Reproduction**: Minimal code example that reproduces the issue
3. **Expected vs Actual**: What you expected to happen vs what actually happened
4. **Error messages**: Full stack traces if applicable

Use the issue template when available.

## 💡 Feature Requests

For new features:

1. **Check existing issues** to avoid duplicates
2. **Describe the use case** and why it's valuable
3. **Propose implementation** if you have ideas
4. **Consider breaking changes** and backward compatibility

See [MAINTAINER_FEEDBACK.md](MAINTAINER_FEEDBACK.md) for our current roadmap and known limitations.

## 🔄 Pull Request Process

1. **Fork the repository** and create a feature branch
2. **Make your changes** following the guidelines above
3. **Write tests** for any new functionality
4. **Update documentation** as needed
5. **Run all checks** locally before submitting
6. **Submit pull request** with:
   - Clear description of changes
   - Reference to related issues
   - Test coverage information

### PR Checklist

- [ ] Tests pass locally (`uv run pytest`)
- [ ] Code follows style guidelines (`uv run pre-commit run --all-files`)
- [ ] Documentation updated if needed
- [ ] CHANGELOG.md updated for user-facing changes
- [ ] Breaking changes documented in MAINTAINER_FEEDBACK.md

## 🏗️ Project Structure

```zsh
genai-processors-url-fetch/
├── genai_processors_url_fetch/    # Main package
│   ├── __init__.py               # Package exports
│   ├── url_fetch.py              # Core UrlFetchProcessor
│   └── tests/                    # Test suite
├── examples/                     # Usage examples
├── .github/                      # GitHub Actions workflows
├── pyproject.toml               # Project configuration
├── README.md                    # User documentation
├── MAINTAINER_FEEDBACK.md       # Technical roadmap
└── CONTRIBUTING.md              # This file
```

## 📦 Release Process

Releases are automated via GitHub Actions:

1. **Create a tag**: `git tag v0.1.0`
2. **Push tag**: `git push origin v0.1.0`
3. **GitHub Actions** automatically:
   - Builds the package
   - Runs full test suite
   - Publishes to PyPI
   - Creates GitHub release

For maintainers only.

## 🤝 Community

- **Issues**: Use GitHub Issues for bug reports and feature requests
- **Discussions**: Use GitHub Discussions for questions and ideas
- **Pull Requests**: All contributions welcome!

## 📄 License

By contributing, you agree that your contributions will be licensed under the Apache 2.0 License.

---

Thank you for contributing to genai-processors-url-fetch! 🎉
