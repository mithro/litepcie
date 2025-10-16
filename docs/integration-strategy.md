# LitePCIe Integration Strategy

## Goal

Provide drop-in replacement for vendor PCIe IP with open source DLL+PIPE stack.

Users can transparently swap between vendor IP (Xilinx, Lattice, etc.) and our
open source implementation without changing TLP layer code.

## Interface Contract

The PHY (whether vendor IP or our custom stack) must provide a well-defined
interface to the TLP layer via the `LitePCIeEndpoint`.

### PHY Layout

From `litepcie/common.py:34-39`:

```python
def phy_layout(data_width):
    layout = [
        ("dat", data_width),
        ("be",  data_width//8)
    ]
    return EndpointDescription(layout)
```

The `phy_layout` defines the datapath signals:
- **dat**: Data (TLP payload)
- **be**: Byte enable (indicates which bytes are valid)

Plus standard stream control signals from LiteX:
- **valid**: Data is valid
- **ready**: Sink is ready to accept data
- **first**: First beat of packet
- **last**: Last beat of packet

### PHY Wrapper Class Structure

All PHY implementations (vendor or open source) must provide:

```python
class SomePCIePHY(LiteXModule):
    """PCIe PHY wrapper (vendor IP or open source)"""

    def __init__(self, platform, pads, data_width=64, ...):
        # Same signature pattern across all PHY implementations

        # Must provide these stream endpoints
        self.sink   = stream.Endpoint(phy_layout(data_width))  # TX from TLP layer
        self.source = stream.Endpoint(phy_layout(data_width))  # RX to TLP layer
        self.msi    = stream.Endpoint(msi_layout())             # MSI interrupts

        # Must provide these CSR registers
        self._link_status       = CSRStatus(...)  # Link up/down, speed, width, LTSSM
        self._msi_enable        = CSRStatus(...)  # MSI enable status
        self._msix_enable       = CSRStatus(...)  # MSI-X enable status
        self._bus_master_enable = CSRStatus(...)  # Bus mastering status
        self._max_request_size  = CSRStatus(...)  # Negotiated max request size
        self._max_payload_size  = CSRStatus(...)  # Negotiated max payload size

        # Must provide these attributes
        self.data_width = data_width              # Datapath width (64, 128, 256, 512)
        self.bar0_mask  = get_bar_mask(bar0_size) # BAR0 address mask
```

### How TLP Layer Connects to PHY

From `litepcie/core/endpoint.py:38-55`:

```python
class LitePCIeEndpoint(LiteXModule):
    def __init__(self, phy, ...):
        # PHY has shared Request/Completion channels
        if hasattr(phy, "sink") and hasattr(phy, "source"):
            # Create TLP depacketizer (RX: PHY → TLP)
            self.depacketizer = LitePCIeTLPDepacketizer(
                data_width = phy.data_width,
                ...
            )
            # Create TLP packetizer (TX: TLP → PHY)
            self.packetizer = LitePCIeTLPPacketizer(
                data_width = phy.data_width,
                ...
            )
            # Connect PHY to TLP layer
            self.comb += [
                phy.source.connect(depacketizer.sink),  # RX path
                packetizer.source.connect(phy.sink)     # TX path
            ]
```

**Key insight:** The `LitePCIeEndpoint` only cares that the PHY has:
1. `.sink` endpoint (receives TLPs to transmit)
2. `.source` endpoint (produces received TLPs)
3. `.data_width` attribute
4. `.bar0_mask` attribute

Everything else is PHY implementation details!

## Architecture Comparison

### Current (Vendor IP)

```
┌─────────────────┐
│   TLP Layer     │  (LitePCIeEndpoint, Packetizer, Depacketizer)
│  litepcie/tlp/  │
└────────┬────────┘
         │ phy.sink/source (phy_layout)
         │
┌────────▼────────┐
│   Vendor PHY    │  (S7PCIEPHY, USPCIEPHY, etc.)
│  litepcie/phy/  │  - Wraps Xilinx/Lattice hard IP
└────────┬────────┘  - DLL+PHY in black box
         │
         │ Transceivers (GTX, SERDES, etc.)
         │
```

