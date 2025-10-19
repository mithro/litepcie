# PIPE Interface Layer Architecture

**Layer:** PHY Interface (Layer 2)
**Location:** `litepcie/dll/pipe.py`
**Purpose:** MAC/PHY boundary - converts between DLL packets and 8-bit PIPE symbols

## Overview

The PIPE (PHY Interface for PCI Express) layer provides the boundary between the Data Link Layer (MAC) and the Physical Layer (PHY). This interface abstracts the physical layer details and provides a standardized way to transmit and receive PCIe packets.

### Key Responsibilities

1. **Packetization:** Convert 64-bit DLL packets into 8-bit PIPE symbols
2. **Depacketization:** Convert 8-bit PIPE symbols back into 64-bit DLL packets
3. **Framing:** Add K-character based START/END framing to packets
4. **Ordered Sets:** Generate and detect SKP, TS1, TS2 ordered sets
5. **Clock Compensation:** Insert SKP ordered sets for clock tolerance

### PIPE Specification

Based on Intel PIPE 3.0 Specification for Gen1/Gen2 operation:
- **Data Width:** 8 bits (Gen1: 2.5 GT/s, Gen2: 5.0 GT/s)
- **Symbol Encoding:** 8b/10b with K-characters
- **Clock:** PCLK at 125 MHz (Gen1) or 250 MHz (Gen2)

### Position in PCIe Stack

```
┌────────────────────────────────────────────────────────────┐
│                 Data Link Layer (DLL)                      │
│                                                            │
│  • LCRC generation/checking                                │
│  • ACK/NAK protocol                                        │
│  • Retry buffer                                            │
│  • DLLP processing                                         │
└────────────────────┬───────────────────────────────────────┘
                     │ 64-bit packets (phy_layout)
                     │ Stream: valid, first, last, dat[63:0]
                     ▼
┌────────────────────────────────────────────────────────────┐
│              PIPE INTERFACE LAYER (THIS LAYER)             │
│                                                            │
│  ┌──────────────────┐         ┌──────────────────┐         │
│  │ TX Packetizer    │         │ RX Depacketizer  │         │
│  │ 64→8 bit convert │         │ 8→64 bit convert │         │
│  └──────────────────┘         └──────────────────┘         │
│                                                            │
│  Ordered Sets: SKP, TS1, TS2 generation/detection          │
└────────────────────┬───────────────────────────────────────┘
                     │ 8-bit PIPE symbols + control
                     │ tx_data[7:0], tx_datak, tx_elecidle
                     │ rx_data[7:0], rx_datak, rx_valid
                     ▼
┌────────────────────────────────────────────────────────────┐
│                    Physical Layer (PHY)                    │
│                                                            │
│  • 8b/10b encoding/decoding                                │
│  • Serializer/Deserializer                                 │
│  • Clock recovery (CDR)                                    │
└────────────────────────────────────────────────────────────┘
```

---

## PIPE Interface Components

### Complete Interface Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                       PIPEInterface                             │
│                  Location: litepcie/dll/pipe.py                 │
│                                                                 │
│  DLL-facing Interface (packet-based, 64-bit)                    │
│  ════════════════════════════════════════════                   │
│                                                                 │
│  dll_tx_sink (input)                dll_rx_source (output)      │
│    • valid, first, last               • valid, first, last      │
│    • dat[63:0]                        • dat[63:0]               │
│                                                                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                    TX PATH                                 │ │
│  │                                                            │ │
│  │   dll_tx_sink                                              │ │
│  │        │                                                   │ │
│  │        ▼                                                   │ │
│  │   ┌────────────────────────────────┐                       │ │
│  │   │   PIPETXPacketizer             │                       │ │
│  │   │                                │                       │ │
│  │   │  FSM States:                   │                       │ │
│  │   │  • IDLE → DATA → END           │                       │ │
│  │   │  • SKP (clock compensation)    │                       │ │
│  │   │  • TS (training sequences)     │                       │ │
│  │   │                                │                       │ │
│  │   │  Functions:                    │                       │ │
│  │   │  • Detect packet type          │                       │ │
│  │   │  • Send STP/SDP framing        │                       │ │
│  │   │  • Serialize 64→8 bits         │                       │ │
│  │   │  • Send END symbol             │                       │ │
│  │   │  • Generate SKP (1180 symbols) │                       │ │
│  │   │  • Generate TS1/TS2 on demand  │                       │ │
│  │   └────────────┬───────────────────┘                       │ │
│  │                │                                           │ │
│  │                ▼                                           │ │
│  │   pipe_tx_data[7:0] ──────────────────────►                │ │
│  │   pipe_tx_datak ───────────────────────────►               │ │
│  │   pipe_tx_elecidle ────────────────────────►               │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                    RX PATH                                 │ │
│  │                                                            │ │
│  │   pipe_rx_data[7:0] ◄──────────────────────                │ │
│  │   pipe_rx_datak ◄───────────────────────────               │ │
│  │   pipe_rx_valid ◄───────────────────────────               │ │
│  │                │                                           │ │
│  │                ▼                                           │ │
│  │   ┌────────────────────────────────┐                       │ │
│  │   │   PIPERXDepacketizer           │                       │ │
│  │   │                                │                       │ │
│  │   │  FSM States:                   │                       │ │
│  │   │  • IDLE → DATA                 │                       │ │
│  │   │  • SKP_CHECK (filter SKP)      │                       │ │
│  │   │  • TS_CHECK (detect TS1/TS2)   │                       │ │
│  │   │                                │                       │ │
│  │   │  Functions:                    │                       │ │
│  │   │  • Detect STP/SDP framing      │                       │ │
│  │   │  • Accumulate 8→64 bits        │                       │ │
│  │   │  • Detect END symbol           │                       │ │
│  │   │  • Filter SKP ordered sets     │                       │ │
│  │   │  • Detect TS1/TS2 patterns     │                       │ │
│  │   └────────────┬───────────────────┘                       │ │
│  │                │                                           │ │
│  │                ▼                                           │ │
│  │   dll_rx_source                                            │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                 │
│  PIPE-facing Interface (8-bit symbols)                          │
│  ══════════════════════════════════════                         │
│                                                                 │
│  TX Signals (MAC → PHY):          RX Signals (PHY → MAC):       │
│    • tx_data[7:0]                   • rx_data[7:0]              │
│    • tx_datak                       • rx_datak                  │
│    • tx_elecidle                    • rx_valid                  │
│                                     • rx_status[2:0]            │
│                                     • rx_elecidle               │
│                                                                 │
│  Control Signals (MAC → PHY):                                   │
│    • powerdown[1:0]  (P0/P0s/P1/P2 states)                      │
│    • rate            (Gen1/Gen2 speed)                          │
│    • rx_polarity     (RX polarity inversion)                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## TX Packetizer Architecture

