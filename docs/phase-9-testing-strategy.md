# Phase 9 Testing Strategy - Tiered Validation

**Last Updated:** 2025-10-17
**Status:** Pre-Implementation Documentation
**Purpose:** Define progressive testing tiers for Phase 9 internal transceiver implementation

---

## Overview

Phase 9 introduces internal transceiver support (GTX/GTY/ECP5), which requires hardware-dependent validation. This document defines a **3-tier testing strategy** that progressively validates functionality from simulation through hardware deployment.

**Key Principle:** Each tier catches different classes of bugs with increasing hardware requirements.

---

## Testing Tier Definitions

### Tier 1: Simulation (No Hardware)

**Purpose:** Validate logic correctness in software simulation
**Environment:** Migen simulator + pytest
**Runtime:** Minutes (fast feedback)
**CI/CD Integration:** ✅ YES - runs on every commit
**Hardware Required:** ❌ NO

**What It Tests:**
- FSM state transitions (LTSSM, reset sequencing)
- 8b/10b encoder/decoder correctness
- Data path transformations (layout converters, AsyncFIFO CDC)
- Protocol compliance (Training Sequence generation, SKP insertion)
- Error detection/reporting logic

**What It Cannot Test:**
- Actual transceiver behavior (GTX/GTP timing)
- Clock domain crossing at real frequencies
- Electrical signal integrity
- PCIe interoperability

**Example Test:**
```python
# test/phy/test_xilinx_gtx_sim.py

import unittest
from migen import *
from litepcie.phy.xilinx_7series import Xilinx7SeriesGTXPHY

class TestGTXSimulation(unittest.TestCase):
    def test_ltssm_detect_state(self):
        """Test LTSSM enters Detect state after reset."""
        dut = Xilinx7SeriesGTXPHY(platform=None, sim=True)

        def testbench():
            # Release reset
            yield dut.reset.eq(0)
            yield

            # LTSSM should enter Detect
            for _ in range(10):
                state = yield dut.pipe.ltssm.current_state
                if state == 1:  # DETECT
                    return
                yield

            self.fail("LTSSM did not enter Detect state")

        run_simulation(dut, testbench(), vcd_name="ltssm_detect.vcd")

    def test_8b10b_encoding(self):
        """Test 8b/10b encoder produces valid disparity."""
        from litepcie.common.encoding import PCIeEncoder

        encoder = PCIeEncoder()

        def testbench():
            # Encode K28.5 comma (0xBC, k=1)
            yield encoder.sink.data.eq(0xBC)
            yield encoder.sink.ctrl.eq(1)
            yield encoder.sink.valid.eq(1)
            yield

            # Check 10-bit output is K28.5 positive disparity (0x17C)
            output = yield encoder.source.data
            self.assertIn(output, [0x17C, 0x283])  # Both disparities valid

            yield encoder.sink.valid.eq(0)
            yield

        run_simulation(encoder, testbench())
```

**Coverage Targets:**
- FSM coverage: 100% of states reached
- Branch coverage: >90% of conditional logic
- Protocol events: All TS1/TS2/SKP/FTS sequences validated

---

### Tier 2: Loopback (FPGA Required)

**Purpose:** Validate hardware transceiver operation in isolated loopback
**Environment:** Physical FPGA board + loopback configuration
**Runtime:** Minutes to hours (requires bitstream build)
**CI/CD Integration:** ⚠️ OPTIONAL - nightly builds on hardware server
**Hardware Required:** ✅ YES - FPGA board only (no PCIe host)

**What It Tests:**
- Transceiver primitive instantiation (GTX/GTY/DCUA)
- PLL lock and clock generation (TXOUTCLK, RXOUTCLK)
- Near-End/Far-End loopback data integrity
- Actual clock domain crossing at real frequencies
- Reset sequencing with real transceiver timing
- Electrical signaling at SERDES level

**What It Cannot Test:**
- PCIe root complex interaction
- Link training with real PCIe devices
- DMA transfers and TLP routing
- Multi-lane interoperability

**Loopback Modes:**

| Mode | Description | Data Path | Use Case |
|------|-------------|-----------|----------|
| **Near-End PCS Loopback** | Before 8b/10b | TX 8b/10b → RX 8b/10b (internal) | Test encoder/decoder |
| **Near-End PMA Loopback** | After 8b/10b | TX SERDES → RX SERDES (internal) | Test transceiver config |
| **Far-End Loopback** | External cable | TX pads → RX pads (SMA loopback) | Test electrical signaling |

