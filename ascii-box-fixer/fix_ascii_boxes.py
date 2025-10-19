"""ASCII Box Border Fixer

Fixes misaligned right borders in ASCII box diagrams by aligning
all vertical borders (│) to the position of the top-right corner (┐).

This tool detects ASCII box diagrams in text files and ensures all
vertical borders align correctly with their top-right corners, including
proper handling of nested box structures.
"""

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


# Box drawing characters
TOP_LEFT = '┌'
TOP_RIGHT = '┐'
BOTTOM_LEFT = '└'
BOTTOM_RIGHT = '┘'
VERTICAL = '│'
HORIZONTAL = '─'

# File size limit (10MB)
MAX_FILE_SIZE = 10 * 1024 * 1024


@dataclass
class Box:
    """Represents a single ASCII box in the text.

    Attributes:
        start_line: Line number where box starts (┌)
        end_line: Line number where box ends (┘)
        left_pos: Column position of ┌ character
        top_right_pos: Column position of ┐ character
        nesting_level: Depth of nesting (0 = top level)
        lines: Original lines of the box
    """
    start_line: int
    end_line: int
    left_pos: int
    top_right_pos: int
    nesting_level: int
    lines: List[str]


class BoxParser:
    """Parses text to identify ASCII box structures.

    This class scans text to find complete ASCII boxes, including nested
    boxes. A complete box must have all four corners (┌ ┐ └ ┘) and at
    least one vertical bar on lines between top and bottom.
    """

    def parse(self, text: str) -> List[Box]:
        """Parse text and return list of Box objects.

        Args:
            text: Input text containing ASCII boxes

        Returns:
            List of Box objects in order of appearance
        """
        # Expand tabs to spaces for consistent positioning
        text = text.expandtabs()
        lines = text.splitlines()
        boxes = []

        i = 0
        while i < len(lines):
            line = lines[i]

            # Find all TOP_LEFT positions in this line efficiently
            match_pos = 0
            while match_pos < len(line):
                match_pos = line.find(TOP_LEFT, match_pos)
                if match_pos == -1:
                    break
                box = self._parse_box(lines, i, match_pos)
                if box:
                    boxes.append(box)
                match_pos += 1
            i += 1

        # Calculate nesting levels
        self._calculate_nesting_levels(boxes)

        return boxes

    def _parse_box(self, lines: List[str], start: int, left_pos: int) -> Optional[Box]:
        """Parse a single box starting at given line and position.

        Args:
            lines: All lines of text
            start: Line index where ┌ was found
            left_pos: Column position where ┌ was found

        Returns:
            Box object or None if invalid box
        """
        start_line = lines[start]

        # Find top-right corner position (must be after left_pos)
        top_right_pos = start_line.find(TOP_RIGHT, left_pos)
        if top_right_pos == -1:
            return None

        # Find bottom of box (┘) - must align horizontally with top-right
        box_lines = [start_line]
        end_idx = start

        for i in range(start + 1, len(lines)):
            box_lines.append(lines[i])
            # Check if this line has a bottom-left at the expected position
            if (left_pos < len(lines[i]) and
                lines[i][left_pos] == BOTTOM_LEFT and
                BOTTOM_RIGHT in lines[i][left_pos:]):
                # Verify the bottom-right is approximately at the right position
                bottom_right_pos = lines[i].find(BOTTOM_RIGHT, left_pos)
                if bottom_right_pos != -1:
                    end_idx = i
                    break
        else:
            # No matching bottom found
            return None

        # Validate: Check that at least some lines between top and bottom have vertical bars
        # This ensures we're not matching on non-box patterns
        has_vertical = False
        for i in range(start + 1, end_idx):
            if left_pos < len(lines[i]) and lines[i][left_pos] == VERTICAL:
                has_vertical = True
                break

        # For single-line boxes (start+1 == end_idx), skip this check
        if end_idx > start + 1 and not has_vertical:
            return None

        return Box(
            start_line=start,
            end_line=end_idx,
            left_pos=left_pos,
            top_right_pos=top_right_pos,
            nesting_level=0,  # Calculate later
            lines=box_lines
        )

    def _calculate_nesting_levels(self, boxes: List[Box]) -> None:
        """Calculate nesting level for each box.

        A box is nested if it's completely contained within another box.
        The nesting level is the count of boxes that contain it.

        Algorithm: For each box, count how many other boxes completely
        contain it (start before it and end after it).

        Args:
            boxes: List of Box objects to calculate nesting for

        Note:
            Modifies boxes in-place by setting their nesting_level attribute.
        """
        for box in boxes:
            nesting = 0
            for other in boxes:
                if other is box:
                    continue
                # Check if box is inside other
                if (other.start_line < box.start_line and
                    other.end_line > box.end_line):
                    nesting += 1
            box.nesting_level = nesting