### TX Packetizer FSM

```
┌─────────────────────────────────────────────────────────────────┐
│                     PIPETXPacketizer                            │
│                                                                 │
│  INPUT: sink (64-bit DLL packets)                               │
│    • sink.valid, sink.first, sink.last                          │
│    • sink.dat[63:0]                                             │
│                                                                 │
│  OUTPUT: PIPE TX symbols (8-bit)                                │
│    • pipe_tx_data[7:0]                                          │
│    • pipe_tx_datak (K-character indicator)                      │
│                                                                 │
│  CONTROL: Ordered set generation                                │
│    • enable_skp (SKP insertion)                                 │
│    • enable_training_sequences (TS1/TS2)                        │
│    • send_ts1, send_ts2 (manual triggers)                       │
│                                                                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                       FSM FLOW                             │ │
│  │                                                            │ │
│  │        ┌──────────────────┐                                │ │
│  │   ┌───►│   IDLE State     │◄───┐                           │ │
│  │   │    │                  │    │                           │ │
│  │   │    │  Priority check: │    │                           │ │
│  │   │    │  1. send_ts1?    │    │                           │ │
│  │   │    │  2. send_ts2?    │    │                           │ │
│  │   │    │  3. skp_counter  │    │                           │ │
│  │   │    │     >= interval? │    │                           │ │
│  │   │    │  4. sink.valid & │    │                           │ │
│  │   │    │     sink.first?  │    │                           │ │
│  │   │    │                  │    │                           │ │
│  │   │    │  Default output: │    │                           │ │
│  │   │    │  tx_data = 0x00  │    │                           │ │
│  │   │    │  tx_datak = 0    │    │                           │ │
│  │   │    └────┬──┬──┬───┬───┘    │                           │ │
│  │   │         │  │  │   │        │                           │ │
│  │   │    TS1  │  │  │   │ Packet │                           │ │
│  │   │         │  │  │   │        │                           │ │
│  │   │    ┌────▼──┴──▼───┴────┐   │                           │ │
│  │   │    │   TS State        │   │                           │ │
│  │   │    │                   │   │                           │ │
│  │   │    │  Send 16 symbols: │   │                           │ │
│  │   │    │  [0] COM (K=1)    │   │                           │ │
│  │   │    │  [1-15] Data(K=0) │   │                           │ │
│  │   │    │                   │   │                           │ │
│  │   │    │  TS1: D10.2 ID    │   │                           │ │
│  │   │    │  TS2: D5.2 ID     │   │                           │ │
│  │   │    └───────────────────┘   │                           │ │
│  │   │             │              │                           │ │
│  │   │    After 16 symbols        │                           │ │
│  │   │             │              │                           │ │
│  │   └─────────────┘               │                          │ │
│  │                                 │                          │ │
│  │         SKP                     │                          │ │
│  │          │                      │                          │ │
│  │     ┌────▼─────────┐            │                          │ │
│  │     │  SKP State   │            │                          │ │
│  │     │              │            │                          │ │
│  │     │  Send 4 sym: │            │                          │ │
│  │     │  COM, SKP,   │            │                          │ │
│  │     │  SKP, SKP    │            │                          │ │
│  │     │  (all K=1)   │            │                          │ │
│  │     └──────────────┘            │                          │ │
│  │          │                      │                          │ │
│  │     After 4 symbols             │                          │ │
│  │          │                      │                          │ │
│  │          └──────────────────────┘                          │ │
│  │                                                            │ │
│  │                Packet                                      │ │
│  │                  │                                         │ │
│  │        ┌─────────▼─────────┐                               │ │
│  │        │  Packet Type      │                               │ │
│  │        │  Detection        │                               │ │
│  │        │                   │                               │ │
│  │        │  first_byte =     │                               │ │
│  │        │  sink.dat[7:0]    │                               │ │
│  │        │                   │                               │ │
│  │        │  is_dllp =        │                               │ │
│  │        │  (first_byte &    │                               │ │
│  │        │   0xC0) == 0x00   │                               │ │
│  │        └─────┬───────┬─────┘                               │ │
│  │              │       │                                     │ │
│  │         DLLP │       │ TLP                                 │ │
│  │              │       │                                     │ │
│  │        ┌─────▼───────▼─────┐                               │ │
│  │        │   Send START      │                               │ │
│  │        │                   │                               │ │
│  │        │  If is_dllp:      │                               │ │
│  │        │    tx_data = SDP  │  SDP = 0x5C                   │ │
│  │        │           (0x5C)  │  K=1                          │ │
│  │        │  Else:            │                               │ │
│  │        │    tx_data = STP  │  STP = 0xFB                   │ │
│  │        │           (0xFB)  │  K=1                          │ │
│  │        │  tx_datak = 1     │                               │ │
│  │        │  byte_counter=0   │                               │ │
│  │        └─────────┬─────────┘                               │ │
│  │                  │                                         │ │
│  │                  ▼                                         │ │
│  │        ┌──────────────────┐                                │ │
│  │   ┌───►│   DATA State     │                                │ │
│  │   │    │                  │                                │ │
│  │   │    │  Send byte from  │                                │ │
│  │   │    │  sink.dat:       │                                │ │
│  │   │    │                  │                                │ │
│  │   │    │  tx_data =       │                                │ │
│  │   │    │   byte_array[    │                                │ │
│  │   │    │   byte_counter]  │                                │ │
│  │   │    │  tx_datak = 0    │  Data byte (not K-char)        │ │
│  │   │    │                  │                                │ │
│  │   │    │  byte_counter++  │                                │ │
│  │   │    └────────┬─────────┘                                │ │
│  │   │             │                                          │ │
│  │   │ Loop 8x     │ After 8 bytes                            │ │
│  │   │ (0-7)       │ (counter == 7)                           │ │
│  │   │             │                                          │ │
│  │   └─────────────┘                                          │ │
│  │                 │                                          │ │
│  │                 ▼                                          │ │
│  │        ┌──────────────────┐                                │ │
│  │        │   END State      │                                │ │
│  │        │                  │                                │ │
│  │        │  Send END:       │                                │ │
│  │        │  tx_data = END   │  END = 0xFD                    │ │
│  │        │         (0xFD)   │  K=1                           │ │
│  │        │  tx_datak = 1    │                                │ │
│  │        └────────┬─────────┘                                │ │
│  │                 │                                          │ │
│  │                 │ Return to IDLE                           │ │
│  │                 │                                          │ │
│  │                 └──────────────────────────────────────►   │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### TX Byte Serialization

```
┌────────────────────────────────────────────────────────────┐
│              BYTE ARRAY MAPPING (Little-Endian)            │
│                                                            │
│   Input: sink.dat[63:0]  (64-bit DLL packet word)          │
│                                                            │
│   Transmission Order (LSB first):                          │
│                                                            │
│   Cycle 1: dat[7:0]   = Byte 0 (LSB) ──► Sent first        │
│   Cycle 2: dat[15:8]  = Byte 1       ──► Sent second       │
│   Cycle 3: dat[23:16] = Byte 2       ──► Sent third        │
│   Cycle 4: dat[31:24] = Byte 3       ──► Sent fourth       │
│   Cycle 5: dat[39:32] = Byte 4       ──► Sent fifth        │
│   Cycle 6: dat[47:40] = Byte 5       ──► Sent sixth        │
│   Cycle 7: dat[55:48] = Byte 6       ──► Sent seventh      │
│   Cycle 8: dat[63:56] = Byte 7 (MSB) ──► Sent last         │
│                                                            │
│   Total: 8 data symbols per 64-bit word                    │
└────────────────────────────────────────────────────────────┘
```

---

## RX Depacketizer Architecture

### RX Depacketizer FSM

```
┌─────────────────────────────────────────────────────────────────┐
│                    PIPERXDepacketizer                           │
│                                                                 │
│  INPUT: PIPE RX symbols (8-bit)                                 │
│    • pipe_rx_data[7:0]                                          │
│    • pipe_rx_datak (K-character indicator)                      │
│                                                                 │
│  OUTPUT: source (64-bit DLL packets)                            │
│    • source.valid, source.first, source.last                    │
│    • source.dat[63:0]                                           │
│                                                                 │
│  STATUS: Ordered set detection                                  │
│    • ts1_detected (TS1 ordered set detected)                    │
│    • ts2_detected (TS2 ordered set detected)                    │
│                                                                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                       FSM FLOW                             │ │
│  │                                                            │ │
│  │        ┌──────────────────┐                                │ │
│  │   ┌───►│   IDLE State     │◄─────────┐                     │ │
│  │   │    │                  │          │                     │ │
│  │   │    │  Wait for START  │          │                     │ │
│  │   │    │  K-character:    │          │                     │ │
│  │   │    │  • STP (0xFB)    │  TLP     │                     │ │
│  │   │    │  • SDP (0x5C)    │  DLLP    │                     │ │
│  │   │    │  • COM (0xBC)    │  Check   │                     │ │
│  │   │    └──┬──┬──┬─────────┘          │                     │ │
│  │   │       │  │  │                    │                     │ │
│  │   │   STP │  │  │ COM                │                     │ │
│  │   │   SDP │  │  │                    │                     │ │
│  │   │       │  │  │                    │                     │ │
│  │   │       │  │  └─────────┐          │                     │ │
│  │   │       │  │            │          │                     │ │
│  │   │       │  │       ┌────▼───────┐  │                     │ │
│  │   │       │  │       │ SKP_CHECK  │  │                     │ │
│  │   │       │  │       │            │  │                     │ │
│  │   │       │  │       │  Verify 3  │  │                     │ │
│  │   │       │  │       │  SKP syms  │  │                     │ │
│  │   │       │  │       │  following │  │                     │ │
│  │   │       │  │       │  COM       │  │                     │ │
│  │   │       │  │       │            │  │                     │ │
│  │   │       │  │       │  Filter if │  │                     │ │
│  │   │       │  │       │  valid SKP │  │                     │ │
│  │   │       │  │       └────────────┘  │                     │ │
│  │   │       │  │            │          │                     │ │
│  │   │       │  │     After 3 SKP       │                     │ │
│  │   │       │  │            │          │                     │ │
│  │   │       │                                                  │            └──────────┘                     │ │
│  │   │       │  │                                               │                       │
│  │   │       │                                                  │  (enable_training_sequences)                │ │
│  │   │       │  │                                               │                       │
│  │   │                                  │  └────────────┐     │ │
│  │   │       │                          │                     │ │
│  │   │       │          ┌────▼────────┐                         │                       │
│  │   │       │          │  TS_CHECK     │                     │ │
│  │   │                  │             │ │                     │ │
│  │   │       │          │  Buffer 16    │                     │ │
│  │   │       │          │  symbols      │                     │ │
│  │   │                  │             │ │                     │ │
│  │   │       │          │  Check for:   │                     │ │
│  │   │       │          │  • TS1 ID     │                     │ │
│  │   │       │          │    (D10.2)    │                     │ │
│  │   │       │          │  • TS2 ID     │                     │ │
│  │   │       │          │    (D5.2)     │                     │ │
│  │   │                  │             │ │                     │ │
│  │   │       │          │  Set flags:   │                     │ │
│  │   │       │          │  ts1/ts2      │                     │ │
│  │   │       │          │  _detected    │                     │ │
│  │   │       │          └─────────────┘                         │                       │
│  │   │       │                          │                     │ │
│  │   │       │        After 16 symbols                          │                       │
│  │   │       │                          │                     │ │
│  │   │                                                          │               └───────────────────────────────┘  │
│  │   │                                  │                     │ │
│  │   │                                  │ STP/SDP             │ │
│  │   │                                  │                     │ │
│  │   │  ┌────▼────────────┐                                     │                       │
│  │   │  │  START Detected               │                     │ │
│  │   │  │                               │                     │ │
│  │   │  │  is_tlp = 1 if                │                     │ │
│  │   │  │    rx_data==STP               │                     │ │
│  │   │  │  else is_tlp=0                │                     │ │
│  │   │  │                               │                     │ │
│  │   │  │  byte_counter=0               │                     │ │
│  │   │  │  data_buffer=0                │                     │ │
│  │   │  └────────┬────────┘                                     │                       │
│  │   │                                  │                     │ │
│  │   │           ▼                                              │                       │
│  │   │  ┌──────────────────┐                                    │                       │
│  │   │  │   DATA State                  │                     │ │
│  │   │  │                               │                     │ │
│  │   │  │  If rx_datak=0:               │  Data byte received │ │
│  │   │  │                               │                     │ │
│  │   │  │   Store byte in               │                     │ │
│  │   │  │   data_buffer:                │                     │ │
│  │   │  │                               │                     │ │
│  │   │  │   [7:0] ← byte0               │                     │ │
│  │   │  │   [15:8]← byte1               │                     │ │
│  │   │  │   ...                         │                     │ │
│  │   │  │   [63:56]←byte7               │                     │ │
│  │   │  │                               │                     │ │
│  │   │  │   byte_counter++              │                     │ │
│  │   │  │                               │                     │ │
│  │   │  │  If rx_datak=1:                                       │  K-character received │ │
│  │   │  │                               │                     │ │
│  │   │  │   If rx_data=END:             │                     │ │
│  │   │  │                               │                     │ │
│  │   │  │   • Output pkt                │                     │ │
│  │   │  │   • source.valid              │                     │ │
│  │   │  │     = 1                       │                     │ │
│  │   │  │   • source.first              │                     │ │
│  │   │  │     = 1                       │                     │ │
│  │   │  │   • source.last               │                     │ │
│  │   │  │     = 1                       │                     │ │
│  │   │  │   • source.dat =              │                     │ │
│  │   │  │     data_buffer               │                     │ │
│  │   │  │   • Go to IDLE                │                     │ │
│  │   │  └──────────────────┘                                    │                       │
│  │   │                                  │                     │ │
│  │   │    END detected                                          │                       │
│  │   │                                  │                     │ │
│  │   └───────────┘                                            │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### RX Byte Accumulation

