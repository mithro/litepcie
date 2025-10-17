# Phase 5: Ordered Sets & Link Training Implementation Plan

> **For Claude:** Use `${SUPERPOWERS_SKILLS_ROOT}/skills/collaboration/executing-plans/SKILL.md` to implement this plan task-by-task.

**Date:** 2025-10-17
**Status:** COMPLETE ✅
**Goal:** Implement SKP ordered set handling for clock compensation and basic TS1/TS2 ordered set structure, laying the foundation for link training.

**Architecture:** Extend the PIPE TX/RX paths to generate and detect SKP ordered sets periodically for clock compensation. Add TS1/TS2 ordered set structures (without full LTSSM). These ordered sets are multi-symbol sequences with specific patterns defined by PCIe spec. SKP is inserted every 1180-1538 symbols to maintain clock synchronization between link partners.

**Tech Stack:** Migen/LiteX, pytest + pytest-cov, Python 3.11+

**Context:**
- Phase 4 complete: PIPE interface with functional TX/RX data paths
- TX/RX handle packet framing (START/DATA/END) but don't insert SKP or handle TS1/TS2
- K-characters defined: SKP (0x1C), STP (0xFB), SDP (0x5C), END (0xFD), EDB (0xFE)
- RX currently ignores SKP and other ordered sets
- No link training state machine yet (future phase)

**Scope Note:** Phase 5 focuses on ordered set generation/detection mechanics, not full link training. Full LTSSM (Link Training and Status State Machine) will come in Phase 6.

---

## Task 5.1: SKP Ordered Set - TX Generation

Implement SKP ordered set generation in TX path for clock compensation.

**Files:**
- Modify: `litepcie/dll/pipe.py` (PIPETXPacketizer class)
- Create: `test/dll/test_pipe_skp.py`

### Step 1: Write failing test for SKP generation structure

Create test file for SKP ordered sets:

```python
# test/dll/test_pipe_skp.py
#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Tests for PIPE SKP ordered set handling.

SKP (Skip) ordered sets are used for clock compensation between
link partners with slightly different clock frequencies.

Reference: PCIe Base Spec 4.0, Section 4.2.7: Clock Compensation
"""

import os
import tempfile
import unittest

from litex.gen import run_simulation
from migen import *

from litepcie.dll.pipe import PIPETXPacketizer


class TestPIPETXSKPGeneration(unittest.TestCase):
    """Test SKP ordered set generation in TX path."""

    def test_tx_has_skp_generation_capability(self):
        """
        TX packetizer should have SKP generation capability.

        SKP Ordered Set Format (Gen1/Gen2):
        - Symbol 0: COM (K28.5, 0xBC) with K=1
        - Symbol 1: SKP (K28.0, 0x1C) with K=1
        - Symbol 2: SKP (K28.0, 0x1C) with K=1
        - Symbol 3: SKP (K28.0, 0x1C) with K=1

        Reference: PCIe Spec 4.0, Section 4.2.7.1
        """
        dut = PIPETXPacketizer(enable_skp=True)

        # Should have SKP generation control
        self.assertTrue(hasattr(dut, "skp_counter"))
        self.assertTrue(hasattr(dut, "skp_interval"))


if __name__ == "__main__":
    unittest.main()
```

### Step 2: Run test to verify it fails

Run: `pytest test/dll/test_pipe_skp.py::TestPIPETXSKPGeneration -v`

Expected: FAIL with "PIPETXPacketizer() got an unexpected keyword argument 'enable_skp'"

### Step 3: Add SKP generation parameters to TX packetizer

Modify PIPETXPacketizer.__init__() in litepcie/dll/pipe.py:

```python
# Around line 148, modify __init__ signature:
def __init__(self, enable_skp=False, skp_interval=1180):
    """
    PIPE TX packetizer (DLL packets → PIPE symbols).

    Parameters
    ----------
    enable_skp : bool, optional
        Enable SKP ordered set generation for clock compensation (default: False)
    skp_interval : int, optional
        Number of symbols between SKP ordered sets (default: 1180)
        PCIe spec requires SKP every 1180-1538 symbols

    ...
    """
    # DLL-facing input (64-bit packets)
    self.sink = stream.Endpoint(phy_layout(64))

    # PIPE-facing output (8-bit symbols)
    self.pipe_tx_data = Signal(8)
    self.pipe_tx_datak = Signal()

    # # #

    # SKP generation (if enabled)
    self.enable_skp = enable_skp
    if enable_skp:
        self.skp_counter = Signal(max=skp_interval+1)
        self.skp_interval = skp_interval

    # ... rest of existing code
```

### Step 4: Run test to verify it passes

Run: `pytest test/dll/test_pipe_skp.py::TestPIPETXSKPGeneration -v`

Expected: PASS

### Step 5: Commit SKP generation foundation

