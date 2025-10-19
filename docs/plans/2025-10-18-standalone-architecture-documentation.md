# Standalone Architecture Documentation Implementation Plan

> **For Claude:** Use `${SUPERPOWERS_SKILLS_ROOT}/skills/collaboration/executing-plans/SKILL.md` to implement this plan task-by-task.

**Goal:** Create comprehensive, standalone architecture documentation with full flow diagrams covering the complete SERDES/PIPE/DLL/TLP structure.

**Architecture:** Multi-layer documentation approach with ASCII diagrams, detailed component descriptions, data flow examples, and integration patterns.

**Tech Stack:** Markdown, ASCII art diagrams, Mermaid diagrams (optional), cross-referenced documentation structure.

---

## Documentation Structure Overview

The plan creates a complete standalone architecture guide that can be read independently without requiring deep knowledge of the existing codebase. The documentation will be organized as:

```
docs/architecture/
├── complete-system-architecture.md    (NEW - Main standalone doc)
├── serdes-layer.md                    (NEW - Physical layer details)
├── pipe-layer.md                      (NEW - PIPE interface details)
├── dll-layer.md                       (NEW - Data Link Layer details)
├── tlp-layer.md                       (NEW - Transaction Layer details)
└── integration-patterns.md            (NEW - Cross-layer integration)
```

**Existing docs to update:**
- `docs/README.md` - Add links to new architecture docs
- `docs/architecture/pipe-architecture.md` - Already exists, will cross-reference
- `docs/architecture/integration-strategy.md` - Already exists, will cross-reference

---

## Task 1: Create Main System Architecture Document

**Goal:** Create the master architecture document with complete system overview

**Files:**
- Create: `docs/architecture/complete-system-architecture.md`

**Step 1: Create document header and introduction**

Write introduction explaining the complete PCIe stack architecture:

```markdown
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
```

**Step 2: Create complete system stack diagram**

Add comprehensive ASCII diagram showing all layers:

```markdown
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
│  │  • TX/RX datapaths (CDC: sys_clk ↔ tx/rx_clk)          │     │
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
```

**Step 3: Add layer overview with cross-references**

```markdown
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
```

**Step 4: Verify document structure**

Run: `ls -la docs/architecture/complete-system-architecture.md`
Expected: File exists with header, stack diagram, and layer overview

**Step 5: Commit**

```bash
git add docs/architecture/complete-system-architecture.md
git commit -m "docs: Add main system architecture document with complete stack diagram

- Add comprehensive system stack diagram showing all 5 layers
- Add layer overview with cross-references
- Provide reading guide for different audiences
- Foundation for detailed layer documentation

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 2: Create SERDES Layer Documentation

**Goal:** Document the physical transceiver layer with detailed diagrams

**Files:**
- Create: `docs/architecture/serdes-layer.md`

**Step 1: Create SERDES layer overview**

Write introduction and architecture:

```markdown
# SERDES/Transceiver Layer Architecture

**Layer:** Physical Layer (Layer 1)
**Location:** `litepcie/phy/transceiver_base/`, `litepcie/phy/xilinx/`, `litepcie/phy/lattice/`
**Purpose:** Physical serialization, clock recovery, and analog signaling

## Overview

The SERDES layer implements the PCIe physical layer using FPGA internal transceivers. This provides a vendor-IP-free alternative to Xilinx/Lattice hard PCIe IP cores.

### Key Innovation

**Software 8b/10b encoding** across all platforms for consistency and visibility, rather than using hardware 8b/10b built into transceivers.

## Architecture Hierarchy

```
TransceiverBase (Common Abstraction)
    ├── S7GTXTransceiver (Xilinx 7-Series)
    ├── USPGTYTransceiver (Xilinx UltraScale+)
    └── ECP5SerDesTransceiver (Lattice ECP5)
```
```

**Step 2: Add transceiver base class diagram**

```markdown
## Transceiver Base Architecture

### PIPETransceiver Base Class

