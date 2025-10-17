# Phase 9: Internal Transceiver Support Implementation Plan v2

**Date:** 2025-10-17
**Status:** NOT STARTED
**Version:** 2.0 (Research-Based)
**Goal:** Replace external PIPE PHY with FPGA internal transceivers using insights from ECP5-PCIe, usb3_pipe, and LUNA reference implementations.

**Tech Stack:** Migen/LiteX, Xilinx GTX/GTY/GTH, Lattice ECP5 SERDES, 8b/10b encoding

---

## Context

**Current State (Post Phase 8):**
- Phases 3-7 complete: PIPE interface, DLL, LTSSM with Gen2/multi-lane support
- Phase 8 Tasks 8.1-8.4 complete: Layout converters, DLL integration, debugging tools
- Current architecture: `TLP → DLL → PIPE → External PHY chip`
- External PHY uses either vendor hard IP or physical PHY chips

**Why Internal Transceivers:**
1. **Cost Reduction:** Eliminate external PHY chips (e.g., PI7C9X2G304)
2. **Open Source:** Enable nextpnr/open toolchain support (ECP5)
3. **Vendor Independence:** No Xilinx PCIe hard IP license needed
4. **Educational:** Full visibility into physical layer
5. **Flexibility:** Customize physical layer behavior

**Target FPGAs:**
- **Xilinx 7-Series:** Artix-7, Kintex-7, Virtex-7 (GTXE2)
- **Xilinx UltraScale+:** Kintex/Virtex US+ (GTHE3/GTHE4/GTYE4)
- **Lattice ECP5:** LFE5U/LFE5UM series (DCU/DCUA)

---

## Research Summary

### 1. ECP5-PCIe Analysis

**Key Files Analyzed:**
- `Gateware/ecp5_pcie/ecp5_serdes.py` - DCU configuration (685 lines)
- `Gateware/ecp5_pcie/serdes.py` - PCIe SERDES interface (395 lines)
- `Gateware/ecp5_pcie/phy.py` - PHY layer integration (133 lines)
- `Gateware/ecp5_pcie/ecp5_phy_x1.py` - Complete PHY wrapper (82 lines)

**Architecture Insights:**
```
PCIePhy
  ├── PCIeScrambler (wraps lane with scrambling)
  ├── PCIePhyRX (receive path)
  ├── PCIePhyTX (transmit path)
  ├── PCIeLTSSM (link training state machine)
  ├── PCIeDLL (data link layer)
  └── TLP (transaction layer)
```

**Key Patterns to Adopt:**
1. **Amaranth/Migen HDL:** Uses modern Python HDL (we need to adapt to Migen)
2. **Symbol-based Interface:** 9-bit symbols (8 data + 1 K-char bit)
3. **Gearing:** 1:2 or 1:4 gearing (multiple symbols per clock)
4. **Control Symbols:** Enum class for K-characters (COM, SKP, FTS, etc.)
5. **Aligner Module:** Separate `PCIeSERDESAligner` for comma alignment
6. **Scrambler Module:** Separate `PCIeScrambler` with LFSR
7. **Clock Domains:** Separate RX and TX clock domains
8. **Reset Sequencing:** Complex FSM for DCU initialization

**ECP5-Specific Considerations:**
- Uses DCUA primitive (Dual Channel Unit)
- No built-in 8b/10b - must implement in gateware
- SCI (SerDes Client Interface) for runtime configuration
- Receiver detection via `pcie_det_en`, `pcie_ct`, `pcie_done`
- Speed switching between 2.5 GT/s and 5.0 GT/s via `divide_clk`
- Reference clock options: 100 MHz or 200 MHz
- CTC FIFO for clock tolerance compensation

**Code Snippet - DCU Configuration:**
```python
# From ecp5_serdes.py lines 432-480
dcu_config = {
    "p_D_MACROPDB": "0b1",
    "p_D_TXPLL_PWDNB": "0b1",
    "p_D_REFCK_MODE": "0b100",   # 25x ref_clk
    "p_D_TX_MAX_RATE": "5.0" if speed_5GTps else "2.5",
    "p_D_TX_VCO_CK_DIV": "0b000",  # DIV/1
    # ... many more parameters
}

ch_config = {
    "p_CHx_PROTOCOL": "PCIe",
    "p_CHx_PCIE_MODE": "0b1",
    "p_CHx_RTERM_RX": "0d22",    # 50 Ohm
    "p_CHx_RX_GEAR_MODE": gearing_str,
    "p_CHx_CDR_MAX_RATE": "5.0" if speed_5GTps else "2.5",
    # ... 60+ configuration parameters
}
```

### 2. usb3_pipe Analysis

**Key Files Analyzed:**
- `usb3_pipe/serdes.py` - GTX/GTP wrapper (569 lines)
- `usb3_pipe/common.py` - K-character definitions
- `usb3_pipe/scrambling.py` - LFSR scrambler

**Architecture Insights:**
```
K7USB3SerDes / A7USB3SerDes
  ├── TXDatapath (sys → tx clock domain)
  │   ├── TXSKPInserter (clock compensation)
  │   ├── AsyncFIFO (CDC)
  │   └── StrideConverter (32-bit → phy_dw)
  ├── RXDatapath (rx clock → sys domain)
  │   ├── StrideConverter (phy_dw → 32-bit)
  │   ├── AsyncFIFO (CDC)
  │   ├── RXSKPRemover (clock compensation)
  │   └── RXWordAligner (comma alignment)
  ├── GTX/GTP primitive (from liteiclink)
  └── RXErrorSubstitution (K28.4 for errors)
```

**Key Patterns to Adopt:**
1. **Clock Domain Crossing:** AsyncFIFO for sys ↔ transceiver clocks
2. **Data Width Adaptation:** StrideConverter (32-bit ↔ phy native width)
3. **SKP Ordered Sets:** Automatic insertion (TX) and removal (RX)
4. **Clock Compensation:** 1 SKP set every 354 symbols (PCIe requirement)
5. **Word Alignment:** Searches for COM symbols, applies barrel shift
6. **Error Handling:** Replace 8b/10b errors with K28.4 symbol
7. **Buffering:** All datapath stages use stream.BufferizeEndpoints
8. **LiteICLink Integration:** Use existing GTX/GTP primitives from liteiclink

**Code Snippet - TX Datapath:**
```python
# From serdes.py lines 246-284
class TXDatapath(Module):
    def __init__(self, clock_domain="sys", phy_dw=16):
        self.sink   = stream.Endpoint([("data", 32), ("ctrl", 4)])
        self.source = stream.Endpoint([("data", phy_dw), ("ctrl", phy_dw//8)])

        # Clock compensation
        skip_inserter = TXSKPInserter()

        # Clock domain crossing
        cdc = stream.AsyncFIFO([("data", 32), ("ctrl", 4)], 8, buffered=True)
        cdc = ClockDomainsRenamer({"write": "sys", "read": clock_domain})(cdc)

        # Data-width adaptation
        converter = stream.StrideConverter(
            [("data", 32), ("ctrl", 4)],
            [("data", phy_dw), ("ctrl", phy_dw//8)])
        converter = ClockDomainsRenamer(clock_domain)(converter)

        # Flow
        self.comb += [
            self.sink.connect(skip_inserter.sink),
            skip_inserter.source.connect(cdc.sink),
            cdc.source.connect(converter.sink),
            converter.source.connect(self.source)
        ]
```

**GTX Configuration Highlights:**
```python
# From serdes.py lines 374-415
gtx = GTX(pll, tx_pads, rx_pads, sys_clk_freq,
    data_width       = 20,
    clock_aligner    = False,
    tx_buffer_enable = True,
    rx_buffer_enable = True,
    tx_polarity      = self.tx_polarity,
    rx_polarity      = self.rx_polarity)

# Override GTX parameters for USB3 (applicable to PCIe too)
gtx.gtx_params.update(
    p_RX_CM_SEL  = 0b11,
    p_RX_CM_TRIM = 0b1010,
    p_RXCDR_CFG  = rxcdr_cfgs[pll.config['d']],
    p_PMA_RSV    = 0x18480,
)
```

### 3. LUNA Analysis

