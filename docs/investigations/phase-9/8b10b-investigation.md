# 8b/10b Encoder/Decoder Investigation

**Date:** 2025-10-17
**Question:** Can we reuse 8b/10b encoder/decoder from liteiclink or liteeth?

---

## Summary

**YES! We should use `litex.soc.cores.code_8b10b`** which is:
- ✅ Already available in LiteX (no new dependency)
- ✅ Used by both liteiclink AND liteeth
- ✅ Explicitly supports PCIe (documented in source)
- ✅ Provides both low-level and stream interfaces

---

## What LiteX Provides

### Module: `litex.soc.cores.code_8b10b`

**Location:** Already in venv at:
```
.venv/lib/python3.13/site-packages/litex/soc/cores/code_8b10b.py
```

**Description from source:**
```python
"""
IBM's 8b/10b Encoding

This scheme is used by a large number of protocols including Display Port, PCI
Express, Gigabit Ethernet, SATA and USB 3.
"""
```

**Key Classes:**

#### 1. `Encoder(nwords=1, lsb_first=False)`
Low-level encoder for multiple words with disparity tracking.

```python
from litex.soc.cores.code_8b10b import Encoder

encoder = Encoder(nwords=2, lsb_first=True)

# Inputs:
encoder.d[0]  # 8-bit data word 0
encoder.k[0]  # K-character flag word 0
encoder.d[1]  # 8-bit data word 1
encoder.k[1]  # K-character flag word 1

# Outputs:
encoder.output[0]     # 10-bit encoded word 0
encoder.output[1]     # 10-bit encoded word 1
encoder.disparity[0]  # Disparity after word 0
encoder.disparity[1]  # Disparity after word 1
```

#### 2. `Decoder(lsb_first=False)`
Low-level decoder (single word at a time).

```python
from litex.soc.cores.code_8b10b import Decoder

decoder = Decoder(lsb_first=True)

# Input:
decoder.input  # 10-bit encoded data

# Outputs:
decoder.d       # 8-bit decoded data
decoder.k       # K-character flag
decoder.invalid # Invalid code detected
```

#### 3. `StreamEncoder(nwords=1)`
Stream-based encoder with LiteX stream interface.

```python
from litex.soc.cores.code_8b10b import StreamEncoder

encoder = StreamEncoder(nwords=2)

# Sink (input):
encoder.sink.d  # 16-bit data (2 words x 8 bits)
encoder.sink.k  # 2-bit K-flags (1 per word)
encoder.sink.valid
encoder.sink.ready

# Source (output):
encoder.source.data  # 20-bit encoded (2 words x 10 bits)
encoder.source.valid
encoder.source.ready
```

#### 4. `StreamDecoder(nwords=1)`
Stream-based decoder with LiteX stream interface.

```python
from litex.soc.cores.code_8b10b import StreamDecoder

decoder = StreamDecoder(nwords=2)

# Sink (input):
decoder.sink.data  # 20-bit encoded (2 words x 10 bits)
decoder.sink.valid
decoder.sink.ready

# Source (output):
decoder.source.d  # 16-bit decoded (2 words x 8 bits)
decoder.source.k  # 2-bit K-flags
decoder.source.valid
decoder.source.ready
```

#### 5. Helper Functions

```python
from litex.soc.cores.code_8b10b import K, D

# Create K-character codes
K28_5 = K(28, 5)  # 0xBC - Comma character

# Create D-character codes
D0_0 = D(0, 0)    # 0x00 - Data character
```

---

## How liteiclink Uses It

**File:** `liteiclink/liteiclink/serdes/gtx_7series.py`

```python
from litex.soc.cores.code_8b10b import Encoder, Decoder

class GTX(LiteXModule):
    def __init__(self, ...):
        self.nwords = nwords = data_width//10

        # SOFTWARE 8b/10b encoder/decoder
        self.encoder = ClockDomainsRenamer("tx")(Encoder(nwords, True))
        self.decoders = [ClockDomainsRenamer("rx")(Decoder(True))
                         for _ in range(nwords)]
```

**Key Finding:** liteiclink uses **software 8b/10b** even for Xilinx GTX!
- No `p_TX_8B10B_ENABLE` or `p_RX_8B10B_ENABLE` parameters found
- Creates explicit Encoder/Decoder instances
- Uses `lsb_first=True` for GTX

---

## How liteeth Uses It

**File:** `liteeth/liteeth/phy/pcs_1000basex.py`

```python
from litex.soc.cores.code_8b10b import K, D, Encoder, Decoder

class PCSTX(LiteXModule):
    def __init__(self, lsb_first=False):
        self.encoder = Encoder(lsb_first=lsb_first)

        # Connect to encoder
        self.comb += [
            self.encoder.d.eq(data),
            self.encoder.k.eq(is_k_char),
        ]
```

---

## Recommendation for LitePCIe Phase 9

### Option 1: Use Software 8b/10b for ALL platforms (like liteiclink)

