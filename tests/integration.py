# SPDX-License-Identifier: GPL-3.0-or-later
import importlib
import os
import sys
import unittest
from pathlib import Path

import bpy


class RegistrationTests(unittest.TestCase):
    def test_register_unregister_register(self):
        package = os.environ.get("TNTMESH_TEST_PACKAGE", "tntmesh")
        if package == "tntmesh":
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        addon = importlib.import_module(package)
        for _ in range(2):
            addon.register()
            try:
                self.assertTrue(hasattr(bpy.types, "TNTMESH_PT_main"))
            finally:
                addon.unregister()
            self.assertFalse(hasattr(bpy.types, "TNTMESH_PT_main"))


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
        raise RuntimeError("TNTMesh integration tests failed")