**Key Files Analyzed:**
- `luna/gateware/interface/serdes_phy/xc7_gtx.py` - GTX backend (1097 lines)
- `luna/gateware/interface/serdes_phy/ecp5.py` - ECP5 backend (1207 lines)
- `luna/gateware/interface/serdes_phy/xc7.py` - Common utilities

**Architecture Insights:**
```
XC7GTXSerDesPIPE / ECP5SerDesPIPE
  ├── PLL (GTXQuadPLL / ECP5SerDesPLLConfiguration)
  ├── SerDes Channel (GTXChannel / ECP5SerDes)
  │   ├── Reset Sequencer (GTResetDeferrer / ECP5SerDesResetSequencer)
  │   ├── DRP (Dynamic Reconfiguration)
  │   ├── SCI (SerDes Client Interface - ECP5 only)
  │   └── OOB Clock Divider
  ├── LFPS Generator (USB3-specific, but pattern applicable)
  └── PIPE Interface mapping
```

**Key Patterns to Adopt:**
1. **PLL Configuration:** Separate PLL class with `compute_config()` method
2. **Reset Sequencing:** Complex FSM with multiple stages and timeouts
3. **DRP Interface:** For runtime reconfiguration (RX termination, etc.)
4. **SCI Interface:** For ECP5 parameter changes (polarity, termination)
5. **PIPE Compliance:** Direct mapping of PIPE signals to transceiver
6. **Clock Domain Management:** Local "pipe" clock domain from txoutclk
7. **Error Tracking:** Synchronize status signals across clock domains
8. **Timing Constraints:** Use platform.add_period_constraint()

**Code Snippet - GTX Reset Deferrer:**
```python
# From xc7.py (pattern)
class GTResetDeferrer(Elaboratable):
    """Per [AR43482], GTX must not reset immediately after config."""
    DEFER_CYCLES = int(50e-3 * ss_clock_frequency)  # 50ms

    def elaborate(self, platform):
        m = Module()
        timer = Signal(range(self.DEFER_CYCLES))

        with m.FSM(domain="ss"):
            with m.State("DEFER"):
                m.d.ss += timer.eq(timer + 1)
                with m.If(timer == (self.DEFER_CYCLES - 1)):
                    m.next = "READY"
            with m.State("READY"):
                m.d.comb += self.done.eq(1)
```

**ECP5 Reset Sequencer (Complex FSM):**
```python
# From ecp5.py lines 505-659
with m.FSM(domain="ss"):
    with m.State("INITIAL_RESET"):
        apply_resets(m, tx_pll=1, tx_pcs=1, rx_cdr=1, rx_pcs=1)
        m.next = "WAIT_FOR_TXPLL_LOCK"

    with m.State("WAIT_FOR_TXPLL_LOCK"):
        apply_resets(m, tx_pll=0, tx_pcs=1, rx_cdr=1, rx_pcs=1)
        with m.If(tx_pll_locked):
            m.next = "APPLY_TXPCS_RESET"

    # ... 8 more states for proper sequencing

    with m.State("IDLE"):
        apply_resets(m, tx_pll=0, tx_pcs=0, rx_cdr=0, rx_pcs=0)
        with m.If(rx_coding_err):
            m.next = "APPLY_RXPCS_RESET"  # Restart on error
```

**PIPE Interface Mapping:**
```python
# From xc7_gtx.py lines 1074-1094
m.d.comb += [
    pll.reset               .eq(self.reset),
    serdes.reset            .eq(self.reset),
    self.pclk               .eq(serdes.pclk),

    serdes.tx_elec_idle     .eq(self.tx_elec_idle),
    serdes.rx_polarity      .eq(self.rx_polarity),
    serdes.rx_eq_training   .eq(self.rx_eq_training),
    serdes.rx_termination   .eq(self.rx_termination),

    self.phy_status         .eq(~serdes.tx_ready),
    self.rx_valid           .eq(serdes.rx_valid),
    self.rx_status          .eq(serdes.rx_status),
    self.rx_elec_idle       .eq(serdes.rx_elec_idle),

    serdes.tx_data          .eq(self.tx_data),
    serdes.tx_datak         .eq(self.tx_datak),
    self.rx_data            .eq(serdes.rx_data),
    self.rx_datak           .eq(serdes.rx_datak),
]
```

---

## Common Patterns Across All Three Codebases

### 1. Symbol-Based Interface (8b/10b)
- **Data:** 8-bit byte
- **K-char:** 1-bit control flag
- **Combined:** 9-bit symbol (or 10-bit after encoding)
- **Gearing:** 1:1, 1:2, or 1:4 (multiple symbols per clock)

### 2. Clock Domain Architecture
```
sys_clk (System)
    ↓
tx_clk (Transmit - 125/250 MHz)
    ↑ AsyncFIFO
rx_clk (Receive - recovered clock)
    ↓ AsyncFIFO
sys_clk (System)
```

### 3. Transceiver Pipeline
```
User Data (32-bit)
    ↓ StrideConverter
PHY Width (16/20-bit)
    ↓ AsyncFIFO (CDC)
Transceiver Clock Domain
    ↓ 8b/10b Encoder
10-bit symbols
    ↓ SERDES
Differential pairs (TX+/TX-)
```

### 4. Common K-Characters (PCIe)
```python
COM = K(28, 5)  # 0xBC - Comma (alignment)
SKP = K(28, 0)  # 0x1C - Skip (clock comp)
FTS = K(28, 1)  # 0x3C - Fast Training Sequence
STP = K(27, 7)  # 0xFB - Start TLP
SDP = K(28, 2)  # 0x5C - Start DLLP
END = K(29, 7)  # 0xFD - End packet
EDB = K(30, 7)  # 0xFE - End bad packet
IDL = K(28, 3)  # 0x7C - Idle
```

### 5. Reset Sequencing Pattern
All three use multi-state FSMs:
1. Initial reset (all blocks in reset)
2. Release PLL reset, wait for lock
3. Release TX PCS reset
4. Wait for RX signal presence
5. Release RX CDR reset
6. Wait for CDR lock
7. Release RX PCS reset
8. Monitor for errors, restart if needed

### 6. FPGA-Specific Differences

| Feature | Xilinx GTX/GTH | Lattice ECP5 |
|---------|----------------|--------------|
| 8b/10b | Built-in hardware | Software in gateware |
| CDR | Automatic | Manual tuning required |
| Buffers | TXBUF/RXBUF primitives | CTC FIFO |
| Config | 100+ parameters | 60+ parameters + SCI |
| DRP | Yes (runtime config) | SCI interface |
| Reset | AR43482 50ms defer | Complex 8-state FSM |
| Gearing | 1:1, 1:2, 1:4 | 1:1, 1:2 |

---

## Scope

**Included in Phase 9:**
- ✅ 8b/10b encoder/decoder (software, based on LiteX patterns)
- ✅ Transceiver base abstraction (PIPETransceiver base class)
- ✅ Xilinx 7-Series GTX wrapper (GTXE2_CHANNEL)
- ✅ Xilinx UltraScale+ GTY/GTH wrapper (GTHE3/GTHE4/GTYE4)
- ✅ Lattice ECP5 SERDES wrapper (DCUA primitive)
- ✅ Clock domain crossing (AsyncFIFO-based)
- ✅ LTSSM integration hooks
- ✅ Gen1/Gen2 speed negotiation
- ✅ Testing infrastructure (loopback tests)
- ✅ Documentation and examples

**NOT Included (Future Work):**
- ❌ Gen3 (128b/130b encoding) - architecture only
- ❌ Gen4/Gen5 support
- ❌ Advanced equalization (DFE, FFE)
- ❌ Multi-lane (x4, x8, x16) - basic support only
- ❌ Hardware compliance testing
- ❌ Production-grade signal integrity tuning
- ❌ Power management (L0s, L1, L2, L3)

**Focus:**
- Gen1 (2.5 GT/s) and Gen2 (5.0 GT/s) with 8b/10b
- Single lane (x1) with x4 architecture support
- Basic transceiver configuration
- Integration with existing PIPE/DLL/LTSSM

---

## Task Breakdown