**Pros:**
- ✅ Consistent behavior across Xilinx and ECP5
- ✅ Proven pattern from liteiclink
- ✅ Easier testing (deterministic behavior)
- ✅ No transceiver-specific quirks

**Cons:**
- ❌ Uses more FPGA resources
- ❌ May limit maximum speed (though liteiclink works at 2.5/5.0 GT/s)

**Implementation:**
```python
from litex.soc.cores.code_8b10b import Encoder, Decoder

class Xilinx7SeriesGTXTransceiver(LiteXModule):
    def __init__(self, ...):
        # Software 8b/10b
        self.encoder = Encoder(nwords=2, lsb_first=True)
        self.decoder = Decoder(lsb_first=True)

        # GTX primitive WITHOUT hardware 8b/10b
        # (omit p_TX_8B10B_ENABLE and p_RX_8B10B_ENABLE)
```

### Option 2: Use Hardware 8b/10b for Xilinx, Software for ECP5

**Pros:**
- ✅ More efficient on Xilinx (less resources)
- ✅ Potentially higher performance

**Cons:**
- ❌ Two different code paths to test
- ❌ Hardware 8b/10b may have platform-specific bugs
- ❌ More complex (need conditional logic)

**Implementation:**
```python
from litex.soc.cores.code_8b10b import Encoder, Decoder

class Xilinx7SeriesGTXTransceiver(LiteXModule):
    def __init__(self, use_hardware_8b10b=True, ...):
        if use_hardware_8b10b:
            # GTX primitive with p_TX_8B10B_ENABLE=True
            # No software encoder/decoder needed
            pass
        else:
            # Software 8b/10b like liteiclink
            self.encoder = Encoder(nwords=2, lsb_first=True)
            self.decoder = Decoder(lsb_first=True)
```

---

## Proposed Decision

**Follow liteiclink's pattern: Use software 8b/10b for ALL platforms**

**Rationale:**
1. liteiclink already validates this works at PCIe speeds (2.5/5.0 GT/s)
2. Consistent behavior simplifies testing (Tier 1-3)
3. ECP5 requires software anyway, so one code path
4. Can optimize to hardware later if needed (perf tuning phase)

**Update Phase 9 Plan:**
- Task 9.1: ~~Create PCIe-specific 8b/10b wrapper~~ → **Use LiteX 8b/10b directly**
- Task 9.3: Xilinx GTX → Use software 8b/10b (omit p_TX_8B10B_ENABLE)
- Task 9.4: Xilinx GTY → Use software 8b/10b (omit p_TX_8B10B_ENABLE)
- Task 9.5: ECP5 DCUA → Use software 8b/10b (already planned)

**Code snippet:**
```python
from litex.soc.cores.code_8b10b import Encoder, Decoder, K

class Xilinx7SeriesGTXPHY(LiteXModule):
    def __init__(self, platform, ...):
        # Use LiteX 8b/10b directly (like liteiclink)
        self.encoder = ClockDomainsRenamer("tx")(
            Encoder(nwords=2, lsb_first=True)
        )
        self.decoder = ClockDomainsRenamer("rx")(
            Decoder(lsb_first=True)
        )

        # GTX primitive without hardware 8b/10b
        self.specials += Instance("GTXE2_CHANNEL",
            # Omit p_TX_8B10B_ENABLE and p_RX_8B10B_ENABLE
            # (defaults to disabled)

            # Connect to software encoder/decoder
            i_TXDATA=Cat(self.encoder.output[0], self.encoder.output[1]),
            o_RXDATA=Cat(self.decoder.input),
            ...
        )
```

---

## Impact on Documentation

### Update Required:

1. **phase-9-dependencies.md**
   - ✅ Already documents `litex.soc.cores.code_8b10b`
   - ✅ Already says "software 8b/10b for ECP5"
   - ❌ Need to clarify: "software 8b/10b for ALL platforms (like liteiclink)"

2. **Phase 9 Plan** (already fixed in previous commit)
   - ✅ Removed contradictory encoder instantiation
   - ✅ Fixed data connections
   - ✅ Added comments about software vs hardware

3. **Task 9.1** - Simplify or remove
   - Instead of creating `PCIeEncoder/PCIeDecoder` wrappers
   - Just import and use `Encoder/Decoder` from LiteX directly

---

## Testing Implications

Since we're using LiteX's 8b/10b:
- ✅ **Already tested** by liteiclink and liteeth
- ✅ **Known to work** at PCIe speeds (2.5/5.0 GT/s)
- ✅ **Tier 1 tests** can reuse LiteX test patterns
- ✅ **Consistent** across all platforms

---

## Conclusion

**Yes, we should use LiteX's 8b/10b encoder/decoder:**
- `from litex.soc.cores.code_8b10b import Encoder, Decoder, K, D`
- Use software 8b/10b for ALL platforms (Xilinx + ECP5)
- Follow liteiclink's proven pattern
- Simplifies Phase 9 Task 9.1 significantly

**No new dependencies needed - it's already in LiteX core!**