### New (Open Source)

```
┌─────────────────┐
│   TLP Layer     │  (LitePCIeEndpoint, Packetizer, Depacketizer)
│  litepcie/tlp/  │
└────────┬────────┘
         │ phy.sink/source (phy_layout) <-- SAME INTERFACE!
         │
┌────────▼────────┐
│   Custom PHY    │  (New: PIPEPCIePHY, ECP5PIPEPCIePHY, etc.)
│  litepcie/phy/  │  - Open source DLL (litepcie/dll/)
│                 │  - PIPE interface (litepcie/dll/pipe.py)
│                 │  - External PIPE chip OR internal transceiver wrapper
└────────┬────────┘
         │
         │ PIPE interface
         │
┌────────▼────────┐
│   PHY Layer     │
│                 │  Option A: External PIPE PHY chip (TI TUSB1310A, etc.)
│                 │  Option B: FPGA transceiver with PIPE wrapper
└─────────────────┘
```

## Drop-In Replacement Examples

### Example 1: Xilinx Vendor IP (Current)

```python
from litepcie.phy.s7pciephy import S7PCIEPHY

# Create PHY using Xilinx vendor IP
phy = S7PCIEPHY(
    platform    = platform,
    pads        = platform.request("pcie_x4"),
    data_width  = 128,
    cd          = "sys",
    bar0_size   = 0x100000,
)

# Create endpoint (TLP layer)
endpoint = LitePCIeEndpoint(phy, address_width=32)

# Rest of design...
```

### Example 2: Open Source External PIPE PHY (New)

```python
from litepcie.phy.pipe_phy import PIPEPCIePHY

# Create PHY using open source DLL + external PIPE chip
phy = PIPEPCIePHY(
    platform    = platform,
    pads        = platform.request("pcie_x4"),
    data_width  = 128,
    cd          = "sys",
    bar0_size   = 0x100000,
    pipe_chip   = "TUSB1310A",  # External PIPE PHY chip
)

# Create endpoint (TLP layer) - IDENTICAL CODE
endpoint = LitePCIeEndpoint(phy, address_width=32)

# Rest of design... - IDENTICAL CODE
```

### Example 3: Open Source ECP5 Internal SERDES (New)

```python
from litepcie.phy.ecp5_pipe_phy import ECP5PIPEPCIePHY

# Create PHY using open source DLL + ECP5 SERDES
phy = ECP5PIPEPCIePHY(
    platform    = platform,
    pads        = platform.request("pcie_x4"),
    data_width  = 128,
    cd          = "sys",
    bar0_size   = 0x100000,
)

# Create endpoint (TLP layer) - IDENTICAL CODE
endpoint = LitePCIeEndpoint(phy, address_width=32)

# Rest of design... - IDENTICAL CODE
```

**Key point:** Only the PHY import and instantiation change. Everything else is identical.

## Internal PHY Architecture

Our custom PHY wrappers will contain:

```
┌──────────────────────────────────────────────────────────────┐
│                    PIPEPCIePHY (or ECP5PIPEPCIePHY)           │
│                                                               │
│  ┌──────────────┐    ┌──────────────┐    ┌───────────────┐  │
│  │   TX Path    │    │   RX Path    │    │  MSI Handler  │  │
│  │              │    │              │    │               │  │
│  │ PHYTXDatapath│    │ PHYRXDatapath│    │   MSI CDC     │  │
│  │  (CDC+Conv)  │    │  (CDC+Conv)  │    │               │  │
│  └──────┬───────┘    └──────▲───────┘    └───────────────┘  │
│         │                   │                                │
│  ┌──────▼───────────────────┴───────┐                        │
│  │           DLL Layer              │                        │
│  │  (litepcie/dll/)                 │                        │
│  │                                  │                        │
│  │  - DLLP processing               │                        │
│  │  - Sequence numbers              │                        │
│  │  - LCRC gen/check                │                        │
│  │  - Retry buffer                  │                        │
│  │  - ACK/NAK protocol              │                        │
│  │  - Flow control                  │                        │
│  └──────┬───────────────────▲───────┘                        │
│         │                   │                                │
│  ┌──────▼───────────────────┴───────┐                        │
│  │        PIPE Interface            │                        │
│  │  (litepcie/dll/pipe.py)          │                        │
│  │                                  │                        │
│  │  - Ordered set generation        │                        │
│  │  - 8b/10b symbol handling        │                        │
│  │  - Power state management        │                        │
│  │  - PIPE signal protocol          │                        │
│  └──────┬───────────────────▲───────┘                        │
│         │                   │                                │
│  ┌──────▼───────────────────┴───────┐                        │
│  │         PHY Wrapper              │                        │
│  │  (External chip OR transceiver)  │                        │
│  │                                  │                        │
│  │  Option A: External PIPE chip    │                        │
│  │  Option B: GTX PIPE wrapper      │                        │
│  │  Option C: ECP5 SERDES wrapper   │                        │
│  └──────────────────────────────────┘                        │
└──────────────────────────────────────────────────────────────┘
```

