# Phase 9 Dependencies - Internal Transceiver Support

**Last Updated:** 2025-10-17
**Status:** Pre-Implementation Documentation
**Purpose:** Document external dependencies required for Phase 9

---

## Overview

Phase 9 (Internal Transceiver Support) introduces new dependencies for FPGA transceiver primitives that are not required in Phases 3-8 (external PHY).

---

## Critical Dependency: LiteICLink

### What is LiteICLink?

**LiteICLink** is a LiteX library providing high-level wrappers for FPGA transceiver primitives (GTX, GTY, GTH, GTP, SERDES).

- **Repository:** https://github.com/enjoy-digital/liteiclink
- **Purpose:** Abstraction layer for multi-gigabit transceivers
- **License:** BSD-2-Clause (compatible with LitePCIe)
- **Maintainer:** Enjoy-Digital (same as LiteX, LitePCIe)

### Why LiteICLink?

**Without LiteICLink:**
```python
# Direct Xilinx primitive instantiation (complex, error-prone)
Instance("GTXE2_CHANNEL",
    # 100+ parameters to configure manually
    p_SIM_RESET_SPEEDUP = "TRUE",
    p_SIM_TX_EEPM_EN = "TRUE",
    p_ALIGN_COMMA_DOUBLE = "FALSE",
    p_ALIGN_COMMA_ENABLE = 0b1111111111,
    # ... 90+ more parameters
    p_TXOUT_DIV = 2,
    p_RXOUT_DIV = 2,
    # ... complex connections
    i_GTXRXP = rx_pads.p,
    i_GTXRXN = rx_pads.n,
    # ... 50+ more connections
)
```

**With LiteICLink:**
```python
# Clean, high-level API
from liteiclink.transceiver.gtx_7series import GTX

gtx = GTX(
    pll        = pll,
    tx_pads    = tx_pads,
    rx_pads    = rx_pads,
    sys_clk_freq = 125e6,
    data_width = 20,  # 2 bytes (16-bit + 2-bit K-char)
    tx_buffer_enable = True,
    rx_buffer_enable = True,
    clock_aligner = False  # We handle in PIPE layer
)
```

### What LiteICLink Provides

| Module | Purpose | Used in Phase 9 |
|--------|---------|-----------------|
| `transceiver.gtx_7series` | Xilinx 7-Series GTX primitives | ✅ Task 9.3 |
| `transceiver.gtp_7series` | Xilinx 7-Series GTP primitives | ✅ Task 9.3 (Artix-7) |
| `transceiver.gth_ultrascale` | UltraScale GTH primitives | ✅ Task 9.4 |
| `transceiver.gty_ultrascale` | UltraScale+ GTY primitives | ✅ Task 9.4 |
| `serwb` | SerDes Wishbone Bridge | ❌ Not used |

### Installation

**Option 1: Using uv (Recommended)**
```bash
# Add to pyproject.toml
[project]
dependencies = [
    "litex",
    "liteiclink",  # <-- Add this
    ...
]

# Install
uv sync
```

**Option 2: Manual Installation**
```bash
cd /path/to/project
git clone https://github.com/enjoy-digital/liteiclink
cd liteiclink
pip install -e .
```

**Option 3: LiteX Install Script**
```bash
# If using litex_setup.py
./litex_setup.py --init --install --user
# Automatically installs liteiclink along with LiteX
```

### Version Requirements

| Dependency | Minimum Version | Recommended | Notes |
|------------|----------------|-------------|-------|
| liteiclink | 2023.04 | Latest (main) | GTX/GTY support stabilized |
| litex | 2023.04 | Latest (main) | Core framework |
| migen | Latest | Latest (main) | HDL framework |

---

## Dependency: LiteX 8b/10b Encoder/Decoder

### What It Provides

LiteX includes software 8b/10b encoding/decoding in `litex.soc.cores.code_8b10b`:

```python
from litex.soc.cores.code_8b10b import Encoder, Decoder

# 8b/10b Encoder
encoder = Encoder(nwords=1, d_last=0, k_last=0)
# Input: 8-bit data + K-char bit
# Output: 10-bit encoded data

# 8b/10b Decoder
decoder = Decoder(nwords=1)
# Input: 10-bit encoded data
# Output: 8-bit data + K-char bit + error flags
```

