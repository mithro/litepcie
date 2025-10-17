# PIPE-Style PCIe DLL & PHY Implementation Plan (REVISED)

> **For Claude:** Use `${SUPERPOWERS_SKILLS_ROOT}/skills/collaboration/executing-plans/SKILL.md` to implement this plan task-by-task.

**Goal:** Implement fully open-source PCIe Data Link Layer (DLL) with PIPE interface support, enabling complete control over the PCIe stack without vendor IP black boxes.

**Target Users:** Developers who want:
- 100% open source PCIe implementation
- Full visibility and control over all layers
- Support for open source FPGA toolchains (Yosys+nextpnr, OpenXC7)
- Advanced features (error injection, improved hot plug, newer PCIe capabilities)
- Freedom from vendor IP licensing and tools

**Primary Platform:** Lattice ECP5 with open source tooling (no vendor PCIe IP available)

**Architecture:** Clean layering with drop-in replacement for vendor IP:
- **TLP Layer** ↔ **DLL Layer** ↔ **PIPE Interface** ↔ **PHY** ↔ Transceivers
- Alternative pathway: Users can choose vendor IP or open-source stack
- Same software interface: transparent swap between implementations

**Approach:**
- Start simple: PIPE 3.0 (Gen1/Gen2), minimal subset to work
- Iterate and expand: add features incrementally
- External PHY first: Begin with external PIPE PHY chip (simplest case)
- Then internal transceivers: Xilinx GTX, ECP5 SERDES (more complex)
- Test-driven: Behavioral tests + compliance tests
- Open source only: No proprietary tools required

**Tech Stack:** Migen/LiteX, cocotb + Verilator, pytest + pytest-cov, Sphinx, Yosys+nextpnr, OpenXC7

---

## Phase 0: Foundation & Standards (Weeks 1-4)

**Purpose:** Establish infrastructure, standards, and specifications before coding begins. This phase ensures quality and prevents drift.

### Task 0.1: Initial PIPE Interface Documentation

**Files:**
- Create: `docs/reference/pipe-interface-spec.md`
- Create: `docs/pipe-signals.md`

**Step 1: Research PIPE specifications**

Research and document PIPE interface from multiple sources:
- Intel PIPE specification white paper (PHY Interface for PCI Express, SATA, USB 3.x)
- External PIPE PHY chip datasheets (TI TUSB1310A, PLX/Broadcom chips)
- PCIe Base Specification physical layer requirements
- USB3 PIPE implementations (usb3_pipe project by Enjoy-Digital)

Cross-check signal definitions, timing requirements, and protocol details across all sources.

**Step 2: Document minimal PIPE 3.0 subset**

Create `docs/reference/pipe-interface-spec.md` with:

```markdown
# PIPE Interface Specification (Minimal PIPE 3.0)

## Overview

This document defines the PIPE (PHY Interface for PCI Express) signals
and protocol used in LitePCIe's open source implementation.

**Version:** PIPE 3.0 (PCIe Gen1/Gen2)
**Scope:** MAC side (we drive the PHY)
**Approach:** Minimal working subset, expand incrementally

## Signal List (8-bit Mode, Gen1)

### Transmit Interface
| Signal | Width | Direction | Description |
|--------|-------|-----------|-------------|
| TxData | 8 | MAC→PHY | Transmit data |
| TxDataK | 1 | MAC→PHY | K-character indicator (1=ordered set) |
| TxElecIdle | 1 | MAC→PHY | Electrical idle request |

### Receive Interface
| Signal | Width | Direction | Description |
|--------|-------|-----------|-------------|
| RxData | 8 | PHY→MAC | Received data |
| RxDataK | 1 | PHY→MAC | K-character indicator |
| RxValid | 1 | PHY→MAC | Data valid |
| RxStatus | 3 | PHY→MAC | Receiver status |
| RxElecIdle | 1 | PHY→MAC | Electrical idle detected |

### Control Interface
| Signal | Width | Direction | Description |
|--------|-------|-----------|-------------|
| PowerDown | 2 | MAC→PHY | Power state (00=P0, 01=P0s, 10=P1, 11=P2) |
| Rate | 1 | MAC→PHY | Speed select (0=Gen1/2.5GT/s, 1=Gen2/5.0GT/s) |
| RxPolarity | 1 | MAC→PHY | Invert RX polarity |

### Clock/Reset
| Signal | Width | Direction | Description |
|--------|-------|-----------|-------------|
| PCLK | 1 | PHY→MAC | Parallel clock (125 MHz for 8-bit Gen1) |
| Reset_n | 1 | MAC→PHY | Active-low reset |

## Protocol Essentials

### Ordered Sets
Indicated by TxDataK=1. Common ordered sets:
- COM (K28.5, 0xBC): Used for alignment
- SKP (K28.0, 0x1C): Used for clock compensation
- IDLE (sequences with K28.5): Link idle state

### Data Transmission
- TxDataK=0: Normal data byte
- TxData contains payload
- 8b/10b encoding handled by PHY

## References
- [PIPE 3.0 Specification](link to spec)
- PCIe Base Spec 4.0, Section 4 (Physical Layer)
- TI TUSB1310A Datasheet, Section X
```

**Step 3: Create iterative documentation workflow**

Add to plan: "PIPE spec is living document. Update as we:
- Implement external PHY wrapper
- Add Gen2 support
- Add internal transceiver wrappers
- Discover edge cases"

**Step 4: Commit initial PIPE documentation**

```bash
git add docs/reference/pipe-interface-spec.md
git commit -m "docs(pipe): Add initial PIPE 3.0 interface specification

Document minimal PIPE interface for Gen1/Gen2:
- Signal definitions (8-bit mode)
- Protocol essentials (ordered sets, data transmission)
- References to multiple sources

This is a living document that will iterate as we implement.

References:
- Intel PIPE Specification
- PCIe Base Spec 4.0 Section 4
- TI TUSB1310A datasheet

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
"
```

### Task 0.2: Analyze LitePCIe Integration Points

**Files:**
- Create: `docs/architecture/integration-strategy.md`
- Read: `litepcie/core/endpoint.py`
- Read: `litepcie/phy/s7pciephy.py`
- Read: `litepcie/phy/common.py`

**Step 1: Analyze existing PHY interface contract**

Study how current vendor PHY integrates with TLP layer:

```python
# From litepcie/core/endpoint.py
self.depacketizer = LitePCIeTLPDepacketizer(...)
self.packetizer = LitePCIeTLPPacketizer(...)

# Connection to PHY
self.comb += [
    phy.source.connect(depacketizer.sink),  # RX: PHY → TLP
    packetizer.source.connect(phy.sink)     # TX: TLP → PHY
]
```

Document the interface contract:
- What layout does `phy.source` use? (Answer: `phy_layout(data_width)`)
- What signals must be present? (dat, be, first, last, valid, ready)
- What are the timing requirements?
- How does MSI work?
- How are link status signals exposed?

**Step 2: Design DLL/PIPE PHY wrapper interface**

Create architecture where our DLL+PIPE stack presents identical interface:

```
Current (Vendor IP):
    TLP Layer → phy.sink/source → Vendor IP (PHY+DLL) → Transceivers

New (Open Source):
    TLP Layer → phy.sink/source → DLL → PIPE → PHY → Transceivers
                                   ↑
                         Same interface as vendor IP!
```

**Step 3: Document integration strategy**

Create `docs/architecture/integration-strategy.md`:

```markdown
# LitePCIe Integration Strategy

## Goal
Provide drop-in replacement for vendor PCIe IP with open source DLL+PIPE stack.

## Interface Contract

The PHY (whether vendor IP or our custom stack) must provide:

### Signals
```python
# From litepcie/common.py
def phy_layout(data_width):
    return [
        ("dat", data_width),
        ("be",  data_width//8)
    ]
```

Plus stream control: valid, ready, first, last

### PHY Wrapper Class Structure
```python
class CustomPCIePHY(LiteXModule):
    """Open source PCIe PHY with DLL and PIPE interface"""

    def __init__(self, platform, pads, data_width=64, ...):
        # Same signature as S7PCIEPHY, USPCIEPHY, etc.

        # Must provide these endpoints
        self.sink   = stream.Endpoint(phy_layout(data_width))  # TX from TLP layer
        self.source = stream.Endpoint(phy_layout(data_width))  # RX to TLP layer
        self.msi    = stream.Endpoint(msi_layout())

        # Must provide these registers
        self._link_status = CSRStatus(...)
        self._msi_enable = CSRStatus(...)
        # ... etc

        # Internal: DLL + PIPE + PHY
        self.submodules.dll = DLL(data_width)
        self.submodules.pipe = PIPEInterface(...)
        self.submodules.phy = PHYWrapper(...)  # External chip or transceiver
```

## Usage

Users can swap implementations:

```python
# Option 1: Vendor IP (Xilinx)
from litepcie.phy.s7pciephy import S7PCIEPHY
phy = S7PCIEPHY(platform, pads, data_width=128)

# Option 2: Open source stack (external PIPE PHY)
from litepcie.phy.pipe_phy import PIPEPCIePHY
phy = PIPEPCIePHY(platform, pads, data_width=128, pipe_chip="TUSB1310A")

# Option 3: Open source stack (ECP5 internal SERDES)
from litepcie.phy.ecp5_pipe_phy import ECP5PIPEPCIePHY
phy = ECP5PIPEPCIePHY(platform, pads, data_width=128)

# Rest of design is identical
endpoint = LitePCIeEndpoint(phy, ...)
```

## Implementation Phases

1. Build DLL in isolation (tests with models)
2. Build PIPE interface (tests with models)
3. Integrate DLL + PIPE
4. Add external PIPE PHY wrapper
5. Add internal transceiver wrappers
6. Test drop-in replacement with existing designs
```

**Step 4: Commit integration strategy**

```bash
git add docs/architecture/integration-strategy.md
git commit -m "docs(integration): Define drop-in replacement strategy

Document how open source DLL+PIPE stack integrates with LitePCIe:
- PHY interface contract (phy_layout, stream endpoints)
- Wrapper class structure
- Usage examples showing transparent swap

Users can choose vendor IP or open source implementation.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
"
```

### Task 0.3: Setup CI/CD Test Infrastructure

**Files:**
- Create: `.github/workflows/test.yml`
- Create: `test/README.md`
- Create: `test/requirements.txt`
- Create: `.coveragerc`

**Step 1: Create GitHub Actions workflow**

```yaml
# .github/workflows/test.yml
name: Tests

on:
  push:
    branches: [ master, develop ]
  pull_request:
    branches: [ master ]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install ruff

      - name: Lint with ruff
        run: ruff check litepcie/ test/

  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r test/requirements.txt
          pip install pytest pytest-cov

      - name: Run unit tests with coverage
        run: |
          pytest test/ -v --cov=litepcie --cov-report=xml --cov-report=term

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml

  cocotb-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install Verilator
        run: |
          sudo apt-get update
          sudo apt-get install -y verilator

      - name: Install Python dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r test/requirements.txt
          pip install cocotb cocotb-test

      - name: Run cocotb tests
        run: |
          cd test/dll/cocotb
          make

      - name: Check Verilator coverage
        run: |
          # Process Verilator coverage files
          verilator_coverage --annotate coverage_output/ coverage.dat
```

**Step 2: Create test requirements file**

```python
# test/requirements.txt
# LiteX and dependencies
migen>=0.9
litex>=2023.12

# Testing frameworks
pytest>=7.4
pytest-cov>=4.1
cocotb>=1.8
cocotb-test>=0.2

# Utilities
pyvcd>=0.3  # Waveform generation
```

**Step 3: Create test documentation**

```markdown
# test/README.md

# LitePCIe Testing

## Overview

LitePCIe uses two complementary testing approaches:
- **Unit tests**: pytest-based tests for individual modules (fast)
- **Integration tests**: cocotb-based tests with Verilator (comprehensive)

## Requirements

### Software
- Python 3.11+
- Verilator 5.0+ (open source Verilog simulator)
- pytest, pytest-cov
- cocotb, cocotb-test

### Installation
```bash
# Install Python dependencies
pip install -r test/requirements.txt

# Install Verilator (Ubuntu/Debian)
sudo apt-get install verilator

# Install Verilator (from source for latest version)
git clone https://github.com/verilator/verilator
cd verilator
autoconf && ./configure && make && sudo make install
```

## Running Tests

### All tests (what CI runs)
```bash
# From repository root
pytest test/ -v --cov=litepcie
```

### Unit tests only
```bash
pytest test/dll/test_*.py -v
```

### Cocotb tests
```bash
cd test/dll/cocotb
make
```

### Single test
```bash
pytest test/dll/test_dllp.py::TestDLLPStructures::test_ack_dllp_creation -v
```

## Coverage

### Generate coverage report
```bash
pytest test/ --cov=litepcie --cov-report=html
open htmlcov/index.html
```

### Coverage goals
- **Target**: 100% line coverage for new code
- **Minimum**: 80% coverage to merge PR
- Uncovered lines must be justified (e.g., unreachable error paths)

## Writing Tests

### Unit tests (pytest)
Use for testing individual modules in isolation:

```python
# test/dll/test_sequence.py
import unittest
from litex.gen import run_simulation
from litepcie.dll.sequence import SequenceNumberManager

class TestSequenceNumbers(unittest.TestCase):
    def test_increment(self):
        dut = SequenceNumberManager()

        def testbench(dut):
            # Allocate sequence 0
            yield dut.tx_alloc.eq(1)
            yield
            seq = (yield dut.tx_seq_num)
            self.assertEqual(seq, 0)

            # Allocate sequence 1
            yield
            seq = (yield dut.tx_seq_num)
            self.assertEqual(seq, 1)

        run_simulation(dut, testbench(dut))
```

### Integration tests (cocotb)
Use for testing module interactions and timing:

```python
# test/dll/cocotb/test_retry_buffer.py
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

@cocotb.test()
async def test_nak_replay(dut):
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Test scenario
    await RisingEdge(dut.clk)
    # ... test logic
```

## Test Organization

```
test/
├── README.md                    # This file
├── requirements.txt             # Python dependencies
├── dll/                         # DLL layer tests
│   ├── test_dllp.py            # Unit tests
│   ├── test_sequence.py
│   ├── test_lcrc.py
│   ├── test_retry_buffer.py
│   ├── compliance/             # PCIe spec compliance tests
│   │   ├── test_spec_3_3.py   # Section 3.3 (DLL)
│   │   └── test_spec_3_4.py   # Section 3.4 (DLLPs)
│   └── cocotb/                 # Integration tests
│       ├── Makefile
│       ├── test_dll_integration.py
│       └── test_retry_scenarios.py
└── pipe/                        # PIPE interface tests
    ├── test_pipe_interface.py
    └── cocotb/
```

## Continuous Integration

All tests run automatically on:
- Every push to master/develop
- Every pull request
- Nightly builds

See `.github/workflows/test.yml` for CI configuration.

## Debugging Failed Tests

### View test output
```bash
pytest test/ -v -s  # -s shows print statements
```

### Generate waveforms (cocotb)
```bash
cd test/dll/cocotb
make WAVES=1
gtkwave dump.vcd
```

### Interactive debugging
```bash
pytest test/dll/test_dllp.py --pdb  # Drop into debugger on failure
```
```

**Step 4: Create coverage configuration**

```ini
# .coveragerc
[run]
source = litepcie
omit =
    */test/*
    */setup.py
    */__init__.py

[report]
exclude_lines =
    pragma: no cover
    def __repr__
    raise AssertionError
    raise NotImplementedError
    if __name__ == .__main__.:
    if TYPE_CHECKING:
```

**Step 5: Commit CI/CD infrastructure**

```bash
git add .github/workflows/test.yml test/README.md test/requirements.txt .coveragerc
git commit -m "ci: Setup CI/CD test infrastructure

Add GitHub Actions workflow for automated testing:
- Linting with ruff
- Unit tests with pytest + coverage
- Integration tests with cocotb + Verilator
- Coverage upload to Codecov

Open source simulators only (Verilator).
All tests must pass in CI.

Test documentation in test/README.md covers:
- Installation instructions
- Running tests locally
- Writing new tests
- Coverage goals (100% target, 80% minimum)

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
"
```

### Task 0.4: Create Code Quality Standards & Pre-commit Hooks

**Files:**
- Create: `docs/development/code-quality.md`
- Create: `.pre-commit-config.yaml`
- Create: `pyproject.toml` (for ruff config)
- Create: `CONTRIBUTING.md`

**Step 1: Write code quality standards document**

```markdown
# docs/development/code-quality.md

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
```

**Step 2: Create ruff configuration**

```toml
# pyproject.toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes
    "I",   # isort (import sorting)
    "N",   # pep8-naming
    "UP",  # pyupgrade
]

ignore = [
    "E501",  # line too long (handled by formatter)
    "F405",  # undefined name from star imports (migen convention)
    "F403",  # unable to detect undefined names (migen convention)
]

[tool.ruff.lint.per-file-ignores]
"__init__.py" = ["F401"]  # Unused imports OK in __init__.py

[tool.ruff.lint.isort]
known-first-party = ["litepcie"]
section-order = ["future", "standard-library", "third-party", "litex", "first-party", "local-folder"]

[tool.ruff.lint.isort.sections]
"litex" = ["migen", "litex"]
```

**Step 3: Create pre-commit configuration**

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.9
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
        args: ['--maxkb=1000']
      - id: mixed-line-ending
```

**Step 4: Create contribution guide**

```markdown
# CONTRIBUTING.md

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

**Before contributing, read**: `docs/development/code-quality.md`

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
```

**Step 5: Commit code quality standards**

```bash
git add docs/development/code-quality.md pyproject.toml .pre-commit-config.yaml CONTRIBUTING.md
git commit -m "docs: Add code quality standards and pre-commit hooks

Define comprehensive code quality standards:
- Python style (ruff linting, 100 char line length)
- Import conventions (no wildcards except migen)
- Naming conventions (PascalCase classes, snake_case functions)
- Error handling (always validate inputs)
- TODO policy (no TODOs in critical paths)
- Migen/LiteX patterns (# # # separator, Signal usage)
- Documentation (NumPy docstrings, PCIe spec references)
- Testing (behavior not structure, 100% coverage goal)

Pre-commit hooks enforce:
- ruff linting
- Import sorting
- Trailing whitespace removal
- File size checks

Standards are living - iterate via PR.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
"
```

---

## Phase 1: DLL Core Infrastructure (Weeks 5-8)

**Note**: Phase numbering continues from Phase 0. Week numbers reset for clarity within each phase.

### Task 1.1: Project Structure & Documentation Foundation

[Content remains largely the same as original plan, but updated to follow new standards]

**Files:**
- Create: `litepcie/dll/__init__.py`
- Create: `litepcie/dll/common.py`
- Create: `test/dll/__init__.py`
- Update: `docs/sphinx/index.rst`
- Create: `docs/sphinx/dll/architecture.rst`

**Step 1: Write failing test for project structure**

```python
# test/dll/test_project_structure.py
import unittest

class TestProjectStructure(unittest.TestCase):
    def test_dll_module_imports(self):
        """Verify DLL module can be imported"""
        try:
            from litepcie.dll import common
            from litepcie.dll import dllp
        except ImportError as e:
            self.fail(f"DLL module import failed: {e}")

    def test_dll_module_has_version(self):
        """Verify DLL module exposes version"""
        from litepcie.dll import __version__
        self.assertIsNotNone(__version__)
```

**Step 2: Run test to verify it fails**

Run: `pytest test/dll/test_project_structure.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'litepcie.dll'"

**Step 3: Create minimal directory structure**

```python
# litepcie/dll/__init__.py
"""
LitePCIe Data Link Layer Implementation.

This module implements the PCIe Data Link Layer as specified in
PCI Express Base Specification Rev. 4.0, Section 3.

The DLL provides reliable packet delivery through:
- DLLP (Data Link Layer Packet) processing
- Sequence number assignment
- LCRC generation and checking
- ACK/NAK protocol with retry buffer
- Flow control credit management

Target Users
------------
Developers who want:
- 100% open source PCIe implementation
- Full visibility and control over all layers
- Support for open source FPGA toolchains
- Advanced features (error injection, improved hot plug)

Primary Platform
----------------
Lattice ECP5 with Yosys+nextpnr (no vendor PCIe IP available)

Architecture
------------
TLP Layer ↔ DLL Layer ↔ PIPE Interface ↔ PHY ↔ Transceivers

This is an alternative pathway to vendor IP. Users can choose
vendor IP or this open-source stack transparently.

References
----------
- PCIe Base Spec 4.0, Section 3: https://pcisig.com/specifications
- "PCI Express System Architecture" by Budruk et al., Chapters 8-9
- Intel PIPE Specification white paper

Examples
--------
>>> # Option 1: Vendor IP
>>> from litepcie.phy.s7pciephy import S7PCIEPHY
>>> phy = S7PCIEPHY(platform, pads)
>>>
>>> # Option 2: Open source DLL+PIPE stack
>>> from litepcie.phy.pipe_phy import PIPEPCIePHY
>>> phy = PIPEPCIePHY(platform, pads, pipe_chip="TUSB1310A")
>>>
>>> # Rest of design is identical
>>> endpoint = LitePCIeEndpoint(phy, ...)
"""

__version__ = "0.1.0"
```

[Rest of Task 1.1 follows similar pattern to original, with code quality improvements]

---

*[Due to length, I'll provide a condensed summary of remaining phases with key changes]*

---

## Remaining Phases Summary

### Phase 1: DLL Core (Weeks 5-8)
- Task 1.1: Project structure (✓ shown above)
- Task 1.2: DLLP types & CRC-16 (revised test examples to test behavior)
- Task 1.3: Sequence number management (add compliance tests)
- Task 1.4: LCRC implementation (no TODOs, complete iterative version first)

### Phase 2: Retry Buffer & ACK/NAK (Weeks 9-12)
- Task 2.1: Retry buffer (configurable depth, test-driven sizing)
- Task 2.2: DLL TX path (behavioral tests)
- Task 2.3: DLL RX path (error injection tests)
- Task 2.4: Compliance tests for PCIe Spec Section 3.3

### Phase 3: PIPE Interface - External PHY (Weeks 13-16)
**KEY CHANGE**: External PIPE PHY chip comes FIRST (simplest case)

- Task 3.1: PIPE interface abstraction (based on Task 0.1 spec)
- Task 3.2: External PIPE PHY wrapper (TI TUSB1310A or similar)
- Task 3.3: Integration tests with DLL
- Task 3.4: Hardware testing on board with external PIPE chip

### Phase 4: Internal Transceivers - Xilinx (Weeks 17-20)
- Task 4.1: Xilinx GTX PIPE wrapper (Gen1/Gen2)
- Task 4.2: 8b/10b encoding/decoding
- Task 4.3: Ordered set handling
- Task 4.4: Integration with DLL

### Phase 5: Internal Transceivers - ECP5 (Weeks 21-24)
**KEY FOCUS**: Open source toolchain hero platform

- Task 5.1: ECP5 SERDES PIPE wrapper
- Task 5.2: Open toolchain validation (Yosys+nextpnr)
- Task 5.3: Hardware testing on ECP5 board
- Task 5.4: Performance characterization

### Phase 6: Integration & Validation (Weeks 25-28)
- Task 6.1: Drop-in replacement testing (swap with vendor IP)
- Task 6.2: Interoperability testing (multiple hosts)
- Task 6.3: Compliance test suite completion
- Task 6.4: Documentation finalization

---

## Key Improvements from Original Plan

### 1. Foundation Phase (Phase 0)
- ✅ PIPE interface spec defined upfront (iterative)
- ✅ Integration strategy documented
- ✅ CI/CD infrastructure setup
- ✅ Code quality standards enforced

### 2. External PHY First Approach
- ✅ Start with external PIPE chip (simplest, most concrete)
- ✅ Then add internal transceivers (more complex)
- ✅ Validates architecture before tackling hard problems

### 3. Testing Improvements
- ✅ Behavioral tests (not structural)
- ✅ Compliance tests for each spec section
- ✅ Both custom scenarios and official test vectors
- ✅ CI/CD enforced, open source simulators only

### 4. Code Quality
- ✅ Standards defined upfront
- ✅ Pre-commit hooks enforce
- ✅ No TODOs in critical paths
- ✅ Error handling throughout
- ✅ PCIe spec references everywhere

### 5. Documentation
- ✅ Iterative approach (build as we develop)
- ✅ NumPy-style docstrings
- ✅ Usage examples in every module
- ✅ Integration guides

### 6. Scope & Motivation
- ✅ Clear target users (open source, no black boxes)
- ✅ ECP5 as hero platform
- ✅ Drop-in replacement for vendor IP
- ✅ Advanced features enabled

---

## Success Criteria

**Functional:**
- [ ] Link trains to L0 on ECP5 with open source tools
- [ ] TLPs transmitted/received with ACK/NAK working
- [ ] External PIPE PHY chip supported
- [ ] Drop-in replacement for vendor IP (transparent swap)
- [ ] Works on multiple platforms (ECP5, Xilinx 7-series)

**Quality:**
- [ ] 100% coverage goal (minimum 80%)
- [ ] All CI tests passing
- [ ] Compliance tests for PCIe Spec Section 3.3-3.4
- [ ] Pre-commit hooks enforced
- [ ] Code quality standards followed

**Open Source:**
- [ ] Builds with Yosys+nextpnr for ECP5
- [ ] No vendor tools required (simulators, synthesis)
- [ ] No vendor IP dependencies
- [ ] BSD-2-Clause license

**Documentation:**
- [ ] Complete Sphinx documentation
- [ ] API reference with examples
- [ ] Integration guide for drop-in replacement
- [ ] PIPE interface specification

---

## Execution Notes

**Approach:**
- Start simple, iterate and expand
- External PHY first, internal transceivers second
- Test-driven: write tests before implementation
- Behavioral tests: verify functionality, not structure
- Compliance tests: map spec "shall" statements to test cases
- Documentation: build iteratively alongside code

**Toolchain:**
- Open source simulators: Verilator, Icarus
- CI/CD: GitHub Actions
- Coverage: pytest-cov, Verilator coverage
- Linting: ruff with pre-commit hooks

**Quality Gates:**
- All tests must pass in CI
- Coverage >= 80% for new code (100% goal)
- Pre-commit hooks must pass
- Code review by maintainer

**Flexibility:**
- Standards iterate as we learn
- Documentation evolves with code
- Test scenarios expand as we discover edge cases
- PIPE spec refines as we implement

---

This revised plan addresses all evaluation findings while maintaining flexibility and iterative development approach.
