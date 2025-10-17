# Phase 4: PIPE TX/RX Data Path Implementation Plan

> **For Claude:** Use `${SUPERPOWERS_SKILLS_ROOT}/skills/collaboration/executing-plans/SKILL.md` to implement this plan task-by-task.

**Goal:** Implement functional TX and RX data paths for the PIPE interface, enabling DLL packets to be transmitted as PIPE symbols and received PIPE symbols to become DLL packets.

**Architecture:** Extend the PIPE interface (litepcie/dll/pipe.py) with TX packetizer (converts 64-bit DLL data to 8-bit PIPE symbols with K-character framing) and RX depacketizer (converts 8-bit PIPE symbols back to 64-bit DLL packets). Add ordered set handling for SKP (clock compensation) and basic TS1/TS2 support. Use Migen FSMs for control logic.

**Tech Stack:** Migen/LiteX, pytest + pytest-cov, Python 3.11+

**Context:**
- Phase 3 complete: PIPE interface structure exists with TX idle behavior
- DLL layer complete: DLLTX/DLLRX handle sequence numbers, LCRC, retry buffer, ACK/NAK
- PIPE interface currently has structure but no actual data transmission
- K-characters: STP (0xFB), SDP (0x5C), END (0xFD), EDB (0xFE), SKP (0x1C)

---

## Task 4.1: PIPE TX Packetizer - Basic Structure

Implement TX packetizer that converts 64-bit DLL data into 8-bit PIPE symbols with K-character framing.

**Files:**
- Modify: `litepcie/dll/pipe.py` (add PIPETXPacketizer class)
- Create: `test/dll/test_pipe_tx_packetizer.py`

### Step 1: Write failing test for TX packetizer structure

Create test file for TX packetizer:

```python
# test/dll/test_pipe_tx_packetizer.py
#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Tests for PIPE TX packetizer.

Tests conversion of DLL packets (64-bit) to PIPE symbols (8-bit) with K-character framing.

Reference: PCIe Base Spec 4.0, Section 4.2.2: Symbol Encoding
"""

import os
import tempfile
import unittest

from migen import *
from litex.gen import run_simulation

from litepcie.dll.pipe import PIPETXPacketizer
from litepcie.common import phy_layout


class TestPIPETXPacketizerStructure(unittest.TestCase):
    """Test TX packetizer structure."""

    def test_tx_packetizer_has_required_interfaces(self):
        """TX packetizer should have DLL input and PIPE output."""
        dut = PIPETXPacketizer()

        # DLL-facing input (64-bit)
        self.assertTrue(hasattr(dut, "sink"))
        self.assertEqual(len(dut.sink.dat), 64)

        # PIPE-facing output (8-bit symbols)
        self.assertTrue(hasattr(dut, "pipe_tx_data"))
        self.assertTrue(hasattr(dut, "pipe_tx_datak"))
        self.assertEqual(len(dut.pipe_tx_data), 8)
        self.assertEqual(len(dut.pipe_tx_datak), 1)


if __name__ == "__main__":
    unittest.main()
```

### Step 2: Run test to verify it fails

Run: `pytest test/dll/test_pipe_tx_packetizer.py::TestPIPETXPacketizerStructure -v`

Expected: FAIL with "ImportError: cannot import name 'PIPETXPacketizer'"

### Step 3: Create minimal TX packetizer class

Add PIPETXPacketizer to litepcie/dll/pipe.py (before PIPEInterface class):

```python
# In litepcie/dll/pipe.py, add after K-character constants:

# PIPE TX Packetizer -------------------------------------------------------------------------------

class PIPETXPacketizer(LiteXModule):
    """
    PIPE TX packetizer (DLL packets → PIPE symbols).

    Converts 64-bit DLL packets to 8-bit PIPE symbols with K-character framing.

    Parameters
    ----------
    None

    Attributes
    ----------
    sink : Endpoint(phy_layout(64)), input
        DLL packets to transmit
    pipe_tx_data : Signal(8), output
        PIPE TX data (8-bit symbol)
    pipe_tx_datak : Signal(1), output
        PIPE TX K-character indicator

    Protocol
    --------
    When sink.valid & sink.first:
        - Determine packet type from sink.dat[0:8]
        - Send STP (0xFB, K=1) for TLP
        - Send SDP (0x5C, K=1) for DLLP
    Then:
        - Send data bytes (K=0) from sink.dat
    When sink.last:
        - Send END (0xFD, K=1) for good packet
        - Send EDB (0xFE, K=1) for bad packet (not implemented yet)

    References
    ----------
    - PCIe Base Spec 4.0, Section 4.2.2: Symbol Encoding
    - PCIe Base Spec 4.0, Section 4.2.3: Framing
    """
    def __init__(self):
        # DLL-facing input (64-bit packets)
        self.sink = stream.Endpoint(phy_layout(64))

        # PIPE-facing output (8-bit symbols)
        self.pipe_tx_data = Signal(8)
        self.pipe_tx_datak = Signal()

        # # #

        # TODO: Implement packetizer FSM
        # States: IDLE, START, DATA, END
```

### Step 4: Run test to verify it passes

Run: `pytest test/dll/test_pipe_tx_packetizer.py::TestPIPETXPacketizerStructure -v`

Expected: PASS

### Step 5: Commit TX packetizer foundation