### When to Use Software vs Hardware 8b/10b

| FPGA | Hardware 8b/10b | Software 8b/10b | Phase 9 Strategy |
|------|-----------------|-----------------|------------------|
| **Xilinx 7-Series** | ✅ Built-in (GTX/GTP) | ✅ Available | **Use software** (consistent, proven by liteiclink) |
| **Xilinx UltraScale+** | ✅ Built-in (GTY/GTH) | ✅ Available | **Use software** (consistent, proven by liteiclink) |
| **Lattice ECP5** | ❌ Not available | ✅ Available | **Use software** (only option) |

**Decision (Clarifies Must Fix 3):**
- **ALL platforms:** Use software 8b/10b from `litex.soc.cores.code_8b10b`
- **Rationale:** liteiclink uses software 8b/10b even for Xilinx GTX/GTY at PCIe speeds (proven pattern)
- **Benefits:** Consistent behavior, single code path, simpler testing, no transceiver-specific quirks
- **See:** `docs/phase-9-8b10b-investigation.md` for detailed analysis

---

## Optional: ECP5 SERDES (for Lattice ECP5 support)

### ECP5-PCIe Integration

For Lattice ECP5 support (Task 9.5), we reference **ECP5-PCIe** codebase but don't add it as a dependency. Instead, we adapt patterns:

**What we take from ECP5-PCIe:**
- DCUA primitive configuration patterns
- Reset sequencing FSM design
- SCI (SerDes Client Interface) usage
- Clock domain crossing approach

