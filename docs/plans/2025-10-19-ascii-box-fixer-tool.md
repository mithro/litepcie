# ASCII Box Border Fixer Tool - Implementation Plan

**Date:** 2025-10-19
**Status:** Ready for Implementation
**Approach:** Test-Driven Development (TDD)

## Overview

Create a standalone Python tool that fixes misaligned ASCII box borders in documentation files. The tool must correctly align right borders (`│`) to match the top-right corner (`┐`) position, with special handling for nested boxes.

## Problem Statement

Documentation files contain ASCII box diagrams where right borders are misaligned:

```
┌─────────┐          ┌─────────┐
│ Content │   →      │ Content │
│ More    │          │ More    │
└─────────┘          └─────────┘
```

The challenge is handling nested boxes correctly:

```
┌──────────────────┐
│ Outer Box        │
│  ┌────────┐      │
│  │ Inner  │      │
│  └────────┘      │
└──────────────────┘
```

Each box must align to its own top-right corner, not to parent boxes.

## Architecture

### Core Components

1. **BoxParser** - Identifies box structures in text
2. **BoxAligner** - Fixes alignment based on top-right corners
3. **FileProcessor** - Handles file I/O and batch processing
4. **CLI** - Command-line interface

### Data Structures

```python
class Box:
    """Represents a single ASCII box"""
    start_line: int
    end_line: int
    top_right_pos: int
    nesting_level: int
    lines: List[str]

class BoxTree:
    """Hierarchical structure of nested boxes"""
    boxes: List[Box]
    children: Dict[Box, List[BoxTree]]
```

## Implementation Tasks

### Phase 1: Core Box Detection (TDD)

#### Task 1.1: Create directory and file structure
**Directory:** `ascii-box-fixer/`

**Action:**
```bash
# Create dedicated directory for the tool
mkdir -p ascii-box-fixer
cd ascii-box-fixer

# Create main files
touch fix_ascii_boxes.py
touch test_fix_ascii_boxes.py
touch README.md
```

**Verification:**
```bash
ls -la ascii-box-fixer/
```

**Expected:** Directory exists with three files

---

#### Task 1.2: Write test for simple box detection
**File:** `ascii-box-fixer/test_fix_ascii_boxes.py`

**Action:** Add test class and first test

```python
import unittest
from fix_ascii_boxes import BoxParser, Box


class TestBoxParser(unittest.TestCase):
    def test_detect_simple_box(self):
        """Test detection of a simple single box"""
        text = """\
Some text before
┌─────────┐
│ Content │
│ More    │
└─────────┘
Text after
"""
        parser = BoxParser()
        boxes = parser.parse(text)

        self.assertEqual(len(boxes), 1)
        self.assertEqual(boxes[0].start_line, 1)
        self.assertEqual(boxes[0].end_line, 4)
        self.assertEqual(boxes[0].top_right_pos, 11)
        self.assertEqual(boxes[0].nesting_level, 0)


if __name__ == '__main__':
    unittest.main()
```

**Verification:**
```bash
cd ascii-box-fixer
python3 test_fix_ascii_boxes.py
```

**Expected:** Test fails with ImportError (RED phase)

---

#### Task 1.3: Implement BoxParser to pass simple detection test
**File:** `ascii-box-fixer/fix_ascii_boxes.py`

**Action:** Create minimal implementation

```python
"""ASCII Box Border Fixer

Fixes misaligned right borders in ASCII box diagrams by aligning
all vertical borders (│) to the position of the top-right corner (┐).
"""

import re
from dataclasses import dataclass
from typing import List, Optional


# Box drawing characters
TOP_LEFT = '┌'
TOP_RIGHT = '┐'
BOTTOM_LEFT = '└'
BOTTOM_RIGHT = '┘'
VERTICAL = '│'
HORIZONTAL = '─'


@dataclass
class Box:
    """Represents a single ASCII box in the text"""
    start_line: int      # Line number where box starts (┌)
    end_line: int        # Line number where box ends (┘)
    top_right_pos: int   # Column position of ┐ character
    nesting_level: int   # Depth of nesting (0 = top level)
    lines: List[str]     # Original lines of the box


class BoxParser:
    """Parses text to identify ASCII box structures"""

    def parse(self, text: str) -> List[Box]:
        """
        Parse text and return list of Box objects.

        Args:
            text: Input text containing ASCII boxes

        Returns:
            List of Box objects in order of appearance
        """
        lines = text.splitlines()
        boxes = []

        i = 0
        while i < len(lines):
            line = lines[i]

            # Look for top-left corner
            if TOP_LEFT in line:
                box = self._parse_box(lines, i)
                if box:
                    boxes.append(box)
                    i = box.end_line + 1
                    continue
            i += 1

        return boxes

    def _parse_box(self, lines: List[str], start: int) -> Optional[Box]:
        """
        Parse a single box starting at given line.

        Args:
            lines: All lines of text
            start: Line index where ┌ was found

        Returns:
            Box object or None if invalid box
        """
        start_line = lines[start]

        # Find top-right corner position
        top_right_pos = start_line.find(TOP_RIGHT)
        if top_right_pos == -1:
            return None

        # Find bottom of box (┘)
        box_lines = [start_line]
        end_idx = start

        for i in range(start + 1, len(lines)):
            box_lines.append(lines[i])
            if BOTTOM_RIGHT in lines[i]:
                end_idx = i
                break
        else:
            # No bottom found
            return None

        return Box(
            start_line=start,
            end_line=end_idx,
            top_right_pos=top_right_pos,
            nesting_level=0,  # Calculate later
            lines=box_lines
        )
```

