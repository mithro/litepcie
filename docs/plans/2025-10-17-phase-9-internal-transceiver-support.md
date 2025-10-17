# Phase 9: Internal Transceiver Support Implementation Plan

> **For Claude:** Use `${SUPERPOWERS_SKILLS_ROOT}/skills/collaboration/executing-plans/SKILL.md` to implement this plan task-by-task.

**Date:** 2025-10-17
**Status:** PLANNED
**Goal:** Integrate PIPE/DLL implementation with FPGA internal transceivers, replacing external PHY chips with vendor-specific SERDES wrappers. Support Xilinx 7-Series GTX, Xilinx UltraScale+ GTH/GTY, and Lattice ECP5 SERDES with 8b/10b encoding and proper PIPE interface compliance.

**Architecture:** Create transceiver wrappers that expose standard PIPE interface to our DLL/LTSSM layer. Each wrapper instantiates vendor-specific SERDES primitives, handles 8b/10b encoding/decoding (for Gen1/Gen2), implements clock domain crossing for transceiver clocks, and provides LTSSM integration. Architecture supports Gen3 (128b/130b encoding) as future extension.

**Tech Stack:** Migen/LiteX, pytest + pytest-cov, Python 3.11+, Xilinx 7-Series GTX/GTH primitives, UltraScale+ GTH/GTY primitives, Lattice ECP5 SERDES primitives

**Context:**
- Phases 3-6 complete: PIPE interface, DLL layer, ordered sets, LTSSM
- Existing vendor PHY implementations: `s7pciephy.py`, `uspciephy.py` (use hard IP blocks)
- Need soft SERDES wrappers that integrate with our PIPE/DLL stack
- External PHY wrapper (`pipe_external_phy.py`) provides template for integration
- Current limitation: No pure-gateware PCIe implementation (all use hard IP)

**Scope:** This phase implements Gen1/Gen2 transceiver wrappers with 8b/10b encoding. Gen3 (128b/130b) support deferred but architecture designed for extensibility. Focus on x1 (single lane) initially, with multi-lane (x4, x8) as stretch goal.

---

## Task 9.1: 8b/10b Encoder/Decoder Core

Create 8b/10b encoding/decoding modules for Gen1/Gen2 physical layer.

**Files:**
- Create: `litepcie/phy/encoding/encoder_8b10b.py`
- Create: `test/phy/test_encoder_8b10b.py`

### Step 1: Write failing test for 8b/10b encoder

Create test file for 8b/10b encoder:

```python
# test/phy/test_encoder_8b10b.py
#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Tests for 8b/10b encoder/decoder.

8b/10b encoding is used in Gen1 (2.5 GT/s) and Gen2 (5.0 GT/s) PCIe for:
- DC balance (equal number of 1s and 0s)
- Run-length limitation (no more than 5 consecutive bits)
- Clock recovery (sufficient transitions)
- K-character support (special control codes)

References:
- Widmer & Franaszek, "A DC-Balanced, Partitioned-Block, 8B/10B Transmission Code"
- PCIe Base Spec 4.0, Section 4.2.2: 8b/10b Encoding
"""

import unittest

from migen import *
from litex.gen import run_simulation

from litepcie.phy.encoding.encoder_8b10b import Encoder8b10b


class TestEncoder8b10bStructure(unittest.TestCase):
    """Test 8b/10b encoder structure."""

    def test_encoder_has_required_signals(self):
        """
        Encoder should have data, K-char control, and running disparity signals.

        8b/10b encoder converts 8-bit data into 10-bit encoded symbols.
        K-characters are special control codes (like COM, SKP).
        Running disparity tracks DC balance.

        Reference: IBM "8B10B Transmit Encoder Core"
        """
        dut = Encoder8b10b()

        # Input signals
        self.assertTrue(hasattr(dut, "d_input"))      # 8-bit data input
        self.assertTrue(hasattr(dut, "k_input"))      # K-character flag

        # Output signals
        self.assertTrue(hasattr(dut, "d_output"))     # 10-bit encoded output
        self.assertTrue(hasattr(dut, "running_disp")) # Running disparity state

    def test_encoder_data_widths(self):
        """
        Encoder should have correct signal widths.
        """
        dut = Encoder8b10b()

        self.assertEqual(len(dut.d_input), 8)   # 8-bit input
        self.assertEqual(len(dut.k_input), 1)   # 1-bit K flag
        self.assertEqual(len(dut.d_output), 10) # 10-bit output
        self.assertEqual(len(dut.running_disp), 1) # 1-bit disparity


class TestEncoder8b10bDataCharacters(unittest.TestCase):
    """Test 8b/10b encoding for data characters."""

    def test_encoder_d0_0(self):
        """
        Test encoding of D0.0 (0x00).

        D0.0 encodes to:
        - RD- (negative disparity): 100111_0100 (0x274)
        - RD+ (positive disparity): 011000_1011 (0x18B)

        Reference: 8b/10b encoding tables
        """
        def testbench(dut):
            # Encode D0.0 with RD-
            yield dut.d_input.eq(0x00)
            yield dut.k_input.eq(0)
            yield
            output = yield dut.d_output
            # Should be 100111_0100 = 0x274 for RD-
            self.assertEqual(output, 0x274)

        dut = Encoder8b10b()
        run_simulation(dut, testbench(dut))

    def test_encoder_d21_5(self):
        """
        Test encoding of D21.5 (0xB5) - commonly used in PCIe.

        D21.5 is part of COM symbol (K28.5 followed by D21.5).
        """
        def testbench(dut):
            # Encode D21.5 with RD-
            yield dut.d_input.eq(0xB5)
            yield dut.k_input.eq(0)
            yield
            output = yield dut.d_output
            # Should be valid 10-bit code
            self.assertNotEqual(output, 0)

        dut = Encoder8b10b()
        run_simulation(dut, testbench(dut))


class TestEncoder8b10bKCharacters(unittest.TestCase):
    """Test 8b/10b encoding for K-characters (special control codes)."""

    def test_encoder_k28_5_com_symbol(self):
        """
        Test encoding of K28.5 (COM symbol, 0xBC).

        K28.5 is the most common K-character in PCIe:
        - Used in ordered sets (TS1, TS2, SKP, etc.)
        - RD- encoding: 001111_1010 (0x0FA)
        - RD+ encoding: 110000_0101 (0x305)

        Reference: PCIe Spec 4.0, Table 4-14: Special Symbol Definitions
        """
        def testbench(dut):
            # Encode K28.5 with RD-
            yield dut.d_input.eq(0xBC)  # K28.5
            yield dut.k_input.eq(1)     # K-character
            yield
            output = yield dut.d_output
            # Should be 001111_1010 = 0x0FA for RD-
            self.assertEqual(output, 0x0FA)

        dut = Encoder8b10b()
        run_simulation(dut, testbench(dut))

    def test_encoder_k23_7_end_symbol(self):
        """
        Test encoding of K23.7 (END symbol, 0xFD).

        K23.7 marks end of packet in PCIe.
        """
        def testbench(dut):
            # Encode K23.7
            yield dut.d_input.eq(0xFD)  # K23.7
            yield dut.k_input.eq(1)
            yield
            output = yield dut.d_output
            self.assertNotEqual(output, 0)

        dut = Encoder8b10b()
        run_simulation(dut, testbench(dut))


class TestEncoder8b10bRunningDisparity(unittest.TestCase):
    """Test running disparity tracking."""

    def test_encoder_maintains_dc_balance(self):
        """
        Running disparity should alternate to maintain DC balance.

        After encoding a character, RD should flip to maintain
        roughly equal 1s and 0s over time.
        """
        def testbench(dut):
            # Track disparity changes
            for i in range(10):
                yield dut.d_input.eq(i)
                yield dut.k_input.eq(0)
                yield
                disp = yield dut.running_disp
                # Disparity should be either 0 or 1
                self.assertIn(disp, [0, 1])

        dut = Encoder8b10b()
        run_simulation(dut, testbench(dut))


if __name__ == "__main__":
    unittest.main()
```

