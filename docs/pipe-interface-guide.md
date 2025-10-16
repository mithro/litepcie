# PIPE Interface User Guide

**Version:** 1.0
**Date:** 2025-10-17
**Status:** Complete

---

## Table of Contents

1. [Introduction](#introduction)
2. [Quick Start](#quick-start)
3. [Architecture Overview](#architecture-overview)
4. [API Reference](#api-reference)
5. [Examples](#examples)
6. [Troubleshooting](#troubleshooting)

---

## Introduction

### What is the PIPE Interface?

PIPE (PHY Interface for PCI Express) is a standardized 8-bit interface between the MAC (Media Access Control) and PHY (Physical Layer) in PCIe implementations. The PIPE interface abstracts away low-level PHY details like 8b/10b encoding, SerDes operation, and physical signaling, allowing you to:

- Use external PIPE PHY chips (e.g., TI TUSB1310A)
- Integrate internal transceivers with PIPE protocol
- Test PCIe designs without physical hardware

**Reference:** Intel PIPE 3.0 Specification

### When to Use It

Use the LitePCIe PIPE interface when:

- **External PHY Integration:** You have an external PIPE PHY chip to handle the physical layer
- **Multi-vendor Support:** You want to support different PHY implementations
- **Testing:** You need to test DLL functionality without physical hardware (loopback mode)
- **Prototyping:** You're developing PCIe designs on FPGAs without built-in PCIe hard blocks

### Supported Features

**Current Implementation:**
- 8-bit PIPE mode (PIPE 3.0)
- Gen1 (2.5 GT/s) and Gen2 (5.0 GT/s) speeds
- TLP (Transaction Layer Packet) and DLLP (Data Link Layer Packet) framing
- TX packetization: 64-bit DLL packets → 8-bit PIPE symbols
- RX depacketization: 8-bit PIPE symbols → 64-bit DLL packets
- K-character framing (STP, SDP, END)
- Electrical idle signaling
- Power management controls

**Future Enhancements:**
- Multi-lane support (x4, x8, x16)
- Error injection (EDB - End Bad packet)
- Advanced power states
- Link training integration

---

## Quick Start

### Minimal Working Example

```python
from migen import *
from litepcie.dll.pipe import PIPEInterface

class PIPELoopbackDesign(Module):
    def __init__(self):
        # Create PIPE interface (Gen1, 8-bit)
        self.submodules.pipe = pipe = PIPEInterface(data_width=8, gen=1)

        # Loopback: Connect TX to RX for testing
        self.comb += [
            pipe.pipe_rx_data.eq(pipe.pipe_tx_data),
            pipe.pipe_rx_datak.eq(pipe.pipe_tx_datak),
        ]

        # Now you can send packets through pipe.dll_tx_sink
        # and receive them from pipe.dll_rx_source
```

### Basic Usage Pattern

```python
# 1. Create PIPE interface
pipe = PIPEInterface(data_width=8, gen=1)

# 2. Connect DLL layer (if you have one)
self.comb += dll.tx_source.connect(pipe.dll_tx_sink)
self.comb += pipe.dll_rx_source.connect(dll.rx_sink)

# 3. Connect to PHY (external chip or loopback)
self.comb += [
    # TX direction (MAC → PHY)
    phy_pads.tx_data.eq(pipe.pipe_tx_data),
    phy_pads.tx_datak.eq(pipe.pipe_tx_datak),
    phy_pads.tx_elecidle.eq(pipe.pipe_tx_elecidle),

    # RX direction (PHY → MAC)
    pipe.pipe_rx_data.eq(phy_pads.rx_data),
    pipe.pipe_rx_datak.eq(phy_pads.rx_datak),
    pipe.pipe_rx_valid.eq(phy_pads.rx_valid),
]
```

### Common Pitfalls

**1. Wrong Data Width**
```python
# ❌ WRONG: Only 8-bit mode supported
pipe = PIPEInterface(data_width=16, gen=1)  # Will raise ValueError

# ✅ CORRECT: Use 8-bit mode
pipe = PIPEInterface(data_width=8, gen=1)
```

**2. Forgetting Stream Control Signals**
```python
# ❌ WRONG: Only setting dat, missing valid/first/last
yield pipe.dll_tx_sink.dat.eq(0x123456789ABCDEF)
yield

# ✅ CORRECT: Set all stream control signals
yield pipe.dll_tx_sink.valid.eq(1)
yield pipe.dll_tx_sink.first.eq(1)
yield pipe.dll_tx_sink.last.eq(1)
yield pipe.dll_tx_sink.dat.eq(0x0123456789ABCDEF)
yield
```

**3. Not Waiting for RX Processing**
```python
# ❌ WRONG: Checking RX immediately
yield pipe.dll_tx_sink.valid.eq(1)
yield
rx_data = yield pipe.dll_rx_source.dat  # Too early!

# ✅ CORRECT: Wait for TX→RX propagation (10+ cycles)
yield pipe.dll_tx_sink.valid.eq(1)
yield
yield pipe.dll_tx_sink.valid.eq(0)
for _ in range(10):  # START(1) + DATA(8) + END(1)
    yield
rx_data = yield pipe.dll_rx_source.dat  # Now valid
```

---

## Architecture Overview

### PCIe Stack Position

```
┌─────────────────────┐
│   Transaction Layer │ (TLP formation)
│      (TL)           │
└──────────┬──────────┘
           │ TLP packets
┌──────────▼──────────┐
│  Data Link Layer    │ (ACK/NAK, LCRC, Retry)
│      (DLL)          │
└──────────┬──────────┘
           │ 64-bit DLL packets
┌──────────▼──────────┐
│  PIPE Interface     │ ← THIS MODULE
│  (TX Packetizer +   │   (Framing, 8b/10b prep)
│   RX Depacketizer)  │
└──────────┬──────────┘
           │ 8-bit PIPE symbols
┌──────────▼──────────┐
│   Physical Layer    │ (8b/10b, SerDes, Link)
│      (PHY)          │
└─────────────────────┘
```

### TX Path: DLL Packets → PIPE Symbols

The TX packetizer converts 64-bit DLL packets into 8-bit PIPE symbols with K-character framing:

```
64-bit DLL Packet (0x0123456789ABCDEF)
           │
           ▼
┌──────────────────────┐
│  PIPETXPacketizer    │
│  ┌────────────────┐  │
│  │ IDLE State     │──┐ No packet: output idle
│  └────────────────┘  │
│           │           │
│  ┌────────▼────────┐ │
│  │ Detect Packet   │ │ valid & first
│  │ Type (TLP/DLLP) │ │
│  └────────┬────────┘ │
│           ▼           │
│  ┌────────────────┐  │
│  │ START State    │  │ Send STP (0xFB, K=1) or
│  │                │  │      SDP (0x5C, K=1)
│  └────────┬───────┘  │
│           ▼           │
│  ┌────────────────┐  │
│  │ DATA State     │  │ Send 8 bytes:
│  │  (8 cycles)    │  │  EF CD AB 89 67 45 23 01
│  │                │  │  (K=0 for all)
│  └────────┬───────┘  │
│           ▼           │
│  ┌────────────────┐  │
│  │ END State      │  │ Send END (0xFD, K=1)
│  └────────┬───────┘  │
│           ▼           │
│  ┌────────────────┐  │
│  │ IDLE State     │◄─┘
│  └────────────────┘  │
└──────────────────────┘
           │
           ▼
PIPE Symbol Stream (10 symbols total):
  FB(K) EF CD AB 89 67 45 23 01 FD(K)
  STP   ←─── 8 data bytes ────→  END
```

**Key Points:**
- **Little-endian byte ordering:** Byte 0 (0xEF) sent first, Byte 7 (0x01) sent last
- **K-character framing:** STP/SDP marks start, END marks completion
- **Packet type detection:** DLLP if first byte bits[7:6] == 0b00, else TLP
- **Timing:** 10 cycles per packet (START + 8 DATA + END)

### RX Path: PIPE Symbols → DLL Packets

The RX depacketizer converts 8-bit PIPE symbols back into 64-bit DLL packets:

```
PIPE Symbol Stream
  FB(K) EF CD AB 89 67 45 23 01 FD(K)
           │
           ▼
┌──────────────────────┐
│  PIPERXDepacketizer  │
│  ┌────────────────┐  │
│  │ IDLE State     │──┐ Wait for START K-char
│  └────────┬───────┘  │
│           ▼           │
│  ┌────────────────┐  │
│  │ Detect START   │  │ STP (0xFB) or SDP (0x5C)
│  │ (STP or SDP)   │  │ with K=1
│  └────────┬───────┘  │
│           ▼           │
│  ┌────────────────┐  │
│  │ DATA State     │  │ Accumulate 8 bytes:
│  │                │  │   [7:0]   ← EF (byte 0)
│  │  Accumulate    │  │   [15:8]  ← CD (byte 1)
│  │  64-bit buffer │  │   ...
│  │                │  │   [63:56] ← 01 (byte 7)
│  └────────┬───────┘  │
│           ▼           │
│  ┌────────────────┐  │
│  │ Detect END     │  │ END (0xFD, K=1)
│  │ Output Packet  │  │
│  └────────┬───────┘  │
│           ▼           │
│  ┌────────────────┐  │
│  │ IDLE State     │◄─┘
│  └────────────────┘  │
└──────────────────────┘
           │
           ▼
64-bit DLL Packet: 0x0123456789ABCDEF
  (valid=1, first=1, last=1)
```

**Key Points:**
- **START detection:** Looks for STP (TLP) or SDP (DLLP) with K=1
- **Data accumulation:** Stores bytes in little-endian order [0:8], [8:16], ..., [56:64]
- **END detection:** When END symbol (K=1) detected, outputs complete packet
- **Stream signals:** Sets valid=1, first=1, last=1 when outputting packet

### Integration Points

The PIPEInterface module integrates TX and RX paths:

```
      DLL Layer (packet-based)
           │
           ▼
    ┌──────────────────────┐
    │  dll_tx_sink         │ (input)
    │  (64-bit packets)    │
    └──────────┬───────────┘
               │
    ┌──────────▼───────────┐
    │  PIPETXPacketizer    │
    └──────────┬───────────┘
               │ pipe_tx_data (8-bit)
               │ pipe_tx_datak (1-bit)
    ───────────┴───────────────► PHY

    ◄──────────┬───────────────── PHY
               │ pipe_rx_data (8-bit)
               │ pipe_rx_datak (1-bit)
    ┌──────────▼───────────┐
    │  PIPERXDepacketizer  │
    └──────────┬───────────┘
               │
    ┌──────────▼───────────┐
    │  dll_rx_source       │ (output)
    │  (64-bit packets)    │
    └──────────────────────┘
           │
           ▼
      DLL Layer (packet-based)
```

---

## API Reference

### PIPEInterface

**Class:** `litepcie.dll.pipe.PIPEInterface`

Top-level PIPE interface providing abstraction between DLL and PHY.

#### Constructor

```python
PIPEInterface(data_width=8, gen=1)
```

**Parameters:**
- `data_width` (int): PIPE data width. Must be 8 (only 8-bit mode supported)
- `gen` (int): PCIe generation. Must be 1 (Gen1/2.5GT/s) or 2 (Gen2/5.0GT/s)

**Raises:**
- `ValueError`: If data_width != 8 or gen not in [1, 2]

#### DLL-Facing Signals

**TX Input (DLL → PIPE):**
- `dll_tx_sink` (Endpoint): Stream endpoint for DLL packets to transmit
  - `dll_tx_sink.valid` (1-bit): Packet valid
  - `dll_tx_sink.first` (1-bit): First beat of packet
  - `dll_tx_sink.last` (1-bit): Last beat of packet
  - `dll_tx_sink.dat` (64-bit): Packet data

**RX Output (PIPE → DLL):**
- `dll_rx_source` (Endpoint): Stream endpoint for received DLL packets
  - `dll_rx_source.valid` (1-bit): Packet valid
  - `dll_rx_source.first` (1-bit): First beat of packet
  - `dll_rx_source.last` (1-bit): Last beat of packet
  - `dll_rx_source.dat` (64-bit): Packet data

#### PIPE-Facing Signals

**TX Output (MAC → PHY):**
- `pipe_tx_data` (8-bit): PIPE TX data symbol
- `pipe_tx_datak` (1-bit): K-character indicator (1=K-char, 0=data)
- `pipe_tx_elecidle` (1-bit): Electrical idle request (1=idle, 0=active)

**RX Input (PHY → MAC):**
- `pipe_rx_data` (8-bit): PIPE RX data symbol
- `pipe_rx_datak` (1-bit): K-character indicator (1=K-char, 0=data)
- `pipe_rx_valid` (1-bit): RX data valid
- `pipe_rx_status` (3-bit): RX status code (see PIPE_RXSTATUS_* constants)
- `pipe_rx_elecidle` (1-bit): Electrical idle detected (1=idle, 0=active)

**Control Signals:**
- `pipe_powerdown` (2-bit): Power state (P0=0b00, P0s=0b01, P1=0b10, P2=0b11)
- `pipe_rate` (1-bit): Speed selection (Gen1=0, Gen2=1)
- `pipe_rx_polarity` (1-bit): RX polarity inversion (0=normal, 1=inverted)

#### Submodules

- `tx_packetizer` (PIPETXPacketizer): TX path component
- `rx_depacketizer` (PIPERXDepacketizer): RX path component

---

### PIPETXPacketizer

**Class:** `litepcie.dll.pipe.PIPETXPacketizer`

Converts 64-bit DLL packets to 8-bit PIPE symbols with K-character framing.

#### Constructor

```python
PIPETXPacketizer()
```

No parameters required.

#### Signals

**Input:**
- `sink` (Endpoint): DLL packet input
  - `sink.valid` (1-bit): Packet valid
  - `sink.first` (1-bit): First beat
  - `sink.last` (1-bit): Last beat
  - `sink.dat` (64-bit): Packet data

**Output:**
- `pipe_tx_data` (8-bit): PIPE TX data symbol
- `pipe_tx_datak` (1-bit): K-character indicator

#### Behavior

**Packet Type Detection:**
- **DLLP:** First byte bits[7:6] == 0b00 → Send SDP (0x5C, K=1)
- **TLP:** Otherwise → Send STP (0xFB, K=1)

**Symbol Sequence:**
1. **START:** STP or SDP with K=1
2. **DATA:** 8 bytes from sink.dat, LSB-first, K=0
3. **END:** END symbol (0xFD, K=1)

**FSM States:**
- **IDLE:** Wait for valid packet (sink.valid & sink.first)
- **DATA:** Transmit 8 data bytes (counter 0-7)
- **END:** Send END symbol

---

### PIPERXDepacketizer

**Class:** `litepcie.dll.pipe.PIPERXDepacketizer`

Converts 8-bit PIPE symbols to 64-bit DLL packets by detecting K-character framing.

#### Constructor

```python
PIPERXDepacketizer(debug=False)
```

**Parameters:**
- `debug` (bool): Enable debug signals for testing (default: False)
  - When True, exposes `debug_data_buffer` signal showing internal accumulation buffer
  - When False (production), no debug overhead

#### Signals

**Input:**
- `pipe_rx_data` (8-bit): PIPE RX data symbol
- `pipe_rx_datak` (1-bit): K-character indicator

**Output:**
- `source` (Endpoint): DLL packet output
  - `source.valid` (1-bit): Packet valid
  - `source.first` (1-bit): First beat
  - `source.last` (1-bit): Last beat
  - `source.dat` (64-bit): Packet data

**Debug (only when debug=True):**
- `debug_data_buffer` (64-bit): Internal accumulation buffer for test verification

#### Behavior

**START Detection:**
- **STP (0xFB, K=1):** TLP packet start
- **SDP (0x5C, K=1):** DLLP packet start

**Data Accumulation:**
- Accumulates 8 data bytes (K=0) into 64-bit buffer
- Little-endian ordering: [7:0], [15:8], ..., [63:56]

**END Detection:**
- **END (0xFD, K=1):** Outputs complete packet with valid=1, first=1, last=1

**FSM States:**
- **IDLE:** Wait for START (STP or SDP with K=1)
- **DATA:** Accumulate data bytes, wait for END

---

### K-Character Constants

```python
# Import from litepcie.dll.pipe
PIPE_K27_7_STP = 0xFB  # Start TLP
PIPE_K28_2_SDP = 0x5C  # Start DLLP
PIPE_K29_7_END = 0xFD  # End packet (good)
PIPE_K30_7_EDB = 0xFE  # End bad packet (not implemented)
PIPE_K28_5_COM = 0xBC  # Comma (alignment)
PIPE_K28_0_SKP = 0x1C  # Skip (clock compensation)
```

---

## Examples

### Example 1: Simple Loopback

Test PIPE functionality without external PHY by connecting TX to RX:

```python
from migen import *
from litepcie.dll.pipe import PIPEInterface

class PIPELoopbackTest(Module):
    def __init__(self):
        # Create PIPE interface
        self.submodules.pipe = pipe = PIPEInterface(data_width=8, gen=1)

        # Connect TX → RX (loopback)
        self.comb += [
            pipe.pipe_rx_data.eq(pipe.pipe_tx_data),
            pipe.pipe_rx_datak.eq(pipe.pipe_tx_datak),
        ]

    def send_packet(self, data):
        """Send a packet through the loopback."""
        yield self.pipe.dll_tx_sink.valid.eq(1)
        yield self.pipe.dll_tx_sink.first.eq(1)
        yield self.pipe.dll_tx_sink.last.eq(1)
        yield self.pipe.dll_tx_sink.dat.eq(data)
        yield

        # Clear TX
        yield self.pipe.dll_tx_sink.valid.eq(0)
        yield

        # Wait for RX (START + 8 DATA + END = 10 cycles)
        for _ in range(10):
            yield

        # Read RX output
        rx_valid = yield self.pipe.dll_rx_source.valid
        rx_data = yield self.pipe.dll_rx_source.dat

        return rx_valid, rx_data

# Usage in simulation:
dut = PIPELoopbackTest()
def testbench():
    rx_valid, rx_data = yield from dut.send_packet(0x0123456789ABCDEF)
    assert rx_valid == 1
    assert rx_data == 0x0123456789ABCDEF

run_simulation(dut, testbench())
```

### Example 2: DLL Integration

Connect PIPE interface between DLL and PHY:

```python
from migen import *
from litepcie.dll.core import LitePCIeDLL
from litepcie.dll.pipe import PIPEInterface

class PCIeWithPIPE(Module):
    def __init__(self, phy_pads):
        # Create DLL
        self.submodules.dll = dll = LitePCIeDLL(
            data_width=64,
            endianness="little",
            # ... other DLL parameters
        )

        # Create PIPE interface
        self.submodules.pipe = pipe = PIPEInterface(data_width=8, gen=1)

        # Connect DLL ↔ PIPE
        self.comb += [
            # TX: DLL → PIPE
            dll.tx_source.connect(pipe.dll_tx_sink),
            # RX: PIPE → DLL
            pipe.dll_rx_source.connect(dll.rx_sink),
        ]

        # Connect PIPE ↔ External PHY pads
        self.comb += [
            # TX: PIPE → PHY
            phy_pads.tx_data.eq(pipe.pipe_tx_data),
            phy_pads.tx_datak.eq(pipe.pipe_tx_datak),
            phy_pads.tx_elecidle.eq(pipe.pipe_tx_elecidle),

            # RX: PHY → PIPE
            pipe.pipe_rx_data.eq(phy_pads.rx_data),
            pipe.pipe_rx_datak.eq(phy_pads.rx_datak),
            pipe.pipe_rx_valid.eq(phy_pads.rx_valid),
            pipe.pipe_rx_status.eq(phy_pads.rx_status),
            pipe.pipe_rx_elecidle.eq(phy_pads.rx_elecidle),

            # Control: PIPE → PHY
            phy_pads.powerdown.eq(pipe.pipe_powerdown),
            phy_pads.rate.eq(pipe.pipe_rate),
            phy_pads.rx_polarity.eq(pipe.pipe_rx_polarity),
        ]
```

### Example 3: External PHY Integration

Using the PIPEExternalPHY wrapper for specific PHY chips:

```python
from migen import *
from litepcie.dll.pipe import PIPEInterface
from litepcie.phy.pipe_external_phy import PIPEExternalPHY

class PCIeWithExternalPHY(Module):
    def __init__(self, platform, phy_pads):
        # Create external PHY wrapper (e.g., TI TUSB1310A)
        self.submodules.phy = phy = PIPEExternalPHY(
            platform=platform,
            pads=phy_pads,
            chip="TUSB1310A",
            sys_clk_freq=125e6,  # PCLK for Gen1
        )

        # Create PIPE interface
        self.submodules.pipe = pipe = PIPEInterface(data_width=8, gen=1)

        # Connect PIPE ↔ PHY using convenience method
        self.comb += phy.connect_pipe(pipe)

        # Now pipe.dll_tx_sink and pipe.dll_rx_source are ready for DLL
```

---

## Troubleshooting

### Common Issues

#### Issue 1: No RX Output in Loopback

**Symptom:** `dll_rx_source.valid` is always 0 even after sending TX packet.

**Causes:**
1. Not waiting long enough for TX→RX propagation
2. Missing loopback connection
3. TX packet not properly formatted

**Solutions:**
```python
# ✅ Wait adequate cycles (10+ for single packet)
yield pipe.dll_tx_sink.valid.eq(1)
yield pipe.dll_tx_sink.first.eq(1)
yield pipe.dll_tx_sink.last.eq(1)
yield pipe.dll_tx_sink.dat.eq(test_data)
yield
yield pipe.dll_tx_sink.valid.eq(0)

# Wait for START(1) + DATA(8) + END(1) = 10 cycles minimum
for _ in range(10):
    yield

# Now check RX
rx_valid = yield pipe.dll_rx_source.valid
```

#### Issue 2: Data Corruption in RX

**Symptom:** RX data doesn't match TX data, bytes are swapped or incorrect.

**Causes:**
1. Byte ordering mismatch (big-endian vs little-endian)
2. Timing issue in simulation
3. Missing stream control signals

**Solutions:**
```python
# ✅ LitePCIe uses little-endian ordering
# Byte 0 = bits[7:0], Byte 7 = bits[63:56]
test_data = 0x0123456789ABCDEF
# This will send: EF CD AB 89 67 45 23 01 (LSB first)
# And reconstruct: 0x0123456789ABCDEF

# ✅ Always set all stream control signals
yield pipe.dll_tx_sink.valid.eq(1)  # Required
yield pipe.dll_tx_sink.first.eq(1)  # Required for framing
yield pipe.dll_tx_sink.last.eq(1)   # Required for framing
yield pipe.dll_tx_sink.dat.eq(test_data)
```

#### Issue 3: ValueError on Construction

**Symptom:** `ValueError: Only 8-bit PIPE mode supported currently`

**Cause:** Trying to use unsupported data width or generation.

**Solutions:**
```python
# ❌ WRONG
pipe = PIPEInterface(data_width=16, gen=3)

# ✅ CORRECT
pipe = PIPEInterface(data_width=8, gen=1)  # Gen1
# or
pipe = PIPEInterface(data_width=8, gen=2)  # Gen2
```

### Debug Tips

#### 1. Enable VCD Waveform Generation

```python
from litex.gen import run_simulation

def testbench(dut):
    # Your test code
    yield

dut = PIPEInterface(data_width=8, gen=1)
run_simulation(dut, testbench(dut), vcd_name="pipe_debug.vcd")
```

View the VCD file with GTKWave:
```bash
gtkwave pipe_debug.vcd
```

**Key signals to monitor:**
- `pipe.pipe_tx_data` / `pipe.pipe_tx_datak` - TX symbol stream
- `pipe.pipe_rx_data` / `pipe.pipe_rx_datak` - RX symbol stream
- `pipe.tx_packetizer.fsm.state` - TX FSM state (IDLE/DATA/END)
- `pipe.rx_depacketizer.fsm.state` - RX FSM state (IDLE/DATA)

#### 2. Use Debug Mode for RX Testing

```python
# Enable debug mode to expose internal buffer
rx_depack = PIPERXDepacketizer(debug=True)

# In testbench, you can inspect internal state:
def testbench(dut):
    # Send data...
    yield

    # Check internal buffer (not available in production mode)
    buffer_value = yield dut.debug_data_buffer
    print(f"Internal buffer: 0x{buffer_value:016X}")
```

#### 3. Check K-Character Detection

```python
def testbench(pipe):
    # Send known K-character
    yield pipe.pipe_rx_data.eq(0xFB)  # STP
    yield pipe.pipe_rx_datak.eq(1)    # K=1
    yield

    # Check if RX FSM detected it (should transition to DATA state)
    # This requires monitoring FSM state in VCD
```

#### 4. Verify Electrical Idle Behavior

```python
def testbench(pipe):
    # No TX data
    yield pipe.dll_tx_sink.valid.eq(0)
    yield

    # Should request electrical idle
    elecidle = yield pipe.pipe_tx_elecidle
    assert elecidle == 1, "Should request idle when no data"
```

### VCD Analysis Tips

When analyzing VCD files in GTKWave:

**Add these signals for TX debugging:**
```
pipe.dll_tx_sink.valid
pipe.dll_tx_sink.first
pipe.dll_tx_sink.last
pipe.dll_tx_sink.dat
pipe.tx_packetizer.fsm.state
pipe.pipe_tx_data
pipe.pipe_tx_datak
```

**Add these signals for RX debugging:**
```
pipe.pipe_rx_data
pipe.pipe_rx_datak
pipe.rx_depacketizer.fsm.state
pipe.dll_rx_source.valid
pipe.dll_rx_source.first
pipe.dll_rx_source.last
pipe.dll_rx_source.dat
```

**Look for:**
1. **START symbol timing:** STP/SDP (K=1) should appear when sink.valid & sink.first
2. **Data byte sequence:** 8 consecutive data bytes (K=0) after START
3. **END symbol timing:** END (K=1) should appear after 8 data bytes
4. **RX packet output:** source.valid should go high when END is detected
5. **FSM state transitions:** IDLE → DATA → END (TX), IDLE → DATA (RX)

---

## References

- **Intel PIPE 3.0 Specification** - Complete PIPE protocol definition
- **PCIe Base Spec 4.0, Section 4** - Physical Layer and Symbol Encoding
- **docs/pipe-interface-spec.md** - LitePCIe PIPE implementation specification
- **docs/pipe-architecture.md** - Detailed architecture diagrams
- **docs/pipe-testing-guide.md** - Comprehensive testing documentation
- **test/dll/test_pipe_*.py** - Example test implementations

---

## Version History

- **1.0 (2025-10-17):** Initial release with Gen1/Gen2 support, TX/RX packetization, loopback testing
