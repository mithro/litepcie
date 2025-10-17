# PIPE Interface Specification (Minimal PIPE 3.0)

## Overview

This document defines the PIPE (PHY Interface for PCI Express) signals
and protocol used in LitePCIe's open source implementation.

**Version:** PIPE 3.0 (PCIe Gen1/Gen2)
**Scope:** MAC side (we drive the PHY)
**Approach:** Minimal working subset, expand incrementally

**Status:** Living document - updates as we implement and discover edge cases.

## What is PIPE?

PIPE (PHY Interface for PCI Express) is a standard interface specification
originally developed by Intel to abstract the PHY layer from the MAC/Link
layer in PCI Express designs. It provides a protocol-agnostic interface
that can support PCIe, USB 3.x, SATA, DisplayPort, and other protocols.

**Why PIPE?**
- **Abstraction:** Separates analog PHY complexity from digital MAC/Link logic
- **Flexibility:** Same interface works with external PHY chips or internal transceivers
- **Portability:** Design once, use with multiple PHY implementations
- **Open Source:** Enables fully open source PCIe stack (no vendor IP black box)

## Signal List (8-bit Mode, Gen1)

This is the **minimal subset** for PCIe Gen1 (2.5 GT/s) with 8-bit PIPE interface.
We will expand to 16-bit and 32-bit modes, and Gen2/Gen3 speeds, as needed.

### Transmit Interface

| Signal | Width | Direction | Description |
|--------|-------|-----------|-------------|
| TxData | 8 | MAC→PHY | Transmit data |
| TxDataK | 1 | MAC→PHY | K-character indicator (1=ordered set, 0=data) |
| TxElecIdle | 1 | MAC→PHY | Electrical idle request |

### Receive Interface

| Signal | Width | Direction | Description |
|--------|-------|-----------|-------------|
| RxData | 8 | PHY→MAC | Received data |
| RxDataK | 1 | PHY→MAC | K-character indicator |
| RxValid | 1 | PHY→MAC | Data valid (1=valid data present) |
| RxStatus | 3 | PHY→MAC | Receiver status (see status codes below) |
| RxElecIdle | 1 | PHY→MAC | Electrical idle detected |

### Control Interface

| Signal | Width | Direction | Description |
|--------|-------|-----------|-------------|
| PowerDown | 2 | MAC→PHY | Power state (00=P0, 01=P0s, 10=P1, 11=P2) |
| Rate | 1 | MAC→PHY | Speed select (0=Gen1/2.5GT/s, 1=Gen2/5.0GT/s) |
| RxPolarity | 1 | MAC→PHY | Invert RX polarity (for lane reversal) |

### Clock/Reset

| Signal | Width | Direction | Description |
|--------|-------|-----------|-------------|
| PCLK | 1 | PHY→MAC | Parallel clock (125 MHz for 8-bit Gen1) |
| Reset_n | 1 | MAC→PHY | Active-low reset |

## RxStatus Codes

The RxStatus[2:0] signal provides receiver state information:

| Code | Name | Description |
|------|------|-------------|
| 000 | Normal | Normal operation, data valid |
| 001 | Reserved | - |
| 010 | Reserved | - |
| 011 | Disparity Error | 8b/10b disparity error detected |
| 100 | Decode Error | Invalid 8b/10b symbol received |
| 101 | Elastic Buffer Overflow | Clock compensation buffer overflow |
| 110 | Elastic Buffer Underflow | Clock compensation buffer underflow |
| 111 | Reserved | - |

## Protocol Essentials

### 8b/10b Encoding

PCIe Gen1/Gen2 use 8b/10b encoding for the serial link. The PHY handles
encoding (TX) and decoding (RX), presenting 8-bit data to the MAC.

**Data Characters:** TxDataK=0, RxDataK=0
- Normal data bytes (0x00-0xFF)

**Control Characters (K-codes):** TxDataK=1, RxDataK=1
- Special ordered sets for link management

### Common Ordered Sets

Ordered sets are sequences that include K-characters. Common ordered sets
used in PCIe:

| Name | K-code | Value | Purpose |
|------|--------|-------|---------|
| COM | K28.5 | 0xBC | Comma character for alignment |
| SKP | K28.0 | 0x1C | Skip ordered set for clock compensation |
| PAD | K23.7 | 0xF7 | Padding between packets |
| STP | K27.7 | 0xFB | Start of TLP |
| SDP | K28.2 | 0x5C | Start of DLLP |
| END | K29.7 | 0xFD | End of packet |
| EDB | K30.7 | 0xFE | End bad (packet with error) |

### Ordered Set Sequences

**TS1 (Training Sequence 1):**
Used during link training (ordered set for link training, speed negotiation, lane number, etc.)

**TS2 (Training Sequence 2):**
Used during link training after TS1

**IDLE:**
Electrical idle ordered set

**FTS (Fast Training Sequence):**
Used for quick exit from low power states

(Full ordered set definitions will be added as we implement link training)

### Data Transmission Flow

**Sending a TLP:**

1. MAC asserts TxDataK=1, TxData=STP (Start of TLP)
2. MAC sends TLP header bytes with TxDataK=0
3. MAC sends TLP data payload with TxDataK=0
4. MAC asserts TxDataK=1, TxData=END (End of TLP)
5. PHY handles 8b/10b encoding and serialization

**Receiving a TLP:**

1. PHY asserts RxDataK=1, RxData=STP, RxValid=1
2. PHY presents header bytes with RxDataK=0, RxValid=1
3. PHY presents data payload with RxDataK=0, RxValid=1
4. PHY asserts RxDataK=1, RxData=END/EDB, RxValid=1
5. MAC validates packet (DLL checks LCRC)

### Clock Domains

**PCLK (Parallel Clock):**
- Gen1 (8-bit): 125 MHz (2.5 GT/s ÷ 10 bits ÷ 2)
- Gen2 (8-bit): 250 MHz (5.0 GT/s ÷ 10 bits ÷ 2)

All PIPE signals are synchronous to PCLK.

### Power States

| PowerDown | State | Description |
|-----------|-------|-------------|
| 00 | P0 | Full power, link active |
| 01 | P0s | Power savings, quick recovery |
| 10 | P1 | Low power, medium recovery time |
| 11 | P2 | Lowest power, longest recovery |

## Implementation Notes

### MAC Side Implementation

We are implementing the **MAC side** of PIPE, which means:
- We **drive** the PHY (send commands via TxData, TxDataK, PowerDown, etc.)
- We **respond** to PHY signals (read RxData, RxDataK, RxStatus, etc.)
- The PHY can be either:
  - **External PIPE chip** (e.g., TI TUSB1310A for USB3, similar for PCIe)
  - **FPGA internal transceiver** (GTX, SERDES) with our PIPE wrapper

### External PHY First

We start with external PIPE PHY chips because:
- Simplest integration (chip handles analog details)
- Concrete reference (datasheet provides exact timing)
- Proven hardware (can test immediately)
- Validates architecture before tackling internal transceivers

### Internal Transceivers Later

After external PHY works, we implement wrappers for FPGA transceivers:
- **Xilinx 7-Series GTX:** PIPE wrapper for Series 7 FPGAs
- **Lattice ECP5 SERDES:** PIPE wrapper for ECP5 (open source hero platform)

These wrappers present the same PIPE interface to the DLL.

### Incremental Expansion

This minimal spec is Gen1, 8-bit mode only. We will iterate to add:
- **Gen2 support:** 5.0 GT/s (Rate=1, PCLK=250 MHz)
- **Gen3 support:** 8.0 GT/s (128b/130b encoding, not 8b/10b)
- **16-bit mode:** Wider datapath (PCLK=125 MHz for Gen2)
- **32-bit mode:** Even wider (PCLK=62.5 MHz for Gen2)
- **Additional ordered sets:** As needed for link training, hot plug, etc.

## References

### PIPE Specifications