## Task 9.1: 8b/10b Encoder/Decoder Implementation

**Goal:** Create software 8b/10b encoder/decoder using LiteX patterns (not hardware primitive).

**Why Software?**
- ECP5 doesn't have built-in 8b/10b (must be gateware)
- Consistency across platforms
- Easier testing and debugging
- Can optimize for PCIe-specific usage

**Files to Create:**
- `litepcie/phy/common/encoding.py` - 8b/10b encoder/decoder
- `test/test_encoding.py` - Comprehensive tests

**Reference:**
- LiteX `litex/soc/cores/code_8b10b.py` (existing implementation)
- usb3_pipe's use of LiteX Encoder/Decoder
- ECP5-PCIe approach (study for PCIe-specific needs)

**Detailed Steps:**

### Step 1: Review LiteX 8b/10b Implementation

```bash
# Check if LiteX already has 8b/10b
find /home/tim/.local/lib/python*/site-packages/litex -name "*8b10b*" -o -name "*code*"
```

LiteX provides: `litex.soc.cores.code_8b10b.Encoder` and `Decoder`

### Step 2: Create Wrapper for PCIe Usage

```python
# litepcie/phy/common/encoding.py

from migen import *
from litex.soc.cores.code_8b10b import Encoder, Decoder

class PCIeEncoder(Module):
    """
    PCIe-optimized 8b/10b encoder.

    Wraps LiteX Encoder with PCIe-specific features:
    - Proper disparity tracking
    - K-character support
    - Running disparity initialization

    Attributes
    ----------
    sink : Record (stream-like)
        Input: 8-bit data + k flag
    source : Record (stream-like)
        Output: 10-bit encoded data
    """
    def __init__(self):
        self.sink = sink = stream.Endpoint([("d", 8), ("k", 1)])
        self.source = source = stream.Endpoint([("d", 10)])

        # # #

        encoder = Encoder(nwords=1, lsb_first=True)
        self.submodules.encoder = encoder

        self.comb += [
            encoder.d[0].eq(sink.d),
            encoder.k[0].eq(sink.k),
            source.d.eq(encoder.output[0]),
        ]
```

### Step 3: Test K-Character Encoding

```python
# test/test_encoding.py

import unittest
from migen import *
from litex.gen import run_simulation

class TestPCIeEncoder(unittest.TestCase):
    def test_k28_5_encoding(self):
        """K28.5 (COM) should encode to 0x17C or 0x283."""
        def testbench(encoder):
            # Send K28.5
            yield encoder.sink.valid.eq(1)
            yield encoder.sink.d.eq(0xBC)  # K28.5
            yield encoder.sink.k.eq(1)
            yield
            output = yield encoder.source.d
            self.assertIn(output, [0x17C, 0x283])  # RD- or RD+

        dut = PCIeEncoder()
        run_simulation(dut, testbench(dut), vcd_name="encoder.vcd")
```

### Step 4: Add Running Disparity Management

Ensure disparity is tracked correctly for PCIe requirements.

### Step 5: Create Decoder with Error Detection

```python
class PCIeDecoder(Module):
    """
    PCIe-optimized 8b/10b decoder.

    Decodes 10-bit symbols to 8-bit + K flag.
    Detects encoding errors (disparity, invalid codes).
    """
    def __init__(self):
        self.sink = stream.Endpoint([("d", 10)])
        self.source = stream.Endpoint([("d", 8), ("k", 1)])
        self.invalid = Signal()  # Encoding error flag

        # # #

        decoder = Decoder(nwords=1, lsb_first=True)
        self.submodules.decoder = decoder

        self.comb += [
            decoder.input[0].eq(self.sink.d),
            self.source.d.eq(decoder.d[0]),
            self.source.k.eq(decoder.k[0]),
            self.invalid.eq(decoder.invalid[0]),
        ]
```

### Step 6: Test Decoder Error Detection

Test invalid codes, disparity errors, etc.

### Step 7: Document and Commit

**Success Criteria:**
- ✅ Encoder correctly encodes all PCIe K-characters
- ✅ Decoder detects all error conditions
- ✅ Running disparity tracks correctly
- ✅ Tests cover >95% of code
- ✅ Compatible with LiteX stream interface

**Estimated Time:** 0.5 days (mostly testing existing LiteX code)

---

## Task 9.2: Transceiver Base Abstraction

**Goal:** Create common base class for all transceiver wrappers.

**Files to Create:**
- `litepcie/phy/common/transceiver.py` - Base classes
- `test/test_transceiver_base.py` - Base class tests

**Detailed Steps:**

### Step 1: Define Common Interface

```python
# litepcie/phy/common/transceiver.py

from migen import *
from litex.gen import LiteXModule

class PIPETransceiver(LiteXModule):
    """
    Base class for PCIe PIPE transceivers.

    Provides common interface for GTX, GTH, GTY, ECP5 SERDES.
    Subclasses implement vendor-specific primitives.

    PIPE Interface (matching our Phase 3 implementation)
    -----------------
    tx_data : Signal(data_width), input
        Transmit data from DLL
    tx_datak : Signal(data_width//8), input
        TX K-character flags
    tx_elecidle : Signal(), input
        TX electrical idle request

    rx_data : Signal(data_width), output
        Received data to DLL
    rx_datak : Signal(data_width//8), output
        RX K-character flags
    rx_elecidle : Signal(), output
        RX electrical idle status
    rx_valid : Signal(), output
        RX data valid (no errors)

    Clock Interface
    ---------------
    tx_clk : Signal(), output
        TX word clock (125/250 MHz)
    rx_clk : Signal(), output
        RX recovered clock

    Control Interface
    -----------------
    reset : Signal(), input
        Transceiver reset
    tx_ready : Signal(), output
        TX path ready
    rx_ready : Signal(), output
        RX path ready

    Parameters
    ----------
    data_width : int
        PIPE data width (8, 16, 32)
    gen : int
        PCIe generation (1=Gen1, 2=Gen2)
    """

    def __init__(self, data_width=8, gen=1):
        self.data_width = data_width
        self.gen = gen

        # PIPE Interface
        self.tx_data = Signal(data_width)
        self.tx_datak = Signal(data_width//8)
        self.tx_elecidle = Signal()

        self.rx_data = Signal(data_width)
        self.rx_datak = Signal(data_width//8)
        self.rx_elecidle = Signal()
        self.rx_valid = Signal()

        # Clock Interface
        self.tx_clk = Signal()
        self.rx_clk = Signal()

        # Control Interface
        self.reset = Signal()
        self.tx_ready = Signal()
        self.rx_ready = Signal()

    def get_line_rate(self):
        """Get line rate in GT/s."""
        return {1: 2.5e9, 2: 5.0e9, 3: 8.0e9}[self.gen]

    def get_word_clk_freq(self):
        """Get word clock frequency in Hz."""
        # For 8b/10b: word clock = line_rate / 10
        line_rate = self.get_line_rate()
        return line_rate / 10
```

### Step 2: Define TX/RX Datapath Pattern

```python
class TransceiverTXDatapath(Module):
    """
    Common TX datapath pattern from usb3_pipe.

    sys_clk domain → tx_clk domain with CDC and width conversion.
    """
    def __init__(self, phy_dw=16):
        self.sink = stream.Endpoint([("data", 32), ("ctrl", 4)])
        self.source = stream.Endpoint([("data", phy_dw), ("ctrl", phy_dw//8)])

        # # #

        # Clock domain crossing
        cdc = stream.AsyncFIFO(
            [("data", 32), ("ctrl", 4)],
            depth=8,
            buffered=True
        )
        cdc = ClockDomainsRenamer({"write": "sys", "read": "tx"})(cdc)
        self.submodules.cdc = cdc

        # Width conversion
        converter = stream.StrideConverter(
            [("data", 32), ("ctrl", 4)],
            [("data", phy_dw), ("ctrl", phy_dw//8)],
            reverse=False
        )
        converter = ClockDomainsRenamer("tx")(converter)
        self.submodules.converter = converter

        # Flow
        self.comb += [
            self.sink.connect(cdc.sink),
            cdc.source.connect(converter.sink),
            converter.source.connect(self.source),
        ]

class TransceiverRXDatapath(Module):
    """
    Common RX datapath pattern from usb3_pipe.

    rx_clk domain → sys_clk domain with CDC and width conversion.
    """
    def __init__(self, phy_dw=16):
        self.sink = stream.Endpoint([("data", phy_dw), ("ctrl", phy_dw//8)])
        self.source = stream.Endpoint([("data", 32), ("ctrl", 4)])

        # # #

        # Width conversion
        converter = stream.StrideConverter(
            [("data", phy_dw), ("ctrl", phy_dw//8)],
            [("data", 32), ("ctrl", 4)],
            reverse=False
        )
        converter = ClockDomainsRenamer("rx")(converter)
        self.submodules.converter = converter

        # Clock domain crossing
        cdc = stream.AsyncFIFO(
            [("data", 32), ("ctrl", 4)],
            depth=8,
            buffered=True
        )
        cdc = ClockDomainsRenamer({"write": "rx", "read": "sys"})(cdc)
        self.submodules.cdc = cdc

        # Flow
        self.comb += [
            self.sink.connect(converter.sink),
            converter.source.connect(cdc.sink),
            cdc.source.connect(self.source),
        ]
```

