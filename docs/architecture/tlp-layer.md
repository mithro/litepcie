# Transaction Layer (TLP) Architecture

**Layer:** Transaction Layer (Layer 4)
**Location:** `litepcie/tlp/`
**Purpose:** High-level read/write transactions and message passing

## Overview

The TLP (Transaction Layer Packet) layer implements PCIe Section 2 requirements for transaction-based communication. It provides the highest level of abstraction in the PCIe protocol stack, converting application-level read/write requests into properly formatted TLP packets.

### Position in PCIe Stack

```
┌─────────────────────────────────────────────────────────┐
│              APPLICATION LAYER                          │
│  • User logic, DMA engines, memory controllers          │
│  • High-level read/write operations                     │
└────────────────────┬────────────────────────────────────┘
                     │ request_layout / completion_layout
                     │ (64-512 bit wide)
┌────────────────────▼────────────────────────────────────┐
│           TRANSACTION LAYER (TLP)                       │ ◄── THIS LAYER
│  • TLP Packetizer: Encode requests/completions          │
│  • TLP Depacketizer: Decode incoming TLPs               │
│  • TLP Controller: Tag management, reordering           │
│  • Flow Control: Credit-based throttling                │
└────────────────────┬────────────────────────────────────┘
                     │ phy_layout (64-512 bit)
                     │ TLP packets with headers
┌────────────────────▼────────────────────────────────────┐
│              DATA LINK LAYER (DLL)                      │
│  • Adds LCRC and sequence numbers                       │
│  • Handles ACK/NAK and retry                            │
└─────────────────────────────────────────────────────────┘
```

## Key Components

The TLP layer consists of three main modules:

1. **TLP Packetizer** (`litepcie/tlp/packetizer.py`)
   - Converts high-level requests/completions into TLP format
   - Inserts TLP headers (3DW or 4DW)
   - Handles endianness conversion

2. **TLP Depacketizer** (`litepcie/tlp/depacketizer.py`)
   - Extracts TLP headers from incoming packets
   - Decodes TLP type and routes to appropriate handler
   - Converts TLP format to high-level requests/completions

3. **TLP Controller** (`litepcie/tlp/controller.py`)
   - Manages outstanding read request tags
   - Reorders completions to match request order
   - Throttles requests based on available tags

## TLP Types and Format

### TLP Type Overview

PCIe defines several TLP types, categorized by their purpose:

| Category | TLP Types | fmt:type | Description |
|----------|-----------|----------|-------------|
| **Memory** | MRd32, MRd64 | 00:00000, 01:00000 | Memory Read (32/64-bit addressing) |
| | MWr32, MWr64 | 10:00000, 11:00000 | Memory Write (32/64-bit addressing) |
| **I/O** | IORd, IOWr | 00:00010, 10:00010 | I/O Read/Write (legacy) |
| **Config** | CfgRd0, CfgWr0 | 00:00100, 10:00100 | Configuration Read/Write Type 0 |
| | CfgRd1, CfgWr1 | 00:00101, 10:00101 | Configuration Read/Write Type 1 |
| **Completion** | Cpl, CplD | 00:01010, 10:01010 | Completion without/with Data |
| **Message** | Msg, MsgD | 01:1xxxx, 11:1xxxx | Various message types |
| | PTM Req/Res | 01:10100, 11:10100 | Precision Time Measurement |

**LitePCIe Implementation** supports:
- Memory Read/Write (32-bit and 64-bit addressing)
- Configuration Read/Write (Type 0)
- Completions (with and without data)
- PTM Request/Response (Precision Time Measurement)

### Format (fmt) and Type Fields

The `fmt` field (2 bits) indicates:
- **Bit 1:** 0 = 3DW header, 1 = 4DW header
- **Bit 0:** 0 = No data payload, 1 = Data payload

The `type` field (5 bits) specifies the transaction type.

Combined `fmt:type` values from `litepcie/tlp/common.py`:
```python
fmt_type_dict = {
    "mem_rd32": 0b00_00000,  # Memory Read  (3DW, no data)
    "mem_rd64": 0b01_00000,  # Memory Read  (4DW, no data)
    "mem_wr32": 0b10_00000,  # Memory Write (3DW, with data)
    "mem_wr64": 0b11_00000,  # Memory Write (4DW, with data)
    "cpld":     0b10_01010,  # Completion with Data
    "cpl":      0b00_01010,  # Completion without Data
    "cfg_rd0":  0b00_00100,  # Config Read Type 0
    "cfg_wr0":  0b10_00100,  # Config Write Type 0
    "ptm_req":  0b01_10100,  # PTM Request (4DW)
    "ptm_res":  0b11_10100,  # PTM Response (4DW, with data)
}
```

## TLP Header Formats

### Memory Request Header (3DW) - 32-bit Addressing

Used for Memory Read/Write with addresses below 4GB.

```
Byte 0          Byte 1          Byte 2          Byte 3
┌───────────────────────────────────────────────────────┐
│fmt│ type│ R │TC │  R│TH│TD│EP│Attr│  R│    Length     │  DW0
├───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───────────────┤
│        Requester ID       │  Tag  │ LBE │   FBE       │  DW1
├───────────────────────────┴───────┴─────┴─────────────┤
│                    Address [31:2]                │ R  │  DW2
└───────────────────────────────────────────────────────┘

Field Descriptions:
  fmt       [31:30]  Format: 00 (Read, 3DW), 10 (Write, 3DW)
  type      [28:24]  Type: 00000 (Memory)
  TC        [22:20]  Traffic Class (0 for normal)
  TH        [16]     TLP Processing Hints
  TD        [15]     TLP Digest present (0 = no ECRC)
  EP        [14]     Poisoned TLP
  Attr      [13:12]  Attributes (Relaxed Ordering, No Snoop)
  Length    [9:0]    Payload length in DWORDs (0 = 1024 DW)
  Requester ID [31:16] Bus:Dev:Func of requester
  Tag       [15:8]   Transaction tag for matching completions
  LBE       [7:4]    Last DW Byte Enable (for multi-DW)
  FBE       [3:0]    First DW Byte Enable (always 0xF)
  Address   [31:2]   Address bits [31:2] (DW aligned)
```