```
┌─────────────────────────────────────────────────────────────────┐
│                      PIPETransceiver                            │
│                 (Base class for all transceivers)               │
│                                                                 │
│  PIPE Interface (sys_clk domain)                                │
│  ═══════════════════════════════════                            │
│                                                                 │
│  TX Signals:                    RX Signals:                     │
│  • tx_data[15:0]                • rx_data[15:0]                 │
│  • tx_datak[1:0]                • rx_datak[1:0]                 │
│  • tx_elecidle                  • rx_elecidle                   │
│                                 • rx_valid                      │
│                                                                 │
│  Control:                       Status:                         │
│  • reset                        • tx_ready                      │
│  • speed[1:0]                   • rx_ready                      │
│                                                                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                    TX Datapath                             │ │
│  │              (TransceiverTXDatapath)                       │ │
│  │                                                            │ │
│  │   sys_clk domain          tx_clk domain                    │ │
│  │   ┌─────────┐           ┌──────────┐                       │ │
│  │   │ PIPE TX │  AsyncFIFO│ 8b/10b   │                       │ │
│  │   │ Input   │───────────►│ Encoder │                       │ │
│  │   │ 16-bit  │           │ (SW)     │                       │ │
│  │   └─────────┘           └────┬─────┘                       │ │
│  │                              │ 20-bit encoded              │ │
│  └──────────────────────────────┼─────────────────────────────┘ │
│                                 │                               │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │              Vendor-Specific Primitive                     │ │
│  │              (GTXE2, GTYE4, or DCUA)                       │ │
│  │                                                            │ │
│  │   ┌───────────────────────────────────────────────┐        │ │
│  │   │         TX Serializer (SERDES)                │        │ │
│  │   │                                               │        │ │
│  │   │  20-bit @ 250MHz → 1-bit @ 5GHz (Gen2)        │        │ │
│  │   │  20-bit @ 125MHz → 1-bit @ 2.5GHz (Gen1)      │        │ │
│  │   └────────────────────┬──────────────────────────┘        │ │
│  │                        │                                   │ │
│  │   ┌───────────────────▼──────────────────────────┐         │ │
│  │   │         RX Deserializer (SERDES)             │         │ │
│  │   │                                              │         │ │
│  │   │  1-bit @ 5GHz → 20-bit @ 250MHz (Gen2)       │         │ │
│  │   │  Includes: CDR, DFE, CTLE                    │         │ │
│  │   └────────────────────┬──────────────────────────┘        │ │
│  │                        │ 20-bit recovered                  │ │
│  └────────────────────────┼───────────────────────────────────┘ │
│                           │                                     │
│  ┌────────────────────────▼─────────────────────────────────┐   │
│  │                    RX Datapath                           │   │
│  │              (TransceiverRXDatapath)                     │   │
│  │                                                          │   │
│  │   rx_clk domain           sys_clk domain                 │   │
│  │   ┌──────────┐          ┌─────────┐                      │   │
│  │   │ 8b/10b   │ AsyncFIFO│ PIPE RX │                      │   │
│  │   │ Decoder  │──────────►│ Output │                      │   │
│  │   │ (SW)     │          │ 16-bit  │                      │   │
│  │   └──────────┘          └─────────┘                      │   │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │              Reset Sequencer                               │ │
│  │        (TransceiverResetSequencer)                         │ │
│  │                                                            │ │
│  │  FSM: INIT → PLL_LOCK → TX_READY → RX_SIGNAL →             │ │
│  │       CDR_LOCK → RX_READY → OPERATIONAL                    │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```
```

**Step 3: Add vendor-specific implementations**

Document each vendor's transceiver implementation with architecture details.

**Step 4: Add data flow timing diagrams**

Show symbol transmission timing, clock domain crossings, and 8b/10b encoding process.

**Step 5: Verify document completeness**

Run: `grep -c "^##" docs/architecture/serdes-layer.md`
Expected: At least 8 sections (overview, base, GTX, GTY, ECP5, reset, clocking, integration)

**Step 6: Commit**

```bash
git add docs/architecture/serdes-layer.md
git commit -m "docs: Add SERDES layer architecture documentation

