"""Frame and registry checks. Run: python3 -m unittest test_cupcake.py"""

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

    def test_every_character_can_sleep(self):
        for character in cupcake.CHARACTERS:
            animations = {a["name"]: a for a in character["anims"]}
            self.assertIn("sleep", animations, character["id"])
            sleep = animations["sleep"]
            self.assertIn(sleep["asset"], animations, character["id"])
            self.assertNotEqual(sleep["asset"], "sleep", character["id"])
            frames = cupcake.generate_sleep_frames(character)
            self.assertEqual(len(frames), sleep["frames"], character["id"])
            for frame in frames:
                self.assertEqual(frame.get_width(), cupcake.SPRITE)
                self.assertEqual(frame.get_height(), cupcake.SPRITE)
                pixels = cupcake.rgba_pixels(frame)
                self.assertTrue(
                    any(pixels[index + 3] for index in range(0, len(pixels), 4)),
                    character["id"],
                )
            self.assertNotEqual(
                cupcake.rgba_pixels(frames[0]),
                cupcake.rgba_pixels(frames[1]),
                character["id"],
            )


if __name__ == "__main__":
    unittest.main()