**Example Test Script:**
```python
#!/usr/bin/env python3
# examples/test_gtx_loopback.py

from litex import *
from litepcie.phy.xilinx_7series import Xilinx7SeriesGTXPHY

class GTXLoopbackTest(SoCMini):
    def __init__(self, platform):
        SoCMini.__init__(self, platform, sys_clk_freq=125e6)

        # Instantiate PHY in near-end PMA loopback mode
        self.phy = Xilinx7SeriesGTXPHY(
            platform,
            pads=platform.request("pcie"),
            loopback_mode=2  # Near-End PMA
        )

        # PRBS31 generator for TX
        self.submodules.prbs_gen = PRBSGenerator(width=64)
        self.comb += self.prbs_gen.source.connect(self.phy.sink)

        # PRBS31 checker for RX
        self.submodules.prbs_chk = PRBSChecker(width=64)
        self.comb += self.phy.source.connect(self.prbs_chk.sink)

        # Error counter CSR
        self.add_csr("prbs_errors")

def main():
    platform = get_platform()
    soc = GTXLoopbackTest(platform)

    # Build and program FPGA
    builder = Builder(soc, output_dir="build/loopback_test")
    builder.build(run=True, program=True)

    # Run loopback test via CSR
    from litex import RemoteClient
    bus = RemoteClient()
    bus.open()

    # Reset error counter
    bus.regs.prbs_errors.write(0)

    # Wait 1 second
    time.sleep(1)

    # Read error count
    errors = bus.regs.prbs_errors.read()
    print(f"PRBS errors: {errors}")

    bus.close()

    # Pass if zero errors
    if errors == 0:
        print("✅ Loopback test PASSED")
        return 0
    else:
        print(f"❌ Loopback test FAILED ({errors} errors)")
        return 1

if __name__ == "__main__":
    sys.exit(main())
```

**Acceptance Criteria:**
- PLL locks within 10ms of reset release
- Near-End PMA loopback: Zero bit errors over 10^9 bits (PRBS31)
- Far-End loopback: <10^-12 BER with SMA cable loopback
- Clock domain CDC: No metastability errors over 1 hour stress test

---

### Tier 3: Real PCIe (Full System)

**Purpose:** Validate PCIe interoperability with real root complex
**Environment:** FPGA board installed in PCIe slot of host system
**Runtime:** Hours to days (full protocol validation)
**CI/CD Integration:** ❌ NO - manual hardware-in-the-loop testing
**Hardware Required:** ✅ YES - FPGA board + PCIe host system

**What It Tests:**
- PCIe link training with real root complex
- Link speed negotiation (Gen1 ↔ Gen2)
- DMA transfers (write/read)
- TLP routing and completion matching
- Interrupt delivery (MSI/MSI-X)
- Power management states (L0s, L1)
- Error recovery (receiver errors, link retraining)

**Test Scenarios:**

#### Scenario 1: Link Training

```bash
# Insert FPGA card into PCIe slot
sudo lspci -vvv -s 01:00.0 | grep "LnkSta:"
# Should show: Speed 2.5GT/s (Gen1), Width x1

# Expected output:
# LnkSta: Speed 2.5GT/s, Width x1
# TrErr- Train- SlotClk+ DLActive+ BWMgmt- ABWMgmt-
```

#### Scenario 2: DMA Transfers

```python
#!/usr/bin/env python3
# examples/test_dma_transfers.py

from litepcie.host import LitePCIeDriver

driver = LitePCIeDriver()
driver.open("/dev/litepcie0")

# Allocate DMA buffer
buf = driver.alloc_dma_buffer(size=4096)

# Write pattern
pattern = bytes([i % 256 for i in range(4096)])
buf[:] = pattern

# DMA write to FPGA
driver.dma_write(addr=0x0, data=buf)

# DMA read back
result = driver.dma_read(addr=0x0, size=4096)

# Verify
if result == pattern:
    print("✅ DMA test PASSED")
else:
    print(f"❌ DMA test FAILED (mismatch at byte {result.index(pattern[0])})")
```

#### Scenario 3: Link Speed Change

```python
# examples/test_link_speed_change.py

from litepcie.host import LitePCIeDriver
import subprocess

driver = LitePCIeDriver()
driver.open("/dev/litepcie0")

# Force Gen1
subprocess.run(["sudo", "setpci", "-s", "01:00.0", "0xA0.b=01"])
driver.link_retrain()
time.sleep(1)

# Check speed
speed = driver.get_link_speed()
assert speed == "2.5GT/s", f"Gen1 failed: {speed}"

# Force Gen2
subprocess.run(["sudo", "setpci", "-s", "01:00.0", "0xA0.b=02"])
driver.link_retrain()
time.sleep(1)

# Check speed
speed = driver.get_link_speed()
assert speed == "5.0GT/s", f"Gen2 failed: {speed}"

print("✅ Link speed change test PASSED")
```