class BoxAligner:
    """Aligns box borders to their top-right corners.

    This class takes text containing ASCII boxes and aligns all vertical
    borders to match the position of their corresponding top-right corners.
    Nested boxes are processed independently.
    """

    def __init__(self):
        self.parser = BoxParser()

    def fix(self, text: str) -> str:
        """Fix alignment of all boxes in text.

        Args:
            text: Input text with potentially misaligned boxes

        Returns:
            Text with aligned boxes
        """
        # Expand tabs to spaces for consistent positioning
        text = text.expandtabs()

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
        """Align a single box's right borders to its top-right corner.

        Args:
            lines: All lines (modified in place)
            box: Box to align
        """
        target_pos = box.top_right_pos
        left_pos = box.left_pos

        # Process each line in the box
        for line_idx in range(box.start_line, box.end_line + 1):
            line = lines[line_idx].rstrip('\n')

            # Skip top and bottom borders (they define the position)
            if line_idx == box.start_line or line_idx == box.end_line:
                continue

            # Align this line
            new_line = self._align_line(line, left_pos, target_pos)

            # Preserve original line ending
            if lines[line_idx].endswith('\n'):
                new_line += '\n'

            lines[line_idx] = new_line

    def _align_line(self, line: str, left_pos: int, target_pos: int) -> str:
        """Align the vertical bar belonging to this box to target position.

        Args:
            line: Single line of text
            left_pos: Column position of box's left border
            target_pos: Column position for box's right border

        Returns:
            Aligned line
        """
        # Find all vertical bars
        positions = [i for i, ch in enumerate(line) if ch == VERTICAL]

        if not positions:
            return line

        # Find the vertical bar that belongs to THIS box
        # It should be at or near target_pos, within the box's horizontal range
        # For nested boxes, we want the bar closest to target_pos that's between
        # left_pos and target_pos (prioritize bars at/before target over bars after)

        # Split candidates into two groups: at/before target vs after target
        candidates_at_or_before = [pos for pos in positions
                                    if pos > left_pos and pos <= target_pos]
        candidates_after = [pos for pos in positions
                           if pos > target_pos and pos <= target_pos + 3]

        right_pos = None

        if candidates_at_or_before:
            # Prefer bars at or before target (belong to this box)
            right_pos = min(candidates_at_or_before,
                           key=lambda p: abs(p - target_pos))
        elif candidates_after:
            # Only use bars after target if no valid bars before
            # (this handles slightly malformed boxes)
            right_pos = min(candidates_after,
                           key=lambda p: abs(p - target_pos))
        else:
            # If no suitable bar found (shouldn't happen), fall back to rightmost
            right_pos = positions[-1]

        if right_pos == target_pos:
            # Already aligned
            return line

        # Calculate how much to adjust
        adjustment = target_pos - right_pos

        if adjustment > 0:
            # Need to add spaces before right border
            # Important: Only shift this bar, not everything after it
            return line[:right_pos] + ' ' * adjustment + VERTICAL + line[right_pos+1:]
        elif adjustment < 0:
            # Need to remove spaces before right border
            content_end = right_pos
            # Search backwards from right_pos to find last non-space, non-vertical-bar character
            for i in range(right_pos - 1, -1, -1):
                if line[i] == VERTICAL:
                    # Stop at the previous vertical bar (likely left border or another box)
                    content_end = i + 1
                    break
                elif line[i] != ' ':
                    content_end = i + 1
                    break

            content = line[:content_end]
            padding_needed = target_pos - len(content)

            if padding_needed >= 0:
                # Preserve everything after the bar we're adjusting
                return content + ' ' * padding_needed + VERTICAL + line[right_pos+1:]
            else:
                # Content is too long, can't fix without data loss
                return line

        return line