```bash
git add litepcie/dll/pipe.py test/dll/test_pipe_skp.py
git commit -m "feat(pipe): Add SKP generation capability to TX packetizer

Add optional SKP ordered set generation for clock compensation:
- enable_skp parameter to enable SKP generation
- skp_interval parameter (default 1180 symbols)
- Foundation for automatic SKP insertion

SKP generation logic to be implemented in next task.

References:
- PCIe Spec 4.0, Section 4.2.7: Clock Compensation

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 5.2: SKP Ordered Set - TX Insertion Logic

Implement SKP insertion at correct intervals.

**Files:**
- Modify: `litepcie/dll/pipe.py` (PIPETXPacketizer FSM)
- Modify: `test/dll/test_pipe_skp.py` (add behavioral test)

### Step 1: Write failing test for SKP insertion

Add to test/dll/test_pipe_skp.py:

```python
class TestPIPETXSKPInsertion(unittest.TestCase):
    """Test SKP insertion behavior."""

    def test_tx_inserts_skp_at_interval(self):
        """
        TX should insert SKP ordered set every N symbols.

        SKP Ordered Set (4 symbols):
        1. COM (0xBC, K=1)
        2. SKP (0x1C, K=1)
        3. SKP (0x1C, K=1)
        4. SKP (0x1C, K=1)

        Test with small interval (16 symbols) for quick verification.
        """
        def testbench(dut):
            # Wait for first SKP insertion (should happen at IDLE)
            for _ in range(20):
                yield

            # Check for COM symbol (start of SKP ordered set)
            tx_data = yield dut.pipe_tx_data
            tx_datak = yield dut.pipe_tx_datak

            if tx_data == 0xBC and tx_datak == 1:
                # Found COM, check next 3 symbols are SKP
                yield
                skp1_data = yield dut.pipe_tx_data
                skp1_datak = yield dut.pipe_tx_datak
                self.assertEqual(skp1_data, 0x1C, "Symbol 1 should be SKP")
                self.assertEqual(skp1_datak, 1, "Symbol 1 should be K-char")

                yield
                skp2_data = yield dut.pipe_tx_data
                skp2_datak = yield dut.pipe_tx_datak
                self.assertEqual(skp2_data, 0x1C, "Symbol 2 should be SKP")
                self.assertEqual(skp2_datak, 1, "Symbol 2 should be K-char")

                yield
                skp3_data = yield dut.pipe_tx_data
                skp3_datak = yield dut.pipe_tx_datak
                self.assertEqual(skp3_data, 0x1C, "Symbol 3 should be SKP")
                self.assertEqual(skp3_datak, 1, "Symbol 3 should be K-char")
            else:
                self.fail("Did not find SKP ordered set in expected window")

        # Use small interval for testing
        dut = PIPETXPacketizer(enable_skp=True, skp_interval=16)
        with tempfile.TemporaryDirectory(dir=".") as tmpdir:
            vcd_path = os.path.join(tmpdir, "test_skp_insertion.vcd")
            run_simulation(dut, testbench(dut), vcd_name=vcd_path)


if __name__ == "__main__":
    unittest.main()
```

### Step 2: Run test to verify it fails

Run: `pytest test/dll/test_pipe_skp.py::TestPIPETXSKPInsertion -v`

Expected: FAIL (no SKP insertion logic yet)

### Step 3: Implement SKP insertion FSM logic

Modify PIPETXPacketizer FSM in litepcie/dll/pipe.py:

```python
# After FSM definition (around line 170), add SKP state and logic:

# SKP symbol counter (if enabled)
if enable_skp:
    self.sync += [
        If(self.fsm.ongoing("IDLE") | self.fsm.ongoing("END"),
            # Increment counter when not actively sending packet
            If(self.skp_counter < skp_interval,
                self.skp_counter.eq(self.skp_counter + 1),
            ).Else(
                # Reset counter, will insert SKP
                self.skp_counter.eq(0),
            )
        ).Elif(self.fsm.ongoing("SKP"),
            # Don't increment during SKP transmission
            self.skp_counter.eq(self.skp_counter),
        )
    ]

    # SKP ordered set counter (0-3 for 4 symbols)
    skp_symbol_counter = Signal(2)

# Modify IDLE state to transition to SKP:
self.fsm.act(
    "IDLE",
    # Check if SKP needs to be inserted
    *([If(enable_skp & (self.skp_counter >= skp_interval),
        NextState("SKP")
    ).Else(] if enable_skp else []),
        # When packet starts, transition to START and output START symbol
        If(
            self.sink.valid & self.sink.first,
            If(
                is_dllp,
                # DLLP: Send SDP (0x5C, K=1)
                NextValue(self.pipe_tx_data, PIPE_K28_2_SDP),
                NextValue(self.pipe_tx_datak, 1),
            ).Else(
                # TLP: Send STP (0xFB, K=1)
                NextValue(self.pipe_tx_data, PIPE_K27_7_STP),
                NextValue(self.pipe_tx_datak, 1),
            ),
            NextValue(byte_counter, 0),
            NextState("DATA"),
        ).Else(
            # Default: output idle (data=0, K=0)
            NextValue(self.pipe_tx_data, 0x00),
            NextValue(self.pipe_tx_datak, 0),
        ),
    *([)] if enable_skp else []),
)

# Add SKP state (if enabled)
if enable_skp:
    self.fsm.act(
        "SKP",
        # Send SKP ordered set: COM, SKP, SKP, SKP
        Case(
            skp_symbol_counter,
            {
                0: [  # COM symbol
                    NextValue(self.pipe_tx_data, PIPE_K28_5_COM),
                    NextValue(self.pipe_tx_datak, 1),
                ],
                1: [  # SKP symbol
                    NextValue(self.pipe_tx_data, PIPE_K28_0_SKP),
                    NextValue(self.pipe_tx_datak, 1),
                ],
                2: [  # SKP symbol
                    NextValue(self.pipe_tx_data, PIPE_K28_0_SKP),
                    NextValue(self.pipe_tx_datak, 1),
                ],
                3: [  # SKP symbol
                    NextValue(self.pipe_tx_data, PIPE_K28_0_SKP),
                    NextValue(self.pipe_tx_datak, 1),
                ],
            },
        ),
        NextValue(skp_symbol_counter, skp_symbol_counter + 1),

        # After 4 symbols, return to IDLE
        If(
            skp_symbol_counter == 3,
            NextValue(skp_symbol_counter, 0),
            NextState("IDLE"),
        ),
    )
