# Examples

This directory contains before/after examples showing how the ASCII box fixer works.

## Files

- `simple_box_before.md` - A simple box with misaligned borders
- `simple_box_after.md` - The same box after fixing
- `nested_boxes_before.md` - Nested boxes with misalignment
- `nested_boxes_after.md` - Nested boxes after fixing

## Running the Examples

To see the fixer in action, run it on any of the "before" files:

```bash
# Preview changes
python ../fix_ascii_boxes.py simple_box_before.md

# Apply changes in-place
python ../fix_ascii_boxes.py --in-place simple_box_before.md

# Process all markdown files in examples directory
python ../fix_ascii_boxes.py --recursive --in-place --pattern "*.md" .
```

## Expected Behavior

The fixer will:
1. Detect all ASCII boxes (looking for ┌ and ┐ corners)
2. Find the position of the top-right corner ┐
3. Align all right borders │ to match that position
4. Handle nested boxes independently
5. Preserve all other text and formatting
