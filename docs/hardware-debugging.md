# Hardware Debugging with LiteScope

This guide explains how to debug PIPEExternalPHY designs on hardware using LiteScope, LiteX's integrated logic analyzer.

## Overview

LiteScope is a platform-agnostic logic analyzer for LiteX designs that works on any FPGA (Xilinx, Lattice, Gowin, etc.). It captures internal signals during runtime and allows you to:
- Monitor LTSSM state transitions
- Observe PIPE TX/RX symbols
- Debug link training issues
- Analyze DLL packet flow
- Verify hardware timing

## Quick Start

### 1. Build Design with LiteScope

```python
from litescope import LiteScopeAnalyzer

# Add analyzer to your SoC
analyzer_signals = [
    # LTSSM signals
    phy.pipe.ltssm.current_state,
    phy.pipe.link_up,
    phy.pipe.ltssm.send_ts1,
    phy.pipe.ltssm.send_ts2,

    # PIPE signals
    phy.pipe.pipe_tx_data,
    phy.pipe.pipe_tx_datak,
    phy.pipe.pipe_rx_data,
    phy.pipe.pipe_rx_datak,
]

self.submodules.analyzer = LiteScopeAnalyzer(
    analyzer_signals,
    depth        = 4096,
    clock_domain = "pcie",
    csr_csv      = "analyzer.csv"
)
self.add_csr("analyzer")
```

### 2. Build and Load Bitstream

```bash
# Build
python3 examples/pcie_pipe_debug.py --build

# Load to FPGA
python3 examples/pcie_pipe_debug.py --load
```

### 3. Capture Signals

```bash
# Using litescope_cli
litescope_cli --csv analyzer.csv

# Or using Python API
from litescope import LiteScopeAnalyzerDriver
analyzer = LiteScopeAnalyzerDriver(csr_csv="analyzer.csv")
analyzer.configure_trigger(cond={"phy_pipe_link_up": 1})
analyzer.run(offset=128, length=512)
analyzer.upload()
analyzer.save("capture.vcd")
```

### 4. View Waveforms

```bash
# Open in GTKWave
gtkwave capture.vcd

# Or export to CSV
litescope_cli --csv analyzer.csv --export capture.csv
```

## Signal Groups

### LTSSM Signals

Monitor link training state machine:

```python
ltssm_signals = [
    "ltssm.current_state",    # 0=DETECT, 1=POLLING, 2=CONFIG, 3=L0, 4=RECOVERY
    "ltssm.link_up",          # Link trained
    "ltssm.send_ts1",         # Sending TS1 ordered sets
    "ltssm.send_ts2",         # Sending TS2 ordered sets
    "ltssm.ts1_detected",     # Received TS1 from partner
    "ltssm.ts2_detected",     # Received TS2 from partner
    "ltssm.rx_elecidle",      # RX electrical idle
    "ltssm.tx_elecidle",      # TX electrical idle
]
```

**Debug tips:**
- Stuck in DETECT → Check PHY power and receiver detection
- Stuck in POLLING → Verify TS1/TS2 exchange
- Link drops from L0 → Check electrical idle signaling

### PIPE Interface Signals

Monitor symbol-level communication:

```python
pipe_signals = [
    "pipe.pipe_tx_data",      # TX data byte (8 bits)
    "pipe.pipe_tx_datak",     # TX is K-character
    "pipe.pipe_rx_data",      # RX data byte
    "pipe.pipe_rx_datak",     # RX is K-character
]
```

**K-characters to look for:**
- `0xBC` (K28.5, COM) - Start of TS1/TS2
- `0x1C` (K28.0, SKP) - Clock compensation
- `0xFB` (K27.7, STP) - Start TLP
- `0x5C` (K28.2, SDP) - Start DLLP
- `0xFD` (K29.7, END) - End good packet
- `0xFE` (K30.7, EDB) - End bad packet

### DLL Signals

Monitor packet flow through DLL:

```python
dll_signals = [
    "dll_tx.tlp_sink.valid",     # TLP entering DLL TX
    "dll_tx.tlp_sink.ready",     # DLL TX ready
    "dll_tx.phy_source.valid",   # DLL TX to PIPE
    "dll_tx.phy_source.ready",   # PIPE ready
    "dll_rx.phy_sink.valid",     # PIPE to DLL RX
    "dll_rx.phy_sink.ready",     # DLL RX ready
    "dll_rx.tlp_source.valid",   # DLL RX to TLP
    "dll_rx.tlp_source.ready",   # TLP layer ready
]
```

**Debug tips:**
- TX stalled → Check `tlp_sink.ready` and backpressure
- RX not receiving → Check `phy_sink.valid` from PIPE
- Packets dropped → Monitor LCRC errors in DLL

### Datapath Signals

Monitor clock domain crossing and width conversion:

```python
datapath_signals = [
    "tx_datapath.source.valid",  # TX CDC output
    "tx_datapath.source.ready",  # TX path ready
    "rx_datapath.sink.valid",    # RX CDC input
    "rx_datapath.sink.ready",    # RX path ready
]
```

## Common Debug Scenarios

### Scenario 1: Link Not Training

**Symptoms:** Stuck in DETECT or POLLING state

**Signals to monitor:**
```python
analyzer_signals = [
    ltssm.current_state,
    ltssm.rx_elecidle,
    ltssm.send_ts1,
    ltssm.ts1_detected,
    pipe.pipe_tx_data,
    pipe.pipe_rx_data,
]
```

