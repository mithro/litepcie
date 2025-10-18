# LitePCIe Architecture Quick Reference

**Purpose:** One-page overview of the complete architecture for quick lookup

**Use this for:**
- Quick architecture refresher
- Onboarding new developers
- Presentation material
- Debugging reference

**For detailed docs, see:**
- [Complete System Architecture](complete-system-architecture.md)
- Layer docs: [SERDES](serdes-layer.md) | [PIPE](pipe-layer.md) | [DLL](dll-layer.md) | [TLP](tlp-layer.md)

---

## Condensed Stack Diagram

```
┌────────────────────────────────────────────────────────────┐
│  APPLICATION: User Logic / DMA Engines                     │
├────────────────────────────────────────────────────────────┤
│  TLP LAYER (litepcie/tlp/)                                 │
│    • Packetizer/Depacketizer (3DW/4DW headers)            │
│    • Flow control (credit management)                      │
│    • Types: MRd/MWr, Config, Completion                    │
├────────────────────────────────────────────────────────────┤
│  DLL LAYER (litepcie/dll/)                                 │
│    • LCRC-32 generation/checking                           │
│    • ACK/NAK protocol with retry buffer (4KB)              │
│    • LTSSM: DETECT → POLLING → CONFIG → L0                │
│    • Sequence numbering (12-bit)                           │
├────────────────────────────────────────────────────────────┤
│  PIPE LAYER (litepcie/dll/pipe.py)                         │
│    • TX Packetizer: 64-bit → 8-bit + framing              │
│    • RX Depacketizer: 8-bit → 64-bit                      │
│    • K-char framing: STP/SDP/END                           │
│    • Ordered sets: SKP (every 1180), TS1/TS2               │
├────────────────────────────────────────────────────────────┤
│  TRANSCEIVER BASE (litepcie/phy/transceiver_base/)         │
│    • TX/RX datapaths (AsyncFIFO CDC)                       │
│    • Software 8b/10b encoder/decoder                       │
│    • Reset sequencing (PLL → TX → RX)                     │
├────────────────────────────────────────────────────────────┤
│  SERDES (litepcie/phy/xilinx/, litepcie/phy/lattice/)      │
│    • GTX (7-Series), GTY (UltraScale+), ECP5              │
│    • Serialization: 20-bit → 1-bit serial                 │
│    • CDR, DFE, CTLE equalization                           │
└────────────────────────────────────────────────────────────┘
     ↕ Differential Serial (TX+/-, RX+/-)
```

---

## Layer Interfaces Summary

| Layer | Input Interface | Output Interface | Width | Clock Domain |
|-------|----------------|------------------|-------|--------------|
| **TLP** | User requests | `phy.sink` | 64-512b | sys_clk |
| **DLL** | `phy.sink` | DLL packets | 64b | sys_clk |
| **PIPE** | DLL packets (64b) | PIPE symbols (8b) | 64b→8b | sys_clk |
| **Transceiver** | PIPE symbols | 8b/10b encoded | 8b→10b | sys/tx/rx_clk |
| **SERDES** | 10b parallel | Serial differential | 10b→1b | 2.5-5 GHz |

### Signal Details

**TLP ↔ DLL:**
- Protocol: Stream interface (valid/ready)
- Layout: `phy_layout` (64-512 bits configurable)
- Signals: `valid`, `first`, `last`, `dat[width-1:0]`

**DLL ↔ PIPE:**
- Protocol: Stream interface
- Framing: K-character based (STP/SDP/END)
- Special: DLLP insertion, ordered sets

**PIPE ↔ Transceiver:**
- TX: `tx_data[7:0]`, `tx_datak`, `tx_elecidle`
- RX: `rx_data[7:0]`, `rx_datak`, `rx_valid`, `rx_elecidle`
- Control: `reset`, `speed[1:0]`
- Status: `tx_ready`, `rx_ready`

**Transceiver ↔ SERDES:**
- Protocol: Vendor-specific (GTX/GTY/ECP5)
- Width: 20 bits (2 symbols × 10 bits)
- Encoding: 8b/10b pre-encoded by software

---

## Key Parameters Table

### Speed and Data Rates

