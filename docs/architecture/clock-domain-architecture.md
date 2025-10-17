# Clock Domain Architecture - LitePCIe PIPE/DLL Implementation

**Last Updated:** 2025-10-17
**Status:** Phase 9 Pre-Implementation Design
**Purpose:** Define clock domain strategy for internal transceiver integration

---

## Executive Summary

This document defines the clock domain architecture for LitePCIe, covering:
- **Phase 3-8:** Single "pcie" clock domain (external PHY)
- **Phase 9:** Multi-clock domain (internal transceivers with separate TX/RX clocks)
- **Migration Strategy:** AsyncFIFO-based CDC, minimal refactoring

**Key Decision:** Use AsyncFIFO CDC pattern from usb3_pipe for clean TX/RX clock separation without breaking existing Phase 3-8 code.

---

## Phase 3-8: Current Clock Architecture

### Clock Domains

```
┌─────────────────────────────────────────────────────────────┐
│                     System Clock Domain                      │
│                         ("sys")                              │
│  ┌────────────────────────────────────────────────────┐     │
│  │  TLP Layer                                         │     │
│  │  - Endpoint logic                                  │     │
│  │  - Packet assembly/disassembly                     │     │
│  └────────────────────────────────────────────────────┘     │
│                          ↓ ↑                                 │
│                   PHYTXDatapath / PHYRXDatapath              │
│                   (CDC: sys ↔ pcie via AsyncFIFO)            │
│                          ↓ ↑                                 │
└──────────────────────────┼─┼─────────────────────────────────┘
                           │ │
┌──────────────────────────┼─┼─────────────────────────────────┐
│                PCIe Clock Domain ("pcie")                     │
│                 125 MHz (Gen1) / 250 MHz (Gen2)              │
│  ┌────────────────────────────────────────────────────┐     │
│  │  Layout Converters                                 │     │
│  │  - PHYToDLLConverter / DLLToPHYConverter           │     │
│  └────────────────────────────────────────────────────┘     │
│                          ↓ ↑                                 │
│  ┌────────────────────────────────────────────────────┐     │
│  │  DLL Layer                                         │     │
│  │  - DLLTX (ACK/NAK, retry, sequence, LCRC)         │     │
│  │  - DLLRX (validation, reordering)                  │     │
│  └────────────────────────────────────────────────────┘     │
│                          ↓ ↑                                 │
│  ┌────────────────────────────────────────────────────┐     │
│  │  PIPE Interface                                    │     │
│  │  - K-character framing (STP/SDP/END/EDB)           │     │
│  │  - SKP ordered sets (clock compensation)           │     │
│  │  - TS1/TS2 (training sequences)                    │     │
│  │  - LTSSM (link training state machine)             │     │
│  └────────────────────────────────────────────────────┘     │
│                          ↓ ↑                                 │
│                    8-bit PIPE symbols                        │
│                    (pipe_tx_data/datak,                      │
│                     pipe_rx_data/datak)                      │
└──────────────────────────┼─┼─────────────────────────────────┘
                           │ │
                           │ │  External PIPE PHY Chip
                           │ │  (e.g., TI TUSB1310A)
                           │ │
                           │ │  PCLK output → drives "pcie" domain
                           ↓ ↑
                    PCIe Physical Layer
```

### Clock Domain Characteristics

| Domain | Frequency | Source | Purpose |
|--------|-----------|--------|---------|
| **sys** | Variable (user-defined) | Platform PLL | Core logic, TLP layer, endpoint |
| **pcie** | 125 MHz (Gen1), 250 MHz (Gen2) | External PHY PCLK output | DLL, PIPE, link training |

### Clock Domain Crossing (CDC)

**Location:** PHYTXDatapath / PHYRXDatapath
**Method:** AsyncFIFO (from litex.soc.interconnect.stream)
**Direction:** sys ↔ pcie

