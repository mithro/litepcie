import unittest
import tempfile
import os
import subprocess
import shutil
from fix_ascii_boxes import BoxParser, Box, BoxAligner, FileProcessor


class TestBoxParser(unittest.TestCase):
    """Test box detection functionality"""

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
        self.assertEqual(boxes[0].left_pos, 0)
        self.assertEqual(boxes[0].top_right_pos, 10)
        self.assertEqual(boxes[0].nesting_level, 0)

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
        self.assertEqual(boxes[0].left_pos, 0)
        self.assertEqual(boxes[0].top_right_pos, 17)
        self.assertEqual(boxes[0].nesting_level, 0)

        # Inner box
        self.assertEqual(boxes[1].start_line, 2)
        self.assertEqual(boxes[1].end_line, 4)
        self.assertEqual(boxes[1].left_pos, 3)
        self.assertEqual(boxes[1].top_right_pos, 10)
        self.assertEqual(boxes[1].nesting_level, 1)


class TestBoxParserEdgeCases(unittest.TestCase):
    """Additional edge case tests for BoxParser"""

    def test_incomplete_box_no_bottom(self):
        """Test that incomplete boxes (no bottom) are ignored"""
        text = "┌───┐\n│ X │\n"  # No bottom
        parser = BoxParser()
        boxes = parser.parse(text)
        self.assertEqual(len(boxes), 0)

    def test_incomplete_box_no_top_right(self):
        """Test that boxes without top-right corner are ignored"""
        text = "┌───\n│ X │\n└───┘"  # No ┐
        parser = BoxParser()
        boxes = parser.parse(text)
        self.assertEqual(len(boxes), 0)

    def test_multiple_boxes_same_line(self):
        """Test multiple boxes starting on the same line"""
        text = "┌───┐ ┌───┐\n│ A │ │ B │\n└───┘ └───┘"
        parser = BoxParser()
        boxes = parser.parse(text)
        self.assertEqual(len(boxes), 2)

    def test_deeply_nested_boxes(self):
        """Test boxes nested 3+ levels deep"""
        text = """\
┌─────────────┐
│ ┌─────────┐ │
│ │ ┌─────┐ │ │
│ │ │ ┌─┐ │ │ │
│ │ │ └─┘ │ │ │
│ │ └─────┘ │ │
│ └─────────┘ │
└─────────────┘"""
        parser = BoxParser()
        boxes = parser.parse(text)
        self.assertEqual(len(boxes), 4)
        max_nesting = max(b.nesting_level for b in boxes)
        self.assertEqual(max_nesting, 3)

    def test_box_without_vertical_bars(self):
        """Test that boxes without vertical bars between top/bottom are rejected"""
        text = "┌───┐\ntext\n└───┘"  # No │ characters
        parser = BoxParser()
        boxes = parser.parse(text)
        # Should be rejected due to validation
        self.assertEqual(len(boxes), 0)


class TestBoxAligner(unittest.TestCase):
    """Test box alignment functionality"""

    def test_align_simple_box(self):
        """Test alignment of a simple box"""
        input_text = """\
┌─────────┐
│ Content │
│ More   │
└─────────┘
"""
        expected = """\
┌─────────┐
│ Content │
│ More    │
└─────────┘
"""
        aligner = BoxAligner()
        result = aligner.fix(input_text)

        self.assertEqual(result, expected)

    def test_align_nested_boxes(self):
        """Test that nested boxes align independently"""
        input_text = """\
┌────────────────┐
│ Outer Box     │
│  ┌──────┐     │
│  │ Inner│     │
│  └──────┘     │
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

    def test_align_multiple_boxes(self):
        """Test alignment of multiple separate boxes"""
        input_text = """\
First box:
┌─────────┐
│ Box 1  │
└─────────┘

Second box:
┌───────────────┐
│ Box 2        │
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


class TestAlignmentEdgeCases(unittest.TestCase):
    """Test edge cases in box alignment"""

    def test_content_longer_than_box(self):
        """Test handling when content extends beyond box border"""
        input_text = "┌───┐\n│ This is way too long │\n└───┘"
        aligner = BoxAligner()
        result = aligner.fix(input_text)
        # Should not corrupt the text
        self.assertIn('This is way too long', result)

    def test_box_with_trailing_whitespace(self):
        """Test box with trailing spaces on lines"""
        input_text = "┌───┐   \n│ X│   \n└───┘   "
        aligner = BoxAligner()
        result = aligner.fix(input_text)
        # Should handle gracefully
        self.assertIn('│ X', result)

    def test_minimal_width_box(self):
        """Test box with minimal width (2 characters)"""
        input_text = "┌┐\n││\n└┘"
        aligner = BoxAligner()
        result = aligner.fix(input_text)
        self.assertIn('┌┐', result)

    def test_very_wide_box(self):
        """Test box with very wide content"""
        width = 200
        input_text = f"┌{'─' * (width-2)}┐\n│{' ' * (width-2)}│\n└{'─' * (width-2)}┘"
        aligner = BoxAligner()
        result = aligner.fix(input_text)
        # Should not crash
        self.assertIn('┌', result)
        self.assertIn('┘', result)