### Step 3: Define Reset Sequencer Interface

```python
class TransceiverResetSequencer(Module):
    """
    Base reset sequencer pattern.

    Subclasses implement vendor-specific timing.
    """
    def __init__(self):
        # Status inputs
        self.tx_pll_locked = Signal()
        self.rx_has_signal = Signal()
        self.rx_cdr_locked = Signal()

        # Reset outputs
        self.tx_pll_reset = Signal(reset=1)
        self.tx_pcs_reset = Signal(reset=1)
        self.rx_cdr_reset = Signal(reset=1)
        self.rx_pcs_reset = Signal(reset=1)

        # Status outputs
        self.tx_ready = Signal()
        self.rx_ready = Signal()
```

**Success Criteria:**
- ✅ Base class defines all common PIPE signals
- ✅ TX/RX datapath modules reusable
- ✅ Clear interface for vendor-specific subclasses
- ✅ Documentation for each signal

**Estimated Time:** 0.5 days

---

## Task 9.3: Xilinx 7-Series GTX Wrapper (GTXE2)

**Goal:** Wrap GTXE2_CHANNEL primitive with PIPE interface.

**Reference:** usb3_pipe K7USB3SerDes class

**Files to Create:**
- `litepcie/phy/xilinx/s7_gtx.py` - GTX wrapper
- `test/test_s7_gtx.py` - GTX tests

**Detailed Steps:**

### Step 1: Create GTX PLL Wrapper

```python
# litepcie/phy/xilinx/s7_gtx.py

from migen import *
from litex.build.xilinx import XilinxPlatform

class GTXChannelPLL(Module):
    """
    GTX Channel PLL configuration.

    Reference: usb3_pipe pattern, LUNA GTXQuadPLL
    """
    def __init__(self, refclk, refclk_freq, linerate):
        self.refclk = refclk
        self.config = self.compute_config(refclk_freq, linerate)

        # Outputs
        self.lock = Signal()

    @staticmethod
    def compute_config(refclk_freq, linerate):
        """
        Compute PLL configuration for target line rate.

        For PCIe:
        - Gen1: 2.5 GT/s (250 MHz word clock)
        - Gen2: 5.0 GT/s (250 MHz word clock with DDR)

        Reference: Xilinx UG476 Table 3-3
        """
        # Try different PLL multipliers/dividers
        for m in [1, 2]:
            for n1 in [4, 5]:
                for n2 in [1, 2, 3, 4, 5]:
                    vco_freq = refclk_freq * (n1 * n2) / m
                    if 1.6e9 <= vco_freq <= 3.3e9:
                        for d in [1, 2, 4, 8, 16]:
                            current_linerate = vco_freq * 2 / d
                            if current_linerate == linerate:
                                return {
                                    "n1": n1, "n2": n2, "m": m, "d": d,
                                    "vco_freq": vco_freq,
                                    "linerate": linerate
                                }
        raise ValueError(f"No config for {refclk_freq/1e6} MHz refclk / {linerate/1e9} Gbps")
```

### Step 2: Create GTX Channel Wrapper

```python
class S7GTXTransceiver(PIPETransceiver):
    """
    Xilinx 7-Series GTX transceiver for PCIe.

    Wraps GTXE2_CHANNEL primitive with PIPE interface.

    Reference:
    - Xilinx UG476: 7 Series FPGAs GTX/GTH Transceivers
    - usb3_pipe K7USB3SerDes implementation
    - LUNA XC7GTXSerDesPIPE

    Parameters
    ----------
    platform : Platform
        LiteX platform for constraints
    pads : Record
        Differential TX/RX pads
    refclk_pads : Record or Signal
        Reference clock (100 MHz typical)
    refclk_freq : float
        Reference clock frequency in Hz
    sys_clk_freq : float
        System clock frequency in Hz
    data_width : int
        PIPE data width (8 or 16)
    gen : int
        PCIe generation (1 or 2)
    """
    def __init__(self, platform, pads, refclk_pads, refclk_freq,
                 sys_clk_freq, data_width=8, gen=1):
        PIPETransceiver.__init__(self, data_width, gen)

        self.platform = platform
        self.pads = pads
        self.sys_clk_freq = sys_clk_freq

        # # #

        # Reference clock
        if isinstance(refclk_pads, (Signal, ClockSignal)):
            refclk = refclk_pads
        else:
            refclk = Signal()
            self.specials += Instance("IBUFDS_GTE2",
                i_CEB = 0,
                i_I   = refclk_pads.p,
                i_IB  = refclk_pads.n,
                o_O   = refclk
            )

        # PLL
        linerate = self.get_line_rate()
        pll = GTXChannelPLL(refclk, refclk_freq, linerate)
        self.submodules.pll = pll

        # TX/RX Datapaths (from usb3_pipe pattern)
        # Note: For Xilinx, we use hardware 8b/10b in the GTX primitive
        # For ECP5, we'll use software 8b/10b (see Task 9.5)
        self.submodules.tx_datapath = TransceiverTXDatapath(phy_dw=16)  # 2 bytes
        self.submodules.rx_datapath = TransceiverRXDatapath(phy_dw=16)  # 2 bytes

        # No software encoder/decoder for Xilinx - hardware 8b/10b is used
        # (Lines removed - was contradictory with p_TX_8B10B_ENABLE=True)

        # GTX primitive (next step)
        # ...
```

### Step 3: Instantiate GTXE2_CHANNEL Primitive