| Parameter | Gen1 | Gen2 | Gen3 (Partial) |
|-----------|------|------|----------------|
| Line Rate | 2.5 GT/s | 5.0 GT/s | 8.0 GT/s |
| Encoding | 8b/10b | 8b/10b | 128b/130b |
| Symbol Rate | 250 MHz | 500 MHz | 500 MHz |
| Byte Throughput | 250 MB/s | 500 MB/s | 985 MB/s |
| Effective (after overhead) | 200 MB/s | 400 MB/s | ~790 MB/s |

### Buffer Sizes

| Component | Size | Purpose |
|-----------|------|---------|
| DLL Retry Buffer | 4 KB | Store unacknowledged TLPs |
| TX AsyncFIFO | 8 × 20b | CDC: sys_clk → tx_clk |
| RX AsyncFIFO | 8 × 20b | CDC: rx_clk → sys_clk |
| PIPE RX Buffer | 64 bits | Accumulate 8 bytes |

### Clock Domains

| Domain | Frequency | Source | Usage |
|--------|-----------|--------|-------|
| sys_clk | 125 MHz | Platform | TLP, DLL, PIPE logic |
| tx_clk | 125/250 MHz | TXOUTCLK | Gen1/Gen2 TX datapath |
| rx_clk | 125/250 MHz | RXOUTCLK (CDR) | RX recovered clock |

### K-Character Encoding

| Symbol | Value | K-Code | Purpose |
|--------|-------|--------|---------|
| COM | 0xBC | K28.5 | Lane alignment |
| SKP | 0x1C | K28.0 | Clock compensation |
| STP | 0xFB | K27.7 | Start TLP |
| SDP | 0x5C | K28.2 | Start DLLP |
| END | 0xFD | K29.7 | End packet |
| PAD | 0xF7 | K23.7 | Link idle fill |

### TLP Types (fmt:type)

| Type | fmt:type | Description |
|------|----------|-------------|
| MRd32 | 00:00000 | Memory Read 32-bit |
| MWr32 | 10:00000 | Memory Write 32-bit |
| MRd64 | 01:00000 | Memory Read 64-bit |
| MWr64 | 11:00000 | Memory Write 64-bit |
| CfgRd0 | 00:00100 | Config Read Type 0 |
| CfgWr0 | 10:00100 | Config Write Type 0 |
| Cpl | 00:01010 | Completion (no data) |
| CplD | 10:01010 | Completion with Data |

### LTSSM States

| State | Purpose | Exit Condition |
|-------|---------|----------------|
| DETECT | Receiver detection | RX presence detected |
| POLLING | Initial negotiation | 8 consecutive TS2 |
| CONFIG | Link configuration | Immediate |
| L0 | Normal operation | Error or idle request |
| RECOVERY | Error recovery | Return to L0 or reset |

---

## Debug Quick Reference

### Common Issues

**Link won't train:**
1. Check `pll_lock` (PLL must lock first)
2. Check `rx_signal_detect` (RX signal present)
3. Check `cdr_lock` (CDR locked to data)
4. Monitor `ltssm_state` (should reach L0)

**CRC Errors:**
1. Monitor `dll_rx_ack_seq` (should increment)
2. Check `dll_retry_count` (high = CRC failures)
3. Examine `pipe_rx_valid` (symbol errors)

**Flow Control Issues:**
1. Monitor TLP credit counters
2. Check for credit exhaustion
3. Verify UpdateFC DLLP reception

### Key Debug Signals

| Signal | Layer | Purpose |
|--------|-------|---------|
| `pll_lock` | SERDES | PLL locked status |
| `tx_ready` / `rx_ready` | Transceiver | Path ready status |
| `ltssm_state` | DLL | Current link state |
| `link_up` | DLL | Link operational (L0) |
| `dll_tx_seq` | DLL | TX sequence number |
| `dll_rx_ack_seq` | DLL | Last ACKed sequence |
| `dll_retry_count` | DLL | Retry buffer activity |
| `pipe_tx_data/datak` | PIPE | TX symbol stream |
| `pipe_rx_data/datak` | PIPE | RX symbol stream |
| `rx_valid` | Transceiver | RX data valid (no 8b/10b errors) |

---

## Latency Budget