**Acceptance Criteria:**
- Link trains to Gen1 (2.5 GT/s) within 500ms
- Gen2 (5.0 GT/s) training succeeds on capable platforms
- DMA transfers sustain >1 GB/s throughput
- Zero TLP completion timeouts over 24-hour stress test
- Survives 100 link retrain cycles without errors

---

## Testing Strategy by Phase 9 Task

| Task | Tier 1 (Sim) | Tier 2 (Loopback) | Tier 3 (PCIe) | Notes |
|------|--------------|-------------------|---------------|-------|
| **9.1: 8b/10b Encoder/Decoder** | ✅ Primary | ⚠️ Validate disparity | ❌ N/A | Pure logic - simulate extensively |
| **9.2: PIPE Transceiver Base** | ✅ FSM only | ❌ N/A | ❌ N/A | Abstract class - unit test interface |
| **9.3: Xilinx 7-Series GTX** | ✅ Instantiation | ✅ Primary | ✅ Final validation | Loopback critical for PLL/clocking |
| **9.4: Xilinx UltraScale+ GTY** | ✅ Instantiation | ✅ Primary | ✅ Final validation | Same as GTX |
| **9.5: Lattice ECP5 SERDES** | ✅ SCI interface | ✅ Primary | ⚠️ Limited platforms | Loopback sufficient for Phase 9 |
| **9.6: Multi-Platform PHY** | ✅ Selection logic | ❌ N/A | ❌ N/A | Factory pattern - unit test |
| **9.7: Platform Support** | ✅ Pad definitions | ❌ N/A | ✅ Per platform | Verify constraints load |
| **9.8: Integration Tests** | ✅ Mock tests | ✅ Loopback e2e | ✅ Primary | End-to-end validation |
| **9.9: Example Designs** | ❌ N/A | ⚠️ Loopback mode | ✅ Primary | User-facing examples |
| **9.10: Documentation** | ❌ N/A | ❌ N/A | ❌ N/A | Review only |

---

## CI/CD Integration

### GitHub Actions Workflow

```yaml
# .github/workflows/phase9_tests.yml

name: Phase 9 - Internal Transceiver Tests

on: [push, pull_request]

jobs:
  tier1-simulation:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Install dependencies
        run: |
          pip install -e .
          pip install pytest pytest-cov

      - name: Run Tier 1 simulation tests
        run: |
          pytest test/phy/test_xilinx_gtx_sim.py \
                 test/phy/test_ecp5_serdes_sim.py \
                 test/common/test_8b10b_encoder.py \
                 --cov=litepcie.phy \
                 --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3

  tier2-loopback:
    runs-on: [self-hosted, fpga-server]
    if: github.ref == 'refs/heads/master'  # Nightly only
    steps:
      - uses: actions/checkout@v3

      - name: Build loopback test
        run: |
          cd examples
          python3 test_gtx_loopback.py --build-only

      - name: Program FPGA
        run: |
          openocd -f board/arty-a7.cfg -c "program build/loopback_test.bit"

      - name: Run loopback test
        run: |
          python3 test_gtx_loopback.py --test-only
        timeout-minutes: 10
```

---

## Test Failure Triage

### Decision Tree

```
Test fails in Tier 1 (Simulation)?
├─ YES → Bug in logic/FSM
│         Fix in HDL, add regression test
│
└─ NO → Test passes Tier 1
         │
         Test fails in Tier 2 (Loopback)?
         ├─ YES → Bug in transceiver config or clocking
         │         Check: PLL settings, reset sequence, primitives
         │
         └─ NO → Test passes Tier 1 & 2
                  │
                  Test fails in Tier 3 (Real PCIe)?
                  └─ YES → Interoperability issue or protocol violation
                            Debug: LiteScope capture, PCIe analyzer, root complex logs
```

---

## Debugging Tools by Tier

### Tier 1 (Simulation)
- **Migen VCD output:** `run_simulation(dut, testbench(), vcd_name="test.vcd")`
- **GTKWave:** Waveform viewer for VCD files
- **pytest fixtures:** Reusable test components

### Tier 2 (Loopback)
- **LiteScope:** Capture PIPE signals at real clock speeds
  ```python
  analyzer_signals = [
      phy.tx_datapath.source.data,
      phy.rx_datapath.sink.data,
      phy.pll.lock,
  ]
  self.analyzer = LiteScopeAnalyzer(analyzer_signals, depth=4096)
  ```