```python
# Inside S7GTXTransceiver.__init__:

# GTX Configuration (from UG476 + usb3_pipe)
rxcdr_cfgs = {
    1: 0x0380008bff10400010,  # /16 (Gen1)
    2: 0x0380008bff10200010,  # /8 (Gen2)
}

self.specials += Instance("GTXE2_CHANNEL",
    # Simulation attributes
    p_SIM_RESET_SPEEDUP = "TRUE",
    p_SIM_VERSION = "4.0",

    # PMA attributes
    p_PMA_RSV = 0x18480,  # USB3 settings (work for PCIe)
    p_PMA_RSV2 = 0x2050,

    # RX Configuration
    p_RX_DATA_WIDTH = 20,  # 2 bytes x 10 bits
    p_RX_INT_DATAWIDTH = 0,

    # TX Configuration
    p_TX_DATA_WIDTH = 20,
    p_TX_INT_DATAWIDTH = 0,

    # 8b/10b Encoder/Decoder
    p_TX_8B10B_ENABLE = True,
    p_RX_8B10B_ENABLE = True,

    # Output dividers (Gen1=/16, Gen2=/8)
    p_TXOUT_DIV = pll.config["d"],
    p_RXOUT_DIV = pll.config["d"],

    # CDR Configuration
    p_RXCDR_CFG = rxcdr_cfgs[self.gen],

    # Clock ports
    i_GTXRXN = pads.rx_n,
    i_GTXRXP = pads.rx_p,
    o_GTXTXN = pads.tx_n,
    o_GTXTXP = pads.tx_p,

    # TX User Interface (hardware 8b/10b enabled)
    i_TXUSRCLK = ClockSignal("tx"),
    i_TXUSRCLK2 = ClockSignal("tx"),
    o_TXOUTCLK = self.tx_clk,
    # Connect 8-bit data directly - GTX handles encoding
    i_TXDATA = self.tx_datapath.source.data,    # 16-bit (2 bytes)
    i_TXCHARISK = self.tx_datapath.source.ctrl, # 2-bit (K-char per byte)

    # RX User Interface (hardware 8b/10b enabled)
    i_RXUSRCLK = ClockSignal("rx"),
    i_RXUSRCLK2 = ClockSignal("rx"),
    o_RXOUTCLK = self.rx_clk,
    # Receive 8-bit decoded data - GTX handles decoding
    o_RXDATA = self.rx_datapath.sink.data,      # 16-bit (2 bytes)
    o_RXCHARISK = self.rx_datapath.sink.ctrl,   # 2-bit (K-char per byte)

    # Electrical Idle
    i_TXELECIDLE = self.tx_elecidle,
    o_RXELECIDLE = self.rx_elecidle,

    # ... 50+ more configuration parameters
)

# Create TX/RX clock domains
self.clock_domains.cd_tx = ClockDomain()
self.clock_domains.cd_rx = ClockDomain()
self.comb += [
    ClockSignal("tx").eq(self.tx_clk),
    ClockSignal("rx").eq(self.rx_clk),
]

# Add timing constraints
platform.add_period_constraint(self.tx_clk, 1e9/self.get_word_clk_freq())
platform.add_period_constraint(self.rx_clk, 1e9/self.get_word_clk_freq())
platform.add_false_path_constraints(
    platform.lookup_request("sys_clk").name,
    self.tx_clk,
    self.rx_clk
)
```

### Step 4: Connect PIPE Interface

```python
# Connect 8b/10b encoder to PIPE TX
self.comb += [
    self.encoder.d[0].eq(self.tx_data[0:8]),
    self.encoder.d[1].eq(self.tx_data[8:16]),
    self.encoder.k[0].eq(self.tx_datak[0]),
    self.encoder.k[1].eq(self.tx_datak[1]),
]

# Connect 8b/10b decoder to PIPE RX
self.comb += [
    self.rx_data[0:8].eq(self.decoder.d[0]),
    self.rx_data[8:16].eq(self.decoder.d[1]),
    self.rx_datak[0].eq(self.decoder.k[0]),
    self.rx_datak[1].eq(self.decoder.k[1]),
    self.rx_valid.eq(~(self.decoder.invalid[0] | self.decoder.invalid[1])),
]
```

### Step 5: Test GTX Wrapper

```python
# test/test_s7_gtx.py

class TestS7GTX(unittest.TestCase):
    def test_gtx_instantiation(self):
        """GTX wrapper should instantiate without errors."""
        # Mock platform
        from litex.build.sim import SimPlatform
        platform = SimPlatform()

        # Create GTX
        gtx = S7GTXTransceiver(
            platform,
            pads=platform.request("pcie_x1"),
            refclk_pads=platform.request("clk100"),
            refclk_freq=100e6,
            sys_clk_freq=125e6,
            data_width=16,
            gen=1
        )

        # Should have PIPE interface signals
        self.assertIsInstance(gtx.tx_data, Signal)
        self.assertIsInstance(gtx.rx_data, Signal)
```

**Success Criteria:**
- ✅ GTX primitive instantiates correctly
- ✅ 8b/10b encoder/decoder integrated
- ✅ PIPE interface connected
- ✅ Clock domains created
- ✅ Timing constraints added
- ✅ Tests pass

**Estimated Time:** 2 days (complex primitive configuration)

---

## Task 9.4: Xilinx UltraScale+ GTY/GTH Wrapper

**Goal:** Wrap GTHE3/GTHE4/GTYE4_CHANNEL for UltraScale+ FPGAs.

**Reference:** Similar to Task 9.3 but with US+ primitives

**Files to Create:**
- `litepcie/phy/xilinx/usp_gty.py` - GTY wrapper
- `litepcie/phy/xilinx/usp_gth.py` - GTH wrapper
- `test/test_usp_transceivers.py` - US+ tests

**Detailed Steps:**

Similar to Task 9.3, but:
1. Use `GTHE3_CHANNEL` (UltraScale) or `GTHE4_CHANNEL` (UltraScale+)
2. Different DRP interface (more advanced)
3. Support Gen3 architecture (not full implementation)
4. Higher performance CDR settings
5. Different PLL configuration

**Key Differences:**
- `GTHE4_COMMON` for shared PLL (QPLL0/QPLL1)
- `BUFG_GT` for clock buffering (instead of BUFG)
- More advanced equalization options
- Gen3/Gen4 capable (architecture support)

**Success Criteria:**
- ✅ GTH/GTY wrappers functional
- ✅ Gen1/Gen2 working
- ✅ Gen3 architecture support (stubs)
- ✅ Tests pass

**Estimated Time:** 1.5 days (leverage Task 9.3 patterns)

---

## Task 9.5: Lattice ECP5 SERDES Wrapper

**Goal:** Wrap ECP5 DCUA primitive with PIPE interface, implementing 8b/10b in gateware.

**Reference:** ECP5-PCIe project extensively

**Files to Create:**
- `litepcie/phy/lattice/ecp5_serdes.py` - ECP5 wrapper
- `test/test_ecp5_serdes.py` - ECP5 tests

**Detailed Steps:**

### Step 1: Study ECP5-PCIe Reset Sequencer

The ECP5 requires a complex 8-state reset FSM (lines 217-264 of ecp5_serdes.py).

```python
# Simplified version from ECP5-PCIe

with m.FSM(domain="rx"):
    with m.State("init"):
        m.d.comb += [
            serdes_tx_reset.eq(1),
            serdes_rx_reset.eq(1),
            pcs_reset.eq(1),
        ]
        with m.If(~self.lane.reset):
            m.next = "start-tx"

    with m.State("start-tx"):
        m.d.comb += [serdes_tx_reset.eq(0)]
        m.d.rx += cnt.eq(cnt + 1)
        with m.If(~tx_lol_s | (cnt > 200)):
            m.next = "start-rx"

    with m.State("start-rx"):
        m.d.comb += [serdes_rx_reset.eq(0)]
        with m.If(~rx_lol_s | (cnt > 200)):
            m.next = "start-pcs-done"

    with m.State("start-pcs-done"):
        m.d.comb += [pcs_reset.eq(0)]
        # Ready to operate
```

### Step 2: Implement SCI Interface

ECP5 uses SCI (SerDes Client Interface) for runtime configuration.

```python
class ECP5SCIInterface(Module):
    """
    ECP5 SerDes Client Interface for runtime config.

    Used for:
    - RX/TX polarity inversion
    - Termination settings
    - Loopback modes

    Reference: Lattice TN1261 pages 52-55
    """
    def __init__(self):
        # SCI signals to DCUA
        self.sci_wdata = Signal(8)
        self.sci_addr = Signal(6)
        self.sci_rdata = Signal(8)
        self.sci_rd = Signal()
        self.sci_wrn = Signal()
        self.dual_sel = Signal()
        self.chan_sel = Signal()
```

### Step 3: Create ECP5 SERDES Wrapper