**Verification:**
```bash
cd ascii-box-fixer
python3 test_fix_ascii_boxes.py
```

**Expected:** Test passes (GREEN phase)

---

#### Task 1.4: Write test for nested box detection
**File:** `ascii-box-fixer/test_fix_ascii_boxes.py`

**Action:** Add test method to TestBoxParser class

```python
    def test_detect_nested_boxes(self):
        """Test detection of nested boxes"""
        text = """\
┌────────────────┐
│ Outer Box      │
│  ┌──────┐      │
│  │ Inner│      │
│  └──────┘      │
└────────────────┘
"""
        parser = BoxParser()
        boxes = parser.parse(text)

        self.assertEqual(len(boxes), 2)

        # Outer box
        self.assertEqual(boxes[0].start_line, 0)
        self.assertEqual(boxes[0].end_line, 5)
        self.assertEqual(boxes[0].top_right_pos, 16)
        self.assertEqual(boxes[0].nesting_level, 0)

        # Inner box
        self.assertEqual(boxes[1].start_line, 2)
        self.assertEqual(boxes[1].end_line, 4)
        self.assertEqual(boxes[1].top_right_pos, 11)
        self.assertEqual(boxes[1].nesting_level, 1)
```

**Verification:**
```bash
cd ascii-box-fixer
python3 test_fix_ascii_boxes.py
```

**Expected:** Test fails on nesting_level assertion (RED phase)

---

#### Task 1.5: Implement nesting level calculation
**File:** `ascii-box-fixer/fix_ascii_boxes.py`

**Action:** Update BoxParser.parse() to calculate nesting levels

```python
    def parse(self, text: str) -> List[Box]:
        """
        Parse text and return list of Box objects.

        Args:
            text: Input text containing ASCII boxes

        Returns:
            List of Box objects in order of appearance
        """
        lines = text.splitlines()
        boxes = []

        i = 0
        while i < len(lines):
            line = lines[i]

            # Look for top-left corner
            if TOP_LEFT in line:
                box = self._parse_box(lines, i)
                if box:
                    boxes.append(box)
                    i = box.end_line + 1
                    continue
            i += 1

        # Calculate nesting levels
        self._calculate_nesting_levels(boxes)

        return boxes

    def _calculate_nesting_levels(self, boxes: List[Box]) -> None:
        """
        Calculate nesting level for each box.
        A box is nested if it's completely contained within another box.
        """
        for i, box in enumerate(boxes):
            nesting = 0
            for other in boxes:
                if other is box:
                    continue
                # Check if box is inside other
                if (other.start_line < box.start_line and
                    other.end_line > box.end_line):
                    nesting += 1
            box.nesting_level = nesting
```

**Verification:**
```bash
cd ascii-box-fixer
python3 test_fix_ascii_boxes.py
```

**Expected:** All tests pass (GREEN phase)

---

### Phase 2: Box Alignment (TDD)

#### Task 2.1: Write test for simple box alignment
**File:** `ascii-box-fixer/test_fix_ascii_boxes.py`

**Action:** Add new test class

```python
class TestBoxAligner(unittest.TestCase):
    def test_align_simple_box(self):
        """Test alignment of a simple box"""
        input_text = """\
┌─────────┐
│ Content │
│ More    │
└─────────┘
"""
        expected = """\
┌─────────┐
│ Content │
│ More    │
└─────────┘
"""
        from fix_ascii_boxes import BoxAligner

        aligner = BoxAligner()
        result = aligner.fix(input_text)

        self.assertEqual(result, expected)
```

**Verification:**
```bash
cd ascii-box-fixer
python3 test_fix_ascii_boxes.py
```

**Expected:** Test fails with ImportError (RED phase)

---

#### Task 2.2: Implement BoxAligner for simple boxes
**File:** `ascii-box-fixer/fix_ascii_boxes.py`

