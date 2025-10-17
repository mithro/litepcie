# Reference Implementation Comparison and Improvement Plan

> **For Claude:** Use `${SUPERPOWERS_SKILLS_ROOT}/skills/collaboration/executing-plans/SKILL.md` to implement this plan task-by-task.

**Date:** 2025-10-18
**Status:** PLANNED
**Goal:** Compare current LitePCIe Phase 9 transceiver implementation against proven reference implementations (liteiclink, ECP5-PCIe, LUNA) and create detailed improvement plan to achieve production-ready, hardware-validated PCIe PHY.

**Architecture:** Build upon Phase 9's validated software 8b/10b architecture by completing full primitive instantiation, adding production-quality reset sequences, implementing proper CDC patterns, and adding comprehensive hardware validation infrastructure.

**Tech Stack:** Migen/LiteX, pytest + pytest-cov, Python 3.11+, Xilinx Vivado, Lattice Diamond/nextpnr, LiteScope

---

## Executive Summary

### Current Status (Phase 9 Complete)

Phase 9 delivered a **validated architecture** with:
- ✅ Software 8b/10b encoding (matches liteiclink approach)
- ✅ Clean base classes and abstraction layers
- ✅ 53/53 tests passing (100%)
- ✅ Comprehensive documentation

### Critical Gap: Skeleton vs Production Implementation

**Current:**
- GTX: 376 lines, **9 primitive parameters** (skeleton)
- GTY: 337 lines, **minimal parameters** (skeleton)
- ECP5: 365 lines, **architectural only** (skeleton)

**Production Target (from liteiclink):**
- GTX: 1,241 lines, **496 primitive parameters** (full)
- GTY: Similar complexity
- ECP5: From ECP5-PCIe project

### Key Findings from Reference Analysis

#### 1. **8b/10b Encoding Strategy: ✅ VALIDATED**

All three reference implementations use **software 8b/10b**:

**liteiclink (GTX/GTY):**
```python
from litex.soc.cores.code_8b10b import Encoder, Decoder
self.encoder = ClockDomainsRenamer("tx")(Encoder(nwords, True))
self.decoders = [ClockDomainsRenamer("rx")(Decoder(True)) for _ in range(nwords)]

# GTX primitive configuration:
i_TX8B10BEN = 0,  # Hardware 8b/10b DISABLED
i_RX8B10BEN = 0,  # Hardware 8b/10b DISABLED
```

**ECP5-PCIe (Amaranth):**
```python
# No hardware 8b/10b in ECP5 DCUA - all software
```

**LUNA (USB3 PIPE):**
- Software 8b/10b for flexibility and debugging

**Conclusion:** Phase 9's software 8b/10b strategy is **correct** and matches industry practice.

#### 2. **Primitive Instantiation: ⚠️ MAJOR GAP**

| Component | LitePCIe (Current) | liteiclink (Reference) | Gap |
|-----------|-------------------|------------------------|-----|
| GTX Parameters | 9 | 496 | **54x incomplete** |
| GTX Lines | 376 | 1,241 | **3.3x incomplete** |
| Reset Sequence | Basic | AR43482 compliant | Missing timing |
| DRP Support | None | Full DRP interface | No dynamic config |
| PRBS Testing | None | Built-in PRBS7/23/31 | No BER testing |
| Clock Aligner | None | Brute-force aligner | No CDR support |

#### 3. **Reset Sequences: ⚠️ NEEDS HARDENING**

**liteiclink GTXInit (gtx_7series_init.py):**
- 8-state FSM (POWER-DOWN → DRP → WAIT-PLL-RESET → WAIT-INIT-DELAY → GTX-RESET → WAIT-ALIGN → READY → ERROR)
- **AR43482 compliance:** 500ns delay after config before GTX reset release
- PLL lock monitoring with deglitching
- Phase alignment detection
- DLY reset sequencing
- Error handling and restart capability
- ~200 lines of production-hardened code

**LitePCIe current:**
- ~100 lines per platform
- Basic FSM structure
- Missing AR43482 timing
- No phase alignment
- No DLY reset
- No error recovery

#### 4. **Clock Domain Crossing: ⚠️ NEEDS VALIDATION**

**liteiclink pattern:**
```python
# TX: sys → tx clock
self.specials += MultiReg(self.tx_produce_square_wave, tx_produce_square_wave, "tx")

# RX: rx → sys clock
self.specials += MultiReg(rx_prbs_errors, self.rx_prbs_errors, "sys")

# Data FIFOs use stream.AsyncFIFO with proper depth calculation
```

**ECP5-PCIe pattern (Amaranth):**
```python
from amaranth.lib.fifo import AsyncFIFOBuffered

# Larger FIFO depths for PCIe elasticity
self.rx_fifo = AsyncFIFOBuffered(width=24, depth=512, ...)
```

**LitePCIe current:**
- Uses AsyncFIFO in base classes ✅
- But FIFO depths may need tuning for PCIe
- Control signal CDC not fully implemented

#### 5. **Testing Infrastructure: ⚠️ NEEDS HARDWARE VALIDATION**

**liteiclink testing:**
- PRBS generators (PRBS7, PRBS23, PRBS31) built-in
- BER (Bit Error Rate) measurement
- Loopback modes (near-end, far-end)
- Pattern generation for signal integrity testing
- CSR interface for runtime control

**ECP5-PCIe testing:**
- Virtual PHY for simulation
- Hardware loopback testing
- LTSSM state monitoring
- Complete PCIe enumeration tests

**LitePCIe current:**
- Excellent unit tests (53/53 passing) ✅
- But no hardware validation yet
- No PRBS/BER testing
- No signal integrity tools

---

## Comparison Matrix

### Architecture & Design

| Feature | LitePCIe Phase 9 | liteiclink | ECP5-PCIe | LUNA | Priority |
|---------|------------------|------------|-----------|------|----------|
| Software 8b/10b | ✅ LiteX Encoder/Decoder | ✅ Same | ✅ Custom | ✅ Custom | **Complete** |
| Base abstraction | ✅ PIPETransceiver | ❌ Direct GTX | ❌ Direct DCUA | ✅ PIPEInterface | **Complete** |
| Modular design | ✅ Excellent | ⚠️ Monolithic | ⚠️ Monolithic | ✅ Good | **Complete** |
| Documentation | ✅ Comprehensive | ⚠️ Minimal | ⚠️ Minimal | ✅ Good | **Complete** |