| Layer | Typical Latency | Notes |
|-------|----------------|-------|
| TLP Packetizer | 2-4 cycles | Header generation |
| DLL TX | 8-16 cycles | LCRC calc, buffering |
| PIPE TX | 8 cycles | Symbol-by-symbol TX |
| TX CDC | 4-8 cycles | AsyncFIFO crossing |
| 8b/10b Encode | 1 cycle | Pipeline stage |
| SERDES TX | 2-4 cycles | Serializer latency |
| **Total TX Path** | **~30-50 cycles** | @ sys_clk (~240-400 ns @ 125 MHz) |
| **Total RX Path** | **~30-50 cycles** | Similar to TX |

---

## Resource Utilization (Per Lane)

| Component | LUTs | FFs | BRAM | Notes |
|-----------|------|-----|------|-------|
| 8b/10b Encoder | ~100 | ~50 | 0 | Software implementation |
| 8b/10b Decoder | ~150 | ~75 | 0 | Software implementation |
| TX/RX AsyncFIFO | ~100 | ~200 | 0 | CDC FIFOs |
| Reset Sequencer | ~100 | ~50 | 0 | FSM |
| **Total (excl. primitives)** | **~450** | **~375** | **0** | GTX/GTY/DCUA are hard IP |

---

## Platform Support

### Xilinx 7-Series (GTX)
- Devices: Artix-7, Kintex-7, Virtex-7
- PLL: CPLL (1.6-3.3 GHz VCO)
- Primitive: GTXE2_CHANNEL
- Reset: AR43482 sequence (50ms defer)
- Gen1/Gen2: Supported

### Xilinx UltraScale+ (GTY)
- Devices: Kintex/Virtex UltraScale+
- PLL: QPLL0/QPLL1 (8-16 GHz VCO)
- Primitive: GTYE4_CHANNEL
- Clock Buffer: BUFG_GT (low jitter)
- Gen1/Gen2/Gen3: Supported (Gen3 needs 128b/130b)

### Lattice ECP5 (SERDES)
- Devices: LFE5U-25F and higher
- Primitive: DCUA (Dual Channel Unit)
- Open-Source: Works with nextpnr
- SCI Interface: Runtime configuration
- Gen1: Well-tested, Gen2: Experimental

---

## Critical Design Decisions

### Software 8b/10b Encoding
- **Why:** Consistency across all platforms, open-source toolchain support
- **Cost:** ~250 LUTs per lane
- **Benefit:** Full visibility, no vendor dependencies
- **Proven:** Used in LiteICLink, USB3 PIPE implementations

### AsyncFIFO for CDC
- **Depth:** 8 entries (sufficient for CDC only)
- **Safety:** Gray code pointers, no metastability
- **Width:** Matches data path (16-bit typical)

### 4KB Retry Buffer
- **Size:** Supports typical TLP sizes
- **Implementation:** Circular buffer
- **Replay:** Automatic on NAK

### SKP Interval
- **Default:** 1180 symbols
- **Range:** 1180-1538 (configurable)
- **Overhead:** < 1% (4 symbols per 1180)

---

## Quick Links

**Core Implementation Files:**
- TLP: `litepcie/tlp/packetizer.py`, `depacketizer.py`
- DLL: `litepcie/dll/tx.py`, `rx.py`, `ltssm.py`
- PIPE: `litepcie/dll/pipe.py`
- Transceiver: `litepcie/phy/transceiver_base/`
- GTX: `litepcie/phy/xilinx/s7_gtx.py`
- GTY: `litepcie/phy/xilinx/usp_gty.py`
- ECP5: `litepcie/phy/lattice/ecp5_serdes.py`

**Test Coverage:**
- 53 transceiver tests (100% pass)
- PIPE interface validation
- LTSSM state machine tests
- End-to-end packet flow tests

**Specifications:**
- PCIe Base Specification Rev. 3.0/4.0
- PIPE 3.0 Specification (Intel)
- Xilinx UG476 (GTX), UG578 (GTY)
- Lattice TN1261 (ECP5 SERDES)

---

**Document Version:** 1.0
**Last Updated:** 2025-10-18
**Status:** Quick Reference - For Complete Details See Layer Documentation