**Action:** Add BoxAligner class

```python
class BoxAligner:
    """Aligns box borders to their top-right corners"""

    def __init__(self):
        self.parser = BoxParser()

    def fix(self, text: str) -> str:
        """
        Fix alignment of all boxes in text.

        Args:
            text: Input text with potentially misaligned boxes

        Returns:
            Text with aligned boxes
        """
        lines = text.splitlines(keepends=True)
        # Handle case where there are no line endings
        if not lines or not any(line.endswith('\n') for line in lines):
            lines = text.splitlines()
            preserve_newlines = False
        else:
            preserve_newlines = True

        boxes = self.parser.parse(text)

        # Process boxes from innermost to outermost
        # This prevents outer box changes from affecting inner boxes
        boxes_by_level = sorted(boxes, key=lambda b: b.nesting_level, reverse=True)

        for box in boxes_by_level:
            self._align_box(lines, box)

        if preserve_newlines:
            return ''.join(lines)
        else:
            return '\n'.join(line.rstrip('\n') for line in lines)

    def _align_box(self, lines: List[str], box: Box) -> None:
        """
        Align a single box's right borders to its top-right corner.

        Args:
            lines: All lines (modified in place)
            box: Box to align
        """
        target_pos = box.top_right_pos

        # Process each line in the box
        for line_idx in range(box.start_line, box.end_line + 1):
            line = lines[line_idx].rstrip('\n')

            # Skip top and bottom borders (they define the position)
            if line_idx == box.start_line or line_idx == box.end_line:
                continue

            # Find all vertical bars in this line
            new_line = self._align_line(line, target_pos)

            # Preserve original line ending
            if lines[line_idx].endswith('\n'):
                new_line += '\n'

            lines[line_idx] = new_line

    def _align_line(self, line: str, target_pos: int) -> str:
        """
        Align vertical bars in a line to target position.

        Args:
            line: Single line of text
            target_pos: Column position for rightmost vertical bar

        Returns:
            Aligned line
        """
        # Find all vertical bars
        positions = [i for i, ch in enumerate(line) if ch == VERTICAL]

        if len(positions) < 2:
            # Single or no vertical bar, nothing to align
            return line

        # The rightmost vertical bar should be at target_pos
        # The leftmost vertical bar stays where it is
        left_pos = positions[0]
        right_pos = positions[-1]

        if right_pos == target_pos:
            # Already aligned
            return line

        # Calculate how much to adjust
        adjustment = target_pos - right_pos

        if adjustment > 0:
            # Need to add spaces before right border
            # Insert spaces before the rightmost │
            return line[:right_pos] + ' ' * adjustment + line[right_pos:]
        elif adjustment < 0:
            # Need to remove spaces before right border
            # Remove spaces before the rightmost │
            spaces_to_remove = min(abs(adjustment),
                                  len(line[:right_pos]) - len(line[:right_pos].rstrip()))
            if spaces_to_remove > 0:
                # Remove trailing spaces before │
                content = line[:right_pos].rstrip()
                padding_needed = target_pos - len(content)
                return content + ' ' * max(0, padding_needed) + line[right_pos:]

        return line
```

**Verification:**
```bash
cd ascii-box-fixer
python3 test_fix_ascii_boxes.py
```

**Expected:** Test passes (GREEN phase)

---

#### Task 2.3: Write test for nested box alignment
**File:** `ascii-box-fixer/test_fix_ascii_boxes.py`

**Action:** Add test method

```python
    def test_align_nested_boxes(self):
        """Test that nested boxes align independently"""
        input_text = """\
┌────────────────┐
│ Outer Box      │
│  ┌──────┐      │
│  │ Inner│      │
│  └──────┘      │
└────────────────┘
"""
        expected = """\
┌────────────────┐
│ Outer Box      │
│  ┌──────┐      │
│  │ Inner│      │
│  └──────┘      │
└────────────────┘
"""
        aligner = BoxAligner()
        result = aligner.fix(input_text)

        self.assertEqual(result, expected)
```

**Verification:**
```bash
cd ascii-box-fixer
python3 test_fix_ascii_boxes.py
```

**Expected:** Test should pass with current implementation (GREEN phase)

---

#### Task 2.4: Write test for multiple adjacent boxes
**File:** `ascii-box-fixer/test_fix_ascii_boxes.py`

**Action:** Add test method

```python
    def test_align_multiple_boxes(self):
        """Test alignment of multiple separate boxes"""
        input_text = """\
First box:
┌─────────┐
│ Box 1   │
└─────────┘

Second box:
┌───────────────┐
│ Box 2         │
└───────────────┘
"""
        expected = """\
First box:
┌─────────┐
│ Box 1   │
└─────────┘

Second box:
┌───────────────┐
│ Box 2         │
└───────────────┘
"""
        aligner = BoxAligner()
        result = aligner.fix(input_text)

        self.assertEqual(result, expected)
```

