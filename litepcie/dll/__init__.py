#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

"""
LitePCIe Data Link Layer Implementation.

This module implements the PCIe Data Link Layer as specified in
PCI Express Base Specification Rev. 4.0, Section 3.

The DLL provides reliable packet delivery through:
- DLLP (Data Link Layer Packet) processing
- Sequence number assignment
- LCRC generation and checking
- ACK/NAK protocol with retry buffer
- Flow control credit management

Target Users
------------
Developers who want:
- 100% open source PCIe implementation
- Full visibility and control over all layers
- Support for open source FPGA toolchains
- Advanced features (error injection, improved hot plug)

Primary Platform
----------------
Lattice ECP5 with Yosys+nextpnr (no vendor PCIe IP available)

Architecture
------------
TLP Layer ↔ DLL Layer ↔ PIPE Interface ↔ PHY ↔ Transceivers

This is an alternative pathway to vendor IP. Users can choose
vendor IP or this open-source stack transparently.

References
----------
- PCIe Base Spec 4.0, Section 3: https://pcisig.com/specifications
- "PCI Express System Architecture" by Budruk et al., Chapters 8-9
- Intel PIPE Specification white paper

Examples
--------
>>> # Option 1: Vendor IP
>>> from litepcie.phy.s7pciephy import S7PCIEPHY
>>> phy = S7PCIEPHY(platform, pads)
>>>
>>> # Option 2: Open source DLL+PIPE stack
>>> from litepcie.phy.pipe_phy import PIPEPCIePHY
>>> phy = PIPEPCIePHY(platform, pads, pipe_chip="TUSB1310A")
>>>
>>> # Rest of design is identical
>>> endpoint = LitePCIeEndpoint(phy, ...)
"""

__version__ = "0.1.0"