### Memory Request Header (4DW) - 64-bit Addressing

Used for Memory Read/Write with addresses above 4GB (or forced on UltraScale+ with 256/512-bit data width).

```
Byte 0          Byte 1          Byte 2          Byte 3
┌───────────────────────────────────────────────────────┐
│fmt│ type│ R │TC │  R│TH│TD│EP│Attr│  R│    Length     │  DW0
├───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───────────────┤
│        Requester ID       │  Tag  │ LBE │   FBE       │  DW1
├───────────────────────────┴───────┴─────┴─────────────┤
│                 Address [63:32]                       │  DW2
├───────────────────────────────────────────────────────┤
│                 Address [31:2]                   │ R  │  DW3
└───────────────────────────────────────────────────────┘

Field Descriptions:
  fmt       [31:30]  Format: 01 (Read, 4DW), 11 (Write, 4DW)
  type      [28:24]  Type: 00000 (Memory)
  [Other fields same as 3DW header]
  Address   [63:2]   Full 64-bit address (DW aligned)
                     Note: In packetizer, DW2=[63:32], DW3=[31:2]
```

**Address Swapping Note:** The TLP packetizer swaps address DWORDs to match PCIe spec ordering:
- Request input: `adr[63:0]` = {MSB[63:32], LSB[31:0]}
- TLP encoding: DW2 = `adr[31:0]`, DW3 = `adr[63:32]`

### Completion Header (3DW)

Used for both Completions with Data (CplD) and without Data (Cpl).

```
Byte 0          Byte 1          Byte 2          Byte 3
┌───────────────────────────────────────────────────────┐
│fmt│ type│ R │TC │  R│TH│TD│EP│Attr│  R│    Length     │  DW0
├───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───────────────┤
│        Completer ID       │ S│BCM│   Byte Count       │  DW1
├───────────────────────────┴───┴───┴───────────────────┤
│        Requester ID       │  Tag  │ R │ Lower Addr    │  DW2
└───────────────────────────────────────────────────────┘

Field Descriptions:
  fmt       [31:30]  Format: 00 (Cpl), 10 (CplD)
  type      [28:24]  Type: 01010 (Completion)
  Length    [9:0]    Data length in DWORDs
  Completer ID [31:16] Bus:Dev:Func of completer
  Status    [15:13]  Completion Status:
                       000 = SC  (Successful Completion)
                       001 = UR  (Unsupported Request)
                       010 = CRS (Configuration Retry Status)
                       011 = CA  (Completer Abort)
  BCM       [12]     Byte Count Modified
  Byte Count [11:0]  Remaining bytes (including this packet)
  Requester ID [31:16] Original requester (from request)
  Tag       [15:8]   Original tag (from request)
  Lower Addr [6:0]   Address bits [6:0] for byte alignment
```

### Configuration Request Header (3DW)

Used for Configuration Read/Write Type 0.

```
Byte 0          Byte 1          Byte 2          Byte 3
┌───────────────────────────────────────────────────────┐
│fmt│ type│ R │TC │  R│TH│TD│EP│Attr│  R│    Length     │  DW0
├───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───────────────┤
│        Requester ID       │  Tag  │ R  R│   FBE       │  DW1
├───────────────────────────┴───────┴─────┴─────────────┤
│  Bus  │ Dev │Fn │ExtRg│ Register │ R R│               │  DW2
└───────────────────────────────────────────────────────┘

Field Descriptions:
  fmt       [31:30]  Format: 00 (Read), 10 (Write)
  type      [28:24]  Type: 00100 (Configuration Type 0)
  Bus       [31:24]  Target bus number
  Device    [23:19]  Target device number
  Function  [18:16]  Target function number
  ExtReg    [11:8]   Extended register (for ECAM)
  Register  [7:2]    Register number (DW aligned)
```

### PTM Request/Response Headers (4DW)

Precision Time Measurement message headers.

```
PTM Request (fmt:type = 01:10100):
┌───────────────────────────────────────────────────────┐
│fmt│ type│ R │TC │ R│LN│TH│TD│EP│Attr│  R│    Length   │  DW0
├───┴───┴───┴───┴───┴───┴───┴───┴───┴───┴───────────────┤
│        Requester ID       │      Message Code         │  DW1
├───────────────────────────┴───────────────────────────┤
│                  Master Time [31:0]                   │  DW2
├───────────────────────────────────────────────────────┤
│                  Master Time [63:32]                  │  DW3
└───────────────────────────────────────────────────────┘

PTM Response (fmt:type = 11:10100):
  [Same as request, plus data payload with timing information]

Field Descriptions:
  fmt          [31:30]  Format: 01 (Request), 11 (Response)
  type         [28:24]  Type: 10100 (PTM Message)
  LN           [17]     Link-specific indicator
  TH           [16]     TLP Hints
  Message Code [7:0]   PTM-specific message code
  Master Time  [63:0]  64-bit timestamp
```

## Transaction Flow Examples

### Memory Write Transaction (Posted)

Memory writes are **posted transactions** - they do not receive completions.