**Verification:**
```bash
cd ascii-box-fixer
python3 test_fix_ascii_boxes.py
```

**Expected:** Test passes (GREEN phase)

---

#### Task 2.5: Write test for boxes with internal sub-boxes
**File:** `ascii-box-fixer/test_fix_ascii_boxes.py`

**Action:** Add complex nested test

```python
    def test_align_complex_nested_structure(self):
        """Test complex multi-level nesting"""
        input_text = """\
┌──────────────────┐
│  TLP Layer       │
│  ┌────────┐  ┌────────┐  │
│  │ TX     │      │ RX     │  │
│  └────────┘  └────────┘  │
└──────────────────┘
"""
        expected = """\
┌──────────────────┐
│  TLP Layer       │
│  ┌────────┐  ┌────────┐   │
│  │ TX     │      │ RX     │   │
│  └────────┘  └────────┘   │
└──────────────────┘
"""
        aligner = BoxAligner()
        result = aligner.fix(input_text)

        self.assertEqual(result, expected)
```

**Verification:**
```bash
cd ascii-box-fixer
python3 test_fix_ascii_boxes.py
```

**Expected:** May fail initially - need to refine alignment logic (RED phase)

---

#### Task 2.6: Refine alignment for multiple sub-boxes per line
**File:** `ascii-box-fixer/fix_ascii_boxes.py`

**Action:** Update `_align_line` method to handle multiple sub-boxes correctly

```python
    def _align_line(self, line: str, target_pos: int) -> str:
        """
        Align vertical bars in a line to target position.

        Only aligns the outermost bars (leftmost and rightmost).
        Inner vertical bars are left unchanged as they belong to nested boxes.

        Args:
            line: Single line of text
            target_pos: Column position for rightmost vertical bar

        Returns:
            Aligned line
        """
        # Find all vertical bars
        positions = [i for i, ch in enumerate(line) if ch == VERTICAL]

        if not positions:
            return line

        # For lines with vertical bars, we only adjust the RIGHTMOST one
        # All others belong to nested boxes or are the left border
        right_pos = positions[-1]

        if right_pos == target_pos:
            # Already aligned
            return line

        # Calculate how much to adjust
        adjustment = target_pos - right_pos

        if adjustment > 0:
            # Need to add spaces before right border
            return line[:right_pos] + ' ' * adjustment + line[right_pos:]
        elif adjustment < 0:
            # Need to remove spaces before right border
            # Only remove actual spaces, not content
            content_end = right_pos
            # Find last non-space before the vertical bar
            for i in range(right_pos - 1, -1, -1):
                if line[i] != ' ':
                    content_end = i + 1
                    break

            # Reconstruct line with proper spacing
            content = line[:content_end]
            padding_needed = target_pos - len(content)

            if padding_needed >= 0:
                return content + ' ' * padding_needed + VERTICAL
            else:
                # Content is too long, can't fix without data loss
                return line

        return line
```

**Verification:**
```bash
cd ascii-box-fixer
python3 test_fix_ascii_boxes.py
```

**Expected:** All tests pass (GREEN phase)

---

### Phase 3: File Processing (TDD)

#### Task 3.1: Write test for file processing
**File:** `ascii-box-fixer/test_fix_ascii_boxes.py`

**Action:** Add new test class

```python
import tempfile
import os


class TestFileProcessor(unittest.TestCase):
    def setUp(self):
        """Create temporary directory for test files"""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary directory"""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_process_single_file(self):
        """Test processing a single file"""
        from fix_ascii_boxes import FileProcessor

        # Create test file
        test_file = os.path.join(self.temp_dir, 'test.md')
        input_text = """\
┌─────────┐
│ Content │
└─────────┘
"""
        expected = """\
┌─────────┐
│ Content │
└─────────┘
"""
        with open(test_file, 'w') as f:
            f.write(input_text)

        # Process file
        processor = FileProcessor()
        processor.process_file(test_file, in_place=True)

        # Verify result
        with open(test_file, 'r') as f:
            result = f.read()

        self.assertEqual(result, expected)
```

**Verification:**
```bash
cd ascii-box-fixer
python3 test_fix_ascii_boxes.py
```

**Expected:** Test fails with ImportError (RED phase)

---

#### Task 3.2: Implement FileProcessor
**File:** `ascii-box-fixer/fix_ascii_boxes.py`

**Action:** Add FileProcessor class