```

### Step 4: Run test to verify it passes

Run: `pytest test/dll/test_pipe_skp.py::TestPIPETXSKPInsertion -v`

Expected: PASS

### Step 5: Commit SKP insertion logic

```bash
git add litepcie/dll/pipe.py test/dll/test_pipe_skp.py
git commit -m "feat(pipe): Implement SKP ordered set insertion in TX path

Add automatic SKP insertion for clock compensation:
- SKP counter tracks symbols transmitted
- Inserts SKP ordered set (COM + 3xSKP) at configured interval
- SKP state in FSM handles 4-symbol sequence
- Defaults to 1180 symbols between SKP (PCIe spec minimum)

SKP helps maintain clock sync between link partners.

References:
- PCIe Spec 4.0, Section 4.2.7.1: SKP Ordered Set

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 5.3: SKP Ordered Set - RX Detection

Implement SKP detection and removal in RX path.

**Files:**
- Modify: `litepcie/dll/pipe.py` (PIPERXDepacketizer class)
- Modify: `test/dll/test_pipe_skp.py` (add RX test)

### Step 1: Write failing test for SKP detection

Add to test/dll/test_pipe_skp.py:

```python
class TestPIPERXSKPDetection(unittest.TestCase):
    """Test SKP detection and handling in RX path."""

    def test_rx_detects_and_skips_skp_ordered_set(self):
        """
        RX should detect SKP ordered set and skip it (not output to DLL).

        SKP is transparent to upper layers - inserted/removed by Physical Layer.

        Reference: PCIe Spec 4.0, Section 4.2.7.2
        """
        def testbench(dut):
            # Send SKP ordered set: COM + 3xSKP
            # Symbol 0: COM
            yield dut.pipe_rx_data.eq(0xBC)  # COM
            yield dut.pipe_rx_datak.eq(1)
            yield

            # Symbols 1-3: SKP
            for _ in range(3):
                yield dut.pipe_rx_data.eq(0x1C)  # SKP
                yield dut.pipe_rx_datak.eq(1)
                yield

            # After SKP, send a packet to verify normal operation resumes
            # START symbol
            yield dut.pipe_rx_data.eq(0xFB)  # STP
            yield dut.pipe_rx_datak.eq(1)
            yield

            # Data bytes
            for byte_val in [0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF, 0x11, 0x22]:
                yield dut.pipe_rx_data.eq(byte_val)
                yield dut.pipe_rx_datak.eq(0)
                yield

            # END symbol
            yield dut.pipe_rx_data.eq(0xFD)  # END
            yield dut.pipe_rx_datak.eq(1)
            yield
            yield  # One more cycle for output

            # Check that packet was received (SKP didn't interfere)
            source_valid = yield dut.source.valid
            self.assertEqual(source_valid, 1, "Should have packet output after SKP")

        dut = PIPERXDepacketizer()
        with tempfile.TemporaryDirectory(dir=".") as tmpdir:
            vcd_path = os.path.join(tmpdir, "test_rx_skp.vcd")
            run_simulation(dut, testbench(dut), vcd_name=vcd_path)


if __name__ == "__main__":
    unittest.main()
```

### Step 2: Run test to verify it fails

Run: `pytest test/dll/test_pipe_skp.py::TestPIPERXSKPDetection -v`

Expected: FAIL (SKP not handled, may cause incorrect operation)

### Step 3: Implement SKP detection in RX depacketizer

Modify PIPERXDepacketizer FSM in litepcie/dll/pipe.py (around line 300):

```python
# In IDLE state, add SKP detection:
self.fsm.act(
    "IDLE",
    # Wait for START symbol or SKP ordered set
    If(
        self.pipe_rx_datak,
        If(
            self.pipe_rx_data == PIPE_K27_7_STP,
            # STP: TLP start detected
            NextValue(is_tlp, 1),
            NextValue(byte_counter, 0),  # Reset counter
            NextState("DATA"),
        ).Elif(
            self.pipe_rx_data == PIPE_K28_2_SDP,
            # SDP: DLLP start detected
            NextValue(is_tlp, 0),
            NextValue(byte_counter, 0),  # Reset counter
            NextState("DATA"),
        ).Elif(
            self.pipe_rx_data == PIPE_K28_5_COM,
            # COM: Possible SKP ordered set, transition to SKP_CHECK
            NextState("SKP_CHECK"),
        ),
        # Ignore other K-characters
    ),
)

# Add SKP_CHECK state to verify it's actually SKP ordered set:
skp_check_counter = Signal(2)  # Count 3 SKP symbols after COM

self.fsm.act(
    "SKP_CHECK",
    # Verify next 3 symbols are SKP
    If(
        self.pipe_rx_datak & (self.pipe_rx_data == PIPE_K28_0_SKP),
        # Valid SKP symbol
        NextValue(skp_check_counter, skp_check_counter + 1),
        If(
            skp_check_counter == 2,  # Received all 3 SKP symbols
            # Complete SKP ordered set detected, return to IDLE
            NextValue(skp_check_counter, 0),
            NextState("IDLE"),
        ),
    ).Else(
        # Not a valid SKP ordered set, return to IDLE
        # (May have been COM for different purpose)
        NextValue(skp_check_counter, 0),
        NextState("IDLE"),
    ),
)
```

### Step 4: Run test to verify it passes

Run: `pytest test/dll/test_pipe_skp.py::TestPIPERXSKPDetection -v`

Expected: PASS

### Step 5: Commit SKP detection