```
Time    Application          TLP Layer               DLL Layer
  │
  ├─── Write Request ──────►
  │    adr=0x1000             ┌──────────────────┐
  │    len=4 DW                │  TLP Packetizer  │
  │    dat=<data>              │                  │
  │                            │  1. Create 3DW   │
  │                            │     MWr header   │
  │                            │  2. Set fmt=10   │
  │                            │  3. Set type=00  │
  │                            │  4. Length=4     │
  │                            │  5. Address=0x1000│
  │                            │  6. Tag=32 (fixed)│
  │                            │  7. Insert header│
  │                            │  8. Append data  │
  │                            └─────────┬────────┘
  │                                      │
  │                                      ├─── TLP Packet ──►
  │                                      │    (3DW header +
  │                                      │     4 DW data)
  │                                      │
  │    [No completion]                   ▼
  │                              [To DLL for transmission]

Packet Structure:
  Beat 0: DW0 [Header] | DW1 [Header]
  Beat 1: DW2 [Header] | Data[0]
  Beat 2: Data[1]      | Data[2]
  Beat 3: Data[3]      | (last)
```

**Posted Transaction:** Completes when transmitted to DLL. No acknowledgment required.

### Memory Read Transaction (Non-Posted)

Memory reads are **non-posted transactions** - they require completions.

```
Time    Application          TLP Controller          TLP Layer         DLL Layer
  │
  ├─── Read Request ────────►
  │    adr=0x2000              ┌────────────────┐
  │    len=8 DW                 │ Check tag avail│
  │                             │                │
  │                             │ Tag available? │
  │                             │ YES: tag=0     │
  │                             └────┬───────────┘
  │                                  │
  │                                  ├─── Forward with tag=0 ──►
  │                                  │                          ┌─────────────┐
  │                                  │                          │ Packetizer  │
  │                                  │                          │ Create MRd  │
  │                                  │                          │ 3DW header  │
  │                                  │                          │ tag=0       │
  │                                  │                          │ len=8       │
  │                                  │                          └──────┬──────┘
  │                                  │                                 │
  │                                  ├─── Store in req_queue ─────     │
  │                                  │    {tag=0, channel, user_id}    │
  │                                  │                                 │
  │                                  │                                 ├─► TLP Packet
  │                                  │                                      (3DW MRd)
  │    [Wait for completion...]      │                                      len=8
  │                                  │                                      tag=0
  ⋮                                  ⋮                                      ▼
  │                                  │                              [To DLL/PHY]
  │    [Time passes: request sent, processed by remote device]
  │    [Remote device sends completion back]
  │                                  │
  │                                  │                          ◄── CplD received
  │                                  │                                 tag=0
  │                                  │                                 len=8
  │                                  │                                 ┌─────────────┐
  │                                  │                                 │Depacketizer │
  │                                  │                                 │Extract hdr  │
  │                                  │                                 │tag=0        │
  │                                  │                                 └──────┬──────┘
  │                                  │                                        │
  │                                  ◄─── Completion (tag=0) ────────────────┘
  │                                  │
  │                                  │  ┌─────────────────────┐
  │                                  │  │ Route to buffer[0]  │
  │                                  │  │ based on tag        │
  │                                  │  └──────────┬──────────┘
  │                                  │             │
  │                                  │  ┌──────────▼──────────┐
  │                                  │  │ Check req_queue:    │
  │                                  │  │ Next expected=tag 0 │
  │                                  │  │ Forward data        │
  │                                  │  └──────────┬──────────┘
  │                                  │             │
  ◄─── Completion Data ─────────────────────────┘
  │    dat=<data>
  │    tag=0
  │    end=1 (last completion)
  │
  │                                  └─── Return tag 0 to pool
  │                                       (available for reuse)

Packet Structures:

Request (3DW MRd, no data):
  Beat 0: DW0 [Header] | DW1 [Header]
  Beat 1: DW2 [Header] | (last, no data)

Completion (3DW CplD, 8 DW data):
  Beat 0: DW0 [Header] | DW1 [Header]
  Beat 1: DW2 [Header] | Data[0]
  Beat 2: Data[1]      | Data[2]
  Beat 3: Data[3]      | Data[4]
  Beat 4: Data[5]      | Data[6]
  Beat 5: Data[7]      | (last)
```

**Non-Posted Transaction:** Request held until completion received. Tag recycled after completion.

### Split Completions (Large Reads)

Large read requests may receive multiple completion packets.

```
Application Request: Read 512 DW from address 0x10000

Request:
  ┌────────────────────────────────────┐
  │ MRd32: adr=0x10000, len=512, tag=1 │
  └────────────────────────────────────┘
                    │
                    ▼
         [Sent to remote device]
                    │
                    ▼
         [Device splits into max payload]
         [Assume max payload = 128 DW]
                    │
    ┌───────────────┼───────────────┬───────────────┐
    ▼               ▼               ▼               ▼
CplD #1         CplD #2         CplD #3         CplD #4
tag=1           tag=1           tag=1           tag=1
len=128         len=128         len=128         len=128
byte_count=2048 byte_count=1536 byte_count=1024 byte_count=512
lower_addr=0x00 lower_addr=0x00 lower_addr=0x00 lower_addr=0x00
data[0:127]     data[128:255]   data[256:383]   data[384:511]
end=0           end=0           end=0           end=1 ← Last

TLP Controller Operation:
  1. All CplDs route to same buffer (tag=1)
  2. Data accumulated in order
  3. When end=1 detected:
     - Forward complete 512 DW to application
     - Return tag 1 to available pool
     - Pop req_queue entry
```

## Flow Control Mechanism

PCIe uses **credit-based flow control** to prevent buffer overflow. The TLP layer must respect credit limits for three traffic classes:

### Credit Pools