- Document transceiver base abstraction
- Add vendor-specific implementations (GTX, GTY, ECP5)
- Include timing diagrams and data flow examples
- Explain software 8b/10b approach

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 3: Create PIPE Layer Documentation

**Goal:** Document the PIPE interface layer with protocol details

**Files:**
- Create: `docs/architecture/pipe-layer.md`

**Step 1: Create PIPE layer overview**

```markdown
# PIPE Interface Layer Architecture

**Layer:** PHY Interface (Layer 2)
**Location:** `litepcie/dll/pipe.py`
**Purpose:** MAC/PHY boundary - converts between DLL packets and 8-bit PIPE symbols

## Overview

The PIPE (PHY Interface for PCI Express) layer provides the boundary between the Data Link Layer (MAC) and the Physical Layer (PHY). It handles:

1. **Packetization:** 64-bit DLL packets → 8-bit PIPE symbols
2. **Depacketization:** 8-bit PIPE symbols → 64-bit DLL packets
3. **Framing:** K-character based START/END framing
4. **Ordered Sets:** SKP, TS1, TS2 generation and detection

## PIPE Interface Specification

Based on Intel PIPE 3.0 Specification for Gen1/Gen2 operation.
```

**Step 2: Add complete PIPE interface diagram**

Include TX packetizer FSM, RX depacketizer FSM, and ordered set handling.

**Step 3: Add symbol encoding tables**

Document K-character encoding (STP=0xFB, SDP=0x5C, END=0xFD, etc.) with examples.

**Step 4: Add timing diagrams**

Show complete TX→RX data flow with cycle-accurate timing.

**Step 5: Verify and commit**

---

## Task 4: Create DLL Layer Documentation

**Goal:** Document the Data Link Layer with reliability mechanisms

**Files:**
- Create: `docs/architecture/dll-layer.md`

**Step 1: Create DLL layer overview**

```markdown
# Data Link Layer (DLL) Architecture

**Layer:** Data Link Layer (Layer 3)
**Location:** `litepcie/dll/`
**Purpose:** Reliable packet delivery with error detection and automatic retry

## Overview

The DLL implements PCIe Section 3 requirements for reliable packet delivery:

1. **Error Detection:** LCRC (32-bit CRC) on all TLPs
2. **Error Recovery:** ACK/NAK protocol with automatic retry
3. **Flow Control:** DLLP-based flow control coordination
4. **Link Training:** LTSSM state machine for link initialization

## Key Components

- **DLL TX:** Adds sequence numbers and LCRC to outgoing TLPs
- **DLL RX:** Checks LCRC, sends ACK/NAK, delivers valid TLPs
- **Retry Buffer:** Stores up to 4KB of unacknowledged TLPs
- **DLLP Processing:** Handles ACK, NAK, UpdateFC, PM DLLPs
- **LTSSM:** Link training from DETECT through L0 to RECOVERY
```

**Step 2: Add DLL architecture diagram**

Show complete DLL TX/RX paths with retry buffer and LTSSM integration.

**Step 3: Add LTSSM state machine diagram**

```markdown
## LTSSM State Machine

```
                 Power On
                     │
                     ▼
            ┌────────────────┐
            │    DETECT      │  Receiver detection
            │                │  • Check for RX presence
            └────────┬───────┘  • Exit: RX detected
                     │
                     ▼
            ┌────────────────┐
            │   POLLING      │  Initial negotiation
            │                │  • Send TS1 ordered sets
            │   Substates:   │  • Wait for partner TS1
            │   • Active     │  • Exchange TS2
            │   • Config     │  • Negotiate speed/width
            └────────┬───────┘  • Exit: 8 consecutive TS2
                     │
                     ▼
            ┌────────────────┐
            │ CONFIGURATION  │  Link configuration
            │                │  • Accept TLPs from upper layer
            └────────┬───────┘  • Exit: Immediately
                     │
                     ▼
            ┌────────────────┐
            │      L0        │◄─┐ Normal operation
            │                │  │ • Data transfer enabled
            │  (Link Up!)    │  │ • Send/receive TLPs
            └────────┬───────┘  │ • Exit: Electrical idle error
                     │          │
                     ▼          │
            ┌────────────────┐  │
            │   RECOVERY     │──┘ Error recovery
            │                │    • Re-establish bit lock
            │   Substates:   │    • Verify configuration
            │   • RcvrLock   │    • Return to L0 or reset
            │   • RcvrCfg    │
            │   • Idle       │
            └────────────────┘