## Datapath Details

### TX Path (TLP → PHY)

From `litepcie/phy/common.py:14-44`:

```python
class PHYTXDatapath(Module):
    """TX datapath with CDC and width conversion"""
    def __init__(self, core_data_width, pcie_data_width, clock_domain):
        self.sink   = stream.Endpoint(phy_layout(core_data_width))
        self.source = stream.Endpoint(phy_layout(pcie_data_width))

        # Handles:
        # 1. Clock domain crossing (core_clock → pcie_clock)
        # 2. Data width conversion (e.g., 64-bit → 128-bit)
        # 3. Pipeline stages for timing
```

**Our implementation will reuse this!** The DLL sits in the "pcie" clock domain
and produces `phy_layout()` data to the TX datapath.

### RX Path (PHY → TLP)

From `litepcie/phy/common.py:91-128`:

```python
class PHYRXDatapath(Module):
    """RX datapath with CDC, width conversion, and alignment"""
    def __init__(self, core_data_width, pcie_data_width, clock_domain, with_aligner):
        self.sink   = stream.Endpoint(phy_layout(pcie_data_width))
        self.source = stream.Endpoint(phy_layout(core_data_width))

        # Handles:
        # 1. Data alignment (128-bit only)
        # 2. Width conversion
        # 3. Clock domain crossing (pcie_clock → core_clock)
```

**Our implementation will reuse this too!** The DLL receives `phy_layout()` data
from RX datapath.

## Implementation Phases

### Phase 0: Foundation (Completed)
- Task 0.1: ✅ PIPE interface documentation
- Task 0.2: ✅ Integration strategy (this document)
- Task 0.3: ✅ CI/CD setup
- Task 0.4: ✅ Code quality standards

### Phase 1: DLL Core (Completed)
- Task 1.1: ✅ DLL common structures
- Task 1.2: ✅ DLLP processing
- Task 1.3: ✅ Sequence number management
- Task 1.4: ✅ LCRC generation/checking
- Task 1.5: ✅ Retry buffer
- Task 1.6: ✅ DLL TX path
- Task 1.7: ✅ DLL RX path

### Phase 2: DLL Core (Continued)
Build DLL layer independently, test with models:
- DLLP structures (ACK, NAK, etc.)
- Sequence number management
- LCRC generation/checking
- Retry buffer

DLL has internal interface (not yet PIPE):
```python
# dll_tx_sink (from TLP layer)
layout = [("dat", data_width), ("be", data_width//8)]

# dll_tx_source (to PIPE interface)
layout = [("dat", data_width), ("be", data_width//8)]

# dll_rx_sink (from PIPE interface)
layout = [("dat", data_width), ("be", data_width//8)]

# dll_rx_source (to TLP layer)
layout = [("dat", data_width), ("be", data_width//8)]
```

### Phase 3: PIPE Interface & External PHY (Completed)
- Task 3.1: ✅ PIPE interface abstraction (litepcie/dll/pipe.py)
- Task 3.2: ✅ External PIPE PHY wrapper (litepcie/phy/pipe_external_phy.py)
- Task 3.3: ✅ Integration tests with DLL (test/dll/integration/)