### Step 2: Run test to verify it fails

Run: `pytest test/phy/test_encoder_8b10b.py -v`

Expected: FAIL with "No module named 'litepcie.phy.encoding.encoder_8b10b'"

### Step 3: Create 8b/10b encoder module

Create directory and module:

```bash
mkdir -p litepcie/phy/encoding
touch litepcie/phy/encoding/__init__.py
```

Create `litepcie/phy/encoding/encoder_8b10b.py`:

```python
#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
8b/10b Encoder/Decoder for PCIe Gen1/Gen2.

Implements Widmer & Franaszek 8b/10b encoding scheme used in:
- PCIe Gen1 (2.5 GT/s)
- PCIe Gen2 (5.0 GT/s)

8b/10b encoding provides:
- DC balance (running disparity control)
- Clock recovery (sufficient transitions)
- Special K-characters for control codes
- Run-length limitation (max 5 consecutive bits)

References
----------
- Widmer & Franaszek, "A DC-Balanced, Partitioned-Block, 8B/10B Transmission Code"
- PCIe Base Spec 4.0, Section 4.2.2: Physical Layer 8b/10b Encoding
- IBM "8B10B Encoder/Decoder"
"""

from migen import *
from litex.gen import LiteXModule


class Encoder8b10b(LiteXModule):
    """
    8b/10b Encoder.

    Converts 8-bit data (with optional K-character flag) into 10-bit
    encoded symbols with DC balance.

    Attributes
    ----------
    d_input : Signal(8), input
        8-bit data input (D0-D7)
    k_input : Signal(1), input
        K-character flag (1=K-char, 0=data)
    d_output : Signal(10), output
        10-bit encoded output
    running_disp : Signal(1), output
        Current running disparity (0=negative, 1=positive)

    Notes
    -----
    Running disparity tracks DC balance:
    - RD- (negative): more 0s than 1s in previous symbols
    - RD+ (positive): more 1s than 0s in previous symbols

    Each symbol is encoded to flip disparity as needed.

    References
    ----------
    - IBM "8B10B Transmit Encoder Core"
    - Xilinx XAPP336: "Efficient 8B/10B Encoding"
    """

    def __init__(self):
        # Input signals
        self.d_input = Signal(8)  # 8-bit data
        self.k_input = Signal()   # K-character flag

        # Output signals
        self.d_output = Signal(10)      # 10-bit encoded
        self.running_disp = Signal()    # Running disparity state

        # # #

        # Split 8-bit input into 5-bit and 3-bit groups
        # 8b/10b encoding works on 5b/6b (low bits) + 3b/4b (high bits)
        edcba = self.d_input[0:5]  # 5 low bits -> 6-bit encoded
        hgf   = self.d_input[5:8]  # 3 high bits -> 4-bit encoded

        # Encoded outputs (will be filled by lookup tables)
        abcdei = Signal(6)  # 6-bit encoded from edcba
        fghj   = Signal(4)  # 4-bit encoded from hgf

        # Combine encoded parts
        self.comb += self.d_output.eq(Cat(abcdei, fghj))

        # TODO: Implement 5b/6b and 3b/4b encoding lookup tables
        # TODO: Implement running disparity calculation
        # TODO: Handle K-character encoding

        # Placeholder: simple pass-through for now
        self.comb += [
            abcdei.eq(edcba),
            fghj.eq(hgf),
        ]
```

### Step 4: Implement encoding lookup tables

Add encoding tables to `encoder_8b10b.py`:

```python
# After class definition, add lookup table functions:

def get_5b6b_table():
    """
    Get 5b/6b encoding lookup table.

    Returns dict mapping (input_5b, rd_negative) -> output_6b

    Reference: IBM 8B10B encoding tables
    """
    # Simplified table - only key values for testing
    # Full implementation would have all 32 entries x 2 disparity states
    table = {
        # (5-bit input, RD-) : 6-bit output
        (0b00000, 0): 0b100111,  # D0
        (0b00000, 1): 0b011000,  # D0 (RD+)
        # ... more entries needed for full implementation
    }
    return table

def get_3b4b_table():
    """
    Get 3b/4b encoding lookup table.

    Returns dict mapping (input_3b, rd_negative) -> output_4b
    """
    table = {
        (0b000, 0): 0b0100,  # D.0
        (0b000, 1): 0b1011,  # D.0 (RD+)
        # ... more entries needed
    }
    return table

def get_k_char_table():
    """
    Get K-character encoding table.

    Special 10-bit codes for control characters.
    """
    table = {
        # K-char code -> (RD- encoding, RD+ encoding)
        0xBC: (0x0FA, 0x305),  # K28.5 (COM)
        0xF7: (0x1AA, 0x255),  # K23.7 (END)
        0xFB: (0x2AA, 0x155),  # K27.7 (EDB)
        0xFD: (0x355, 0x0AA),  # K29.7 (STP)
        0xFE: (0x2A9, 0x156),  # K30.7 (SDP)
        # ... more K-chars
    }
    return table
```

### Step 5: Run tests iteratively

Run: `pytest test/phy/test_encoder_8b10b.py -v`

Implement encoding logic until tests pass. Key steps:
1. Implement 5b/6b lookup
2. Implement 3b/4b lookup
3. Implement running disparity calculation
4. Implement K-character handling

Expected: PASS (all encoder tests)

### Step 6: Implement decoder

Add decoder tests and implementation in same files.

Create `Decoder8b10b` class that reverses encoding:
- 10-bit input -> 8-bit output
- Detect K-characters
- Detect encoding errors
- Track running disparity

### Step 7: Commit encoder/decoder