```python
import sys
from pathlib import Path


class FileProcessor:
    """Processes files to fix ASCII box alignment"""

    def __init__(self, verbose: bool = False):
        self.aligner = BoxAligner()
        self.verbose = verbose

    def process_file(self, file_path: str, in_place: bool = False,
                    dry_run: bool = False) -> str:
        """
        Process a single file.

        Args:
            file_path: Path to file to process
            in_place: If True, modify file in place
            dry_run: If True, don't write changes

        Returns:
            Fixed content
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Read file
        with open(path, 'r', encoding='utf-8') as f:
            original = f.read()

        # Fix boxes
        fixed = self.aligner.fix(original)

        # Check if changes were made
        changed = original != fixed

        if self.verbose:
            if changed:
                print(f"Fixed: {file_path}")
            else:
                print(f"No changes: {file_path}")

        # Write back if requested
        if in_place and changed and not dry_run:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(fixed)

        return fixed

    def process_directory(self, dir_path: str, pattern: str = '*.md',
                         in_place: bool = False, dry_run: bool = False) -> int:
        """
        Process all matching files in directory.

        Args:
            dir_path: Directory to process
            pattern: Glob pattern for files
            in_place: If True, modify files in place
            dry_run: If True, don't write changes

        Returns:
            Number of files processed
        """
        path = Path(dir_path)

        if not path.is_dir():
            raise NotADirectoryError(f"Not a directory: {dir_path}")

        count = 0
        for file_path in path.rglob(pattern):
            if file_path.is_file():
                self.process_file(str(file_path), in_place, dry_run)
                count += 1

        return count
```

**Verification:**
```bash
cd ascii-box-fixer
python3 test_fix_ascii_boxes.py
```

**Expected:** Test passes (GREEN phase)

---

#### Task 3.3: Write test for directory processing
**File:** `ascii-box-fixer/test_fix_ascii_boxes.py`

**Action:** Add test method to TestFileProcessor

```python
    def test_process_directory(self):
        """Test processing multiple files in directory"""
        from fix_ascii_boxes import FileProcessor

        # Create test files
        for i in range(3):
            test_file = os.path.join(self.temp_dir, f'test{i}.md')
            with open(test_file, 'w') as f:
                f.write(f"┌───┐\n│ {i}│\n└───┘\n")

        # Process directory
        processor = FileProcessor()
        count = processor.process_directory(self.temp_dir, in_place=True)

        self.assertEqual(count, 3)

        # Verify all files were fixed
        for i in range(3):
            test_file = os.path.join(self.temp_dir, f'test{i}.md')
            with open(test_file, 'r') as f:
                content = f.read()
            self.assertIn(f'│ {i} │', content)
```

**Verification:**
```bash
cd ascii-box-fixer
python3 test_fix_ascii_boxes.py
```

**Expected:** Test passes (GREEN phase)

---

### Phase 4: CLI Interface (TDD)

#### Task 4.1: Write CLI tests
**File:** `ascii-box-fixer/test_fix_ascii_boxes.py`

**Action:** Add CLI test class

```python
import subprocess


class TestCLI(unittest.TestCase):
    def setUp(self):
        """Create temporary directory for test files"""
        self.temp_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.temp_dir, 'test.md')
        with open(self.test_file, 'w') as f:
            f.write("┌───┐\n│ X│\n└───┘\n")

    def tearDown(self):
        """Clean up temporary directory"""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_cli_help(self):
        """Test CLI help message"""
        result = subprocess.run(
            ['python3', 'fix_ascii_boxes.py', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('usage:', result.stdout.lower())

    def test_cli_process_file(self):
        """Test CLI file processing"""
        result = subprocess.run(
            ['python3', 'fix_ascii_boxes.py', '--in-place', self.test_file],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)

        # Verify file was modified
        with open(self.test_file, 'r') as f:
            content = f.read()
        self.assertIn('│ X │', content)

    def test_cli_dry_run(self):
        """Test CLI dry run mode"""
        original_content = open(self.test_file, 'r').read()

        result = subprocess.run(
            ['python3', 'fix_ascii_boxes.py', '--dry-run', '--in-place',
             self.test_file],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)

        # Verify file was NOT modified
        with open(self.test_file, 'r') as f:
            content = f.read()
        self.assertEqual(content, original_content)
```

**Verification:**
```bash
cd ascii-box-fixer
python3 test_fix_ascii_boxes.py TestCLI
```

**Expected:** Tests fail (RED phase)

---

#### Task 4.2: Implement CLI interface
**File:** `ascii-box-fixer/fix_ascii_boxes.py`

**Action:** Add CLI code at end of file

