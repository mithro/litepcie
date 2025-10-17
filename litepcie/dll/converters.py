#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
Layout converters for PHY, DLL, and PIPE interfaces.

Different layers use different record layouts:
- PHY layer (TLP): phy_layout with (dat, be) fields
- DLL layer: Simple layout with (data) field
- PIPE layer: phy_layout with (dat, be) for symbol data

These converters handle the translation between layouts.

References
----------
- litepcie/common.py: Layout definitions
"""

from migen import *
from litex.gen import LiteXModule
from litex.soc.interconnect import stream

from litepcie.common import phy_layout


class PHYToDLLConverter(LiteXModule):
    """
    Convert PHY layer layout (dat, be) to DLL layer layout (data).

    Parameters
    ----------
    data_width : int
        Data width in bits (64, 128, 256, or 512)

    Attributes
    ----------
    sink : Endpoint(phy_layout), input
        PHY layer data (dat, be fields)
    source : Endpoint([("data", data_width)]), output
        DLL layer data (data field only)

    Examples
    --------
    >>> conv = PHYToDLLConverter(data_width=64)
    >>> comb += phy_datapath.source.connect(conv.sink)
    >>> comb += conv.source.connect(dll.tlp_sink)
    """

    def __init__(self, data_width):
        # PHY layout input (dat, be)
        self.sink = stream.Endpoint(phy_layout(data_width))

        # DLL layout output (data only)
        self.source = stream.Endpoint([("data", data_width)])

        # # #

        # Convert PHY (dat, be) to DLL (data)
        # Extract data field, ignore be field (DLL doesn't use byte enables)
        self.comb += [
            self.source.valid.eq(self.sink.valid),
            self.source.data.eq(self.sink.dat),
            self.sink.ready.eq(self.source.ready),
        ]


class DLLToPHYConverter(LiteXModule):
    """
    Convert DLL layer layout (data) to PHY layer layout (dat, be).

    Parameters
    ----------
    data_width : int
        Data width in bits (64, 128, 256, or 512)

    Attributes
    ----------
    sink : Endpoint([("data", data_width)]), input
        DLL layer data (data field only)
    source : Endpoint(phy_layout), output
        PHY layer data (dat, be fields)

    Examples
    --------
    >>> conv = DLLToPHYConverter(data_width=64)
    >>> comb += dll.tlp_source.connect(conv.sink)
    >>> comb += conv.source.connect(phy_datapath.sink)
    """

    def __init__(self, data_width):
        # DLL layout input (data only)
        self.sink = stream.Endpoint([("data", data_width)])

        # PHY layout output (dat, be)
        self.source = stream.Endpoint(phy_layout(data_width))

        # # #

        # Convert DLL (data) to PHY (dat, be)
        # Set all byte enables to 1 (all bytes valid)
        byte_width = data_width // 8

        self.comb += [
            self.source.valid.eq(self.sink.valid),
            self.source.dat.eq(self.sink.data),
            self.source.be.eq((1 << byte_width) - 1),  # All bytes enabled
            self.sink.ready.eq(self.source.ready),
        ]