```
┌─────────────────────────────────────────────────────────┐
│                    Flow Control Credits           │
├─────────────────────────────────────────────────────────┤
│                                                   │
│  Posted (P)           Non-Posted (NP)      Completion(Cpl)│
│  ┌──────────┐         ┌──────────┐         ┌──────────┐ │
│  │ Header   │         │ Header   │                │ Header   │ │
│  │ Credits  │         │ Credits  │                │ Credits  │ │
│  │ (PHC)    │         │ (NPHC)   │                │ (CPLHC)  │ │
│  ├──────────┤         ├──────────┤         ├──────────┤ │
│  │ Data     │         │ Data     │         │ Data │     │
│  │ Credits  │         │ Credits  │                │ Credits  │ │
│  │ (PDC)    │         │ (NPDC)   │                │ (CPLD)   │ │
│  └──────────┘         └──────────┘         └──────────┘ │
│                                                   │
│  Memory Writes       Memory Reads        Completions    │
│  I/O Writes          I/O Reads           (MRd, CfgRd)   │
│  Messages            Config Reads                 │
│                      Atomics                      │
└─────────────────────────────────────────────────────────┘

Credit Types:
  - Header Credits: Count of TLP packets (1 credit per TLP)
  - Data Credits:   Count of DWORDs payload (N credits for N DW)

Credit Management:
  - Receiver advertises available buffer space via DLLPs
  - Transmitter consumes credits when sending TLPs
  - Receiver returns credits via UpdateFC DLLPs
```

### Credit-Based Throttling

```
┌─────────────────────────────────────────────────────────┐
│              TLP Transmission Decision            │
└─────────────────────────────────────────────────────────┘
                                                    │
                          ▼
                 ┌─────────────────┐
                 │ TLP ready to TX                  │
                 └────────┬────────┘
                                                    │
          ┌───────────────┼───────────────┐
          │               │                         │
          ▼               ▼               ▼
    Memory Write?   Memory Read?    Completion?
          │               │                         │
          ▼               ▼               ▼
     Check Posted    Check Non-Posted  Check Cpl
     Credits (P)     Credits (NP)      Credits (Cpl)
          │               │                         │
    ┌─────┴─────┐   ┌─────┴─────┐   ┌─────┴─────┐
    │           │   │           │   │           │
    ▼           ▼   ▼           ▼   ▼           ▼
  PHC >= 1?  PDC >= len?  NPHC >= 1?  NPDC >= 0?  CPLHC >= 1?  CPLD >= len?
  (header)   (data)       (header)    (no data)   (header)     (data)
    │           │   │           │   │           │
    └─────┬─────┘   └─────┬─────┘   └─────┬─────┘
          │               │               │
     YES? │          YES? │          YES? │
          ▼               ▼               ▼
    ┌─────────┐     ┌─────────┐     ┌─────────┐
    │ Send TLP│     │ Send TLP│     │ Send TLP│
    │         │     │         │     │         │
    │ PHC--   │     │ NPHC--  │     │ CPLHC-- │
    │ PDC-=len│     │         │     │ CPLD-=len│
    └─────────┘     └─────────┘     └─────────┘
          │               │               │
          │    NO?        │    NO?        │    NO?
          │               │               │
          ▼               ▼               ▼
      ┌───────────────────────────────────┐
      │      WAIT - Throttle TX           │
      │  (Cannot send until credits avail)│
      └───────────────────────────────────┘
                      │
                      ▼
                 [Wait for UpdateFC DLLP]
                 [Credits replenished]
                      │
                      └──────┐
                             │
                     [Retry transmission]
```

**Note:** In LitePCIe, flow control is typically handled at the DLL layer through DLLP exchange. The TLP layer focuses on packet formatting and tag management.

### Flow Control Initialization

```
Link Training Sequence:
  1. LTSSM reaches L0 (operational state)
  2. Each side advertises initial credits via InitFC DLLPs:
     - InitFC1-P  (Posted header/data credits)
     - InitFC1-NP (Non-Posted header/data credits)
     - InitFC1-Cpl (Completion header/data credits)
     - InitFC2-P, InitFC2-NP, InitFC2-Cpl (confirmation)
  3. Credits exchanged in both directions
  4. TLP transmission can begin

During Operation:
  - UpdateFC-P, UpdateFC-NP, UpdateFC-Cpl DLLPs
  - Periodically update credit counts
  - Allow continuous data flow
```

## Routing Methods

TLPs use different routing methods depending on type:

### Address-Based Routing (Memory TLPs)

```
┌────────────────────────────────────────────┐
│          Memory Read/Write TLP             │
├────────────────────────────────────────────┤
│  Address: 0x00000000F0000000               │
└────────────────┬───────────────────────────┘
                 │
                 ▼
         ┌───────────────┐
         │ PCIe Switch   │
         │               │
         │ Check BAR     │
         │ mapping       │
         └───────┬───────┘
                 │
    ┌────────────┼────────────┐
    │            │            │
    ▼            ▼            ▼
  Port 0       Port 1      Port 2
  BAR:         BAR:        BAR:
  0xF0000000   0xE0000000  0xD0000000
  ↓ MATCH      ↓ no       ↓ no
  Route here

Routing Decision:
  1. Compare address against all downstream BARs
  2. Forward to matching port
  3. If no match: route upstream toward root
```

### ID-Based Routing (Completions, Config)

```
┌────────────────────────────────────────────┐
│             Completion TLP  │
├────────────────────────────────────────────┤
│  Requester ID: Bus=1, Dev=0, Func=0        │
│  (Who sent the original request)           │
└────────────────┬───────────────────────────┘
                              │
                 ▼
         ┌───────────────┐
         │ PCIe Switch        │
         │                    │
         │ Check Bus#         │
         │ in Req ID          │
         └───────┬───────┘
                              │
    Bus 1 downstream?
                              │
         ▼
       Port 1 (secondary bus = 1)
                              │
         ▼
    ┌────────────┐
                              │ Endpoint                │  Bus=1, Dev=0, Func=0
                              │ (Requester)             │  ← Completion delivered
    └────────────┘

Routing Decision:
  1. Extract Requester ID (for Cpl) or Dest ID (for Config)
  2. Compare bus number against routing table
  3. Forward to port containing that bus number
```

### Implicit Routing (Messages)

```
Message TLPs may use:
  - Broadcast: All downstream ports
  - Local: Terminate at receiver
  - Routing by ID: Similar to completions
  - Routing by Address: Similar to memory TLPs
```

