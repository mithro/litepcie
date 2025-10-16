# Contributing to LitePCIe

Thank you for your interest in contributing to LitePCIe!

## Getting Started

1. **Fork the repository**
2. **Clone your fork**:
   ```bash
   git clone https://github.com/YOUR-USERNAME/litepcie.git
   cd litepcie
   ```
3. **Install development dependencies**:
   ```bash
   pip install -r test/requirements.txt
   pip install pre-commit
   pre-commit install
   ```

## Code Quality Standards

**Before contributing, read**: `docs/code-quality.md`

Key points:
- Follow Migen/LiteX conventions
- Use NumPy-style docstrings
- Test behavior, not structure
- No TODOs in critical paths
- Document with PCIe spec references

## Development Workflow

1. **Create a branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make changes**:
   - Write tests first (TDD)
   - Implement functionality
   - Update documentation

3. **Run tests locally**:
   ```bash
   pytest test/ -v --cov=litepcie
   ```

4. **Commit with quality checks**:
   ```bash
   git add .
   git commit  # Pre-commit hooks run automatically
   ```

5. **Push and create PR**:
   ```bash
   git push origin feature/your-feature-name
   ```
   Then create Pull Request on GitHub

## Pull Request Guidelines

### PR Must Include:
- [ ] Tests for new functionality
- [ ] Documentation updates
- [ ] Code quality checks pass (pre-commit)
- [ ] All CI tests pass
- [ ] Coverage >= 80% for new code

### PR Description Should:
- Explain what changed and why
- Reference related issues
- Note any breaking changes
- Include usage examples if adding features

## Testing

### Run All Tests
```bash
pytest test/ -v
```

### Run Specific Test File
```bash
pytest test/dll/test_dllp.py -v
```

### Check Coverage
```bash
pytest test/ --cov=litepcie --cov-report=html
open htmlcov/index.html
```

### Run Pre-commit Manually
```bash
pre-commit run --all-files
```

## Code Review Process

1. Maintainer reviews code for:
   - Functionality correctness
   - Code quality adherence
   - Test coverage
   - Documentation completeness

2. Address review feedback

3. Once approved, maintainer merges

## Questions?

- Open an issue for bugs or feature requests
- Ask in discussions for questions
- Email maintainers for security issues

## License

By contributing, you agree to license your contributions under the BSD-2-Clause license.