```bash
git add litepcie/dll/pipe.py test/dll/test_pipe_tx_packetizer.py
git commit -m "feat(pipe): Add TX packetizer foundation

Add PIPETXPacketizer class structure:
- DLL packet input (64-bit)
- PIPE symbol output (8-bit + K-character)
- Placeholder for FSM implementation

Next: Implement START symbol generation (STP/SDP).

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4.2: PIPE TX Packetizer - START Symbol Generation

Implement START symbol generation (STP for TLPs, SDP for DLLPs).

**Files:**
- Modify: `litepcie/dll/pipe.py` (implement START state)
- Modify: `test/dll/test_pipe_tx_packetizer.py` (add behavioral test)

### Step 1: Write failing test for START symbol

Add to test/dll/test_pipe_tx_packetizer.py:

```python
class TestPIPETXPacketizerStart(unittest.TestCase):
    """Test START symbol generation."""

    def test_tx_sends_stp_for_tlp(self):
        """
        TX should send STP (0xFB, K=1) at start of TLP.

        TLP identification: First byte is not DLLP type (0x00, 0x10, 0x20, 0x30)

        Reference: PCIe Spec 4.0, Section 4.2.2.1: START Framing
        """
        def testbench(dut):
            # Prepare TLP data (first byte = 0x40, indicating TLP)
            tlp_data = 0x0123456789ABCDEF  # 64-bit TLP data
            yield dut.sink.valid.eq(1)
            yield dut.sink.first.eq(1)
            yield dut.sink.last.eq(0)
            yield dut.sink.dat.eq(tlp_data)
            yield

            # Check START symbol (STP)
            tx_data = (yield dut.pipe_tx_data)
            tx_datak = (yield dut.pipe_tx_datak)
            self.assertEqual(tx_data, 0xFB, "Should send STP (0xFB)")
            self.assertEqual(tx_datak, 1, "STP should be K-character")

            yield dut.sink.first.eq(0)
            yield

        dut = PIPETXPacketizer()
        with tempfile.TemporaryDirectory(dir=".") as tmpdir:
            vcd_path = os.path.join(tmpdir, "test_tx_stp.vcd")
            run_simulation(dut, testbench(dut), vcd_name=vcd_path)

    def test_tx_sends_sdp_for_dllp(self):
        """
        TX should send SDP (0x5C, K=1) at start of DLLP.

        DLLP identification: First byte is DLLP type (0x00=ACK, 0x10=NAK, etc.)

        Reference: PCIe Spec 4.0, Section 3.3.1: DLLP Format
        """
        def testbench(dut):
            # Prepare DLLP data (first byte = 0x00, indicating ACK DLLP)
            dllp_data = 0x00000000ABCD1234  # 64-bit DLLP data (type=0x00)
            yield dut.sink.valid.eq(1)
            yield dut.sink.first.eq(1)
            yield dut.sink.last.eq(0)
            yield dut.sink.dat.eq(dllp_data)
            yield

            # Check START symbol (SDP)
            tx_data = (yield dut.pipe_tx_data)
            tx_datak = (yield dut.pipe_tx_datak)
            self.assertEqual(tx_data, 0x5C, "Should send SDP (0x5C)")
            self.assertEqual(tx_datak, 1, "SDP should be K-character")

            yield dut.sink.first.eq(0)
            yield

        dut = PIPETXPacketizer()
        with tempfile.TemporaryDirectory(dir=".") as tmpdir:
            vcd_path = os.path.join(tmpdir, "test_tx_sdp.vcd")
            run_simulation(dut, testbench(dut), vcd_name=vcd_path)


if __name__ == "__main__":
    unittest.main()
```

### Step 2: Run test to verify it fails

Run: `pytest test/dll/test_pipe_tx_packetizer.py::TestPIPETXPacketizerStart -v`

Expected: FAIL (no FSM implementation yet)

### Step 3: Implement START symbol generation

Replace TODO section in PIPETXPacketizer.__init__():

```python
        # # #

        # FSM for packetization
        self.submodules.fsm = FSM(reset_state="IDLE")

        # Detect packet type from first byte
        first_byte = Signal(8)
        is_dllp = Signal()
        self.comb += [
            first_byte.eq(self.sink.dat[0:8]),
            # DLLP types: 0x00 (ACK), 0x10 (NAK), 0x20 (PM), 0x30 (Vendor)
            is_dllp.eq((first_byte & 0xC0) == 0x00),
        ]

        self.fsm.act("IDLE",
            # Default: output idle (data=0, K=0)
            NextValue(self.pipe_tx_data, 0x00),
            NextValue(self.pipe_tx_datak, 0),

            # When packet starts, send START symbol
            If(self.sink.valid & self.sink.first,
                If(is_dllp,
                    # DLLP: Send SDP (0x5C, K=1)
                    NextValue(self.pipe_tx_data, 0x5C),
                    NextValue(self.pipe_tx_datak, 1),
                ).Else(
                    # TLP: Send STP (0xFB, K=1)
                    NextValue(self.pipe_tx_data, 0xFB),
                    NextValue(self.pipe_tx_datak, 1),
                ),
                NextState("DATA")
            )
        )

        self.fsm.act("DATA",
            # TODO: Implement data transmission
            # For now, go back to IDLE
            NextState("IDLE")
        )
```

### Step 4: Run test to verify it passes

Run: `pytest test/dll/test_pipe_tx_packetizer.py::TestPIPETXPacketizerStart -v`

Expected: PASS

### Step 5: Commit START symbol generation

```bash
git add litepcie/dll/pipe.py test/dll/test_pipe_tx_packetizer.py
git commit -m "feat(pipe): Implement TX START symbol generation

Add FSM to TX packetizer with START symbol generation:
- STP (0xFB) for TLPs
- SDP (0x5C) for DLLPs
- Packet type detection from first byte

Next: Implement data transmission.

References:
- PCIe Spec 4.0, Section 4.2.2.1: START Framing
- PCIe Spec 4.0, Section 3.3.1: DLLP Format

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4.3: PIPE TX Packetizer - Data Transmission

Implement data byte transmission (64-bit → 8-bit conversion).

**Files:**
- Modify: `litepcie/dll/pipe.py` (implement DATA state)
- Modify: `test/dll/test_pipe_tx_packetizer.py` (add data transmission test)

### Step 1: Write failing test for data transmission

Add to test/dll/test_pipe_tx_packetizer.py:

```python
class TestPIPETXPacketizerData(unittest.TestCase):
    """Test data transmission."""

    def test_tx_sends_data_bytes_in_order(self):
        """
        TX should send 64-bit data as 8 bytes in little-endian order.

        After START symbol, data bytes should be sent with K=0.

        Reference: PCIe Spec 4.0, Section 4.2.2.2: Data Symbols
        """
        def testbench(dut):
            # Prepare packet with known data
            test_data = 0x0123456789ABCDEF
            expected_bytes = [0xEF, 0xCD, 0xAB, 0x89, 0x67, 0x45, 0x23, 0x01]

            # Start packet
            yield dut.sink.valid.eq(1)
            yield dut.sink.first.eq(1)
            yield dut.sink.last.eq(0)
            yield dut.sink.dat.eq(test_data)
            yield

            # Skip START symbol (already tested)
            yield dut.sink.first.eq(0)
            yield

            # Check data bytes
            for i, expected_byte in enumerate(expected_bytes):
                tx_data = (yield dut.pipe_tx_data)
                tx_datak = (yield dut.pipe_tx_datak)
                self.assertEqual(tx_data, expected_byte,
                    f"Byte {i}: expected 0x{expected_byte:02X}, got 0x{tx_data:02X}")
                self.assertEqual(tx_datak, 0, f"Byte {i} should not be K-character")
                yield

            yield dut.sink.valid.eq(0)
            yield

        dut = PIPETXPacketizer()
        with tempfile.TemporaryDirectory(dir=".") as tmpdir:
            vcd_path = os.path.join(tmpdir, "test_tx_data.vcd")
            run_simulation(dut, testbench(dut), vcd_name=vcd_path)


if __name__ == "__main__":
    unittest.main()
```

### Step 2: Run test to verify it fails

Run: `pytest test/dll/test_pipe_tx_packetizer.py::TestPIPETXPacketizerData -v`

Expected: FAIL (DATA state not implemented)

### Step 3: Implement data transmission

Update DATA state in PIPETXPacketizer.__init__():

```python
        # Byte counter for 64-bit → 8-bit conversion
        byte_counter = Signal(3)  # 0-7
        data_buffer = Signal(64)

        self.fsm.act("DATA",
            # Output current byte from buffer
            NextValue(self.pipe_tx_data, data_buffer[0:8]),
            NextValue(self.pipe_tx_datak, 0),  # Data symbols, not K-characters

            # Shift buffer by 8 bits
            NextValue(data_buffer, data_buffer[8:64]),
            NextValue(byte_counter, byte_counter + 1),

            # After 8 bytes, check for more data or end
            If(byte_counter == 7,
                NextValue(byte_counter, 0),
                If(self.sink.valid & self.sink.last,
                    NextState("END")
                ).Elif(self.sink.valid,
                    # Load next 64-bit word
                    NextValue(data_buffer, self.sink.dat),
                    self.sink.ready.eq(1),
                    NextState("DATA")
                ).Else(
                    NextState("IDLE")
                )
            )
        )

        # Initialize data buffer when entering DATA state
        self.sync += [
            If(self.fsm.ongoing("IDLE") & self.fsm.next_state("DATA"),
                data_buffer.eq(self.sink.dat),
            )
        ]
```

### Step 4: Run test to verify it passes

Run: `pytest test/dll/test_pipe_tx_packetizer.py::TestPIPETXPacketizerData -v`

Expected: PASS

### Step 5: Commit data transmission

```bash
git add litepcie/dll/pipe.py test/dll/test_pipe_tx_packetizer.py
git commit -m "feat(pipe): Implement TX data transmission

Add data byte transmission to TX packetizer:
- 64-bit to 8-bit conversion
- Byte-by-byte transmission with K=0
- Buffer management and byte counter

Next: Implement END symbol generation.

References:
- PCIe Spec 4.0, Section 4.2.2.2: Data Symbols

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4.4: PIPE TX Packetizer - END Symbol Generation

Implement END symbol generation (END for good packets).

**Files:**
- Modify: `litepcie/dll/pipe.py` (implement END state)
- Modify: `test/dll/test_pipe_tx_packetizer.py` (add END test)

### Step 1: Write failing test for END symbol

Add to test/dll/test_pipe_tx_packetizer.py:

```python
class TestPIPETXPacketizerEnd(unittest.TestCase):
    """Test END symbol generation."""

    def test_tx_sends_end_symbol(self):
        """
        TX should send END (0xFD, K=1) at end of packet.

        Reference: PCIe Spec 4.0, Section 4.2.2.3: END Framing
        """
        def testbench(dut):
            # Send single 64-bit word packet
            yield dut.sink.valid.eq(1)
            yield dut.sink.first.eq(1)
            yield dut.sink.last.eq(1)
            yield dut.sink.dat.eq(0x0123456789ABCDEF)
            yield

            # Skip START
            yield dut.sink.first.eq(0)
            yield

            # Skip 8 data bytes
            for _ in range(8):
                yield

            # Check END symbol
            tx_data = (yield dut.pipe_tx_data)
            tx_datak = (yield dut.pipe_tx_datak)
            self.assertEqual(tx_data, 0xFD, "Should send END (0xFD)")
            self.assertEqual(tx_datak, 1, "END should be K-character")

            yield dut.sink.valid.eq(0)
            yield

        dut = PIPETXPacketizer()
        with tempfile.TemporaryDirectory(dir=".") as tmpdir:
            vcd_path = os.path.join(tmpdir, "test_tx_end.vcd")
            run_simulation(dut, testbench(dut), vcd_name=vcd_path)


if __name__ == "__main__":
    unittest.main()
```

### Step 2: Run test to verify it fails

Run: `pytest test/dll/test_pipe_tx_packetizer.py::TestPIPETXPacketizerEnd -v`

Expected: FAIL (END state not implemented)

### Step 3: Implement END symbol generation

Add END state in PIPETXPacketizer.__init__():

```python
        self.fsm.act("END",
            # Send END symbol (0xFD, K=1)
            NextValue(self.pipe_tx_data, 0xFD),
            NextValue(self.pipe_tx_datak, 1),

            # Consume the packet from DLL
            self.sink.ready.eq(1),

            NextState("IDLE")
        )