## TLP Layer Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        TLP LAYER ARCHITECTURE                           │
└─────────────────────────────────────────────────────────────────────────┘

APPLICATION INTERFACES:
  request_layout:        adr, len, we, dat, req_id, tag, channel, user_id
  completion_layout:     adr, len, dat, req_id, cmp_id, tag, err, end
  configuration_layout:  bus, dev, func, register, we, dat, req_id, tag
  ptm_layout:           request, response, requester_id, master_time, dat

          │ Requests          │ Completions      │ Config        │ PTM
          ▼                   ▼                  ▼               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         TLP PACKETIZER                                  │
│                     (litepcie/tlp/packetizer.py)                        │
│                                                                         │
│  ┌───────────────────┐   ┌───────────────────┐   ┌─────────────────┐    │
│  │ Request Formatter │   │ Completion Format │   │  PTM Formatter  │    │
│  │                   │   │                   │   │                 │    │
│  │ • Detect 32/64-bit│   │ • Set CplD/Cpl    │   │ • Set Req/Res   │    │
│  │ • Set MRd32/MRd64 │   │ • Set status SC/UR│   │ • Insert time   │    │
│  │   or MWr32/MWr64  │   │ • Set byte_count  │   │ • Message code  │    │
│  │ • Set length      │   │ • Set lower_addr  │   │                 │    │
│  │ • Tag assignment  │   │ • Match req tag   │   │                 │    │
│  └─────────┬─────────┘   └─────────┬─────────┘   └────────┬────────┘    │
│            │                       │                      │             │
│            └───────────────┬───────┴──────────────────────┘             │
│                            │                                            │
│                            ▼                                            │
│                   ┌─────────────────┐                                   │
│                   │    Arbiter      │                                   │
│                   │  (Round-Robin)  │                                   │
│                   └────────┬────────┘                                   │
│                            │                                            │
│                            ▼                                            │
│                   ┌─────────────────┐                                   │
│                   │  Stream Buffer  │                                   │
│                   └────────┬────────┘                                   │
│                            │                                            │
│                            ▼                                            │
│            ┌───────────────────────────────┐                            │
│            │   Header Inserter (3DW/4DW)   │                            │
│            │                               │                            │
│            │  Select based on fmt field:   │                            │
│            │    fmt[1]=0 → 3DW inserter    │                            │
│            │    fmt[1]=1 → 4DW inserter    │                            │
│            │                               │                            │
│            │  Data widths: 64/128/256/512  │                            │
│            │                               │                            │
│            │  Header alignment:            │                            │
│            │   - 64b:  2 beats for header  │                            │
│            │   - 128b: 1 beat for header   │                            │
│            │   - 256b: header + data       │                            │
│            │   - 512b: header + more data  │                            │
│            └───────────────┬───────────────┘                            │
│                            │                                            │
│                    ┌───────┴────────┐                                   │
│                    │ Endianness Swap│                                   │
│                    │ (if needed)    │                                   │
│                    └───────┬────────┘                                   │
└────────────────────────────┼────────────────────────────────────────────┘
                             │ phy_layout(data_width)
                             │ {dat[N], be[N/8]}
                             ▼
                    ┌──────────────────┐
                    │   TO DLL LAYER   │
                    └──────────────────┘


                    ┌──────────────────┐
                    │  FROM DLL LAYER  │
                    └────────┬─────────┘
                             │ phy_layout(data_width)
┌────────────────────────────┼────────────────────────────────────────────┐
│                            │                                            │
│                    ┌───────▼────────┐                                   │
│                    │ Endianness Swap│                                   │
│                    │ (if needed)    │                                   │
│                    └───────┬────────┘                                   │
│                            │                                            │
│            ┌───────────────▼───────────────┐                            │
│            │   Header Extracter (3DW/4DW)  │                            │
│            │                               │                            │
│            │  Extract header from stream:  │                            │
│            │   - 64b:  2 beats → header    │                            │
│            │   - 128b: 1 beat → header     │                            │
│            │   - 256b: extract + shift     │                            │
│            │   - 512b: extract + shift     │                            │
│            └───────────────┬───────────────┘                            │
│                            │                                            │
│                            ▼                                            │
│                   ┌─────────────────┐                                   │
│                   │ Header Decoder  │                                   │
│                                     │ (Extract fmt:type)                │
│                   └────────┬────────┘                                   │
│                            │                                            │
│                            ▼                                            │
│                   ┌─────────────────┐                                   │
│                   │   Dispatcher    │                                   │
│                                     │ Route by fmt:type                 │
│                   └────────┬────────┘                                   │
│                            │                                            │
│        ┌───────────────────┼───────────────────┬─────────────┐          │
│        │                   │                   │             │          │
│        ▼                   ▼                   ▼             ▼          │
│  ┌──────────┐       ┌──────────┐       ┌──────────┐   ┌─────────┐       │
│  │ Memory   │       │Completion│       │  Config  │   │   PTM   │       │
│  │ Request  │       │ Decoder  │       │ Decoder  │   │ Decoder │       │
│  │ Decoder  │       │          │       │          │   │         │       │
│  │          │       │ • Extract│       │ • Bus/   │   │ • Time  │       │
│  │ • Address│       │   status │       │   Dev/   │   │   stamp │       │
│  │ • Length │       │ • Match  │       │   Func   │   │ • Msg   │       │
│  │ • Detect │       │   tag    │       │ • Reg    │   │   code  │       │
│  │   Rd/Wr  │       │ • Byte   │       │          │   │         │       │
│  │          │       │   count  │       │          │   │         │       │
│  └─────┬────┘       └─────┬────┘       └─────┬────┘   └────┬────┘       │
│        │                  │                  │             │            │
│                        TLP DEPACKETIZER                                 │
│                     (litepcie/tlp/depacketizer.py)                      │
└────────┼──────────────────┼──────────────────┼─────────────┼──────────┘
         │                  │                  │             │
         ▼                  ▼                  ▼             ▼
   request_layout    completion_layout   config_layout  ptm_layout
         │                  │
         ▼                  │
