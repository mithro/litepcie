#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
PIPE interface pad definitions for external PHY chips.

Defines standard PIPE 3.0 signals for connecting FPGA to external
PIPE PHY chips (e.g., TI TUSB1310A, PLX PEX8311, etc.).

Usage
-----
Add to your platform file:

```python
from litex.build.generic_platform import Pins, Subsignal, IOStandard

# Define PIPE IO pins for your board:
_io = [
    ("pcie_pipe", 0,
        # TX signals (FPGA → PHY)
        Subsignal("tx_data",     Pins("A1 A2 A3 A4 A5 A6 A7 A8")),
        Subsignal("tx_datak",    Pins("B1")),
        Subsignal("tx_elecidle", Pins("B2")),

        # RX signals (PHY → FPGA)
        Subsignal("rx_data",     Pins("C1 C2 C3 C4 C5 C6 C7 C8")),
        Subsignal("rx_datak",    Pins("D1")),
        Subsignal("rx_elecidle", Pins("D2")),
        Subsignal("rx_status",   Pins("E1 E2 E3")),
        Subsignal("rx_valid",    Pins("E4")),

        # Control signals (FPGA → PHY)
        Subsignal("powerdown",   Pins("F1 F2")),
        Subsignal("reset",       Pins("F3")),

        # Clock (PHY → FPGA)
        Subsignal("pclk",        Pins("G1")),
        IOStandard("LVCMOS33"),
    ),
]
```

Then request pads and create PHY:
```python
pcie_pads = platform.request("pcie_pipe")
phy = PIPEExternalPHY(platform, pcie_pads, data_width=64)
```

References
----------
- Intel PIPE 3.0 Specification
- TI TUSB1310A Datasheet
- PCIe Base Spec 4.0, Section 8: Electrical Specification
"""


def get_pipe_pads():
    """
    Get PIPE interface pad structure definition.

    Returns a dictionary of PIPE signal names and their widths.
    This is used for documentation and testing.

    Returns
    -------
    dict
        Dictionary mapping signal names to bit widths

    Notes
    -----
    PIPE 3.0 signals for single-lane (x1) configuration:

    **TX Path (FPGA → PHY):**
    - tx_data[7:0]: Transmit data byte
    - tx_datak: TX data is K-character (special symbol)
    - tx_elecidle: TX electrical idle request

    **RX Path (PHY → FPGA):**
    - rx_data[7:0]: Receive data byte
    - rx_datak: RX data is K-character
    - rx_elecidle: RX electrical idle status
    - rx_status[2:0]: RX status (disparity, symbol errors)
    - rx_valid: RX data valid

    **Control (FPGA → PHY):**
    - powerdown[1:0]: Power management (00=P0, 01=P0s, 10=P1, 11=P2)
    - reset: PHY reset (active high)

    **Clock (PHY → FPGA):**
    - pclk: PIPE clock output from PHY (125 MHz for Gen1, 250 MHz for Gen2)

    Examples
    --------
    >>> pads = get_pipe_pads()
    >>> pads["tx_data"]
    8
    >>> pads["rx_status"]
    3
    """
    return {
        # TX signals (FPGA → PHY)
        "tx_data": 8,      # TX data (8-bit)
        "tx_datak": 1,     # TX data is K-character
        "tx_elecidle": 1,  # TX electrical idle

        # RX signals (PHY → FPGA)
        "rx_data": 8,      # RX data (8-bit)
        "rx_datak": 1,     # RX data is K-character
        "rx_elecidle": 1,  # RX electrical idle
        "rx_status": 3,    # RX status (disparity, symbol errors)
        "rx_valid": 1,     # RX data valid

        # Control signals (FPGA → PHY)
        "powerdown": 2,    # Power down mode (2-bit)
        "reset": 1,        # PHY reset

        # Clock (PHY → FPGA)
        "pclk": 1,         # PIPE clock (125 MHz for Gen1)
    }


def get_pipe_io_template():
    """
    Get PIPE interface IO template for LiteX platforms.

    Returns a template string showing how to define PIPE IOs
    in a LiteX platform file.

    Returns
    -------
    str
        Template code for platform IO definition

    Examples
    --------
    >>> print(get_pipe_io_template())
    # PIPE interface for external PHY (e.g., TI TUSB1310A)
    ("pcie_pipe", 0,
        # TX signals (FPGA → PHY)
        ...
    """
    return '''# PIPE interface for external PHY (e.g., TI TUSB1310A)
("pcie_pipe", 0,
    # TX signals (FPGA → PHY)
    Subsignal("tx_data",     Pins("# TODO: 8 pins")),
    Subsignal("tx_datak",    Pins("# TODO: 1 pin")),
    Subsignal("tx_elecidle", Pins("# TODO: 1 pin")),

    # RX signals (PHY → FPGA)
    Subsignal("rx_data",     Pins("# TODO: 8 pins")),
    Subsignal("rx_datak",    Pins("# TODO: 1 pin")),
    Subsignal("rx_elecidle", Pins("# TODO: 1 pin")),
    Subsignal("rx_status",   Pins("# TODO: 3 pins")),
    Subsignal("rx_valid",    Pins("# TODO: 1 pin")),

    # Control signals (FPGA → PHY)
    Subsignal("powerdown",   Pins("# TODO: 2 pins")),
    Subsignal("reset",       Pins("# TODO: 1 pin")),

    # Clock (PHY → FPGA)
    Subsignal("pclk",        Pins("# TODO: 1 pin")),
    IOStandard("LVCMOS33"),  # Adjust for your board
),
'''