### Xilinx 7-Series GTX

| Feature | LitePCIe Phase 9 | liteiclink | Priority |
|---------|------------------|------------|----------|
| GTXE2_CHANNEL params | 9 (skeleton) | 496 (complete) | **🔴 CRITICAL** |
| PLL configuration | ✅ Auto-calc | ✅ Auto-calc | ✅ Complete |
| Reset sequence | ⚠️ Basic FSM | ✅ AR43482 | **🟡 HIGH** |
| DRP interface | ❌ None | ✅ Full | **🟢 MEDIUM** |
| Clock aligner | ❌ None | ✅ Brute-force | **🟡 HIGH** |
| PRBS testing | ❌ None | ✅ PRBS7/23/31 | **🟢 MEDIUM** |
| TX buffer | ❌ Disabled | ⚠️ Optional | **🟢 LOW** |
| RX buffer | ❌ Disabled | ⚠️ Optional | **🟢 LOW** |
| Production ready | ❌ No | ✅ Yes | **🔴 CRITICAL** |

### Xilinx UltraScale+ GTY

| Feature | LitePCIe Phase 9 | liteiclink | Priority |
|---------|------------------|------------|----------|
| GTYE4_CHANNEL params | Minimal | ~500 | **🔴 CRITICAL** |
| QPLL vs CPLL | ⚠️ Basic | ✅ Auto-select | **🟡 HIGH** |
| Reset sequence | ⚠️ Basic | ✅ UG576 | **🟡 HIGH** |
| Gen3 support | 📋 Architecture | ⚠️ Partial | **🟢 MEDIUM** |

### Lattice ECP5 SERDES

| Feature | LitePCIe Phase 9 | ECP5-PCIe | Priority |
|---------|------------------|-----------|----------|
| DCUA primitive | ⚠️ Skeleton | ✅ Full (Amaranth) | **🔴 CRITICAL** |
| SCI interface | ✅ Structure | ✅ Full | **🟡 HIGH** |
| Reset FSM | ⚠️ 8-state | ✅ Production | **🟡 HIGH** |
| Gearing modes | ✅ 1:1, 1:2 | ✅ 1:1, 1:2, 1:4 | **🟢 LOW** |
| 5 GT/s support | ⚠️ Architecture | ✅ Gen2 | **🟢 MEDIUM** |

### Clock Domain Crossing

| Feature | LitePCIe Phase 9 | liteiclink | ECP5-PCIe | Priority |
|---------|------------------|------------|-----------|----------|
| TX CDC (sys→tx) | ✅ AsyncFIFO | ✅ MultiReg | ✅ AsyncFIFO | ✅ Complete |
| RX CDC (rx→sys) | ✅ AsyncFIFO | ✅ MultiReg | ✅ AsyncFIFO | ✅ Complete |
| Control signals | ⚠️ Partial | ✅ MultiReg all | ✅ FFSync | **🟡 HIGH** |
| FIFO depths | ⚠️ Generic | ✅ Tuned | ✅ Large (512) | **🟡 HIGH** |
| Status signals | ⚠️ Partial | ✅ MultiReg all | ✅ FFSync | **🟡 HIGH** |

### Testing & Validation

| Feature | LitePCIe Phase 9 | liteiclink | ECP5-PCIe | LUNA | Priority |
|---------|------------------|------------|-----------|------|----------|
| Unit tests | ✅ 53/53 | ⚠️ Limited | ❌ None | ⚠️ Some | ✅ Complete |
| Simulation | ✅ Migen sim | ✅ Migen sim | ✅ Amaranth | ✅ Amaranth | ✅ Complete |
| PRBS generators | ❌ None | ✅ Built-in | ⚠️ Custom | ❌ None | **🟢 MEDIUM** |
| BER measurement | ❌ None | ✅ Built-in | ❌ None | ❌ None | **🟢 MEDIUM** |
| Hardware loopback | ❌ None | ✅ Supported | ✅ Tested | ✅ Tested | **🔴 CRITICAL** |
| Signal integrity | ❌ None | ⚠️ Limited | ⚠️ Limited | ⚠️ Limited | **🟢 MEDIUM** |
| PCIe enumeration | ❌ Not tested | ❌ Not tested | ✅ Verified | ❌ N/A (USB) | **🔴 CRITICAL** |

---

## Implementation Plan

### Task 1: Complete GTX Primitive Instantiation (3 days)

**Goal:** Transform S7GTXTransceiver from 9-parameter skeleton to 496-parameter production-ready implementation

**Files:**
- Modify: `litepcie/phy/xilinx/s7_gtx.py`
- Create: `test/phy/test_s7_gtx_complete.py`
- Reference: `liteiclink/liteiclink/serdes/gtx_7series.py`

#### Step 1.1: Add complete GTXE2_CHANNEL configuration parameters

**Parameters to add (~500 total):**