class FileProcessor:
    """Processes files to fix ASCII box alignment.

    Handles reading files, applying box alignment fixes, and writing
    results back to disk or stdout. Supports both single file and
    recursive directory processing.
    """

    def __init__(self, verbose: bool = False):
        self.aligner = BoxAligner()
        self.verbose = verbose

        # Set up logging
        log_level = logging.INFO if verbose else logging.WARNING
        logging.basicConfig(
            level=log_level,
            format='%(levelname)s: %(message)s'
        )
        self.logger = logging.getLogger(__name__)

    def process_file(self, file_path: str, in_place: bool = False,
                    dry_run: bool = False) -> str:
        """Process a single file.

        Args:
            file_path: Path to the file to process
            in_place: Whether to modify the file in place
            dry_run: If True, don't actually write changes

        Returns:
            The fixed content

        Raises:
            FileNotFoundError: If file doesn't exist
            PermissionError: If file cannot be read/written
            UnicodeDecodeError: If file is not valid UTF-8
            ValueError: If file is too large or not a regular file
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not path.is_file():
            raise ValueError(f"Not a regular file: {file_path}")

        # Check file size
        file_size = path.stat().st_size
        if file_size > MAX_FILE_SIZE:
            raise ValueError(
                f"File too large: {file_size} bytes (max {MAX_FILE_SIZE})"
            )

        # Check if file is writable before attempting to modify
        if in_place and not dry_run and not os.access(path, os.W_OK):
            raise PermissionError(f"File not writable: {file_path}")

        try:
            with open(path, 'r', encoding='utf-8') as f:
                original = f.read()
        except UnicodeDecodeError as exc:
            raise UnicodeDecodeError(
                exc.encoding, exc.object, exc.start, exc.end,
                f"Cannot decode {file_path} as UTF-8"
            ) from exc

        fixed = self.aligner.fix(original)
        changed = original != fixed

        if changed:
            self.logger.info(f"Fixed: {file_path}")
        else:
            self.logger.debug(f"No changes: {file_path}")

        if in_place and changed and not dry_run:
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(fixed)
            except PermissionError as exc:
                raise PermissionError(f"Cannot write to {file_path}") from exc

        return fixed

    def process_directory(self, dir_path: str, pattern: str = '*.md',
                         in_place: bool = False, dry_run: bool = False) -> int:
        """Process all matching files in directory.

        Args:
            dir_path: Directory to process
            pattern: Glob pattern for files (default: *.md)
            in_place: Whether to modify files in place
            dry_run: If True, don't actually write changes

        Returns:
            Number of files successfully processed

        Raises:
            NotADirectoryError: If dir_path is not a directory
        """
        path = Path(dir_path)

        if not path.is_dir():
            raise NotADirectoryError(f"Not a directory: {dir_path}")

        count = 0
        for file_path in path.rglob(pattern):
            if file_path.is_file():
                try:
                    self.process_file(str(file_path), in_place, dry_run)
                    count += 1
                except Exception as exc:
                    self.logger.error(f"Error processing {file_path}: {exc}")

        return count


def main() -> int:
    """Main CLI entry point.

    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    parser = argparse.ArgumentParser(
        description='Fix ASCII box border alignment in documentation files',
        epilog='Example: %(prog)s --in-place file.md',
        formatter_class=argparse.RawDescriptionHelpFormatter
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
    exit_code = 0

    for path_str in args.paths:
        path = Path(path_str)

        try:
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
                    print(
                        f"Error: {path_str} is a directory. Use --recursive to process directories.",
                        file=sys.stderr
                    )
                    exit_code = 1
                    continue

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
                exit_code = 1

        except FileNotFoundError as exc:
            print(f"Error: File not found: {path_str}", file=sys.stderr)
            exit_code = 1
        except PermissionError as exc:
            print(f"Error: Permission denied: {path_str}", file=sys.stderr)
            exit_code = 1
        except UnicodeDecodeError as exc:
            print(f"Error: Cannot decode file {path_str}: {exc.reason}", file=sys.stderr)
            exit_code = 1
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            exit_code = 1
        except Exception as exc:
            print(f"Error processing {path_str}: {exc}", file=sys.stderr)
            exit_code = 1

    return exit_code


if __name__ == '__main__':
    sys.exit(main())
