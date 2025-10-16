#
# This file is part of LitePCIe.
#
# Copyright (c) 2015-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

import unittest


class TestProjectStructure(unittest.TestCase):
    """Test that DLL module structure is set up correctly."""

    def test_dll_module_imports(self):
        """Verify DLL module can be imported."""
        try:
            from litepcie.dll import common, dllp
        except ImportError as e:
            self.fail(f"DLL module import failed: {e}")

    def test_dll_module_has_version(self):
        """Verify DLL module exposes version."""
        from litepcie.dll import __version__

        self.assertIsNotNone(__version__)

    def test_dll_common_constants_exist(self):
        """Verify DLL common constants are defined."""
        from litepcie.dll.common import (
            DLL_SEQUENCE_NUM_MAX,
            DLL_SEQUENCE_NUM_WIDTH,
            DLLP_TYPE_ACK,
            DLLP_TYPE_NAK,
        )

        # Basic sanity checks
        self.assertEqual(DLL_SEQUENCE_NUM_WIDTH, 12)
        self.assertEqual(DLL_SEQUENCE_NUM_MAX, 4095)
        self.assertIsInstance(DLLP_TYPE_ACK, int)
        self.assertIsInstance(DLLP_TYPE_NAK, int)


if __name__ == "__main__":
    unittest.main()