```bash
git add litepcie/dll/pipe.py test/dll/test_pipe_skp.py
git commit -m "feat(pipe): Implement SKP ordered set detection in RX path

Add SKP detection and transparent removal:
- Detect COM symbol (potential SKP start)
- Verify next 3 symbols are SKP (K28.0)
- Skip SKP ordered set (transparent to DLL)
- Resume normal operation after SKP

SKP removal maintains packet integrity while handling clock compensation.

References:
- PCIe Spec 4.0, Section 4.2.7.2: SKP Removal

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 5.4: SKP Integration Test

Test SKP generation and detection through complete TX→RX loopback.

**Files:**
- Modify: `test/dll/test_pipe_loopback.py` (add SKP test)

### Step 1: Write SKP loopback test

Add to test/dll/test_pipe_loopback.py:

```python
class TestPIPELoopbackWithSKP(unittest.TestCase):
    """Test loopback with SKP ordered set insertion."""

    def test_loopback_with_skp_insertion(self):
        """
        SKP ordered sets should be transparent to data transfer.

        TX inserts SKP periodically.
        RX removes SKP automatically.
        Data packets should pass through correctly.
        """
        def testbench(dut):
            # Send a packet
            test_data = 0x0123456789ABCDEF

            yield dut.dll_tx_sink.valid.eq(1)
            yield dut.dll_tx_sink.first.eq(1)
            yield dut.dll_tx_sink.last.eq(1)
            yield dut.dll_tx_sink.dat.eq(test_data)
            yield

            # Clear TX input
            yield dut.dll_tx_sink.valid.eq(0)

            # Wait for processing (may include SKP insertion)
            for _ in range(30):  # Extra cycles for potential SKP
                yield

            # Check RX output
            rx_valid = yield dut.dll_rx_source.valid
            rx_data = yield dut.dll_rx_source.dat

            self.assertEqual(rx_valid, 1, "RX should have valid output")
            self.assertEqual(
                rx_data,
                test_data,
                f"Data should pass through SKP: expected 0x{test_data:016X}, got 0x{rx_data:016X}",
            )

        # Create PIPE interface with SKP enabled (small interval for testing)
        dut = PIPEInterface(data_width=8, gen=1, enable_skp=True, skp_interval=12)

        # Loopback TX → RX
        dut.comb += [
            dut.pipe_rx_data.eq(dut.pipe_tx_data),
            dut.pipe_rx_datak.eq(dut.pipe_tx_datak),
        ]

        with tempfile.TemporaryDirectory(dir=".") as tmpdir:
            vcd_path = os.path.join(tmpdir, "test_loopback_skp.vcd")
            run_simulation(dut, testbench(dut), vcd_name=vcd_path)


if __name__ == "__main__":
    unittest.main()
```

### Step 2: Run test to verify it fails

Run: `pytest test/dll/test_pipe_loopback.py::TestPIPELoopbackWithSKP -v`

Expected: FAIL (PIPEInterface doesn't accept enable_skp parameter yet)

### Step 3: Add SKP parameters to PIPEInterface

Modify PIPEInterface.__init__() in litepcie/dll/pipe.py (around line 434):

```python
def __init__(self, data_width=8, gen=1, enable_skp=False, skp_interval=1180):
    """
    PIPE interface abstraction (MAC side).

    Parameters
    ----------
    data_width : int
        PIPE data width (8 for PIPE 3.0 8-bit mode)
    gen : int
        PCIe generation (1 for Gen1/2.5GT/s, 2 for Gen2/5.0GT/s)
    enable_skp : bool, optional
        Enable SKP ordered set generation/detection (default: False)
    skp_interval : int, optional
        Symbols between SKP ordered sets (default: 1180)

    ...
    """
    if data_width != 8:
        raise ValueError("Only 8-bit PIPE mode supported currently")
    if gen not in [1, 2]:
        raise ValueError("Only Gen1/Gen2 supported currently")

    # ... existing interface definitions ...

    # # #

    # TX Path: DLL packets → PIPE symbols
    self.submodules.tx_packetizer = tx_packetizer = PIPETXPacketizer(
        enable_skp=enable_skp,
        skp_interval=skp_interval,
    )

    # ... rest of existing code (no changes to RX, it auto-detects SKP) ...
```

### Step 4: Run test to verify it passes

Run: `pytest test/dll/test_pipe_loopback.py::TestPIPELoopbackWithSKP -v`

Expected: PASS

### Step 5: Commit SKP integration

```bash
git add litepcie/dll/pipe.py test/dll/test_pipe_loopback.py
git commit -m "feat(pipe): Integrate SKP handling in PIPE interface

Add SKP parameters to PIPEInterface:
- enable_skp flag passed to TX packetizer
- skp_interval configurable (default 1180)
- RX automatically detects and removes SKP
- Loopback test verifies transparent SKP handling

SKP ordered sets now fully functional for clock compensation.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 5.5: TS1/TS2 Ordered Set - Data Structures

Define TS1 and TS2 ordered set structures (without full LTSSM).

**Files:**
- Modify: `litepcie/dll/pipe.py` (add TS1/TS2 constants and structures)
- Create: `test/dll/test_pipe_training_sequences.py`

### Step 1: Write test for TS1/TS2 structures

Create test file:

```python
# test/dll/test_pipe_training_sequences.py
#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Tests for PIPE Training Sequence (TS1/TS2) ordered sets.

Training Sequences are used during link training for speed negotiation,
lane configuration, and link equalization.

Reference: PCIe Base Spec 4.0, Section 4.2.6: Ordered Sets
"""

import unittest

from litepcie.dll.pipe import (
    TS1OrderedSet,
    TS2OrderedSet,
    PIPE_K28_5_COM,
)


class TestTS1OrderedSet(unittest.TestCase):
    """Test TS1 ordered set structure."""

    def test_ts1_has_correct_structure(self):
        """
        TS1 ordered set has 16 symbols (Gen1/Gen2).

        Symbol 0: COM (K28.5)
        Symbols 1-15: Configuration data (link/lane numbers, etc.)

        Reference: PCIe Spec 4.0, Section 4.2.6.2
        """
        ts1 = TS1OrderedSet(
            link_number=0,
            lane_number=0,
            n_fts=128,  # Fast Training Sequence count
            rate_id=1,  # Gen1
        )

        self.assertEqual(len(ts1.symbols), 16, "TS1 should have 16 symbols")
        self.assertEqual(ts1.symbols[0], PIPE_K28_5_COM, "Symbol 0 should be COM")


class TestTS2OrderedSet(unittest.TestCase):
    """Test TS2 ordered set structure."""

    def test_ts2_has_correct_structure(self):
        """
        TS2 ordered set has 16 symbols (Gen1/Gen2).

        Same structure as TS1, but signifies later training stage.

        Reference: PCIe Spec 4.0, Section 4.2.6.3
        """
        ts2 = TS2OrderedSet(
            link_number=0,
            lane_number=0,
            n_fts=128,
            rate_id=1,
        )

        self.assertEqual(len(ts2.symbols), 16, "TS2 should have 16 symbols")
        self.assertEqual(ts2.symbols[0], PIPE_K28_5_COM, "Symbol 0 should be COM")


if __name__ == "__main__":
    unittest.main()
```

### Step 2: Run test to verify it fails

Run: `pytest test/dll/test_pipe_training_sequences.py -v`

Expected: FAIL with "cannot import name 'TS1OrderedSet'"

### Step 3: Implement TS1/TS2 data structures

Add to litepcie/dll/pipe.py (after K-character constants, around line 107):

```python
# Training Sequence Ordered Sets ------------------------------------------------------------

class TS1OrderedSet:
    """
    Training Sequence 1 (TS1) Ordered Set.

    Used during link training for speed negotiation, lane configuration,
    and equalization. TS1 is sent in early training stages.

    Parameters
    ----------
    link_number : int
        Link number (0-255)
    lane_number : int
        Lane number within link (0-31)
    n_fts : int
        Number of Fast Training Sequences for L0s exit (0-255)
    rate_id : int
        Data rate identifier (1=Gen1, 2=Gen2, etc.)

    Attributes
    ----------
    symbols : list of int
        16-symbol ordered set

    References
    ----------
    PCIe Base Spec 4.0, Section 4.2.6.2: TS1 Ordered Set
    """

    def __init__(self, link_number=0, lane_number=0, n_fts=128, rate_id=1):
        # Symbol 0: COM (always K28.5)
        self.symbols = [PIPE_K28_5_COM]

        # Symbol 1: Link number
        self.symbols.append(link_number & 0xFF)

        # Symbol 2: Lane number
        self.symbols.append(lane_number & 0x1F)  # 5 bits

        # Symbol 3: N_FTS
        self.symbols.append(n_fts & 0xFF)

        # Symbol 4: Rate ID
        self.symbols.append(rate_id & 0x1F)

        # Symbols 5-6: Training Control
        # Bit 0: Hot Reset
        # Bit 1: Disable Link
        # Bit 2: Loopback
        # Bit 3: Disable Scrambling
        # Bits 4-5: Reserved
        self.symbols.append(0x00)  # Training Control byte 0
        self.symbols.append(0x00)  # Training Control byte 1

        # Symbols 7-14: TS1 Identifier (all D10.2 = 0x4A for TS1)
        for _ in range(8):
            self.symbols.append(0x4A)  # D10.2 identifies TS1

        # Symbol 15: TS1 Identifier (D10.2)
        self.symbols.append(0x4A)


class TS2OrderedSet:
    """
    Training Sequence 2 (TS2) Ordered Set.

    Used during link training after TS1 exchange. TS2 signifies
    later training stages and configuration lock.

    Parameters
    ----------
    link_number : int
        Link number (0-255)
    lane_number : int
        Lane number within link (0-31)
    n_fts : int
        Number of Fast Training Sequences for L0s exit (0-255)
    rate_id : int
        Data rate identifier (1=Gen1, 2=Gen2, etc.)

    Attributes
    ----------
    symbols : list of int
        16-symbol ordered set

    References
    ----------
    PCIe Base Spec 4.0, Section 4.2.6.3: TS2 Ordered Set
    """

    def __init__(self, link_number=0, lane_number=0, n_fts=128, rate_id=1):
        # Structure identical to TS1, except identifier symbols

        # Symbol 0: COM (always K28.5)
        self.symbols = [PIPE_K28_5_COM]

        # Symbols 1-6: Same as TS1
        self.symbols.append(link_number & 0xFF)
        self.symbols.append(lane_number & 0x1F)
        self.symbols.append(n_fts & 0xFF)
        self.symbols.append(rate_id & 0x1F)
        self.symbols.append(0x00)  # Training Control byte 0
        self.symbols.append(0x00)  # Training Control byte 1

        # Symbols 7-15: TS2 Identifier (all D5.2 = 0x45 for TS2)
        for _ in range(9):
            self.symbols.append(0x45)  # D5.2 identifies TS2
```

### Step 4: Run test to verify it passes

Run: `pytest test/dll/test_pipe_training_sequences.py -v`

Expected: PASS

### Step 5: Commit TS1/TS2 structures