```
┌────────────────────────────────────────────────────────────┐
│         DATA BUFFER ACCUMULATION (Little-Endian)           │
│                                                            │
│   Output: data_buffer[63:0]  (64-bit accumulation)         │
│                                                            │
│   Reception Order (LSB first):                             │
│                                                            │
│   Cycle 1: rx_data → buffer[7:0]   = Byte 0 (LSB)          │
│   Cycle 2: rx_data → buffer[15:8]  = Byte 1                │
│   Cycle 3: rx_data → buffer[23:16] = Byte 2                │
│   Cycle 4: rx_data → buffer[31:24] = Byte 3                │
│   Cycle 5: rx_data → buffer[39:32] = Byte 4                │
│   Cycle 6: rx_data → buffer[47:40] = Byte 5                │
│   Cycle 7: rx_data → buffer[55:48] = Byte 6                │
│   Cycle 8: rx_data → buffer[63:56] = Byte 7 (MSB)          │
│                                                            │
│   On END detection: source.dat ← data_buffer               │
└────────────────────────────────────────────────────────────┘
```

---

## Symbol Encoding Tables

### K-Character Encoding (8b/10b Special Codes)

PCIe uses specific K-characters from the 8b/10b encoding table for framing and ordered sets.

```
┌────────────────────────────────────────────────────────────────┐
│                  PCIe K-Character Encoding Table               │
├──────────┬─────────┬──────────┬─────────────────────────────────┤
│ Symbol   │ 8b Value│ K-Code   │ Purpose                        │
├──────────┼─────────┼──────────┼─────────────────────────────────┤
│ COM      │ 0xBC    │ K28.5    │ Comma - Lane alignment         │
│          │         │          │ Used in: SKP, TS1, TS2         │
├──────────┼─────────┼──────────┼─────────────────────────────────┤
│ SKP      │ 0x1C    │ K28.0    │ Skip - Clock compensation      │
│          │         │          │ Used in: SKP ordered set       │
├──────────┼─────────┼──────────┼─────────────────────────────────┤
│ STP      │ 0xFB    │ K27.7    │ Start TLP - Begins TLP packet  │
│          │         │          │ Framing: Start of TLP          │
├──────────┼─────────┼──────────┼─────────────────────────────────┤
│ SDP      │ 0x5C    │ K28.2    │ Start DLLP - Begins DLLP packet│
│          │         │          │ Framing: Start of DLLP         │
├──────────┼─────────┼──────────┼─────────────────────────────────┤
│ END      │ 0xFD    │ K29.7    │ End - Packet termination       │
│          │         │          │ Framing: End of TLP/DLLP       │
├──────────┼─────────┼──────────┼─────────────────────────────────┤
│ EDB      │ 0xFE    │ K30.7    │ End Bad - Bad packet marker    │
│          │         │          │ (Not yet implemented)          │
├──────────┼─────────┼──────────┼─────────────────────────────────┤
│ PAD      │ 0xF7    │ K23.7    │ Pad - Link idle fill           │
│          │         │          │ (Future use)                   │
└──────────┴─────────┴──────────┴─────────────────────────────────┘
```

