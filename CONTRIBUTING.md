# Contributing to Spotim8

Thank you for your interest in contributing to Spotim8! This document provides guidelines and instructions for contributing.

## Getting Started

### Development Setup

1. **Fork and Clone**:
   ```bash
   git clone https://github.com/YOUR_USERNAME/spotim8.git
   cd spotim8
   ```

2. **Create Virtual Environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Dependencies**:
   ```bash
   pip install --upgrade pip
   pip install -e ".[dev]"
   ```

4. **Set Up Environment**:
   ```bash
   cp env.example .env
   # Edit .env with your Spotify API credentials
   ```

## Code Style

### Python Code

- **Formatting**: Use `black` for code formatting
  ```bash
  black spotim8/ scripts/
  ```

- **Linting**: Use `ruff` for linting
  ```bash
  ruff check spotim8/ scripts/
  ```

- **Type Hints**: Prefer type hints for function signatures
- **Docstrings**: Use Google-style docstrings for all public functions and classes
- **Line Length**: Maximum 100 characters

### Example Code Style

```python
from typing import Optional
import pandas as pd

def example_function(
    param1: str,
    param2: Optional[int] = None
) -> pd.DataFrame:
    """
    Brief description of the function.
    
    Args:
        param1: Description of param1
        param2: Description of param2 (optional)
    
    Returns:
        DataFrame with results
    
    Example:
        >>> result = example_function("test", 42)
        >>> len(result) > 0
        True
    """
    # Implementation here
    pass
```

## Project Structure

```
spotim8/
├── spotim8/              # Core library
│   ├── client.py         # Main Spotim8 class
│   ├── catalog.py        # Data caching
│   └── ...
├── scripts/              # Organized by category
│   ├── automation/       # Sync & automation scripts
│   ├── playlist/         # Playlist management scripts
│   └── utils/            # Utility scripts
├── notebooks/            # Jupyter notebooks for analysis
├── examples/             # Example code
└── tests/                # Test suite
```

### Where to Add Code

- **New Features**: Add to `spotim8/` module
- **Scripts**: Add to appropriate subdirectory in `scripts/`
- **Examples**: Add to `examples/`
- **Notebooks**: Add to `notebooks/` (use descriptive names)

## Testing

### Run Tests

```bash
pytest tests/
```

### Write Tests

- Add tests for new features in `tests/`
- Use descriptive test names
- Test both success and error cases

Example:
```python
def test_feature_success():
    """Test that feature works correctly."""
    result = feature_function(input)
    assert result is not None
    assert len(result) > 0

def test_feature_error_handling():
    """Test that feature handles errors gracefully."""
    with pytest.raises(ValueError):
        feature_function(invalid_input)
```

## Making Changes

### Workflow

1. **Create a Branch**:
   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/bug-description
   ```

2. **Make Changes**:
   - Write code following the style guide
   - Add tests for new features
   - Update documentation if needed

3. **Test Your Changes**:
   ```bash
   # Run tests
   pytest tests/
   
   # Format code
   black spotim8/ scripts/
   
   # Lint code
   ruff check spotim8/ scripts/
   ```

4. **Commit Changes**:
   ```bash
   git add .
   git commit -m "Description of changes"
   ```
   
   **Commit Message Guidelines**:
   - Use clear, descriptive messages
   - Start with a verb (Add, Fix, Update, Remove)
   - Keep first line under 72 characters
   - Add more details in body if needed

5. **Push and Create Pull Request**:
   ```bash
   git push origin feature/your-feature-name
   ```
   
   Then create a Pull Request on GitHub.

## Pull Request Process

### Before Submitting

- [ ] Code follows the style guide
- [ ] Tests pass (`pytest tests/`)
- [ ] Code is formatted (`black spotim8/ scripts/`)
- [ ] Code is linted (`ruff check spotim8/ scripts/`)
- [ ] Documentation updated if needed
- [ ] Commit messages are clear and descriptive

### Pull Request Description

Include:
- **What**: Description of changes
- **Why**: Reason for changes
- **How**: Brief explanation of implementation
- **Testing**: How you tested the changes

### Review Process

- Maintainers will review your PR
- Address any feedback or requested changes
- Once approved, your PR will be merged

## Documentation

### Update Documentation

- **README.md**: Update for user-facing changes
- **CHANGELOG.md**: Add entry for significant changes
- **Code Comments**: Add/update docstrings for API changes
- **Examples**: Update examples if API changes

### Documentation Style

- Use clear, concise language
- Include examples where helpful
- Keep formatting consistent with existing docs

## Questions?

- Open an issue for questions or discussions
- Check existing issues first
- Be respectful and constructive

## Code of Conduct

- Be respectful and inclusive
- Welcome newcomers
- Focus on constructive feedback
- Help others learn and grow

Thank you for contributing to Spotim8! 🎵

