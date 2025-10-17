# LitePCIe Code Quality Standards

This document defines code quality standards for the LitePCIe project.
These standards ensure consistency, maintainability, and quality across contributions.

**Philosophy:** These are living standards. Propose improvements via PR.

## Python Style

### Linter
- **Tool**: [ruff](https://github.com/astral-sh/ruff)
- **Config**: See `pyproject.toml`
- **Enforcement**: Pre-commit hooks + CI

### Line Length
- **Maximum**: 100 characters (LiteX standard)
- **Why**: Balance readability with modern displays

### Imports

**DO:**
```python
from migen import Module, Signal, If, FSM
from litepcie.dll.common import (
    DLLP_TYPE_ACK,
    DLLP_TYPE_NAK,
    dllp_layout,
)
```

**DON'T:**
```python
from litepcie.dll.common import *  # Too broad
```

**Exception**: `from migen import *` is acceptable (LiteX convention)

**Order**: Standard library → Third party → LiteX/Migen → Local
```python
import os
from pathlib import Path

from migen import *
from litex.gen import *

from litepcie.dll.common import dllp_layout
```

### Naming Conventions

| Type | Convention | Example |
|------|------------|---------|
| Module/File | snake_case | `retry_buffer.py` |
| Class | PascalCase | `RetryBuffer` |
| Function | snake_case | `calculate_crc()` |
| Constant | UPPER_SNAKE | `DLL_SEQUENCE_NUM_WIDTH` |
| Signal | snake_case | `tx_seq_num` |
| Private | _prefix | `_internal_helper()` |

**Acronyms**: Use ALL-CAPS in class names
- Good: `DLLPAck`, `LCRCGenerator`, `PHYTXDatapath`
- Bad: `DllpAck`, `LcrcGenerator`, `PhyTxDatapath`

### Error Handling

**Always validate inputs:**

```python
def calculate_dllp_crc16(data: list[int]) -> int:
    """Calculate CRC-16 for DLLP."""
    if len(data) != 6:
        raise ValueError(f"DLLP data must be 6 bytes, got {len(data)}")
    if any(b < 0 or b > 255 for b in data):
        raise ValueError("All bytes must be in range 0-255")

    # ... implementation
```

**Document error conditions in docstrings:**

```python
def send_tlp(self, data):
    """
    Send TLP to DLL.

    Raises
    ------
    ValueError
        If data length exceeds maximum payload size
    BufferFullError
        If retry buffer is full
    """
```

### TODO Policy

**NEVER commit working code with TODOs in critical paths.**

**BAD:**
```python
def calculate_lcrc(self, data):
    # TODO: Implement parallel CRC
    return 0  # Placeholder
```

**GOOD - Option 1 (Iterative implementation):**
```python
def calculate_lcrc(self, data):
    """
    Calculate LCRC using iterative algorithm.

    Note: This is a correct but slow implementation.
    Parallel optimization tracked in issue #123.
    """
    crc = 0xFFFFFFFF
    for byte in data:
        # ... complete working implementation
    return crc
```

**GOOD - Option 2 (Explicit not implemented):**
```python
def calculate_lcrc_parallel(self, data):
    """
    Calculate LCRC using parallel algorithm (future optimization).

    Not yet implemented. See issue #123.
    """
    raise NotImplementedError("Parallel CRC optimization - issue #123")
```

## Migen/LiteX Patterns

### Module Structure

**Follow LiteX convention with `# # #` separator:**

```python
class RetryBuffer(Module):
    """
    Retry buffer for PCIe DLL.

    Stores transmitted TLPs until acknowledged.
    """
    def __init__(self, depth=64, data_width=64):
        # Interface definition (public API)
        self.write_data = Signal(data_width)
        self.write_valid = Signal()
        self.ack_seq = Signal(12)
        self.replay_data = Signal(data_width)

        # # #

        # Implementation (internal details)
        self.specials.storage = Memory(data_width, depth, name="retry_buffer_storage")
        # ...
```

### Signal Usage

**Reset values** only for registers needing non-zero initialization:

```python
# Good: CRC starts at 0xFFFFFFFF per spec
crc_reg = Signal(32, reset=0xFFFFFFFF)

# Good: Counter starts at zero (default)
counter = Signal(12)

# Bad: Don't use reset for initialization values
data = Signal(64, reset=initial_value)  # Use sync logic instead
```

**Memory naming**: Always use `name=` parameter for debugging:

```python
self.specials.data_mem = Memory(
    width = data_width,
    depth = depth,
    name  = "retry_buffer_data"  # Shows in waveforms
)
```

### Submodule Organization

```python
class DLL(LiteXModule):
    def __init__(self):
        # Create submodules
        self.submodules.sequence_mgr = SequenceNumberManager()
        self.submodules.lcrc_gen = LCRCGenerator()
        self.submodules.retry_buffer = RetryBuffer()

        # OR use automatic submodule tracking (LiteX 2023.12+)
        self.sequence_mgr = SequenceNumberManager()
        self.lcrc_gen = LCRCGenerator()
        # ... automatically added to submodules
```

## Documentation

### Docstring Format

**Use NumPy style** (consistent with LiteX):

```python
class RetryBuffer(Module):
    """
    Retry buffer for PCIe DLL ACK/NAK protocol.

    Stores transmitted TLPs until acknowledged by receiver. On NAK reception,
    replays all TLPs after the NAKed sequence number.

    Parameters
    ----------
    depth : int
        Number of TLP slots (must be power of 2)
    data_width : int
        Width of TLP data in bits (64, 128, 256, or 512)

    Attributes
    ----------
    write_data : Signal(data_width), input
        TLP data to store
    write_valid : Signal(1), input
        Write enable
    ack_seq : Signal(12), input
        Sequence number from ACK DLLP

    Examples
    --------
    >>> retry_buf = RetryBuffer(depth=64, data_width=128)
    >>> self.comb += [
    ...     retry_buf.write_data.eq(tlp_data),
    ...     retry_buf.write_valid.eq(tlp_valid),
    ... ]

    References
    ----------
    - PCIe Base Spec 4.0, Section 3.3.7: Retry Buffer
    - "PCI Express System Architecture" Chapter 8

    See Also
    --------
    SequenceNumberManager : Manages sequence number allocation
    DLLTXPath : TX path that uses retry buffer
    """
```

**All public classes/functions must have docstrings.**

**PCIe Spec References**: Always cite section numbers:

```python
def send_nak(self, seq_num):
    """
    Send NAK DLLP.

    NAK indicates the last correctly received TLP. Transmitter must
    replay all TLPs with sequence number > NAK sequence.

    Reference: PCIe Base Spec 4.0, Section 3.4.2
    """
```

### Code Comments

**Explain WHY, not WHAT:**

```python
# Bad: Describes what code does (obvious)
counter = counter + 1  # Increment counter

# Good: Explains why (not obvious)
counter = counter + 1  # Keep retry count for exponential backoff
```

**Link to spec for non-obvious requirements:**

```python
# Sequence numbers wrap at 4096 (PCIe Spec 3.3.5)
if seq_num == 4095:
    seq_num = 0
```

## Testing

### Test Organization

```
test/
├── dll/
│   ├── test_dllp.py           # Unit tests for DLLP module
│   ├── test_sequence.py       # Unit tests for sequence manager
│   ├── compliance/            # PCIe spec compliance tests
│   │   └── test_spec_3_3.py
│   └── cocotb/                # Integration tests
│       └── test_dll_integration.py
```

### Test Naming

```python
def test_ack_clears_retry_buffer():      # Good: describes behavior
def test_retry_buffer_ack():             # OK: clear enough
def test_ack_dllp_type_field():          # Bad: tests structure not behavior
```

### Test Behavior, Not Structure

**BAD (tests internal structure):**
```python
def test_ack_dllp_creation(self):
    dut = DLLPAck(seq_num=42)
    type_val = (yield dut.type)
    self.assertEqual(type_val, DLLP_TYPE_ACK)  # Just checks a constant
```

**GOOD (tests actual behavior):**
```python
def test_ack_clears_retry_buffer(self):
    """Test that ACK DLLP releases stored TLP from retry buffer."""
    dut = DLLSystem()

    # Send TLP (stored in retry buffer)
    yield from send_tlp(dut, seq=5, data=0xDEAD)
    self.assertEqual((yield dut.retry_buffer.count), 1)

    # Receive ACK DLLP
    yield from receive_ack(dut, seq=5)

    # Retry buffer should be cleared
    self.assertEqual((yield dut.retry_buffer.count), 0)
```

### Coverage Requirements

- **Target**: 100% line coverage for new code
- **Minimum to merge**: 80% coverage
- **Exceptions**: Document uncovered lines (e.g., unreachable error handling)

## Performance Standards

### Resource Usage

**Document expected resource consumption:**

```python
class LCRCGenerator(Module):
    """
    Hardware LCRC generator.

    Resource Usage (Xilinx 7-Series, 128-bit datapath):
    - LUTs: ~200
    - FFs: ~32 (pipeline registers)
    - BRAMs: 0

    Verified on: Kintex-7 XC7K325T
    """
```

### Timing

**Document critical paths and Fmax:**

```python
class RetryBuffer(Module):
    """
    Retry buffer with dual-port RAM.

    Performance:
    - Latency: 2 cycles (write → read)
    - Throughput: 1 TLP per cycle
    - Fmax: >300 MHz (Kintex-7)

    Critical path: address decode → RAM access
    """
```

## Git Workflow

### Commit Messages

**Format** (already in use with Claude Code):

```
type(scope): Subject line (imperative, present tense)

Detailed description explaining:
- What changed
- Why it changed
- Any breaking changes
- Issue/spec references

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

**Types**: feat, fix, docs, test, refactor, perf, ci

### Branch Strategy

- `master`: stable, tested code
- `develop`: integration branch
- `feature/xxx`: new features
- `fix/xxx`: bug fixes

### Pull Requests

**Every PR must:**
- Pass all CI tests
- Include tests for new code
- Update documentation
- Follow code quality standards (enforced by pre-commit)

## Pre-commit Hooks

**Install**:
```bash
pip install pre-commit
pre-commit install
```

**What runs automatically:**
- ruff linting
- Import sorting
- Trailing whitespace removal
- File size checks

**Manual run**:
```bash
pre-commit run --all-files
```

## Enforcement

### Pre-commit Hooks
Runs automatically on `git commit`. Fix issues before committing.

### CI Pipeline
All checks run on every PR. Must pass before merge.

### Code Review
Maintainers verify adherence during PR review.

## Questions?

See `CONTRIBUTING.md` or open an issue.