Phase 3 created the foundation for external PIPE PHY support:
- PIPE interface abstraction with TX idle behavior
- External PHY wrapper as drop-in replacement for vendor IP
- Integration tests verifying DLL-PIPE compatibility
- All tests passing, code quality standards met

### Phase 4: TX/RX Data Paths (Completed - 2025-10-17)
- Task 4.1: ✅ TX Packetizer basic structure
- Task 4.2: ✅ TX Packetizer START symbol generation (STP/SDP)
- Task 4.3: ✅ TX Packetizer data transmission (64-bit → 8-bit)
- Task 4.4: ✅ TX Packetizer END symbol generation
- Task 4.5: ✅ RX Depacketizer basic structure
- Task 4.6: ✅ RX Depacketizer START detection (STP/SDP)
- Task 4.7: ✅ RX Depacketizer data accumulation (8-bit → 64-bit)
- Task 4.8: ✅ RX Depacketizer END detection and packet output
- Task 4.9: ✅ Integration of TX/RX into PIPE interface
- Task 4.10: ✅ Loopback testing (TX → RX verification)
- Task 4.11: ✅ Full test suite validation (82/82 DLL tests passing)

Phase 4 implemented functional TX/RX data paths:
- TX: 64-bit DLL packets → 8-bit PIPE symbols with START/DATA/END framing
- RX: 8-bit PIPE symbols → 64-bit DLL packets with symbol detection
- Loopback: Complete end-to-end TX → RX verification
- Test coverage: 26 PIPE tests + 56 existing DLL tests, all passing (100% success rate)
- Code coverage: litepcie/dll/pipe.py at 99% (77 statements, 1 missed), overall DLL at 98%
- Code quality: TDD approach, comprehensive docstrings, PCIe spec references

### Phase 2: PIPE Interface (Archived - merged into Phase 3)
Create PIPE interface abstraction:

```python
# litepcie/dll/pipe.py
class PIPEInterface(Module):
    """Abstract PIPE interface (MAC side)"""
    def __init__(self, data_width=8, gen=1):
        # DLL-facing interface (phy_layout)
        self.dll_tx_sink   = stream.Endpoint(phy_layout(data_width))
        self.dll_tx_source = stream.Endpoint(phy_layout(data_width))

        # PIPE-facing interface (raw PIPE signals)
        self.pipe_tx_data    = Signal(8)
        self.pipe_tx_datak   = Signal()
        self.pipe_rx_data    = Signal(8)
        self.pipe_rx_datak   = Signal()
        # ... etc
```

### Phase 3: External PIPE PHY Wrapper
Simplest case: external chip handles PHY, we just connect PIPE signals:

```python
# litepcie/phy/pipe_phy.py
class PIPEPCIePHY(LiteXModule):
    """PHY wrapper for external PIPE chip"""
    def __init__(self, platform, pads, data_width=64, pipe_chip="TUSB1310A"):
        # Standard PHY interface (drop-in replacement)
        self.sink   = stream.Endpoint(phy_layout(data_width))
        self.source = stream.Endpoint(phy_layout(data_width))
        self.msi    = stream.Endpoint(msi_layout())

        # Internal: DLL + PIPE + external chip
        self.submodules.tx_datapath = PHYTXDatapath(...)
        self.submodules.rx_datapath = PHYRXDatapath(...)
        self.submodules.dll = DLL(data_width)
        self.submodules.pipe = PIPEInterface(...)
        self.submodules.external_phy = ExternalPIPEChip(chip=pipe_chip)

        # Connections
        self.comb += [
            self.sink.connect(self.tx_datapath.sink),
            self.tx_datapath.source.connect(self.dll.tx_sink),
            self.dll.tx_source.connect(self.pipe.dll_tx_sink),
            # ... etc
        ]
```

### Phase 4: Internal Transceiver Wrappers
More complex: wrap FPGA transceivers with PIPE interface:

```python
# litepcie/phy/xilinx_gtp_pipe.py
class XilinxGTPPIPEWrapper(Module):
    """Wraps Xilinx GTX with PIPE interface"""
    # Presents PIPE signals to PIPEInterface
    # Internally uses GTX primitives for SERDES

# litepcie/phy/ecp5_serdes_pipe.py
class ECP5SERDESPIPEWrapper(Module):
    """Wraps ECP5 SERDES with PIPE interface"""
    # Presents PIPE signals to PIPEInterface
    # Internally uses ECP5 SERDES primitives
```

Then use these in PHY wrappers:

```python
# litepcie/phy/ecp5_pipe_phy.py
class ECP5PIPEPCIePHY(LiteXModule):
    """Open source PHY for ECP5 (no vendor IP!)"""
    def __init__(self, platform, pads, data_width=64):
        # Standard PHY interface (drop-in replacement)
        self.sink   = stream.Endpoint(phy_layout(data_width))
        self.source = stream.Endpoint(phy_layout(data_width))
        # ... etc

        # Internal: DLL + PIPE + ECP5 SERDES wrapper
        self.submodules.dll = DLL(data_width)
        self.submodules.pipe = PIPEInterface(...)
        self.submodules.serdes = ECP5SERDESPIPEWrapper(...)
```

## Testing Strategy

### Unit Tests (Isolation)
Each layer tested independently:
- DLL tested with PIPE models
- PIPE tested with DLL models and PHY models
- PHY wrappers tested with real transceivers

### Integration Tests
Full stack tested together:
- TLP → DLL → PIPE → PHY (model)
- TLP → DLL → PIPE → External chip (hardware)
- TLP → DLL → PIPE → Internal transceiver (hardware)

### Drop-In Replacement Tests
Verify transparent swap:
1. Run test design with vendor IP
2. Swap to open source PHY (change import only)
3. Run same test
4. Verify identical behavior

## Success Criteria

Our custom PHY implementations will be considered successful when:

**Functional:**
- [ ] Implements all required PHY interface (sink, source, msi, CSRs)
- [ ] `LitePCIeEndpoint` works without modification
- [ ] TLPs transmitted and received correctly
- [ ] Link trains to L0 state
- [ ] MSI interrupts work

**Drop-In Replacement:**
- [ ] Can replace vendor IP by changing import only
- [ ] All existing LitePCIe designs work unchanged
- [ ] Same performance characteristics
- [ ] Same resource usage (or better)

**Open Source:**
- [ ] Builds with Yosys+nextpnr (ECP5)
- [ ] Builds with OpenXC7 (Xilinx 7-series)
- [ ] No vendor tools required
- [ ] No vendor IP dependencies

**Quality:**
- [ ] 100% test coverage (goal, 80% minimum)
- [ ] All tests pass in CI
- [ ] Code quality standards met
- [ ] Complete documentation

## References

### LitePCIe Source Files Analyzed

- **litepcie/core/endpoint.py:38-55**
  Connection between PHY and TLP layer

- **litepcie/phy/s7pciephy.py:22-39**
  PHY class structure, required endpoints and CSRs

- **litepcie/phy/common.py:14-128**
  PHYTXDatapath, PHYRXDatapath (we will reuse these)

- **litepcie/common.py:34-39**
  phy_layout() definition

### Related Documentation

- **PIPE Interface Specification:** `docs/pipe-interface-spec.md`
  Details of PIPE signals and protocol

- **PCIe Base Specification 4.0, Section 3:**
  Data Link Layer requirements

## Next Steps

1. ✅ Document integration strategy (this file)
2. ✅ Setup CI/CD test infrastructure
3. ✅ Define code quality standards
4. ✅ Implement DLL core independently
5. ✅ Create PIPE interface abstraction
6. ✅ Build external PIPE PHY wrapper
7. ⏳ Implement TX data path (DLL packets → PIPE symbols)
8. ⏳ Implement RX data path (PIPE symbols → DLL packets)
9. ⏳ Add ordered set handling (TS1, TS2, SKP, etc.)
10. ⏳ Test drop-in replacement with simple design
11. ⏳ Add internal transceiver wrappers (Xilinx GTX, ECP5 SERDES)

---

**Status:** Living document - will update as we implement and discover details.