class TestFileProcessor(unittest.TestCase):
    """Test file processing functionality"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_process_single_file(self):
        """Test processing a single file"""
        test_file = os.path.join(self.temp_dir, 'test.md')
        with open(test_file, 'w') as f:
            f.write("┌───┐\n│ X│\n└───┘\n")

        processor = FileProcessor()
        processor.process_file(test_file, in_place=True)

        with open(test_file, 'r') as f:
            result = f.read()

        self.assertIn('│ X │', result)

    def test_process_file_not_found(self):
        """Test handling of non-existent file"""
        processor = FileProcessor()
        with self.assertRaises(FileNotFoundError):
            processor.process_file('/nonexistent/file.md')

    def test_process_directory(self):
        """Test processing multiple files in directory"""
        # Create multiple test files
        for i in range(3):
            test_file = os.path.join(self.temp_dir, f'test{i}.md')
            with open(test_file, 'w') as f:
                f.write("┌───┐\n│ X│\n└───┘\n")

        processor = FileProcessor()
        count = processor.process_directory(self.temp_dir, pattern='*.md', in_place=True)

        self.assertEqual(count, 3)

        # Verify all files were fixed
        for i in range(3):
            test_file = os.path.join(self.temp_dir, f'test{i}.md')
            with open(test_file, 'r') as f:
                result = f.read()
            self.assertIn('│ X │', result)

    def test_process_directory_with_subdirs(self):
        """Test recursive directory processing"""
        # Create subdirectory
        subdir = os.path.join(self.temp_dir, 'subdir')
        os.makedirs(subdir)

        test_file = os.path.join(subdir, 'test.md')
        with open(test_file, 'w') as f:
            f.write("┌───┐\n│ X│\n└───┘\n")

        processor = FileProcessor()
        count = processor.process_directory(self.temp_dir, pattern='*.md', in_place=True)

        self.assertEqual(count, 1)

    def test_process_file_dry_run(self):
        """Test dry-run mode doesn't modify files"""
        test_file = os.path.join(self.temp_dir, 'test.md')
        original_content = "┌───┐\n│ X│\n└───┘\n"
        with open(test_file, 'w') as f:
            f.write(original_content)

        processor = FileProcessor()
        result = processor.process_file(test_file, in_place=True, dry_run=True)

        # File should not be modified
        with open(test_file, 'r') as f:
            file_content = f.read()

        self.assertEqual(file_content, original_content)
        # But result should show what would be fixed
        self.assertIn('│ X │', result)

    def test_process_directory_not_a_directory(self):
        """Test error handling for non-directory path"""
        test_file = os.path.join(self.temp_dir, 'test.md')
        with open(test_file, 'w') as f:
            f.write("test")

        processor = FileProcessor()
        with self.assertRaises(NotADirectoryError):
            processor.process_directory(test_file)

    def test_unicode_file_handling(self):
        """Test processing files with Unicode content"""
        test_file = os.path.join(self.temp_dir, 'unicode.md')
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write("┌───┐\n│ 中文│\n└───┘\n")

        processor = FileProcessor()
        processor.process_file(test_file, in_place=True)

        with open(test_file, 'r', encoding='utf-8') as f:
            result = f.read()

        self.assertIn('中文', result)

    def test_file_not_a_regular_file(self):
        """Test error when path is not a regular file"""
        processor = FileProcessor()
        with self.assertRaises(ValueError):
            processor.process_file(self.temp_dir)  # Directory, not file