- **UART console:** Print PLL lock status, error counters
- **Vivado ILA (if necessary):** For Xilinx-specific transceiver signals

### Tier 3 (Real PCIe)
- **dmesg:** Linux kernel PCIe logs
  ```bash
  sudo dmesg | grep -i pci
  ```
- **lspci:** PCIe device enumeration
  ```bash
  sudo lspci -vvv -s 01:00.0
  ```
- **PCIe analyzer:** Lecroy, Teledyne (hardware protocol analyzer)
- **LiteScope:** Trigger on link training failures

---

## Success Metrics

### Phase 9 Completion Criteria (All Tiers)

| Metric | Target | Tier |
|--------|--------|------|
| **Simulation test pass rate** | 100% | Tier 1 |
| **Code coverage (phy/)** | >85% | Tier 1 |
| **Loopback BER (PRBS31)** | <10^-12 | Tier 2 |
| **PLL lock time** | <10ms | Tier 2 |
| **Link training success rate** | >99% | Tier 3 |
| **DMA throughput (Gen1 x1)** | >200 MB/s | Tier 3 |
| **DMA throughput (Gen2 x1)** | >400 MB/s | Tier 3 |
| **24-hour stress test** | Zero errors | Tier 3 |

---

## Timeline and Milestones

| Milestone | Tasks | Tier | Duration |
|-----------|-------|------|----------|
| **M1: Core Logic Complete** | 9.1, 9.2 | Tier 1 | 2 days |
| **M2: Xilinx Simulation** | 9.3, 9.4 | Tier 1 | 2 days |
| **M3: Xilinx Loopback** | 9.3, 9.4 | Tier 2 | 3 days |
| **M4: ECP5 Simulation** | 9.5 | Tier 1 | 2 days |
| **M5: ECP5 Loopback** | 9.5 | Tier 2 | 2 days |
| **M6: Integration Tests** | 9.8 | Tier 1+2 | 2 days |
| **M7: Real PCIe Validation** | 9.3-9.5 | Tier 3 | 3 days |
| **M8: Examples & Docs** | 9.9, 9.10 | Tier 3 | 2 days |
| **Total** | | | **18 days** |

---

## Risk Mitigation

### High-Risk Areas

1. **Xilinx Transceiver Config**
   - **Risk:** 100+ parameters, easy to misconfigure
   - **Mitigation:** Copy proven usb3_pipe settings, validate in Tier 2 loopback
   - **Tier 2 gate:** PLL must lock before moving to Tier 3

2. **Clock Domain Crossing**
   - **Risk:** Metastability at high frequencies
   - **Mitigation:** Use AsyncFIFO pattern from usb3_pipe, stress test in Tier 2
   - **Tier 2 gate:** 1-hour loopback with no CDC errors

3. **ECP5 Reset Sequencing**
   - **Risk:** Complex 8-state FSM, timing-dependent
   - **Mitigation:** Port exact ECP5-PCIe FSM, validate in Tier 1 simulation
   - **Tier 1 gate:** FSM coverage 100%, all transitions verified

---

## Appendix: Test Execution Checklist

### Before Starting Phase 9 Implementation

- [ ] Read this testing strategy document
- [ ] Set up Tier 1 simulation environment (migen, pytest installed)
- [ ] Identify Tier 2 hardware platform (which FPGA board available?)
- [ ] Identify Tier 3 test system (which PCIe host machine?)

### After Each Task

- [ ] Write Tier 1 simulation tests first (TDD)
- [ ] Achieve >85% code coverage for new code
- [ ] Run `pytest test/phy/ -v` locally before committing
- [ ] If hardware-dependent, write Tier 2 loopback test (manual run)

### Before Claiming Task Complete

- [ ] All Tier 1 tests pass in CI
- [ ] If hardware task (9.3-9.5), Tier 2 loopback test passes
- [ ] If integration task (9.8-9.9), Tier 3 real PCIe test passes
- [ ] Code reviewed and approved

### Before Closing Phase 9

- [ ] All 10 tasks complete
- [ ] Tier 1: 100% test pass rate in CI
- [ ] Tier 2: Loopback tests pass on ≥2 platforms (Xilinx + ECP5)
- [ ] Tier 3: Real PCIe link training succeeds on ≥1 platform
- [ ] Documentation updated (phase-9-plan, testing-strategy, README)

---

**Document Status:** APPROVED - Addresses Phase 9 Plan Review "Must Fix 4"

**Key Takeaway:** Progressive validation (Sim → Loopback → Real PCIe) ensures bugs are caught early, reducing debug time and hardware dependency for core development.