┌────────────────────┐      │
│  TLP CONTROLLER    │      │
│  (litepcie/tlp/    │      │
│   controller.py)   │      │
│                    │      │
│  ┌──────────────┐  │      │
│  │  Tag Queue   │  │      │
│  │              │  │      │
│  │ Available    │  │      │
│  │ tags: 0..N-1 │  │      │
│  └──────┬───────┘  │      │
│         │          │      │
│         ▼          │      │
                     │    Allocate tag ───┼──────┘
│    on read req     │
│         │          │
│         ▼          │
│  ┌──────────────┐  │
│  │ Request Queue│  │
│  │              │  │
│  │ Store issued │  │
│  │ read tags    │  │
│  │ {tag, ch, ID}│  │
│  └──────┬───────┘  │
│         │          │
│         ▼          │
│  ┌──────────────┐  │◄──── Completion arrives
│  │ Completion   │  │      with tag=X
│  │ Buffers      │  │
│  │              │  │      ┌────────────────┐
│                    │ Buffer[0] ◄──┼──┼──────┤ Demux on tag   │
│                    │ Buffer[1] ◄──┼──┼──────┤ (tag → buffer) │
│                    │    ...    ◄──┼──┼──────┤                │
│                    │ Buffer[N] ◄──┼──┼──────┤                │
│  │              │  │      └────────────────┘
│  │              │  │
│  │ Reorder:     │  │
│  │ Output in    │  │      ┌────────────────┐
│                    │ request order├──┼──────► Mux based on   │
│  │              │  │        req_queue order│
│  └──────────────┘  │      └────────────────┘
│                    │              │
│  Return tag to     │              │
                     │  tag queue when ◄──┼──────────────┘
│  completion done   │       (when end=1)
│                    │
└────────────────────┘
         │
         ▼
    APPLICATION
    (Ordered completions)
```

## Implementation Details

### TLP Packetizer Operation

**File:** `litepcie/tlp/packetizer.py`

The packetizer converts high-level request/completion structures into TLP format:

```python
# Example: Memory Write Request packetization
# Input: req_sink (request_layout)
#   - we=1, adr=0x1000, len=4, dat=<data>, req_id=0x0100, tag=X

# Step 1: Determine format
if req_sink.we:
    if address_width == 64 and adr[32:] != 0:
        fmt = fmt_dict["mem_wr64"]  # 11 (4DW with data)
    else:
        fmt = fmt_dict["mem_wr32"]  # 10 (3DW with data)
else:
    # Similar for reads (01 or 00)

# Step 2: Build TLP header fields
tlp_req.fmt    = fmt
tlp_req.type   = 0b00000  # Memory
tlp_req.tc     = 0        # Traffic class 0
tlp_req.td     = 0        # No digest
tlp_req.ep     = 0        # Not poisoned
tlp_req.attr   = 0        # No special attributes
tlp_req.length = req_sink.len
tlp_req.requester_id = req_sink.req_id
tlp_req.tag    = req_sink.tag
tlp_req.first_be = 0xF    # All bytes enabled
tlp_req.last_be  = 0xF if len > 1 else 0x0
tlp_req.address  = req_sink.adr

# Step 3: Encode header to raw format
tlp_request_header.encode(tlp_req, tlp_raw_req_header)

# Step 4: Apply endianness conversion
dword_endianness_swap(src=tlp_raw_req_header, dst=tlp_raw_req.header,
                      data_width=data_width, endianness=endianness)

# Step 5: Insert header into data stream
# Uses HeaderInserter64b/128b/256b/512b based on data_width
# - Inserts 3DW or 4DW header at start of packet
# - Shifts data accordingly
# - Handles alignment for different data widths

# Output: source (phy_layout)
#   - dat[N], be[N/8] formatted for DLL layer
```

### TLP Depacketizer Operation

**File:** `litepcie/tlp/depacketizer.py`

The depacketizer extracts headers and routes TLPs:

```python
# Example: Completion TLP depacketization
# Input: sink (phy_layout from DLL)

# Step 1: Extract header
# Uses HeaderExtracter64b/128b/256b/512b
# - Accumulates header bytes over multiple beats (for 64-bit)
# - Single beat for 128-bit and wider
# - Shifts data to remove header

# Step 2: Decode common header
tlp_common_header.decode(header, dispatch_sink)
# Extracts: fmt, type

# Step 3: Route based on fmt:type
fmt_type = Cat(dispatch_sink.type, dispatch_sink.fmt)

if fmt_type == fmt_type_dict["cpld"]:  # Completion with data
    dispatcher.sel = "COMPLETION"

    # Decode full completion header
    tlp_completion_header.decode(header, tlp_cmp)

    # Extract fields:
    cmp_source.len        = tlp_cmp.length
    cmp_source.req_id     = tlp_cmp.requester_id
    cmp_source.cmp_id     = tlp_cmp.completer_id
    cmp_source.tag        = tlp_cmp.tag
    cmp_source.err        = (tlp_cmp.status != 0)
    cmp_source.end        = (tlp_cmp.length == tlp_cmp.byte_count[2:])
    cmp_source.adr        = tlp_cmp.lower_address
    cmp_source.dat        = tlp_cmp.dat

# Output: cmp_source (completion_layout)
#   - Converted back to high-level format
```

### TLP Controller Operation

**File:** `litepcie/tlp/controller.py`

The controller manages tags and reorders completions:

```python
# Initialization: Fill tag queue
for i in range(max_pending_requests):
    tag_queue.sink.valid = 1
    tag_queue.sink.tag = i