```
```

**Step 4: Add ACK/NAK protocol explanation**

Document sequence number management, ACK timing, NAK conditions, and retry mechanism.

**Step 5: Add DLLP format diagrams**

Show ACK, NAK, UpdateFC DLLP structures with field descriptions.

**Step 6: Verify and commit**

---

## Task 5: Create TLP Layer Documentation

**Goal:** Document the Transaction Layer

**Files:**
- Create: `docs/architecture/tlp-layer.md`

**Step 1: Create TLP layer overview**

```markdown
# Transaction Layer (TLP) Architecture

**Layer:** Transaction Layer (Layer 4)
**Location:** `litepcie/tlp/`
**Purpose:** High-level read/write transactions and message passing

## Overview

The TLP layer implements PCIe Section 2 requirements for transaction-based communication:

1. **TLP Types:** Memory Read/Write, I/O, Config, Completion, Messages
2. **Flow Control:** Credit-based flow control (Posted, Non-Posted, Completion)
3. **Routing:** Address-based and ID-based routing
4. **Completion Tracking:** Match completions to outstanding requests
```

**Step 2: Add TLP format diagrams**

Document all TLP header formats (3DW, 4DW) with field descriptions.

**Step 3: Add transaction flow examples**

Show complete read and write transaction sequences with timing.

**Step 4: Add flow control mechanism**

Explain credit pools, credit return, and throttling.

**Step 5: Verify and commit**

---

## Task 6: Create Integration Patterns Documentation

**Goal:** Document how layers integrate and data flows end-to-end

**Files:**
- Create: `docs/architecture/integration-patterns.md`

**Step 1: Create integration overview**

Document how all layers connect together with interface contracts.

**Step 2: Add complete end-to-end data flow**

Show a single TLP's journey from application through all layers to the wire and back.

**Step 3: Add clock domain architecture**

Document all clock domains (sys_clk, tx_clk, rx_clk, pcie_clk) and CDC points.

**Step 4: Add vendor PHY integration examples**

Show how to integrate with vendor IP vs. custom PIPE implementation.

**Step 5: Verify and commit**

---

## Task 7: Update Main Documentation Index

**Goal:** Link all new documentation into the main README

**Files:**
- Modify: `docs/README.md`

**Step 1: Read current README structure**

```bash
cat docs/README.md | head -50
```

**Step 2: Add new architecture section**

Update the architecture section to include:
```markdown
### 🏗️ Architecture Documentation
**Location:** `architecture/`

Complete system architecture with detailed layer documentation:

- **[Complete System Architecture](architecture/complete-system-architecture.md)** - Master architecture document with full stack overview
- **[SERDES Layer](architecture/serdes-layer.md)** - Physical transceiver layer (GTX/GTY/ECP5)
- **[PIPE Layer](architecture/pipe-layer.md)** - PHY Interface layer with protocol details
- **[DLL Layer](architecture/dll-layer.md)** - Data Link Layer with LTSSM and reliability
- **[TLP Layer](architecture/tlp-layer.md)** - Transaction Layer with flow control
- **[Integration Patterns](architecture/integration-patterns.md)** - Cross-layer integration guide
- [PIPE Architecture](architecture/pipe-architecture.md) - PIPE interface component diagrams (detailed)
- [Clock Domain Architecture](architecture/clock-domain-architecture.md) - Multi-domain clock strategy
- [Integration Strategy](architecture/integration-strategy.md) - Overall integration roadmap
```

