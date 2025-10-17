# PIPE Interface Testing Guide

**Version:** 1.0
**Date:** 2025-10-17
**Status:** Complete

This guide explains how to test the LitePCIe PIPE interface implementation, write new tests, and debug issues using simulation.

---

## Table of Contents

1. [Running Tests](#running-tests)
2. [Test Structure](#test-structure)
3. [Writing New Tests](#writing-new-tests)
4. [TDD Workflow](#tdd-workflow)
5. [Debugging Tests](#debugging-tests)
6. [Coverage Analysis](#coverage-analysis)
7. [Performance Testing](#performance-testing)

---

## Running Tests

### Quick Start

```bash
# Run all PIPE tests
uv run pytest test/dll/test_pipe*.py test/phy/test_pipe*.py -v

# Run specific test file
uv run pytest test/dll/test_pipe_loopback.py -v

# Run specific test
uv run pytest test/dll/test_pipe_loopback.py::TestPIPELoopback::test_loopback_single_word -v

# Run with coverage
uv run pytest test/dll/test_pipe*.py --cov=litepcie/dll/pipe --cov-report=term-missing

# Generate HTML coverage report
uv run pytest test/dll/ --cov=litepcie/dll/pipe --cov-report=html
# View: open htmlcov/index.html
```

### Test Organization

```
test/
├── dll/
│   ├── test_pipe_interface.py        # Interface structure and behavior tests
│   ├── test_pipe_tx_packetizer.py    # TX packetizer tests
│   ├── test_pipe_rx_depacketizer.py  # RX depacketizer tests
│   ├── test_pipe_loopback.py         # Integration loopback tests
│   └── test_pipe_edge_cases.py       # Edge cases and error conditions
└── phy/
    └── test_pipe_external_phy.py     # External PHY wrapper tests
```

### Test Counts by Category

```
Total PIPE Tests: 30

Component Tests:
  - TX Packetizer: 6 tests
  - RX Depacketizer: 6 tests
  - Interface: 7 tests
  - External PHY: 4 tests
  - Integration: 4 tests
  - Edge Cases: 8 tests

Coverage:
  - litepcie/dll/pipe.py: 99% (77 statements, 1 missed)
  - litepcie/phy/pipe_external_phy.py: 96% (25 statements, 1 missed)
```

---

## Test Structure

### Anatomy of a PIPE Test

```python
import os
import tempfile
import unittest

from litex.gen import run_simulation
from migen import *

from litepcie.dll.pipe import PIPEInterface

class TestPIPEExample(unittest.TestCase):
    """Test class docstring explaining what is tested."""

    def test_specific_behavior(self):
        """
        Test method docstring explaining:
        - What behavior is tested
        - Why it matters
        - References to spec sections
        """

        def testbench(dut):
            """Testbench generator function."""
            # 1. Setup: Initialize signals
            yield dut.dll_tx_sink.valid.eq(0)
            yield

            # 2. Stimulus: Apply test inputs
            yield dut.dll_tx_sink.valid.eq(1)
            yield dut.dll_tx_sink.dat.eq(0x0123456789ABCDEF)
            yield

            # 3. Wait: Allow propagation
            for _ in range(10):
                yield

            # 4. Check: Verify outputs
            output = yield dut.dll_rx_source.dat
            self.assertEqual(output, 0x0123456789ABCDEF)

        # 5. Create DUT
        dut = PIPEInterface(data_width=8, gen=1)

        # 6. Add loopback if needed
        dut.comb += [
            dut.pipe_rx_data.eq(dut.pipe_tx_data),
            dut.pipe_rx_datak.eq(dut.pipe_tx_datak),
        ]

        # 7. Run simulation with VCD
        with tempfile.TemporaryDirectory(dir=".") as tmpdir:
            vcd_path = os.path.join(tmpdir, "test_example.vcd")
            run_simulation(dut, testbench(dut), vcd_name=vcd_path)

if __name__ == "__main__":
    unittest.main()
```

### Key Patterns

**1. Use Temporary Directories**
```python
# ✅ CORRECT: Auto-cleanup temporary VCD files
with tempfile.TemporaryDirectory(dir=".") as tmpdir:
    vcd_path = os.path.join(tmpdir, "test.vcd")
    run_simulation(dut, testbench(dut), vcd_name=vcd_path)

# ❌ WRONG: VCD files left in project directory
run_simulation(dut, testbench(dut), vcd_name="test.vcd")
```

**2. Wait for Propagation**
```python
# PIPE loopback timing: START(1) + DATA(8) + END(1) = 10 cycles
yield dut.dll_tx_sink.valid.eq(1)
yield
yield dut.dll_tx_sink.valid.eq(0)

# Wait for TX→RX propagation
for _ in range(10):
    yield

# Now check RX output
rx_data = yield dut.dll_rx_source.dat
```

**3. Clear Inputs After Stimulus**
```python
# Send packet
yield dut.dll_tx_sink.valid.eq(1)
yield dut.dll_tx_sink.dat.eq(test_data)
yield

# ✅ CORRECT: Clear input to prevent re-triggering
yield dut.dll_tx_sink.valid.eq(0)
yield
```

**4. Use Debug Mode for Internal Verification**
```python
# Create RX depacketizer with debug signals exposed
dut = PIPERXDepacketizer(debug=True)

# Can now inspect internal buffer
def testbench(dut):
    # ... send data ...
    buffer_value = yield dut.debug_data_buffer
    self.assertEqual(buffer_value, expected_value)
```

---

## Writing New Tests

### Step 1: Identify What to Test

Ask yourself:
- **What behavior?** (e.g., "RX should accumulate 8 bytes")
- **What conditions?** (e.g., "When START symbol received")
- **What output?** (e.g., "64-bit word on source endpoint")
- **What edge cases?** (e.g., "Missing END symbol", "All-zero data")

### Step 2: Create Test File

```python
# test/dll/test_pipe_new_feature.py
"""
Tests for new PIPE feature.

Description of what this test file covers.

Reference: Relevant spec sections
"""

import unittest
from litepcie.dll.pipe import PIPEInterface

class TestNewFeature(unittest.TestCase):
    """Test new feature behavior."""

    def test_specific_aspect(self):
        """Test a specific aspect of the feature."""
        # Test implementation
        pass
```

### Step 3: Write Testbench

```python
def testbench(dut):
    """Testbench for specific aspect test."""
    # Phase 1: Reset/Initialize
    yield dut.input_signal.eq(0)
    yield

    # Phase 2: Apply Stimulus
    yield dut.input_signal.eq(test_value)
    yield

    # Phase 3: Wait for Processing
    for _ in range(expected_cycles):
        yield

    # Phase 4: Verify Outputs
    output = yield dut.output_signal
    self.assertEqual(output, expected_value, "Description of expectation")

    # Phase 5: Cleanup (if needed)
    yield dut.input_signal.eq(0)
    yield
```

### Step 4: Run and Debug

```bash
# Run new test
uv run pytest test/dll/test_pipe_new_feature.py -v

# If it fails, check VCD in temporary directory (manually save if needed)
# Or modify test to save VCD to specific location:
vcd_path = "debug_new_feature.vcd"  # Save to project root for inspection
run_simulation(dut, testbench(dut), vcd_name=vcd_path)

# View in GTKWave
gtkwave debug_new_feature.vcd
```

### Example: Testing a New Edge Case

Let's write a test for "RX should handle duplicate START symbols":

```python
def test_rx_duplicate_start_symbols(self):
    """
    RX should ignore duplicate START symbols.

    If multiple START symbols arrive consecutively without END,
    the RX should reset and start accumulating from the latest START.

    This could happen due to packet corruption or re-transmission.
    """

    def testbench(dut):
        # Send first START (STP)
        yield dut.pipe_rx_data.eq(0xFB)
        yield dut.pipe_rx_datak.eq(1)
        yield

        # Send 4 data bytes
        for byte_val in [0x11, 0x22, 0x33, 0x44]:
            yield dut.pipe_rx_data.eq(byte_val)
            yield dut.pipe_rx_datak.eq(0)
            yield

        # Send another START (should reset accumulation)
        yield dut.pipe_rx_data.eq(0xFB)
        yield dut.pipe_rx_datak.eq(1)
        yield

        # Send 8 data bytes (fresh packet)
        data_bytes = [0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF, 0x00, 0x11]
        for byte_val in data_bytes:
            yield dut.pipe_rx_data.eq(byte_val)
            yield dut.pipe_rx_datak.eq(0)
            yield

        # Send END
        yield dut.pipe_rx_data.eq(0xFD)
        yield dut.pipe_rx_datak.eq(1)
        yield

        # Check output (should be the second packet only)
        source_valid = yield dut.source.valid
        source_dat = yield dut.source.dat

        self.assertEqual(source_valid, 1)
        expected = 0x1100FFEEDDCCBBAA  # Little-endian
        self.assertEqual(source_dat, expected)

    dut = PIPERXDepacketizer()
    with tempfile.TemporaryDirectory(dir=".") as tmpdir:
        vcd_path = os.path.join(tmpdir, "test_duplicate_start.vcd")
        run_simulation(dut, testbench(dut), vcd_name=vcd_path)
```

---

## TDD Workflow

Test-Driven Development (TDD) is the recommended approach for PIPE development.

### RED-GREEN-REFACTOR Cycle

```
1. RED: Write failing test
   ↓
2. GREEN: Implement minimum code to pass
   ↓
3. REFACTOR: Clean up while keeping tests green
   ↓
4. COMMIT: Save working state
   ↓
(repeat)
```

### Example: Adding EDB (End Bad Packet) Support

**Step 1: RED - Write Failing Test**

```python
def test_tx_sends_edb_for_bad_packet(self):
    """TX should send EDB (0xFE) for packets marked as bad."""

    def testbench(dut):
        # Send packet marked as bad
        yield dut.sink.valid.eq(1)
        yield dut.sink.first.eq(1)
        yield dut.sink.last.eq(1)
        yield dut.sink.dat.eq(0x0123456789ABCDEF)
        yield dut.sink.error.eq(1)  # Mark as bad
        yield

        # Clear input
        yield dut.sink.valid.eq(0)
        yield

        # Skip START + 8 DATA bytes
        for _ in range(9):
            yield

        # Check END symbol (should be EDB, not END)
        tx_data = yield dut.pipe_tx_data
        tx_datak = yield dut.pipe_tx_datak
        self.assertEqual(tx_data, 0xFE, "Should send EDB for bad packet")
        self.assertEqual(tx_datak, 1)

    dut = PIPETXPacketizer()
    run_simulation(dut, testbench(dut))
```

**Run test (should FAIL):**
```bash
uv run pytest test/dll/test_pipe_tx_packetizer.py::TestPIPETXEDB::test_tx_sends_edb_for_bad_packet -v
# FAILED: AttributeError: 'sink' has no attribute 'error'
```

**Step 2: GREEN - Implement Feature**

```python
# In litepcie/dll/pipe.py PIPETXPacketizer.__init__()

# Add error signal to sink
self.sink = stream.Endpoint(phy_layout(64))
self.sink.error = Signal()  # Add error flag

# In FSM END state:
self.fsm.act(
    "END",
    # Send END or EDB based on error flag
    If(
        self.sink.error,
        NextValue(self.pipe_tx_data, PIPE_K30_7_EDB),  # Bad packet
    ).Else(
        NextValue(self.pipe_tx_data, PIPE_K29_7_END),  # Good packet
    ),
    NextValue(self.pipe_tx_datak, 1),
    NextState("IDLE"),
)
```

**Run test (should PASS):**
```bash
uv run pytest test/dll/test_pipe_tx_packetizer.py::TestPIPETXEDB::test_tx_sends_edb_for_bad_packet -v
# PASSED
```

**Step 3: REFACTOR - Clean Up**

- Add docstring explaining error handling
- Add constant for EDB if not already defined
- Ensure consistent naming conventions

**Step 4: COMMIT**

```bash
git add test/dll/test_pipe_tx_packetizer.py litepcie/dll/pipe.py
git commit -m "feat(pipe): Add EDB (End Bad Packet) support to TX packetizer"
```

---

## Debugging Tests

### Common Issues and Solutions

#### Issue 1: Test Times Out

**Symptom:** Test hangs or takes too long

**Causes:**
- Infinite loop in testbench
- Waiting for signal that never arrives
- FSM stuck in wrong state

**Solutions:**
```python
# Add timeout to simulation
run_simulation(dut, testbench(dut), clocks={"sys": 10}, timeout=1000)

# Add debug prints
def testbench(dut):
    for i in range(20):
        state = yield dut.fsm.state
        print(f"Cycle {i}: FSM state = {state}")
        yield
```

#### Issue 2: Assertion Failure

**Symptom:** `AssertionError: 0 != 1`

**Causes:**
- Timing issue (checking too early/late)
- Signal not propagating correctly
- Test expectations wrong

**Solutions:**
```python
# Check signal at each cycle
def testbench(dut):
    for cycle in range(15):
        rx_valid = yield dut.source.valid
        if rx_valid:
            rx_data = yield dut.source.dat
            print(f"Cycle {cycle}: Found valid output: 0x{rx_data:016X}")
            break
        yield
    else:
        self.fail("Never received valid output")
```

#### Issue 3: Data Mismatch

**Symptom:** `Expected 0x0123456789ABCDEF, got 0x0123456789ABCD00`

**Causes:**
- Byte ordering confusion (big-endian vs little-endian)
- Missing bytes in accumulation
- Buffer not fully written

**Solutions:**
```python
# Enable debug mode to inspect internal buffer
dut = PIPERXDepacketizer(debug=True)

def testbench(dut):
    # After each byte
    for i, byte_val in enumerate([0xEF, 0xCD, ...]):
        yield dut.pipe_rx_data.eq(byte_val)
        yield
        buffer = yield dut.debug_data_buffer
        print(f"After byte {i}: buffer = 0x{buffer:016X}")
```

### Using GTKWave for Debugging

**1. Generate VCD file:**
```python
run_simulation(dut, testbench(dut), vcd_name="debug.vcd")
```

**2. Open in GTKWave:**
```bash
gtkwave debug.vcd
```

**3. Add signals to watch:**
```
# For TX debugging:
- dll_tx_sink.valid
- dll_tx_sink.dat
- tx_packetizer.fsm.state
- pipe_tx_data
- pipe_tx_datak

# For RX debugging:
- pipe_rx_data
- pipe_rx_datak
- rx_depacketizer.fsm.state
- rx_depacketizer.debug_data_buffer (if debug=True)
- dll_rx_source.valid
- dll_rx_source.dat
```

**4. Look for:**
- FSM state transitions (are they correct?)
- Signal timing (are delays correct?)
- Data values (correct byte ordering?)
- K-character markers (datak high when expected?)

---

## Coverage Analysis

### Running Coverage

```bash
# Generate coverage for PIPE modules
uv run coverage run -m pytest test/dll/ test/phy/ -q
uv run coverage report -m --include="litepcie/dll/pipe.py,litepcie/phy/pipe_external_phy.py"

# Output shows:
# Name                                Stmts   Miss  Cover   Missing
# -----------------------------------------------------------------
# litepcie/dll/pipe.py                   77      1    99%   61
# litepcie/phy/pipe_external_phy.py      25      1    96%   180
```

### Interpreting Coverage

**High Coverage (95%+):** Good
- Most code paths tested
- Edge cases covered
- Error handling verified

**Medium Coverage (80-95%):** Acceptable
- Core functionality tested
- Some edge cases may be missing
- Review missed lines

**Low Coverage (<80%):** Needs Work
- Significant untested code
- Missing test cases
- Potential bugs lurking

### Improving Coverage

**1. Identify missed lines:**
```bash
uv run coverage report -m --include="litepcie/dll/pipe.py"
# Shows: litepcie/dll/pipe.py    77    1    99%   61
# Line 61 is not covered
```

**2. Examine missed line:**
```python
# Line 61 in pipe.py:
def pipe_layout_8b(data_width=8):
    return [  # <-- Line 61 is the return statement
        # ... layout definition
    ]
```

**3. Decide if test needed:**
- **Intentionally unused:** Document why (e.g., "Future multi-lane support")
- **Error path:** Add test to exercise it
- **Dead code:** Remove it

**4. Add test if needed:**
```python
def test_pipe_layout_8b_returns_correct_layout(self):
    """pipe_layout_8b() should return proper signal layout."""
    from litepcie.dll.pipe import pipe_layout_8b
    layout = pipe_layout_8b(data_width=8)
    # Verify layout structure
    self.assertIsInstance(layout, list)
    self.assertTrue(len(layout) > 0)
```

---

## Performance Testing

### Measuring Throughput

```python
def test_loopback_throughput(self):
    """Measure packets per second through loopback."""

    def testbench(dut):
        num_packets = 100
        start_cycle = 0
        end_cycle = 0

        # Record start
        start_cycle = (yield Tick())

        # Send packets
        for i in range(num_packets):
            yield dut.dll_tx_sink.valid.eq(1)
            yield dut.dll_tx_sink.dat.eq(i)
            yield
            yield dut.dll_tx_sink.valid.eq(0)

            # Wait for completion
            for _ in range(12):
                yield

        # Record end
        end_cycle = (yield Tick())

        total_cycles = end_cycle - start_cycle
        packets_per_cycle = num_packets / total_cycles
        print(f"Throughput: {packets_per_cycle:.4f} packets/cycle")
        print(f"Total cycles: {total_cycles}")

    dut = PIPEInterface(data_width=8, gen=1)
    # Loopback
    dut.comb += [
        dut.pipe_rx_data.eq(dut.pipe_tx_data),
        dut.pipe_rx_datak.eq(dut.pipe_tx_datak),
    ]
    run_simulation(dut, testbench(dut), clocks={"sys": 10})
```

### Measuring Latency

```python
def test_single_packet_latency(self):
    """Measure cycles from TX input to RX output."""

    def testbench(dut):
        # Send packet at cycle 0
        yield dut.dll_tx_sink.valid.eq(1)
        yield dut.dll_tx_sink.dat.eq(0x0123456789ABCDEF)
        start_cycle = 0
        yield

        yield dut.dll_tx_sink.valid.eq(0)
        yield

        # Wait for output and measure
        for cycle in range(1, 20):
            rx_valid = yield dut.dll_rx_source.valid
            if rx_valid:
                latency = cycle
                print(f"Latency: {latency} cycles")
                self.assertLessEqual(latency, 12, "Latency too high")
                break
            yield
        else:
            self.fail("Packet never received")

    dut = PIPEInterface(data_width=8, gen=1)
    # Loopback
    dut.comb += [
        dut.pipe_rx_data.eq(dut.pipe_tx_data),
        dut.pipe_rx_datak.eq(dut.pipe_tx_datak),
    ]
    run_simulation(dut, testbench(dut))
```

---

## Best Practices

### DO:

✅ **Write tests before implementation** (TDD)
✅ **Use descriptive test names** (`test_rx_ignores_invalid_k_characters`)
✅ **Document test purpose** in docstrings
✅ **Use temporary directories** for VCD files
✅ **Wait adequate cycles** for signal propagation
✅ **Clear inputs** after stimulus to prevent re-triggering
✅ **Test edge cases** (all-zero, all-ones, boundary conditions)
✅ **Check coverage** regularly
✅ **Commit after each passing test**

### DON'T:

❌ **Skip test documentation** (future you will be confused)
❌ **Hardcode magic numbers** (use constants like `PIPE_K27_7_STP`)
❌ **Leave VCD files** in project directory
❌ **Test multiple things** in one test (keep tests focused)
❌ **Ignore test failures** ("it works on my machine")
❌ **Write tests without running them**
❌ **Copy-paste tests** without adapting them

---

## References

- **PIPE Implementation:** `litepcie/dll/pipe.py`
- **Test Examples:** `test/dll/test_pipe_*.py`
- **User Guide:** `docs/guides/pipe-interface-guide.md`
- **Architecture:** `docs/architecture/pipe-architecture.md`
- **Integration Examples:** `docs/guides/pipe-integration-examples.md`
- **Intel PIPE 3.0 Specification**
- **PCIe Base Spec 4.0, Section 4: Physical Layer**

---

## Version History

- **1.0 (2025-10-17):** Initial testing guide with TDD workflow, debugging tips, and performance testing