```python
# In S7GTXTransceiver.__init__, expand GTXE2_CHANNEL Instance:

self.specials += Instance("GTXE2_CHANNEL",
    # ===== Simulation Attributes =====
    p_SIM_RESET_SPEEDUP       = "TRUE",
    p_SIM_TX_EIDLE_DRIVE_LEVEL = "X",
    p_SIM_VERSION             = "4.0",
    p_SIM_RECEIVER_DETECT_PASS = "TRUE",

    # ===== CPLL Configuration =====
    # (Already have from Phase 9 PLL class)
    p_CPLL_CFG                = 0x00BC07DC,
    p_CPLL_FBDIV              = cpll_fbdiv,
    p_CPLL_FBDIV_45           = cpll_fbdiv_45,
    p_CPLL_REFCLK_DIV         = cpll_refclk_div,

    # ===== RX AFE (Analog Front End) =====
    p_RX_CM_SEL               = 0b11,  # VREF source
    p_RX_CM_TRIM              = 0b010,  # Common mode
    p_TERM_RCAL_CFG           = 0b10000,
    p_TERM_RCAL_OVRD          = 0,

    # ===== RX CDR (Clock Data Recovery) =====
    # Critical for 2.5/5.0 GT/s
    p_RXCDR_CFG               = rxcdr_cfg_dict[out_div],  # From liteiclink
    p_RXCDR_FR_RESET_ON_EIDLE = 0b0,
    p_RXCDR_HOLD_DURING_EIDLE = 0b0,
    p_RXCDR_PH_RESET_ON_EIDLE = 0b0,
    p_RXCDR_LOCK_CFG          = 0b010101,

    # ===== RX Equalizer =====
    p_RXLPM_HF_CFG            = 0b00000011110000,
    p_RXLPM_LF_CFG            = 0b00000011110000,
    p_RX_DFE_GAIN_CFG         = 0x020FEA,
    p_RX_DFE_H2_CFG           = 0b000000000000,
    p_RX_DFE_H3_CFG           = 0b000001000000,
    p_RX_DFE_H4_CFG           = 0b00011110000,
    p_RX_DFE_H5_CFG           = 0b00011100000,
    p_RX_DFE_KL_CFG           = 0b0000011111110,
    p_RX_DFE_LPM_CFG          = 0x0954,
    p_RX_DFE_LPM_HOLD_DURING_EIDLE = 0b0,
    p_RX_DFE_UT_CFG           = 0b10001111000000000,
    p_RX_DFE_VP_CFG           = 0b00011111100000011,

    # ===== RX OOB (Out of Band) Signaling =====
    p_RXOOB_CFG               = 0b0000110,
    p_SATA_BURST_SEQ_LEN      = 0b0101,  # Not used for PCIe
    p_SATA_BURST_VAL          = 0b100,
    p_SATA_EIDLE_VAL          = 0b100,

    # ===== RX Buffer =====
    p_RXBUF_ADDR_MODE         = "FULL",
    p_RXBUF_EIDLE_HI_CNT      = 0b1000,
    p_RXBUF_EIDLE_LO_CNT      = 0b0000,
    p_RXBUF_EN                = "FALSE",  # Disabled for PCIe PIPE
    p_RXBUF_RESET_ON_CB_CHANGE = "TRUE",
    p_RXBUF_RESET_ON_COMMAALIGN = "FALSE",
    p_RXBUF_RESET_ON_EIDLE    = "FALSE",
    p_RXBUF_RESET_ON_RATE_CHANGE = "TRUE",
    p_RXBUF_THRESH_OVFLW      = 61,
    p_RXBUF_THRESH_OVRD       = "FALSE",
    p_RXBUF_THRESH_UNDFLW     = 4,

    # ===== RX Byte and Word Alignment =====
    p_ALIGN_COMMA_DOUBLE      = "FALSE",
    p_ALIGN_COMMA_ENABLE      = 0b1111111111,  # Enable all comma patterns
    p_ALIGN_COMMA_WORD        = (data_width == 20) ? 2 : 4,
    p_ALIGN_MCOMMA_DET        = "TRUE",
    p_ALIGN_MCOMMA_VALUE      = 0b1010000011,  # K28.5- = 0x17C
    p_ALIGN_PCOMMA_DET        = "TRUE",
    p_ALIGN_PCOMMA_VALUE      = 0b0101111100,  # K28.5+ = 0x0BC
    p_SHOW_REALIGN_COMMA      = "TRUE",
    p_RXSLIDE_AUTO_WAIT       = 7,
    p_RXSLIDE_MODE            = "PCS",  # Not using RX buffer
    p_RX_SIG_VALID_DLY        = 10,

    # ===== RX 8B/10B Decoder (DISABLED - using software) =====
    p_RX_DISPERR_SEQ_MATCH    = "TRUE",
    p_DEC_MCOMMA_DETECT       = "TRUE",
    p_DEC_PCOMMA_DETECT       = "TRUE",
    p_DEC_VALID_COMMA_ONLY    = "TRUE",

    # ===== RX Clock Correction (DISABLED for PIPE) =====
    p_CBCC_DATA_SOURCE_SEL    = "DECODED",
    p_CLK_COR_SEQ_2_USE       = "FALSE",
    p_CLK_COR_KEEP_IDLE       = "FALSE",
    p_CLK_COR_MAX_LAT         = 9 if data_width == 20 else 20,
    p_CLK_COR_MIN_LAT         = 7 if data_width == 20 else 16,
    p_CLK_COR_PRECEDENCE      = "TRUE",
    p_CLK_COR_REPEAT_WAIT     = 0,
    p_CLK_COR_SEQ_LEN         = 1,
    p_CLK_COR_SEQ_1_ENABLE    = 0b1111,
    p_CLK_COR_SEQ_1_1         = 0b0100000000,  # K28.5
    p_CLK_CORRECT_USE         = "FALSE",  # Disabled for PIPE

    # ===== TX Buffer =====
    p_TXBUF_EN                = "FALSE",  # Disabled for PIPE
    p_TXBUF_RESET_ON_RATE_CHANGE = "TRUE",

    # ===== TX Phase Alignment =====
    p_TX_RXDETECT_CFG         = 0x1832,
    p_TX_RXDETECT_REF         = 0b100,

    # ===== TX Driver =====
    p_TX_DEEMPH0              = 0b00000,  # No de-emphasis
    p_TX_DEEMPH1              = 0b00000,
    p_TX_DRIVE_MODE           = "DIRECT",
    p_TX_MAINCURSOR_SEL       = 0b0,
    p_TX_MARGIN_FULL_0        = 0b1001110,
    p_TX_MARGIN_FULL_1        = 0b1001001,
    p_TX_MARGIN_FULL_2        = 0b1000101,
    p_TX_MARGIN_FULL_3        = 0b1000010,
    p_TX_MARGIN_FULL_4        = 0b1000000,
    p_TX_MARGIN_LOW_0         = 0b1000110,
    p_TX_MARGIN_LOW_1         = 0b1000100,
    p_TX_MARGIN_LOW_2         = 0b1000010,
    p_TX_MARGIN_LOW_3         = 0b1000000,
    p_TX_MARGIN_LOW_4         = 0b1000000,

    # ===== TX PRBS (for testing) =====
    p_TXPHDLY_CFG             = 0x084020,
    p_TXPH_CFG                = 0x0780,
    p_TXPH_MONITOR_SEL        = 0b00000,
    p_TXPCSRESET_TIME         = 0b00001,
    p_TXPI_GREY_SEL           = 0b0,
    p_TXPI_INVSTROBE_SEL      = 0b0,
    p_TXPI_PPMCLK_SEL         = "TXUSRCLK2",

    # ===== TX Gearbox (not used for 8b/10b) =====
    p_TXGEARBOX_EN            = "FALSE",
    p_GEARBOX_MODE            = 0b000,

    # ===== Power Down =====
    p_PD_TRANS_TIME_FROM_P2   = 0x03c,
    p_PD_TRANS_TIME_NONE_P2   = 0x3c,
    p_PD_TRANS_TIME_TO_P2     = 0x64,
    p_TRANS_TIME_RATE         = 0x0E,

    # ... (470+ more parameters from liteiclink)

    # ===== Clock Ports =====
    i_CPLLREFCLKSEL           = 0b001,
    i_TXSYSCLKSEL             = use_cpll ? 0b00 : 0b11,
    i_RXSYSCLKSEL             = use_cpll ? 0b00 : 0b11,
    i_TXOUTCLKSEL             = 0b010,  # TXOUTCLKPCS
    i_RXOUTCLKSEL             = 0b010,  # RXOUTCLKPCS

    # ... (continues for all 496 parameters)
)
```

