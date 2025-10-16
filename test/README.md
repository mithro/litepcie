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

## Test-Driven Development (TDD)

We follow TDD for all new features:

1. **Write failing test** that describes desired behavior
2. **Run test** to verify it fails (RED)
3. **Write minimal code** to make test pass (GREEN)
4. **Refactor** while keeping tests passing (REFACTOR)
5. **Repeat** for next feature

Example:

```python
# Step 1: Write failing test
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

# Step 2: Run test → FAIL (modules don't exist yet)

# Step 3: Implement minimal code to pass

# Step 4: Refactor and improve

# Step 5: Next test
```

## Philosophy: Test Behavior, Not Structure

### BAD (tests internal structure):
```python
def test_ack_dllp_creation(self):
    dut = DLLPAck(seq_num=42)
    type_val = (yield dut.type)
    self.assertEqual(type_val, DLLP_TYPE_ACK)  # Just checks a constant
```

### GOOD (tests actual behavior):
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

The good test verifies **what the system does** (ACK clears retry buffer),
not **how it's implemented** (checking internal type fields).

## Compliance Testing

In addition to functional tests, we include compliance tests that map directly
to PCIe Base Specification requirements:

```python
# test/dll/compliance/test_spec_3_3.py
class TestPCIeSpec3_3_DLL(unittest.TestCase):
    """Tests for PCIe Base Spec Section 3.3: Data Link Layer"""

    def test_spec_3_3_5_sequence_numbers(self):
        """
        PCIe Spec 3.3.5: Sequence numbers shall be 12 bits (0-4095).
        """
        dut = SequenceNumberManager()
        # ... test that sequence numbers wrap at 4096

    def test_spec_3_3_7_retry_buffer_requirement(self):
        """
        PCIe Spec 3.3.7: Retry buffer shall store TLPs until ACK received.
        """
        # ... test retry buffer stores and releases on ACK
```

These tests ensure our implementation conforms to the PCIe specification.

## Questions?

Open an issue or see `CONTRIBUTING.md` for more information.