class TestEdgeCases(unittest.TestCase):
    """Test general edge cases"""

    def test_empty_box(self):
        """Test handling of empty box"""
        aligner = BoxAligner()
        result = aligner.fix("┌───┐\n└───┘\n")
        self.assertIn('┌', result)

    def test_no_boxes(self):
        """Test text with no boxes"""
        input_text = "Just some regular text\n"
        aligner = BoxAligner()
        result = aligner.fix(input_text)
        self.assertEqual(result, input_text)

    def test_box_with_tabs(self):
        """Test that tabs are expanded to spaces for consistent alignment"""
        # Input has tabs (represented as \t) which should be expanded
        input_text = "┌─────────┐\n│\tContent │\n│ Text\t│\n└─────────┘\n"
        aligner = BoxAligner()
        result = aligner.fix(input_text)

        # Result should have no tabs, all converted to spaces
        self.assertNotIn('\t', result)
        # Should still contain the box characters
        self.assertIn('┌', result)
        self.assertIn('│', result)
        self.assertIn('└', result)

    def test_complex_nested_box_with_malformed_inner_box(self):
        """Test malformed nested box from real docs - inner box has inconsistent borders"""
        # This is the ACTUAL box from complete-system-architecture.md
        # The LTSSM inner box has inconsistent right borders (61, 62, 63)
        # The outer box also has inconsistent right borders (64, 65, 66)
        input_text = """\
┌────────────────────────────▼────────────────────────────────────┐
│                    DATA LINK LAYER (DLL)                         │
│                    Location: litepcie/dll/                       │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐│
│  │   DLL TX     │  │   DLL RX     │  │   Retry Buffer         ││
│  │              │  │              │  │                        ││
│  │ • LCRC gen   │  │ • LCRC check │  │ • Store TLPs           ││
│  │ • Seq num    │  │ • ACK/NAK    │  │ • Replay on NAK        ││
│  │ • DLLP gen   │  │ • DLLP parse │  │ • 4KB circular buffer  ││
│  └──────────────┘  └──────────────┘  └────────────────────────┘│
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              LTSSM (Link Training State Machine)         │  │
│  │                                                           │  │
│  │  States: DETECT → POLLING → CONFIG → L0 → RECOVERY      │  │
│  │  Controls: Speed negotiation, TS1/TS2 exchange          │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  DLLP Types: ACK, NAK, UpdateFC, PM_Enter_L1, etc.             │
└────────────────────────────┬────────────────────────────────────┘"""
        expected = """\
┌────────────────────────────▼────────────────────────────────────┐
│                    DATA LINK LAYER (DLL)                        │
│                    Location: litepcie/dll/                      │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │   DLL TX     │  │   DLL RX     │  │   Retry Buffer         │ │
│  │              │  │              │  │                        │ │
│  │ • LCRC gen   │  │ • LCRC check │  │ • Store TLPs           │ │
│  │ • Seq num    │  │ • ACK/NAK    │  │ • Replay on NAK        │ │
│  │ • DLLP gen   │  │ • DLLP parse │  │ • 4KB circular buffer  │ │
│  └──────────────┘  └──────────────┘  └────────────────────────┘ │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              LTSSM (Link Training State Machine)         │   │
│  │                                                          │   │
│  │  States: DETECT → POLLING → CONFIG → L0 → RECOVERY       │   │
│  │  Controls: Speed negotiation, TS1/TS2 exchange           │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  DLLP Types: ACK, NAK, UpdateFC, PM_Enter_L1, etc.              │
└────────────────────────────┬────────────────────────────────────┘"""

        aligner = BoxAligner()
        result = aligner.fix(input_text)

        self.assertEqual(result, expected)


class TestCommandLineIntegration(unittest.TestCase):
    """Integration tests for command-line interface"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_cli_help(self):
        """Test that --help works"""
        result = subprocess.run(
            ['python3', 'fix_ascii_boxes.py', '--help'],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('usage:', result.stdout.lower())

    def test_cli_single_file_stdout(self):
        """Test processing single file to stdout"""
        test_file = os.path.join(self.temp_dir, 'test.md')
        with open(test_file, 'w') as f:
            f.write("┌───┐\n│ X│\n└───┘\n")

        result = subprocess.run(
            ['python3', 'fix_ascii_boxes.py', test_file],
            capture_output=True, text=True
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn('│ X │', result.stdout)

    def test_cli_in_place_modification(self):
        """Test in-place file modification via CLI"""
        test_file = os.path.join(self.temp_dir, 'test.md')
        with open(test_file, 'w') as f:
            f.write("┌───┐\n│ X│\n└───┘\n")

        result = subprocess.run(
            ['python3', 'fix_ascii_boxes.py', '--in-place', test_file],
            capture_output=True, text=True
        )

        self.assertEqual(result.returncode, 0)

        with open(test_file, 'r') as f:
            content = f.read()
        self.assertIn('│ X │', content)

    def test_cli_directory_without_recursive_flag(self):
        """Test that directory requires --recursive flag"""
        result = subprocess.run(
            ['python3', 'fix_ascii_boxes.py', self.temp_dir],
            capture_output=True, text=True
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('recursive', result.stderr.lower())

    def test_cli_nonexistent_file(self):
        """Test CLI with non-existent file"""
        result = subprocess.run(
            ['python3', 'fix_ascii_boxes.py', '/nonexistent/file.md'],
            capture_output=True, text=True
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('not found', result.stderr.lower())


if __name__ == '__main__':
    unittest.main()