# On Read Request:
if req_sink.valid and not req_sink.we:
    if tag_queue.source.valid:  # Tag available
        tag = tag_queue.source.tag
        tag_queue.source.ready = 1  # Pop tag

        # Store in request queue
        req_queue.sink.valid = 1
        req_queue.sink.tag = tag
        req_queue.sink.channel = req_sink.channel
        req_queue.sink.user_id = req_sink.user_id

        # Forward request with assigned tag
        req_source.tag = tag
        req_source.connect(req_sink)

# On Completion Received:
cmp_tag = cmp_sink.tag

# Route to appropriate buffer
cmp_bufs[cmp_tag].sink.connect(cmp_reorder)

# Output in request order (from req_queue)
expected_tag = req_queue.source.tag
cmp_source.connect(cmp_bufs[expected_tag].source)

if cmp_source.valid and cmp_source.last and cmp_source.end:
    req_queue.source.ready = 1  # Pop request

    # Return tag to pool
    tag_queue.sink.valid = 1
    tag_queue.sink.tag = cmp_sink.tag
```

**Key Features:**
- **Tag Pool:** Pre-allocated tags (0 to N-1) for N max pending requests
- **Request Queue:** FIFO storing issued read request metadata
- **Completion Buffers:** Per-tag buffers (depth = 4 * max_request_size / data_width)
- **Reordering:** Outputs completions in original request order, not arrival order
- **Buffering:** Completions can arrive out-of-order; buffers hold until ready

## Data Width Handling

LitePCIe supports multiple data widths: 64, 128, 256, 512 bits.

### Header Insertion Examples

**64-bit Data Width (3DW Header):**
```
Input (tlp_raw_layout):
  header[127:0] = [DW0 | DW1 | DW2 | reserved]
  dat[63:0]     = [Data_DW0 | Data_DW1]

Output (phy_layout):
  Beat 0: [DW0 | DW1]            be=[0xF, 0xF]
  Beat 1: [DW2 | Data_DW0]       be=[0xF, 0xF]
  Beat 2: [Data_DW1 | Data_DW2]  be=[0xF, 0xF]
  ...
```

**128-bit Data Width (3DW Header):**
```
Input (tlp_raw_layout):
  header[127:0] = [DW0 | DW1 | DW2 | reserved]
  dat[127:0]    = [Data_DW0 | Data_DW1 | Data_DW2 | Data_DW3]

Output (phy_layout):
  Beat 0: [DW0 | DW1 | DW2 | Data_DW0]       be=[0xF, 0xF, 0xF, 0xF]
  Beat 1: [Data_DW1 | Data_DW2 | Data_DW3 | Data_DW4]
  ...
```

**256-bit Data Width (4DW Header):**
```
Input (tlp_raw_layout):
  header[127:0] = [DW0 | DW1 | DW2 | DW3]
  dat[255:0]    = [Data_DW0..Data_DW7]

Output (phy_layout):
  Beat 0: [DW0 | DW1 | DW2 | DW3 | Data_DW0 | Data_DW1 | Data_DW2 | Data_DW3]
  Beat 1: [Data_DW4 | Data_DW5 | Data_DW6 | Data_DW7 | ...]
  ...
```

Each data width has specialized header inserter/extracter implementations optimized for that width.

## Integration with Other Layers

### Interface to DLL Layer (Downstream)

```
TLP Layer Output: phy_layout(data_width)
  - dat[N]:    Data payload (N = 64/128/256/512 bits)
  - be[N/8]:   Byte enables
  - valid:     Data valid
  - ready:     Ready to accept
  - first:     First beat of TLP
  - last:      Last beat of TLP

DLL Layer expects:
  - Complete TLP packets (header + data)
  - first flag on header beat
  - last flag on final data beat
  - Byte enables indicate valid bytes

DLL will add:
  - Sequence number (12-bit, wrapping)
  - LCRC (32-bit CRC)
  - Retry buffering
```

### Interface to Application Layer (Upstream)

```
Application Output: request_layout / completion_layout
  Request:
    - adr:     Address (32 or 64 bits)
    - len:     Length in DWORDs (10 bits, max 1024)
    - we:      Write enable (1=write, 0=read)
    - dat:     Data (for writes)
    - req_id:  Requester ID (Bus:Dev:Func)
    - tag:     Managed by controller
    - channel: Internal routing
    - user_id: Packet identification

  Completion:
    - dat:     Data (for reads)
    - len:     Length in DWORDs
    - req_id:  Original requester
    - cmp_id:  Completer ID
    - tag:     Matched from request
    - err:     Error flag
    - end:     Last completion flag
    - adr:     Lower address bits
    - channel: Internal routing
    - user_id: Packet identification