**Code Example (from litepcie/phy/common.py):**
```python
class PHYTXDatapath(Module):
    def __init__(self, core_data_width, pcie_data_width, clock_domain):
        # TX: sys → pcie
        self.cdc = stream.AsyncFIFO(
            layout      = phy_layout(pcie_data_width),
            depth       = 8,
            buffered    = True
        )
        self.cdc = ClockDomainsRenamer({
            "write": "sys",
            "read":  clock_domain  # "pcie"
        })(self.cdc)
```

### Design Constraints

1. **Single PCIE Clock:** External PHY provides one PCLK for both TX and RX
2. **No TX/RX Separation:** All PIPE/DLL logic runs on same clock
3. **Simple CDC:** Only one boundary (sys ↔ pcie)
4. **External Clock Source:** Platform must create "pcie" clock domain from PHY's PCLK

---

## Phase 9: Internal Transceiver Architecture

### Clock Domains

```
┌─────────────────────────────────────────────────────────────┐
│                     System Clock Domain                      │
│                         ("sys")                              │
│  ┌────────────────────────────────────────────────────┐     │
│  │  TLP Layer (unchanged)                             │     │
│  └────────────────────────────────────────────────────┘     │
│                          ↓ ↑                                 │
│                   PHYTXDatapath / PHYRXDatapath              │
│                   (CDC: sys ↔ pcie via AsyncFIFO)            │
│                          ↓ ↑                                 │
└──────────────────────────┼─┼─────────────────────────────────┘
                           │ │
┌──────────────────────────┼─┼─────────────────────────────────┐
│                PCIe Clock Domain ("pcie")                     │
│                 125 MHz (Gen1) / 250 MHz (Gen2)              │
│                 Derived from TX clock (see below)            │
│  ┌────────────────────────────────────────────────────┐     │
│  │  Layout Converters (unchanged)                     │     │
│  └────────────────────────────────────────────────────┘     │
│                          ↓ ↑                                 │
│  ┌────────────────────────────────────────────────────┐     │
│  │  DLL Layer (unchanged)                             │     │
│  └────────────────────────────────────────────────────┘     │
│                          ↓ ↑                                 │
│  ┌────────────────────────────────────────────────────┐     │
│  │  PIPE Interface (unchanged)                        │     │
│  └────────────────────────────────────────────────────┘     │
│                          ↓ ↑                                 │
└──────────────────────────┼─┼─────────────────────────────────┘
                           │ │
┌──────────────────────────┼─┼─────────────────────────────────┐
│                  Transceiver Wrapper                         │
│                      (NEW - Phase 9)                         │
│  ┌────────────────────┐          ┌────────────────────┐     │
│  │   TX Path          │          │   RX Path          │     │
│  │                    │          │                    │     │
│  │  ┌──────────────┐  │          │  ┌──────────────┐  │     │
│  │  │ TX CDC       │  │          │  │ RX CDC       │  │     │
│  │  │ AsyncFIFO    │  │          │  │ AsyncFIFO    │  │     │
│  │  │ pcie → tx    │  │          │  │ rx → pcie    │  │     │
│  │  └──────────────┘  │          │  └──────────────┘  │     │
│  │         ↓          │          │         ↑          │     │
│  │  ┌──────────────┐  │          │  ┌──────────────┐  │     │
│  │  │ 8b/10b       │  │          │  │ 8b/10b       │  │     │
│  │  │ Encoder      │  │          │  │ Decoder      │  │     │
│  │  └──────────────┘  │          │  └──────────────┘  │     │
│  │         ↓          │          │         ↑          │     │
│  └─────────┼──────────┘          └─────────┼──────────┘     │
│            │                               │                 │
│            │   "tx" domain                 │  "rx" domain    │
│            │   (txoutclk)                  │  (rxoutclk)     │
│            ↓                               ↑                 │
│  ┌──────────────────────────────────────────────────┐       │
│  │  GTX/GTY/ECP5 Transceiver Primitive             │       │
│  │  - 10-bit TX data (8b + 2b disparity)            │       │
│  │  - 10-bit RX data (8b + 2b disparity)            │       │
│  │  - Separate TX and RX clocks                     │       │
│  │  - TXOUTCLK: Recovered TX clock                  │       │
│  │  - RXOUTCLK: Recovered RX clock                  │       │
│  └──────────────────────────────────────────────────┘       │
└──────────────────────────┼─┼───────────────────────────────┘
                           │ │
                           ↓ ↑
                    PCIe Physical Layer
```