### Packet Framing Examples

```
┌────────────────────────────────────────────────────────────┐
│                  TLP Packet Framing                        │
│                                                            │
│   Symbol  │ Data   │ K │ Description                       │
│   ────────┼────────┼───┼──────────────────────────────     │
│   0       │ 0xFB   │ 1 │ STP (Start TLP)                   │
│   1       │ 0xXX   │ 0 │ TLP Byte 0 (Header/Data)          │
│   2       │ 0xXX   │ 0 │ TLP Byte 1                        │
│   3       │ 0xXX   │ 0 │ TLP Byte 2                        │
│   4       │ 0xXX   │ 0 │ TLP Byte 3                        │
│   5       │ 0xXX   │ 0 │ TLP Byte 4                        │
│   6       │ 0xXX   │ 0 │ TLP Byte 5                        │
│   7       │ 0xXX   │ 0 │ TLP Byte 6                        │
│   8       │ 0xXX   │ 0 │ TLP Byte 7                        │
│   9       │ 0xFD   │ 1 │ END (End packet)                  │
│                                                            │
│   Total: 10 symbols for 8-byte TLP                         │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│                 DLLP Packet Framing                        │
│                                                            │
│   Symbol  │ Data   │ K │ Description                       │
│   ────────┼────────┼───┼──────────────────────────────     │
│   0       │ 0x5C   │ 1 │ SDP (Start DLLP)                  │
│   1       │ 0xXX   │ 0 │ DLLP Byte 0 (Type)                │
│   2       │ 0xXX   │ 0 │ DLLP Byte 1                       │
│   3       │ 0xXX   │ 0 │ DLLP Byte 2                       │
│   4       │ 0xXX   │ 0 │ DLLP Byte 3                       │
│   5       │ 0xXX   │ 0 │ DLLP Byte 4                       │
│   6       │ 0xXX   │ 0 │ DLLP Byte 5                       │
│   7       │ 0xXX   │ 0 │ DLLP Byte 6                       │
│   8       │ 0xXX   │ 0 │ DLLP Byte 7 (CRC)                 │
│   9       │ 0xFD   │ 1 │ END (End packet)                  │
│                                                            │
│   Total: 10 symbols for 8-byte DLLP                        │
└────────────────────────────────────────────────────────────┘
```