```python
class ECP5SerDesTransceiver(PIPETransceiver):
    """
    Lattice ECP5 SERDES wrapper for PCIe.

    Key differences from Xilinx:
    - No built-in 8b/10b (use gateware encoder/decoder)
    - Uses DCUA (Dual Channel Unit) primitive
    - SCI interface for runtime configuration
    - Complex reset sequencing required
    - Gen1 primary target (Gen2 experimental)

    Reference:
    - ECP5-PCIe project
    - Lattice TN1261: ECP5/ECP5-5G SERDES/PCS Usage Guide
    - Lattice FPGA-TN-02032: ECP5 and ECP5-5G SERDES Design Guide

    Parameters
    ----------
    dcu : int
        DCU number (0 or 1)
    channel : int
        Channel within DCU (0 or 1)
    gearing : int
        Gearbox ratio (1 or 2)
    speed_5GTps : bool
        Enable 5 GT/s support (Gen2)
    clkfreq : float
        Reference clock frequency (100e6 or 200e6)
    """
    def __init__(self, dcu=0, channel=0, gearing=2,
                 speed_5GTps=False, clkfreq=100e6):
        assert dcu in [0, 1]
        assert channel in [0, 1]
        assert gearing in [1, 2]
        assert clkfreq in [100e6, 200e6]

        gen = 2 if speed_5GTps else 1
        data_width = 16 if gearing == 2 else 8

        PIPETransceiver.__init__(self, data_width, gen)

        # # #

        # 8b/10b Encoder/Decoder (software - ECP5 doesn't have hardware)
        self.submodules.encoder = PCIeEncoder()  # From Task 9.1
        self.submodules.decoder = PCIeDecoder()

        # SCI Interface
        self.submodules.sci = ECP5SCIInterface()

        # Reset sequencer (from ECP5-PCIe pattern)
        # ...

        # DCUA Primitive
        self.instantiate_dcua(dcu, channel, gearing, speed_5GTps, clkfreq)
```

### Step 4: Instantiate DCUA Primitive

```python
def instantiate_dcua(self, dcu, channel, gearing, speed_5GTps, clkfreq):
    """
    Instantiate DCUA primitive with PCIe configuration.

    Reference: ECP5-PCIe lines 432-680
    """
    # Reference clock
    ref_clk = Signal()
    self.specials += Instance("EXTREFB",
        o_REFCLKO = ref_clk,
        p_REFCK_PWDNB = "0b1",
        p_REFCK_RTERM = "0b1",  # 100 Ohm
    )

    # DCU configuration (from ECP5-PCIe)
    dcu_config = {
        "p_D_MACROPDB": "0b1",
        "p_D_TXPLL_PWDNB": "0b1",
        "p_D_REFCK_MODE": "0b100" if clkfreq == 100e6 else "0b000",
        "p_D_TX_MAX_RATE": "5.0" if speed_5GTps else "2.5",
        # ... 20+ more DCU parameters
    }

    # Channel configuration
    ch_config = {
        "p_CHx_PROTOCOL": "PCIe",
        "p_CHx_PCIE_MODE": "0b1",
        "p_CHx_ENC_BYPASS": "0b1",  # We do 8b/10b in gateware
        "p_CHx_DEC_BYPASS": "0b1",
        "p_CHx_RX_GEAR_MODE": "0b1" if gearing == 2 else "0b0",
        "p_CHx_TX_GEAR_MODE": "0b1" if gearing == 2 else "0b0",
        # ... 50+ more channel parameters
    }

    # Replace CHx with actual channel
    ch_config_actual = {}
    for key, val in ch_config.items():
        ch_config_actual[key.replace("CHx", f"CH{channel}")] = val

    # Instantiate
    self.specials += Instance("DCUA",
        **dcu_config,
        **ch_config_actual,

        # Connect SCI
        **{f"i_D_SCIWDATA{n}": self.sci.sci_wdata[n] for n in range(8)},
        **{f"i_D_SCIADDR{n}": self.sci.sci_addr[n] for n in range(6)},
        # ... more SCI connections

        attrs={"LOC": f"DCU{dcu}", "CHAN": f"CH{channel}"}
    )
```

### Step 5: Integrate 8b/10b Encoder/Decoder

```python
# Connect gateware 8b/10b (ECP5 doesn't have hardware)
self.comb += [
    # TX: PIPE data → 8b/10b → SERDES
    self.encoder.sink.d.eq(self.tx_data[0:8]),
    self.encoder.sink.k.eq(self.tx_datak[0]),
    # ... feed encoder output to DCUA

    # RX: SERDES → 8b/10b → PIPE data
    # ... feed DCUA output to decoder
    self.rx_data[0:8].eq(self.decoder.source.d),
    self.rx_datak[0].eq(self.decoder.source.k),
    self.rx_valid.eq(~self.decoder.invalid),
]
```

### Step 6: Test ECP5 SERDES

```python
# test/test_ecp5_serdes.py

def test_ecp5_serdes_with_software_8b10b():
    """
    ECP5 SERDES should use software 8b/10b encoder/decoder.
    """
    serdes = ECP5SerDesTransceiver(dcu=0, channel=0)

    # Should have gateware encoder/decoder
    assert hasattr(serdes, 'encoder')
    assert hasattr(serdes, 'decoder')
    assert isinstance(serdes.encoder, PCIeEncoder)
```

**Success Criteria:**
- ✅ DCUA primitive configured for PCIe
- ✅ Software 8b/10b integrated
- ✅ SCI interface functional
- ✅ Reset sequencer working
- ✅ Gen1 support verified
- ✅ Gen2 architecture support

**Estimated Time:** 1.5 days (complex ECP5-specific features)

---

## Task 9.6: Clock Domain Crossing Implementation

**Goal:** Implement robust CDC between sys_clk and transceiver clocks.

**Reference:** usb3_pipe TXDatapath/RXDatapath pattern

**Files to Modify:**
- All transceiver wrappers from Tasks 9.3-9.5

**Detailed Steps:**

### Step 1: Add TX Datapath to Each Wrapper

```python
# In each transceiver __init__:

# TX Datapath: sys_clk → tx_clk
self.submodules.tx_datapath = TransceiverTXDatapath(phy_dw=20)

# Connect to PIPE interface
self.comb += [
    self.tx_datapath.sink.data.eq(self.tx_data),
    self.tx_datapath.sink.ctrl.eq(self.tx_datak),
]

# Connect to transceiver primitive
# (transceiver reads from tx_datapath.source in tx_clk domain)
```

### Step 2: Add RX Datapath to Each Wrapper

```python
# RX Datapath: rx_clk → sys_clk
self.submodules.rx_datapath = TransceiverRXDatapath(phy_dw=20)

# Connect from transceiver primitive
# (writes to rx_datapath.sink in rx_clk domain)

# Connect to PIPE interface
self.comb += [
    self.rx_data.eq(self.rx_datapath.source.data),
    self.rx_datak.eq(self.rx_datapath.source.ctrl),
]
```

### Step 3: Test CDC Timing

```python
# test/test_transceiver_cdc.py

def test_tx_cdc_no_data_loss():
    """
    TX CDC should not lose data when crossing clock domains.
    """
    # Send pattern through CDC
    # Verify all data arrives
    pass

def test_rx_cdc_handles_async_clock():
    """
    RX CDC should handle asynchronous recovered clock.
    """
    # Simulate with async RX clock
    # Verify data integrity
    pass
```

**Success Criteria:**
- ✅ TX CDC working in all wrappers
- ✅ RX CDC working in all wrappers
- ✅ AsyncFIFO depths appropriate
- ✅ No data loss under test
- ✅ Timing constraints added

**Estimated Time:** 1 day (apply pattern to all wrappers)

---

## Task 9.7: Gen1/Gen2 Speed Switching

**Goal:** Implement dynamic speed negotiation between Gen1 and Gen2.

**Reference:** ECP5-PCIe `divide_clk` pattern

**Files to Modify:**
- All transceiver wrappers

**Detailed Steps:**

### Step 1: Add Speed Control Signal

```python
# In PIPETransceiver base class:

self.speed = Signal(reset=1)  # 1=Gen1, 2=Gen2
```

### Step 2: Configure Transceiver for Speed

```python
# GTX: Change TXOUT_DIV/RXOUT_DIV
# - Gen1: divide by 16 (2.5 GT/s → 156.25 MHz)
# - Gen2: divide by 8 (5.0 GT/s → 312.5 MHz)

# ECP5: Change divide_clk
# - Gen1: divide_clk = 0 (100 MHz ref → 2.5 GT/s)
# - Gen2: divide_clk = 1 (200 MHz ref → 5.0 GT/s)
```

### Step 3: Integrate with LTSSM

```python
# From Phase 6 LTSSM:
# LTSSM negotiates speed during training
# Signals speed change via link_speed output

# Connect LTSSM to transceiver:
self.comb += self.transceiver.speed.eq(self.ltssm.link_speed)
```

### Step 4: Test Speed Switching