### Clock Domain Characteristics

| Domain | Frequency | Source | Purpose |
|--------|-----------|--------|---------|
| **sys** | Variable (user-defined) | Platform PLL | Core logic, TLP layer |
| **pcie** | 125 MHz (Gen1), 250 MHz (Gen2) | Derived from txoutclk (see below) | DLL, PIPE, link training |
| **tx** | 125 MHz (Gen1), 250 MHz (Gen2) | Transceiver TXOUTCLK | Transmit datapath, 8b/10b encoder |
| **rx** | 125 MHz (Gen1), 250 MHz (Gen2) | Transceiver RXOUTCLK | Receive datapath, 8b/10b decoder |

### "pcie" Clock Domain Source

**Strategy:** Drive "pcie" domain from TXOUTCLK (transmit clock)

**Rationale:**
- TX clock is the reference (driven by local oscillator)
- RX clock tracks remote transmitter (may have slight frequency offset)
- PIPE/DLL/LTSSM should run on stable TX clock
- RX CDC handles any frequency mismatch via AsyncFIFO

**Implementation:**
```python
# In transceiver wrapper (e.g., litepcie/phy/xilinx_7series.py)
# Create "pcie" clock domain from TXOUTCLK
self.clock_domains.cd_pcie = ClockDomain()
self.comb += self.cd_pcie.clk.eq(txoutclk)

# Platform constraint
platform.add_period_constraint(self.cd_pcie.clk, 1e9/125e6)  # 8ns for Gen1
```

### Clock Domain Crossing (CDC)

**Two CDC Boundaries:**

#### 1. sys ↔ pcie (Unchanged from Phase 3-8)
- **Location:** PHYTXDatapath / PHYRXDatapath
- **Method:** AsyncFIFO
- **Direction:** Bidirectional

#### 2. pcie ↔ tx/rx (NEW in Phase 9)
- **Location:** Transceiver wrapper TX/RX datapaths
- **Method:** AsyncFIFO (following usb3_pipe pattern)
- **Direction:**
  - TX: pcie → tx (PIPE symbols → 8b/10b encoder)
  - RX: rx → pcie (8b/10b decoder → PIPE symbols)

**Code Example (adapted from usb3_pipe):**
```python
class TransceiverTXDatapath(Module):
    def __init__(self):
        # Input from PIPE (in "pcie" domain): 8-bit symbols
        self.sink = stream.Endpoint([("data", 8), ("datak", 1)])

        # Output to transceiver (in "tx" domain): 10-bit encoded
        self.source = stream.Endpoint([("data", 10)])

        # CDC: pcie → tx
        self.cdc = stream.AsyncFIFO(
            layout   = [("data", 8), ("datak", 1)],
            depth    = 8,
            buffered = True
        )
        self.cdc = ClockDomainsRenamer({
            "write": "pcie",
            "read":  "tx"
        })(self.cdc)

        self.comb += self.sink.connect(self.cdc.sink)

        # 8b/10b encoder (in "tx" domain)
        self.encoder = ClockDomainsRenamer("tx")(Encoder(...))
        self.comb += self.cdc.source.connect(self.encoder.sink)
        self.comb += self.encoder.source.connect(self.source)
```

---

## Migration Strategy: Phase 8 → Phase 9

### Goal
Enable Phase 9 internal transceivers WITHOUT breaking Phase 3-8 external PHY support.

### Strategy: Drop-In Replacement

Both PIPEExternalPHY (Phase 8) and internal transceiver wrappers (Phase 9) present the same interface:

**Common Interface:**
```python
class PHYWrapper:  # Base abstraction
    # TLP layer interface (in "sys" domain)
    self.sink = stream.Endpoint(phy_layout(data_width))
    self.source = stream.Endpoint(phy_layout(data_width))

    # MSI interface
    self.msi = stream.Endpoint(msi_layout())

    # Configuration
    self.data_width = data_width
    self.bar0_mask = get_bar_mask(bar0_size)

    # Status
    self.link_up = Signal()  # From LTSSM
```