### Ordered Set Structures

```
┌────────────────────────────────────────────────────────────┐
│              SKP Ordered Set (Clock Compensation)          │
│                                                            │
│   Symbol  │ Data   │ K │ Description                       │
│   ────────┼────────┼───┼──────────────────────────────     │
│   0       │ 0xBC   │ 1 │ COM (K28.5) - Alignment           │
│   1       │ 0x1C   │ 1 │ SKP (K28.0)                       │
│   2       │ 0x1C   │ 1 │ SKP (K28.0)                       │
│   3       │ 0x1C   │ 1 │ SKP (K28.0)                       │
│                                                            │
│   Total: 4 symbols                                         │
│   Insertion: Every 1180-1538 symbols (configurable)        │
│   Purpose: PHY elastic buffer management                   │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│           TS1 Ordered Set (Training Sequence 1)            │
│                                                            │
│   Symbol  │ Data   │ K │ Description                       │
│   ────────┼────────┼───┼──────────────────────────────     │
│   0       │ 0xBC   │ 1 │ COM (K28.5) - Alignment           │
│   1       │ 0xXX   │ 0 │ Link Number                       │
│   2       │ 0xXX   │ 0 │ Lane Number                       │
│   3       │ 0xXX   │ 0 │ N_FTS (Fast Training Seq count)   │
│   4       │ 0xXX   │ 0 │ Rate ID (1=Gen1, 2=Gen2)          │
│   5       │ 0x00   │ 0 │ Training Control 0                │
│   6       │ 0x00   │ 0 │ Training Control 1                │
│   7       │ 0x4A   │ 0 │ TS1 Identifier (D10.2)            │
│   8       │ 0x4A   │ 0 │ TS1 Identifier (D10.2)            │
│   9       │ 0x4A   │ 0 │ TS1 Identifier (D10.2)            │
│   10      │ 0x4A   │ 0 │ TS1 Identifier (D10.2)            │
│   11      │ 0x4A   │ 0 │ TS1 Identifier (D10.2)            │
│   12      │ 0x4A   │ 0 │ TS1 Identifier (D10.2)            │
│   13      │ 0x4A   │ 0 │ TS1 Identifier (D10.2)            │
│   14      │ 0x4A   │ 0 │ TS1 Identifier (D10.2)            │
│   15      │ 0x4A   │ 0 │ TS1 Identifier (D10.2)            │
│                                                            │
│   Total: 16 symbols                                        │
│   Purpose: Link training, speed negotiation                │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│           TS2 Ordered Set (Training Sequence 2)            │
│                                                            │
│   Symbol  │ Data   │ K │ Description                       │
│   ────────┼────────┼───┼──────────────────────────────     │
│   0       │ 0xBC   │ 1 │ COM (K28.5) - Alignment           │
│   1       │ 0xXX   │ 0 │ Link Number                       │
│   2       │ 0xXX   │ 0 │ Lane Number                       │
│   3       │ 0xXX   │ 0 │ N_FTS (Fast Training Seq count)   │
│   4       │ 0xXX   │ 0 │ Rate ID (1=Gen1, 2=Gen2)          │
│   5       │ 0x00   │ 0 │ Training Control 0                │
│   6       │ 0x00   │ 0 │ Training Control 1                │
│   7       │ 0x45   │ 0 │ TS2 Identifier (D5.2)             │
│   8       │ 0x45   │ 0 │ TS2 Identifier (D5.2)             │
│   9       │ 0x45   │ 0 │ TS2 Identifier (D5.2)             │
│   10      │ 0x45   │ 0 │ TS2 Identifier (D5.2)             │
│   11      │ 0x45   │ 0 │ TS2 Identifier (D5.2)             │
│   12      │ 0x45   │ 0 │ TS2 Identifier (D5.2)             │
│   13      │ 0x45   │ 0 │ TS2 Identifier (D5.2)             │
│   14      │ 0x45   │ 0 │ TS2 Identifier (D5.2)             │
│   15      │ 0x45   │ 0 │ TS2 Identifier (D5.2)             │
│                                                            │
│   Total: 16 symbols                                        │
│   Purpose: Configuration lock, final training              │
└────────────────────────────────────────────────────────────┘
```