```bash
git add litepcie/phy/encoding/ test/phy/test_encoder_8b10b.py
git commit -m "feat(phy): Add 8b/10b encoder/decoder for Gen1/Gen2

Implement Widmer & Franaszek 8b/10b encoding:
- 5b/6b and 3b/4b encoding tables
- Running disparity tracking for DC balance
- K-character support (COM, SKP, END, etc.)
- Decoder with error detection

8b/10b is used in PCIe Gen1 (2.5 GT/s) and Gen2 (5.0 GT/s).

References:
- Widmer & Franaszek 8B/10B paper
- PCIe Spec 4.0, Section 4.2.2

Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 9.2: Xilinx 7-Series GTX Transceiver Wrapper

Create PIPE-compliant wrapper for Xilinx 7-Series GTX transceivers.

**Files:**
- Create: `litepcie/phy/transceivers/s7_gtx.py`
- Create: `test/phy/test_s7_gtx.py`

### Step 1: Write failing test for GTX wrapper structure

Create test:

```python
# test/phy/test_s7_gtx.py
#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Tests for Xilinx 7-Series GTX transceiver wrapper.

GTX transceivers provide multi-gigabit serial I/O:
- Support 2.5 GT/s (Gen1) and 5.0 GT/s (Gen2)
- Include 8b/10b encoder/decoder
- Provide clock recovery and CDR
- TX/RX buffering and alignment

References:
- Xilinx UG476: "7 Series FPGAs GTX/GTH Transceivers"
- PCIe Base Spec 4.0
"""

import unittest

from migen import *

from litepcie.phy.transceivers.s7_gtx import S7GTXTransceiver


class TestS7GTXStructure(unittest.TestCase):
    """Test GTX transceiver wrapper structure."""

    def test_gtx_has_pipe_interface(self):
        """
        GTX wrapper should expose PIPE interface signals.

        PIPE interface connects transceiver to DLL layer.
        """
        dut = S7GTXTransceiver()

        # PIPE TX signals
        self.assertTrue(hasattr(dut, "pipe_tx_data"))
        self.assertTrue(hasattr(dut, "pipe_tx_datak"))

        # PIPE RX signals
        self.assertTrue(hasattr(dut, "pipe_rx_data"))
        self.assertTrue(hasattr(dut, "pipe_rx_datak"))

        # PIPE control
        self.assertTrue(hasattr(dut, "pipe_tx_elecidle"))
        self.assertTrue(hasattr(dut, "pipe_rx_elecidle"))

    def test_gtx_has_serdes_pads(self):
        """
        GTX should have differential TX/RX pads for chip I/O.
        """
        dut = S7GTXTransceiver()

        # Differential signals to/from PCIe connector
        self.assertTrue(hasattr(dut, "tx_p"))
        self.assertTrue(hasattr(dut, "tx_n"))
        self.assertTrue(hasattr(dut, "rx_p"))
        self.assertTrue(hasattr(dut, "rx_n"))

    def test_gtx_has_clock_outputs(self):
        """
        GTX provides recovered clock outputs.
        """
        dut = S7GTXTransceiver()

        self.assertTrue(hasattr(dut, "tx_clk"))
        self.assertTrue(hasattr(dut, "rx_clk"))


if __name__ == "__main__":
    unittest.main()
```

### Step 2: Run test to verify it fails

Run: `pytest test/phy/test_s7_gtx.py -v`

Expected: FAIL with "No module named 'litepcie.phy.transceivers.s7_gtx'"

### Step 3: Create GTX wrapper structure

Create directory:

```bash
mkdir -p litepcie/phy/transceivers
touch litepcie/phy/transceivers/__init__.py
```

Create `litepcie/phy/transceivers/s7_gtx.py`:

```python
#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Xilinx 7-Series GTX Transceiver Wrapper for PCIe.

Provides PIPE-compliant interface to GTX transceivers for soft PCIe implementation.
Supports Gen1 (2.5 GT/s) and Gen2 (5.0 GT/s) with 8b/10b encoding.

References
----------
- Xilinx UG476: 7 Series FPGAs GTX/GTH Transceivers User Guide
- PCIe Base Spec 4.0
- Intel PIPE 3.0 Specification
"""

from migen import *
from litex.gen import LiteXModule


class S7GTXTransceiver(LiteXModule):
    """
    Xilinx 7-Series GTX transceiver wrapper.

    Wraps GTXE2_CHANNEL primitive with PIPE interface for PCIe.

    Parameters
    ----------
    refclk : Signal, optional
        Reference clock (100 MHz)
    gen : int, optional
        PCIe generation (1=Gen1 2.5GT/s, 2=Gen2 5.0GT/s)

    Attributes
    ----------
    PIPE TX Interface:
    pipe_tx_data : Signal(8), input
        TX data from DLL layer
    pipe_tx_datak : Signal(1), input
        TX K-character flag
    pipe_tx_elecidle : Signal(1), input
        TX electrical idle

    PIPE RX Interface:
    pipe_rx_data : Signal(8), output
        RX data to DLL layer
    pipe_rx_datak : Signal(1), output
        RX K-character flag
    pipe_rx_elecidle : Signal(1), output
        RX electrical idle

    SERDES Interface:
    tx_p, tx_n : Signal, output
        TX differential pair
    rx_p, rx_n : Signal, input
        RX differential pair

    Clock Outputs:
    tx_clk : Signal, output
        TX clock (125 MHz for Gen1, 250 MHz for Gen2)
    rx_clk : Signal, output
        RX recovered clock

    Notes
    -----
    GTX transceiver includes built-in 8b/10b encoder/decoder.
    Clock recovery and CDR handled by transceiver.

    References
    ----------
    - Xilinx UG476: GTX/GTH Transceivers User Guide
    """

    def __init__(self, refclk=None, gen=1):
        # PIPE interface signals (to DLL layer)
        self.pipe_tx_data     = Signal(8)
        self.pipe_tx_datak    = Signal()
        self.pipe_tx_elecidle = Signal()

        self.pipe_rx_data     = Signal(8)
        self.pipe_rx_datak    = Signal()
        self.pipe_rx_elecidle = Signal()

        # SERDES pads (to chip I/O)
        self.tx_p = Signal()
        self.tx_n = Signal()
        self.rx_p = Signal()
        self.rx_n = Signal()

        # Clock outputs
        self.tx_clk = Signal()
        self.rx_clk = Signal()

        # # #

        # TODO: Instantiate GTXE2_CHANNEL primitive
        # TODO: Configure for Gen1/Gen2 speeds
        # TODO: Enable 8b/10b encoder/decoder
        # TODO: Configure clock settings
        # TODO: Connect PIPE signals to GTX ports
```

### Step 4: Add GTX primitive instantiation

Add GTX configuration:

```python
# In S7GTXTransceiver.__init__:

# GTX Configuration Parameters
line_rate = {1: 2.5e9, 2: 5.0e9}[gen]  # 2.5 GT/s or 5.0 GT/s
tx_clk_freq = {1: 125e6, 2: 250e6}[gen]