```python
def test_gen1_to_gen2_speed_change():
    """
    Transceiver should switch from Gen1 to Gen2 when requested.
    """
    # Start at Gen1
    # Signal speed change
    # Verify Gen2 operation
    pass
```

**Success Criteria:**
- ✅ Speed control signal in all wrappers
- ✅ Gen1 and Gen2 both functional
- ✅ Dynamic switching working
- ✅ LTSSM integration

**Estimated Time:** 1 day

---

## Task 9.8: LTSSM Integration

**Goal:** Connect Phase 6 LTSSM to transceiver wrappers.

**Reference:** ECP5-PCIe PHY layer integration

**Files to Modify:**
- `litepcie/phy/common/transceiver.py`
- All transceiver wrappers

**Detailed Steps:**

### Step 1: Add LTSSM Hooks to Base Class

```python
# In PIPETransceiver:

# LTSSM control signals
self.ltssm_reset = Signal()
self.ltssm_tx_ts = Signal()  # Transmit training sequence
self.ltssm_rx_ts = Signal()  # Received training sequence
self.ltssm_link_up = Signal()  # Link trained
```

### Step 2: Create Integrated PHY Wrapper

```python
# litepcie/phy/s7_pcie_phy.py

class S7PCIePHY(Module):
    """
    Complete PCIe PHY using GTX transceiver + soft stack.

    Integrates:
    - GTX transceiver (Task 9.3)
    - PIPE interface (Phase 3)
    - DLL layer (Phase 4)
    - LTSSM (Phase 6)

    Drop-in replacement for Xilinx hard IP.
    """
    def __init__(self, platform, pads):
        # Transceiver
        self.submodules.gtx = S7GTXTransceiver(
            platform, pads,
            refclk_pads=platform.request("clk100"),
            refclk_freq=100e6,
            sys_clk_freq=125e6,
            data_width=16,
            gen=1
        )

        # PIPE Interface (from Phase 3)
        from litepcie.phy.pipe import PIPEInterface
        self.submodules.pipe = PIPEInterface(data_width=16)

        # Connect GTX to PIPE
        self.comb += [
            self.pipe.tx_data.eq(self.gtx.tx_data),
            self.gtx.rx_data.eq(self.pipe.rx_data),
            # ... more connections
        ]

        # DLL Layer (from Phase 4)
        from litepcie.core.dll import DLL
        self.submodules.dll = DLL()

        # LTSSM (from Phase 6)
        from litepcie.core.ltssm import LTSSM
        self.submodules.ltssm = LTSSM()

        # Connect everything
        # ...
```

### Step 3: Test Integrated PHY

```python
def test_integrated_phy_link_training():
    """
    Integrated PHY should automatically train link.
    """
    phy = S7PCIePHY(platform, pads)

    # Simulate loopback
    # Verify link trains to L0
    # Check ltssm.link_up asserts
    pass
```

**Success Criteria:**
- ✅ LTSSM connected to transceiver
- ✅ Automatic link training working
- ✅ Link status monitored
- ✅ Integrated PHY classes for each FPGA

**Estimated Time:** 1.5 days

---

## Task 9.9: Testing Infrastructure

**Goal:** Create comprehensive test suite for transceivers.

**Files to Create:**
- `test/test_transceiver_loopback.py`
- `test/test_transceiver_integration.py`
- `test/test_gen1_gen2_switching.py`

**Detailed Steps:**

### Step 1: Loopback Tests

```python
def test_gtx_internal_loopback():
    """
    GTX should pass data in internal loopback mode.
    """
    # Configure GTX for loopback
    # Send known pattern
    # Verify received correctly
    pass

def test_8b10b_roundtrip():
    """
    Data should survive 8b/10b encode → decode.
    """
    # Send all possible byte values
    # Send all K-characters
    # Verify decoded correctly
    pass
```

### Step 2: Integration Tests

```python
def test_full_stack_tlp_to_serdes():
    """
    TLP should traverse full stack to SERDES.
    """
    # Send TLP from user logic
    # Trace through DLL → PIPE → transceiver
    # Verify appears on TX differential pair
    pass
```

### Step 3: Speed Switching Tests

```python
def test_gen1_to_gen2_transition():
    """
    Link should retrain when switching Gen1 → Gen2.
    """
    # Start at Gen1
    # LTSSM signals Gen2 capability
    # Link retrains
    # Verify Gen2 operation
    pass
```

### Step 4: Error Injection Tests

```python
def test_8b10b_error_recovery():
    """
    Decoder should detect and report encoding errors.
    """
    # Inject invalid 10-bit code
    # Verify decoder.invalid asserts
    # Verify LTSSM handles error
    pass
```

**Success Criteria:**
- ✅ Loopback tests for each transceiver
- ✅ Integration tests for full stack
- ✅ Speed switching tests
- ✅ Error handling tests
- ✅ >85% code coverage

**Estimated Time:** 2 days

---

## Task 9.10: Documentation and Examples

**Goal:** Create comprehensive documentation and usage examples.

**Files to Create:**
- `docs/transceiver-integration.md`
- `docs/fpga-specific-notes.md`
- `docs/phase-9-completion-summary.md`
- `examples/transceiver_loopback.py`

**Detailed Steps:**

### Step 1: Write Integration Guide

```markdown
# Transceiver Integration Guide

## Overview

LitePCIe Phase 9 adds support for FPGA internal transceivers, enabling
PCIe implementation without external PHY chips or vendor hard IP.

## Supported Platforms

### Xilinx 7-Series (GTX)
- Artix-7, Kintex-7, Virtex-7
- Gen1 (2.5 GT/s) and Gen2 (5.0 GT/s)
- Example: Artix-7 XC7A100T on Nexys Video

### Xilinx UltraScale+ (GTH/GTY)
- Kintex UltraScale+, Virtex UltraScale+
- Gen1, Gen2, Gen3 (architecture)
- Higher performance than GTX

### Lattice ECP5 (SERDES)
- LFE5U-25F and higher
- Gen1 (2.5 GT/s), Gen2 experimental
- Open-source toolchain (nextpnr)

## Usage Example

```python
from litex import *
from litepcie.phy.s7_pcie_phy import S7PCIePHY

# Create PHY with GTX transceiver
phy = S7PCIePHY(
    platform,
    pads=platform.request("pcie_x1"),
)

# Use like any other LitePCIe PHY
endpoint = LitePCIeEndpoint(phy)
dma = LitePCIeDMA(endpoint)
```

## Architecture

```
User Logic (TLPs)
    ↓
DLL Layer (ACK/NAK, retry)
    ↓
PIPE Interface (8-bit + K)
    ↓
Clock Domain Crossing
    ↓
Transceiver Wrapper
    ↓
8b/10b Encoder/Decoder
    ↓
SERDES (Physical Layer)
    ↓
Differential Pairs (PCIe connector)
```

## Benefits

1. **No Vendor IP Required**: No Xilinx PCIe license needed
2. **Open Source Friendly**: Works with nextpnr (ECP5)
3. **Educational**: Full visibility into physical layer
4. **Flexible**: Customize at all protocol layers
5. **Portable**: Same code across FPGA vendors

## Limitations

1. **Resource Usage**: Higher than hard IP (~2x LUTs)
2. **Performance**: Slightly higher latency (~20ns)
3. **Compliance**: Requires testing for production
4. **Gen3**: Architecture only, not fully implemented

## Hardware Requirements

- FPGA with GTX/GTH/GTY or ECP5 SERDES
- PCIe edge connector or M.2 slot
- 100 MHz reference clock (typically on-board)
- Proper PCB design (impedance matching)
```

### Step 2: Write FPGA-Specific Notes

Document quirks and best practices for each FPGA family.

### Step 3: Create Loopback Example

```python
# examples/transceiver_loopback.py

"""
Simple transceiver loopback example.

Demonstrates:
- GTX transceiver configuration
- Internal loopback mode
- Data transmission and reception
"""

from migen import *
from litex.soc.cores.clock import *
from litepcie.phy.xilinx.s7_gtx import S7GTXTransceiver

class TransceiverLoopback(Module):
    def __init__(self, platform):
        # ... create transceiver
        # ... configure loopback
        # ... send test pattern
        pass

# ...
```