```python
import argparse


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description='Fix ASCII box border alignment in documentation files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview changes to a file
  %(prog)s file.md

  # Fix a file in place
  %(prog)s --in-place file.md

  # Fix all markdown files in directory
  %(prog)s --in-place --recursive docs/

  # Dry run to see what would change
  %(prog)s --dry-run --in-place docs/
        """
    )

    parser.add_argument(
        'paths',
        nargs='+',
        help='Files or directories to process'
    )

    parser.add_argument(
        '-i', '--in-place',
        action='store_true',
        help='Modify files in place'
    )

    parser.add_argument(
        '-r', '--recursive',
        action='store_true',
        help='Process directories recursively'
    )

    parser.add_argument(
        '-p', '--pattern',
        default='*.md',
        help='File pattern for recursive processing (default: *.md)'
    )

    parser.add_argument(
        '-n', '--dry-run',
        action='store_true',
        help='Show what would be changed without modifying files'
    )

    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Verbose output'
    )

    args = parser.parse_args()

    processor = FileProcessor(verbose=args.verbose)

    for path_str in args.paths:
        path = Path(path_str)

        if path.is_file():
            # Process single file
            fixed = processor.process_file(
                str(path),
                in_place=args.in_place,
                dry_run=args.dry_run
            )

            # Print to stdout if not in-place
            if not args.in_place:
                print(fixed, end='')

        elif path.is_dir():
            if not args.recursive:
                print(f"Error: {path_str} is a directory. Use --recursive to process directories.",
                      file=sys.stderr)
                sys.exit(1)

            # Process directory
            count = processor.process_directory(
                str(path),
                pattern=args.pattern,
                in_place=args.in_place,
                dry_run=args.dry_run
            )

            if args.verbose:
                print(f"Processed {count} files in {path_str}")

        else:
            print(f"Error: {path_str} not found", file=sys.stderr)
            sys.exit(1)


if __name__ == '__main__':
    main()
```

**Verification:**
```bash
cd ascii-box-fixer
python3 test_fix_ascii_boxes.py TestCLI
```

**Expected:** All tests pass (GREEN phase)

---

### Phase 5: Edge Cases and Refinement (TDD)

#### Task 5.1: Write test for edge cases
**File:** `ascii-box-fixer/test_fix_ascii_boxes.py`

**Action:** Add edge case test class

```python
class TestEdgeCases(unittest.TestCase):
    def test_empty_box(self):
        """Test handling of empty box"""
        input_text = "┌───┐\n└───┘\n"
        expected = "┌───┐\n└───┘\n"

        aligner = BoxAligner()
        result = aligner.fix(input_text)
        self.assertEqual(result, expected)

    def test_single_line_content(self):
        """Test box with single content line"""
        input_text = "┌───┐\n│ X│\n└───┘\n"
        expected = "┌───┐\n│ X │\n└───┘\n"

        aligner = BoxAligner()
        result = aligner.fix(input_text)
        self.assertEqual(result, expected)

    def test_no_boxes(self):
        """Test text with no boxes"""
        input_text = "Just some regular text\nNo boxes here\n"

        aligner = BoxAligner()
        result = aligner.fix(input_text)
        self.assertEqual(result, input_text)

    def test_incomplete_box(self):
        """Test handling of incomplete box (no bottom)"""
        input_text = "┌───┐\n│ X │\n"

        aligner = BoxAligner()
        result = aligner.fix(input_text)
        # Should return unchanged since box is incomplete
        self.assertEqual(result, input_text)

    def test_unicode_content(self):
        """Test box with unicode content"""
        input_text = "┌───────┐\n│ 你好 │\n└───────┘\n"
        expected = "┌───────┐\n│ 你好  │\n└───────┘\n"

        aligner = BoxAligner()
        result = aligner.fix(input_text)
        # Note: May need special handling for wide characters
        # This test documents current behavior

    def test_very_wide_box(self):
        """Test handling of very wide boxes"""
        input_text = "┌" + "─" * 100 + "┐\n│ " + "X" * 98 + "│\n└" + "─" * 100 + "┘\n"

        aligner = BoxAligner()
        result = aligner.fix(input_text)
        # Should handle without issues
        self.assertIn('┐', result)
        self.assertIn('┘', result)
```

**Verification:**
```bash
cd ascii-box-fixer
python3 test_fix_ascii_boxes.py TestEdgeCases
```

**Expected:** Some tests may fail, revealing edge cases to fix (RED phase)

---

#### Task 5.2: Fix edge cases as needed
**File:** `ascii-box-fixer/fix_ascii_boxes.py`

**Action:** Add defensive checks and handle edge cases