- **PIPE 3.1 (Multi-protocol):**
  https://www.intel.com/content/dam/www/public/us/en/documents/white-papers/phy-interface-pci-express-sata-usb30-architectures-3.1.pdf
  Covers PCI Express, SATA, USB 3.1, DisplayPort, Converged IO

- **PIPE 3.0 (PCIe & USB3):**
  https://www.intel.in/content/dam/doc/white-paper/usb3-phy-interface-pci-express-paper.pdf
  Intel white paper defining PIPE for PCIe and USB 3.0

### PCIe Base Specification

- **PCIe Base Spec 4.0 (Section 4: Physical Layer):**
  https://raw.githubusercontent.com/osdev-jp/spec/refs/heads/main/PCI_Express_Base_4.0_Rev0.3_February19-2014.pdf
  Official specification (also available at https://pcisig.com with membership)

- **Relevant sections:**
  - Section 4.2: Physical Layer (Logical)
  - Section 4.2.6: Training Sequences
  - Section 4.2.7: Ordered Sets

### External PIPE PHY Chips

- **TI TUSB1310A (USB3.0 with PIPE interface):**
  https://www.ti.com/lit/ds/symlink/tusb1310a.pdf
  Note: This is a USB3 chip, but demonstrates PIPE interface implementation
  Status: NRND (Not Recommended for New Designs)

- **Alternative external PIPE PHY chips:** TBD as we discover them

### Open Source PIPE Implementations

- **Enjoy-Digital usb3_pipe:**
  https://github.com/enjoy-digital/usb3_pipe
  USB3 PIPE interface for Xilinx 7-Series (Kintex-7, Artix-7)
  Shows how to wrap GTX transceivers with PIPE interface

### Books

- **"PCI Express System Architecture"** by Ravi Budruk, Don Anderson, Tom Shanley
  Chapters 8-9: Physical Layer and Link Layer

## Open Questions

(This section tracks questions we discover during implementation)

1. **Exact timing requirements:** What are setup/hold times for PIPE signals?
   - *Resolution:* Check PIPE spec Section X and PHY datasheet

2. **Error handling:** How should MAC respond to RxStatus errors?
   - *Resolution:* DLL protocol defines retry mechanism (covered in DLL docs)

3. **Clock compensation:** How often to insert/remove SKP ordered sets?
   - *Resolution:* PCIe spec defines every 1180-1538 symbols

4. **Lane reversal:** When to assert RxPolarity?
   - *Resolution:* During link training if TS1/TS2 received with inverted polarity

## Implementation Status

### Phase 4: PIPE TX/RX Datapath ✅ COMPLETE (2025-10-17)

**Implementation Files:**
- `litepcie/dll/pipe.py` - Complete PIPE interface implementation (495 lines, 99% coverage)
  - `PIPETXPacketizer` - Converts 64-bit DLL packets → 8-bit PIPE symbols
  - `PIPERXDepacketizer` - Converts 8-bit PIPE symbols → 64-bit DLL packets
  - `PIPEInterface` - Top-level integration with TX/RX paths
  - K-character framing (STP, SDP, END)
  - Little-endian byte ordering
  - Electrical idle signaling
  - Power management controls

- `litepcie/phy/pipe_external_phy.py` - External PHY wrapper foundation (96% coverage)
  - Drop-in replacement interface for vendor IP
  - Platform integration helpers
  - DLL integration (work in progress)

**Test Coverage:**
- 26 PIPE-specific tests (all passing, 100% success rate)
- TX Packetizer: 5 tests (structure, START for TLP/DLLP, DATA, END)
- RX Depacketizer: 5 tests (structure, START for TLP/DLLP, DATA, END)
- Integration: 6 tests (interface structure, TX behavior, TX/RX integration, loopback, parameter validation)
- Edge Cases: 8 tests (TX: all-zeros/ones/back-to-back; RX: invalid K-char/K-char in data/missing END; Integration: multi-packet/K-char data)
- External PHY: 2 tests (structure validation)
- Code coverage: 99% (pipe.py - 77 statements, 1 missed), 92% (pipe_external_phy.py)

**Documentation:**
- [PIPE Interface User Guide](pipe-interface-guide.md) - Complete API reference and usage guide
- [PIPE Architecture](pipe-architecture.md) - Detailed architecture with timing diagrams
- [Integration Examples](pipe-integration-examples.md) - 5 practical integration examples
- [Testing Guide](pipe-testing-guide.md) - TDD workflow and debugging guide
- [Integration Strategy](integration-strategy.md) - Development phases (updated)

**Features Implemented:**
- ✅ 8-bit PIPE mode (Gen1/Gen2)
- ✅ TX packetization with K-character framing
- ✅ RX depacketization with byte accumulation
- ✅ TLP/DLLP packet type detection
- ✅ Loopback testing infrastructure
- ✅ Comprehensive edge case handling
- ✅ Parameter validation
- ✅ Debug mode for testing

**Features Pending:**
- ⬜ Multi-lane support (x4, x8, x16)
- ⬜ Internal transceiver wrappers (Xilinx GTX, ECP5 SERDES)
- ⬜ Gen3 support (128b/130b encoding)
- ⬜ 16/32-bit PIPE modes
- ⬜ Complete external PHY integration
- ⬜ Error injection (EDB - End Bad packet)

### Phase 5: Ordered Sets & Link Training Foundation ✅ COMPLETE (2025-10-17)

**Implementation Files:**
- `litepcie/dll/pipe.py` - Extended with ordered set support (924 lines total)
  - SKP ordered set generation and detection (clock compensation)
  - TS1/TS2 ordered set data structures and TX/RX support
  - Enhanced TX/RX FSMs with SKP and TS states
  - PIPEInterface integration (enable_skp, enable_training_sequences parameters)

**Test Coverage:**
- 90 DLL tests total (all passing, 100% success rate)
- SKP Tests: 3 tests (TX generation, TX insertion, RX detection)
- TS1/TS2 Tests: 4 tests (structure validation, TX generation, RX detection)
- Integration: SKP loopback test validates transparent operation
- Code coverage: 99% (litepcie/dll/pipe.py - 142 statements, 2 missed)

**Documentation:**
- [Phase 5 Completion Summary](phase-5-completion-summary.md) - Detailed implementation notes
- [Performance Analysis](pipe-performance.md) - Throughput, latency, resource analysis
- [Testing Guide](pipe-testing-guide.md) - Updated with Phase 5 test patterns
- [Integration Strategy](integration-strategy.md) - Updated with Phase 5 completion

**Features Implemented:**
- ✅ SKP ordered set TX generation with configurable interval (default 1180 symbols)
- ✅ SKP ordered set RX detection and transparent removal
- ✅ SKP integration through PIPEInterface (enable_skp parameter)
- ✅ TS1OrderedSet data structure (16 symbols, D10.2 identifier)
- ✅ TS2OrderedSet data structure (16 symbols, D5.2 identifier)
- ✅ TS1/TS2 TX generation in PIPETXPacketizer (manual trigger via send_ts1/send_ts2)
- ✅ TS1/TS2 RX detection in PIPERXDepacketizer (ts1_detected/ts2_detected flags)
- ✅ Edge case handling (COM disambiguation: SKP vs TS vs START symbols)

**Phase 6 Complete (LTSSM) ✅:**
- ✅ LTSSM States: DETECT, POLLING, CONFIGURATION, L0, RECOVERY
- ✅ Automatic link training (power-on to L0 in ~56 cycles)
- ✅ Automatic TS1/TS2 exchange during link training
- ✅ Error recovery (L0 → RECOVERY → L0)
- ✅ Link status indication (link_up signal)

**Features Pending (Phase 7):**
- ⬜ Gen2 speed negotiation (5.0 GT/s)
- ⬜ Multi-lane support (x4, x8, x16)
- ⬜ Lane reversal detection
- ⬜ Power management states (L0s, L1, L2)

**Commits:**
- `0747c51` - SKP TX insertion logic
- `d011a01` - SKP RX detection
- `b011f3e` - SKP PIPEInterface integration
- `7ba638e` - SKP edge case fixes (START symbols in SKP_CHECK)
- `2a7f614` - TS1/TS2 data structures
- `cf17359` - TS1/TS2 TX generation capability
- `70c78cc` - TS1/TS2 RX detection capability

## Revision History

| Date | Version | Changes |
|------|---------|---------|
| 2025-10-16 | 0.1 | Initial minimal PIPE 3.0 spec for Gen1, 8-bit mode |
| 2025-10-17 | 0.2 | Added Implementation Status section for Phase 4 completion |
| 2025-10-17 | 0.3 | Added Phase 5 status: SKP ordered sets and TS1/TS2 structures |
| 2025-10-17 | 0.4 | Added Phase 6 completion: LTSSM with automatic link training |

## Implementation Status

### Phase 4: TX/RX Data Paths ✅ (Completed 2025-10-17)
1. ~~Implement DLL layer (independent of PIPE)~~ ✅ Complete
2. ~~Create PIPE interface abstraction in litepcie/dll/pipe.py~~ ✅ Complete
3. ~~Integrate DLL with PIPE interface~~ ✅ Complete
4. ~~TX Packetizer: 64-bit DLL packets → 8-bit PIPE symbols~~ ✅ Complete
5. ~~RX Depacketizer: 8-bit PIPE symbols → 64-bit DLL packets~~ ✅ Complete
6. ~~Loopback testing and validation~~ ✅ Complete
7. ~~Comprehensive documentation (user guide, architecture, examples)~~ ✅ Complete

### Phase 5: Ordered Sets & Link Training Foundation ✅ (Completed 2025-10-17)
1. ~~Add SKP ordered set generation and detection~~ ✅ Complete
2. ~~Create TS1/TS2 ordered set data structures~~ ✅ Complete
3. ~~Implement TS1/TS2 TX generation in PIPETXPacketizer~~ ✅ Complete
4. ~~Implement TS1/TS2 RX detection in PIPERXDepacketizer~~ ✅ Complete
5. ~~Coverage analysis and edge case testing~~ ✅ Complete
6. ~~91 DLL tests passing, 99% code coverage~~ ✅ Complete

### Phase 6: Link Training State Machine (LTSSM) ✅ (Completed 2025-10-17)
1. ~~Implement LTSSM states (Detect, Polling, Configuration, Recovery, L0)~~ ✅ Complete
2. ~~Add automatic TS1/TS2 exchange during link initialization~~ ✅ Complete
3. ~~Add lane configuration logic (x1)~~ ✅ Complete (Gen1 x1)
4. ~~Implement link up/down detection~~ ✅ Complete
5. ~~LTSSM integration with PIPEInterface~~ ✅ Complete
6. ~~Automatic link training loopback test~~ ✅ Complete
7. ~~107 DLL tests passing, 98% code coverage~~ ✅ Complete

### Phase 7: Advanced LTSSM Features ⏳ (Planned)
1. Gen2 speed negotiation (5.0 GT/s)
2. Multi-lane support (x4, x8, x16)
3. Lane reversal detection
4. Equalization support
5. Power management states (L0s, L1, L2)
6. Compliance mode

### Phase 8: External PHY Integration ⏳ (Planned)
1. Complete external PIPE PHY wrapper integration
2. Test with external hardware (TI TUSB1310A or similar)
3. Receiver detection using PHY capabilities
4. Validate Gen1 x1 operation on hardware

### Future Enhancements (Phase 9+)
1. Add internal transceiver wrappers (Xilinx GTX, ECP5 SERDES)
2. Add multi-lane support (x4, x8, x16)
3. Expand to Gen3, wider datapaths (16/32-bit modes)
4. Advanced features (equalization, hot-plug, power management)

---

**This is a living document.** Updates will be made as we:
- Implement external PHY wrapper and discover timing requirements
- Add Gen2 support and 16/32-bit modes
- Implement internal transceiver wrappers
- Discover edge cases and error conditions during testing
