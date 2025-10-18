# Integration Patterns - LitePCIe Cross-Layer Architecture

**Layer:** Cross-Cutting Integration
**Purpose:** Document how all PCIe layers integrate and interact
**Status:** Comprehensive Reference

## Overview

This document provides comprehensive integration patterns showing how all LitePCIe layers connect together. It covers:

1. **Integration Overview** - How layers connect and communicate
2. **End-to-End Data Flow** - Complete TLP journey through all layers
3. **Clock Domain Architecture** - All clock domains and CDC points
4. **Vendor PHY Integration** - Different PHY approaches (vendor IP vs. custom PIPE)
5. **Error Handling** - Cross-layer error propagation and recovery
6. **Performance Considerations** - Throughput, latency, and optimization

## Reading This Documentation

- **New to integration?** Start with [Integration Overview](#integration-overview)
- **Need to understand data flow?** See [End-to-End Data Flow](#end-to-end-data-flow)
- **Working on clocking?** Jump to [Clock Domain Architecture](#clock-domain-architecture)
- **Integrating a PHY?** Check [Vendor PHY Integration Examples](#vendor-phy-integration-examples)

---

## Integration Overview

### Layer Interface Contracts

Each layer in the PCIe stack presents a well-defined interface to adjacent layers:

```
┌─────────────────────────────────────────────────────────────┐
│                     APPLICATION LAYER                        │
│                                                               │
│  User logic, DMA engines, memory controllers                │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ request_layout / completion_layout
                       │ Width: 64-512 bits
                       │ Format: Stream endpoint
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                    TRANSACTION LAYER (TLP)                   │
│                  Location: litepcie/tlp/                     │
│                                                               │
│  Interface to Application:                                   │
│  • request_sink: Accepts read/write requests                │
│  • completion_source: Provides completions                  │
│                                                               │
│  Interface to DLL:                                            │
│  • phy.sink: Stream of TLP packets (phy_layout)             │
│  • phy.source: Stream from DLL                               │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ phy_layout(data_width)
                       │ Width: 64-512 bits
                       │ Fields: dat[n:0], be[n/8:0]
                       │ Control: valid, ready, first, last
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                   DATA LINK LAYER (DLL)                      │
│                  Location: litepcie/dll/                     │
│                                                               │
│  Interface to TLP:                                            │
│  • dll_sink: Receives TLPs to transmit                      │
│  • dll_source: Provides received TLPs                        │
│                                                               │
│  Interface to PIPE:                                           │
│  • pipe_sink: 64-bit packets with framing                   │
│  • pipe_source: 64-bit packets from PHY                     │
│                                                               │
│  Control Interface:                                           │
│  • ltssm_state: Current training state                      │
│  • link_up: Link operational status                         │
│  • send_ts1, send_ts2: Training sequence triggers           │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ 64-bit packets + ordered sets
                       │ Format: DLL framing (STP/SDP/END)
                       │ Protocol: Valid/ready handshaking
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                     PIPE INTERFACE LAYER                     │
│                  Location: litepcie/dll/pipe.py              │
│                                                               │
│  Interface to DLL:                                            │
│  • dll_tx_sink: 64-bit packet input                         │
│  • dll_rx_source: 64-bit packet output                      │
│                                                               │
│  Interface to PHY (PIPE signals):                            │
│  • tx_data[7:0], tx_datak: 8-bit symbols to PHY            │
│  • rx_data[7:0], rx_datak: 8-bit symbols from PHY          │
│  • tx_elecidle, rx_elecidle: Electrical idle control       │
│  • rx_valid: Symbol validity flag                           │
│                                                               │
│  Status:                                                      │
│  • ts1_detected, ts2_detected: Training seq detection       │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ PIPE protocol (8-bit symbols + ctrl)
                       │ Data width: 8 bits (16 bits Gen3+)
                       │ Protocol: Intel PIPE 3.0 subset
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                    TRANSCEIVER BASE LAYER                    │
│            Location: litepcie/phy/transceiver_base/          │
│                                                               │
│  Interface to PIPE:                                           │
│  • tx_data[15:0], tx_datak[1:0]: PIPE input (2 bytes)      │
│  • rx_data[15:0], rx_datak[1:0]: PIPE output                │
│                                                               │
│  Interface to SERDES:                                         │
│  • 20-bit encoded symbols (10 bits per byte)                │
│  • Internal primitive ports (vendor-specific)                │
│                                                               │
│  Control/Status:                                              │
│  • tx_ready, rx_ready: Operational status                   │
│  • reset: Reset request                                      │
│  • speed[1:0]: Gen1/Gen2/Gen3 selection                     │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ 10-bit 8b/10b encoded symbols
                       │ Width: 20 bits (2×10)
                       │ Clocks: tx_clk, rx_clk
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                    SERDES/TRANSCEIVER LAYER                  │
│   Location: litepcie/phy/xilinx/, litepcie/phy/lattice/      │
│                                                               │
│  Vendor primitives: GTX, GTY, ECP5 DCUA                      │
│  Functions: Serialization, CDR, equalization                 │
│  Output: Differential serial (TX+/-, RX+/-)                 │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ Differential serial
                       │ Line rate: 2.5 GT/s (Gen1), 5.0 GT/s (Gen2)
                       ▼
                 Physical PCIe Link
```

### Interface Contract Summary

| Layer | Input Interface | Output Interface | Width | Clock Domain |
|-------|----------------|------------------|-------|--------------|
| **TLP** | request_layout | completion_layout | 64-512b | sys |
| ↓↑ | phy_layout | phy_layout | 64-512b | sys |
| **DLL** | phy_layout | phy_layout | 64b | pcie |
| ↓↑ | 64-bit packets | 64-bit packets | 64b | pcie |
| **PIPE** | 64-bit packets | 64-bit packets | 64b | pcie |
| ↓↑ | PIPE symbols | PIPE symbols | 8-16b | pcie |
| **Transceiver Base** | PIPE symbols | PIPE symbols | 16b | sys |
| ↓↑ | 8b/10b encoded | 8b/10b encoded | 20b | tx/rx |
| **SERDES** | Parallel encoded | Parallel encoded | 20b | tx/rx |
| ↓↑ | Serial differential | Serial differential | 1b | Line rate |

---

## End-to-End Data Flow

This section shows a complete TLP's journey through all layers in both directions.

### Example: Memory Write Request (Application → Physical Link)

Let's trace a 64-byte memory write from application through all layers to the wire.

#### Application Layer

```
Application Request:
  Operation: Write 64 bytes to address 0x1000_0000
  Data: [64 bytes of payload]

Format: request_layout
  • we = 1 (write enable)
  • adr = 0x1000_0000
  • len = 16 DW (64 bytes = 16 × 4-byte DWORDs)
  • dat[511:0] = payload data
```

#### TLP Layer Processing

```
┌─────────────────────────────────────────────────────────────┐
│                   TLP Packetizer                             │
│                                                               │
│ Input: Application write request                            │
│ Processing:                                                   │
│   1. Determine TLP type: MWr64 (64-bit addressing)          │
│      fmt:type = 11:00000                                     │
│                                                               │
│   2. Build TLP header (4DW for 64-bit addressing):          │
│      DW0: fmt=11, type=00000, length=16                     │
│      DW1: requester_id=00:00.0, tag=32, BE=0xF              │
│      DW2: address[63:32] = 0x1000                           │
│      DW3: address[31:2]  = 0x0000, reserved                 │
│                                                               │
│   3. Calculate ECRC (if enabled): CRC-32 over header+data   │
│                                                               │
│   4. Format into phy_layout stream:                          │
│      Beat 0: {DW1, DW0} = 64 bits                           │
│      Beat 1: {DW3, DW2} = 64 bits                           │
│      Beat 2: {Data[1], Data[0]} = 64 bits                   │
│      ...                                                     │
│      Beat 9: {Data[15], Data[14]} = 64 bits (last)          │
│                                                               │
│ Output: TLP packet on phy.sink                              │
│   Total: 4 DW header + 16 DW data = 20 DW = 10 beats @64b   │
└─────────────────────────────────────────────────────────────┘
```

#### DLL Layer Processing

```
┌─────────────────────────────────────────────────────────────┐
│                    DLL TX Path                               │
│                                                               │
│ Input: TLP packet (4 DW header + 16 DW data)                │
│                                                               │
│ Step 1: Assign Sequence Number                              │
│   • tx_seq_counter = 0x042                                  │
│   • Sequence number: 0x042 (12-bit)                         │
│   • tx_seq_counter++ (now 0x043)                            │
│                                                               │
│ Step 2: Calculate LCRC (Link CRC)                           │
│   • Input: TLP header + TLP data (20 DW)                    │
│   • Algorithm: CRC-32 (polynomial 0x04C11DB7)               │
│   • Result: LCRC = 0xABCD1234                               │
│                                                               │
│ Step 3: Store in Retry Buffer                               │
│   • Buffer[0x042] = {seq=0x042, tlp_data=20DW, lcrc}        │
│   • Status: Awaiting ACK                                     │
│   • Timeout: 50μs (if no ACK, replay from buffer)          │
│                                                               │
│ Step 4: Frame for PIPE Layer                                │
│   • Packet structure:                                        │
│     STP | Seq[11:0] | TLP[0] | ... | TLP[19] | LCRC | END  │
│   • Total: 1 + 20 + 1 + 1 = 23 QW (64-bit words)            │
│                                                               │
│ Output: 64-bit framed packet to PIPE layer                  │
└─────────────────────────────────────────────────────────────┘
```

#### PIPE Layer Processing

```
┌─────────────────────────────────────────────────────────────┐
│                    PIPE TX Packetizer                        │
│                                                               │
│ Input: 64-bit DLL packet (23 QW)                            │
│                                                               │
│ Symbol-by-Symbol Transmission:                              │
│                                                               │
│ Symbol 0: STP (K27.7 = 0xFB)                                │
│   tx_data = 0xFB, tx_datak = 1                              │
│   Marks start of TLP                                         │
│                                                               │
│ Symbols 1-184: Data bytes                                   │
│   • 23 QW × 8 bytes/QW = 184 data bytes                     │
│   • Each symbol: tx_datak = 0 (data)                        │
│   • Byte order: Little-endian (LSB first)                   │
│                                                               │
│   Example symbols:                                           │
│   Symbol 1: dat[7:0]   = Seq[7:0]                           │
│   Symbol 2: dat[15:8]  = Seq[11:8]                          │
│   Symbol 3: dat[23:16] = TLP DW0[7:0]                       │
│   ...                                                        │
│   Symbol 184: LCRC[31:24] (last data byte)                  │
│                                                               │
│ Symbol 185: END (K29.7 = 0xFD)                              │
│   tx_data = 0xFD, tx_datak = 1                              │
│   Marks end of packet                                        │
│                                                               │
│ SKP Insertion (every 1180 symbols):                         │
│   • Periodically insert: COM + 3×SKP                        │
│   • Frequency: ~Every 6 packets                             │
│   • Purpose: Clock compensation between TX and RX           │
│                                                               │
│ Output: 8-bit symbol stream to transceiver                  │
│   Total: 186 symbols (1 STP + 184 data + 1 END)             │
└─────────────────────────────────────────────────────────────┘
```

#### Transceiver Base Layer Processing

```
┌─────────────────────────────────────────────────────────────┐
│                  TX Datapath (sys → tx)                      │
│                                                               │
│ Input: 8-bit PIPE symbols from PIPE layer (sys_clk domain)  │
│                                                               │
│ Step 1: Clock Domain Crossing (CDC)                         │
│   Clock: sys_clk (125 MHz) → tx_clk (250 MHz Gen2)         │
│   Mechanism: AsyncFIFO (depth=8)                             │
│   Latency: ~2-4 cycles                                       │
│                                                               │
│ Step 2: 8b/10b Encoding (in tx_clk domain)                  │
│   For each 8-bit symbol:                                     │
│                                                               │
│   STP (K27.7 = 0xFB):                                       │
│     Input: data=0xFB, k=1                                    │
│     Output: 10b code = 0b110_1101_000 (RD-)                 │
│             or       = 0b001_0010_111 (RD+)                 │
│     Running disparity updated                                │
│                                                               │
│   Data byte (e.g., 0x42):                                   │
│     Input: data=0x42, k=0                                    │
│     Split: EDCBA=00010 (D2), HGF=010 (x.2)                  │
│     Encode: 5b/6b(D2)=100010, 3b/4b(x.2)=0101              │
│     Output: 10b code = 0b010110_0010                        │
│     Running disparity updated                                │
│                                                               │
│   END (K29.7 = 0xFD):                                       │
│     Input: data=0xFD, k=1                                    │
│     Output: 10b code = 0b101_1101_000 (RD-)                 │
│             or       = 0b010_0010_111 (RD+)                 │
│                                                               │
│ Step 3: Output to SERDES                                    │
│   • Width: 20 bits (2 symbols × 10 bits each)               │
│   • Format: {symbol[1][9:0], symbol[0][9:0]}                │
│   • Rate: 250 MHz word clock (Gen2)                         │
│                                                               │
│ Output: 20-bit encoded symbols to GTX/GTY/ECP5              │
└─────────────────────────────────────────────────────────────┘
```

#### SERDES Layer Processing

```
┌─────────────────────────────────────────────────────────────┐
│              Xilinx GTX/GTY or ECP5 SERDES                   │
│                                                               │
│ Input: 20-bit encoded symbols @ 250 MHz (Gen2)              │
│                                                               │
│ TX Serializer Operation:                                     │
│   Clock: 250 MHz word clock → 5.0 GHz bit clock             │
│   Ratio: 20:1 (20 bits serialized per word clock)           │
│                                                               │
│   Example serialization:                                     │
│   Input word: 0b01011_00010_10110_1101                      │
│                                                               │
│   Bit 0:  1  ──┐                                            │
│   Bit 1:  0    │                                            │
│   Bit 2:  1    │                                            │
│   ...          │ Serialized at 5.0 Gb/s                     │
│   Bit 19: 0  ──┘                                            │
│                                                               │
│ Output Driver:                                               │
│   • Differential signaling: TX+, TX-                        │
│   • Voltage swing: 0.8-1.2V (PCIe compliant)                │
│   • Pre-emphasis: Configured for trace length               │
│   • De-emphasis: -3.5 dB for Gen2                           │
│                                                               │
│ Physical Layer Functions:                                    │
│   • DC balance maintenance (via 8b/10b)                     │
│   • Transmit equalization                                    │
│   • Output impedance: 50Ω differential                      │
│                                                               │
│ Output: Serial differential signal on PCIe lanes            │
│   Line rate: 5.0 Gb/s (Gen2)                                │
│   Effective data rate: 4.0 Gb/s (after 8b/10b overhead)     │
└─────────────────────────────────────────────────────────────┘
```

#### Physical Link

```
Serial bit stream on PCB traces:
  TX+ / TX- differential pair
  Traveling at ~5.0 Gb/s (200 ps per bit)

  Total transmission time for 186 symbols:
    186 symbols × 10 bits/symbol = 1860 bits
    1860 bits ÷ 5.0 Gb/s = 372 ns
```

### Example: Memory Read Completion (Physical Link → Application)

Now let's trace the reverse path - a completion returning from the remote device.

#### Physical Link

```
Serial bit stream arriving on RX+/RX-:
  1-bit serial @ 5.0 Gb/s (Gen2)
  Differential voltage: ±400 mV typical
```

#### SERDES Layer Processing

```
┌─────────────────────────────────────────────────────────────┐
│                    RX Deserializer                           │
│                                                               │
│ Input: Serial differential signal (RX+, RX-)                │
│                                                               │
│ Clock and Data Recovery (CDR):                              │
│   • Extract clock from data transitions                     │
│   • Lock to incoming bit stream                             │
│   • Frequency: 5.0 GHz ± 300 ppm                            │
│   • Output: rx_clk @ 250 MHz                                │
│                                                               │
│ Serial to Parallel Conversion:                              │
│   1-bit @ 5.0 GHz → 20-bit @ 250 MHz                        │
│                                                               │
│   Bit sampling:                                              │
│   Bit 0:  1  ─┐                                             │
│   Bit 1:  1   │                                             │
│   Bit 2:  0   │ Accumulated into                            │
│   ...         │ 20-bit word                                 │
│   Bit 19: 1  ─┘                                             │
│                                                               │
│   Result: 20-bit word = 0b1...1                             │
│                                                               │
│ Equalization:                                                │
│   • DFE (Decision Feedback Equalization): 3-tap             │
│   • CTLE (Continuous Time Linear Equalization)              │
│   • Compensates for ISI (Inter-Symbol Interference)         │
│                                                               │
│ Output: 20-bit parallel words @ 250 MHz to transceiver base │
└─────────────────────────────────────────────────────────────┘
```

#### Transceiver Base Layer Processing

```
┌─────────────────────────────────────────────────────────────┐
│                  RX Datapath (rx → sys)                      │
│                                                               │
│ Input: 20-bit encoded symbols @ 250 MHz (rx_clk domain)     │
│                                                               │
│ Step 1: 8b/10b Decoding (in rx_clk domain)                  │
│   For each 10-bit code:                                      │
│                                                               │
│   K27.7 (STP) detection:                                    │
│     Input: 10b = 0b001_0010_111 (RD+ variant)               │
│     Decode: Recognize as K27.7 comma character              │
│     Output: data=0xFB, datak=1                              │
│     Update running disparity                                 │
│                                                               │
│   Data symbol decode:                                        │
│     Input: 10b = 0b010110_0010                              │
│     Decode: 6b(100010)→5b(00010), 4b(0101)→3b(010)         │
│     Output: data=0x42 (EDCBA=00010, HGF=010), datak=0       │
│                                                               │
│   Disparity checking:                                        │
│     • Running disparity tracking                             │
│     • If disparity error → rx_valid=0                       │
│     • If valid symbol → rx_valid=1                          │
│                                                               │
│   K29.7 (END) detection:                                    │
│     Input: 10b = 0b010_0010_111                             │
│     Decode: Recognize as K29.7                              │
│     Output: data=0xFD, datak=1                              │
│                                                               │
│ Step 2: Clock Domain Crossing (CDC)                         │
│   Clock: rx_clk (recovered, 250 MHz) → sys_clk (125 MHz)   │
│   Mechanism: AsyncFIFO (depth=8)                             │
│   Latency: ~2-4 cycles                                       │
│   Safety: Handles PPM drift between TX and RX clocks        │
│                                                               │
│ Output: 8-bit PIPE symbols to PIPE layer (sys_clk domain)   │
│   rx_data[7:0], rx_datak, rx_valid                          │
└─────────────────────────────────────────────────────────────┘
```

#### PIPE Layer Processing

```
┌─────────────────────────────────────────────────────────────┐
│                    PIPE RX Depacketizer                      │
│                                                               │
│ Input: 8-bit symbol stream from transceiver                 │
│                                                               │
│ Symbol-by-Symbol Reception:                                 │
│                                                               │
│ Symbol 0: Detect STP (0xFB, k=1)                            │
│   • FSM: IDLE → DATA                                        │
│   • Reset byte counter = 0                                   │
│   • Clear data buffer                                        │
│   • is_tlp = 1 (STP indicates TLP)                          │
│                                                               │
│ Symbols 1-N: Accumulate data bytes                          │
│   While rx_datak = 0:                                        │
│     data_buffer[byte_counter] = rx_data                      │
│     byte_counter++                                           │
│                                                               │
│   Example accumulation:                                      │
│   Symbol 1: buffer[0] = completion DW0[7:0]                 │
│   Symbol 2: buffer[1] = completion DW0[15:8]                │
│   ...                                                        │
│   Symbol 8: buffer[7] = completion DW1[31:24]               │
│   (First 64-bit word complete)                               │
│                                                               │
│   Symbol 9-16: Second 64-bit word                           │
│   Symbol 17-24: Third 64-bit word (data starts)            │
│   ...                                                        │
│                                                               │
│ SKP Filtering:                                               │
│   If COM (0xBC) detected:                                   │
│     Check next 3 symbols for SKP (0x1C)                     │
│     If valid SKP ordered set: Filter out, don't forward     │
│     Resume data accumulation                                 │
│                                                               │
│ Symbol N: Detect END (0xFD, k=1)                            │
│   • FSM: DATA → IDLE                                        │
│   • Package accumulated buffer into 64-bit words            │
│   • Output packet:                                           │
│     - dll_rx_source.valid = 1                               │
│     - dll_rx_source.first = 1                               │
│     - dll_rx_source.last = 1                                │
│     - dll_rx_source.dat = accumulated data                  │
│                                                               │
│ Output: 64-bit DLL packets                                  │
└─────────────────────────────────────────────────────────────┘
```

#### DLL Layer Processing

```
┌─────────────────────────────────────────────────────────────┐
│                    DLL RX Path                               │
│                                                               │
│ Input: 64-bit framed packet from PIPE layer                 │
│                                                               │
│ Step 1: Extract Components                                  │
│   • Sequence number: Extract from packet header            │
│   • TLP payload: Extract TLP data                           │
│   • LCRC: Extract last 4 bytes                              │
│                                                               │
│ Step 2: Verify LCRC                                         │
│   • Calculate CRC-32 over TLP payload                       │
│   • Compare with received LCRC                               │
│   • If mismatch:                                             │
│     - Generate NAK DLLP with last good seq number           │
│     - Discard packet                                         │
│     - Wait for retransmission                                │
│   • If match:                                                │
│     - Continue to sequence check                             │
│                                                               │
│ Step 3: Check Sequence Number                               │
│   • Expected: rx_seq_expected = 0x100                       │
│   • Received: rx_seq_received = 0x100                       │
│   • Comparison: MATCH                                        │
│   • Action: Accept packet                                    │
│   • Update: rx_seq_expected = 0x101                         │
│                                                               │
│ Step 4: Generate ACK DLLP                                   │
│   • ACK DLLP format:                                         │
│     Type: 0x0 (ACK)                                          │
│     Seq: 0x100 (acknowledging this sequence)                │
│     CRC-16: Calculate over DLLP                             │
│   • Send ACK to remote transmitter                          │
│                                                               │
│ Step 5: Forward TLP to TLP Layer                            │
│   • Remove DLL framing                                       │
│   • Extract pure TLP (header + data)                        │
│   • Present on dll_source endpoint                          │
│                                                               │
│ Output: Clean TLP to TLP layer (no LCRC, no seq number)    │
└─────────────────────────────────────────────────────────────┘
```

#### TLP Layer Processing

```
┌─────────────────────────────────────────────────────────────┐
│                   TLP Depacketizer                           │
│                                                               │
│ Input: TLP packet from DLL (phy.source)                     │
│                                                               │
│ Step 1: Parse TLP Header                                    │
│   Extract DW0:                                               │
│     fmt = 10 (3DW header with data)                         │
│     type = 01010 (Completion with Data - CplD)              │
│     length = 16 DW (64 bytes)                               │
│                                                               │
│   Extract DW1:                                               │
│     completer_id = 01:00.0                                  │
│     status = 000 (Successful Completion)                    │
│     byte_count = 64 (total bytes in completion)             │
│                                                               │
│   Extract DW2:                                               │
│     requester_id = 00:00.0 (us)                             │
│     tag = 0x05                                               │
│     lower_addr = 0x00                                        │
│                                                               │
│ Step 2: Route by Tag                                        │
│   • Tag 0x05 identifies the original request                │
│   • TLP Controller lookup:                                   │
│     req_queue[0x05] = {channel=2, user_id=0x42}             │
│   • Route completion to buffer[0x05]                        │
│                                                               │
│ Step 3: Extract Completion Data                             │
│   • Data payload: 16 DW (64 bytes)                          │
│   • Store in completion buffer                               │
│                                                               │
│ Step 4: Check Completion Status                             │
│   • Is this the last completion for tag 0x05?               │
│   • Check byte_count: 64 bytes total, 64 bytes this packet │
│   • Result: Yes, this is the final completion               │
│                                                               │
│ Step 5: Forward to Application                              │
│   • completion_source.valid = 1                             │
│   • completion_source.tag = 0x05                            │
│   • completion_source.end = 1 (last completion)             │
│   • completion_source.dat = [64 bytes]                      │
│                                                               │
│ Step 6: Return Tag to Pool                                  │
│   • Mark tag 0x05 as available                              │
│   • Can be reused for next read request                     │
│   • Pop req_queue entry for tag 0x05                        │
│                                                               │
│ Output: Completion data to application                      │
└─────────────────────────────────────────────────────────────┘
```

#### Application Layer

```
Application receives completion:
  Tag: 0x05 (matches original read request)
  Data: [64 bytes of payload]
  Status: Successful

Application can now:
  • Process the read data
  • Issue next transaction (tag 0x05 now available)
```

---

## Clock Domain Architecture

LitePCIe operates across multiple clock domains with carefully managed CDC (Clock Domain Crossing).

### Clock Domains Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Clock Domain Map                         │
│                                                               │
│  ┌────────────────────────────────────────────────────┐     │
│  │  sys_clk Domain (User-defined, e.g., 125 MHz)     │     │
│  │  ══════════════════════════════════════════════     │     │
│  │                                                     │     │
│  │  Components:                                        │     │
│  │  • Application logic                                │     │
│  │  • TLP layer (packetizer, depacketizer)            │     │
│  │  • Endpoint logic                                   │     │
│  │  • DMA engines                                      │     │
│  │  • PHYTXDatapath write side                        │     │
│  │  • PHYRXDatapath read side                         │     │
│  │                                                     │     │
│  │  Source: Platform PLL (user-configured)            │     │
│  └─────────────────────────┬───────────────────────────┘     │
│                            │                                  │
│                            │ AsyncFIFO CDC                    │
│                            │ (PHYTXDatapath / PHYRXDatapath)  │
│                            │                                  │
│  ┌─────────────────────────▼───────────────────────────┐     │
│  │  pcie_clk Domain (125 MHz Gen1, 250 MHz Gen2)      │     │
│  │  ═══════════════════════════════════════════════     │     │
│  │                                                     │     │
│  │  Components:                                        │     │
│  │  • DLL TX (LCRC, sequencing, retry buffer)         │     │
│  │  • DLL RX (LCRC check, ACK/NAK)                    │     │
│  │  • DLLP processing                                  │     │
│  │  • LTSSM (link training state machine)             │     │
│  │  • PIPE interface (packetizer, depacketizer)       │     │
│  │  • Layout converters                                │     │
│  │  • PHYTXDatapath read side                         │     │
│  │  • PHYRXDatapath write side                        │     │
│  │  • Transceiver TX datapath write side              │     │
│  │  • Transceiver RX datapath read side               │     │
│  │                                                     │     │
│  │  Source (Phase 3-8): External PHY PCLK output      │     │
│  │  Source (Phase 9): Derived from tx_clk (TXOUTCLK)  │     │
│  └─────────────────────────┬───────────────────────────┘     │
│                            │                                  │
│                            │ AsyncFIFO CDC                    │
│                            │ (TransceiverTXDatapath /         │
│                            │  TransceiverRXDatapath)          │
│                            │ [Phase 9 only]                   │
│                            │                                  │
│  ┌─────────────────────────▼───────────────────────────┐     │
│  │  tx_clk Domain (125 MHz Gen1, 250 MHz Gen2)        │     │
│  │  ═══════════════════════════════════════════        │     │
│  │  [Phase 9 only - Internal transceivers]            │     │
│  │                                                     │     │
│  │  Components:                                        │     │
│  │  • 8b/10b encoder (software)                       │     │
│  │  • Transceiver TX datapath read side               │     │
│  │  • GTX/GTY/ECP5 TX primitive                       │     │
│  │                                                     │     │
│  │  Source: Transceiver TXOUTCLK                      │     │
│  └─────────────────────────────────────────────────────┘     │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐     │
│  │  rx_clk Domain (Recovered, 125/250 MHz ± PPM)      │     │
│  │  ═════════════════════════════════════════════       │     │
│  │  [Phase 9 only - Internal transceivers]            │     │
│  │                                                     │     │
│  │  Components:                                        │     │
│  │  • GTX/GTY/ECP5 RX primitive                       │     │
│  │  • 8b/10b decoder (software)                       │     │
│  │  • Transceiver RX datapath write side              │     │
│  │                                                     │     │
│  │  Source: Transceiver RXOUTCLK (CDR recovered)      │     │
│  └─────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

### Clock Domain Frequencies

| Domain | Gen1 | Gen2 | Gen3 | Source |
|--------|------|------|------|--------|
| **sys_clk** | Variable | Variable | Variable | Platform PLL |
| **pcie_clk** | 125 MHz | 250 MHz | 500 MHz | PHY PCLK or tx_clk |
| **tx_clk** | 125 MHz | 250 MHz | 500 MHz | TXOUTCLK (Phase 9) |
| **rx_clk** | 125 MHz ± PPM | 250 MHz ± PPM | 500 MHz ± PPM | RXOUTCLK (Phase 9) |

### Clock Domain Crossing Points

#### CDC Point 1: sys ↔ pcie (Always Present)

```
Location: PHYTXDatapath / PHYRXDatapath
Files: litepcie/phy/common.py

┌─────────────────────────────────────────────────────────────┐
│                     PHYTXDatapath                            │
│                                                               │
│  sys_clk Domain              pcie_clk Domain                │
│  ┌──────────────┐            ┌──────────────┐              │
│  │  TLP Layer   │            │  DLL Layer   │              │
│  │  Output      │            │  Input       │              │
│  └──────┬───────┘            └──────▲───────┘              │
│         │                           │                       │
│         │ Write                     │ Read                  │
│         │                           │                       │
│  ┌──────▼───────────────────────────┴───────┐              │
│  │          AsyncFIFO (depth=8)              │              │
│  │                                            │              │
│  │  • Layout: phy_layout(data_width)         │              │
│  │  • Buffered: True                         │              │
│  │  • Gray code pointers                     │              │
│  │  • Safe for arbitrary clock relationship  │              │
│  └────────────────────────────────────────────┘              │
│                                                               │
│  Implementation:                                             │
│    self.cdc = stream.AsyncFIFO(...)                         │
│    self.cdc = ClockDomainsRenamer({                         │
│        "write": "sys",                                       │
│        "read":  clock_domain  # "pcie"                      │
│    })(self.cdc)                                              │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                     PHYRXDatapath                            │
│                                                               │
│  pcie_clk Domain             sys_clk Domain                 │
│  ┌──────────────┐            ┌──────────────┐              │
│  │  DLL Layer   │            │  TLP Layer   │              │
│  │  Output      │            │  Input       │              │
│  └──────┬───────┘            └──────▲───────┘              │
│         │                           │                       │
│         │ Write                     │ Read                  │
│         │                           │                       │
│  ┌──────▼───────────────────────────┴───────┐              │
│  │          AsyncFIFO (depth=8)              │              │
│  │                                            │              │
│  │  • Layout: phy_layout(data_width)         │              │
│  │  • Buffered: True                         │              │
│  │  • Gray code pointers                     │              │
│  └────────────────────────────────────────────┘              │
│                                                               │
│  Implementation:                                             │
│    self.cdc = stream.AsyncFIFO(...)                         │
│    self.cdc = ClockDomainsRenamer({                         │
│        "write": clock_domain,  # "pcie"                     │
│        "read":  "sys"                                        │
│    })(self.cdc)                                              │
└─────────────────────────────────────────────────────────────┘
```

#### CDC Point 2: pcie ↔ tx/rx (Phase 9 Only)

```
Location: TransceiverTXDatapath / TransceiverRXDatapath
Files: litepcie/phy/transceiver_base/

┌─────────────────────────────────────────────────────────────┐
│                TransceiverTXDatapath                         │
│                                                               │
│  pcie_clk Domain             tx_clk Domain                  │
│  ┌──────────────┐            ┌──────────────┐              │
│  │  PIPE Layer  │            │  8b/10b      │              │
│  │  8-bit syms  │            │  Encoder     │              │
│  └──────┬───────┘            └──────▲───────┘              │
│         │                           │                       │
│         │ Write                     │ Read                  │
│         │                           │                       │
│  ┌──────▼───────────────────────────┴───────┐              │
│  │          AsyncFIFO (depth=8)              │              │
│  │                                            │              │
│  │  • Layout: [("data", 8), ("datak", 1)]    │              │
│  │  • Buffered: True                         │              │
│  │  • Handles TX clock domain                │              │
│  └────────────────────────────────────────────┘              │
│                                                               │
│  Why needed:                                                 │
│    • tx_clk is transceiver TXOUTCLK (reference)             │
│    • pcie_clk derived from tx_clk but may differ in phase   │
│    • AsyncFIFO provides clean separation                    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                TransceiverRXDatapath                         │
│                                                               │
│  rx_clk Domain               pcie_clk Domain                │
│  ┌──────────────┐            ┌──────────────┐              │
│  │  8b/10b      │            │  PIPE Layer  │              │
│  │  Decoder     │            │  8-bit syms  │              │
│  └──────┬───────┘            └──────▲───────┘              │
│         │                           │                       │
│         │ Write                     │ Read                  │
│         │                           │                       │
│  ┌──────▼───────────────────────────┴───────┐              │
│  │          AsyncFIFO (depth=8)              │              │
│  │                                            │              │
│  │  • Layout: [("data", 8), ("datak", 1),    │              │
│  │            ("valid", 1)]                   │              │
│  │  • Buffered: True                         │              │
│  │  • Critical: Handles PPM drift            │              │
│  └────────────────────────────────────────────┘              │
│                                                               │
│  Why needed:                                                 │
│    • rx_clk is CDR recovered from remote transmitter        │
│    • May have ±300 PPM frequency offset from tx_clk         │
│    • AsyncFIFO absorbs frequency mismatch                   │
│    • SKP ordered sets provide additional compensation       │
└─────────────────────────────────────────────────────────────┘
```

### Clock Constraints

Platform constraints must be properly configured for each clock domain:

```python
# sys_clk (user-defined, e.g., 125 MHz)
platform.add_period_constraint(sys_clk, 1e9/125e6)  # 8.0 ns

# pcie_clk (Gen1: 125 MHz, Gen2: 250 MHz)
platform.add_period_constraint(pcie_clk, 1e9/250e6)  # 4.0 ns (Gen2)

# Phase 9: tx_clk and rx_clk
platform.add_period_constraint(tx_clk, 1e9/250e6)  # 4.0 ns (Gen2)
platform.add_period_constraint(rx_clk, 1e9/250e6)  # 4.0 ns (Gen2)

# Mark async paths (no timing relationship)
platform.add_false_path_constraints(sys_clk, pcie_clk)
platform.add_false_path_constraints(pcie_clk, tx_clk)   # Phase 9
platform.add_false_path_constraints(rx_clk, pcie_clk)   # Phase 9
```

### CDC Safety Mechanisms

All clock domain crossings use AsyncFIFO with these safety features:

1. **Gray Code Pointers:** Write and read pointers encoded in Gray code to prevent metastability
2. **Multi-FF Synchronizers:** Control signals synchronized through 2-3 flip-flop chains
3. **Buffered Outputs:** Registered outputs prevent combinatorial paths across domains
4. **Depth Sizing:** Minimum depth of 8 ensures adequate buffering for burst traffic
5. **Valid/Ready Handshaking:** Back-pressure mechanism prevents overflow

---

## Vendor PHY Integration Examples

LitePCIe supports multiple PHY integration approaches. The choice depends on FPGA family, toolchain availability, and design requirements.

### Integration Strategy Comparison

| Approach | Advantages | Disadvantages | Use Cases |
|----------|-----------|---------------|-----------|
| **Vendor Hard IP** | • Proven, certified<br>• High performance<br>• Minimal resource usage | • Proprietary<br>• Vendor lock-in<br>• Limited visibility | Production designs on Xilinx/Lattice with vendor tools |
| **Custom PIPE + External PHY** | • Open-source friendly<br>• Full visibility<br>• Portable across vendors | • External chip required<br>• PCB complexity | Open-source designs, ECP5 with nextpnr |
| **Custom PIPE + Internal Transceiver** | • No external chips<br>• Full visibility<br>• Maximum flexibility | • Complex implementation<br>• Requires careful tuning | Advanced users, custom protocols |

### Example 1: Xilinx Vendor IP Integration

**Platform:** Xilinx 7-Series (Artix-7, Kintex-7, Virtex-7)
**PHY:** Hard PCIe IP block (PCIE_2_1 primitive)

```python
from litepcie.phy.s7pciephy import S7PCIEPHY

# Platform setup
pcie_pads = platform.request("pcie_x4")  # 4-lane PCIe connector

# Create PHY wrapper around Xilinx hard IP
phy = S7PCIEPHY(
    platform    = platform,
    pads        = pcie_pads,
    data_width  = 128,  # 128-bit datapath (Gen2 x4)
    cd          = "sys",
    bar0_size   = 0x100000,  # 1MB BAR0
)

# Platform creates "pcie" clock domain from hard IP's user_clk output
# This is done automatically by S7PCIEPHY

# Create endpoint (TLP layer)
endpoint = LitePCIeEndpoint(phy, address_width=32)

# Application connects to endpoint
self.comb += [
    app_read_request.connect(endpoint.read_request),
    endpoint.read_completion.connect(app_read_completion),
]
```

**Architecture:**

```
Application
     ↓ ↑
  TLP Layer (sys_clk)
     ↓ ↑ PHYTXDatapath/PHYRXDatapath CDC
  S7PCIEPHY
     ↓ ↑ user_clk (pcie_clk, from hard IP)
┌────────────────────┐
│  Xilinx PCIE_2_1   │ Hard IP Block
│  Primitive         │
│                    │
│  • DLL built-in    │
│  • LTSSM built-in  │
│  • PHY built-in    │
│  • Uses GT         │
│    transceivers    │
└────────────────────┘
     ↓ ↑
  PCIe Link
```

### Example 2: ECP5 with Custom PIPE + External PHY

**Platform:** Lattice ECP5 (LFE5U-85F)
**Toolchain:** Open-source (Yosys + nextpnr-ecp5)
**PHY:** TI TUSB1310A (external PIPE PHY chip)

```python
from litepcie.phy.pipe_external import PIPEExternalPHY

# Platform setup
pipe_pads = platform.request("pcie_pipe")  # PIPE interface to TUSB1310A

# Create PHY wrapper for external PIPE chip
phy = PIPEExternalPHY(
    platform    = platform,
    pads        = pipe_pads,
    data_width  = 64,   # 64-bit datapath
    cd          = "sys",
    bar0_size   = 0x100000,
)

# Platform must create "pcie" clock domain from external PHY's PCLK
# TUSB1310A outputs PCLK at 125 MHz (Gen1) or 250 MHz (Gen2)
self.comb += [
    self.cd_pcie.clk.eq(pipe_pads.pclk),
    self.cd_pcie.rst.eq(~pipe_pads.phy_status),  # Reset when PHY not ready
]

# Create endpoint (TLP layer) - identical to Xilinx example
endpoint = LitePCIeEndpoint(phy, address_width=32)
```

**Architecture:**

```
Application
     ↓ ↑
  TLP Layer (sys_clk)
     ↓ ↑ PHYTXDatapath/PHYRXDatapath CDC
┌──────────────────────────────┐
│  PIPEExternalPHY             │
│  (Open-source DLL + PIPE)    │
│                              │
│  • DLLTX/DLLRX               │
│  • LTSSM                     │
│  • PIPE interface            │
│  • pcie_clk domain           │
└──────────────────────────────┘
     ↓ ↑ PIPE signals (8-bit, pcie_clk)
     ↓ ↑ tx_data, rx_data, tx_datak, rx_datak, etc.
┌──────────────────────────────┐
│  TI TUSB1310A                │ External chip on PCB
│  (PIPE PHY)                  │
│                              │
│  • PIPE→PCIe conversion      │
│  • 8b/10b encode/decode      │
│  • Analog PHY                │
│  • Outputs PCLK              │
└──────────────────────────────┘
     ↓ ↑
  PCIe Link
```

**PCB Connections (PIPE interface):**
- PCLK: 125/250 MHz clock from TUSB1310A to FPGA
- TX_DATA[7:0]: 8-bit symbols from FPGA to PHY
- TX_DATAK: K-character flag from FPGA
- RX_DATA[7:0]: 8-bit symbols from PHY to FPGA
- RX_DATAK: K-character flag from PHY
- PHY_STATUS: Ready indication from PHY
- Power, reset, configuration pins

### Example 3: ECP5 with Internal SERDES (Fully Open-Source)

**Platform:** Lattice ECP5-5G (LFE5UM5G-85F)
**Toolchain:** Open-source (Yosys + nextpnr-ecp5)
**PHY:** Internal ECP5 DCUA SERDES

```python
from litepcie.phy.ecp5_serdes import ECP5SerDesPHY

# Platform setup
pcie_pads = platform.request("pcie_x1")  # Direct PCIe connector (no external PHY)

# Create PHY wrapper using internal SERDES
phy = ECP5SerDesPHY(
    platform    = platform,
    pads        = pcie_pads,
    data_width  = 64,
    cd          = "sys",
    bar0_size   = 0x100000,
    dcu         = 0,       # Which DCU to use (0 or 1)
    channel     = 0,       # Which channel (0 or 1)
    gen         = 1,       # Gen1 (2.5 GT/s) - Gen2 experimental on ECP5
)

# Platform creates "pcie" clock domain from TXOUTCLK
# This is done automatically by ECP5SerDesPHY

# Create endpoint (TLP layer) - identical to previous examples
endpoint = LitePCIeEndpoint(phy, address_width=32)
```

**Architecture:**

```
Application
     ↓ ↑
  TLP Layer (sys_clk)
     ↓ ↑ PHYTXDatapath/PHYRXDatapath CDC
┌──────────────────────────────────┐
│  ECP5SerDesPHY                   │
│  (Open-source DLL + PIPE +       │
│   Transceiver wrapper)           │
│                                  │
│  pcie_clk domain:                │
│  • DLLTX/DLLRX                   │
│  • LTSSM                         │
│  • PIPE interface                │
│                                  │
│  tx_clk/rx_clk domains:          │
│  • 8b/10b encoder (software)     │
│  • 8b/10b decoder (software)     │
│  • TransceiverTXDatapath CDC     │
│  • TransceiverRXDatapath CDC     │
└──────────────────────────────────┘
     ↓ ↑ 10-bit encoded symbols
┌──────────────────────────────────┐
│  ECP5 DCUA Primitive             │ On-chip SERDES
│                                  │
│  • Serialization (20→1 bits)     │
│  • Deserialization (1→20 bits)   │
│  • CDR (clock recovery)          │
│  • Outputs TXOUTCLK, RXOUTCLK    │
└──────────────────────────────────┘
     ↓ ↑ Differential serial
  PCIe Link
```

**Key Differences:**
- **No external PHY chip** - fully integrated
- **Multiple clock domains** - sys, pcie, tx, rx
- **Software 8b/10b** - required (ECP5 has no hardware 8b/10b)
- **Full open-source** - works with nextpnr!

### Example 4: Xilinx 7-Series with Internal GTX

**Platform:** Xilinx 7-Series (with GTX transceivers)
**Toolchain:** Xilinx Vivado or OpenXC7 (experimental)
**PHY:** Internal GTX transceivers

```python
from litepcie.phy.xilinx_gtx import S7GTXTransceiverPHY

# Platform setup
pcie_pads = platform.request("pcie_x1")  # Direct PCIe connector

# Create PHY wrapper using GTX transceiver
phy = S7GTXTransceiverPHY(
    platform    = platform,
    pads        = pcie_pads,
    data_width  = 64,
    cd          = "sys",
    bar0_size   = 0x100000,
    refclk_freq = 100e6,   # 100 MHz reference clock
    gen         = 2,        # Gen2 (5.0 GT/s)
)

# Create endpoint
endpoint = LitePCIeEndpoint(phy, address_width=32)
```

**Architecture:** Similar to ECP5 example but using Xilinx GTX primitives.

### Integration Comparison Summary

| Feature | Vendor Hard IP | External PIPE PHY | Internal Transceiver |
|---------|----------------|-------------------|----------------------|
| **Resource Usage** | Low (hard IP) | Medium (DLL in fabric) | High (DLL + transceiver mgmt) |
| **PCB Complexity** | Simple (direct connector) | Medium (PIPE chip) | Simple (direct connector) |
| **Open-Source Friendly** | No | Yes | Yes |
| **Toolchain Support** | Vendor only | All | Vendor + OpenXC7/nextpnr |
| **Performance** | Highest | High | High (if tuned correctly) |
| **Visibility/Debug** | Limited | Full | Full |
| **Cost** | License fees | External chip | No extra cost |

---

## Error Handling Across Layers

Errors can occur at any layer and must be properly propagated and handled.

### Error Propagation Flow

```
┌─────────────────────────────────────────────────────────────┐
│                   Error Types by Layer                       │
└─────────────────────────────────────────────────────────────┘

SERDES Layer Errors:
  • PLL unlock
  • CDR lock loss
  • Signal detect loss
  • Disparity errors
     ↓ Propagates to

Transceiver Base Layer:
  • rx_valid = 0 (8b/10b decode error)
  • tx_ready = 0 (TX not operational)
  • rx_ready = 0 (RX not operational)
     ↓ Propagates to

PIPE Layer Errors:
  • Invalid K-character
  • Framing error (unexpected END)
  • Symbol decode error
     ↓ Propagates to

DLL Layer Errors:
  • LCRC mismatch
  • Sequence number mismatch
  • Timeout (no ACK received)
  • LTSSM training failure
     ↓ Generates NAK DLLP or retry
     ↓ Propagates to (if unrecoverable)

TLP Layer Errors:
  • Completion timeout
  • Unsupported request
  • Completer abort
     ↓ Propagates to

Application Layer:
  • Error completion status
  • Transaction failure
```

### Error Handling Example: LCRC Failure

```
Time    TX Side                        Link                    RX Side
────────────────────────────────────────────────────────────────────────
t=0     Send TLP (seq=100)             ──────────────────────►
        Store in retry buffer
        Start ACK timeout timer

t=1                                                            Receive TLP
                                                               Calculate LCRC
                                                               LCRC MISMATCH!

t=2                                    ◄──────────────────────  Send NAK DLLP
                                       NAK (last_good=99)      (seq=99)

t=3     Receive NAK (seq=99)
        Lookup retry buffer
        Found unACKed seq 100

t=4     Replay from buffer             ──────────────────────►
        Send TLP (seq=100)             (Retry attempt)
        Reset timeout timer

t=5                                                            Receive TLP
                                                               Calculate LCRC
                                                               LCRC MATCH!

t=6                                    ◄──────────────────────  Send ACK DLLP
                                       ACK (seq=100)           (seq=100)

t=7     Receive ACK (seq=100)
        Release retry buffer[100]
        Continue normal operation
```

### Error Recovery Mechanisms by Layer

#### SERDES Layer Error Recovery

```
Error: PLL Unlock Detected

Recovery:
  1. Reset sequencer detects pll_lock = 0
  2. Transition to PLL_LOCK state
  3. Assert PLL reset
  4. Wait for PLL to relock (timeout: 1ms)
  5. If success: Continue to TX_READY
  6. If failure: Retry or signal fatal error to application
```

#### LTSSM Error Recovery

```
Error: Link Training Timeout in POLLING state

Recovery:
  1. LTSSM detects no TS1 received within timeout (24ms)
  2. Transition to DETECT state
  3. Perform receiver detection
  4. If receiver present: Re-enter POLLING
  5. If no receiver: Report link down to application
```

#### DLL Error Recovery

```
Error: Retry Buffer Exhausted (too many unACKed TLPs)

Recovery:
  1. DLL TX detects buffer full (4KB limit)
  2. Assert flow control back-pressure to TLP layer
  3. Stop accepting new TLPs
  4. Wait for ACKs to free buffer space
  5. Resume when buffer space available

Prevention:
  • Monitor ACK latency
  • Alert application if consistently high
  • May indicate link quality issues
```

---

## Performance Considerations

### Throughput Analysis

#### Theoretical Maximum (Gen2 x1)

```
Line Rate: 5.0 GT/s (Gigatransfers/second)
8b/10b Overhead: 5.0 × 8/10 = 4.0 Gb/s raw bandwidth

Protocol Overhead:
  • TLP header: 3-4 DW (12-16 bytes) per TLP
  • LCRC: 4 bytes per TLP
  • DLLP (ACK): 8 bytes per N TLPs
  • Framing: STP(1) + END(1) = 2 bytes per TLP
  • SKP: 4 bytes per ~1180 symbols (~0.3% overhead)

Example: 64-byte payload TLPs
  Header: 12 bytes (3 DW)
  Data: 64 bytes
  LCRC: 4 bytes
  Framing: 2 bytes
  Total: 82 bytes transmitted for 64 bytes payload
  Efficiency: 64/82 = 78%

Effective throughput: 4.0 Gb/s × 0.78 = 3.12 Gb/s = 390 MB/s
```

#### Practical Throughput

Measured throughput depends on:
1. **TLP Size:** Larger TLPs amortize header overhead
2. **Read vs. Write:** Writes are posted (no completion), reads require completion
3. **Credit Availability:** Flow control can stall transmission
4. **LTSSM State:** Only L0 allows data transfer
5. **Retry Rate:** NAKs cause retransmissions

```
Best case (large writes): ~380 MB/s (95% of theoretical)
Typical case (mixed traffic): ~320 MB/s (80% of theoretical)
Worst case (small reads): ~200 MB/s (50% of theoretical)
```

### Latency Budget

End-to-end latency for a single TLP (memory write):

```
Component                        Latency (cycles @ 125 MHz)  Time (ns)
────────────────────────────────────────────────────────────────────
Application → TLP packetizer              2-4                16-32
TLP packetizer processing                 1-2                8-16
PHYTXDatapath CDC (sys→pcie)              4-8                32-64
DLL TX (seq + LCRC)                       8-16               64-128
DLL → PIPE                                1-2                8-16
PIPE TX packetizer                        2-4                16-32
PIPE → Transceiver CDC (pcie→tx)          4-8                32-64
8b/10b encoding                           1                  8
Transceiver TX serialization              2-4                16-32
──────────────────────────────────────────────────────────────────
TX Path Total:                            25-49              200-392

Physical propagation (6" trace)           -                  ~100
Remote device processing                  -                  Variable

RX Path (similar to TX):                  25-49              200-392
──────────────────────────────────────────────────────────────────
Round-trip latency (minimum):             50-98 + prop       ~1 μs
```

### Optimization Strategies

#### 1. Increase TLP Size

```python
# Configure larger max payload size (if supported by remote device)
endpoint.configure_max_payload_size(512)  # vs. default 128

Impact:
  • Reduces header overhead
  • Increases throughput by ~10-15%
  • May reduce latency for large transfers
```

#### 2. Pipeline Datapaths

```python
# Increase AsyncFIFO depth for burst tolerance
self.cdc = stream.AsyncFIFO(
    layout = phy_layout(data_width),
    depth = 32,  # vs. default 8
    buffered = True
)

Impact:
  • Absorbs burst traffic
  • Reduces back-pressure stalls
  • Increases throughput by ~5%
```

#### 3. Optimize Credit Management

```python
# Advertise larger receive buffer (more credits)
dll.configure_flow_control_credits(
    posted_header = 256,     # vs. default 128
    posted_data = 2048,      # vs. default 1024
)

Impact:
  • Remote can send more TLPs before stalling
  • Increases sustained throughput
  • Requires larger DLL receive buffer
```

#### 4. Reduce Retry Buffer Latency

```python
# Faster ACK generation
dll_rx.configure_ack_latency(
    cycles = 4  # vs. default 8
)

Impact:
  • Faster buffer release on TX side
  • Allows more in-flight TLPs
  • Increases sustained throughput
```

---

## Related Documentation

### Layer-Specific Documentation
- [Complete System Architecture](complete-system-architecture.md) - Full stack overview
- [SERDES Layer Architecture](serdes-layer.md) - Physical transceiver layer
- [PIPE Layer Architecture](pipe-layer.md) - PIPE interface protocol
- [DLL Layer Architecture](dll-layer.md) - Data Link Layer with LTSSM
- [TLP Layer Architecture](tlp-layer.md) - Transaction Layer Packets

### Implementation Documentation
- [PIPE Architecture](pipe-architecture.md) - PIPE component details
- [Clock Domain Architecture](clock-domain-architecture.md) - Clock strategy (detailed)
- [Integration Strategy](integration-strategy.md) - Integration roadmap

### Guides
- [PIPE Integration Examples](../guides/pipe-integration-examples.md) - Practical integration examples
- [PIPE Interface Guide](../guides/pipe-interface-guide.md) - User guide and API reference

---

**Document Version:** 1.0
**Last Updated:** 2025-10-18
**Status:** Complete and Comprehensive