**Step 3: Update "Getting Started" section**

Add new entry:
```markdown
### For New Users
1. **Start here:** [Complete System Architecture](architecture/complete-system-architecture.md)
2. Review layer-specific docs: [SERDES](architecture/serdes-layer.md), [PIPE](architecture/pipe-layer.md), [DLL](architecture/dll-layer.md), [TLP](architecture/tlp-layer.md)
3. Check [Integration Patterns](architecture/integration-patterns.md)
4. Explore [Integration Examples](guides/pipe-integration-examples.md)
```

**Step 4: Verify links work**

```bash
# Check all links resolve
for file in docs/architecture/*.md; do
  echo "Checking $file"
  grep -o '\[.*\](.*\.md)' "$file" | while read link; do
    # Extract path and verify file exists
    path=$(echo "$link" | sed 's/.*](\(.*\))/\1/')
    if [ ! -f "docs/$path" ] && [ ! -f "$path" ]; then
      echo "  BROKEN: $link"
    fi
  done
done
```

Expected: No broken links

**Step 5: Commit**

```bash
git add docs/README.md
git commit -m "docs: Update README with new standalone architecture documentation

- Add links to complete system architecture
- Add layer-specific documentation links
- Update getting started guide
- Organize architecture section with new comprehensive docs

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 8: Create Quick Reference Diagram

**Goal:** Create a one-page quick reference with the most important diagrams

**Files:**
- Create: `docs/architecture/quick-reference.md`

**Step 1: Create quick reference header**

```markdown
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
```

**Step 2: Add one-page stack diagram**

Include condensed version of the complete stack showing only essential components.

**Step 3: Add signal interface summary table**

Create table showing all layer interfaces:

```markdown
## Layer Interfaces Summary

| Layer | Input Interface | Output Interface | Width | Clock Domain |
|-------|----------------|------------------|-------|--------------|
| TLP   | User TLP requests | `phy.sink` | 64-512b | sys_clk |
| DLL   | `phy.sink` | DLL packets | 64b | sys_clk |
| PIPE  | DLL packets | PIPE symbols | 8b | sys_clk |
| Transceiver | PIPE symbols | 8b/10b encoded | 10b | tx_clk/rx_clk |
| SERDES | 10b encoded | Serial differential | 1b | 2.5-8 GHz |
```

**Step 4: Add key parameters table**

Document important configuration parameters (data widths, speeds, buffer sizes).

**Step 5: Verify and commit**

---

## Task 9: Validation and Cross-Reference Check

**Goal:** Ensure all documentation is consistent and cross-referenced correctly

**Files:**
- All files in `docs/architecture/`

**Step 1: Validate all internal links**

Run link checker script:
```bash
cd docs
for file in architecture/*.md; do
  echo "Checking $file..."
  # Extract all markdown links
  grep -o '\[.*\](.*\.md[^)]*)' "$file" | while IFS= read -r link; do
    path=$(echo "$link" | sed -n 's/.*](\([^)]*\)).*/\1/p')
    # Remove anchor if present
    filepath=$(echo "$path" | cut -d'#' -f1)
    if [ -n "$filepath" ]; then
      if [ ! -f "$filepath" ] && [ ! -f "architecture/$filepath" ]; then
        echo "  BROKEN LINK: $link in $file"
      fi
    fi
  done