# GTX Primitive Instance
self.specials += Instance("GTXE2_CHANNEL",
    # PMA Configuration
    p_SIM_RESET_SPEEDUP       = "TRUE",
    p_SIM_TX_EIDLE_DRIVE_LEVEL = "X",
    p_SIM_VERSION             = "4.0",

    # TX Configuration
    p_TX_DATA_WIDTH           = 20,  # 8b/10b: 8 bits -> 10 bits x 2 (DDR)
    p_TX_INT_DATAWIDTH        = 0,   # 20-bit internal

    # RX Configuration
    p_RX_DATA_WIDTH           = 20,
    p_RX_INT_DATAWIDTH        = 0,

    # 8b/10b Encoder/Decoder
    p_TX_8B10B_ENABLE         = True,
    p_RX_8B10B_ENABLE         = True,

    # Line Rate
    p_TXOUT_DIV               = 2 if gen == 1 else 1,
    p_RXOUT_DIV               = 2 if gen == 1 else 1,

    # Clock Ports
    i_TXUSRCLK                = self.tx_clk,
    i_TXUSRCLK2               = self.tx_clk,
    i_RXUSRCLK                = self.rx_clk,
    i_RXUSRCLK2               = self.rx_clk,
    o_TXOUTCLK                = self.tx_clk,
    o_RXOUTCLK                = self.rx_clk,

    # TX Data Ports
    i_TXDATA                  = Cat(self.pipe_tx_data, Replicate(0, 8)),
    i_TXCHARISK               = Cat(self.pipe_tx_datak, 0),

    # RX Data Ports
    o_RXDATA                  = Cat(self.pipe_rx_data, Signal(8)),
    o_RXCHARISK               = Cat(self.pipe_rx_datak, Signal()),

    # TX/RX Differential Ports
    o_GTXTXP                  = self.tx_p,
    o_GTXTXN                  = self.tx_n,
    i_GTXRXP                  = self.rx_p,
    i_GTXRXN                  = self.rx_n,

    # Power-Down Ports
    i_TXELECIDLE              = self.pipe_tx_elecidle,
    o_RXELECIDLE              = self.pipe_rx_elecidle,

    # ... many more GTX configuration parameters
)
```

### Step 5: Test and iterate

Run: `pytest test/phy/test_s7_gtx.py -v`

Add more tests for:
- TX data flow
- RX data flow
- K-character handling
- Clock generation
- Electrical idle

### Step 6: Commit GTX wrapper

```bash
git add litepcie/phy/transceivers/ test/phy/test_s7_gtx.py
git commit -m "feat(phy): Add Xilinx 7-Series GTX transceiver wrapper

Implement PIPE-compliant wrapper for GTX transceivers:
- GTXE2_CHANNEL primitive instantiation
- 8b/10b encoder/decoder configuration
- Gen1 (2.5 GT/s) and Gen2 (5.0 GT/s) support
- PIPE interface for DLL integration
- Clock generation and recovery

Enables soft PCIe implementation on 7-Series FPGAs without hard IP.

References:
- Xilinx UG476: GTX/GTH Transceivers

Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 9.3: UltraScale+ GTH/GTY Transceiver Wrapper

Create wrapper for UltraScale+ GTH/GTY transceivers (higher performance).

**Files:**
- Create: `litepcie/phy/transceivers/usp_gth.py`
- Create: `test/phy/test_usp_gth.py`

### Step 1-6: Similar process to Task 9.2

Follow same TDD approach:
1. Write tests for GTHE3/GTHE4 structure
2. Implement wrapper with PIPE interface
3. Configure for Gen1/Gen2 (and optionally Gen3)
4. Test clock domain crossing
5. Validate with tests
6. Commit

Key differences from GTX:
- Use GTHE3_CHANNEL (US) or GTHE4_CHANNEL (US+)
- Support higher speeds (up to 16.3 GT/s)
- Gen3 support (128b/130b encoding) - architecture only
- Different DRP (Dynamic Reconfiguration Port) interface

---

## Task 9.4: Lattice ECP5 SERDES Wrapper

Create wrapper for Lattice ECP5 SERDES (open-source FPGA target).

**Files:**
- Create: `litepcie/phy/transceivers/ecp5_serdes.py`
- Create: `test/phy/test_ecp5_serdes.py`

### Step 1-6: Similar process to Task 9.2

