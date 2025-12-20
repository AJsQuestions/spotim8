# Contributing to Spotim8

Thank you for your interest in contributing to Spotim8! This document provides guidelines for contributing.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/yourusername/spotim8.git`
3. Install in development mode: `pip install -e ".[dev]"`
4. Set up your Spotify credentials (see `env.example`)

## Development Setup

### Python Library

```bash
# Install with dev dependencies
pip install -e ".[all]"

# Run tests
pytest tests/

# Format code
black spotim8/
ruff check spotim8/
```

### Web App

```bash
cd spotim8_app

# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build
```

## Code Style

- **Python**: Follow PEP 8, use `black` for formatting, `ruff` for linting
- **TypeScript/React**: Use consistent patterns from existing code
- **Commits**: Use clear, descriptive commit messages

## Pull Request Process

1. Create a feature branch from `main`
2. Make your changes with clear commits
3. Test your changes locally
4. Update documentation if needed
5. Submit a pull request with a clear description

## Project Structure

```
spotim8/           # Python library core
spotim8_app/       # React web application
notebooks/         # Jupyter notebooks for analysis
scripts/           # Automation scripts
tests/             # Test suite
```

## Questions?

Feel free to open an issue for questions or discussions.

