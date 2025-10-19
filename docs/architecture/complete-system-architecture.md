# LitePCIe Complete System Architecture

**Version:** 1.0
**Date:** 2025-10-18
**Status:** Comprehensive Reference

## Overview

This document provides complete standalone architecture documentation for the LitePCIe PCIe implementation, covering all layers from physical transceivers (SERDES) through the transaction layer (TLP).

## What Makes This Implementation Unique

- **Vendor-IP-Free**: No Xilinx/Lattice hard IP required
- **Open-Source Friendly**: Works with nextpnr (ECP5) and OpenXC7 (7-Series)
- **Educational**: Full visibility into all protocol layers
- **Portable**: Consistent architecture across FPGA vendors

## Architecture Layers

LitePCIe implements the complete PCIe protocol stack:

1. **SERDES Layer** - Physical transceivers (GTX/GTY/ECP5)
2. **PIPE Layer** - PHY Interface for PCI Express
3. **DLL Layer** - Data Link Layer (LCRC, ACK/NAK, Retry)
4. **TLP Layer** - Transaction Layer Packets

## Reading This Documentation

- **New to PCIe?** Start with [Layer Overview](#layer-overview) and read top-down
- **Implementing a feature?** Jump to the relevant layer's detailed document
- **Debugging?** Use the [Data Flow Examples](#data-flow-examples) section
- **Integrating?** See [Integration Patterns](integration-patterns.md)

## Complete System Stack

### Full Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                      APPLICATION LAYER                          │
│                                                                 │
│  User Logic: DMA Engines, Memory Controllers, Custom Logic      │
│  Interface: TLP-level read/write requests                       │
└────────────────────────────┬────────────────────────────────────┘
                             │ 64-512 bit TLP interface
┌────────────────────────────▼────────────────────────────────────┐
│                    TRANSACTION LAYER (TLP)                      │
│                    Location: litepcie/tlp/                      │
│                                                                 │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐   │
│  │  TLP Packetizer  │  │ TLP Depacketizer │  │ Flow Control │   │
│  │                  │  │                  │  │              │   │
│  │ • Header gen     │  │ • Header parse   │  │ • Credits    │   │
│  │ • CRC calc       │  │ • CRC check      │  │ • Throttling │   │
│  │ • Routing        │  │ • Type decode    │  │              │   │
│  └──────────────────┘  └──────────────────┘  └──────────────┘   │
│                                                                 │
│  TLP Types: Memory Read/Write, Config, Completion, Messages     │
└────────────────────────────┬────────────────────────────────────┘
                             │ 64-bit packets (phy_layout)
┌────────────────────────────▼────────────────────────────────────┐
│                    DATA LINK LAYER (DLL)                        │
│                    Location: litepcie/dll/                      │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │   DLL TX     │  │   DLL RX     │  │   Retry Buffer         │ │
│  │              │  │              │  │                        │ │
│  │ • LCRC gen   │  │ • LCRC check │  │ • Store TLPs           │ │
│  │ • Seq num    │  │ • ACK/NAK    │  │ • Replay on NAK        │ │
│  │ • DLLP gen   │  │ • DLLP parse │  │ • 4KB circular buffer  │ │
│  └──────────────┘  └──────────────┘  └────────────────────────┘ │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              LTSSM (Link Training State Machine)         │   │
│  │                                                          │   │
│  │  States: DETECT → POLLING → CONFIG → L0 → RECOVERY       │   │
│  │  Controls: Speed negotiation, TS1/TS2 exchange           │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  DLLP Types: ACK, NAK, UpdateFC, PM_Enter_L1, etc.              │
└────────────────────────────┬────────────────────────────────────┘
                             │ 64-bit packets + ordered sets
┌────────────────────────────▼────────────────────────────────────┐
│                      PIPE INTERFACE LAYER                       │
│                      Location: litepcie/dll/pipe.py             │
│                                                                 │
│  ┌──────────────────┐         ┌──────────────────┐              │
│  │  TX Packetizer   │         │  RX Depacketizer │              │
│  │                  │         │                  │              │
│  │ • 64→8 bit conv  │         │ • 8→64 bit conv  │              │
│  │ • STP/SDP/END    │         │ • START detect   │              │
│  │ • K-char framing │         │ • Symbol accum   │              │
│  └──────────────────┘         └──────────────────┘              │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │           Ordered Set Generation/Detection               │   │
│  │                                                          │   │
│  │  • SKP insertion (every 1180 symbols)                    │   │
│  │  • TS1/TS2 generation (link training)                    │   │
│  │  • COM symbol handling (alignment)                       │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  Interface: 8-bit data + K-char flag + control signals          │
└────────────────────────────┬────────────────────────────────────┘
                             │ PIPE signals (8-bit + ctrl)
┌────────────────────────────▼────────────────────────────────────┐
│                    TRANSCEIVER BASE LAYER                       │
│                    Location: litepcie/phy/transceiver_base/     │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              PIPETransceiver Base Class                  │   │
│  │                                                          │   │
│  │  Common interface for all transceivers                   │   │
│  │  • TX/RX datapaths (CDC: sys_clk ↔ tx/rx_clk)            │   │
│  │  • Reset sequencing (PLL → PCS → CDR)                    │   │
│  │  • Speed control (Gen1/Gen2 switching)                   │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐   │
│  │ TX Datapath      │  │ RX Datapath      │  │ 8b/10b       │   │
│  │                  │  │                  │  │              │   │
│  │ • AsyncFIFO CDC  │  │ • AsyncFIFO CDC  │  │ • Encoder    │   │
│  │ • sys→tx domain  │  │ • rx→sys domain  │  │ • Decoder    │   │
│  └──────────────────┘  └──────────────────┘  └──────────────┘   │
└────────────────────────────┬────────────────────────────────────┘
                             │ 10-bit encoded symbols
┌────────────────────────────▼────────────────────────────────────┐
│                    SERDES/TRANSCEIVER LAYER                     │
│            Location: litepcie/phy/xilinx/, litepcie/phy/lattice/│
│                                                                 │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐   │
│  │  Xilinx GTX      │  │ Xilinx GTY       │  │ ECP5 SERDES  │   │
│  │  (7-Series)      │  │ (UltraScale+)    │  │ (Lattice)    │   │
│  │                  │  │                  │  │              │   │
│  │ • GTXE2 wrapper  │  │ • GTYE4 wrapper  │  │ • DCUA wrap  │   │
│  │ • CPLL/QPLL      │  │ • QPLL0/QPLL1    │  │ • SCI config │   │
│  │ • Gen1/Gen2      │  │ • Gen1/Gen2/Gen3 │  │ • Gen1/Gen2  │   │
│  └──────────────────┘  └──────────────────┘  └──────────────┘   │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Physical Layer Functions                    │   │
│  │                                                          │   │
│  │  • Serialization/Deserialization (10 Gbps line rate)     │   │
│  │  • Clock recovery (RX CDR)                               │   │
│  │  • Equalization (DFE, CTLE)                              │   │
│  │  • Electrical idle detection                             │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────────┘
                             │ Differential serial (TX+/-, RX+/-)
                             ▼
                    Physical PCIe Link
                    (PCB traces, connector)
```

## Layer Overview

### Layer 1: SERDES/Transceiver Layer

**Purpose:** Physical serialization/deserialization and analog signaling

**Location:** `litepcie/phy/xilinx/`, `litepcie/phy/lattice/`

**Key Components:**
- GTX wrapper (Xilinx 7-Series)
- GTY wrapper (Xilinx UltraScale+)
- ECP5 SERDES wrapper (Lattice)

**Detailed Documentation:** [SERDES Layer Architecture](serdes-layer.md)

### Layer 2: Transceiver Base Layer

**Purpose:** Common abstraction for all FPGA transceivers

**Location:** `litepcie/phy/transceiver_base/`

**Key Components:**
- PIPETransceiver base class
- TX/RX datapaths (CDC)
- Reset sequencers
- 8b/10b encoder/decoder

**Detailed Documentation:** [SERDES Layer Architecture](serdes-layer.md#transceiver-base)

### Layer 3: PIPE Interface Layer

**Purpose:** PHY Interface for PCI Express - MAC/PHY boundary

**Location:** `litepcie/dll/pipe.py`

**Key Components:**
- TX Packetizer (64-bit → 8-bit symbols)
- RX Depacketizer (8-bit symbols → 64-bit)
- Ordered set generation (SKP, TS1, TS2)
- K-character framing (STP/SDP/END)

**Detailed Documentation:** [PIPE Layer Architecture](pipe-layer.md)

### Layer 4: Data Link Layer (DLL)

**Purpose:** Reliable packet delivery with error detection and retry

**Location:** `litepcie/dll/`

**Key Components:**
- LCRC generation/checking
- Sequence number management
- ACK/NAK protocol
- Retry buffer (4KB)
- DLLP processing
- LTSSM (Link Training State Machine)

**Detailed Documentation:** [DLL Layer Architecture](dll-layer.md)

### Layer 5: Transaction Layer (TLP)

**Purpose:** High-level read/write transactions and message passing

**Location:** `litepcie/tlp/`

**Key Components:**
- TLP Packetizer
- TLP Depacketizer
- Flow control credit management
- Completion tracking

**Detailed Documentation:** [TLP Layer Architecture](tlp-layer.md)

## Data Flow Examples

### Example 1: Memory Write Request (TLP → Physical Link)

This example shows how a single memory write request flows through all layers from the application down to the physical link.

```
Application Layer
    │
    │ Memory Write Request:
    │ - Address: 0x1000_0000
    │ - Data: 0xDEADBEEF (4 bytes)
    │
    ▼
┌───────────────────────────────────────────────────────┐
│ Transaction Layer (TLP)                               │
│                                                       │
│ 1. Build TLP Header:                                  │
│    - Type: MWr32 (Memory Write 32-bit addressing)     │
│    - Length: 1 DW                                     │
│    - Requester ID: 00:00.0                            │
│    - Tag: 0x42                                        │
│    - Address: 0x1000_0000                             │
│                                                       │
│ 2. Attach payload: 0xDEADBEEF                         │
│                                                       │
│ 3. Calculate ECRC (if enabled)                        │
│                                                       │
│ Output: 64-bit wide packet (phy_layout)               │
│    Header: [3 DW] + Data: [1 DW]                      │
└───────────┬───────────────────────────────────────────┘
            │ 64-bit TLP packet
            ▼
┌───────────────────────────────────────────────────────┐
│ Data Link Layer (DLL)                                 │
│                                                       │
│ 1. Assign sequence number: 0x123                      │
│                                                       │
│ 2. Calculate LCRC:                                    │
│    - Input: TLP header + payload                      │
│    - Output: 32-bit LCRC                              │
│                                                       │
│ 3. Store in retry buffer (until ACK)                  │
│                                                       │
│ 4. Package for transmission:                          │
│    STP | TLP Header | TLP Data | LCRC | END           │
│                                                       │
│ Output: 64-bit DLL packet with framing                │
└───────────┬───────────────────────────────────────────┘
            │ 64-bit DLL packet
            ▼
┌───────────────────────────────────────────────────────┐
│ PIPE Interface Layer                                  │
│                                                       │
│ TX Packetizer FSM:                                    │
│                                                       │
│ 1. Receive 64-bit word                                │
│                                                       │
│ 2. Break into 8-bit symbols (8 symbols per word)      │
│                                                       │
│ 3. Add K-character framing:                           │
│    - STP → K27.7 (0xFB)                               │
│    - SDP → K28.2 (0x5C)                               │
│    - END → K29.7 (0xFD)                               │
│                                                       │
│ 4. Insert SKP ordered sets (every 1180 symbols)       │
│                                                       │
│ Output: 8-bit symbols + K-char flag                   │
│    K27.7 | D0 | D1 | ... | K29.7                      │
└───────────┬───────────────────────────────────────────┘
            │ 8-bit PIPE symbols
            ▼
┌───────────────────────────────────────────────────────┐
│ Transceiver Base Layer                                │
│                                                       │
│ 1. CDC: sys_clk → tx_clk (AsyncFIFO)                  │
│                                                       │
│ 2. 8b/10b Encoding:                                   │
│    - Data symbols → 10-bit codes                      │
│    - K27.7 → 0x17C (comma character)                  │
│    - Disparity tracking                               │
│                                                       │
│ Output: 20-bit encoded (2 symbols @ 10-bit each)      │
└───────────┬───────────────────────────────────────────┘
            │ 20-bit encoded symbols
            ▼
┌───────────────────────────────────────────────────────┐
│ SERDES Layer (GTX/GTY/ECP5)                           │
│                                                       │
│ 1. Parallel to Serial conversion:                     │
│    20-bit @ 250 MHz → 1-bit @ 5.0 GHz (Gen2)          │
│                                                       │
│ 2. Differential drive:                                │
│    - TX+ and TX- outputs                              │
│    - Voltage swing: 0.8-1.2V                          │
│                                                       │
│ 3. Pre-emphasis/de-emphasis for signal integrity      │
│                                                       │
│ Output: Serial differential signal                    │
└───────────┬───────────────────────────────────────────┘
            │ Differential serial (TX+/-)
            ▼
      Physical PCIe Link
```

### Example 2: Memory Read Completion (Physical Link → TLP)

This example shows the reverse path - receiving a completion from the PCIe link.

```
Physical PCIe Link (RX+/-)
    │ Serial differential signal
    ▼
┌───────────────────────────────────────────────────────┐
│ SERDES Layer (GTX/GTY/ECP5)                           │
│                                                       │
│ 1. Clock and Data Recovery (CDR):                     │
│    - Extract clock from data                          │
│    - Align to bit boundaries                          │
│                                                       │
│ 2. Serial to Parallel conversion:                     │
│    1-bit @ 5.0 GHz → 20-bit @ 250 MHz (Gen2)          │
│                                                       │
│ 3. Equalization (DFE, CTLE) for signal integrity      │
│                                                       │
│ Output: 20-bit parallel symbols                       │
└───────────┬───────────────────────────────────────────┘
            │ 20-bit encoded symbols
            ▼
┌───────────────────────────────────────────────────────┐
│ Transceiver Base Layer                                │
│                                                       │
│ 1. 8b/10b Decoding:                                   │
│    - 10-bit codes → 8-bit symbols                     │
│    - Detect K-characters (comma, framing)             │
│    - Check disparity errors                           │
│    - Report decode errors                             │
│                                                       │
│ 2. CDC: rx_clk → sys_clk (AsyncFIFO)                  │
│                                                       │
│ Output: 8-bit symbols + K-char flag                   │
└───────────┬───────────────────────────────────────────┘
            │ 8-bit PIPE symbols
            ▼
┌───────────────────────────────────────────────────────┐
│ PIPE Interface Layer                                  │
│                                                       │
│ RX Depacketizer FSM:                                  │
│                                                       │
│ 1. Detect framing K-characters:                       │
│    - K27.7 (0xFB) → Start of TLP (STP)                │
│    - K28.2 (0x5C) → Start of Data Packet (SDP)        │
│    - K29.7 (0xFD) → End of packet (END)               │
│                                                       │
│ 2. Filter ordered sets:                               │
│    - Remove SKP ordered sets                          │
│    - Pass through TS1/TS2 to LTSSM                    │
│                                                       │
│ 3. Accumulate 8 symbols → 64-bit word                 │
│                                                       │
│ 4. Detect packet boundaries (STP to END)              │
│                                                       │
│ Output: 64-bit DLL packets                            │
└───────────┬───────────────────────────────────────────┘
            │ 64-bit DLL packet
            ▼
┌───────────────────────────────────────────────────────┐
│ Data Link Layer (DLL)                                 │
│                                                       │
│ DLL RX Processing:                                    │
│                                                       │
│ 1. Extract LCRC from packet end                       │
│                                                       │
│ 2. Verify LCRC:                                       │
│    - Calculate CRC over header + payload              │
│    - Compare with received LCRC                       │
│                                                       │
│ 3. If LCRC valid:                                     │
│    - Send ACK DLLP to remote                          │
│    - Extract sequence number                          │
│    - Pass TLP to upper layer                          │
│                                                       │
│ 4. If LCRC invalid:                                   │
│    - Send NAK DLLP to remote                          │
│    - Discard packet                                   │
│    - Request retransmission                           │
│                                                       │
│ Output: 64-bit TLP packet (without LCRC)              │
└───────────┬───────────────────────────────────────────┘
            │ 64-bit TLP packet
            ▼
┌───────────────────────────────────────────────────────┐
│ Transaction Layer (TLP)                               │
│                                                       │
│ 1. Parse TLP header:                                  │
│    - Type: CplD (Completion with Data)                │
│    - Completer ID: 01:00.0                            │
│    - Tag: 0x42 (matches outstanding read)             │
│    - Byte Count: 64 bytes                             │
│    - Lower Address: 0x00                              │
│                                                       │
│ 2. Verify ECRC (if present)                           │
│                                                       │
│ 3. Match to outstanding request (by Tag)              │
│                                                       │
│ 4. Extract completion data                            │
│                                                       │
│ 5. Update flow control credits                        │
│                                                       │
│ Output: Completion data to application                │
└───────────┬───────────────────────────────────────────┘
            │ Completion data
            ▼
      Application Layer
      (Read data: 64 bytes)
```

## Cross-Layer Interactions

### Clock Domain Architecture

The system operates across multiple clock domains with careful CDC (Clock Domain Crossing) handling:

```
┌──────────────────────────────────────────────────────┐
│ Clock Domains in LitePCIe                            │
│                                                      │
│  ┌──────────────┐                                    │
│  │   sys_clk    │  User logic clock (e.g., 125 MHz)  │
│  └──────┬───────┘                                    │
│         │                                            │
│         │ Used by: TLP, DLL, PIPE (parallel path)    │
│         │                                            │
│  ┌──────▼───────┐                                    │
│  │  AsyncFIFO   │  CDC boundary                      │
│  └──────┬───────┘                                    │
│         │                                            │
│  ┌──────▼───────┐                                    │
│  │   tx_clk     │  TX transceiver clock (250 MHz)    │
│  └──────────────┘  (Gen2 - 5.0 Gbps line rate)       │
│                                                      │
│  ┌──────────────┐                                    │
│  │   rx_clk     │  RX recovered clock (250 MHz)      │
│  └──────┬───────┘  (Recovered by CDR from RX data)   │
│         │                                            │
│  ┌──────▼───────┐                                    │
│  │  AsyncFIFO   │  CDC boundary                      │
│  └──────┬───────┘                                    │
│         │                                            │
│         ▼                                            │
│    sys_clk domain                                    │
└──────────────────────────────────────────────────────┘
```

**Key CDC Points:**
1. **TX Path:** sys_clk → tx_clk (in TransceiverTXDatapath)
2. **RX Path:** rx_clk → sys_clk (in TransceiverRXDatapath)
3. **Control Signals:** Proper synchronization using GrayCode for counters, multi-FF sync for single-bit signals

### Reset Sequencing

Proper reset sequencing is critical for reliable transceiver operation:

```
Power-On / Reset Assertion
    │
    ▼
┌───────────────────────────────────┐
│ 1. INIT State                     │
│    - Hold all resets active       │
│    - Wait for clock stability     │
│    Duration: ~100 ms              │
└───────┬───────────────────────────┘
        │
        ▼
┌───────────────────────────────────┐
│ 2. PLL_LOCK                       │
│    - Release PLL reset            │
│    - Wait for CPLL/QPLL lock      │
│    - Timeout: 1 ms                │
└───────┬───────────────────────────┘
        │
        ▼
┌───────────────────────────────────┐
│ 3. TX_READY                       │
│    - Release TX reset             │
│    - Wait for TX PCS ready        │
│    - Enable TX datapath           │
└───────┬───────────────────────────┘
        │
        ▼
┌───────────────────────────────────┐
│ 4. RX_SIGNAL                      │
│    - Wait for RX signal detect    │
│    - Verify electrical idle de-   │
│      assertion                    │
└───────┬───────────────────────────┘
        │
        ▼
┌───────────────────────────────────┐
│ 5. CDR_LOCK                       │
│    - Release RX reset             │
│    - Wait for CDR lock            │
│    - Verify comma detection       │
│    - Timeout: 10 ms               │
└───────┬───────────────────────────┘
        │
        ▼
┌───────────────────────────────────┐
│ 6. RX_READY                       │
│    - Enable RX datapath           │
│    - Signal ready to PIPE layer   │
└───────┬───────────────────────────┘
        │
        ▼
┌───────────────────────────────────┐
│ 7. OPERATIONAL                    │
│    - All datapaths active         │
│    - LTSSM can proceed            │
│    - Link training begins         │
└───────────────────────────────────┘
```

## Integration Points

### Between Layers

Each layer presents a well-defined interface to adjacent layers:

**TLP ↔ DLL Interface:**
- Protocol: Migen/LiteX stream interface (Source/Sink)
- Data width: 64 bits (configurable up to 512 bits)
- Layout: `phy_layout` (defined in `litepcie/common.py`)
- Flow control: `valid`/`ready` handshaking

**DLL ↔ PIPE Interface:**
- Protocol: Custom packet interface
- Data width: 64 bits (DLL side), 8 bits (PIPE side)
- Framing: K-character based (STP/SDP/END)
- Special handling: Ordered sets, DLLP insertion

**PIPE ↔ Transceiver Base Interface:**
- Protocol: PIPE 3.0 subset
- Data width: 8 bits (16 bits for Gen3+)
- Control signals: `tx_datak`, `rx_datak`, `tx_elecidle`, `rx_elecidle`
- Status signals: `tx_ready`, `rx_ready`

**Transceiver Base ↔ SERDES Interface:**
- Protocol: Vendor-specific primitive ports
- Data width: 20 bits (10-bit per symbol, 2 symbols)
- Encoding: 8b/10b pre-encoded (software)
- Clocking: Independent TX/RX clocks

### Existing Documentation Cross-References

This architecture integrates with existing LitePCIe documentation:

- **[PIPE Architecture](pipe-architecture.md)** - Detailed PIPE component diagrams and implementation
- **[Clock Domain Architecture](clock-domain-architecture.md)** - Comprehensive clock domain strategy
- **[Integration Strategy](integration-strategy.md)** - Overall integration roadmap and planning

For implementation examples and integration guides, see:
- **Integration Examples:** Check existing integration examples in the codebase
- **PHY Integration:** See vendor-specific PHY integration patterns

## Technical Specifications

### Supported PCIe Generations

| Generation | Line Rate | Symbol Rate | Data Rate | Status |
|------------|-----------|-------------|-----------|--------|
| Gen1       | 2.5 GT/s  | 250 MHz     | 2.0 Gbps  | Supported |
| Gen2       | 5.0 GT/s  | 250 MHz     | 4.0 Gbps  | Supported |
| Gen3       | 8.0 GT/s  | 500 MHz     | 7.877 Gbps | Partial (GTY only) |

Note: Gen3 requires 128b/130b encoding instead of 8b/10b (different from Gen1/Gen2 architecture).

### Data Path Widths

| Layer | TX Width | RX Width | Clock Domain |
|-------|----------|----------|--------------|
| TLP   | 64-512b  | 64-512b  | sys_clk |
| DLL   | 64b      | 64b      | sys_clk |
| PIPE  | 8b       | 8b       | sys_clk |
| Transceiver | 20b (2x10b) | 20b (2x10b) | tx_clk / rx_clk |
| SERDES | 1b serial | 1b serial | Line rate |

### Buffer Sizes

- **DLL Retry Buffer:** 4 KB (configurable)
- **TX AsyncFIFO:** 16 entries × 20 bits
- **RX AsyncFIFO:** 16 entries × 20 bits
- **Flow Control Credits:** Configurable per type (Posted, Non-Posted, Completion)

## Debug and Monitoring

### Observable Signals

For debugging, the following signals are exposed at each layer:

**TLP Layer:**
- `tlp_tx_valid`, `tlp_tx_ready` - TX flow control
- `tlp_rx_valid`, `tlp_rx_ready` - RX flow control
- Flow control credit counters

**DLL Layer:**
- `dll_tx_seq` - Current TX sequence number
- `dll_rx_ack_seq` - Last acknowledged sequence
- `dll_ltssm_state` - Current LTSSM state
- `dll_retry_count` - Number of retries

**PIPE Layer:**
- `pipe_tx_data`, `pipe_tx_datak` - TX symbol stream
- `pipe_rx_data`, `pipe_rx_datak` - RX symbol stream
- Ordered set detection flags

**Transceiver Layer:**
- `tx_ready`, `rx_ready` - Transceiver ready status
- `pll_lock` - PLL lock status
- `cdr_lock` - CDR lock status
- `rx_signal_detect` - Signal presence

### Common Debug Scenarios

**Link Won't Train:**
1. Check `pll_lock` - PLL must lock first
2. Check `rx_signal_detect` - Verify RX signal present
3. Check `cdr_lock` - CDR must lock to data
4. Monitor `dll_ltssm_state` - Should progress: DETECT → POLLING → CONFIG → L0

**CRC Errors:**
1. Monitor `dll_rx_ack_seq` - Should increment on successful packets
2. Check `dll_retry_count` - High retry count indicates CRC failures
3. Examine `pipe_rx_datak` - Look for symbol errors

**Flow Control Issues:**
1. Monitor TLP credit counters
2. Check for credit exhaustion (transmitter blocked)
3. Verify UpdateFC DLLP reception

## Performance Characteristics

### Latency Budget

Typical latency through the stack (one direction):

| Layer | Typical Latency | Notes |
|-------|----------------|-------|
| TLP Packetizer | 2-4 cycles | Header generation |
| DLL TX | 8-16 cycles | LCRC calculation, buffering |
| PIPE TX | 8 cycles | Symbol-by-symbol transmission |
| TX CDC | 4-8 cycles | AsyncFIFO crossing |
| 8b/10b Encode | 1 cycle | Pipeline stage |
| SERDES TX | 2-4 cycles | Serializer latency |
| **Total TX** | **~30-50 cycles** | @ sys_clk (e.g., 125 MHz = 240-400 ns) |

RX path has similar latency plus CDR lock time on initial startup.

### Throughput

Maximum throughput depends on:
1. **PCIe Generation:** Gen1 (2 Gbps) vs Gen2 (4 Gbps) vs Gen3 (7.877 Gbps)
2. **Link Width:** x1, x2, x4, x8, x16
3. **Data Path Width:** 64-bit (1 cycle/TLP) vs 128-bit (0.5 cycle/TLP) vs 512-bit
4. **Overhead:** 8b/10b encoding (20% overhead), protocol headers, flow control

**Example (Gen2 x1 with 64-bit datapath):**
- Line rate: 5.0 GT/s
- After 8b/10b: 4.0 Gbps
- After protocol overhead (~10%): ~3.6 Gbps
- Effective: ~450 MBps (megabytes per second)

## Conclusion

The LitePCIe architecture provides a complete, vendor-IP-free PCIe implementation from physical transceivers through transaction layer packets. The multi-layer design offers:

- **Portability:** Common architecture across Xilinx and Lattice FPGAs
- **Visibility:** Full access to all protocol layers for debugging and customization
- **Education:** Clear separation of concerns makes learning PCIe protocol easier
- **Flexibility:** Can integrate with vendor hard IP or use fully-soft implementation

For detailed information on each layer, refer to the layer-specific documentation linked in the [Layer Overview](#layer-overview) section.

## Related Documentation

- [SERDES Layer Architecture](serdes-layer.md) - Physical transceiver layer details
- [PIPE Layer Architecture](pipe-layer.md) - PHY interface protocol details
- [DLL Layer Architecture](dll-layer.md) - Data link layer with LTSSM
- [TLP Layer Architecture](tlp-layer.md) - Transaction layer protocol
- [Integration Patterns](integration-patterns.md) - Cross-layer integration guide
- [PIPE Architecture](pipe-architecture.md) - PIPE component implementation
- [Clock Domain Architecture](clock-domain-architecture.md) - Multi-domain clocking
- [Integration Strategy](integration-strategy.md) - Integration roadmap

---

**Document Version:** 1.0
**Last Updated:** 2025-10-18
**Maintained By:** LitePCIe Documentation Team
