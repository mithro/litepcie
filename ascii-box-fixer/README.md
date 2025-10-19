# ASCII Box Border Fixer

A Python tool for fixing misaligned borders in ASCII box diagrams in documentation files.

## Problem

ASCII box diagrams often have misaligned right borders. This tool automatically aligns all vertical borders (`│`) to match the position of the top-right corner (`┐`).

**Before:**
```
┌─────────┐
│ Content│
│ Text   │
└─────────┘
```

**After:**
```
┌─────────┐
│ Content │
│ Text    │
└─────────┘
```

## Features

- ✅ Fixes simple boxes
- ✅ Handles nested boxes correctly
- ✅ Supports multiple boxes in the same file
- ✅ In-place file editing or stdout output
- ✅ Recursive directory processing
- ✅ Dry-run mode for safe previewing
- ✅ Comprehensive error handling
- ✅ File size limits and permission checks
- ✅ No external dependencies (pure Python stdlib)
- ✅ Fully type-annotated
- ✅ Extensively tested (29 test cases)

## Installation

### As a standalone script

Simply copy `fix_ascii_boxes.py` to your project:

```bash
wget https://raw.githubusercontent.com/yourusername/fix-ascii-boxes/main/fix_ascii_boxes.py
chmod +x fix_ascii_boxes.py
```

### Using pip (if published)

```bash
pip install fix-ascii-boxes
```

### For development

```bash
git clone https://github.com/yourusername/fix-ascii-boxes.git
cd fix-ascii-boxes
pip install -e .
```

## Usage

### Command Line

#### Preview changes (output to stdout)

```bash
python3 fix_ascii_boxes.py file.md
```

#### Fix file in-place

```bash
python3 fix_ascii_boxes.py --in-place file.md
```

#### Fix all markdown files in directory (recursive)

```bash
python3 fix_ascii_boxes.py --in-place --recursive docs/
```

#### Dry-run mode (show what would change without modifying files)

```bash
python3 fix_ascii_boxes.py --dry-run --in-place --verbose docs/
```

#### Process specific file patterns

```bash
python3 fix_ascii_boxes.py --in-place --recursive --pattern "*.md" docs/
python3 fix_ascii_boxes.py --in-place --recursive --pattern "*.txt" .
```

#### Verbose output

```bash
python3 fix_ascii_boxes.py --verbose --in-place file.md
```

### Programmatic API

You can also use the tool as a Python library:

```python
from fix_ascii_boxes import BoxParser, BoxAligner, FileProcessor

# Parse boxes in text
parser = BoxParser()
text = """
┌─────┐
│ Hi │
└─────┘
"""
boxes = parser.parse(text)
print(f"Found {len(boxes)} boxes")

# Fix alignment
aligner = BoxAligner()
fixed_text = aligner.fix(text)
print(fixed_text)

# Process files
processor = FileProcessor()

# Single file
processor.process_file("docs/file.md", in_place=True)

# Directory
count = processor.process_directory(
    "docs/",
    pattern="*.md",
    in_place=True,
    dry_run=False
)
print(f"Processed {count} files")
```

## Examples

See the [examples/](examples/) directory for before/after examples:
- Simple box alignment
- Nested boxes
- Multiple boxes in one file

## How It Works

1. **Detection**: Scans for box top-left corners (`┌`) and finds matching bottom-right corners (`┘`)
   - Uses optimized string search with `str.find()` instead of character-by-character iteration
   - Validates that boxes have proper structure (vertical bars, complete corners)

2. **Nesting Analysis**: Identifies which boxes are nested within others
   - Calculates nesting level by checking containment
   - Ensures nested boxes are processed independently

3. **Alignment**: Aligns all right-side vertical borders (`│`) to match the top-right corner (`┐`)
   - Preserves content by adding appropriate padding
   - Handles edge cases (empty boxes, very wide boxes, etc.)

4. **Processing Order**: Processes innermost boxes first to prevent interference
   - Sorts boxes by nesting level (deepest first)
   - Each box is processed independently

5. **Safety Features**:
   - File size limit (10MB) to prevent memory issues
   - Permission checks before writing
   - Comprehensive error handling
   - Dry-run mode for safe testing

## Testing

Run the comprehensive test suite:

```bash
# Option 1: Using unittest (no dependencies, quickest)
python3 test_fix_ascii_boxes.py

# Option 2: Using pytest with uv
uv run --extra dev pytest -v

# Option 3: Using pytest (if installed)
pytest test_fix_ascii_boxes.py -v

# Run with coverage (if installed)
coverage run -m pytest test_fix_ascii_boxes.py
coverage report
```

The test suite includes 29 tests covering:
- Box detection and parsing
- Simple and nested box alignment
- Edge cases (incomplete boxes, very wide boxes, Unicode content)
- File processing operations
- CLI integration
- Error handling

## Development

### Code Quality Tools

The project includes configuration for:
- **black**: Code formatting
- **ruff**: Fast linting
- **mypy**: Type checking
- **pre-commit**: Git hooks for quality checks

Install development dependencies:

```bash
pip install black ruff mypy pre-commit pytest pytest-cov
```

Setup pre-commit hooks:

```bash
pre-commit install
```

Run linters:

```bash
black .
ruff check .
mypy fix_ascii_boxes.py
```

### CI/CD

The project includes GitHub Actions workflows for:
- Running tests on Python 3.7-3.12
- Code linting and formatting checks
- Type checking
- Coverage reporting

## Troubleshooting

### File size too large error
The tool has a 10MB file size limit. For larger files, process them in chunks or increase `MAX_FILE_SIZE` in the code.

### Permission denied error
Ensure you have write permissions for the target files when using `--in-place`.

### Unicode encoding issues
All files are processed as UTF-8. If you encounter encoding errors, ensure your files are UTF-8 encoded.

### Box not detected
The tool looks for complete boxes with:
- Top-left corner: `┌`
- Top-right corner: `┐`
- Bottom-left corner: `└`
- Bottom-right corner: `┘`
- Vertical bars: `│` between top and bottom

If any component is missing, the box won't be detected.

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Run code quality tools (black, ruff, mypy)
6. Submit a pull request

## License

MIT License

## Credits

Created with Test-Driven Development methodology using comprehensive test coverage.
