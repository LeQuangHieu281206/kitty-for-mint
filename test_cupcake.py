"""Frame and registry checks. Run: python3 -m unittest linux/test_cupcake.py"""

import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "cupcake", Path(__file__).parent / "cupcake.py"
)
cupcake = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cupcake)


class CupcakeTest(unittest.TestCase):
    def test_every_frame_exists(self):
        for character in cupcake.CHARACTERS:
            for animation in character["anims"]:
                frames = cupcake.load_frames(character, animation)
                self.assertEqual(
                    len(frames),
                    animation["frames"],
                    f"{character['id']}/{animation['name']}",
                )

    def test_character_ids_are_unique(self):
        ids = [character["id"] for character in cupcake.CHARACTERS]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
