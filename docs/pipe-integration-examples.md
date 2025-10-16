# PIPE Interface Integration Examples

**Version:** 1.0
**Date:** 2025-10-17
**Status:** Complete

This document provides practical examples for integrating the LitePCIe PIPE interface into your designs.

---

## Table of Contents

1. [Example 1: Basic Loopback Testing](#example-1-basic-loopback-testing)
2. [Example 2: DLL Layer Integration](#example-2-dll-layer-integration)
3. [Example 3: External PHY Chip Integration](#example-3-external-phy-chip-integration)
4. [Example 4: Custom PHY Platform Support](#example-4-custom-phy-platform-support)
5. [Example 5: Testing with Simulation](#example-5-testing-with-simulation)
6. [Future: Multi-Lane Support](#future-multi-lane-support)

---

## Example 1: Basic Loopback Testing

The simplest integration is loopback mode, where TX signals are directly connected to RX signals. This is useful for:
- Testing PIPE interface functionality without external hardware
- Validating packet transmission/reception logic
- Debugging timing issues in simulation

### Complete Loopback Design

```python
from migen import *
from litex.gen import run_simulation
from litepcie.dll.pipe import PIPEInterface

class PIPELoopbackDesign(Module):
    """
    Simple PIPE loopback for testing.

    Data flows: DLL TX → PIPE TX → (loopback) → PIPE RX → DLL RX
    """
    def __init__(self, data_width=8, gen=1):
        # Create PIPE interface
        self.submodules.pipe = pipe = PIPEInterface(
            data_width=data_width,
            gen=gen
        )

        # Loopback connection: Connect TX directly to RX
        self.comb += [
            pipe.pipe_rx_data.eq(pipe.pipe_tx_data),
            pipe.pipe_rx_datak.eq(pipe.pipe_tx_datak),
            # Optionally connect status signals
            pipe.pipe_rx_valid.eq(1),  # Always valid in loopback
            pipe.pipe_rx_status.eq(0), # No errors
        ]

    def send_packet(self, data):
        """Helper to send a packet through loopback."""
        # Set TX input
        yield self.pipe.dll_tx_sink.valid.eq(1)
        yield self.pipe.dll_tx_sink.first.eq(1)
        yield self.pipe.dll_tx_sink.last.eq(1)
        yield self.pipe.dll_tx_sink.dat.eq(data)
        yield

        # Clear TX input
        yield self.pipe.dll_tx_sink.valid.eq(0)
        yield

        # Wait for TX→RX propagation
        # START(1) + DATA(8) + END(1) = 10 cycles minimum
        for _ in range(10):
            yield

        # Read RX output
        rx_valid = yield self.pipe.dll_rx_source.valid
        rx_data = yield self.pipe.dll_rx_source.dat

        return rx_valid, rx_data

# Usage Example
if __name__ == "__main__":
    def testbench(dut):
        # Test packet data
        test_data = 0x0123456789ABCDEF

        # Send packet
        rx_valid, rx_data = yield from dut.send_packet(test_data)

        # Verify
        print(f"TX Data: 0x{test_data:016X}")
        print(f"RX Data: 0x{rx_data:016X}")
        print(f"Valid:   {rx_valid}")

        assert rx_valid == 1, "RX should be valid"
        assert rx_data == test_data, f"Data mismatch!"
        print("✓ Loopback test passed!")

    dut = PIPELoopbackDesign()
    run_simulation(dut, testbench(dut), vcd_name="loopback.vcd")
```

### Running the Example

```bash
# Save as examples/pipe_loopback.py
python examples/pipe_loopback.py

# View waveforms
gtkwave loopback.vcd
```

### What to Monitor in VCD

Key signals to observe:
- `pipe.dll_tx_sink.dat` - Input data
- `pipe.pipe_tx_data` - TX symbol stream (10 symbols total)
- `pipe.pipe_tx_datak` - K-character indicators (START and END)
- `pipe.pipe_rx_data` - RX symbol stream (same as TX in loopback)
- `pipe.dll_rx_source.dat` - Output data (should match input)

---

## Example 2: DLL Layer Integration

Connecting the PIPE interface to a full DLL (Data Link Layer) for ACK/NAK protocol, retry buffer, and LCRC.

### Complete DLL + PIPE Integration

```python
from migen import *
from litepcie.dll.pipe import PIPEInterface
from litepcie.dll.tx import DLLTX
from litepcie.dll.rx import DLLRX
from litepcie.common import *

class PCIeDLLWithPIPE(Module):
    """
    Complete DLL + PIPE integration.

    Architecture:
      TLP Layer → DLLTX → PIPE TX → PHY
                            ↓ (loopback)
      TLP Layer ← DLLRX ← PIPE RX ← PHY
    """
    def __init__(self, data_width=64):
        # TLP layer endpoints (connect to your TLP logic)
        self.tlp_tx_sink = stream.Endpoint([("data", data_width)])
        self.tlp_rx_source = stream.Endpoint([("data", data_width)])

        # # #

        # DLL TX: Add sequence numbers, LCRC, send DLLPs
        self.submodules.dll_tx = DLLTX(data_width=data_width)

        # DLL RX: Check LCRC, send ACKs/NAKs, reorder packets
        self.submodules.dll_rx = DLLRX(data_width=data_width)

        # PIPE interface: Convert DLL packets ↔ PIPE symbols
        self.submodules.pipe = PIPEInterface(data_width=8, gen=1)

        # Connect TLP → DLL TX
        self.comb += self.tlp_tx_sink.connect(self.dll_tx.tlp_sink)

        # Connect DLL TX → PIPE TX
        # Note: Requires layout conversion between DLL and PIPE formats
        self.comb += self.dll_tx.phy_source.connect(self.pipe.dll_tx_sink)

        # Connect PIPE RX → DLL RX
        self.comb += self.pipe.dll_rx_source.connect(self.dll_rx.phy_sink)

        # Connect DLL RX → TLP
        self.comb += self.dll_rx.tlp_source.connect(self.tlp_rx_source)

        # Loopback for testing (remove when connecting to real PHY)
        self.comb += [
            self.pipe.pipe_rx_data.eq(self.pipe.pipe_tx_data),
            self.pipe.pipe_rx_datak.eq(self.pipe.pipe_tx_datak),
            self.pipe.pipe_rx_valid.eq(1),
            self.pipe.pipe_rx_status.eq(0),
        ]

# Usage
def create_pcie_with_dll():
    dut = PCIeDLLWithPIPE(data_width=64)
    # Now connect your TLP layer to dut.tlp_tx_sink and dut.tlp_rx_source
    return dut
```

### Layout Conversion Notes

The DLL layer uses `[("data", 64)]` layout, while PIPE uses `phy_layout(64)` which includes `("dat", 64)` and `("be", 8)`. You may need a layout converter:

```python
from litex.soc.interconnect.stream import StrideConverter

# Convert DLL format to PIPE format
dll_to_pipe = StrideConverter(
    [("data", 64)],           # DLL format
    phy_layout(64),           # PIPE format (dat, be)
    reverse=False
)

# Connect with converter
self.submodules.dll_to_pipe = dll_to_pipe
self.comb += [
    self.dll_tx.phy_source.connect(dll_to_pipe.sink),
    dll_to_pipe.source.connect(self.pipe.dll_tx_sink),
]
```

---

## Example 3: External PHY Chip Integration

Integrating with an external PIPE PHY chip like TI TUSB1310A or similar.

### Platform PIPE Pads Definition

First, define the PIPE signals in your platform file:

```python
# platform.py
from litex.build.generic_platform import *

# PIPE PHY pads for external chip (e.g., TUSB1310A)
_pipe_phy_io = [
    # TX Interface (FPGA → PHY)
    ("pipe_tx", 0,
        Subsignal("data",     Pins("A1 A2 A3 A4 A5 A6 A7 A8"), IOStandard("LVCMOS33")),
        Subsignal("datak",    Pins("A9"), IOStandard("LVCMOS33")),
        Subsignal("elecidle", Pins("A10"), IOStandard("LVCMOS33")),
    ),

    # RX Interface (PHY → FPGA)
    ("pipe_rx", 0,
        Subsignal("data",     Pins("B1 B2 B3 B4 B5 B6 B7 B8"), IOStandard("LVCMOS33")),
        Subsignal("datak",    Pins("B9"), IOStandard("LVCMOS33")),
        Subsignal("valid",    Pins("B10"), IOStandard("LVCMOS33")),
        Subsignal("status",   Pins("B11 B12 B13"), IOStandard("LVCMOS33")),
        Subsignal("elecidle", Pins("B14"), IOStandard("LVCMOS33")),
    ),

    # Control Interface
    ("pipe_ctrl", 0,
        Subsignal("powerdown",   Pins("C1 C2"), IOStandard("LVCMOS33")),
        Subsignal("rate",        Pins("C3"), IOStandard("LVCMOS33")),
        Subsignal("rx_polarity", Pins("C4"), IOStandard("LVCMOS33")),
    ),

    # Clock from PHY (PCLK - 125 MHz for Gen1)
    ("pcie_clk", 0, Pins("D1"), IOStandard("LVCMOS33")),
]

class MyPlatform(XilinxPlatform):
    def __init__(self):
        # ... platform initialization
        self.add_extension(_pipe_phy_io)
```

### Complete External PHY Design

```python
from migen import *
from litepcie.dll.pipe import PIPEInterface

class PCIeWithExternalPHY(Module):
    """
    PCIe design using external PIPE PHY chip.

    External chip handles:
    - 8b/10b encoding/decoding
    - Physical layer (SerDes, electrical signaling)
    - Ordered sets (SKP, COM, TS1, TS2)

    FPGA handles:
    - DLL layer (ACK/NAK, retry buffer, LCRC)
    - TLP layer (routing, flow control)
    - Application logic
    """
    def __init__(self, platform):
        # Request PIPE pads from platform
        pipe_tx_pads = platform.request("pipe_tx")
        pipe_rx_pads = platform.request("pipe_rx")
        pipe_ctrl_pads = platform.request("pipe_ctrl")
        pcie_clk = platform.request("pcie_clk")

        # Create "pcie" clock domain driven by PHY PCLK
        self.clock_domains.cd_pcie = ClockDomain()
        self.comb += self.cd_pcie.clk.eq(pcie_clk)

        # Create PIPE interface in "pcie" clock domain
        self.submodules.pipe = ClockDomainsRenamer("pcie")(
            PIPEInterface(data_width=8, gen=1)
        )

        # Connect PIPE → External PHY Chip
        self.comb += [
            # TX signals (FPGA → PHY)
            pipe_tx_pads.data.eq(self.pipe.pipe_tx_data),
            pipe_tx_pads.datak.eq(self.pipe.pipe_tx_datak),
            pipe_tx_pads.elecidle.eq(self.pipe.pipe_tx_elecidle),

            # RX signals (PHY → FPGA)
            self.pipe.pipe_rx_data.eq(pipe_rx_pads.data),
            self.pipe.pipe_rx_datak.eq(pipe_rx_pads.datak),
            self.pipe.pipe_rx_valid.eq(pipe_rx_pads.valid),
            self.pipe.pipe_rx_status.eq(pipe_rx_pads.status),
            self.pipe.pipe_rx_elecidle.eq(pipe_rx_pads.elecidle),

            # Control signals (FPGA → PHY)
            pipe_ctrl_pads.powerdown.eq(self.pipe.pipe_powerdown),
            pipe_ctrl_pads.rate.eq(self.pipe.pipe_rate),
            pipe_ctrl_pads.rx_polarity.eq(self.pipe.pipe_rx_polarity),
        ]

        # Now connect DLL layer to self.pipe.dll_tx_sink / dll_rx_source
        # (See Example 2 for DLL integration)

# Usage in SoC
class MySoC(SoCCore):
    def __init__(self, platform):
        SoCCore.__init__(self, platform, ...)

        # Add PCIe with external PHY
        self.submodules.pcie = PCIeWithExternalPHY(platform)

        # Connect to application logic
        # self.submodules.dma = LitePCIeDMA(...)
        # self.comb += self.pcie.pipe.dll_tx_sink.connect(...)
```

### External PHY Chip Configuration

Some external PHY chips require configuration via I2C or SPI. Example for TUSB1310A:

```python
# I2C configuration for TUSB1310A (example)
def configure_tusb1310a(platform):
    """Configure TUSB1310A PHY via I2C."""
    i2c = platform.request("i2c")

    # TUSB1310A I2C address: 0x58
    # Configuration registers (refer to TUSB1310A datasheet):
    # - 0x00: Device ID (read-only)
    # - 0x01: Configuration register
    #   - Bit 0: PIPE mode enable
    #   - Bit 1: Gen1/Gen2 speed
    #   - Bit 2: Power state

    # Example configuration sequence (pseudocode)
    i2c_write(i2c, addr=0x58, reg=0x01, data=0x01)  # Enable PIPE mode
    i2c_write(i2c, addr=0x58, reg=0x02, data=0x00)  # Gen1 speed
```

---

## Example 4: Custom PHY Platform Support

Adding PIPE PHY support for a new FPGA platform or custom PHY chip.

### Custom Platform Integration

```python
from migen import *
from litex.build.generic_platform import *
from litepcie.dll.pipe import PIPEInterface

class CustomPIPEPlatform:
    """
    Platform-specific PIPE PHY integration.

    Use this template to add PIPE support for your platform.
    """
    @staticmethod
    def add_pipe_support(platform, pipe_interface):
        """
        Connect PIPE interface to platform-specific PHY.

        Parameters
        ----------
        platform : Platform
            LiteX platform
        pipe_interface : PIPEInterface
            PIPE interface instance to connect

        Returns
        -------
        dict
            Platform-specific resources (clocks, resets, etc.)
        """
        # 1. Request platform pads
        pipe_tx = platform.request("pipe_tx")
        pipe_rx = platform.request("pipe_rx")
        pipe_ctrl = platform.request("pipe_ctrl")
        pcie_clk = platform.request("pcie_clk")

        # 2. Create clock domain
        cd_pcie = ClockDomain()
        platform.add_clock_constraint(pcie_clk, 125e6)  # Gen1: 125 MHz

        # 3. Connect signals
        connections = [
            # TX
            pipe_tx.data.eq(pipe_interface.pipe_tx_data),
            pipe_tx.datak.eq(pipe_interface.pipe_tx_datak),
            pipe_tx.elecidle.eq(pipe_interface.pipe_tx_elecidle),

            # RX
            pipe_interface.pipe_rx_data.eq(pipe_rx.data),
            pipe_interface.pipe_rx_datak.eq(pipe_rx.datak),
            pipe_interface.pipe_rx_valid.eq(pipe_rx.valid),
            pipe_interface.pipe_rx_status.eq(pipe_rx.status),
            pipe_interface.pipe_rx_elecidle.eq(pipe_rx.elecidle),

            # Control
            pipe_ctrl.powerdown.eq(pipe_interface.pipe_powerdown),
            pipe_ctrl.rate.eq(pipe_interface.pipe_rate),
            pipe_ctrl.rx_polarity.eq(pipe_interface.pipe_rx_polarity),
        ]

        return {
            "connections": connections,
            "clk": pcie_clk,
            "cd": cd_pcie,
        }

# Usage
class MyCustomPCIeDesign(Module):
    def __init__(self, platform):
        self.submodules.pipe = PIPEInterface(data_width=8, gen=1)

        # Add platform-specific connections
        platform_resources = CustomPIPEPlatform.add_pipe_support(
            platform, self.pipe
        )

        self.comb += platform_resources["connections"]
        self.clock_domains += platform_resources["cd"]
```

### Supporting Different PHY Chips

Different PIPE PHY chips may have variations. Create chip-specific wrappers:

```python
class TI_TUSB1310A_PHY:
    """TI TUSB1310A PIPE PHY chip support."""
    CHIP_ID = 0x1310A
    I2C_ADDR = 0x58
    SUPPORTS_GEN1 = True
    SUPPORTS_GEN2 = True

    @staticmethod
    def connect(platform, pipe_interface):
        # TI-specific connection logic
        pass

class Pericom_PI7C9X2G404_PHY:
    """Pericom PI7C9X2G404 PIPE PHY chip support."""
    CHIP_ID = 0x2G404
    CONFIG_VIA_JTAG = True
    SUPPORTS_GEN1 = True
    SUPPORTS_GEN2 = False

    @staticmethod
    def connect(platform, pipe_interface):
        # Pericom-specific connection logic
        pass

# Factory function
def create_pipe_phy(platform, chip_name):
    """Create PIPE PHY for specified chip."""
    chips = {
        "TUSB1310A": TI_TUSB1310A_PHY,
        "PI7C9X2G404": Pericom_PI7C9X2G404_PHY,
    }

    if chip_name not in chips:
        raise ValueError(f"Unsupported chip: {chip_name}")

    return chips[chip_name]
```

---

## Example 5: Testing with Simulation

Comprehensive simulation testing with realistic scenarios.

### Multi-Packet Simulation Test

```python
from migen import *
from litex.gen import run_simulation
from litepcie.dll.pipe import PIPEInterface

class PIPEMultiPacketTest(Module):
    """Test multiple packets through PIPE interface."""
    def __init__(self):
        self.submodules.pipe = PIPEInterface(data_width=8, gen=1)

        # Loopback
        self.comb += [
            self.pipe.pipe_rx_data.eq(self.pipe.pipe_tx_data),
            self.pipe.pipe_rx_datak.eq(self.pipe.pipe_tx_datak),
            self.pipe.pipe_rx_valid.eq(1),
        ]

def multi_packet_testbench(dut):
    """Send multiple packets with gaps between them."""
    test_packets = [
        0x0123456789ABCDEF,
        0xFEDCBA9876543210,
        0xAAAAAAAAAAAAAAAA,
        0x5555555555555555,
    ]

    received_packets = []

    for i, test_data in enumerate(test_packets):
        print(f"\n=== Packet {i+1} ===")

        # Send packet
        yield dut.pipe.dll_tx_sink.valid.eq(1)
        yield dut.pipe.dll_tx_sink.first.eq(1)
        yield dut.pipe.dll_tx_sink.last.eq(1)
        yield dut.pipe.dll_tx_sink.dat.eq(test_data)
        yield

        # Clear TX
        yield dut.pipe.dll_tx_sink.valid.eq(0)
        yield

        # Wait for TX→RX propagation
        for _ in range(10):
            yield

        # Read RX
        rx_valid = yield dut.pipe.dll_rx_source.valid
        rx_data = yield dut.pipe.dll_rx_source.dat

        if rx_valid:
            print(f"TX: 0x{test_data:016X}")
            print(f"RX: 0x{rx_data:016X}")
            received_packets.append(rx_data)

            assert rx_data == test_data, "Data mismatch!"
            print("✓ Match!")

        # Gap between packets (simulate realistic spacing)
        for _ in range(5):
            yield

    # Verify all packets received
    assert len(received_packets) == len(test_packets)
    print(f"\n✓ All {len(test_packets)} packets received correctly!")

# Run simulation
dut = PIPEMultiPacketTest()
run_simulation(
    dut,
    multi_packet_testbench(dut),
    vcd_name="multi_packet_test.vcd",
    clocks={"sys": 10}  # 100 MHz system clock
)
```

### Back-to-Back Packets Test

```python
def back_to_back_testbench(dut):
    """Test back-to-back packets without gaps."""
    test_packets = [
        0x1111111111111111,
        0x2222222222222222,
        0x3333333333333333,
    ]

    # Send all packets back-to-back
    for test_data in test_packets:
        yield dut.pipe.dll_tx_sink.valid.eq(1)
        yield dut.pipe.dll_tx_sink.first.eq(1)
        yield dut.pipe.dll_tx_sink.last.eq(1)
        yield dut.pipe.dll_tx_sink.dat.eq(test_data)
        yield

    # Clear TX
    yield dut.pipe.dll_tx_sink.valid.eq(0)

    # Wait for all packets to complete
    # Each packet: START(1) + DATA(8) + END(1) = 10 cycles
    # Total: 3 packets × 10 cycles = 30 cycles
    for _ in range(35):
        yield

        rx_valid = yield dut.pipe.dll_rx_source.valid
        if rx_valid:
            rx_data = yield dut.pipe.dll_rx_source.dat
            print(f"Received: 0x{rx_data:016X}")

# Run
dut = PIPEMultiPacketTest()
run_simulation(dut, back_to_back_testbench(dut), vcd_name="back_to_back.vcd")
```

---

## Future: Multi-Lane Support

Multi-lane PIPE support (x4, x8, x16) is planned for future releases. Here's the anticipated architecture:

### Multi-Lane Architecture (Future)

```python
# FUTURE: Not yet implemented
class PIPEInterfaceMultiLane(Module):
    """
    Multi-lane PIPE interface (x4, x8, x16).

    Each lane has independent PIPE signals but coordinated framing.
    """
    def __init__(self, num_lanes=4, data_width=8, gen=1):
        # num_lanes: 1, 4, 8, or 16
        assert num_lanes in [1, 4, 8, 16]

        # Create per-lane PIPE interfaces
        self.lanes = []
        for i in range(num_lanes):
            lane = PIPEInterface(data_width=data_width, gen=gen)
            setattr(self, f"lane{i}", lane)
            self.lanes.append(lane)

        # Lane bonding and alignment logic
        # - Coordinate START/END symbols across lanes
        # - Handle lane-to-lane skew
        # - Implement elastic buffer for clock compensation

        # Combined DLL interface
        # - Wider data width (64 × num_lanes bits)
        self.dll_tx_sink = stream.Endpoint(phy_layout(64 * num_lanes))
        self.dll_rx_source = stream.Endpoint(phy_layout(64 * num_lanes))

        # TODO: Implement lane distribution and aggregation
```

### Multi-Lane Platform Definition (Future)

```python
# FUTURE: Example platform definition for x4 link
_pipe_phy_x4_io = [
    # Lane 0
    ("pipe_tx", 0, Subsignal("data", Pins("A1:A8")), ...),
    ("pipe_rx", 0, Subsignal("data", Pins("B1:B8")), ...),

    # Lane 1
    ("pipe_tx", 1, Subsignal("data", Pins("C1:C8")), ...),
    ("pipe_rx", 1, Subsignal("data", Pins("D1:D8")), ...),

    # Lane 2
    ("pipe_tx", 2, Subsignal("data", Pins("E1:E8")), ...),
    ("pipe_rx", 2, Subsignal("data", Pins("F1:F8")), ...),

    # Lane 3
    ("pipe_tx", 3, Subsignal("data", Pins("G1:G8")), ...),
    ("pipe_rx", 3, Subsignal("data", Pins("H1:H8")), ...),
]
```

---

## Summary

### Integration Checklist

When integrating PIPE interface into your design:

- [ ] **Choose integration mode:**
  - Loopback (testing only)
  - With DLL layer (full protocol support)
  - External PHY chip (production)

- [ ] **Define platform pads:**
  - TX signals (data, datak, elecidle)
  - RX signals (data, datak, valid, status, elecidle)
  - Control signals (powerdown, rate, rx_polarity)
  - PCLK input (125 MHz for Gen1)

- [ ] **Clock domain management:**
  - Create "pcie" clock domain from PCLK
  - Use ClockDomainsRenamer for PIPE components
  - Add CDC (Clock Domain Crossing) to/from core logic

- [ ] **Connect DLL layer:**
  - TX path: TLP → DLLTX → PIPE TX
  - RX path: PIPE RX → DLLRX → TLP
  - Handle layout conversions

- [ ] **Test in simulation:**
  - Single packet loopback
  - Multiple packets with gaps
  - Back-to-back packets
  - Verify timing in VCD

- [ ] **Hardware validation:**
  - Check signal integrity (oscilloscope)
  - Verify PCLK frequency and phase
  - Test link training (if applicable)
  - Measure throughput and latency

---

## References

- **docs/pipe-interface-guide.md** - Complete API reference and user guide
- **docs/pipe-architecture.md** - Detailed architecture diagrams
- **Intel PIPE 3.0 Specification** - Official PIPE protocol specification
- **test/dll/test_pipe_loopback.py** - Loopback test implementation
- **litepcie/phy/pipe_external_phy.py** - External PHY wrapper (work in progress)

---

## Version History

- **1.0 (2025-10-17):** Initial release with loopback, DLL integration, and external PHY examples