#### Step 1.2: Add DRP (Dynamic Reconfiguration Port) interface

```python
# In S7GTXTransceiver class:

# DRP Interface for runtime reconfiguration
self.drp = DRPInterface()

# DRP ports in GTXE2_CHANNEL:
i_DRPCLK      = ClockSignal("sys"),
i_DRPADDR     = self.drp.addr,
i_DRPEN       = self.drp.en,
i_DRPDI       = self.drp.di,
i_DRPWE       = self.drp.we,
o_DRPRDY      = self.drp.rdy,
o_DRPDO       = self.drp.do,
```

#### Step 1.3: Add PRBS generator/checker ports

```python
# TX PRBS
self.tx_prbs_config = Signal(2)  # 00=off, 01=PRBS7, 10=PRBS23, 11=PRBS31

# RX PRBS
self.rx_prbs_config = Signal(2)
self.rx_prbs_errors = Signal(32)
self.rx_prbs_locked = Signal()

# In GTXE2_CHANNEL:
i_TXPRBSSEL       = tx_prbs_config,
i_RXPRBSSEL       = rx_prbs_config,
o_RXPRBSERR       = rx_prbs_err,
o_RXPRBSLOCKED    = self.rx_prbs_locked,
```

#### Step 1.4: Test complete primitive

```python
# test/phy/test_s7_gtx_complete.py

def test_gtx_has_all_essential_parameters(self):
    """GTX should have all essential PCIe parameters configured."""
    gtx = S7GTXTransceiver(...)

    # Verify primitive exists
    primitives = [s for s in gtx.specials if isinstance(s, Instance)]
    gtx_primitive = [p for p in primitives if p.of == "GTXE2_CHANNEL"][0]

    essential_params = [
        "CPLL_FBDIV", "CPLL_REFCLK_DIV",
        "RXCDR_CFG", "RXOUT_DIV", "TXOUT_DIV",
        "RX_DATA_WIDTH", "TX_DATA_WIDTH",
        # ... check ~100 essential params
    ]

    for param in essential_params:
        assert param in gtx_primitive.items, f"Missing {param}"

def test_gtx_software_8b10b_configured(self):
    """Verify hardware 8b/10b is disabled, software is enabled."""
    gtx = S7GTXTransceiver(...)

    # Hardware 8b/10b should be OFF
    assert gtx_primitive.items["i_TX8B10BEN"] == 0
    assert gtx_primitive.items["i_RX8B10BEN"] == 0

    # Software encoder/decoder should exist
    assert hasattr(gtx, 'encoder')
    assert isinstance(gtx.encoder, Encoder)
```

#### Step 1.5: Commit complete GTX primitive

```bash
git add litepcie/phy/xilinx/s7_gtx.py test/phy/test_s7_gtx_complete.py
git commit -m "feat(phy): Complete GTX primitive instantiation with 496 parameters

Transform S7GTXTransceiver from skeleton to production-ready:
- Add all 496 GTXE2_CHANNEL parameters from UG476
- Configure RX CDR for 2.5/5.0 GT/s line rates
- Add RX equalizer settings (DFE/LPM)
- Configure TX driver and de-emphasis
- Add DRP interface for runtime reconfiguration
- Add PRBS generators for BER testing
- Verify software 8b/10b (TX8B10BEN=0, RX8B10BEN=0)

Based on proven liteiclink implementation with 1,241 lines.
Ready for hardware validation.

References:
- liteiclink gtx_7series.py
- Xilinx UG476: 7 Series GTX/GTH Transceivers

Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: Harden GTX Reset Sequence to AR43482 Standard (1.5 days)

**Goal:** Implement production-quality reset sequence matching liteiclink's AR43482-compliant GTXInit

**Files:**
- Modify: `litepcie/phy/xilinx/s7_gtx.py` (GTXResetSequencer class)
- Create: `test/phy/test_s7_gtx_reset_sequence.py`
- Reference: `liteiclink/liteiclink/serdes/gtx_7series_init.py`

#### Step 2.1: Expand reset FSM to 8 states

Current Phase 9 has basic reset. Expand to match liteiclink:

```python
# litepcie/phy/xilinx/s7_gtx.py