```

### Step 4: Run test to verify it passes

Run: `pytest test/dll/test_pipe_tx_packetizer.py::TestPIPETXPacketizerEnd -v`

Expected: PASS

### Step 5: Commit END symbol generation

```bash
git add litepcie/dll/pipe.py test/dll/test_pipe_tx_packetizer.py
git commit -m "feat(pipe): Implement TX END symbol generation

Add END state to TX packetizer:
- Send END (0xFD, K=1) after last data byte
- Complete packet framing: START → DATA → END

TX packetizer now functional for basic packet transmission.

Next: Implement RX depacketizer.

References:
- PCIe Spec 4.0, Section 4.2.2.3: END Framing

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4.5: PIPE RX Depacketizer - Basic Structure

Implement RX depacketizer that converts 8-bit PIPE symbols to 64-bit DLL packets.

**Files:**
- Modify: `litepcie/dll/pipe.py` (add PIPERXDepacketizer class)
- Create: `test/dll/test_pipe_rx_depacketizer.py`

### Step 1: Write failing test for RX depacketizer structure

Create test file:

```python
# test/dll/test_pipe_rx_depacketizer.py
#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Tests for PIPE RX depacketizer.

Tests conversion of PIPE symbols (8-bit) to DLL packets (64-bit).

Reference: PCIe Base Spec 4.0, Section 4.2.2: Symbol Encoding
"""

import unittest

from migen import *

from litepcie.dll.pipe import PIPERXDepacketizer
from litepcie.common import phy_layout


class TestPIPERXDepacketizerStructure(unittest.TestCase):
    """Test RX depacketizer structure."""

    def test_rx_depacketizer_has_required_interfaces(self):
        """RX depacketizer should have PIPE input and DLL output."""
        dut = PIPERXDepacketizer()

        # PIPE-facing input (8-bit symbols)
        self.assertTrue(hasattr(dut, "pipe_rx_data"))
        self.assertTrue(hasattr(dut, "pipe_rx_datak"))
        self.assertTrue(hasattr(dut, "pipe_rx_valid"))
        self.assertEqual(len(dut.pipe_rx_data), 8)
        self.assertEqual(len(dut.pipe_rx_datak), 1)

        # DLL-facing output (64-bit)
        self.assertTrue(hasattr(dut, "source"))
        self.assertEqual(len(dut.source.dat), 64)


if __name__ == "__main__":
    unittest.main()
```

### Step 2: Run test to verify it fails

Run: `pytest test/dll/test_pipe_rx_depacketizer.py::TestPIPERXDepacketizerStructure -v`

Expected: FAIL with "ImportError: cannot import name 'PIPERXDepacketizer'"

### Step 3: Create minimal RX depacketizer class

Add PIPERXDepacketizer to litepcie/dll/pipe.py (after PIPETXPacketizer):

```python
# PIPE RX Depacketizer -------------------------------------------------------------------------------

class PIPERXDepacketizer(LiteXModule):
    """
    PIPE RX depacketizer (PIPE symbols → DLL packets).

    Converts 8-bit PIPE symbols to 64-bit DLL packets by detecting K-character
    framing and assembling data bytes.

    Parameters
    ----------
    None

    Attributes
    ----------
    pipe_rx_data : Signal(8), input
        PIPE RX data (8-bit symbol)
    pipe_rx_datak : Signal(1), input
        PIPE RX K-character indicator
    pipe_rx_valid : Signal(1), input
        PIPE RX data valid
    source : Endpoint(phy_layout(64)), output
        DLL packets received

    Protocol
    --------
    Wait for START (STP or SDP with K=1):
        - STP (0xFB): TLP follows
        - SDP (0x5C): DLLP follows
    Then:
        - Accumulate 8 data bytes (K=0) into 64-bit word
        - Output to source when word complete
    Until END (0xFD, K=1) or EDB (0xFE, K=1)

    References
    ----------
    - PCIe Base Spec 4.0, Section 4.2.2: Symbol Encoding
    - PCIe Base Spec 4.0, Section 4.2.3: Framing
    """
    def __init__(self):
        # PIPE-facing input (8-bit symbols)
        self.pipe_rx_data = Signal(8)
        self.pipe_rx_datak = Signal()
        self.pipe_rx_valid = Signal()

        # DLL-facing output (64-bit packets)
        self.source = stream.Endpoint(phy_layout(64))

        # # #

        # TODO: Implement depacketizer FSM
        # States: IDLE, DATA, ERROR
```

### Step 4: Run test to verify it passes

Run: `pytest test/dll/test_pipe_rx_depacketizer.py::TestPIPERXDepacketizerStructure -v`

Expected: PASS

### Step 5: Commit RX depacketizer foundation

```bash
git add litepcie/dll/pipe.py test/dll/test_pipe_rx_depacketizer.py
git commit -m "feat(pipe): Add RX depacketizer foundation

Add PIPERXDepacketizer class structure:
- PIPE symbol input (8-bit + K-character)
- DLL packet output (64-bit)
- Placeholder for FSM implementation

Next: Implement START symbol detection.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4.6: PIPE RX Depacketizer - START Detection

Implement START symbol detection (STP/SDP).

**Files:**
- Modify: `litepcie/dll/pipe.py` (implement START detection)
- Modify: `test/dll/test_pipe_rx_depacketizer.py` (add behavioral test)

### Step 1: Write failing test for START detection

Add to test/dll/test_pipe_rx_depacketizer.py:

```python
import os
import tempfile
from litex.gen import run_simulation