---

## Timing Diagrams

### Complete TX → RX Data Flow (TLP Packet)

```
Cycle: 0    1    2    3    4    5    6    7    8    9    10   11   12   13
       ───┬────┬────┬────┬────┬────┬────┬────┬────┬────┬────┬────┬────┬────
Clock      │    │    │    │    │    │    │    │    │    │    │    │    │

TX INPUT (dll_tx_sink):
─────────────────────────
valid  ────┘    ├─────┐___________________________________________________
first  ────┘    ├─────┐___________________________________________________
last   ────┘    ├─────┐___________________________________________________
dat    ─────────< 0x0123456789ABCDEF >────────────────────────────────────
               ^
               64-bit word (8 bytes)

TX PACKETIZER FSM:
──────────────────
state  IDLE IDLE DATA DATA DATA DATA DATA DATA DATA DATA DATA END  IDLE IDLE
                 ^                                          ^
                 Detect packet type                        After 8 bytes

TX OUTPUT (pipe_tx_*):
──────────────────────
data   ──< 0x00│ 0xFB│ 0xEF│ 0xCD│ 0xAB│ 0x89│ 0x67│ 0x45│ 0x23│ 0x01│ 0xFD│ 0x00 >
              │      │     │     │     │     │     │     │     │     │      │
              Idle   STP   Byte0 Byte1 Byte2 Byte3 Byte4 Byte5 Byte6 Byte7 END   Idle

datak  ─────────────┘├─────┐_____________________________________________├─────┐_____
                     K=1    K=0 (8 data bytes)                          K=1
                     START                                              END

RX INPUT (pipe_rx_* - loopback from TX):
─────────────────────────────────────────
data   ──< 0x00│ 0xFB│ 0xEF│ 0xCD│ 0xAB│ 0x89│ 0x67│ 0x45│ 0x23│ 0x01│ 0xFD│ 0x00 >
datak  ─────────────┘├─────┐_____________________________________________├─────┐_____

RX DEPACKETIZER FSM:
────────────────────
state  IDLE IDLE IDLE DATA DATA DATA DATA DATA DATA DATA DATA DATA DATA IDLE IDLE
                      ^                                          ^
                      STP detected                              END detected

RX INTERNAL (data_buffer accumulation):
────────────────────────────────────────
buffer ───< 0x00...00│ 0x00...EF│ 0x00CDEF│ 0xABCDEF│ ... │ 0x0123456789ABCDEF >──
                     ^           ^                             ^
                     Byte 0      Byte 1                       Byte 7 complete

RX OUTPUT (dll_rx_source):
──────────────────────────
valid  ___________________________________________________________├─────┐________
first  ___________________________________________________________├─────┐________
last   ___________________________________________________________├─────┐________
dat    ────────────────────────────────────────────────< 0x0123456789ABCDEF >───
                                                                  ^
                                                        Packet output on END

Total latency: 11 cycles (2 IDLE + 1 STP + 8 DATA + 1 END = 11 cycles from input to output)
```

### SKP Ordered Set Insertion Timing

```
Cycle: 1176 1177 1178 1179 1180 1181 1182 1183 1184 1185 1186
       ────┬────┬────┬────┬────┬────┬────┬────┬────┬────┬────
Clock      │    │    │    │    │    │    │    │    │    │

TX PACKETIZER:
──────────────
counter    1176 1177 1178 1179 1180 1181 1182 1183    0    1    2
           ───────────────────────┐────┘____________________________
                                  │
                             Threshold reached

state  DATA DATA DATA DATA END  IDLE SKP  SKP  SKP  SKP  IDLE IDLE
                                  │    ^    ^    ^    ^    │
                                  │    Symbol counters     │
                                  │    0    1    2    3    │
                                  └──────────────────────────┘

TX OUTPUT:
──────────
data   ──< 0xXX│ 0xXX│ 0xXX│ 0xXX│ 0xFD│ 0x00│ 0xBC│ 0x1C│ 0x1C│ 0x1C│ 0x00 >
              Data bytes         END   Idle  COM   SKP   SKP   SKP   Idle

datak  ──────────────────────────────┘      ├───────────────────────┐__________
                                            K=1 (4 symbols)         K=0

RX DEPACKETIZER:
────────────────
state  DATA DATA DATA DATA DATA IDLE IDLE SKP_ SKP_ SKP_ IDLE IDLE
                                           CHK  CHK  CHK
                                           ^              ^
                                           COM detected   3 SKP verified

SKP Action: Transparently filtered, not forwarded to DLL

Legend:
  • SKP insertion interval: 1180 symbols (configurable 1180-1538)
  • SKP ordered set: COM + 3×SKP = 4 symbols
  • Counter resets after SKP transmission
  • RX removes SKP, invisible to upper layers
```

### TS1/TS2 Ordered Set Transmission