```bash
git add litepcie/dll/pipe.py test/dll/test_pipe_training_sequences.py
git commit -m "feat(pipe): Add TS1/TS2 ordered set data structures

Add Training Sequence ordered set structures:
- TS1OrderedSet: Early link training stage
- TS2OrderedSet: Later training stage (after TS1 exchange)
- 16-symbol format with COM + configuration data
- Link/lane numbers, N_FTS, rate ID support
- TS1 uses D10.2 (0x4A) identifier
- TS2 uses D5.2 (0x45) identifier

Foundation for link training implementation (future phase).

References:
- PCIe Spec 4.0, Section 4.2.6: Ordered Sets

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 5.6: TS1/TS2 TX Generation (Basic)

Add ability to generate TS1/TS2 ordered sets (manual trigger, not LTSSM).

**Files:**
- Modify: `litepcie/dll/pipe.py` (add TS generation to TX packetizer)
- Modify: `test/dll/test_pipe_training_sequences.py` (add generation test)

### Step 1: Write test for TS1 generation

Add to test/dll/test_pipe_training_sequences.py:

```python
import os
import tempfile

from litex.gen import run_simulation
from migen import *

from litepcie.dll.pipe import PIPETXPacketizer


class TestTS1Generation(unittest.TestCase):
    """Test TS1 generation in TX path."""

    def test_tx_can_generate_ts1(self):
        """
        TX should be able to generate TS1 ordered set on command.

        TS1 is 16 symbols starting with COM.
        """
        def testbench(dut):
            # Trigger TS1 generation
            yield dut.send_ts1.eq(1)
            yield
            yield dut.send_ts1.eq(0)

            # Check for COM symbol (TS1 start)
            yield
            tx_data = yield dut.pipe_tx_data
            tx_datak = yield dut.pipe_tx_datak
            self.assertEqual(tx_data, 0xBC, "Symbol 0 should be COM")
            self.assertEqual(tx_datak, 1, "Symbol 0 should be K-character")

            # Check next 15 symbols (don't validate specific values yet)
            for i in range(15):
                yield
                tx_datak = yield dut.pipe_tx_datak
                self.assertEqual(tx_datak, 0, f"Symbol {i+1} should be data (K=0)")

        dut = PIPETXPacketizer(enable_training_sequences=True)
        with tempfile.TemporaryDirectory(dir=".") as tmpdir:
            vcd_path = os.path.join(tmpdir, "test_ts1_gen.vcd")
            run_simulation(dut, testbench(dut), vcd_name=vcd_path)


if __name__ == "__main__":
    unittest.main()
```

### Step 2: Run test to verify it fails

Run: `pytest test/dll/test_pipe_training_sequences.py::TestTS1Generation -v`

Expected: FAIL (enable_training_sequences parameter doesn't exist)

### Step 3: Add TS generation capability to TX packetizer

Modify PIPETXPacketizer.__init__() in litepcie/dll/pipe.py:

```python
def __init__(self, enable_skp=False, skp_interval=1180, enable_training_sequences=False):
    """
    PIPE TX packetizer (DLL packets → PIPE symbols).

    Parameters
    ----------
    enable_skp : bool, optional
        Enable SKP ordered set generation for clock compensation (default: False)
    skp_interval : int, optional
        Number of symbols between SKP ordered sets (default: 1180)
    enable_training_sequences : bool, optional
        Enable TS1/TS2 generation capability (default: False)

    ...
    """
    # ... existing code ...

    # Training sequence generation (if enabled)
    if enable_training_sequences:
        self.send_ts1 = Signal()
        self.send_ts2 = Signal()
        self.ts1_data = TS1OrderedSet(link_number=0, lane_number=0)
        self.ts2_data = TS2OrderedSet(link_number=0, lane_number=0)

        # TS symbol counter (0-15 for 16 symbols)
        ts_symbol_counter = Signal(4)

        # Current TS being sent (1=TS1, 2=TS2)
        ts_type = Signal(2)

    # ... existing FSM code ...
```

### Step 4: Add TS generation FSM logic

Modify FSM in PIPETXPacketizer (in IDLE state and add TS state):

```python
# Modify IDLE state to handle TS generation:
self.fsm.act(
    "IDLE",
    # Check for TS generation request (highest priority)
    *([If(enable_training_sequences & self.send_ts1,
        NextValue(ts_type, 1),
        NextValue(ts_symbol_counter, 0),
        NextState("TS"),
    ).Elif(enable_training_sequences & self.send_ts2,
        NextValue(ts_type, 2),
        NextValue(ts_symbol_counter, 0),
        NextState("TS"),
    ).Else(] if enable_training_sequences else []),
        # SKP check
        *([If(enable_skp & (self.skp_counter >= skp_interval),
            NextState("SKP")
        ).Else(] if enable_skp else []),
            # Normal packet handling
            If(
                self.sink.valid & self.sink.first,
                # ... existing START logic ...
            ).Else(
                # Default: output idle
                NextValue(self.pipe_tx_data, 0x00),
                NextValue(self.pipe_tx_datak, 0),
            ),
        *([)] if enable_skp else []),
    *([)] if enable_training_sequences else []),
)

# Add TS state (if enabled):
if enable_training_sequences:
    # Create symbol arrays for TS1/TS2
    ts1_symbols = Array([Signal(8, reset=sym) for sym in self.ts1_data.symbols])
    ts2_symbols = Array([Signal(8, reset=sym) for sym in self.ts2_data.symbols])

    self.fsm.act(
        "TS",
        # Output current symbol from TS1 or TS2
        If(
            ts_type == 1,  # TS1
            NextValue(self.pipe_tx_data, ts1_symbols[ts_symbol_counter]),
        ).Elif(
            ts_type == 2,  # TS2
            NextValue(self.pipe_tx_data, ts2_symbols[ts_symbol_counter]),
        ),

        # Symbol 0 (COM) is K-character, rest are data
        NextValue(self.pipe_tx_datak, 1 if ts_symbol_counter == 0 else 0),

        NextValue(ts_symbol_counter, ts_symbol_counter + 1),

        # After 16 symbols, return to IDLE
        If(
            ts_symbol_counter == 15,
            NextValue(ts_symbol_counter, 0),
            NextState("IDLE"),
        ),
    )