**Phase 8 Implementation:**
```python
# External PHY - platform provides "pcie" clock from PHY's PCLK
phy = PIPEExternalPHY(
    platform   = platform,
    pads       = platform.request("pcie_pipe"),  # External PHY pads
    data_width = 64,
    cd         = "sys"
)
# Platform must: self.cd_pcie.clk = pads.pclk
```

**Phase 9 Implementation:**
```python
# Internal transceiver - creates "pcie" clock from TXOUTCLK
phy = Xilinx7SeriesPCIePHY(
    platform   = platform,
    pads       = platform.request("pcie_x1"),  # PCIe connector pads
    data_width = 64,
    cd         = "sys"
)
# Wrapper creates: self.cd_pcie.clk = txoutclk
```

### No Refactoring Required

✅ **Phase 3-8 code unchanged:**
- DLL (DLLTX, DLLRX)
- PIPE interface (K-chars, SKP, TS1/TS2)
- LTSSM (link training)
- Layout converters

✅ **Only change:** Replace PHY wrapper instantiation

### Clock Domain Validation

**Phase 8 Check:**
```python
# In platform file or SoC
assert hasattr(platform, "cd_pcie"), "Platform must provide 'pcie' clock domain"
```

**Phase 9 Check:**
```python
# Transceiver wrapper creates cd_pcie internally
assert hasattr(phy, "cd_pcie"), "PHY must create 'pcie' clock domain"
```

---

## Reference Implementation Patterns

### usb3_pipe Approach

**Clock Domains:**
```python
# usb3_pipe/serdes.py
class K7USB3SerDes(Module):
    # Creates separate TX and RX clock domains
    self.clock_domains.cd_tx = ClockDomain()
    self.clock_domains.cd_rx = ClockDomain()

    # Driven from GTX
    self.comb += [
        self.cd_tx.clk.eq(gtx.txoutclk),
        self.cd_rx.clk.eq(gtx.rxoutclk)
    ]

    # CDC for each direction
    tx_cdc = AsyncFIFO(..., w_domain="sys", r_domain="tx")
    rx_cdc = AsyncFIFO(..., w_domain="rx", r_domain="sys")
```

**Adaptation for LitePCIe:**
```python
# litepcie/phy/xilinx_7series.py
class Xilinx7SeriesPCIePHY(Module):
    # Create pcie, tx, rx domains
    self.clock_domains.cd_pcie = ClockDomain()
    self.clock_domains.cd_tx = ClockDomain()
    self.clock_domains.cd_rx = ClockDomain()

    # pcie = tx (stable reference)
    self.comb += [
        self.cd_pcie.clk.eq(gtx.txoutclk),
        self.cd_tx.clk.eq(gtx.txoutclk),
        self.cd_rx.clk.eq(gtx.rxoutclk)
    ]
```

### ECP5-PCIe Approach

**Clock Domains:**
```python
# ECP5-PCIe uses single DCUA for TX and RX
# Separate TX and RX clocks from DCUA outputs
tx_clk = Signal()
rx_clk = Signal()

# CTC FIFO for clock tolerance compensation
# (similar function to AsyncFIFO in Xilinx)
```

---

## Design Decisions Summary

| Decision | Rationale |
|----------|-----------|
| **"pcie" domain = TXOUTCLK** | TX clock is stable reference, DLL/LTSSM need stable clock |
| **Separate tx/rx domains** | Handle independent transceiver clocks, frequency offset tolerance |
| **AsyncFIFO for CDC** | Proven pattern from usb3_pipe, robust, simple |
| **No Phase 3-8 refactoring** | Drop-in replacement, maintain backward compatibility |
| **8b/10b placement** | In "tx"/"rx" domains close to transceiver, matches usb3_pipe |

---

## Clocking Requirements

### Xilinx 7-Series (GTX)