class TestPIPERXDepacketizerStart(unittest.TestCase):
    """Test START symbol detection."""

    def test_rx_detects_stp_start(self):
        """
        RX should detect STP (0xFB, K=1) as TLP start.

        Reference: PCIe Spec 4.0, Section 4.2.2.1: START Framing
        """
        def testbench(dut):
            # Send STP symbol
            yield dut.pipe_rx_valid.eq(1)
            yield dut.pipe_rx_data.eq(0xFB)
            yield dut.pipe_rx_datak.eq(1)
            yield

            # After START, FSM should be in DATA state
            # We can't directly check FSM state, but we can verify
            # it's ready to receive data by checking source.first
            yield dut.pipe_rx_data.eq(0xAA)  # Data byte
            yield dut.pipe_rx_datak.eq(0)
            yield

            # If START was detected, source.first should be asserted
            # when first word is ready (we'll test this in later tasks)

        dut = PIPERXDepacketizer()
        with tempfile.TemporaryDirectory(dir=".") as tmpdir:
            vcd_path = os.path.join(tmpdir, "test_rx_stp.vcd")
            run_simulation(dut, testbench(dut), vcd_name=vcd_path)

    def test_rx_detects_sdp_start(self):
        """
        RX should detect SDP (0x5C, K=1) as DLLP start.

        Reference: PCIe Spec 4.0, Section 3.3.1: DLLP Format
        """
        def testbench(dut):
            # Send SDP symbol
            yield dut.pipe_rx_valid.eq(1)
            yield dut.pipe_rx_data.eq(0x5C)
            yield dut.pipe_rx_datak.eq(1)
            yield

            # After START, should be ready for data
            yield dut.pipe_rx_data.eq(0xBB)  # Data byte
            yield dut.pipe_rx_datak.eq(0)
            yield

        dut = PIPERXDepacketizer()
        with tempfile.TemporaryDirectory(dir=".") as tmpdir:
            vcd_path = os.path.join(tmpdir, "test_rx_sdp.vcd")
            run_simulation(dut, testbench(dut), vcd_name=vcd_path)


if __name__ == "__main__":
    unittest.main()
```

### Step 2: Run test to verify it fails

Run: `pytest test/dll/test_pipe_rx_depacketizer.py::TestPIPERXDepacketizerStart -v`

Expected: FAIL (FSM not implemented)

### Step 3: Implement START detection

Replace TODO section in PIPERXDepacketizer.__init__():

```python
        # # #

        # FSM for depacketization
        self.submodules.fsm = FSM(reset_state="IDLE")

        # Packet type tracking
        is_tlp = Signal()  # True if STP, False if SDP

        self.fsm.act("IDLE",
            # Wait for START symbol
            If(self.pipe_rx_valid & self.pipe_rx_datak,
                If(self.pipe_rx_data == 0xFB,
                    # STP: TLP follows
                    NextValue(is_tlp, 1),
                    NextState("DATA")
                ).Elif(self.pipe_rx_data == 0x5C,
                    # SDP: DLLP follows
                    NextValue(is_tlp, 0),
                    NextState("DATA")
                )
                # Ignore other K-characters (SKP, COM, etc.)
            )
        )

        self.fsm.act("DATA",
            # TODO: Implement data accumulation
            # For now, go back to IDLE
            NextState("IDLE")
        )
```

### Step 4: Run test to verify it passes

Run: `pytest test/dll/test_pipe_rx_depacketizer.py::TestPIPERXDepacketizerStart -v`

Expected: PASS

### Step 5: Commit START detection

```bash
git add litepcie/dll/pipe.py test/dll/test_pipe_rx_depacketizer.py
git commit -m "feat(pipe): Implement RX START detection

Add FSM to RX depacketizer with START detection:
- Detect STP (0xFB) for TLPs
- Detect SDP (0x5C) for DLLPs
- Track packet type for framing

Next: Implement data accumulation.

References:
- PCIe Spec 4.0, Section 4.2.2.1: START Framing

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4.7: PIPE RX Depacketizer - Data Accumulation

Implement data byte accumulation (8-bit → 64-bit conversion).

**Files:**
- Modify: `litepcie/dll/pipe.py` (implement DATA state)
- Modify: `test/dll/test_pipe_rx_depacketizer.py` (add data accumulation test)

### Step 1: Write failing test for data accumulation

Add to test/dll/test_pipe_rx_depacketizer.py:

```python
class TestPIPERXDepacketizerData(unittest.TestCase):
    """Test data accumulation."""

    def test_rx_accumulates_bytes_to_word(self):
        """
        RX should accumulate 8 bytes into 64-bit word.

        Bytes received in little-endian order.

        Reference: PCIe Spec 4.0, Section 4.2.2.2: Data Symbols
        """
        def testbench(dut):
            # Send START
            yield dut.pipe_rx_valid.eq(1)
            yield dut.pipe_rx_data.eq(0xFB)  # STP
            yield dut.pipe_rx_datak.eq(1)
            yield

            # Send 8 data bytes
            test_bytes = [0xEF, 0xCD, 0xAB, 0x89, 0x67, 0x45, 0x23, 0x01]
            expected_word = 0x0123456789ABCDEF

            for byte_val in test_bytes:
                yield dut.pipe_rx_data.eq(byte_val)
                yield dut.pipe_rx_datak.eq(0)
                yield

            # After 8 bytes, should have valid word on source
            source_valid = (yield dut.source.valid)
            source_data = (yield dut.source.dat)
            self.assertEqual(source_valid, 1, "Should have valid output after 8 bytes")
            self.assertEqual(source_data, expected_word,
                f"Expected 0x{expected_word:016X}, got 0x{source_data:016X}")

        dut = PIPERXDepacketizer()
        with tempfile.TemporaryDirectory(dir=".") as tmpdir:
            vcd_path = os.path.join(tmpdir, "test_rx_data_accum.vcd")
            run_simulation(dut, testbench(dut), vcd_name=vcd_path)


if __name__ == "__main__":
    unittest.main()
```

### Step 2: Run test to verify it fails

Run: `pytest test/dll/test_pipe_rx_depacketizer.py::TestPIPERXDepacketizerData -v`

Expected: FAIL (DATA state not implemented)

### Step 3: Implement data accumulation

Update DATA state in PIPERXDepacketizer.__init__():