```

### Step 5: Run test to verify it passes

Run: `pytest test/dll/test_pipe_training_sequences.py::TestTS1Generation -v`

Expected: PASS

### Step 6: Commit TS generation

```bash
git add litepcie/dll/pipe.py test/dll/test_pipe_training_sequences.py
git commit -m "feat(pipe): Add TS1/TS2 generation capability to TX packetizer

Add Training Sequence generation:
- send_ts1/send_ts2 control signals
- TS state in FSM transmits 16-symbol sequences
- Symbol arrays for TS1/TS2 data
- COM symbol (K-character) followed by 15 data symbols

Foundation for link training state machine (future phase).

References:
- PCIe Spec 4.0, Section 4.2.6: Training Sequences

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 5.7: TS1/TS2 RX Detection (Basic)

Add ability to detect TS1/TS2 ordered sets in RX path.

**Files:**
- Modify: `litepcie/dll/pipe.py` (add TS detection to RX depacketizer)
- Modify: `test/dll/test_pipe_training_sequences.py` (add detection test)

### Step 1: Write test for TS1 detection

Add to test/dll/test_pipe_training_sequences.py:

```python
from litepcie.dll.pipe import PIPERXDepacketizer


class TestTS1Detection(unittest.TestCase):
    """Test TS1 detection in RX path."""

    def test_rx_detects_ts1(self):
        """
        RX should detect TS1 ordered set and set flag.

        TS1 detection is first step in link training response.
        """
        def testbench(dut):
            # Create TS1 to send
            ts1 = TS1OrderedSet(link_number=0, lane_number=0)

            # Send TS1 symbols
            for i, symbol in enumerate(ts1.symbols):
                yield dut.pipe_rx_data.eq(symbol)
                yield dut.pipe_rx_datak.eq(1 if i == 0 else 0)  # COM is K-char
                yield

            # Check detection flag
            yield
            ts1_detected = yield dut.ts1_detected
            self.assertEqual(ts1_detected, 1, "Should detect TS1 ordered set")

        dut = PIPERXDepacketizer(enable_training_sequences=True)
        with tempfile.TemporaryDirectory(dir=".") as tmpdir:
            vcd_path = os.path.join(tmpdir, "test_ts1_detect.vcd")
            run_simulation(dut, testbench(dut), vcd_name=vcd_path)


if __name__ == "__main__":
    unittest.main()
```

### Step 2: Run test to verify it fails

Run: `pytest test/dll/test_pipe_training_sequences.py::TestTS1Detection -v`