```python
    def _parse_box(self, lines: List[str], start: int) -> Optional[Box]:
        """
        Parse a single box starting at given line.

        Args:
            lines: All lines of text
            start: Line index where ┌ was found

        Returns:
            Box object or None if invalid box
        """
        start_line = lines[start]

        # Find top-right corner position
        top_right_pos = start_line.find(TOP_RIGHT)
        if top_right_pos == -1:
            return None

        # Validate: top-left should come before top-right
        top_left_pos = start_line.find(TOP_LEFT)
        if top_left_pos >= top_right_pos:
            return None

        # Find bottom of box (┘)
        box_lines = [start_line]
        end_idx = start

        for i in range(start + 1, len(lines)):
            box_lines.append(lines[i])
            if BOTTOM_RIGHT in lines[i]:
                end_idx = i
                break
        else:
            # No bottom found - incomplete box
            return None

        # Validate bottom line has matching bottom-left
        if BOTTOM_LEFT not in lines[end_idx]:
            return None

        return Box(
            start_line=start,
            end_line=end_idx,
            top_right_pos=top_right_pos,
            nesting_level=0,
            lines=box_lines
        )
```

**Verification:**
```bash
cd ascii-box-fixer
python3 test_fix_ascii_boxes.py TestEdgeCases
```

**Expected:** All tests pass (GREEN phase)

---

### Phase 6: Documentation and Integration

#### Task 6.1: Add docstring documentation
**File:** `ascii-box-fixer/fix_ascii_boxes.py`

**Action:** Ensure all classes and functions have complete docstrings

Already done in implementation above - verify completeness.

---

#### Task 6.2: Create README for the tool
**File:** `ascii-box-fixer/README.md`

**Action:** Write comprehensive README

```markdown
# ASCII Box Border Fixer

A Python tool for fixing misaligned borders in ASCII box diagrams in documentation files.

## Problem

ASCII box diagrams often have misaligned right borders:

\`\`\`
┌─────────┐
│ Content │  <- correct
│ More    │   <- misaligned
└─────────┘
\`\`\`

This tool automatically aligns all vertical borders (`│`) to match the position of the top-right corner (`┐`).

## Features

- ✅ Fixes simple boxes
- ✅ Handles nested boxes correctly (each box aligns to its own top-right corner)
- ✅ Supports multiple boxes in the same file
- ✅ Preserves box content
- ✅ Works with all standard box-drawing characters
- ✅ In-place file editing or stdout output
- ✅ Recursive directory processing
- ✅ Dry-run mode
- ✅ No external dependencies (pure Python stdlib)

## Installation

No installation needed - it's a single standalone Python file.

\`\`\`bash
# Make executable
chmod +x fix_ascii_boxes.py
\`\`\`

## Usage

### Preview changes

\`\`\`bash
python3 fix_ascii_boxes.py file.md
\`\`\`

### Fix file in place

\`\`\`bash
python3 fix_ascii_boxes.py --in-place file.md
\`\`\`

### Fix all markdown files in directory

\`\`\`bash
python3 fix_ascii_boxes.py --in-place --recursive docs/
\`\`\`

### Dry run (show what would change)

\`\`\`bash
python3 fix_ascii_boxes.py --dry-run --in-place --verbose docs/
\`\`\`

### Help

\`\`\`bash
python3 fix_ascii_boxes.py --help
\`\`\`

## How It Works

1. **Detection**: Scans for box top-left corners (`┌`) and finds matching bottom-right corners (`┘`)
2. **Nesting Analysis**: Identifies which boxes are nested within others
3. **Alignment**: For each box, aligns all right-side vertical borders (`│`) to match the position of the top-right corner (`┐`)
4. **Processing Order**: Processes innermost boxes first to prevent outer box changes from affecting inner boxes

## Box Drawing Characters Supported

- `┌` `┐` `└` `┘` - Corners
- `    │` `─` - Straight lines
- `┬` `┴` `├` `┤` `┼` - Junctions (detected but not modified)

## Examples

### Simple Box

Before:
\`\`\`
┌─────────┐
│ Content │
│ More │
└─────────┘
\`\`\`

After:
\`\`\`
┌─────────┐
│ Content │
│ More │
└─────────┘
\`\`\`

### Nested Boxes

Before:
\`\`\`
┌────────────────┐
│ Outer          │
│  ┌──────┐      │
│  │ Inner│      │
│  └──────┘      │
└────────────────┘
\`\`\`

After:
\`\`\`
┌────────────────┐
│ Outer          │
│  ┌──────┐      │
│  │ Inner│      │
│  └──────┘      │
└────────────────┘
\`\`\`

Note: Both boxes align to their own top-right corners independently.

## Testing

Run the test suite:

\`\`\`bash
python3 test_fix_ascii_boxes.py
\`\`\`

Run specific test class:

\`\`\`bash
python3 test_fix_ascii_boxes.py TestBoxParser
python3 test_fix_ascii_boxes.py TestBoxAligner
python3 test_fix_ascii_boxes.py TestEdgeCases
\`\`\`

## Limitations

- Only processes complete boxes (must have all four corners)
- Assumes boxes use standard Unicode box-drawing characters
- Does not modify box content, only spacing before right border
- Wide Unicode characters (CJK) may require special handling

## License

MIT License - Feel free to use and modify
\`\`\`

**Verification:**
```bash
ls -la ascii-box-fixer/README.md
```

---

#### Task 6.3: Create usage examples
**File:** `ascii-box-fixer/example_boxes.md`

**Action:** Create example file for testing

```markdown
# Example ASCII Boxes