class GTXResetSequencer(LiteXModule):
    """
    GTX reset sequence following Xilinx AR43482.

    Implements production-quality 8-state FSM for reliable GTX initialization.

    References:
    - Xilinx AR43482: GTX Reset Sequence
    - liteiclink gtx_7series_init.py
    """

    def __init__(self, sys_clk_freq):
        # Inputs (from GTX)
        self.plllock         = Signal()  # PLL locked
        self.resetdone       = Signal()  # GTX reset done
        self.dlysresetdone   = Signal()  # Delay alignment done
        self.phaligndone     = Signal()  # Phase alignment done

        # Outputs (to GTX)
        self.pllreset        = Signal()  # PLL reset
        self.gtxreset        = Signal()  # GTX reset
        self.gtxpd           = Signal()  # GTX power down
        self.dlysreset       = Signal()  # Delay reset
        self.userrdy         = Signal()  # User ready

        # Status
        self.done            = Signal()  # Initialization complete
        self.restart         = Signal()  # Restart initialization

        # # #

        # Double-latch asynchronous signals (critical for metastability)
        plllock       = Signal()
        resetdone     = Signal()
        dlysresetdone = Signal()
        phaligndone   = Signal()
        self.specials += [
            MultiReg(self.plllock,       plllock),
            MultiReg(self.resetdone,     resetdone),
            MultiReg(self.dlysresetdone, dlysresetdone),
            MultiReg(self.phaligndone,   phaligndone),
        ]

        # Detect phaligndone rising edge
        phaligndone_r      = Signal(reset=1)
        phaligndone_rising = Signal()
        self.sync += phaligndone_r.eq(phaligndone)
        self.comb += phaligndone_rising.eq(phaligndone & ~phaligndone_r)

        # Deglitch FSM outputs driving GTX asynchronous inputs
        gtxreset_i   = Signal()
        gtxpd_i      = Signal()
        dlysreset_i  = Signal()
        userrdy_i    = Signal()
        self.sync += [
            self.gtxreset.eq(gtxreset_i),
            self.gtxpd.eq(gtxpd_i),
            self.dlysreset.eq(dlysreset_i),
            self.userrdy.eq(userrdy_i),
        ]

        # FSM
        self.fsm = fsm = ResetInserter()(FSM(reset_state="POWER-DOWN"))

        # State 1: POWER-DOWN (hold in reset)
        fsm.act("POWER-DOWN",
            gtxreset_i.eq(1),
            gtxpd_i.eq(1),
            self.pllreset.eq(1),
            NextState("WAIT-PLL-RESET")
        )

        # State 2: WAIT-PLL-RESET (wait for PLL to lock)
        fsm.act("WAIT-PLL-RESET",
            gtxreset_i.eq(1),
            If(plllock,
                NextState("WAIT-INIT-DELAY")
            )
        )

        # State 3: WAIT-INIT-DELAY
        # **AR43482 CRITICAL:** Wait 500ns after config before GTX reset
        init_delay = WaitTimer(int(500e-9 * sys_clk_freq))
        self.submodules += init_delay
        self.comb += init_delay.wait.eq(1)

        fsm.act("WAIT-INIT-DELAY",
            gtxreset_i.eq(1),
            If(init_delay.done,
                NextState("GTX-RESET")
            )
        )

        # State 4: GTX-RESET (release GTX reset, wait for done)
        fsm.act("GTX-RESET",
            gtxreset_i.eq(0),  # Release reset
            If(resetdone,
                NextState("WAIT-USERRDY-DELAY")
            )
        )

        # State 5: WAIT-USERRDY-DELAY (delay before asserting userrdy)
        userrdy_delay = WaitTimer(int(500e-9 * sys_clk_freq))
        self.submodules += userrdy_delay

        fsm.act("WAIT-USERRDY-DELAY",
            userrdy_delay.wait.eq(1),
            If(userrdy_delay.done,
                NextState("ASSERT-USERRDY")
            )
        )

        # State 6: ASSERT-USERRDY (enable user interface)
        fsm.act("ASSERT-USERRDY",
            userrdy_i.eq(1),
            NextState("WAIT-ALIGN")
        )

        # State 7: WAIT-ALIGN (wait for phase alignment)
        align_timeout = WaitTimer(int(1e-3 * sys_clk_freq))  # 1ms timeout
        self.submodules += align_timeout

        fsm.act("WAIT-ALIGN",
            userrdy_i.eq(1),
            align_timeout.wait.eq(1),
            If(phaligndone_rising,
                NextState("READY")
            ).Elif(align_timeout.done,
                NextState("ERROR")  # Timeout
            )
        )

        # State 8: READY (normal operation)
        fsm.act("READY",
            userrdy_i.eq(1),
            self.done.eq(1),
            If(self.restart,
                NextState("POWER-DOWN")
            )
        )

        # ERROR state (restart on error)
        error_timeout = WaitTimer(int(10e-3 * sys_clk_freq))  # 10ms
        self.submodules += error_timeout

        fsm.act("ERROR",
            error_timeout.wait.eq(1),
            If(error_timeout.done,
                NextState("POWER-DOWN")  # Restart
            )
        )

        # Auto-restart on reset or PLL unlock
        self.comb += fsm.reset.eq(self.restart | ~plllock)
```

#### Step 2.2: Test reset sequence timing

```python
# test/phy/test_s7_gtx_reset_sequence.py

def test_reset_sequence_ar43482_timing(self):
    """
    Verify AR43482 500ns delay before GTX reset release.

    Critical for reliable GTX initialization.
    """
    dut = GTXResetSequencer(sys_clk_freq=125e6)

    def testbench():
        # Start in POWER-DOWN
        assert (yield dut.gtxreset) == 1
        assert (yield dut.pllreset) == 1

        # Simulate PLL lock
        yield dut.plllock.eq(1)
        yield from wait_fsm_state(dut.fsm, "WAIT-INIT-DELAY")

        # Count cycles in WAIT-INIT-DELAY
        cycles = 0
        while (yield dut.gtxreset) == 1:
            yield
            cycles += 1
            if cycles > 1000:
                break

        # Should be ~63 cycles @ 125 MHz (500ns)
        expected_cycles = int(500e-9 * 125e6)
        assert abs(cycles - expected_cycles) < 5, \
            f"AR43482 timing: expected {expected_cycles}, got {cycles}"

    run_simulation(dut, testbench())

def test_reset_sequence_phase_alignment(self):
    """Verify phase alignment detection."""
    dut = GTXResetSequencer(sys_clk_freq=125e6)

    def testbench():
        # Fast-forward to WAIT-ALIGN state
        yield dut.plllock.eq(1)
        yield from advance_to_state(dut.fsm, "WAIT-ALIGN")

        # Simulate phaligndone rising edge
        yield dut.phaligndone.eq(0)
        yield
        yield dut.phaligndone.eq(1)
        yield
        yield

        # Should transition to READY
        assert (yield from fsm_state(dut.fsm)) == "READY"
        assert (yield dut.done) == 1

    run_simulation(dut, testbench())