Expected: FAIL (enable_training_sequences parameter doesn't exist)

### Step 3: Add TS detection capability to RX depacketizer

Modify PIPERXDepacketizer.__init__() in litepcie/dll/pipe.py:

```python
def __init__(self, debug=False, enable_training_sequences=False):
    """
    PIPE RX depacketizer (PIPE symbols → DLL packets).

    Parameters
    ----------
    debug : bool, optional
        Enable debug signals for testing (default: False)
    enable_training_sequences : bool, optional
        Enable TS1/TS2 detection capability (default: False)

    ...
    """
    # ... existing code ...

    # Training sequence detection (if enabled)
    if enable_training_sequences:
        self.ts1_detected = Signal()
        self.ts2_detected = Signal()

        # TS symbol buffer (store 16 symbols for detection)
        ts_buffer = Array([Signal(8) for _ in range(16)])
        ts_buffer_counter = Signal(4)  # 0-15

    # ... existing FSM code ...
```

### Step 4: Add TS detection FSM logic

Modify FSM in PIPERXDepacketizer to detect TS patterns:

```python
# Add TS_CHECK state for TS1/TS2 detection:
if enable_training_sequences:
    # Clear detection flags when not actively detecting
    self.sync += [
        If(~self.fsm.ongoing("TS_CHECK"),
            self.ts1_detected.eq(0),
            self.ts2_detected.eq(0),
        )
    ]

    self.fsm.act(
        "TS_CHECK",
        # Accumulate symbols into buffer
        NextValue(ts_buffer[ts_buffer_counter], self.pipe_rx_data),
        NextValue(ts_buffer_counter, ts_buffer_counter + 1),

        # After 16 symbols, check if TS1 or TS2
        If(
            ts_buffer_counter == 15,
            # Check for TS1 identifier (D10.2 = 0x4A in symbols 7-15)
            If(
                (ts_buffer[7] == 0x4A) & (ts_buffer[8] == 0x4A) &
                (ts_buffer[9] == 0x4A) & (ts_buffer[10] == 0x4A),
                # TS1 detected
                self.ts1_detected.eq(1),
            ).Elif(
                # Check for TS2 identifier (D5.2 = 0x45 in symbols 7-15)
                (ts_buffer[7] == 0x45) & (ts_buffer[8] == 0x45) &
                (ts_buffer[9] == 0x45) & (ts_buffer[10] == 0x45),
                # TS2 detected
                self.ts2_detected.eq(1),
            ),

            NextValue(ts_buffer_counter, 0),
            NextState("IDLE"),
        ),
    )

# Modify IDLE state to transition to TS_CHECK when COM seen:
self.fsm.act(
    "IDLE",
    # Wait for START symbol, SKP, or potential TS
    If(
        self.pipe_rx_datak,
        If(
            self.pipe_rx_data == PIPE_K27_7_STP,
            # STP: TLP start
            NextValue(is_tlp, 1),
            NextValue(byte_counter, 0),
            NextState("DATA"),
        ).Elif(
            self.pipe_rx_data == PIPE_K28_2_SDP,
            # SDP: DLLP start
            NextValue(is_tlp, 0),
            NextValue(byte_counter, 0),
            NextState("DATA"),
        ).Elif(
            self.pipe_rx_data == PIPE_K28_5_COM,
            # COM: Could be SKP or TS, check next symbols
            *([If(enable_training_sequences,
                # Start buffering for TS detection
                NextValue(ts_buffer[0], PIPE_K28_5_COM),
                NextValue(ts_buffer_counter, 1),
                NextState("TS_CHECK"),
            ).Else(] if enable_training_sequences else []),
                # Just SKP handling (existing code)
                NextState("SKP_CHECK"),
            *([)] if enable_training_sequences else []),
        ),
    ),
)
```

### Step 5: Run test to verify it passes

Run: `pytest test/dll/test_pipe_training_sequences.py::TestTS1Detection -v`

Expected: PASS

### Step 6: Commit TS detection

```bash
git add litepcie/dll/pipe.py test/dll/test_pipe_training_sequences.py
git commit -m "feat(pipe): Add TS1/TS2 detection capability to RX depacketizer

Add Training Sequence detection:
- ts1_detected/ts2_detected output flags
- TS_CHECK state buffers 16 symbols
- Identifies TS1 by D10.2 (0x4A) pattern
- Identifies TS2 by D5.2 (0x45) pattern
- Distinguishes TS from SKP (both start with COM)

Foundation for link training state machine (future phase).

References:
- PCIe Spec 4.0, Section 4.2.6: Training Sequences

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 5.8: Run Full Test Suite

Verify all tests pass including new SKP and TS features.

**Files:**
- None (testing only)

### Step 1: Run all PIPE tests

Run: `pytest test/dll/test_pipe*.py test/phy/test_pipe*.py -v`

Expected: All tests PASS

### Step 2: Run with coverage

Run: `pytest test/dll/ --cov=litepcie/dll/pipe --cov-report=term-missing`

Expected: ≥85% coverage on pipe.py (may be lower due to optional features)

### Step 3: Run pre-commit hooks

Run: `pre-commit run --all-files`

Expected: All hooks pass (fix any issues)

### Step 4: Run full DLL test suite

Run: `pytest test/dll/ -v`

Expected: All tests PASS, no regressions

### Step 5: Document Phase 5 completion

Update docs/architecture/integration-strategy.md:

```markdown
### Phase 5: Ordered Sets & Link Training Foundation (Completed - 2025-10-17)
- Task 5.1: ✅ SKP ordered set TX generation structure
- Task 5.2: ✅ SKP TX insertion logic (automatic at intervals)
- Task 5.3: ✅ SKP RX detection and removal
- Task 5.4: ✅ SKP loopback integration test
- Task 5.5: ✅ TS1/TS2 data structures
- Task 5.6: ✅ TS1/TS2 TX generation (manual trigger)
- Task 5.7: ✅ TS1/TS2 RX detection
- Task 5.8: ✅ Full test suite validation

Phase 5 implemented ordered set foundations:
- SKP: Automatic generation every 1180 symbols, transparent removal
- TS1/TS2: 16-symbol Training Sequences with proper structure
- Manual TS generation and detection (no LTSSM yet)
- All features optional (backward compatible)
- Test coverage: XX new tests, all passing
```

Commit documentation:

```bash
git add docs/architecture/integration-strategy.md
git commit -m "docs: Update integration strategy with Phase 5 completion

Phase 5 complete: Ordered sets and training sequence foundations.
SKP clock compensation and TS1/TS2 structures implemented.
Full LTSSM (Link Training State Machine) deferred to Phase 6.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Phase 5 Summary

**Completed:**
- ✅ Task 5.1-5.2: SKP TX generation (automatic at configurable intervals)
- ✅ Task 5.3: SKP RX detection (transparent to DLL)
- ✅ Task 5.4: SKP integration testing (loopback verification)
- ✅ Task 5.5: TS1/TS2 ordered set data structures
- ✅ Task 5.6: TS1/TS2 TX generation (manual trigger)
- ✅ Task 5.7: TS1/TS2 RX detection (flag-based)
- ✅ Task 5.8: Full test suite validation

**Files Created/Modified:**
- `litepcie/dll/pipe.py` - Added SKP and TS1/TS2 capabilities
- `test/dll/test_pipe_skp.py` - SKP generation/detection tests
- `test/dll/test_pipe_training_sequences.py` - TS1/TS2 structure and behavior tests
- `test/dll/test_pipe_loopback.py` - SKP loopback integration test
- `docs/architecture/integration-strategy.md` - Phase 5 completion status

**Key Achievements:**
1. Clock compensation via SKP ordered sets (Gen1/Gen2 compliant)
2. Training Sequence structures (TS1/TS2) with proper format
3. Manual TS generation/detection (foundation for LTSSM)
4. All features optional and backward compatible
5. TDD approach maintained throughout

**Next Steps (Phase 6 - Link Training State Machine):**
- Implement LTSSM (Link Training and Status State Machine)
- Automatic TS1/TS2 exchange during link initialization
- Speed negotiation (Gen1/Gen2)
- Lane configuration (x1 support initially)
- Link up/down detection
- Integration with power management states

---

## Execution Notes

**Approach:**
- Test-driven development (write failing test first, then implement)
- Minimal implementation (just enough to pass tests)
- Frequent commits (after each passing test)
- All new features are optional (enable_skp, enable_training_sequences flags)
- Backward compatible with Phase 4

**Quality Gates:**
- All tests must pass before committing
- Pre-commit hooks must pass
- Coverage should remain ≥80% for core functionality
- PCIe spec references in comments

**Flexibility:**
- If tests reveal issues, fix before proceeding
- Plan can be adjusted if blockers discovered
- Some tasks can be parallelized (SKP and TS are independent)