done
```

Expected: No broken links

**Step 2: Verify diagram consistency**

Check that component names are consistent across all diagrams:
```bash
# Extract all component names from diagrams
grep -h "│.*│" docs/architecture/*.md | grep -v "^│ *│" | sort -u > /tmp/components.txt
# Review for inconsistencies
less /tmp/components.txt
```

Expected: Consistent naming (e.g., always "DLL TX" not "DLL Transmit" in one place and "DLL TX" in another)

**Step 3: Verify code references**

Check that all file path references are accurate:
```bash
# Find all code references like `litepcie/dll/pipe.py`
grep -ho '`litepcie/[^`]*`' docs/architecture/*.md | sort -u | while read ref; do
  file=$(echo "$ref" | tr -d '`')
  if [ ! -f "$file" ] && [ ! -d "$file" ]; then
    echo "Invalid reference: $ref"
  fi
done
```

Expected: All paths resolve to actual files

**Step 4: Check cross-references between docs**

Verify that each layer doc references the master doc and related layers:
```bash
# Each layer doc should reference complete-system-architecture.md
for file in docs/architecture/{serdes,pipe,dll,tlp}-layer.md; do
  if ! grep -q "complete-system-architecture.md" "$file"; then
    echo "Missing master doc reference in $file"
  fi
done
```

Expected: All layer docs reference master architecture doc

**Step 5: Generate documentation coverage report**

```bash
# Count sections in each doc
for file in docs/architecture/*.md; do
  sections=$(grep -c "^## " "$file")
  diagrams=$(grep -c "^```$" "$file" | awk '{print $1/2}')
  echo "$(basename $file): $sections sections, $diagrams diagrams"
done
```

Expected: Each layer doc has at least 6 sections and 3 diagrams

**Step 6: Commit validation fixes**

```bash
git add docs/architecture/
git commit -m "docs: Validate and fix cross-references in architecture documentation

- Fix broken internal links
- Standardize component naming across diagrams
- Verify all code path references
- Ensure cross-references between documents

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 10: Create Documentation Review Checklist

**Goal:** Create a checklist for reviewing the documentation completeness

**Files:**
- Create: `docs/architecture/REVIEW_CHECKLIST.md`

**Step 1: Create checklist document**

```markdown
# Architecture Documentation Review Checklist

Use this checklist to verify documentation completeness and quality.

## Completeness

### Complete System Architecture (`complete-system-architecture.md`)
- [ ] Contains full 5-layer stack diagram
- [ ] Explains what makes LitePCIe unique
- [ ] Provides reading guide for different audiences
- [ ] Cross-references all layer-specific docs
- [ ] Includes layer overview with component summaries

### SERDES Layer (`serdes-layer.md`)
- [ ] Documents PIPETransceiver base class
- [ ] Includes diagrams for GTX, GTY, and ECP5 wrappers
- [ ] Explains software 8b/10b decision
- [ ] Shows TX/RX datapath architecture
- [ ] Documents reset sequencing
- [ ] Includes timing diagrams

### PIPE Layer (`pipe-layer.md`)
- [ ] Documents TX Packetizer FSM
- [ ] Documents RX Depacketizer FSM
- [ ] Shows K-character framing (STP/SDP/END)
- [ ] Explains ordered set generation (SKP, TS1, TS2)
- [ ] Includes complete timing diagrams
- [ ] Shows data flow examples

### DLL Layer (`dll-layer.md`)
- [ ] Documents DLL TX and RX paths
- [ ] Shows LTSSM state machine diagram
- [ ] Explains ACK/NAK protocol
- [ ] Documents retry buffer mechanism
- [ ] Shows DLLP formats
- [ ] Explains sequence number management

### TLP Layer (`tlp-layer.md`)
- [ ] Documents all TLP types
- [ ] Shows TLP header formats
- [ ] Explains flow control mechanism
- [ ] Documents routing methods
- [ ] Shows transaction examples

### Integration Patterns (`integration-patterns.md`)
- [ ] Shows end-to-end data flow
- [ ] Documents clock domain architecture
- [ ] Shows vendor PHY integration
- [ ] Explains interface contracts between layers
- [ ] Includes complete integration example

## Quality

### Diagrams
- [ ] All diagrams use consistent component names
- [ ] ASCII diagrams are properly formatted (aligned columns)
- [ ] Signal names match code (e.g., `tx_data` not `txdata`)
- [ ] Arrows clearly show data flow direction
- [ ] Diagrams fit in 80-column terminal

### Cross-References
- [ ] All internal links work (no 404s)
- [ ] Each layer doc references master doc
- [ ] Related concepts are cross-linked
- [ ] Code file paths are accurate
- [ ] External spec references are included

### Code Examples
- [ ] All code paths are valid (files exist)
- [ ] Signal names match implementation
- [ ] Register names are accurate
- [ ] Examples are syntactically correct
- [ ] Comments explain non-obvious details

### Readability
- [ ] Suitable for readers with no LitePCIe experience
- [ ] Technical terms are defined on first use
- [ ] Complex concepts have examples
- [ ] Progressive disclosure (simple → complex)
- [ ] Consistent terminology throughout

## Validation

Run these commands to verify:

```bash
# Check for broken links
cd docs && for f in architecture/*.md; do echo "=== $f ===" && grep -o '\[.*\](.*\.md)' "$f"; done

# Verify code references
grep -ho '`litepcie/[^`]*`' docs/architecture/*.md | sort -u | while read ref; do file=$(echo "$ref" | tr -d '`'); [ -e "$file" ] || echo "Missing: $ref"; done

# Count coverage
for f in docs/architecture/{serdes,pipe,dll,tlp}-layer.md; do echo "$f: $(grep -c '^## ' $f) sections"; done
```

## Sign-off

- [ ] All checklist items complete
- [ ] Validation commands pass
- [ ] Peer review completed
- [ ] Ready for publication
```

**Step 2: Run initial checklist review**

Go through checklist and verify initial implementation meets requirements.

**Step 3: Commit checklist**

```bash
git add docs/architecture/REVIEW_CHECKLIST.md
git commit -m "docs: Add architecture documentation review checklist

- Create comprehensive review checklist
- Include completeness checks for all layer docs
- Add quality validation criteria
- Provide validation commands

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Success Criteria

Documentation is complete when:

**Completeness:**
- [ ] All 6 core architecture documents exist (master + 5 layers)
- [ ] Each document has minimum 6 sections
- [ ] Each document has minimum 3 diagrams
- [ ] Quick reference document created
- [ ] Review checklist complete

**Quality:**
- [ ] All internal links work (0 broken links)
- [ ] All code references are valid
- [ ] Component names consistent across docs
- [ ] Diagrams properly formatted and aligned
- [ ] No spelling/grammar errors

**Standalone:**
- [ ] Can be read without external references
- [ ] Suitable for readers with no LitePCIe knowledge
- [ ] All technical terms defined
- [ ] Progressive complexity (overview → details)

**Integration:**
- [ ] All docs cross-reference each other
- [ ] Master README updated with links
- [ ] Fits into existing docs structure
- [ ] Consistent with existing guides

**Validation:**
- [ ] Review checklist 100% complete
- [ ] All validation commands pass
- [ ] Peer review approved
- [ ] Ready for publication

---

## Timeline Estimate

| Task | Description | Estimated Time |
|------|-------------|----------------|
| 1 | Main system architecture | 2 hours |
| 2 | SERDES layer docs | 3 hours |
| 3 | PIPE layer docs | 2 hours |
| 4 | DLL layer docs | 3 hours |
| 5 | TLP layer docs | 2 hours |
| 6 | Integration patterns | 2 hours |
| 7 | Update README | 0.5 hours |
| 8 | Quick reference | 1 hour |
| 9 | Validation | 1 hour |
| 10 | Review checklist | 0.5 hours |
| **Total** | **Complete documentation** | **17 hours** |

---

## Notes

- Each task is self-contained with clear inputs and outputs
- All diagrams use ASCII art for universal compatibility
- Documentation follows existing LitePCIe docs conventions
- Code examples reference actual implementation files
- Cross-references create cohesive documentation set
- Validation ensures quality and accuracy

---

**Plan Status:** Ready for execution
**Created:** 2025-10-18
**Execution Method:** Use `${SUPERPOWERS_SKILLS_ROOT}/skills/collaboration/executing-plans/SKILL.md`