```

---

### Task 3: Complete GTY Primitive for UltraScale+ (2 days)

Similar process to GTX but with GTYE4_CHANNEL (~500 parameters).

**Key differences:**
- QPLL0 vs QPLL1 selection (automatic based on frequency)
- Different CDR settings for higher speeds
- UG576 timing requirements
- Gen3 support architecture

---

### Task 4: Complete ECP5 DCUA Primitive (2 days)

**Goal:** Transform ECP5 skeleton into full DCUA instantiation

**Reference:** ECP5-PCIe `ecp5_serdes.py` (Amaranth) → port to Migen

**Files:**
- Modify: `litepcie/phy/lattice/ecp5_serdes.py`
- Reference: `.tmp/reference-repos/ECP5-PCIe/Gateware/ecp5_pcie/ecp5_serdes.py`

#### Step 4.1: Port Amaranth DCUA to Migen

```python
# ECP5-PCIe uses Amaranth's Instance, port to Migen

# Amaranth (reference):
m.submodules.dcu = Instance("DCUA",
    # Amaranth syntax
)

# Migen (LitePCIe):
self.specials += Instance("DCUA",
    # Migen syntax with p_, i_, o_ prefixes
)
```

#### Step 4.2: Add SCI (SerDes Client Interface) runtime control

```python
# SCI allows runtime reconfiguration of ECP5 SERDES

class ECP5SCIInterface(LiteXModule):
    """SerDes Client Interface for ECP5 DCU runtime configuration."""

    def __init__(self):
        self.addr      = Signal(6)   # SCI address
        self.wdata     = Signal(8)   # Write data
        self.rdata     = Signal(8)   # Read data
        self.sel       = Signal(4)   # Channel select
        self.rdwrn     = Signal()    # Read=1, Write=0
        self.req       = Signal()    # Request
        self.ack       = Signal()    # Acknowledge

# Connect to DCUA:
i_D_SCIWDATA      = self.sci.wdata,
o_D_SCIRDATA      = self.sci.rdata,
i_D_SCIADDR       = self.sci.addr,
i_D_SCISEL        = self.sci.sel,
i_D_SCIRD         = self.sci.rdwrn,
i_D_SCIENAUX      = self.sci.req,
o_D_SCIINT        = self.sci.ack,
```

---

### Task 5: Add Clock Aligner for Comma Detection (1.5 days)

**Goal:** Implement brute-force clock aligner for symbol alignment

**Reference:** `liteiclink/liteiclink/serdes/clock_aligner.py`

```python
# litepcie/phy/common/clock_aligner.py

class BruteforceClockAligner(LiteXModule):
    """
    Brute-force clock alignment by trying all bit slips.

    Searches for comma character (K28.5) to achieve symbol alignment.
    """

    def __init__(self, comma=0b0101111100, check_period=1024):
        self.rxdata  = Signal(10)  # Raw 10-bit symbols
        self.slip    = Signal()     # Bit slip control
        self.aligned = Signal()     # Alignment achieved

        # # #

        # Comma detection
        comma_detected = Signal()
        self.comb += comma_detected.eq(self.rxdata == comma)

        # FSM
        self.submodules.fsm = fsm = FSM(reset_state="WAIT")

        slip_count = Signal(max=32)
        check_count = Signal(max=check_period)

        fsm.act("WAIT",
            NextValue(check_count, check_count + 1),
            If(comma_detected,
                NextState("ALIGNED")
            ).Elif(check_count == check_period - 1,
                NextState("SLIP")
            )
        )

        fsm.act("SLIP",
            self.slip.eq(1),
            NextValue(slip_count, slip_count + 1),
            NextValue(check_count, 0),
            If(slip_count == 31,
                NextState("ERROR")  # Tried all positions
            ).Else(
                NextState("WAIT")
            )
        )

        fsm.act("ALIGNED",
            self.aligned.eq(1)
        )

        fsm.act("ERROR",
            # Restart alignment
            NextValue(slip_count, 0),
            NextValue(check_count, 0),
            NextState("WAIT")
        )
```

---

### Task 6: Add PRBS Generators and BER Measurement (1 day)

**Goal:** Built-in BER testing for signal integrity validation

**Reference:** `liteiclink` PRBSTX/PRBSRX

```python
# litepcie/phy/common/prbs.py

# Already exists in litex.soc.cores.prbs
# Just need to instantiate in wrappers

class GTXWithPRBS(GTX):
    """GTX wrapper with PRBS testing."""

    def __init__(self, ...):
        super().__init__(...)

        # TX PRBS generator
        self.submodules.tx_prbs = ClockDomainsRenamer("tx")(
            PRBSTX(data_width=20, prbs_type="prbs31")
        )

        # RX PRBS checker
        self.submodules.rx_prbs = ClockDomainsRenamer("rx")(
            PRBSRX(data_width=20, prbs_type="prbs31")
        )

        # Mux: normal data or PRBS
        self.comb += [
            If(self.tx_prbs_enable,
                # Send PRBS
                self.encoder.input.eq(self.tx_prbs.o)
            ).Else(
                # Send normal data
                self.encoder.input.eq(self.tx_data)
            )
        ]

        # BER counter
        self.rx_prbs_errors = Signal(32)
        self.sync.rx += [
            If(self.rx_prbs.error,
                self.rx_prbs_errors.eq(self.rx_prbs_errors + 1)
            )
        ]
```

---

### Task 7: Improve CDC for Control/Status Signals (1 day)

**Goal:** Add MultiReg for all control/status crossings

**Current:** Only data uses AsyncFIFO
**Needed:** Control signals need proper CDC

```python
# In each transceiver wrapper:

# TX control CDC (sys → tx)
self.tx_elecidle_sys = Signal()
tx_elecidle_tx = Signal()
self.specials += MultiReg(self.tx_elecidle_sys, tx_elecidle_tx, "tx")

# RX status CDC (rx → sys)
rx_valid_rx = Signal()
self.rx_valid_sys = Signal()
self.specials += MultiReg(rx_valid_rx, self.rx_valid_sys, "sys")

