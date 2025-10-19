# Nested Boxes Example - After

This shows properly aligned nested boxes:

┌────────────────┐
│ Outer Box      │
│  ┌──────┐      │
│  │ Inner│      │
│  └──────┘      │
└────────────────┘

Both outer and inner boxes now have their right borders properly aligned.
The fixer handles each box independently, processing from innermost to outermost.