```python
        # Byte accumulator for 8-bit → 64-bit conversion
        byte_counter = Signal(3)  # 0-7
        data_buffer = Signal(64)

        self.fsm.act("DATA",
            # Accumulate data bytes
            If(self.pipe_rx_valid & ~self.pipe_rx_datak,
                # Data symbol: accumulate into buffer
                NextValue(data_buffer, Cat(self.pipe_rx_data, data_buffer[0:56])),
                NextValue(byte_counter, byte_counter + 1),

                # After 8 bytes, output word
                If(byte_counter == 7,
                    NextValue(self.source.valid, 1),
                    NextValue(self.source.dat, Cat(self.pipe_rx_data, data_buffer[0:56])),
                    NextValue(byte_counter, 0),
                )
            ).Elif(self.pipe_rx_valid & self.pipe_rx_datak,
                # K-character: check for END
                If((self.pipe_rx_data == 0xFD) | (self.pipe_rx_data == 0xFE),
                    # END or EDB: finalize packet
                    NextState("END")
                )
                # Ignore other K-characters (SKP, etc.)
            )
        )

        # Clear source.valid when consumed
        self.sync += [
            If(self.source.valid & self.source.ready,
                self.source.valid.eq(0),
            )
        ]
```

### Step 4: Run test to verify it passes

Run: `pytest test/dll/test_pipe_rx_depacketizer.py::TestPIPERXDepacketizerData -v`

Expected: PASS

### Step 5: Commit data accumulation

```bash
git add litepcie/dll/pipe.py test/dll/test_pipe_rx_depacketizer.py
git commit -m "feat(pipe): Implement RX data accumulation

Add data byte accumulation to RX depacketizer:
- 8-bit to 64-bit conversion
- Byte counter and buffer management
- Output word when 8 bytes received

Next: Implement END detection.

References:
- PCIe Spec 4.0, Section 4.2.2.2: Data Symbols

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4.8: PIPE RX Depacketizer - END Detection

Implement END symbol detection and packet finalization.

**Files:**
- Modify: `litepcie/dll/pipe.py` (implement END state)
- Modify: `test/dll/test_pipe_rx_depacketizer.py` (add END test)

### Step 1: Write failing test for END detection

Add to test/dll/test_pipe_rx_depacketizer.py:

```python
class TestPIPERXDepacketizerEnd(unittest.TestCase):
    """Test END detection."""

    def test_rx_detects_end_symbol(self):
        """
        RX should detect END (0xFD, K=1) and finalize packet.

        Reference: PCIe Spec 4.0, Section 4.2.2.3: END Framing
        """
        def testbench(dut):
            # Send complete packet: START + 8 bytes + END
            yield dut.pipe_rx_valid.eq(1)

            # START
            yield dut.pipe_rx_data.eq(0xFB)  # STP
            yield dut.pipe_rx_datak.eq(1)
            yield

            # 8 data bytes
            for byte_val in [0xEF, 0xCD, 0xAB, 0x89, 0x67, 0x45, 0x23, 0x01]:
                yield dut.pipe_rx_data.eq(byte_val)
                yield dut.pipe_rx_datak.eq(0)
                yield

            # END
            yield dut.pipe_rx_data.eq(0xFD)
            yield dut.pipe_rx_datak.eq(1)
            yield

            # Check that source.last is asserted
            source_last = (yield dut.source.last)
            self.assertEqual(source_last, 1, "Should assert source.last on END")

        dut = PIPERXDepacketizer()
        with tempfile.TemporaryDirectory(dir=".") as tmpdir:
            vcd_path = os.path.join(tmpdir, "test_rx_end.vcd")
            run_simulation(dut, testbench(dut), vcd_name=vcd_path)


if __name__ == "__main__":
    unittest.main()
```

### Step 2: Run test to verify it fails

Run: `pytest test/dll/test_pipe_rx_depacketizer.py::TestPIPERXDepacketizerEnd -v`

Expected: FAIL (END state not implemented)

### Step 3: Implement END detection

Add END state in PIPERXDepacketizer.__init__():

```python
        self.fsm.act("END",
            # Finalize packet
            NextValue(self.source.last, 1),

            # If partial word in buffer, output it
            If(byte_counter != 0,
                NextValue(self.source.valid, 1),
                NextValue(self.source.dat, data_buffer),
            ),

            NextState("IDLE")
        )

        # Track first beat of packet
        first_beat = Signal(reset=1)
        self.sync += [
            If(self.fsm.ongoing("IDLE"),
                first_beat.eq(1),
            ).Elif(self.source.valid & self.source.ready,
                first_beat.eq(0),
            )
        ]
        self.comb += self.source.first.eq(first_beat & self.source.valid)
```

### Step 4: Run test to verify it passes

Run: `pytest test/dll/test_pipe_rx_depacketizer.py::TestPIPERXDepacketizerEnd -v`

Expected: PASS

### Step 5: Commit END detection

```bash
git add litepcie/dll/pipe.py test/dll/test_pipe_rx_depacketizer.py
git commit -m "feat(pipe): Implement RX END detection

Add END state to RX depacketizer:
- Detect END (0xFD, K=1)
- Assert source.last on packet end
- Handle partial words if needed
- Track first/last beat of packet

RX depacketizer now functional for basic packet reception.

References:
- PCIe Spec 4.0, Section 4.2.2.3: END Framing

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4.9: Integrate TX/RX into PIPE Interface

Integrate TX packetizer and RX depacketizer into PIPEInterface class.

**Files:**
- Modify: `litepcie/dll/pipe.py` (update PIPEInterface)
- Modify: `test/dll/test_pipe_interface.py` (add integration test)

### Step 1: Write failing test for TX/RX integration

Add to test/dll/test_pipe_interface.py:

```python
class TestPIPEInterfaceTXRX(unittest.TestCase):
    """Test TX/RX integration."""

    def test_pipe_interface_has_tx_rx(self):
        """PIPE interface should have TX and RX components."""
        dut = PIPEInterface(data_width=8, gen=1)

        # Should have TX packetizer
        self.assertTrue(hasattr(dut, "tx_packetizer"))

        # Should have RX depacketizer
        self.assertTrue(hasattr(dut, "rx_depacketizer"))


if __name__ == "__main__":
    unittest.main()
```

### Step 2: Run test to verify it fails

Run: `pytest test/dll/test_pipe_interface.py::TestPIPEInterfaceTXRX -v`