# Speed control CDC
self.speed_sys = Signal(2)
speed_tx = Signal(2)
self.specials += MultiReg(self.speed_sys, speed_tx, "tx")
```

---

### Task 8: Hardware Validation Infrastructure (2 days)

**Goal:** Create hardware test designs for FPGA validation

**Files:**
- Create: `examples/hardware_validation/pcie_gtx_loopback.py`
- Create: `examples/hardware_validation/pcie_ecp5_loopback.py`
- Create: `docs/hardware-validation-guide.md`

#### Step 8.1: GTX loopback test design

```python
# examples/hardware_validation/pcie_gtx_loopback.py

from migen import *
from litex.soc.cores.clock import S7MMCM
from litex.soc.integration.soc import SoCCore
from litex.build.generic_platform import Pins, Subsignal

from litepcie.phy.xilinx.s7_gtx import S7GTXTransceiver

class GTXLoopbackSoC(SoCCore):
    """
    Hardware validation SoC for GTX loopback testing.

    Tests:
    - GTX initialization and reset sequence
    - Internal loopback (TX → RX)
    - PRBS BER measurement
    - Clock recovery

    Hardware: Kintex-7 KC705 or similar
    """

    def __init__(self, platform):
        sys_clk_freq = 125e6

        # SoC
        SoCCore.__init__(self, platform, sys_clk_freq,
            integrated_rom_size=0x8000,
            integrated_main_ram_size=0x4000,
            uart_name="crossover"
        )

        # GTX
        gtx_pads = platform.request("sfp", 0)
        refclk_pads = platform.request("sfp_refclk", 0)

        self.submodules.gtx = S7GTXTransceiver(
            platform=platform,
            pads=gtx_pads,
            refclk_pads=refclk_pads,
            refclk_freq=125e6,
            sys_clk_freq=sys_clk_freq,
            data_width=20,
            gen=1
        )

        # Internal loopback
        self.comb += self.gtx.loopback.eq(0b010)  # Near-end PCS loopback

        # PRBS generator/checker
        self.add_csr("gtx")

        # CSRs for control
        from litex.soc.interconnect.csr import CSRStorage, CSRStatus

        self.gtx_prbs_enable = CSRStorage(1, description="Enable PRBS31 transmission")
        self.gtx_prbs_errors = CSRStatus(32, description="PRBS error count")
        self.gtx_status = CSRStatus(8, description="GTX status (bit 0=tx_ready, bit 1=rx_ready, bit 2=aligned)")

        # Connect
        self.comb += [
            self.gtx.tx_prbs_enable.eq(self.gtx_prbs_enable.storage),
            self.gtx_prbs_errors.status.eq(self.gtx.rx_prbs_errors),
            self.gtx_status.status.eq(Cat(
                self.gtx.tx_ready,
                self.gtx.rx_ready,
                self.gtx.aligned
            ))
        ]

        # LiteScope for debugging
        from litescope import LiteScopeAnalyzer
        analyzer_signals = [
            self.gtx.tx_data,
            self.gtx.tx_datak,
            self.gtx.rx_data,
            self.gtx.rx_datak,
            self.gtx.tx_ready,
            self.gtx.rx_ready,
            self.gtx.reset_sequencer.fsm,
        ]
        self.submodules.analyzer = LiteScopeAnalyzer(
            analyzer_signals,
            depth=4096,
            clock_domain="sys"
        )

def main():
    from litex.build.xilinx import XilinxPlatform
    # Load KC705 platform
    platform = ...

    soc = GTXLoopbackSoC(platform)
    builder = Builder(soc, output_dir="build/gtx_loopback")
    builder.build()

if __name__ == "__main__":
    main()
```

#### Step 8.2: Hardware validation procedure

```markdown
# docs/hardware-validation-guide.md

# Hardware Validation Guide

## GTX Loopback Test

### Hardware Setup
1. Kintex-7 KC705 board
2. SFP loopback cable (optional - using internal loopback)
3. JTAG programmer

### Build and Load
```bash
cd examples/hardware_validation
python pcie_gtx_loopback.py
```

### Test Procedure

**1. Check GTX Initialization:**
```python
# In litex_server console
from litex import RemoteClient
bus = RemoteClient()
bus.open()

# Check GTX status
status = bus.regs.gtx_status.read()
tx_ready = (status >> 0) & 1
rx_ready = (status >> 1) & 1
aligned  = (status >> 2) & 1

print(f"TX Ready: {tx_ready}")
print(f"RX Ready: {rx_ready}")
print(f"Aligned:  {aligned}")

# All should be 1
assert tx_ready and rx_ready and aligned
```

**2. Run PRBS Test:**
```python
# Enable PRBS31 transmission
bus.regs.gtx_prbs_enable.write(1)

# Wait 1 second
import time
time.sleep(1)

# Check errors
errors = bus.regs.gtx_prbs_errors.read()
print(f"PRBS errors: {errors}")

# Should be 0 for good signal integrity
assert errors == 0
```

**3. Capture Waveforms:**
```python
from litescope import LiteScopeAnalyzerDriver

analyzer = LiteScopeAnalyzerDriver(bus.regs, "analyzer", debug=True)
analyzer.configure_trigger(cond={"gtx_tx_ready": 1})
analyzer.run(offset=128, length=512)
analyzer.wait_done()
analyzer.upload()
analyzer.save("gtx_loopback.vcd")
```

**4. Analyze Results:**
- Open gtx_loopback.vcd in GTKWave
- Verify TX data appears on RX
- Check K-characters are detected
- Verify alignment signals
```

---

### Task 9: Performance Benchmarking (1 day)

**Goal:** Compare performance against reference implementations

**Metrics:**
- Resource utilization (LUTs, FFs, BRAMs)
- Clock frequency (Fmax)
- Latency (TX to RX)
- Throughput (Gbps)

```python
# examples/benchmarks/compare_implementations.py

def benchmark_litepcie_vs_liteiclink():
    """
    Compare LitePCIe GTX vs liteiclink GTX.

    Metrics:
    - Resource usage
    - Achievable Fmax
    - Latency
    """

    # Build both
    build_litepcie_gtx()
    build_liteiclink_gtx()

    # Parse reports
    litepcie_resources = parse_vivado_utilization("build/litepcie_gtx/")
    liteiclink_resources = parse_vivado_utilization("build/liteiclink_gtx/")

    # Compare
    print("Resource Comparison:")
    print(f"LitePCIe:  {litepcie_resources['LUTs']} LUTs, {litepcie_resources['FFs']} FFs")
    print(f"liteiclink: {liteiclink_resources['LUTs']} LUTs, {liteiclink_resources['FFs']} FFs")

    # Expect similar (both use software 8b/10b)
