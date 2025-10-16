#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
External PIPE PHY Wrapper for PCIe.

This module provides a PHY wrapper for external PIPE PHY chips (e.g., devices
similar to TI TUSB1310A). The external chip handles:
- 8b/10b encoding/decoding
- Ordered set generation/detection
- Physical layer (SERDES, electrical signaling)

Our wrapper handles:
- DLL layer (ACK/NAK, retry buffer, sequence numbers, LCRC)
- PIPE interface abstraction
- Integration with LitePCIe TLP layer

This is a drop-in replacement for vendor IP PHYs (S7PCIEPHY, USPCIEPHY, etc.).

Usage
-----
```python
from litepcie.phy.pipe_external_phy import PIPEExternalPHY

phy = PIPEExternalPHY(
    platform    = platform,
    pads        = platform.request("pcie_x4"),
    data_width  = 128,
    cd          = "sys",
    bar0_size   = 0x100000,
)
endpoint = LitePCIeEndpoint(phy, ...)
```

References
----------
- docs/integration-strategy.md: Drop-in replacement strategy
- docs/pipe-interface-spec.md: PIPE signal definitions
- Intel PIPE 3.0 Specification
"""

from migen import *
from litex.gen import *

from litepcie.common import *
from litepcie.phy.common import PHYTXDatapath, PHYRXDatapath
from litepcie.dll.tx import DLLTX
from litepcie.dll.rx import DLLRX
from litepcie.dll.pipe import PIPEInterface

# External PIPE PHY Wrapper ------------------------------------------------------------------------

class PIPEExternalPHY(LiteXModule):
    """
    External PIPE PHY wrapper for PCIe.

    Drop-in replacement for vendor IP PHYs. Integrates DLL + PIPE interface
    with external PIPE PHY chip.

    Parameters
    ----------
    platform : Platform
        LiteX platform
    pads : Record
        PCIe pads (PIPE signals to external chip)
    data_width : int
        TLP datapath width (64, 128, 256, or 512 bits)
    cd : str
        Core clock domain name
    bar0_size : int
        BAR0 size in bytes

    Attributes
    ----------
    sink : Endpoint(phy_layout), input
        TX data from TLP layer
    source : Endpoint(phy_layout), output
        RX data to TLP layer
    msi : Endpoint(msi_layout), output
        MSI interrupt endpoint
    data_width : int
        Datapath width
    bar0_mask : int
        BAR0 address mask

    Notes
    -----
    The external PIPE chip must support PIPE 3.0 (or compatible) interface.
    Clock: PCLK from PHY chip drives "pcie" clock domain (125 MHz for Gen1).

    Examples
    --------
    >>> phy = PIPEExternalPHY(platform, pads, data_width=128)
    >>> endpoint = LitePCIeEndpoint(phy, address_width=32)

    References
    ----------
    - docs/integration-strategy.md: PHY interface contract
    - Intel PIPE 3.0 Specification
    """
    def __init__(self, platform, pads, data_width=64, cd="sys", bar0_size=0x10000):
        # Validate parameters
        if data_width not in [64, 128, 256, 512]:
            raise ValueError(f"Invalid data_width: {data_width}")

        # Required attributes for drop-in replacement
        self.data_width = data_width
        self.bar0_mask = get_bar_mask(bar0_size)

        # Required endpoints for drop-in replacement
        self.sink = stream.Endpoint(phy_layout(data_width))
        self.source = stream.Endpoint(phy_layout(data_width))
        self.msi = stream.Endpoint(msi_layout())

        # # #

        # Internal components:
        # - TX/RX datapaths (clock domain crossing + width conversion)
        # - DLL layer (ACK/NAK, retry buffer, sequence numbers, LCRC)
        # - PIPE interface (DLL ↔ PIPE signals)
        # - External PIPE chip connections

        # TX Datapath: TLP layer → DLL (with CDC and width conversion)
        self.tx_datapath = PHYTXDatapath(
            core_data_width=data_width,
            pcie_data_width=64,  # DLL operates at 64-bit internally
            clock_domain=cd,
        )
        self.comb += self.sink.connect(self.tx_datapath.sink)

        # RX Datapath: DLL → TLP layer (with CDC and width conversion)
        self.rx_datapath = PHYRXDatapath(
            core_data_width=data_width,
            pcie_data_width=64,  # DLL operates at 64-bit internally
            clock_domain=cd,
            with_aligner=False,  # No alignment needed (DLL handles this)
        )
        self.comb += self.rx_datapath.source.connect(self.source)

        # DLL Layer (in "pcie" clock domain)
        self.dll_tx = ClockDomainsRenamer("pcie")(DLLTX(data_width=64))
        self.dll_rx = ClockDomainsRenamer("pcie")(DLLRX(data_width=64))

        # Connect TX datapath to DLL
        # TODO: Implement proper connection (layout conversion needed)
        # self.comb += self.tx_datapath.source.connect(self.dll_tx.tlp_sink)

        # Connect DLL to RX datapath
        # TODO: Implement proper connection (layout conversion needed)
        # self.comb += self.dll_rx.tlp_source.connect(self.rx_datapath.sink)

        # PIPE Interface (in "pcie" clock domain)
        self.pipe = ClockDomainsRenamer("pcie")(PIPEInterface(data_width=8, gen=1))

        # Connect DLL to PIPE interface
        # TODO: Implement proper connection (currently placeholder)
        # self.comb += [
        #     self.dll_tx.pipe_source.connect(self.pipe.dll_tx_sink),
        #     self.pipe.dll_rx_source.connect(self.dll_rx.pipe_sink),
        # ]

        # Connect PIPE interface to external chip pads
        if pads is not None:
            # TODO: Connect PIPE signals to pads
            # self.comb += [
            #     pads.tx_data.eq(self.pipe.pipe_tx_data),
            #     pads.tx_datak.eq(self.pipe.pipe_tx_datak),
            #     self.pipe.pipe_rx_data.eq(pads.rx_data),
            #     self.pipe.pipe_rx_datak.eq(pads.rx_datak),
            #     # ... etc
            # ]
            pass

        # MSI handling (placeholder)
        # TODO: Implement MSI CDC from pcie → core clock domain