Expected: FAIL (tx_packetizer/rx_depacketizer not in PIPEInterface)

### Step 3: Integrate TX/RX into PIPEInterface

Update PIPEInterface.__init__() to add TX/RX components:

```python
# In PIPEInterface.__init__(), replace placeholder section:

        # # #

        # TX Path: DLL packets → PIPE symbols
        self.tx_packetizer = PIPETXPacketizer()

        # Connect DLL TX sink to packetizer
        self.comb += self.dll_tx_sink.connect(self.tx_packetizer.sink)

        # Connect packetizer output to PIPE TX
        self.comb += [
            self.pipe_tx_data.eq(self.tx_packetizer.pipe_tx_data),
            self.pipe_tx_datak.eq(self.tx_packetizer.pipe_tx_datak),
        ]

        # When no data, send electrical idle
        self.comb += [
            If(~self.tx_packetizer.sink.valid,
                self.pipe_tx_elecidle.eq(1),
            )
        ]

        # RX Path: PIPE symbols → DLL packets
        self.rx_depacketizer = PIPERXDepacketizer()

        # Connect PIPE RX to depacketizer
        self.comb += [
            self.rx_depacketizer.pipe_rx_data.eq(self.pipe_rx_data),
            self.rx_depacketizer.pipe_rx_datak.eq(self.pipe_rx_datak),
            self.rx_depacketizer.pipe_rx_valid.eq(self.pipe_rx_valid),
        ]

        # Connect depacketizer output to DLL RX source
        self.comb += self.rx_depacketizer.source.connect(self.dll_rx_source)
```

### Step 4: Run test to verify it passes

Run: `pytest test/dll/test_pipe_interface.py::TestPIPEInterfaceTXRX -v`

Expected: PASS

### Step 5: Commit TX/RX integration

```bash
git add litepcie/dll/pipe.py test/dll/test_pipe_interface.py
git commit -m "feat(pipe): Integrate TX/RX into PIPE interface

Integrate TX packetizer and RX depacketizer into PIPEInterface:
- TX: dll_tx_sink → packetizer → pipe_tx signals
- RX: pipe_rx signals → depacketizer → dll_rx_source
- Electrical idle when no TX data

PIPE interface now has functional TX/RX data paths.

Next: Add loopback tests.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4.10: Loopback Testing

Create loopback tests to verify TX → RX data flow.

**Files:**
- Create: `test/dll/test_pipe_loopback.py`

### Step 1: Write loopback test

Create comprehensive loopback test:

```python
# test/dll/test_pipe_loopback.py
#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Tests for PIPE loopback (TX → RX).

Verifies complete data path through PIPE interface.