```
Cycle: 0    1    2    3    4    5    6    7    8    9    ...  16   17
       ───┬────┬────┬────┬────┬────┬────┬────┬────┬────┬────┬────┬────
Clock      │    │    │    │    │    │    │    │    │    │    │    │

TX CONTROL:
───────────
send_ts1 ──┘    ├─────┐___________________________________________________
                ^     ^
                Trigger pulse

TX PACKETIZER FSM:
──────────────────
state  IDLE IDLE TS   TS   TS   TS   TS   TS   TS   TS   ... TS   IDLE IDLE
                 ^                                         ^
                 Symbol counter: 0,1,2,3,4,5,6,7,8,9,...,15

TX OUTPUT (TS1):
────────────────
data   ──< 0x00│ 0xBC│ link │ lane │ nfts │ rate │ ctrl0│ ctrl1│ 0x4A│ ... │ 0x4A│ 0x00 >
              Idle  COM   #0    #1    #2    #3    #4    #5    #6        #15   Idle
                    ^                                           ^             ^
                    K=1                                         D10.2         D10.2

datak  ─────────────┘├───┐_______________________________________________________
                     K=1  K=0 (15 data symbols)

RX DEPACKETIZER FSM:
────────────────────
state  IDLE IDLE IDLE TS_  TS_  TS_  TS_  TS_  TS_  TS_  ... TS_  IDLE IDLE
                      CHK  CHK  CHK  CHK  CHK  CHK  CHK      CHK
                      ^                                 ^         ^
                      COM detected                     Check ID   ts1_detected=1

RX TS BUFFER:
─────────────
ts_buffer  ──< 0xBC│ link│ lane│ nfts│ rate│ ctrl0│ ctrl1│ 0x4A│ ... │ 0x4A >
symbol#       [0]   [1]   [2]   [3]   [4]   [5]    [6]    [7]        [15]
                                                           ^
                                                    Check [7-10] = 0x4A
                                                    → TS1 detected

RX STATUS:
──────────
ts1_det    _____________________________________________________________├────────
                                                                        ^
                                                                After 16 symbols

Legend:
  • TS1: 16 symbols (COM + 15 data symbols)
  • TS1 Identifier: D10.2 (0x4A) in symbols 7-15
  • TS2: Same structure, but D5.2 (0x45) identifier
  • Manual trigger: send_ts1 / send_ts2 signals
  • RX detection: ts1_detected / ts2_detected flags
```

### Multi-Packet with SKP Insertion

```
Cycle: 0-9   10-11 12-21 22-25 26-35 36-37
       ─────┬──────┬─────┬─────┬─────┬─────
Packets     PKT1         PKT2        PKT3

Timeline Detail:
────────────────

Cycles 0-9: Packet 1 Transmission
  TX: STP + 8 DATA + END = 10 cycles
  Counter: 0 → 10 symbols

Cycles 10-11: IDLE
  Counter: 10 → 12 symbols

Cycles 12-21: Packet 2 Transmission
  TX: STP + 8 DATA + END = 10 cycles
  Counter: 12 → 22 symbols

Cycles 22-25: SKP Insertion (if counter >= 1180)
  TX: COM + SKP + SKP + SKP = 4 cycles
  Counter: RESET → 0 symbols

Cycles 26-35: Packet 3 Transmission
  TX: STP + 8 DATA + END = 10 cycles
  Counter: 0 → 10 symbols

Visual:
───────
TX:  [PKT1]  --  [PKT2]  [SKP]  [PKT3]  --
     10 cyc  2   10 cyc  4 cyc  10 cyc  2

RX:  -- [PKT1]  --  [PKT2] (SKP) [PKT3]  --
        OUT         OUT          OUT

Notes:
  • SKP transparent to DLL layer
  • Packets delivered intact
  • Counter tracks symbols between SKP insertions
```

---

## Integration with DLL and PHY Layers

### DLL Layer Integration (Above PIPE)

```
┌─────────────────────────────────────────────────────────────┐
│                   Data Link Layer (DLL)                     │
│                                                             │
│  Components:                                                │
│  • DLL TX: Adds LCRC, sequence numbers                      │
│  • DLL RX: Checks LCRC, sends ACK/NAK                       │
│  • LTSSM: Link training state machine                       │
│                                                             │
│  Interface to PIPE:                                         │
│  • phy.sink (TX): Stream endpoint, 64-bit packets           │
│  • phy.source (RX): Stream endpoint, 64-bit packets         │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ phy_layout(64)
                       │ • valid, first, last
                       │ • dat[63:0]
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    PIPE Interface                           │
│                                                             │
│  Interface to DLL:                                          │
│  • dll_tx_sink ← phy.sink                                   │
│  • dll_rx_source → phy.source                               │
│                                                             │
│  Processing:                                                │
│  • TX: 64-bit → 8-bit conversion + framing                  │
│  • RX: 8-bit → 64-bit conversion + framing removal          │
│  • Ordered sets: SKP, TS1, TS2                              │
└──────────────────────┬─────────────────────────────────────┘
                       │
                       │ PIPE signals (8-bit)
                       ▼
                  PHY Layer
```

### PHY Layer Integration (Below PIPE)

```
┌─────────────────────────────────────────────────────────────┐
│                    PIPE Interface                           │
│                                                             │
│  PIPE TX Signals:                                           │
│  • pipe_tx_data[7:0]                                        │
│  • pipe_tx_datak                                            │
│  • pipe_tx_elecidle                                         │
│                                                             │
│  PIPE RX Signals:                                           │
│  • pipe_rx_data[7:0]                                        │
│  • pipe_rx_datak                                            │
│  • pipe_rx_valid                                            │
│                                                             │
│  Control/Status:                                            │
│  • pipe_powerdown[1:0]                                      │
│  • pipe_rate (Gen1/Gen2)                                    │
└──────────────────────┬─────────────────────────────────────┘
                       │
                       │ PIPE protocol (8-bit symbols + ctrl)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              Transceiver Base / PHY Layer                   │
│                                                             │
│  • 8b/10b encoding/decoding                                 │
│  • TX/RX datapaths with CDC                                 │
│  • Reset sequencing                                         │
│  • Vendor-specific primitives:                              │
│    - Xilinx GTX (7-Series)                                  │
│    - Xilinx GTY (UltraScale+)                               │
│    - Lattice ECP5 SERDES                                    │
└─────────────────────────────────────────────────────────────┘
```

### Clock Domains