Follow TDD approach for ECP5:
1. Write tests for EXTREFB/DCU primitive structure
2. Implement wrapper with PIPE interface
3. Configure for Gen1 (Gen2 stretch goal - ECP5 limited to ~3 GT/s)
4. Integrate 8b/10b encoder from Task 9.1 (ECP5 doesn't have built-in)
5. Test and validate
6. Commit

Key differences:
- Use EXTREFB for clock generation
- Use DCU (Dual Channel Unit) for SERDES
- No built-in 8b/10b - use our encoder from Task 9.1
- Lower maximum speed (Gen1 primary target)
- Important for open-source toolchain (nextpnr)

---

## Task 9.5: Clock Domain Crossing for Transceiver Clocks

Implement proper CDC between transceiver clocks and system clock.

**Files:**
- Modify: `litepcie/phy/transceivers/s7_gtx.py`
- Modify: `litepcie/phy/transceivers/usp_gth.py`
- Modify: `litepcie/phy/transceivers/ecp5_serdes.py`
- Create: `test/phy/test_transceiver_cdc.py`

### Step 1: Write failing test for CDC

```python
# test/phy/test_transceiver_cdc.py

def test_tx_data_cdc_from_sys_to_txclk(self):
    """
    TX data must cross from system clock to TX clock domain.

    PIPE interface operates in system clock domain.
    GTX transceiver TX operates in txusrclk domain.
    Need proper CDC with FIFO to prevent metastability.
    """
    # Test TX CDC functionality
    pass

def test_rx_data_cdc_from_rxclk_to_sys(self):
    """
    RX data must cross from RX clock to system clock domain.

    RX recovered clock is asynchronous to system clock.
    Need CDC FIFO with proper synchronization.
    """
    # Test RX CDC functionality
    pass
```

### Step 2: Implement CDC in wrappers

Add AsyncFIFO for TX and RX paths:

```python
# In each transceiver wrapper:

# TX CDC: sys clock -> tx clock
self.submodules.tx_cdc = tx_cdc = stream.AsyncFIFO(
    layout=[("data", 8), ("datak", 1)],
    depth=8,
    cd_from="sys",
    cd_to="tx",
)

# RX CDC: rx clock -> sys clock
self.submodules.rx_cdc = rx_cdc = stream.AsyncFIFO(
    layout=[("data", 8), ("datak", 1)],
    depth=8,
    cd_from="rx",
    cd_to="sys",
)
```

### Step 3: Test CDC timing

Add timing verification:
- Test data integrity across clock domains
- Verify FIFO depth is sufficient
- Check for overflow/underflow conditions

### Step 4: Commit CDC implementation

```bash
git add litepcie/phy/transceivers/*.py test/phy/test_transceiver_cdc.py
git commit -m "feat(phy): Add clock domain crossing for transceivers

Implement CDC between system clock and transceiver clocks:
- TX CDC: system -> TX clock domain (FIFO-based)
- RX CDC: RX recovered clock -> system (FIFO-based)
- Proper synchronization for metastability prevention
- FIFO depth tuned for PCIe timing requirements

Critical for reliable transceiver operation.

Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 9.6: LTSSM Integration with Transceivers

Integrate LTSSM from Phase 6 with transceiver wrappers.

**Files:**
- Modify: `litepcie/phy/transceivers/s7_gtx.py`
- Create: `test/phy/test_transceiver_ltssm.py`

### Step 1: Write test for LTSSM integration

```python
def test_transceiver_ltssm_integration(self):
    """
    Transceiver should integrate with LTSSM for automatic training.

    LTSSM controls:
    - Receiver detection (rx_elecidle monitoring)
    - TS1/TS2 transmission
    - Link training sequence
    """
    pass
```

### Step 2: Add LTSSM option to transceivers

Modify transceiver wrappers:

```python
class S7GTXTransceiver(LiteXModule):
    def __init__(self, refclk=None, gen=1, enable_ltssm=False):
        # ... existing code ...

        if enable_ltssm:
            from litepcie.dll.ltssm import LTSSM

            # Instantiate LTSSM
            self.submodules.ltssm = ltssm = LTSSM(gen=gen, lanes=1)

            # Connect LTSSM to PIPE interface
            # (connects to PIPEInterface from previous phases)
            self.comb += [
                ltssm.rx_elecidle.eq(self.pipe_rx_elecidle),
                self.pipe_tx_elecidle.eq(ltssm.tx_elecidle),
                # ... TS1/TS2 connections via PIPEInterface
            ]

            # Expose link status
            self.link_up = ltssm.link_up
```

### Step 3: Test automatic link training

Add loopback test:
- GTX TX -> GTX RX loopback
- LTSSM automatically trains link
- Verify link_up signal

### Step 4: Commit LTSSM integration

```bash
git add litepcie/phy/transceivers/*.py test/phy/test_transceiver_ltssm.py
git commit -m "feat(phy): Integrate LTSSM with transceivers

Add LTSSM support to transceiver wrappers:
- Optional enable_ltssm parameter
- Automatic link training without manual control
- Receiver detection via electrical idle
- Link status monitoring

Enables fully automatic PCIe link initialization.

Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 9.7: Gen3 Architecture (128b/130b Encoding)

Design architecture for Gen3 support (implementation deferred).

**Files:**
- Create: `docs/gen3-architecture.md`
- Create: `litepcie/phy/encoding/encoder_128b130b.py` (stub)

### Step 1: Document Gen3 architecture

Create architecture document:

```markdown
# Gen3 (8.0 GT/s) Architecture

## Overview

Gen3 PCIe uses 128b/130b encoding instead of 8b/10b:
- Higher efficiency: 98.46% vs 80%
- Lower overhead
- Different scrambling algorithm

## Implementation Strategy

### Phase 1: 128b/130b Encoder/Decoder
- Implement 128b/130b encoding algorithm
- Scrambling/descrambling (LFSR-based)
- Sync header insertion (2-bit: 01 or 10)

### Phase 2: Transceiver Gen3 Support
- Configure GTH/GTY for 8.0 GT/s
- Disable 8b/10b, use raw mode
- Implement custom 128b/130b in gateware

### Phase 3: Gen3 LTSSM States
- Add Gen3-specific states
- Equalization support
- Phase 2/3 training

## References
- PCIe Spec 4.0, Section 4.2.3: 128b/130b Encoding
```

### Step 2: Create encoder stub

```python
# litepcie/phy/encoding/encoder_128b130b.py

"""
128b/130b Encoder for PCIe Gen3.

Implements 128b/130b encoding scheme used in PCIe Gen3 (8.0 GT/s).

Status: ARCHITECTURE ONLY - Implementation deferred to future phase.

References:
- PCIe Base Spec 4.0, Section 4.2.3
"""

from migen import *

class Encoder128b130b(Module):
    """
    128b/130b Encoder (Gen3).

    TODO: Implement full encoding logic
    - 128-bit to 130-bit encoding
    - Sync header (2-bit: 01 or 10)
    - LFSR-based scrambling
    """
    def __init__(self):
        self.d_input  = Signal(128)  # 128-bit input
        self.d_output = Signal(130)  # 130-bit output with sync header

        # TODO: Implement encoding
        pass
```

### Step 3: Commit Gen3 architecture

```bash
git add docs/gen3-architecture.md litepcie/phy/encoding/encoder_128b130b.py
git commit -m "docs(phy): Add Gen3 architecture design

Document Gen3 (8.0 GT/s) support architecture:
- 128b/130b encoding scheme
- Transceiver configuration approach
- LTSSM extensions needed

Create encoder stub for future implementation.
Gen3 support deferred to future phase but architecture defined.

References:
- PCIe Spec 4.0, Section 4.2.3

Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 9.8: Transceiver PHY Wrapper Integration

Create high-level PHY wrappers that integrate transceivers with DLL/LTSSM.

**Files:**
- Create: `litepcie/phy/s7_pipe_phy.py`
- Create: `test/phy/test_s7_pipe_phy.py`

### Step 1: Write test for integrated PHY

```python
def test_s7_pipe_phy_drop_in_replacement(self):
    """
    S7PipePHY should be drop-in replacement for S7PCIEPHY.

    Must provide same interface:
    - sink/source endpoints
    - msi endpoint
    - data_width, bar0_mask attributes
    - Compatible with LitePCIeEndpoint
    """
    phy = S7PipePHY(platform, pads, data_width=64)

    # Check required attributes
    assert hasattr(phy, 'sink')
    assert hasattr(phy, 'source')
    assert hasattr(phy, 'msi')
    assert hasattr(phy, 'data_width')
    assert hasattr(phy, 'bar0_mask')
```

### Step 2: Create integrated PHY wrapper

```python
# litepcie/phy/s7_pipe_phy.py

class S7PipePHY(LiteXModule):
    """
    Xilinx 7-Series PCIe PHY using soft PIPE implementation.

    Drop-in replacement for S7PCIEPHY that uses:
    - GTX transceivers (from Task 9.2)
    - Our DLL layer (from Phase 4)
    - Our LTSSM (from Phase 6)
    - Our PIPE interface (from Phase 3)

    Instead of Xilinx hard IP block.
    """

    def __init__(self, platform, pads, data_width=64, cd="sys",
                 bar0_size=0x100000):
        # Required interface (same as S7PCIEPHY)
        self.sink = stream.Endpoint(phy_layout(data_width))
        self.source = stream.Endpoint(phy_layout(data_width))
        self.msi = stream.Endpoint(msi_layout())

        self.data_width = data_width
        self.bar0_mask = get_bar_mask(bar0_size)

        # # #

        # GTX Transceiver
        self.submodules.gtx = S7GTXTransceiver(gen=1, enable_ltssm=True)

        # PIPE Interface (connects GTX to DLL)
        self.submodules.pipe = PIPEInterface(
            data_width=8,
            gen=1,
            enable_ltssm=True,
            enable_training_sequences=True,
            enable_skp=True,
        )

        # Connect GTX to PIPE
        self.comb += [
            self.pipe.pipe_tx_data.eq(self.gtx.pipe_tx_data),
            self.gtx.pipe_rx_data.eq(self.pipe.pipe_rx_data),
            # ... more connections
        ]

        # DLL Layer
        self.submodules.dll_tx = DLLTX(data_width=64)
        self.submodules.dll_rx = DLLRX(data_width=64)

        # Connect PIPE to DLL
        # ... (from pipe_external_phy.py pattern)

        # Connect DLL to endpoint (sink/source)
        # ... (using PHYTXDatapath/PHYRXDatapath)
```

### Step 3: Test integration

Write integration tests:
- End-to-end data flow
- TLP layer -> DLL -> PIPE -> GTX -> loopback
- MSI interrupt handling
- Link training

### Step 4: Commit integrated PHY

```bash
git add litepcie/phy/s7_pipe_phy.py test/phy/test_s7_pipe_phy.py
git commit -m "feat(phy): Add S7 soft PIPE PHY implementation

Create complete soft PCIe PHY for 7-Series:
- Integrates GTX transceiver wrapper
- Uses our DLL layer
- Uses our LTSSM for automatic training
- Drop-in replacement for S7PCIEPHY hard IP

Enables vendor-IP-free PCIe on 7-Series FPGAs.

Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 9.9: Testing Strategy and Validation

Create comprehensive testing strategy for transceiver support.

**Files:**
- Create: `docs/transceiver-testing-guide.md`
- Create: `test/phy/test_transceiver_loopback.py`
- Create: `test/phy/test_transceiver_integration.py`

### Step 1: Document testing approach

```markdown
# Transceiver Testing Guide

## Unit Tests

### Encoder/Decoder Tests
- 8b/10b encoding correctness
- K-character handling
- Running disparity
- Error detection

### Transceiver Wrapper Tests
- Signal presence
- Clock generation
- Basic data flow

## Integration Tests

### Loopback Tests
- GTX TX -> GTX RX internal loopback
- Verify data integrity
- Test at Gen1 and Gen2 speeds

### LTSSM Integration Tests
- Automatic link training
- State transitions
- Recovery handling

## Hardware Validation (future)

### FPGA Testing
- Deploy to 7-Series FPGA
- External loopback (TX -> RX cable)
- Connect to PCIe root complex
- Enumerate and test TLPs

### Performance Testing
- Bandwidth measurement
- Latency measurement
- Error rate testing
```

### Step 2: Create loopback tests

```python
# test/phy/test_transceiver_loopback.py

def test_gtx_internal_loopback_gen1(self):
    """
    Test GTX loopback at Gen1 speed (2.5 GT/s).

    Send known pattern through GTX TX, receive on RX.
    Verify data integrity and K-character handling.
    """
    pass

def test_gtx_loopback_with_ltssm(self):
    """
    Test automatic link training in loopback.

    LTSSM should:
    1. Detect receiver (exit electrical idle)
    2. Exchange TS1 ordered sets
    3. Exchange TS2 ordered sets
    4. Reach L0 state
    5. Assert link_up
    """
    pass
```

### Step 3: Create integration test suite

Write tests covering:
- Full datapath (TLP -> DLL -> PIPE -> GTX)
- Multiple transceivers (x4, x8 multi-lane)
- Error injection and recovery
- Clock domain crossing validation

### Step 4: Run full test suite

```bash
# Run all transceiver tests
pytest test/phy/ -v --cov=litepcie/phy --cov-report=term-missing

# Check coverage targets:
# - encoder_8b10b.py: >90%
# - s7_gtx.py: >85%
# - Integration: >80%
```

### Step 5: Commit testing suite

```bash
git add docs/transceiver-testing-guide.md test/phy/test_transceiver_*.py
git commit -m "test(phy): Add comprehensive transceiver test suite

Add testing infrastructure for transceivers:
- Unit tests for encoders and wrappers
- Integration tests with LTSSM
- Loopback tests for data integrity
- Testing guide documentation

Achieves >85% coverage on transceiver code.

Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 9.10: Documentation and Completion

Create comprehensive documentation for Phase 9.

**Files:**
- Create: `docs/transceiver-integration-guide.md`
- Create: `docs/phase-9-completion-summary.md`
- Update: `docs/implementation-status.md`

### Step 1: Write integration guide

```markdown
# Transceiver Integration Guide

## Overview

This guide explains how to use internal FPGA transceivers with LitePCIe
instead of external PHY chips or vendor hard IP blocks.

## Supported Transceivers

### Xilinx 7-Series GTX
- FPGAs: Artix-7, Kintex-7, Virtex-7
- Speed: Gen1 (2.5 GT/s), Gen2 (5.0 GT/s)
- Lanes: x1, x4, x8
- Example: Artix-7 XC7A100T

### Xilinx UltraScale+ GTH/GTY
- FPGAs: Kintex US+, Virtex US+
- Speed: Gen1, Gen2, Gen3 (architecture)
- Lanes: x1, x4, x8, x16
- Higher performance than GTX

### Lattice ECP5 SERDES
- FPGAs: LFE5U/LFE5UM series
- Speed: Gen1 (2.5 GT/s)
- Lanes: x1, x4
- Open-source toolchain support

## Usage Examples

### Basic 7-Series Usage

```python
from litepcie.phy.s7_pipe_phy import S7PipePHY

# Create PHY with GTX transceiver
phy = S7PipePHY(
    platform   = platform,
    pads       = platform.request("pcie_x1"),
    data_width = 64,
    cd         = "sys",
    bar0_size  = 0x100000,
)

# Use with LitePCIe endpoint (same as vendor PHY)
endpoint = LitePCIeEndpoint(phy, address_width=32)
```

### Advanced Configuration

```python
# Multi-lane with Gen2
phy = S7PipePHY(
    platform   = platform,
    pads       = platform.request("pcie_x4"),
    data_width = 128,
    gen        = 2,  # Gen2 (5.0 GT/s)
    lanes      = 4,  # x4 link
)
```

## Architecture

```
TLP Layer (User Logic)
    ↓
DLL Layer (ACK/NAK, Retry, LCRC)
    ↓
PIPE Interface (8-bit symbols + K-chars)
    ↓
Transceiver Wrapper (GTX/GTH/SERDES)
    ↓
8b/10b Encoder/Decoder
    ↓
SERDES (Physical signaling)
```

## Benefits

### Vendor IP Independence
- No Xilinx PCIe hard IP license needed
- Works on FPGAs without PCIe blocks
- Portable across vendors

### Educational Value
- Understand PCIe internals
- Debug at all protocol layers
- Customize behavior

### Flexibility
- Custom link training
- Non-standard speeds
- Research applications

## Limitations

### Performance
- Soft implementation uses more resources
- Slightly higher latency than hard IP
- Gen3 requires more development

### Testing
- Requires hardware validation
- PCIe compliance testing needed
- More complex than hard IP

## Hardware Setup

### FPGA Board Requirements
- GTX/GTH/SERDES transceivers
- PCIe edge connector or adapter
- Reference clock (100 MHz)
- Proper PCB impedance matching

### Connection Options
1. PCIe edge connector (desktop)
2. M.2 adapter (laptop/mini-PC)
3. Thunderbolt PCIe adapter
4. Development board with PCIe

## Troubleshooting

### Link Won't Train
- Check reference clock (100 MHz)
- Verify TX/RX differential pairs
- Check LTSSM state (should reach L0)
- Verify electrical idle signaling

### Data Corruption
- Check clock domain crossing
- Verify 8b/10b encoding
- Test RX equalization settings
- Check for metastability

### Performance Issues
- Profile with VCD waveforms
- Check FIFO depths (CDC)
- Verify clock frequencies
- Monitor retry buffer usage

## References
- Xilinx UG476: GTX/GTH Transceivers
- PCIe Base Spec 4.0
- Intel PIPE 3.0 Specification
```

### Step 2: Write completion summary

```markdown
# Phase 9: Internal Transceiver Support - Completion Summary

**Date:** 2025-10-17 (planned)
**Status:** Planned (not yet implemented)

## Overview

Phase 9 will integrate our PIPE/DLL implementation with FPGA internal
transceivers, enabling soft PCIe implementation without vendor hard IP.

## Planned Tasks

### Task 9.1: 8b/10b Encoder/Decoder ⏳
- Implement Widmer & Franaszek 8b/10b encoding
- Support data and K-characters
- Running disparity tracking
- Decoder with error detection

### Task 9.2: Xilinx 7-Series GTX Wrapper ⏳
- GTXE2_CHANNEL primitive wrapper
- PIPE interface compliance
- Gen1/Gen2 support
- Clock generation

### Task 9.3: UltraScale+ GTH/GTY Wrapper ⏳
- GTHE3/GTHE4 primitive wrapper
- Higher performance
- Gen3 architecture support
- Advanced DRP configuration

### Task 9.4: Lattice ECP5 SERDES Wrapper ⏳
- EXTREFB/DCU primitive wrapper
- Open-source toolchain support
- Software 8b/10b integration
- Gen1 support

### Task 9.5: Clock Domain Crossing ⏳
- TX CDC (sys -> tx clock)
- RX CDC (rx clock -> sys)
- AsyncFIFO implementation
- Timing verification

### Task 9.6: LTSSM Integration ⏳
- Connect LTSSM to transceivers
- Automatic link training
- Receiver detection
- Link status monitoring

### Task 9.7: Gen3 Architecture ⏳
- 128b/130b encoding design
- Architecture documentation
- Implementation stubs
- Future roadmap

### Task 9.8: PHY Wrapper Integration ⏳
- Drop-in replacement PHYs
- S7PipePHY, USPPipePHY, ECP5PipePHY
- Full stack integration
- TLP to transceiver datapath

### Task 9.9: Testing Strategy ⏳
- Unit tests (encoders, wrappers)
- Integration tests (loopback)
- LTSSM training tests
- Hardware validation plan

### Task 9.10: Documentation ⏳
- Integration guide
- Troubleshooting guide
- Testing guide
- Completion summary

## Expected Deliverables

### Code
- `litepcie/phy/encoding/encoder_8b10b.py` - 8b/10b encoder/decoder
- `litepcie/phy/transceivers/s7_gtx.py` - 7-Series GTX wrapper
- `litepcie/phy/transceivers/usp_gth.py` - UltraScale+ GTH wrapper
- `litepcie/phy/transceivers/ecp5_serdes.py` - ECP5 SERDES wrapper
- `litepcie/phy/s7_pipe_phy.py` - Integrated 7-Series PHY
- `litepcie/phy/usp_pipe_phy.py` - Integrated UltraScale+ PHY
- `litepcie/phy/ecp5_pipe_phy.py` - Integrated ECP5 PHY

### Tests
- 20+ unit tests for encoders
- 15+ tests per transceiver wrapper
- 10+ integration tests
- Hardware validation procedures

### Documentation
- Transceiver integration guide
- Testing guide
- Gen3 architecture document
- API documentation

## Technical Achievements

### 8b/10b Encoding
- Correct encoding/decoding tables
- K-character support
- Running disparity tracking
- Error detection

### Transceiver Wrappers
- PIPE-compliant interfaces
- Gen1/Gen2 support
- Proper clock generation
- Electrical idle handling

### Integration
- Works with existing DLL layer
- LTSSM automatic training
- Drop-in replacement for hard IP
- Portable across FPGA vendors

## Benefits

### Vendor IP Independence
- No Xilinx PCIe license required
- Works on non-PCIe FPGAs
- Open-source friendly (ECP5)
- Educational value

### Flexibility
- Customizable at all layers
- Debug visibility
- Research applications
- Non-standard configurations

### Portability
- Same code across vendors
- Easier migration
- Unified testing
- Consistent behavior

## Known Limitations

### Performance
- Higher resource usage than hard IP
- Slightly higher latency
- Gen3 needs more work
- Single-lane focus initially

### Validation
- Requires hardware testing
- PCIe compliance testing needed
- More complex debug
- Limited Gen2/multi-lane testing

## Future Work

### Short Term
- Hardware validation on real FPGAs
- Multi-lane support (x4, x8)
- Gen2 optimization
- Compliance testing

### Medium Term
- Full Gen3 implementation
- Advanced equalization
- Power management (L0s, L1)
- Performance optimization

### Long Term
- Gen4 support (16 GT/s)
- Gen5 exploration (32 GT/s)
- More FPGA families
- Production hardening

## Timeline (Estimated)

- **Task 9.1-9.2**: 2-3 days (8b/10b + GTX)
- **Task 9.3-9.4**: 2 days (US+ and ECP5)
- **Task 9.5-9.6**: 1-2 days (CDC + LTSSM)
- **Task 9.7**: 0.5 day (Gen3 architecture)
- **Task 9.8**: 1-2 days (Integration)
- **Task 9.9**: 1-2 days (Testing)
- **Task 9.10**: 1 day (Documentation)

**Total:** 8-13 days development time

Note: Hardware validation adds 2-4 weeks (board bring-up, debugging, compliance)

## References

### Specifications
- PCIe Base Spec 4.0
- Intel PIPE 3.0 Specification
- Widmer & Franaszek 8B/10B paper

### Vendor Docs
- Xilinx UG476: 7 Series GTX/GTH Transceivers
- Xilinx UG576: UltraScale GTH Transceivers
- Lattice FPGA-TN-02032: ECP5 SERDES Usage Guide

### Implementation
- docs/transceiver-integration-guide.md
- docs/transceiver-testing-guide.md
- docs/gen3-architecture.md

## Conclusion

Phase 9 represents a major milestone: **vendor-IP-free PCIe implementation**.

By integrating transceivers with our PIPE/DLL/LTSSM stack, we achieve:

✅ **Independence**: No vendor PCIe blocks needed

✅ **Portability**: Works across FPGA families

✅ **Transparency**: Full visibility into PHY layer

✅ **Flexibility**: Customizable at all layers

This completes the path from TLP layer (user) down to physical signaling
(transceivers), all in open-source gateware.

**Next Steps:** Hardware validation and Gen3 implementation.
```

### Step 3: Update implementation status

Update `docs/implementation-status.md`:

```markdown
## Phase 9: Internal Transceiver Support (Planned)

**Status:** PLANNED
**Date:** TBD
**Plan:** `docs/plans/2025-10-17-phase-9-internal-transceiver-support.md`

### Planned Features
- 8b/10b encoder/decoder
- Xilinx 7-Series GTX wrapper
- UltraScale+ GTH/GTY wrapper
- Lattice ECP5 SERDES wrapper
- Clock domain crossing
- LTSSM integration
- Gen3 architecture
- Comprehensive testing

### Dependencies
- Phases 3-6 complete (PIPE, DLL, LTSSM)
- Hardware for validation

### Timeline
- Development: 8-13 days
- Hardware validation: 2-4 weeks
```

### Step 4: Commit documentation

```bash
git add docs/transceiver-integration-guide.md docs/phase-9-completion-summary.md docs/implementation-status.md
git commit -m "docs: Add Phase 9 implementation plan and guides

Create comprehensive Phase 9 documentation:
- Implementation plan with TDD structure
- Transceiver integration guide
- Testing strategy
- Gen3 architecture design
- Completion summary (planned)

Phase 9 will enable soft PCIe implementation with FPGA transceivers,
removing dependency on vendor hard IP blocks.

Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Success Criteria

**Functionality:**
- ✅ 8b/10b encoder/decoder working correctly
- ✅ GTX transceiver wrapper with PIPE interface
- ✅ UltraScale+ GTH/GTY wrapper functional
- ✅ ECP5 SERDES wrapper (Gen1 minimum)
- ✅ Clock domain crossing validated
- ✅ LTSSM integration working
- ✅ Gen3 architecture documented
- ✅ Drop-in PHY replacements complete

**Testing:**
- ✅ Unit tests for encoders (>90% coverage)
- ✅ Unit tests for wrappers (>85% coverage)
- ✅ Integration tests (loopback, LTSSM)
- ✅ Hardware validation plan documented
- ✅ Testing guide complete

**Code Quality:**
- ✅ >85% code coverage on transceivers
- ✅ All tests passing
- ✅ Pre-commit hooks pass
- ✅ Follows project standards
- ✅ Comprehensive docstrings

**Documentation:**
- ✅ Integration guide complete
- ✅ Testing guide complete
- ✅ Gen3 architecture documented
- ✅ Troubleshooting section
- ✅ Hardware setup guide

**Hardware Validation (stretch goal):**
- ⏳ Deploy to 7-Series FPGA
- ⏳ External loopback test passes
- ⏳ Enumerate with PCIe root complex
- ⏳ Basic TLP transactions work

---

## Timeline

- **Task 9.1**: 8b/10b encoder/decoder - 1.5 days
- **Task 9.2**: GTX wrapper - 1.5 days
- **Task 9.3**: UltraScale+ wrapper - 1 day
- **Task 9.4**: ECP5 wrapper - 1 day
- **Task 9.5**: CDC implementation - 1 day
- **Task 9.6**: LTSSM integration - 1 day
- **Task 9.7**: Gen3 architecture - 0.5 day
- **Task 9.8**: PHY integration - 1.5 days
- **Task 9.9**: Testing strategy - 1.5 days
- **Task 9.10**: Documentation - 1 day

**Total:** ~11.5 days development time

**Hardware Validation:** +2-4 weeks (not in this plan)

---

## Notes

### Implementation Priorities

1. **Critical Path**: 8b/10b encoder -> GTX wrapper -> Integration
2. **Parallel Work**: Other transceivers (US+, ECP5) can be done in parallel
3. **Stretch Goals**: Gen3, multi-lane, hardware validation

### Transceiver Complexity

- GTX is most complex (many configuration parameters)
- Each primitive has 100+ ports
- CDC is critical for reliability
- Testing requires hardware ideally

### Gen3 Scope

- Architecture documented but implementation deferred
- 128b/130b encoding is complex
- Requires different LTSSM states
- Can be Phase 10 if needed

### Hardware Requirements

For validation (not required for plan completion):
- 7-Series FPGA board with GTX and PCIe connector
- PCIe cable or adapter
- Host system with PCIe slot
- Logic analyzer (helpful)

### Comparison with Hard IP

**Hard IP Advantages:**
- Less FPGA resources
- Proven compliance
- Better performance
- Xilinx support

**Soft Implementation Advantages:**
- No license needed
- Works on any FPGA with transceivers
- Full debug visibility
- Customizable
- Educational
- Open-source friendly

### Open Source Impact

ECP5 SERDES support especially important:
- Works with nextpnr (open toolchain)
- No proprietary IP
- Enables open-source PCIe development
- Research and education

---

## Risk Mitigation

### Technical Risks

**Risk:** 8b/10b encoder has subtle bugs
**Mitigation:** Extensive unit tests, validate against known test vectors

**Risk:** GTX configuration is complex
**Mitigation:** Start with Xilinx examples, use simulation, reference UG476

**Risk:** Clock domain crossing issues cause data corruption
**Mitigation:** Proven AsyncFIFO implementation, timing analysis, test thoroughly

**Risk:** Hardware validation reveals issues
**Mitigation:** Plan for iteration, use logic analyzer, reference working designs

### Schedule Risks

**Risk:** GTX wrapper takes longer than estimated
**Mitigation:** This is critical path - allocate buffer time, get help if needed

**Risk:** Hardware validation blocked on FPGA board availability
**Mitigation:** Hardware validation is stretch goal, can be follow-on work

**Risk:** Gen3 architecture proves more complex
**Mitigation:** Gen3 is already scoped as architecture only, implementation separate

### Scope Risks

**Risk:** Multi-lane support adds complexity
**Mitigation:** Focus on x1 initially, multi-lane as follow-on

**Risk:** Gen2 testing reveals issues
**Mitigation:** Gen1 is primary focus, Gen2 stretch goal

**Risk:** ECP5 has limited SERDES capabilities
**Mitigation:** Focus on Gen1 only for ECP5, document limitations

---

## Success Metrics

### Quantitative
- 8b/10b encoder: >90% test coverage
- Transceiver wrappers: >85% coverage
- Integration tests: >80% coverage
- All tests passing (100%)
- Documentation: >3000 lines

### Qualitative
- Code follows project patterns
- Clean integration with existing phases
- Clear documentation for users
- Architecture supports future Gen3
- Drop-in replacement working

### Validation (if hardware available)
- Link trains to L0 on FPGA
- Enumerates with host
- Basic read/write works
- No electrical violations (optional)

---

## Conclusion

Phase 9 completes the full PCIe stack from TLP to physical layer using only
soft gateware implementation. This is a **major milestone** toward vendor-IP-free
PCIe on FPGAs.

By integrating transceivers with our PIPE/DLL/LTSSM layers (Phases 3-6), we create
a complete, portable, open-source PCIe implementation.

The TDD approach ensures reliability, the modular architecture allows incremental
development, and the documentation enables others to use and extend this work.

**This plan is ready for execution!**
