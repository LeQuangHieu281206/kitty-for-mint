"""Frame and registry checks. Run: python3 -m unittest test_cupcake.py"""

import importlib.util
import tempfile
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

    def test_every_character_faces_a_known_way(self):
        for character in cupcake.CHARACTERS:
            self.assertIn(character["facing"], ("left", "right"), character["id"])

    def test_run_faces_movement_direction(self):
        marmalade = next(c for c in cupcake.CHARACTERS if c["id"] == "marmalade_cat")
        samurai = next(c for c in cupcake.CHARACTERS if c["id"] == "samurai")
        self.assertFalse(cupcake.needs_flip(marmalade, moving_left=True))
        self.assertTrue(cupcake.needs_flip(marmalade, moving_left=False))
        self.assertTrue(cupcake.needs_flip(samurai, moving_left=True))
        self.assertFalse(cupcake.needs_flip(samurai, moving_left=False))

    def test_load_states_accepts_old_and_new_layouts(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = cupcake.CONFIG
            try:
                cupcake.CONFIG = Path(tmp) / "state.json"
                cupcake.CONFIG.write_text('{"character": "hare"}')
                self.assertEqual(
                    [s["character"] for s in cupcake.load_states()], ["hare"]
                )
                cupcake.CONFIG.write_text(
                    '[{"character": "gecko"}, {"character": "cheetah"}]'
                )
                self.assertEqual(
                    [s["character"] for s in cupcake.load_states()],
                    ["gecko", "cheetah"],
                )
                cupcake.CONFIG.write_text("not json")
                self.assertEqual(cupcake.load_states(), [])
            finally:
                cupcake.CONFIG = original

    def test_every_character_can_sleep(self):
        for character in cupcake.CHARACTERS:
            animations = {a["name"]: a for a in character["anims"]}
            sleep = animations.get("sleep")
            if sleep is None:
                continue
            self.assertIn(sleep["asset"], animations, character["id"])
            self.assertNotEqual(sleep["asset"], "sleep", character["id"])
            if sleep.get("generated") == "sprite":
                frames = cupcake.generate_sleep_sprite_frames(
                    sleep["sprite"], sleep["frames"]
                )
                size = cupcake.SIZE
            elif sleep.get("generated"):
                frames = cupcake.generate_sleep_frames(character)
                size = cupcake.SPRITE
            else:
                frames = cupcake.load_frames(character, sleep)
                size = cupcake.SIZE
            self.assertEqual(len(frames), sleep["frames"], character["id"])
            for frame in frames:
                self.assertEqual(frame.get_width(), size)
                self.assertEqual(frame.get_height(), size)
                pixels = cupcake.rgba_pixels(frame)
                self.assertTrue(
                    any(pixels[index + 3] for index in range(0, len(pixels), 4)),
                    character["id"],
                )
            if len(frames) >= 3:
                self.assertNotEqual(
                    cupcake.rgba_pixels(frames[0]),
                    cupcake.rgba_pixels(frames[2]),
                    character["id"],
                )

    def test_bed_image_loads(self):
        image = cupcake.load_bed_image()
        self.assertIsNotNone(image)
        self.assertEqual(image.get_width(), cupcake.BED_W)
        self.assertEqual(image.get_height(), cupcake.BED_H)
        pixels = cupcake.rgba_pixels(image)
        self.assertTrue(
            any(pixels[index + 3] for index in range(0, len(pixels), 4))
        )


if __name__ == "__main__":
    unittest.main()