```
┌────────────────────────────────────────────────────────┐
│  sys_clk Domain                                        │
│  ═══════════════                                       │
│                                                        │
│  DLL Layer ──► PIPE Interface (TX/RX logic)            │
│                                                        │
│  • dll_tx_sink, dll_rx_source                          │
│  • FSM states                                          │
│  • Byte counters                                       │
│  • Data buffers                                        │
└────────────────────────┬───────────────────────────────┘
                         │
                         │ PIPE signals cross
                         │ into PHY clocks
                         ▼
┌────────────────────────────────────────────────────────┐
│  tx_clk Domain (PHY TX)                                │
│  ═══════════════════════                               │
│                                                        │
│  • pipe_tx_data[7:0]                                   │
│  • pipe_tx_datak                                       │
│  • AsyncFIFO: sys_clk → tx_clk                         │
│  • 8b/10b encoder                                      │
│                                                        │
│  Clock: 125 MHz (Gen1) or 250 MHz (Gen2)               │
└────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────┐
│  rx_clk Domain (PHY RX)                                │
│  ═══════════════════════                               │
│                                                        │
│  • pipe_rx_data[7:0]                                   │
│  • pipe_rx_datak                                       │
│  • 8b/10b decoder                                      │
│  • AsyncFIFO: rx_clk → sys_clk                         │
│                                                        │
│  Clock: Recovered from RX data (CDR)                   │
└────────────────────────────────────────────────────────┘
```

---

## Performance Characteristics

### Throughput

```
Gen1 (2.5 GT/s):
  Symbol rate: 2.5 GSymbols/s
  8b/10b overhead: 2.5 × 8/10 = 2.0 Gb/s line rate
  Framing overhead: (8 data / 10 total) = 80% efficiency
  Effective throughput: 2.0 × 0.8 = 1.6 Gb/s = 200 MB/s

Gen2 (5.0 GT/s):
  Symbol rate: 5.0 GSymbols/s
  8b/10b overhead: 5.0 × 8/10 = 4.0 Gb/s line rate
  Framing overhead: (8 data / 10 total) = 80% efficiency
  Effective throughput: 4.0 × 0.8 = 3.2 Gb/s = 400 MB/s

SKP Overhead:
  SKP insertion: 4 symbols per 1180 symbols
  Overhead: 4/1180 = 0.34%
  Impact on throughput: < 1%
```

### Latency

```
TX Path Latency:
  Packet arrival → First symbol output
  1. IDLE state: 1 cycle (detection)
  2. Type detection: 0 cycles (combinatorial)
  3. STP output: 1 cycle
  Total: 2 cycles from packet to STP

RX Path Latency:
  Symbol arrival → Packet output
  1. STP detection: 1 cycle
  2. DATA accumulation: 8 cycles
  3. END detection: 1 cycle
  Total: 10 cycles from STP to packet output

Round-trip Latency (TX → RX loopback):
  TX latency: 2 cycles
  Symbol transmission: 10 cycles (STP + 8 DATA + END)
  RX latency: 10 cycles
  Total: 22 cycles minimum
```

---

## Usage Examples

### Basic Configuration

```python
from litepcie.dll.pipe import PIPEInterface

# Create PIPE interface for Gen1
pipe = PIPEInterface(
    data_width=8,
    gen=1,
    enable_skp=True,          # Enable SKP ordered sets
    skp_interval=1180,        # Insert SKP every 1180 symbols
    enable_training_sequences=False,  # Disable TS1/TS2 for now
)

# Connect to DLL layer
self.comb += [
    dll.tx_source.connect(pipe.dll_tx_sink),
    pipe.dll_rx_source.connect(dll.rx_sink),
]

# Connect to PHY layer (external PIPE PHY chip)
self.comb += [
    phy_pads.tx_data.eq(pipe.pipe_tx_data),
    phy_pads.tx_datak.eq(pipe.pipe_tx_datak),
    phy_pads.tx_elecidle.eq(pipe.pipe_tx_elecidle),
    pipe.pipe_rx_data.eq(phy_pads.rx_data),
    pipe.pipe_rx_datak.eq(phy_pads.rx_datak),
    pipe.pipe_rx_valid.eq(phy_pads.rx_valid),
]
```

### With Link Training Support

```python
from litepcie.dll.pipe import PIPEInterface

# Create PIPE interface with training sequences
pipe = PIPEInterface(
    data_width=8,
    gen=2,  # Gen2 (5.0 GT/s)
    enable_skp=True,
    skp_interval=1180,
    enable_training_sequences=True,  # Enable TS1/TS2
    enable_ltssm=True,  # Enable automatic LTSSM
)

# LTSSM automatically manages training sequences
# Link status available via pipe.link_up signal

# Application logic
self.comb += [
    If(pipe.link_up,
        # Link is trained and in L0 state
        # Normal packet transmission enabled
        dll.tx_source.connect(pipe.dll_tx_sink),
    ).Else(
        # Link training in progress
        # Wait for link_up
    )
]
```

---

## References

### Specifications

- **Intel PIPE 3.0 Specification** - PHY Interface for PCI Express
- **PCIe Base Spec 4.0**
  - Section 4.2.2: Symbol Encoding (8b/10b)
  - Section 4.2.3: Framing (STP/SDP/END)
  - Section 4.2.6: Ordered Sets (TS1/TS2)
  - Section 4.2.7: Clock Compensation (SKP)

### Implementation Files

- `litepcie/dll/pipe.py` - PIPE interface implementation
- `litepcie/phy/transceiver_base/` - Transceiver base classes
- `test/dll/test_pipe_*.py` - PIPE interface tests

### Related Documentation

- [PIPE Architecture](pipe-architecture.md) - Detailed component diagrams
- [PIPE Interface Guide](../guides/pipe-interface-guide.md) - User guide and API reference
- [Complete System Architecture](complete-system-architecture.md) - Overall PCIe stack
- [DLL Layer Architecture](dll-layer.md) - Data Link Layer details
- [SERDES Layer Architecture](serdes-layer.md) - Physical layer details

### Phase Documentation

- [Phase 4 Completion Summary](../phases/phase-4-completion-summary.md) - PIPE testing and documentation
- [Phase 5 Completion Summary](../phases/phase-5-completion-summary.md) - Ordered sets implementation

---

**Version:** 1.0
**Date:** 2025-10-18
**Status:** Complete