**What to check:**
1. Is `rx_elecidle` transitioning? (Should go low in POLLING)
2. Are TS1 being sent? (`send_ts1` high, `pipe_tx_data` shows 0xBC)
3. Are TS1 being received? (`ts1_detected` high)
4. Check PIPE PHY power and clock

### Scenario 2: Link Training Then Dropping

**Symptoms:** Reaches L0 then returns to RECOVERY

**Signals to monitor:**
```python
analyzer_signals = [
    ltssm.current_state,
    ltssm.link_up,
    ltssm.rx_elecidle,
    pipe.pipe_tx_datak,
    pipe.pipe_rx_datak,
    dll_tx.tlp_sink.valid,
    dll_rx.tlp_source.valid,
]
```

**What to check:**
1. SKP ordered sets being sent/received correctly?
2. Electrical idle triggering recovery?
3. Packet errors causing retraining?

### Scenario 3: No Data Flow

**Symptoms:** Link trained but no packets

**Signals to monitor:**
```python
analyzer_signals = [
    ltssm.link_up,
    dll_tx.tlp_sink.valid,
    dll_tx.phy_source.valid,
    pipe.pipe_tx_data,
    pipe.pipe_tx_datak,
]
```

**What to check:**
1. Are TLPs being sent to DLL? (`tlp_sink.valid`)
2. Is DLL outputting to PIPE? (`phy_source.valid`)
3. Are packets framed correctly? (STP/END K-characters)

## Trigger Conditions

### Trigger on Link Up

```python
analyzer.configure_trigger(cond={
    "phy_pipe_link_up": 1
})
```

### Trigger on State Change

```python
analyzer.configure_trigger(cond={
    "phy_pipe_ltssm_current_state": "!=0"  # Exit DETECT
})
```

### Trigger on K-Character

```python
analyzer.configure_trigger(cond={
    "phy_pipe_pipe_tx_datak": 1,
    "phy_pipe_pipe_tx_data": 0xBC  # COM symbol
})
```

### Trigger on Error

```python
analyzer.configure_trigger(cond={
    "phy_pipe_ltssm_current_state": 4  # RECOVERY state
})
```

## Advanced Usage

### Remote Access via Etherbone

If your platform has Ethernet:

```python
# In SoC __init__:
self.submodules.eth_phy = LiteEthPHY(...)
self.add_etherbone(phy=self.eth_phy, ip_address="192.168.1.50")
```

Then capture remotely:

```bash
litescope_cli --csv analyzer.csv --host 192.168.1.50
```

### Continuous Capture Mode

```python
while True:
    analyzer.run(offset=0, length=4096)
    analyzer.upload()
    analyzer.save(f"capture_{time.time()}.vcd")
    time.sleep(1)
```

### Multi-Analyzer Setup

Capture different clock domains:

```python
# PCIE domain analyzer
self.submodules.analyzer_pcie = LiteScopeAnalyzer(
    pcie_signals,
    depth=4096,
    clock_domain="pcie",
    csr_csv="analyzer_pcie.csv"
)

# SYS domain analyzer
self.submodules.analyzer_sys = LiteScopeAnalyzer(
    sys_signals,
    depth=4096,
    clock_domain="sys",
    csr_csv="analyzer_sys.csv"
)
```

## Performance Considerations

### Sample Depth

- **1024 samples:** ~8µs at 125 MHz (good for quick captures)
- **4096 samples:** ~32µs at 125 MHz (default, good balance)
- **16384 samples:** ~130µs at 125 MHz (longer captures, more BRAM)

### Trigger Offset

```python
# Capture before and after trigger
analyzer.run(
    offset=2048,  # 50% pre-trigger data
    length=4096   # Total samples
)
```

### Clock Domain Selection

```python
# PCIE clock domain (125 MHz for Gen1)
clock_domain="pcie"  # Use this for LTSSM, PIPE signals

# SYS clock domain (varies)
clock_domain="sys"   # Use this for TLP layer signals
```

## LiteScope Advantages

LiteScope provides several advantages for LiteX designs:

- **Platform-agnostic:** Works on any FPGA (Xilinx, Lattice, Gowin, etc.)
- **Python-based:** Configure and capture using Python scripts
- **Runtime access:** Capture signals via Wishbone/Etherbone without JTAG
- **Export formats:** VCD for GTKWave, CSV for analysis
- **Integration:** Natural integration with LiteX SoC designs
- **Open-source:** Full source code available

## References

- [LiteScope Documentation](https://github.com/enjoy-digital/litescope)
- [usb3_pipe Examples](https://github.com/enjoy-digital/usb3_pipe)
- [examples/pcie_pipe_debug.py](../examples/pcie_pipe_debug.py) - Complete example

## Troubleshooting

### Analyzer Not Found

```
Error: CSR 'analyzer' not found
```

**Solution:** Make sure you added `self.add_csr("analyzer")` after creating analyzer.

### No Trigger

**Solution:** Check trigger condition is reachable. Try simple trigger first:

```python
analyzer.configure_trigger(cond={})  # Trigger immediately
```

### Empty Capture

**Solution:** Verify signals are in correct clock domain. Use `clock_domain="pcie"` for PIPE/LTSSM signals.

### BRAM Usage Too High

**Solution:** Reduce sample depth or number of signals:

```python
LiteScopeAnalyzer(signals[:10], depth=1024)  # Fewer signals, less depth
```