```

---

### Task 10: Documentation and Completion (1 day)

**Goal:** Document all improvements and create migration guide

**Files:**
- Update: `docs/phase-9-completion-summary.md`
- Create: `docs/reference-comparison.md`
- Create: `docs/hardware-validation-results.md`
- Update: `docs/implementation-status.md`

```markdown
# docs/reference-comparison.md

# Reference Implementation Comparison Results

## Summary

LitePCIe Phase 9 transceiver implementation has been upgraded to **production quality** by:

1. ✅ Complete primitive instantiation (496 parameters for GTX)
2. ✅ AR43482-compliant reset sequence
3. ✅ Proper CDC for all signals
4. ✅ PRBS generators for BER testing
5. ✅ Clock aligner for symbol alignment
6. ✅ Hardware validation infrastructure
7. ✅ Performance benchmarking

## Comparison Matrix

| Feature | Phase 9 (Before) | Phase 9 (After) | liteiclink | Status |
|---------|------------------|-----------------|------------|--------|
| GTX Parameters | 9 | 496 | 496 | ✅ Match |
| Reset Sequence | Basic | AR43482 | AR43482 | ✅ Match |
| 8b/10b Strategy | Software | Software | Software | ✅ Match |
| PRBS Testing | None | PRBS7/23/31 | PRBS7/23/31 | ✅ Match |
| Clock Aligner | None | Brute-force | Brute-force | ✅ Match |
| Hardware Tested | No | Yes | Yes | ✅ Match |

## Performance Results

**Resource Usage (Kintex-7):**
- LitePCIe GTX: X LUTs, Y FFs
- liteiclink GTX: X LUTs, Y FFs
- Overhead: <5% (acceptable)

**Latency:**
- TX to RX (loopback): N ns
- Matches liteiclink: ✅

**BER (Bit Error Rate):**
- PRBS31 @ 2.5 GT/s: 0 errors (10^12 bits tested)
- PRBS31 @ 5.0 GT/s: 0 errors (10^12 bits tested)

## Conclusion

LitePCIe Phase 9 transceivers are now **production-ready** and **validated** against industry-standard reference implementations.
```

---

## Success Criteria

### Functionality
- ✅ All 496 GTX parameters configured
- ✅ AR43482-compliant reset sequence
- ✅ PRBS BER testing: 0 errors @ 10^12 bits
- ✅ Hardware loopback working on FPGA
- ✅ Clock alignment achieving lock
- ✅ Software 8b/10b matching liteiclink

### Testing
- ✅ All existing tests still pass (53/53)
- ✅ New hardware tests pass on real FPGA
- ✅ PRBS BER < 10^-12
- ✅ Reset sequence timing verified
- ✅ CDC verified (no metastability)

### Performance
- ✅ Resource usage within 10% of liteiclink
- ✅ Achieves target line rates (2.5/5.0 GT/s)
- ✅ Latency comparable to reference
- ✅ No timing violations

### Code Quality
- ✅ All tests passing
- ✅ Code follows LiteX patterns
- ✅ Comprehensive docstrings
- ✅ Hardware validated

### Documentation
- ✅ Reference comparison document
- ✅ Hardware validation guide
- ✅ Performance benchmark results
- ✅ Migration guide for users

---

## Timeline

| Task | Effort | Priority | Dependencies |
|------|--------|----------|--------------|
| 1. Complete GTX Primitive | 3 days | 🔴 CRITICAL | None |
| 2. Harden Reset Sequence | 1.5 days | 🟡 HIGH | Task 1 |
| 3. Complete GTY Primitive | 2 days | 🔴 CRITICAL | Task 1, 2 |
| 4. Complete ECP5 DCUA | 2 days | 🔴 CRITICAL | None |
| 5. Add Clock Aligner | 1.5 days | 🟡 HIGH | Task 1 |
| 6. Add PRBS/BER Testing | 1 day | 🟢 MEDIUM | Task 1 |
| 7. Improve CDC | 1 day | 🟡 HIGH | Task 1 |
| 8. Hardware Validation | 2 days | 🔴 CRITICAL | All above |
| 9. Performance Benchmarking | 1 day | 🟢 MEDIUM | Task 8 |
| 10. Documentation | 1 day | 🟡 HIGH | All above |

**Total:** 15.5 days

**Critical Path:** Task 1 → 2 → 3 → 8 → 10 (10 days)

---

## Risk Mitigation

### Technical Risks

**Risk:** Hardware testing reveals signal integrity issues
**Mitigation:** PRBS testing catches problems early, can adjust TX driver settings via DRP

**Risk:** Reset timing doesn't match AR43482 exactly
**Mitigation:** Reference liteiclink timing exactly, add oscilloscope verification

**Risk:** ECP5 DCUA has subtle differences from reference
**Mitigation:** Port Amaranth code carefully, test on real ECP5 FPGA

### Hardware Risks

**Risk:** No access to required FPGA boards
**Mitigation:** Can validate most functionality in simulation, hardware tests can be deferred

**Risk:** Board bring-up issues (clock, power)
**Mitigation:** Use known-good development boards (KC705, Versa ECP5)

---

## Conclusion

This plan transforms the Phase 9 **architectural skeleton** into a **production-ready, hardware-validated** transceiver implementation by:

1. **Completing primitive instantiation** (9 → 496 parameters)
2. **Hardening reset sequences** (AR43482 compliance)
3. **Adding test infrastructure** (PRBS, BER, loopback)
4. **Hardware validation** (real FPGA testing)
5. **Performance verification** (benchmarking vs liteiclink)

The architecture decisions from Phase 9 (software 8b/10b, base classes, modular design) are **validated** by matching liteiclink's proven approach.

With these improvements, LitePCIe will have **production-quality transceivers** ready for real PCIe applications.

**Next Steps:** Begin with Task 1 (Complete GTX Primitive) as it unblocks all other tasks.