TLP Layer provides:
  - Transparent tag management (app doesn't assign tags)
  - Automatic header generation
  - In-order completion delivery
  - Error propagation
```

## Configuration Parameters

### Key Parameters

```python
# TLP Packetizer/Depacketizer
data_width = 64/128/256/512    # PHY data width in bits
endianness = "little"/"big"    # Byte order (typically "little")
address_width = 32/64          # Address bus width
address_mask = 0x0             # Address masking for BAR
capabilities = ["REQUEST",     # Support memory requests
                "COMPLETION",  # Support completions
                "CONFIGURATION", # Support config TLPs
                "PTM"]         # Support Precision Time Measurement

# TLP Controller
max_pending_requests = 8/16/32/64  # Number of concurrent reads
cmp_bufs_buffered = True           # Add buffering to cmp buffers

# From tlp/common.py
max_payload_size = 512  # Maximum TLP payload (bytes)
max_request_size = 512  # Maximum read request size (bytes)
```

### Address Width Selection

```python
# 32-bit addressing (addresses < 4GB)
address_width = 32
# TLPs use 3DW headers (MRd32, MWr32)

# 64-bit addressing (addresses >= 4GB or forced)
address_width = 64
# TLPs use 4DW headers when adr[63:32] != 0
# Exception: UltraScale+ with 256/512-bit forces 4DW always

# UltraScale+ detection (from packetizer.py):
if platform.device in ["xcku", "xcvu", "xczu", "xcau"]:
    if data_width in [256, 512]:
        force_64b = True  # Always use 4DW headers
```

## Error Handling

### Completion Status Codes

```python
# From tlp/common.py cpl_dict
cpl_status = {
    0b000: "SC",   # Successful Completion - Data is valid
    0b001: "UR",   # Unsupported Request - Request not supported
    0b010: "CRS",  # Configuration Request Retry Status
    0b011: "CA",   # Completer Abort - Error during processing
}

# Depacketizer sets err flag for non-SC status
cmp_source.err = (tlp_cmp.status != 0)
```

### Error Propagation

```
Completion with error:
  1. Depacketizer detects status != SC
  2. Sets cmp_source.err = 1
  3. Application receives completion with err flag
  4. Application should discard data and handle error

Unsupported TLP types:
  1. Dispatcher routes to "DISCARD" sink
  2. TLP consumed but not processed
  3. No error reported to application
  4. Remote device may timeout and retry
```

### Poisoned TLP (EP bit)

```
EP (Error Poisoned) bit in header:
  - Set by device detecting data corruption
  - Propagated through switches
  - Receiver should:
    1. Check EP bit in header
    2. Discard poisoned data
    3. Report error to software

LitePCIe:
  - Packetizer sets EP=0 (no poison)
  - Depacketizer can read EP bit from header if needed
  - Application can check tlp_xxx.ep field
```

## Performance Considerations

### Maximum Throughput

```
Theoretical throughput = (data_width / 8) * clock_frequency

Example: 256-bit @ 250 MHz
  = (256 / 8) * 250 MHz
  = 32 bytes/cycle * 250 MHz
  = 8 GB/s (64 Gb/s)

Efficiency factors:
  - Header overhead: 12-16 bytes per TLP
  - Flow control: Credit exhaustion stalls
  - Tag availability: Read throughput limited by pending tags
  - DLL overhead: ACK/NAK, retry buffer
  - PHY overhead: Ordered sets (SKP, TS)

Typical efficiency: 85-95% for large transfers
```

### Optimization Strategies

**1. Maximize Payload Size**
```
Use max_payload_size = 512 bytes
  - Reduces header overhead (3-4 bytes per 512 bytes vs. per 64 bytes)
  - Amortizes fixed costs

Configure via PCIe Device Control Register:
  Max_Payload_Size = 010b (512 bytes)
```

**2. Increase Data Width**
```
Use 256-bit or 512-bit data width:
  - Fewer cycles per TLP
  - Better utilization of PHY bandwidth
  - Requires wider application interface

Trade-off: More FPGA resources, routing complexity
```

**3. Increase Pending Requests**
```
max_pending_requests = 32 or 64
  - Hides read latency
  - Keeps pipeline full
  - Requires more buffer memory (tag buffers)

Memory = max_pending_requests * max_request_size * data_width/8
Example: 32 * 512 * 64/8 = 128 KB
```

**4. Pipeline Control Path**
```
cmp_bufs_buffered = True
  - Adds pipeline stage to completion buffers
  - Improves timing closure
  - Slight latency increase (1 cycle)

Use for high-speed designs (250+ MHz)
```

## Debugging and Verification

### Verification Points

**1. Header Encoding**
```
Check packetizer output:
  - fmt field correct (3DW vs 4DW, data vs no-data)
  - type field matches operation
  - length matches actual payload
  - address properly formatted
  - tag assigned (for reads)
  - byte enables correct

Tools: Simulation waveforms, ILA/Chipscope
```

**2. Header Decoding**
```
Check depacketizer output:
  - fmt:type correctly identifies TLP
  - fields extracted accurately
  - data aligned properly
  - completions routed to correct buffer
  - error status propagated

Verify against golden model or reference impl
```

**3. Tag Management**
```
Monitor TLP controller:
  - Tags allocated sequentially
  - No duplicate tags outstanding
  - Tags returned after completion
  - Request queue depth
  - Completion buffer occupancy

Check for tag exhaustion (requests stalled)
```

**4. Reordering**
```
Verify completions in-order:
  - Issue multiple reads (varying sizes)
  - Delay completions randomly
  - Check output matches request order

Test cases:
  - Out-of-order arrivals
  - Split completions
  - Error completions
```

### Common Issues

| Issue | Symptom | Cause | Solution |
|-------|---------|-------|----------|
| Tag exhaustion | Reads stall | All tags in use | Increase max_pending_requests |
| Completion timeout | No data returned | Tag mismatch | Check tag assignment logic |
| Data corruption | Wrong data | Endianness error | Verify endianness setting |
| Alignment errors | be signals wrong | Header insertion bug | Check header inserter FSM |
| Throughput low | < expected BW | Flow control stall | Check credit management |
| Completion stuck | Hangs waiting | Missing end flag | Verify byte_count logic |

## Summary

The TLP layer provides transaction-based communication for PCIe:

**Key Responsibilities:**
- Convert application requests to TLP format
- Decode incoming TLPs to application format
- Manage read request tags
- Reorder completions to match request order
- Handle multiple TLP types (Memory, Config, Completion, PTM)

**Architecture:**
- Packetizer: Application → TLP
- Depacketizer: TLP → Application
- Controller: Tag management, reordering

**Performance:**
- Supports 64 to 512-bit data widths
- Configurable pending request depth
- Credit-based flow control
- Optimized header insertion/extraction

**Interfaces:**
- Upstream: request/completion/config/ptm layouts
- Downstream: phy_layout to DLL

For detailed layer integration, see [Complete System Architecture](complete-system-architecture.md).
For flow control details, see [DLL Layer Architecture](dll-layer.md).