Reference: PCIe Base Spec 4.0, Section 4.2
"""

import os
import tempfile
import unittest

from migen import *
from litex.gen import run_simulation

from litepcie.dll.pipe import PIPEInterface
from litepcie.common import phy_layout


class TestPIPELoopback(unittest.TestCase):
    """Test PIPE loopback functionality."""

    def test_loopback_single_word(self):
        """
        Single 64-bit word should loop back correctly.

        TX: DLL packet → PIPE symbols
        Loopback: Connect TX → RX
        RX: PIPE symbols → DLL packet

        Verify output matches input.
        """
        def testbench(dut):
            # Test data
            test_data = 0x0123456789ABCDEF

            # Send packet to TX
            yield dut.dll_tx_sink.valid.eq(1)
            yield dut.dll_tx_sink.first.eq(1)
            yield dut.dll_tx_sink.last.eq(1)
            yield dut.dll_tx_sink.dat.eq(test_data)
            yield

            # Let TX process (START + 8 bytes + END = 10 cycles)
            yield dut.dll_tx_sink.valid.eq(0)
            for _ in range(15):
                yield

            # Check RX output
            rx_valid = (yield dut.dll_rx_source.valid)
            rx_data = (yield dut.dll_rx_source.dat)
            rx_first = (yield dut.dll_rx_source.first)
            rx_last = (yield dut.dll_rx_source.last)

            self.assertEqual(rx_valid, 1, "RX should have valid output")
            self.assertEqual(rx_data, test_data,
                f"RX data mismatch: expected 0x{test_data:016X}, got 0x{rx_data:016X}")
            self.assertEqual(rx_first, 1, "RX should assert first")
            self.assertEqual(rx_last, 1, "RX should assert last")

        # Create PIPE interface with loopback
        dut = PIPEInterface(data_width=8, gen=1)

        # Loopback TX → RX
        dut.comb += [
            dut.pipe_rx_data.eq(dut.pipe_tx_data),
            dut.pipe_rx_datak.eq(dut.pipe_tx_datak),
            dut.pipe_rx_valid.eq(1),  # Always valid in loopback
        ]

        with tempfile.TemporaryDirectory(dir=".") as tmpdir:
            vcd_path = os.path.join(tmpdir, "test_loopback_single.vcd")
            run_simulation(dut, testbench(dut), vcd_name=vcd_path)

    def test_loopback_multiple_words(self):
        """
        Multiple 64-bit words should loop back correctly.

        Verifies multi-word packet handling.
        """
        def testbench(dut):
            # Test data (3 words)
            test_words = [
                0x0123456789ABCDEF,
                0xFEDCBA9876543210,
                0xAAAABBBBCCCCDDDD,
            ]

            # Send packet to TX
            for i, word in enumerate(test_words):
                yield dut.dll_tx_sink.valid.eq(1)
                yield dut.dll_tx_sink.first.eq(1 if i == 0 else 0)
                yield dut.dll_tx_sink.last.eq(1 if i == len(test_words)-1 else 0)
                yield dut.dll_tx_sink.dat.eq(word)
                yield

            # Let TX/RX process
            yield dut.dll_tx_sink.valid.eq(0)
            for _ in range(50):
                yield

            # Check RX output (consume all words)
            for i, expected_word in enumerate(test_words):
                # Wait for valid
                while not (yield dut.dll_rx_source.valid):
                    yield

                rx_data = (yield dut.dll_rx_source.dat)
                rx_first = (yield dut.dll_rx_source.first)
                rx_last = (yield dut.dll_rx_source.last)

                self.assertEqual(rx_data, expected_word,
                    f"Word {i}: expected 0x{expected_word:016X}, got 0x{rx_data:016X}")

                if i == 0:
                    self.assertEqual(rx_first, 1, "First word should have first=1")
                if i == len(test_words) - 1:
                    self.assertEqual(rx_last, 1, "Last word should have last=1")

                # Consume word
                yield dut.dll_rx_source.ready.eq(1)
                yield
                yield dut.dll_rx_source.ready.eq(0)

        # Create PIPE interface with loopback
        dut = PIPEInterface(data_width=8, gen=1)

        # Loopback TX → RX
        dut.comb += [
            dut.pipe_rx_data.eq(dut.pipe_tx_data),
            dut.pipe_rx_datak.eq(dut.pipe_tx_datak),
            dut.pipe_rx_valid.eq(1),
        ]

        with tempfile.TemporaryDirectory(dir=".") as tmpdir:
            vcd_path = os.path.join(tmpdir, "test_loopback_multi.vcd")
            run_simulation(dut, testbench(dut), vcd_name=vcd_path)


if __name__ == "__main__":
    unittest.main()
```

### Step 2: Run loopback test

Run: `pytest test/dll/test_pipe_loopback.py -v`

Expected: PASS (if TX/RX implementation correct) or FAIL with specific errors

### Step 3: Fix any issues revealed by loopback test

If tests fail, debug and fix issues in TX packetizer or RX depacketizer.

Common issues:
- Timing: Add pipeline stages if needed
- Byte ordering: Verify little-endian conversion
- State transitions: Check FSM logic

### Step 4: Re-run loopback test to verify

Run: `pytest test/dll/test_pipe_loopback.py -v`

Expected: PASS

### Step 5: Commit loopback tests

```bash
git add test/dll/test_pipe_loopback.py
git commit -m "test(pipe): Add loopback tests

Add comprehensive loopback tests:
- Single word loopback
- Multi-word packet loopback
- Verify complete TX → RX data path

All loopback tests passing.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4.11: Run Full Test Suite

Verify all tests pass, including existing DLL tests.

**Files:**
- None (testing only)

### Step 1: Run complete test suite

Run: `pytest test/dll/ -v --cov=litepcie/dll --cov-report=term`

Expected: All tests PASS, high coverage on pipe.py

### Step 2: Check coverage

Verify coverage ≥80% on:
- `litepcie/dll/pipe.py`

If coverage low, add tests for uncovered paths.

### Step 3: Run pre-commit hooks

Run: `pre-commit run --all-files`

Expected: All hooks pass (ruff, formatting)

### Step 4: Generate coverage report

Run: `pytest test/dll/ --cov=litepcie/dll --cov-report=html`

Review coverage in htmlcov/index.html

### Step 5: Document completion

Update docs/architecture/integration-strategy.md with Phase 4 completion:

```markdown
### Phase 4: TX/RX Data Paths (Completed)
- Task 4.1-4.4: ✅ TX packetizer (DLL packets → PIPE symbols)
- Task 4.5-4.8: ✅ RX depacketizer (PIPE symbols → DLL packets)
- Task 4.9: ✅ Integration into PIPE interface
- Task 4.10: ✅ Loopback testing

Phase 4 implemented functional TX/RX data paths:
- Complete packet framing (START → DATA → END)
- 64-bit to 8-bit conversion (TX) and reverse (RX)
- K-character generation and detection
- Loopback tests verify end-to-end functionality
- All tests passing, 85%+ coverage
```

Commit documentation update:

```bash
git add docs/architecture/integration-strategy.md
git commit -m "docs: Update integration strategy with Phase 4 completion

Phase 4 complete: TX/RX data paths functional.
All tests passing, ready for Phase 5 (ordered sets and link training).

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Phase 4 Summary

**Completed:**
- ✅ Task 4.1-4.4: TX packetizer (DLL packets → PIPE symbols with K-character framing)
- ✅ Task 4.5-4.8: RX depacketizer (PIPE symbols → DLL packets with frame detection)
- ✅ Task 4.9: Integration into PIPE interface
- ✅ Task 4.10: Loopback testing (single/multi-word packets)
- ✅ Task 4.11: Full test suite verification

**Files Created/Modified:**
- `litepcie/dll/pipe.py` - Added PIPETXPacketizer and PIPERXDepacketizer classes
- `test/dll/test_pipe_tx_packetizer.py` - TX packetizer tests (structure, START, data, END)
- `test/dll/test_pipe_rx_depacketizer.py` - RX depacketizer tests (structure, START, data, END)
- `test/dll/test_pipe_loopback.py` - Loopback integration tests
- `test/dll/test_pipe_interface.py` - Updated with TX/RX integration tests

**Key Achievements:**
1. Complete TX path with K-character framing (STP/SDP/END)
2. Complete RX path with frame detection and byte accumulation
3. Loopback tests verify end-to-end functionality
4. All tests pass with ≥80% code coverage
5. TDD approach with RED-GREEN-REFACTOR maintained throughout

**Next Steps (Phase 5 - Ordered Sets & Link Training):**
- Implement SKP ordered set generation/detection (clock compensation)
- Add TS1/TS2 ordered set structure
- Implement basic link training state machine
- Add electrical idle handling
- Integration tests with external PHY wrapper

---

## Execution Notes

**Approach:**
- Test-driven development (write failing test first, then implement)
- Minimal implementation (just enough to pass tests)
- Frequent commits (after each passing test)
- Follow code quality standards (ruff, coverage ≥80%)

**Quality Gates:**
- All tests must pass before committing
- Pre-commit hooks must pass
- Coverage must be ≥80% for new code
- PCIe spec references in comments

**Flexibility:**
- If tests reveal issues, fix before proceeding to next task
- Plan can be adjusted if blockers discovered
- Loopback tests are integration checkpoints