**Why not a dependency:**
- ECP5-PCIe is Amaranth-based (we're Migen-based)
- We only need the patterns, not the code
- Direct DCUA instantiation is feasible

**Implementation:**
```python
# litepcie/phy/ecp5.py
# Based on ECP5-PCIe but rewritten in Migen
Instance("DCUA",
    # Configuration based on ECP5-PCIe ecp5_serdes.py
    p_D_MACROPDB = "0b1",
    p_D_TXPLL_PWDNB = "0b1",
    # ... 60+ parameters from reference
)
```

---

## Testing Dependencies

### Simulation

**No additional dependencies** - All simulation handled by existing tools:
- Migen simulation framework
- pytest for test orchestration
- cocotb (if needed for complex scenarios)

### Hardware Validation

**Platform-specific:**
- **Xilinx:** Vivado (for synthesis, not a Python dependency)
- **Lattice:** Yosys + nextpnr (open-source toolchain)

---

## Dependency Graph

```
LitePCIe (Phase 9)
├── LiteX (core framework)
│   ├── Migen (HDL)
│   └── litex.soc.cores.code_8b10b (software 8b/10b)
├── liteiclink (transceiver primitives)  ← NEW in Phase 9
│   ├── GTX/GTP wrappers (Xilinx 7-Series)
│   ├── GTH/GTY wrappers (UltraScale+)
│   └── Common transceiver abstractions
└── ECP5-PCIe patterns (reference only, not a dependency)
```

---

## Import Examples

### Phase 9 Task 9.3: Xilinx 7-Series GTX

```python
# litepcie/phy/xilinx_7series.py

from migen import *
from litex.gen import LiteXModule
from litex.soc.interconnect import stream
from litex.soc.cores.code_8b10b import Encoder, Decoder, K  # Software 8b/10b

# Critical dependency for PLL configuration:
from liteiclink.transceiver.gtx_7series import GTXChannelPLL

class Xilinx7SeriesGTXTransceiver(LiteXModule):
    def __init__(self, platform, pads, ...):
        # PLL for reference clock
        self.pll = GTXChannelPLL(
            refclk     = refclk,
            refclk_freq = 100e6,
            linerate   = 2.5e9  # Gen1: 2.5 GT/s
        )

        # Software 8b/10b encoder/decoder (like liteiclink GTX)
        self.encoder = ClockDomainsRenamer("tx")(
            Encoder(nwords=2, lsb_first=True)  # 2 bytes
        )
        self.decoder = ClockDomainsRenamer("rx")(
            Decoder(lsb_first=True)
        )

        # GTX primitive (direct instantiation, no hardware 8b/10b)
        self.specials += Instance("GTXE2_CHANNEL",
            # Omit p_TX_8B10B_ENABLE and p_RX_8B10B_ENABLE
            # (use software encoder/decoder above)

            # Connect to software encoder/decoder
            i_TXDATA = Cat(self.encoder.output[0], self.encoder.output[1]),
            o_RXDATA = self.decoder.input,
            ...
        )
```

### Phase 9 Task 9.5: Lattice ECP5

```python
# litepcie/phy/ecp5.py

from migen import *
from litex.gen import LiteXModule
from litex.soc.cores.code_8b10b import Encoder, Decoder  # Required (no hardware 8b/10b)

# No liteiclink import - direct DCUA primitive

class LatticeECP5Transceiver(LiteXModule):
    def __init__(self, platform, pads, ...):
        # Software 8b/10b encoder/decoder
        self.encoder = Encoder(nwords=1)
        self.decoder = Decoder(nwords=1)

        # Direct DCUA instantiation (based on ECP5-PCIe patterns)
        self.specials += Instance("DCUA",
            # 60+ parameters from ECP5-PCIe reference
            ...
        )
```

---

## Dependency Verification

### Pre-Flight Check Script

```python
#!/usr/bin/env python3
# scripts/check_phase9_deps.py

import sys

def check_dependency(module_name, import_path):
    try:
        __import__(import_path)
        print(f"✅ {module_name:20} - OK")
        return True
    except ImportError as e:
        print(f"❌ {module_name:20} - MISSING: {e}")
        return False

deps = [
    ("LiteX", "litex"),
    ("Migen", "migen"),
    ("LiteX 8b/10b", "litex.soc.cores.code_8b10b"),
    ("LiteICLink", "liteiclink"),
    ("LiteICLink GTX", "liteiclink.transceiver.gtx_7series"),
    ("LiteICLink GTY", "liteiclink.transceiver.gty_ultrascale"),
]

print("Phase 9 Dependency Check")
print("=" * 50)

all_ok = all(check_dependency(name, path) for name, path in deps)

if not all_ok:
    print("\n❌ Missing dependencies. Install with:")
    print("   uv sync  (if using pyproject.toml)")
    print("   OR")
    print("   pip install liteiclink")
    sys.exit(1)

print("\n✅ All Phase 9 dependencies present!")
```

**Usage:**
```bash
uv run python scripts/check_phase9_deps.py
```

---

## Migration Notes: Phase 8 → Phase 9

### Code Changes

**Phase 8 (External PHY):**
```python
# No liteiclink import needed
from litepcie.phy.pipe_external_phy import PIPEExternalPHY

phy = PIPEExternalPHY(...)  # Works without liteiclink
```

**Phase 9 (Internal Transceiver):**
```python
# liteiclink required
from litepcie.phy.xilinx_7series import Xilinx7SeriesGTXPHY

phy = Xilinx7SeriesGTXPHY(...)  # Needs liteiclink
```

### Backward Compatibility

✅ **Phase 8 code still works** - liteiclink is optional if only using external PHY
✅ **No breaking changes** - existing code doesn't need liteiclink import
✅ **Graceful degradation** - import errors only if trying to use internal transceivers

---

## Summary

| Dependency | Required | Phase | Purpose |
|------------|----------|-------|---------|
| **liteiclink** | **YES** | **Phase 9** | **GTX/GTY/GTH transceiver wrappers** |
| litex.soc.cores.code_8b10b | YES | Phase 9 | Software 8b/10b (ECP5, optional for Xilinx) |
| LiteX | YES | All | Core framework |
| Migen | YES | All | HDL generation |
| ECP5-PCIe | NO (reference only) | Phase 9 | Design patterns for ECP5 |

**Action Items:**
1. ✅ Add liteiclink to pyproject.toml dependencies
2. ✅ Document liteiclink usage in code
3. ✅ Create dependency check script
4. ✅ Update README with liteiclink installation

---

**Document Status:** APPROVED - Clarifies liteiclink dependency
**Next Document:** Must Fix 3 - 8b/10b Strategy Clarification