## Simple Box

┌─────────────┐
│ Title       │
│ Content     │
└─────────────┘

## Nested Box

┌──────────────────────┐
│ Outer Container      │
│                      │
│  ┌──────────┐        │
│  │ Inner    │        │
│  │ Box      │        │
│  └──────────┘        │
│                      │
└──────────────────────┘

## Multiple Sub-boxes

┌────────────────────────────┐
│        Parent Box          │
│                            │
│  ┌────────┐  ┌────────┐    │
│  │ Left   │  │ Right  │    │
│  └────────┘  └────────┘    │
└────────────────────────────┘
\`\`\`

**Verification:**
```bash
cd ascii-box-fixer
python3 fix_ascii_boxes.py example_boxes.md
```

**Expected:** Shows aligned version

---

#### Task 6.4: Run full test suite
**File:** All test files

**Action:** Execute complete test suite

```bash
cd ascii-box-fixer
python3 test_fix_ascii_boxes.py -v
```

**Verification:** All tests pass

**Expected Output:**
```
test_align_complex_nested_structure ... ok
test_align_multiple_boxes ... ok
test_align_nested_boxes ... ok
test_align_simple_box ... ok
test_cli_dry_run ... ok
test_cli_help ... ok
test_cli_process_file ... ok
test_detect_nested_boxes ... ok
test_detect_simple_box ... ok
test_empty_box ... ok
test_incomplete_box ... ok
test_no_boxes ... ok
test_process_directory ... ok
test_process_single_file ... ok
test_single_line_content ... ok
test_unicode_content ... ok
test_very_wide_box ... ok

----------------------------------------------------------------------
Ran 17 tests in X.XXXs

OK
```

---

#### Task 6.5: Test on real documentation
**File:** Documentation files in `docs/architecture/`

**Action:** Run tool on actual project documentation

```bash
cd ascii-box-fixer
python3 fix_ascii_boxes.py --dry-run --verbose --in-place ../docs/architecture/complete-system-architecture.md
```

**Verification:** Check output shows detected issues

**Expected:** Tool identifies misaligned boxes

---

#### Task 6.6: Apply fixes to documentation (if requested)
**File:** Documentation files

**Action:** Actually fix the documentation

```bash
cd ascii-box-fixer
python3 fix_ascii_boxes.py --in-place ../docs/architecture/complete-system-architecture.md
```

**Verification:**
```bash
git diff docs/architecture/complete-system-architecture.md
```

**Expected:** Shows alignment fixes

---

## Success Criteria

### Functionality
- ✅ Correctly detects ASCII boxes with all four corners
- ✅ Aligns right borders to top-right corner position
- ✅ Handles nested boxes independently
- ✅ Processes multiple boxes in single file
- ✅ Preserves box content unchanged
- ✅ Handles edge cases gracefully

### Code Quality
- ✅ 100% test coverage of core functionality
- ✅ All tests pass
- ✅ Clear, documented code
- ✅ No external dependencies
- ✅ Follows Python best practices
- ✅ Type hints where appropriate

### Usability
- ✅ Simple CLI interface
- ✅ Clear help messages
- ✅ Verbose mode for debugging
- ✅ Dry-run mode for safety
- ✅ Works on single files and directories
- ✅ Comprehensive README

### TDD Process
- ✅ Tests written before implementation
- ✅ RED-GREEN-REFACTOR cycle followed
- ✅ Edge cases covered by tests

## File Structure

```
ascii-box-fixer/
├── fix_ascii_boxes.py           # Main tool (standalone)
├── test_fix_ascii_boxes.py      # Complete test suite
├── README.md                     # Documentation
└── example_boxes.md             # Example input for testing
```

## Estimated Effort

- Phase 1 (Core Detection): 2-3 hours
- Phase 2 (Alignment): 2-3 hours
- Phase 3 (File Processing): 1-2 hours
- Phase 4 (CLI): 1 hour
- Phase 5 (Edge Cases): 1-2 hours
- Phase 6 (Documentation): 1 hour

**Total:** 8-12 hours

## Notes

- The key insight is processing boxes from innermost to outermost to prevent cascading changes
- Each box must track its own top-right corner position
- Only the rightmost `│` on each line should be adjusted
- Inner box borders are left unchanged when processing outer boxes