### Step 4: Write Completion Summary

Document what was accomplished in Phase 9.

**Success Criteria:**
- ✅ Integration guide complete
- ✅ FPGA-specific notes documented
- ✅ Working examples provided
- ✅ Completion summary written

**Estimated Time:** 1.5 days

---

## Timeline

| Task | Description | Duration | Dependencies |
|------|-------------|----------|--------------|
| 9.1 | 8b/10b Encoder/Decoder | 0.5 days | None |
| 9.2 | Transceiver Base Abstraction | 0.5 days | 9.1 |
| 9.3 | Xilinx GTX Wrapper | 2 days | 9.1, 9.2 |
| 9.4 | Xilinx UltraScale+ GTY/GTH | 1.5 days | 9.3 |
| 9.5 | Lattice ECP5 SERDES | 1.5 days | 9.1, 9.2 |
| 9.6 | Clock Domain Crossing | 1 day | 9.3, 9.4, 9.5 |
| 9.7 | Gen1/Gen2 Speed Switching | 1 day | 9.6 |
| 9.8 | LTSSM Integration | 1.5 days | 9.7, Phase 6 |
| 9.9 | Testing Infrastructure | 2 days | 9.8 |
| 9.10 | Documentation | 1.5 days | 9.9 |

**Total:** ~13 days development time

**Critical Path:** 9.1 → 9.2 → 9.3 → 9.6 → 9.7 → 9.8 → 9.9 → 9.10

**Parallel Work:** Tasks 9.4 and 9.5 can proceed in parallel with 9.3

---

## Success Criteria

### Functionality
- ✅ 8b/10b encoder/decoder working (using LiteX)
- ✅ GTX wrapper with PIPE interface functional
- ✅ GTY/GTH wrapper functional
- ✅ ECP5 SERDES wrapper with software 8b/10b
- ✅ Clock domain crossing validated
- ✅ Gen1 and Gen2 speed switching
- ✅ LTSSM integration working
- ✅ Loopback tests passing

### Testing
- ✅ Unit tests for encoders (>95% coverage)
- ✅ Unit tests for wrappers (>85% coverage)
- ✅ Integration tests (loopback, LTSSM)
- ✅ Speed switching tests

### Code Quality
- ✅ All tests passing
- ✅ Pre-commit hooks pass
- ✅ Follows LiteX/LitePCIe patterns
- ✅ Comprehensive docstrings

### Documentation
- ✅ Integration guide complete
- ✅ FPGA-specific notes documented
- ✅ Examples provided
- ✅ Completion summary written

---

## Dependencies

**External:**
- None (all internal to FPGA)

**Internal:**
- Phase 3: PIPE interface definitions
- Phase 4: DLL layer for integration
- Phase 6: LTSSM for link training

**Tools:**
- Vivado (Xilinx synthesis, optional for simulation)
- nextpnr (ECP5, required for open-source)
- LiteX/Migen (Python HDL framework)

---

## Risk Mitigation

### Technical Risks

**Risk:** Transceiver configuration is complex (100+ parameters)
**Mitigation:** Use reference designs (usb3_pipe, LUNA), iterate on working config

**Risk:** ECP5 reset sequencing difficult to get right
**Mitigation:** Follow ECP5-PCIe FSM exactly, extensive testing

**Risk:** Clock domain crossing causes data corruption
**Mitigation:** Use proven AsyncFIFO, add timing constraints, test thoroughly

**Risk:** Hardware validation reveals electrical issues
**Mitigation:** Start with known-good boards, use logic analyzer, follow layout guidelines

### Schedule Risks

**Risk:** GTX wrapper takes longer than 2 days
**Mitigation:** Allocate buffer time, leverage usb3_pipe patterns heavily

**Risk:** ECP5 limited documentation
**Mitigation:** ECP5-PCIe is excellent reference, community support available

---

## Key Architectural Decisions

### 1. Use LiteX 8b/10b Instead of Custom

**Decision:** Leverage `litex.soc.cores.code_8b10b.Encoder/Decoder`

**Rationale:**
- Already tested and working
- Consistent with LiteX ecosystem
- ECP5 needs software 8b/10b anyway

### 2. Follow usb3_pipe Datapath Pattern

**Decision:** Use TXDatapath/RXDatapath modules with AsyncFIFO

**Rationale:**
- Proven pattern from usb3_pipe
- Clean clock domain separation
- Reusable across transceiver types

### 3. Base Class for All Transceivers

**Decision:** Create PIPETransceiver base class

**Rationale:**
- Common interface for DLL layer
- Easier testing (mock base class)
- Clear documentation of PIPE signals

### 4. ECP5 Gets Full Reference Implementation

**Decision:** Study ECP5-PCIe in depth, follow patterns exactly

**Rationale:**
- Only working open-source PCIe implementation
- Complex reset sequencing critical
- Enables nextpnr support

### 5. Gen3 Architecture Only (No Implementation)

**Decision:** Define interfaces, stub encoder, defer implementation

**Rationale:**
- 128b/130b encoding is complex (separate phase)
- Gen1/Gen2 sufficient for most use cases
- Architecture defined for future work

---

## Reference Codebase Insights Summary

### ECP5-PCIe
**Best For:** ECP5-specific implementation, reset sequencing, SCI interface
**Key Files:** `ecp5_serdes.py`, `serdes.py`, `phy.py`
**Pattern:** Amaranth HDL, complex FSM, symbol-based interface

### usb3_pipe
**Best For:** Xilinx GTX/GTP wrappers, datapath pattern, CDC
**Key Files:** `serdes.py` (TXDatapath, RXDatapath, K7USB3SerDes)
**Pattern:** Migen, stream endpoints, AsyncFIFO for CDC

### LUNA
**Best For:** PIPE compliance, reset deferral, multi-platform support
**Key Files:** `xc7_gtx.py`, `ecp5.py`
**Pattern:** Amaranth, PLL configuration, reset sequencer

### Common Patterns
1. Symbol-based interface (9-bit: 8 data + 1 K-char)
2. Separate TX/RX clock domains with AsyncFIFO
3. Complex reset sequencing (multi-state FSM)
4. Runtime configuration (DRP for Xilinx, SCI for ECP5)
5. 8b/10b in hardware (Xilinx) or gateware (ECP5)

---

## Conclusion

Phase 9 represents a major milestone: **vendor-IP-free PCIe implementation** using FPGA internal transceivers.

By studying three excellent reference implementations (ECP5-PCIe, usb3_pipe, LUNA), we've identified proven patterns and best practices for:
- Transceiver configuration (100+ parameters handled correctly)
- Clock domain crossing (AsyncFIFO-based, robust)
- Reset sequencing (complex FSMs, vendor-specific)
- 8b/10b encoding (hardware vs. software)
- PIPE interface compliance

This plan provides a clear path to integrate transceivers with our existing PIPE/DLL/LTSSM stack (Phases 3-6), creating a complete open-source PCIe implementation.

**Key Benefits:**
- ✅ No vendor PCIe IP required
- ✅ Open-source toolchain support (ECP5 + nextpnr)
- ✅ Educational visibility into physical layer
- ✅ Portable across FPGA vendors
- ✅ Foundation for future Gen3/Gen4 support

**Next Steps After Phase 9:**
- Hardware validation on real FPGAs
- PCIe compliance testing
- Multi-lane support (x4, x8)
- Gen3 full implementation
- Production hardening

---

**Plan Status:** READY FOR EXECUTION

**Plan Version:** 2.0 (Research-Based)

**Plan Author:** Claude (Anthropic) based on codebase analysis

**References:**
1. ECP5-PCIe: https://codeberg.org/ECP5-PCIe/ECP5-PCIe
2. usb3_pipe: https://github.com/enjoy-digital/usb3_pipe
3. LUNA: https://github.com/greatscottgadgets/luna
4. Xilinx UG476: 7 Series FPGAs GTX/GTH Transceivers User Guide
5. Lattice TN1261: ECP5/ECP5-5G SERDES/PCS Usage Guide
6. PCIe Base Spec 4.0
7. Intel PIPE 3.0 Specification