**Reference Clock:**
- Frequency: 100 MHz or 125 MHz
- Source: External oscillator or platform PLL
- Connects to: GTREFCLK0/GTREFCLK1

**Output Clocks:**
- TXOUTCLK: 125 MHz (Gen1) or 250 MHz (Gen2)
- RXOUTCLK: 125 MHz (Gen1) or 250 MHz (Gen2), tracks remote TX

**Clock Buffers Required:**
```python
# TX clock buffering
Instance("BUFG",
    i_I = txoutclk_unbuffered,
    o_O = txoutclk
)

# Platform constraint
platform.add_period_constraint(txoutclk, 1e9/125e6)  # 8ns
```

### Lattice ECP5 (SERDES)

**Reference Clock:**
- Frequency: 100 MHz or 200 MHz
- Source: External oscillator
- Connects to: REFCLK_P/REFCLK_N

**Output Clocks:**
- TX: Derived from DCU_CLK (125 MHz Gen1, 250 MHz Gen2)
- RX: Recovered clock from CDR

**CTC FIFO:**
- ECP5 uses CTC (Clock Tolerance Compensation) FIFO
- Similar function to AsyncFIFO but integrated in DCUA

---

## Timing Constraints

### Xilinx Example

```python
# In platform file or transceiver wrapper
platform.add_period_constraint(phy.cd_pcie.clk, 8.0)  # 125 MHz = 8ns
platform.add_period_constraint(phy.cd_tx.clk, 8.0)
platform.add_period_constraint(phy.cd_rx.clk, 8.0)

# Asynchronous clock groups (no timing relationship)
platform.add_false_path_constraints(
    platform.lookup_request("sys_clk"),
    phy.cd_pcie.clk
)
platform.add_false_path_constraints(
    phy.cd_pcie.clk,
    phy.cd_rx.clk  # RX may have slight frequency offset
)
```

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Clock domain refactoring needed | Use AsyncFIFO CDC, no Phase 3-8 code changes |
| TX/RX frequency mismatch | AsyncFIFO handles elasticity, sized appropriately (depth=8) |
| Clock jitter/instability | Proper buffering (BUFG), timing constraints |
| Multiple clock domain bugs | Careful ClockDomainsRenamer usage, simulation with cocotb |

---

## Testing Strategy

### Clock Domain Testing

1. **Unit Tests:**
   - Verify AsyncFIFO CDC works (write @ pcie, read @ tx/rx)
   - Test frequency mismatch tolerance
   - Confirm no data loss

2. **Integration Tests:**
   - Phase 8 external PHY still works (regression)
   - Phase 9 internal transceiver creates correct clocks
   - End-to-end data flow (sys → pcie → tx/rx)

3. **Timing Analysis:**
   - All timing constraints met
   - No hold violations at CDC boundaries
   - Clock skew within limits

---

## Next Steps

1. ✅ **Complete this document** (DONE)
2. ⏳ **Implement base transceiver abstraction** (Task 9.2)
   - Define common interface with clock domain methods
3. ⏳ **Prototype GTX wrapper with clocking** (Task 9.3)
   - Verify clock domain creation works
   - Test AsyncFIFO CDC
4. ⏳ **Validate with existing Phase 3-8 tests**
   - Ensure no regression
5. ⏳ **Document platform requirements**
   - Reference clock source
   - Timing constraints

---

## Conclusion

**Phase 9 clock architecture is well-defined and low-risk:**

✅ No Phase 3-8 refactoring required
✅ Proven AsyncFIFO CDC pattern from usb3_pipe
✅ Clean separation of concerns (sys, pcie, tx, rx)
✅ Drop-in replacement for external PHY
✅ Foundation for future Gen3/Gen4 support

**Key Insight:** By deriving "pcie" domain from TXOUTCLK and using AsyncFIFO CDC for tx/rx domains, we maintain compatibility with existing code while enabling internal transceiver support.

---

**Document Status:** APPROVED - Ready for Phase 9 Implementation
**Next Document:** Must Fix 2 - liteiclink Dependency Documentation
