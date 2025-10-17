# PIPE Interface Architecture

**Version:** 1.0
**Date:** 2025-10-17
**Status:** Complete

This document provides detailed architecture diagrams for the LitePCIe PIPE interface implementation.

---

## Table of Contents

1. [High-Level PCIe Stack](#high-level-pcie-stack)
2. [PIPE Interface Component Breakdown](#pipe-interface-component-breakdown)
3. [TX Packetizer Architecture](#tx-packetizer-architecture)
4. [RX Depacketizer Architecture](#rx-depacketizer-architecture)
5. [Signal Timing Diagrams](#signal-timing-diagrams)
6. [Data Flow Examples](#data-flow-examples)

---

## High-Level PCIe Stack

### Complete PCIe Protocol Stack

```
┌────────────────────────────────────────────────────────────┐
│                     Application Layer                      │
│                                                            │
│  User logic, DMA engines, configuration registers         │
└────────────────────┬───────────────────────────────────────┘
                     │
┌────────────────────▼───────────────────────────────────────┐
│                   Transaction Layer (TL)                   │
│                                                            │
│  • TLP assembly/disassembly                               │
│  • Flow control credit management                          │
│  • TLP routing and addressing                             │
│  • Virtual channel management                              │
└────────────────────┬───────────────────────────────────────┘
                     │ TLPs (Transaction Layer Packets)
┌────────────────────▼───────────────────────────────────────┐
│                  Data Link Layer (DLL)                     │
│                                                            │
│  • LCRC generation/checking                               │
│  • ACK/NAK protocol                                        │
│  • Retry buffer management                                 │
│  • Sequence numbers                                        │
│  • DLLPs (Flow Control, ACK/NAK)                          │
└────────────────────┬───────────────────────────────────────┘
                     │ 64-bit DLL packets
┌────────────────────▼───────────────────────────────────────┐
│              PIPE Interface (THIS MODULE)                  │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐ │
│  │          TX Packetizer (PIPETXPacketizer)            │ │
│  │  • 64-bit DLL packets → 8-bit PIPE symbols          │ │
│  │  • K-character framing (STP/SDP/END)                 │ │
│  │  • Packet type detection (TLP vs DLLP)              │ │
│  │  • Byte serialization (little-endian)                │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐ │
│  │         RX Depacketizer (PIPERXDepacketizer)         │ │
│  │  • 8-bit PIPE symbols → 64-bit DLL packets          │ │
│  │  • K-character detection (STP/SDP/END)               │ │
│  │  • Byte accumulation (little-endian)                 │ │
│  │  • Packet reconstruction                              │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                            │
│  Control Signals: powerdown, rate, rx_polarity            │
│  Status Signals: rx_status, elecidle                       │
└────────────────────┬───────────────────────────────────────┘
                     │ 8-bit PIPE symbols + control/status
┌────────────────────▼───────────────────────────────────────┐
│                    Physical Layer (PHY)                    │
│                                                            │
│  • 8b/10b encoding/decoding                               │
│  • Serializer/Deserializer (SerDes)                       │
│  • Clock recovery and data alignment                       │
│  • Ordered set generation (SKP, COM, TS1, TS2)           │
│  • Electrical characteristics (voltage, impedance)         │
│  • Link training and state machine (LTSSM)                │
└────────────────────┬───────────────────────────────────────┘
                     │ Differential serial data
                     ▼
              Physical Medium
          (PCIe lanes on PCB/connector)
```

### PIPE Interface Position in Detail

```
        DLL Layer
            │
            │ Stream Interface
            │ (valid, first, last, dat[63:0])
            ▼
   ┌─────────────────┐
   │  dll_tx_sink    │◄─── Input from DLL TX
   └────────┬────────┘
            │
    ┌───────▼────────┐
    │  PIPE          │
    │  Interface     │
    │  Module        │
    └───────┬────────┘
            │
   ┌────────▼────────┐
   │ dll_rx_source   │───► Output to DLL RX
   └─────────────────┘
            │
            │ Stream Interface
            │ (valid, first, last, dat[63:0])
            ▼
        DLL Layer
```

---

## PIPE Interface Component Breakdown

### PIPEInterface Module Structure

```
┌─────────────────────────────────────────────────────────────────┐
│                       PIPEInterface                              │
│                                                                  │
│  Parameters:                                                     │
│    • data_width = 8 (fixed for Gen1/Gen2)                       │
│    • gen = 1 or 2 (PCIe generation)                             │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                    TX PATH                                  │ │
│  │                                                             │ │
│  │   dll_tx_sink (input)                                       │ │
│  │        │                                                    │ │
│  │        ▼                                                    │ │
│  │   ┌────────────────────────────────┐                       │ │
│  │   │   PIPETXPacketizer             │                       │ │
│  │   │   (submodules.tx_packetizer)   │                       │ │
│  │   │                                │                       │ │
│  │   │  FSM: IDLE → DATA → END        │                       │ │
│  │   │  • Detect packet type          │                       │ │
│  │   │  • Send START (STP/SDP)        │                       │ │
│  │   │  • Send 8 data bytes           │                       │ │
│  │   │  • Send END symbol             │                       │ │
│  │   └────────────┬───────────────────┘                       │ │
│  │                │                                            │ │
│  │                ▼                                            │ │
│  │   pipe_tx_data[7:0] ──────────────────────►                │ │
│  │   pipe_tx_datak ───────────────────────────►                │ │
│  │   pipe_tx_elecidle ────────────────────────►                │ │
│  │                                              (TX to PHY)    │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                    RX PATH                                  │ │
│  │                                              (RX from PHY)  │ │
│  │   pipe_rx_data[7:0] ◄──────────────────────                │ │
│  │   pipe_rx_datak ◄───────────────────────────                │ │
│  │   pipe_rx_valid ◄───────────────────────────                │ │
│  │   pipe_rx_status[2:0] ◄─────────────────────                │ │
│  │   pipe_rx_elecidle ◄─────────────────────────               │ │
│  │                │                                            │ │
│  │                ▼                                            │ │
│  │   ┌────────────────────────────────┐                       │ │
│  │   │   PIPERXDepacketizer           │                       │ │
│  │   │   (submodules.rx_depacketizer) │                       │ │
│  │   │                                │                       │ │
│  │   │  FSM: IDLE → DATA              │                       │ │
│  │   │  • Detect START (STP/SDP)      │                       │ │
│  │   │  • Accumulate 8 data bytes     │                       │ │
│  │   │  • Detect END symbol           │                       │ │
│  │   │  • Output complete packet      │                       │ │
│  │   └────────────┬───────────────────┘                       │ │
│  │                │                                            │ │
│  │                ▼                                            │ │
│  │   dll_rx_source (output)                                   │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                 CONTROL/STATUS                              │ │
│  │                                                             │ │
│  │   pipe_powerdown[1:0] ──────────────────►  (to PHY)        │ │
│  │   pipe_rate ─────────────────────────────►  (to PHY)       │ │
│  │   pipe_rx_polarity ──────────────────────►  (to PHY)       │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## TX Packetizer Architecture

### TX Packetizer FSM and Datapath

```
┌─────────────────────────────────────────────────────────────────┐
│                     PIPETXPacketizer                             │
│                                                                  │
│  INPUT: sink (64-bit DLL packets)                               │
│    • sink.valid, sink.first, sink.last                          │
│    • sink.dat[63:0]                                             │
│                                                                  │
│  OUTPUT: PIPE TX symbols (8-bit)                                │
│    • pipe_tx_data[7:0]                                          │
│    • pipe_tx_datak (K-character indicator)                      │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                       FSM FLOW                              │ │
│  │                                                             │ │
│  │        ┌──────────────────┐                                │ │
│  │        │   IDLE State     │                                │ │
│  │        │                  │                                │ │
│  │        │  Wait for:       │                                │ │
│  │        │  sink.valid &    │                                │ │
│  │        │  sink.first      │                                │ │
│  │        └────────┬─────────┘                                │ │
│  │                 │                                           │ │
│  │                 │ Packet detected                           │ │
│  │                 │                                           │ │
│  │        ┌────────▼─────────┐                                │ │
│  │        │  Packet Type     │                                │ │
│  │        │  Detection       │                                │ │
│  │        │                  │                                │ │
│  │        │  first_byte =    │                                │ │
│  │        │  sink.dat[7:0]   │                                │ │
│  │        │                  │                                │ │
│  │        │  is_dllp =       │                                │ │
│  │        │  (first_byte &   │                                │ │
│  │        │   0xC0) == 0x00  │                                │ │
│  │        └────────┬─────────┘                                │ │
│  │                 │                                           │ │
│  │        ┌────────▼─────────┐                                │ │
│  │        │   Send START     │                                │ │
│  │        │                  │                                │ │
│  │        │  If is_dllp:     │                                │ │
│  │        │    tx_data = SDP │  SDP = 0x5C                   │ │
│  │        │           (0x5C) │  K=1                           │ │
│  │        │  Else:           │                                │ │
│  │        │    tx_data = STP │  STP = 0xFB                   │ │
│  │        │           (0xFB) │  K=1                           │ │
│  │        │  tx_datak = 1    │                                │ │
│  │        │  byte_counter=0  │                                │ │
│  │        └────────┬─────────┘                                │ │
│  │                 │                                           │ │
│  │                 ▼                                           │ │
│  │        ┌──────────────────┐                                │ │
│  │   ┌───►│   DATA State     │                                │ │
│  │   │    │                  │                                │ │
│  │   │    │  Send byte from  │                                │ │
│  │   │    │  sink.dat:       │                                │ │
│  │   │    │                  │                                │ │
│  │   │    │  tx_data =       │                                │ │
│  │   │    │   byte_array[    │                                │ │
│  │   │    │   byte_counter]  │                                │ │
│  │   │    │  tx_datak = 0    │  Data byte (not K-char)       │ │
│  │   │    │                  │                                │ │
│  │   │    │  byte_counter++  │                                │ │
│  │   │    └────────┬─────────┘                                │ │
│  │   │             │                                           │ │
│  │   │ Loop 8x     │ After 8 bytes                            │ │
│  │   │ (0-7)       │ (counter == 7)                           │ │
│  │   │             │                                           │ │
│  │   └─────────────┘                                           │ │
│  │                 │                                           │ │
│  │                 ▼                                           │ │
│  │        ┌──────────────────┐                                │ │
│  │        │   END State      │                                │ │
│  │        │                  │                                │ │
│  │        │  Send END:       │                                │ │
│  │        │  tx_data = END   │  END = 0xFD                   │ │
│  │        │         (0xFD)   │  K=1                           │ │
│  │        │  tx_datak = 1    │                                │ │
│  │        └────────┬─────────┘                                │ │
│  │                 │                                           │ │
│  │                 │ Return to IDLE                            │ │
│  │                 ▼                                           │ │
│  │        ┌──────────────────┐                                │ │
│  │        │   IDLE State     │                                │ │
│  │        │                  │                                │ │
│  │        │  Default output: │                                │ │
│  │        │  tx_data = 0x00  │                                │ │
│  │        │  tx_datak = 0    │                                │ │
│  │        └──────────────────┘                                │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                 BYTE ARRAY MAPPING                          │ │
│  │                                                             │ │
│  │   sink.dat[63:0]  (64-bit input word)                      │ │
│  │                                                             │ │
│  │   Byte 0: dat[7:0]    ──►  Sent first   (LSB)              │ │
│  │   Byte 1: dat[15:8]   ──►  Sent second                     │ │
│  │   Byte 2: dat[23:16]  ──►  Sent third                      │ │
│  │   Byte 3: dat[31:24]  ──►  Sent fourth                     │ │
│  │   Byte 4: dat[39:32]  ──►  Sent fifth                      │ │
│  │   Byte 5: dat[47:40]  ──►  Sent sixth                      │ │
│  │   Byte 6: dat[55:48]  ──►  Sent seventh                    │ │
│  │   Byte 7: dat[63:56]  ──►  Sent last    (MSB)              │ │
│  │                                                             │ │
│  │   Little-endian ordering: LSB sent first                    │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### TX Packetizer Timing Example

```
Input Packet: 0x0123456789ABCDEF (64 bits)

Cycle │ FSM State │ Output            │ Notes
──────┼───────────┼───────────────────┼────────────────────────────
  0   │ IDLE      │ 0x00 (K=0)        │ Waiting for packet
  1   │ IDLE      │ 0x00 (K=0)        │ sink.valid=1, sink.first=1
      │           │                   │ sink.dat=0x0123456789ABCDEF
  2   │ DATA      │ 0xFB (K=1) STP    │ START detected, send STP
  3   │ DATA      │ 0xEF (K=0)        │ Byte 0: dat[7:0]
  4   │ DATA      │ 0xCD (K=0)        │ Byte 1: dat[15:8]
  5   │ DATA      │ 0xAB (K=0)        │ Byte 2: dat[23:16]
  6   │ DATA      │ 0x89 (K=0)        │ Byte 3: dat[31:24]
  7   │ DATA      │ 0x67 (K=0)        │ Byte 4: dat[39:32]
  8   │ DATA      │ 0x45 (K=0)        │ Byte 5: dat[47:40]
  9   │ DATA      │ 0x23 (K=0)        │ Byte 6: dat[55:48]
 10   │ DATA      │ 0x01 (K=0)        │ Byte 7: dat[63:56]
 11   │ END       │ 0xFD (K=1) END    │ END symbol, packet complete
 12   │ IDLE      │ 0x00 (K=0)        │ Back to IDLE
```

---

## RX Depacketizer Architecture

### RX Depacketizer FSM and Datapath

```
┌─────────────────────────────────────────────────────────────────┐
│                    PIPERXDepacketizer                            │
│                                                                  │
│  INPUT: PIPE RX symbols (8-bit)                                 │
│    • pipe_rx_data[7:0]                                          │
│    • pipe_rx_datak (K-character indicator)                      │
│                                                                  │
│  OUTPUT: source (64-bit DLL packets)                            │
│    • source.valid, source.first, source.last                    │
│    • source.dat[63:0]                                           │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                       FSM FLOW                              │ │
│  │                                                             │ │
│  │        ┌──────────────────┐                                │ │
│  │        │   IDLE State     │                                │ │
│  │        │                  │                                │ │
│  │        │  Wait for START  │                                │ │
│  │        │  K-character:    │                                │ │
│  │        │  • STP (0xFB)    │  TLP start                     │ │
│  │        │  • SDP (0x5C)    │  DLLP start                    │ │
│  │        └────────┬─────────┘                                │ │
│  │                 │                                           │ │
│  │                 │ rx_datak=1 and                            │ │
│  │                 │ (rx_data==STP or rx_data==SDP)            │ │
│  │                 │                                           │ │
│  │        ┌────────▼─────────┐                                │ │
│  │        │  START Detected  │                                │ │
│  │        │                  │                                │ │
│  │        │  is_tlp = 1 if   │                                │ │
│  │        │    rx_data==STP  │                                │ │
│  │        │  else is_tlp = 0 │                                │ │
│  │        │                  │                                │ │
│  │        │  byte_counter=0  │                                │ │
│  │        │  data_buffer=0   │                                │ │
│  │        └────────┬─────────┘                                │ │
│  │                 │                                           │ │
│  │                 ▼                                           │ │
│  │        ┌──────────────────┐                                │ │
│  │   ┌───►│   DATA State     │                                │ │
│  │   │    │                  │                                │ │
│  │   │    │  If rx_datak=0:  │  Data byte received           │ │
│  │   │    │                  │                                │ │
│  │   │    │   Store byte in  │                                │ │
│  │   │    │   data_buffer:   │                                │ │
│  │   │    │                  │                                │ │
│  │   │    │   [7:0]  ← byte0 │                                │ │
│  │   │    │   [15:8] ← byte1 │                                │ │
│  │   │    │   ...            │                                │ │
│  │   │    │   [63:56]← byte7 │                                │ │
│  │   │    │                  │                                │ │
│  │   │    │   byte_counter++ │                                │ │
│  │   │    │                  │                                │ │
│  │   │    │  If rx_datak=1:  │  K-character received         │ │
│  │   │    │                  │                                │ │
│  │   │    │   If rx_data=END:│                                │ │
│  │   │    │                  │                                │ │
│  │   │    │   • Output packet│                                │ │
│  │   │    │   • source.valid │                                │ │
│  │   │    │     = 1          │                                │ │
│  │   │    │   • source.first │                                │ │
│  │   │    │     = 1          │                                │ │
│  │   │    │   • source.last  │                                │ │
│  │   │    │     = 1          │                                │ │
│  │   │    │   • source.dat = │                                │ │
│  │   │    │     data_buffer  │                                │ │
│  │   │    │   • Go to IDLE   │                                │ │
│  │   │    └────────┬─────────┘                                │ │
│  │   │             │                                           │ │
│  │   │ Loop while  │ END detected                             │ │
│  │   │ accumulating│                                           │ │
│  │   │             │                                           │ │
│  │   └─────────────┘                                           │ │
│  │                 │                                           │ │
│  │                 ▼                                           │ │
│  │        ┌──────────────────┐                                │ │
│  │        │   IDLE State     │                                │ │
│  │        │                  │                                │ │
│  │        │  Wait for next   │                                │ │
│  │        │  START symbol    │                                │ │
│  │        └──────────────────┘                                │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │              DATA BUFFER ACCUMULATION                       │ │
│  │                                                             │ │
│  │   data_buffer[63:0]  (64-bit accumulation)                 │ │
│  │                                                             │ │
│  │   Byte 0 (first): rx_data → buffer[7:0]    (LSB)           │ │
│  │   Byte 1:         rx_data → buffer[15:8]                   │ │
│  │   Byte 2:         rx_data → buffer[23:16]                  │ │
│  │   Byte 3:         rx_data → buffer[31:24]                  │ │
│  │   Byte 4:         rx_data → buffer[39:32]                  │ │
│  │   Byte 5:         rx_data → buffer[47:40]                  │ │
│  │   Byte 6:         rx_data → buffer[55:48]                  │ │
│  │   Byte 7 (last):  rx_data → buffer[63:56]  (MSB)           │ │
│  │                                                             │ │
│  │   Little-endian ordering: LSB received first                │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### RX Depacketizer Timing Example

```
Input Symbol Stream: STP, 0xEF, 0xCD, 0xAB, 0x89, 0x67, 0x45, 0x23, 0x01, END

Cycle │ FSM State │ Input          │ Action                  │ data_buffer
──────┼───────────┼────────────────┼─────────────────────────┼──────────────────
  0   │ IDLE      │ 0xFB (K=1) STP │ Detect START (TLP)      │ 0x0000000000000000
  1   │ DATA      │ 0xEF (K=0)     │ Store in [7:0]          │ 0x00000000000000EF
  2   │ DATA      │ 0xCD (K=0)     │ Store in [15:8]         │ 0x000000000000CDEF
  3   │ DATA      │ 0xAB (K=0)     │ Store in [23:16]        │ 0x0000000000ABCDEF
  4   │ DATA      │ 0x89 (K=0)     │ Store in [31:24]        │ 0x00000000089ABCDEF
  5   │ DATA      │ 0x67 (K=0)     │ Store in [39:32]        │ 0x0000006789ABCDEF
  6   │ DATA      │ 0x45 (K=0)     │ Store in [47:40]        │ 0x000045678ABCDEF
  7   │ DATA      │ 0x23 (K=0)     │ Store in [55:48]        │ 0x002345678ABCDEF
  8   │ DATA      │ 0x01 (K=0)     │ Store in [63:56]        │ 0x0123456789ABCDEF
  9   │ DATA      │ 0xFD (K=1) END │ END detected, output!   │ 0x0123456789ABCDEF
      │           │                │ source.valid = 1        │
      │           │                │ source.first = 1        │
      │           │                │ source.last = 1         │
      │           │                │ source.dat = buffer     │
 10   │ IDLE      │ ...            │ Wait for next START     │ 0x0123456789ABCDEF
```

---

## Signal Timing Diagrams

### Complete TX → RX Loopback Timing

```
Cycle: 0    1    2    3    4    5    6    7    8    9    10   11   12   13
       ───┬────┬────┬────┬────┬────┬────┬────┬────┬────┬────┬────┬────┬────
Clock      │    │    │    │    │    │    │    │    │    │    │    │    │

TX Input (dll_tx_sink):
valid  ────┘    ├─────┐___________________________________________________
first  ────┘    ├─────┐___________________________________________________
last   ────┘    ├─────┐___________________________________________________
dat    ─────────< 0x0123456789ABCDEF >────────────────────────────────────

TX Packetizer FSM:
state  IDLE IDLE DATA DATA DATA DATA DATA DATA DATA DATA DATA END  IDLE IDLE
                 ^
                 START detected

TX Output (pipe_tx_*):
data   ──< 0x00 │ 0xFB│ 0xEF│ 0xCD│ 0xAB│ 0x89│ 0x67│ 0x45│ 0x23│ 0x01│ 0xFD│ 0x00 >
datak  ─────────┘      ├─────┐_____________________________________________├─────┐_____
                       K=1    K=0 (8 data bytes)                          K=1
                       STP                                                 END

RX Input (pipe_rx_* - loopback from TX):
data   ──< 0x00 │ 0xFB│ 0xEF│ 0xCD│ 0xAB│ 0x89│ 0x67│ 0x45│ 0x23│ 0x01│ 0xFD│ 0x00 >
datak  ─────────┘      ├─────┐_____________________________________________├─────┐_____

RX Depacketizer FSM:
state  IDLE IDLE IDLE DATA DATA DATA DATA DATA DATA DATA DATA DATA DATA IDLE IDLE
                      ^                                          ^
                      START                                      END

RX Internal (data_buffer accumulation):
buffer ───< 0x0...00 │ 0x0...EF│ 0x0.CDEF│ ...│ 0x0123456789ABCDEF >────────────

RX Output (dll_rx_source):
valid  ___________________________________________________________├─────┐________
first  ___________________________________________________________├─────┐________
last   ___________________________________________________________├─────┐________
dat    ────────────────────────────────────────────────< 0x0123456789ABCDEF >───
                                                                  ^
                                                        Packet output on END
```

### TX Electrical Idle Timing

```
Cycle: 0    1    2    3    4    5    6    7    8
       ───┬────┬────┬────┬────┬────┬────┬────┬────
Clock      │    │    │    │    │    │    │    │

TX Input:
valid  ____┘    ├─────┐________________________________

TX Output:
elecidle ────┐______┘                            ├────
             ^                                   ^
             No data: request electrical idle    Data present: active

Interpretation:
  • When dll_tx_sink.valid=0: pipe_tx_elecidle=1 (request idle)
  • When dll_tx_sink.valid=1: pipe_tx_elecidle=0 (active transmission)
  • PHY uses elecidle to manage power and signal presence
```

### Multi-Packet Timing

```
Cycle: 0-1  2-11 12-13 14-23 24-25 26-35 36+
       ────┬────┬─────┬─────┬─────┬─────┬────
Packets     PKT1       PKT2        PKT3

Packet 1:
TX:    IDLE STP+8D+END IDLE
RX:         IDLE       STP+8D+END OUT  IDLE

Packet 2:
TX:                    IDLE STP+8D+END IDLE
RX:                         IDLE       STP+8D+END OUT  IDLE

Packet 3:
TX:                                    IDLE STP+8D+END
RX:                                         IDLE       STP+8D+END OUT

Legend:
  STP+8D+END = START(1) + DATA(8) + END(1) = 10 cycles
  OUT = Output valid for 1 cycle
  IDLE = Gap between packets
```

---

## Data Flow Examples

### Example 1: TLP Packet Transmission

```
Step 1: DLL sends TLP packet
──────────────────────────────
  dll_tx_sink.valid = 1
  dll_tx_sink.first = 1
  dll_tx_sink.last  = 1
  dll_tx_sink.dat   = 0x0123456789ABCDEF

  First byte: 0xEF
  Bits [7:6]: 0b11 (not 0b00, so NOT a DLLP → TLP)


Step 2: TX Packetizer processes
────────────────────────────────
  Cycle 1: Detect TLP type
           is_dllp = (0xEF & 0xC0) == 0x00 → False
           → Send STP (0xFB, K=1)

  Cycle 2: Output START
           pipe_tx_data  = 0xFB  (STP)
           pipe_tx_datak = 1

  Cycles 3-10: Output 8 data bytes
           pipe_tx_data  = 0xEF, 0xCD, 0xAB, 0x89, 0x67, 0x45, 0x23, 0x01
           pipe_tx_datak = 0

  Cycle 11: Output END
           pipe_tx_data  = 0xFD  (END)
           pipe_tx_datak = 1


Step 3: RX Depacketizer receives (via loopback)
────────────────────────────────────────────────
  Cycle 2: Detect STP (0xFB, K=1)
           → is_tlp = 1
           → Enter DATA state

  Cycles 3-10: Accumulate 8 data bytes
           data_buffer[7:0]   ← 0xEF
           data_buffer[15:8]  ← 0xCD
           data_buffer[23:16] ← 0xAB
           data_buffer[31:24] ← 0x89
           data_buffer[39:32] ← 0x67
           data_buffer[47:40] ← 0x45
           data_buffer[55:48] ← 0x23
           data_buffer[63:56] ← 0x01
           → data_buffer = 0x0123456789ABCDEF

  Cycle 11: Detect END (0xFD, K=1)
           → Output packet:
              dll_rx_source.valid = 1
              dll_rx_source.first = 1
              dll_rx_source.last  = 1
              dll_rx_source.dat   = 0x0123456789ABCDEF


Step 4: DLL receives reconstructed packet
──────────────────────────────────────────
  Original: 0x0123456789ABCDEF
  Received: 0x0123456789ABCDEF
  ✓ Match!
```

### Example 2: DLLP Packet Transmission

```
Step 1: DLL sends DLLP packet (ACK)
────────────────────────────────────
  dll_tx_sink.dat = 0x0000000000000000  (ACK DLLP)

  First byte: 0x00
  Bits [7:6]: 0b00 → DLLP detected


Step 2: TX Packetizer processes
────────────────────────────────
  Cycle 1: Detect DLLP type
           is_dllp = (0x00 & 0xC0) == 0x00 → True
           → Send SDP (0x5C, K=1)

  Cycle 2: Output START
           pipe_tx_data  = 0x5C  (SDP)
           pipe_tx_datak = 1

  Cycles 3-10: Output 8 data bytes
           pipe_tx_data  = 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
           pipe_tx_datak = 0

  Cycle 11: Output END
           pipe_tx_data  = 0xFD  (END)
           pipe_tx_datak = 1


Step 3: RX Depacketizer receives
─────────────────────────────────
  Cycle 2: Detect SDP (0x5C, K=1)
           → is_tlp = 0
           → Enter DATA state

  Cycles 3-10: Accumulate 8 data bytes
           → data_buffer = 0x0000000000000000

  Cycle 11: Detect END (0xFD, K=1)
           → Output DLLP packet
```

---

## References

- **Intel PIPE 3.0 Specification** - Complete signal and protocol definitions
- **PCIe Base Spec 4.0, Section 4.2** - Symbol Encoding and Framing
- **docs/guides/pipe-interface-guide.md** - User guide and API reference
- **litepcie/dll/pipe.py** - Implementation source code
- **test/dll/test_pipe_*.py** - Test implementations with timing examples

---

## Version History

- **1.0 (2025-10-17):** Initial architecture documentation with FSM diagrams, timing diagrams, and data flow examples
