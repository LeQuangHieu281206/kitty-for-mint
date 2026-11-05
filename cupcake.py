#!/usr/bin/env python3
"""Cupcake — animated pixel-art cats on your Linux desktop."""

import json
import math
import os
import random
import warnings
from pathlib import Path

# GTK3 cannot position windows or keep them above on Wayland. XWayland can.
# Set this before importing Gdk; no re-exec needed.
if (
    __name__ == "__main__"
    and os.environ.get("XDG_SESSION_TYPE") == "wayland"
    and not os.environ.get("GDK_BACKEND")
):
    os.environ["GDK_BACKEND"] = "x11"

import cairo
import gi

warnings.filterwarnings("ignore", category=DeprecationWarning)

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk

SIZE = 128  # window size; 32x32 frames are upscaled 4x, 128x128 frames draw 1:1
BED_W = 160  # bed art cropped and drawn at half size
BED_H = 95
BED_GAP = 4  # px between the bed window and the screen edge
BED_CAT = 66  # sleeping cat, scaled down to sit inside the cushion
BED_CAT_X = (BED_W - BED_CAT) // 2
BED_CAT_Y = 8
BED_SPRITE_W = 120  # hand-drawn sleep sprites are drawn at their native size
BED_SPRITE_Y = 15
SPRITE = 32
WALK_SPEED = 90  # pixels per second
WALK_TICK = 40  # milliseconds
SLEEP_WAKE = (30, 90)  # seconds
SLEEP_TICK = 150  # ms, redraws the floating Zzz while sleeping
LOVE_CLICKS = 3
LOVE_WINDOW = 1.1  # seconds between clicks that count as one cuddle
LOVE_TIME = 1.9
PIXEL_Z = ((1, 1, 1), (0, 0, 1), (0, 1, 0), (1, 0, 0), (1, 1, 1))
ZZZ_BIG = ((88, 34, 2), (98, 22, 2), (108, 4, 3))
ZZZ_BED = ((104, 20, 2), (114, 12, 2), (124, 2, 2))
PIXEL_HEART = (
    (0, 1, 1, 0, 1, 1, 0),
    (1, 1, 1, 1, 1, 1, 1),
    (1, 1, 1, 1, 1, 1, 1),
    (0, 1, 1, 1, 1, 1, 0),
    (0, 0, 1, 1, 1, 0, 0),
    (0, 0, 0, 1, 0, 0, 0),
)

HERE = Path(__file__).resolve().parent
ASSETS = Path(os.environ.get("CUPCAKE_ASSETS", HERE / "assets"))
if not ASSETS.is_dir():  # running from the repo without installing
    ASSETS = HERE.parent / "src" / "cupcake" / "Assets.xcassets"

ICON = HERE / "icon.png"
if not ICON.is_file():
    ICON = ASSETS / "AppIcon.appiconset" / "icon_256x256.png"

CONFIG = Path(GLib.get_user_config_dir()) / "cupcake" / "state.json"

def animal(ident, name, idle, run, jump=0, facing="right"):
    return (
        ident,
        name,
        [
            ("idle", "Rest", idle, 0.18),
            ("run", "Run", run, 0.09),
            ("jump", "Hop", jump or idle, 0.1),
        ],
        False,
        facing,
    )


SPECIALS = [
    (
        "marmalade_cat",
        "Marmalade",
        [
            ("idle", "Chill", 8, 0.15),
            ("walk", "Walk", 12, 0.12),
            ("run", "Run", 8, 0.1),
            ("jump", "Hop", 3, 0.12),
            ("attack", "Pounce", 8, 0.08),
        ],
        False,
        "left",
    ),
    (
        "samurai",
        "Samurai",
        [
            ("idle", "Rest", 10, 0.12),
            ("run", "Run", 16, 0.08),
            ("jump", "Slash", 7, 0.08),
        ],
        False,
    ),
    animal("penguin", "Penguin", 2, 2),
    animal("cheetah", "Cheetah", 5, 5),
    animal("vulture", "Vulture", 7, 5, 3),
    animal("prairie_dog", "Prairie Dog", 9, 6, 3),
    animal("hare", "Hare", 4, 4, facing="left"),
    animal("gecko", "Gecko", 4, 4, facing="left"),
    animal("tree_frog", "Tree Frog", 3, 3),
    animal("poison_frog", "Poison Frog", 7, 7, facing="left"),
]

# Hand-drawn sleep sprites (full-size, not 32x32 frames) and their frame count.
SLEEP_SPRITES = {
    "xmas_cat": ("sleep_xmas_cat", 8, 0.17),
    "noel_cat": ("sleep_noel_cat", 8, 0.2),
}
SLEEP_BOB = (0, 0, 1, 1, 0, -1, -1, 0)
SLEEP_SPRITE_PAD = 8


def character(ident, name, animations, sleep=True, facing="right"):
    anims = []
    for a in animations:
        anim = {"name": a[0], "label": a[1], "frames": a[2], "rate": a[3]}
        if len(a) > 4:
            anim["asset"] = a[4]  # reuse another animation's frames
        anims.append(anim)
    # A character may ship its own sleep pose or have none at all.
    if not sleep or any(a["name"] == "sleep" for a in anims):
        return {
            "id": ident,
            "name": name,
            "anims": anims,
            "facing": facing,
        }
    # There are no sleep sprites in the original assets. Synthesise a lying
    # pose from the cat's own head/body and draw the Zzz in on_draw.
    source = next((a for a in anims if a["name"] == "idle"), anims[0])
    sprite = SLEEP_SPRITES.get(ident)
    if sprite is not None:
        anims.append(
            {
                "name": "sleep",
                "label": "Sleep",
                "frames": sprite[1],
                "rate": sprite[2],
                "asset": source["name"],
                "generated": "sprite",
                "sprite": sprite[0],
            }
        )
    else:
        anims.append(
            {
                "name": "sleep",
                "label": "Sleep",
                "frames": 4,
                "rate": 0.75,
                "asset": source["name"],
                "generated": "sleep",
            }
        )
    return {
        "id": ident,
        "name": name,
        "anims": anims,
        "facing": facing,
    }


CHARACTERS = [character(*spec) for spec in SPECIALS]
PETS = []
QUITTING = False


def load_states():
    """Read every saved pet, accepting the old single-pet dict."""
    try:
        data = json.loads(CONFIG.read_text())
    except (OSError, ValueError):
        return []
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return [state for state in data if isinstance(state, dict)]
    return []


def save_all():
    states = [pet.state() for pet in PETS]
    try:
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text(json.dumps(states))
    except OSError as error:
        print(f"Warning: cannot save state: {error}")

# Set to a character id to offer only that one; None lists every character.
ONLY_CHARACTER = None
if ONLY_CHARACTER:
    CHARACTERS = [c for c in CHARACTERS if c["id"] == ONLY_CHARACTER]


def find_animation(character, name):
    return next((a for a in character["anims"] if a["name"] == name), None)


def needs_flip(character, moving_left):
    """Sprites are drawn facing right unless the model declares left."""
    return moving_left != (character["facing"] == "left")


def transparent(window):
    window.set_decorated(False)
    window.set_resizable(False)
    window.set_keep_above(True)
    window.set_skip_taskbar_hint(True)
    window.set_skip_pager_hint(True)
    window.set_accept_focus(False)
    window.set_app_paintable(True)
    window.set_type_hint(Gdk.WindowTypeHint.UTILITY)
    window.stick()  # follow the user across every workspace
    visual = window.get_screen().get_rgba_visual()
    if visual is not None:
        window.set_visual(visual)


def set_hand_cursor(widget, name):
    """Use the theme's hand cursors, falling back to a plain pointing hand."""
    window = widget.get_window()
    if window is None:
        return
    try:
        cursor = Gdk.Cursor.new_from_name(widget.get_display(), name)
    except (TypeError, GLib.Error):
        cursor = Gdk.Cursor.new_for_display(
            widget.get_display(), Gdk.CursorType.HAND1
        )
    window.set_cursor(cursor)


def asset(name):
    """Find a frame in the installed flat folder or the Xcode asset catalog."""
    for path in (ASSETS / f"{name}.png", ASSETS / f"{name}.imageset" / f"{name}.png"):
        if path.is_file():
            return path
    return None


def load_frames(character, animation):
    frames = []
    source = animation.get("asset", animation["name"])
    for index in range(animation["frames"]):
        path = asset(f"{index:02d}_{character['id']}_{source}")
        if path is None:
            print(f"Warning: missing frame {index} for {character['id']}/{source}")
            continue
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(path))
        except GLib.Error as error:
            print(f"Warning: cannot load {path}: {error.message}")
            continue
        frames.append(pixbuf.scale_simple(SIZE, SIZE, GdkPixbuf.InterpType.NEAREST))
    return frames


def rgba_pixels(pixbuf):
    """Copy a pixbuf into a plain RGBA bytearray."""
    width, height = pixbuf.get_width(), pixbuf.get_height()
    stride = pixbuf.get_rowstride()
    channels = pixbuf.get_n_channels()
    source = pixbuf.get_pixels()
    out = bytearray(width * height * 4)
    for y in range(height):
        row = y * stride
        for x in range(width):
            source_index = row + x * channels
            target_index = (y * width + x) * 4
            out[target_index : target_index + 3] = source[
                source_index : source_index + 3
            ]
            out[target_index + 3] = (
                source[source_index + 3] if pixbuf.get_has_alpha() else 255
            )
    return out


def close_eyes(pixels):
    """Turn open eyes into two short closed eyelids on the sprite."""
    def pixel(x, y):
        index = (y * SPRITE + x) * 4
        return pixels[index : index + 4]

    def put(x, y, color):
        index = (y * SPRITE + x) * 4
        pixels[index : index + 4] = color

    for eye_x in (20, 25):
        cheek = pixel(eye_x, 16)
        if cheek[3] == 0:
            continue
        light = sum(cheek[:3]) < 220
        line = (220, 205, 170, 255) if light else (46, 43, 39, 255)
        for y in (14, 15):
            for x in (eye_x, eye_x + 1):
                put(x, y, cheek)
        put(eye_x, 15, line)
        put(eye_x + 1, 15, line)


def pixel_at(pixels, x, y):
    index = (y * SPRITE + x) * 4
    return tuple(pixels[index : index + 4])


def put_pixel(pixels, x, y, color):
    if 0 <= x < SPRITE and 0 <= y < SPRITE:
        index = (y * SPRITE + x) * 4
        pixels[index : index + 4] = bytes(color)


def body_palette(pixels):
    """Most common body colour plus a light paw and the sprite's outline."""
    counts = {}
    darkest = None
    for y in range(18, 30):
        for x in range(8, 28):
            color = pixel_at(pixels, x, y)
            if color[3] < 200:
                continue
            if darkest is None or sum(color[:3]) < sum(darkest[:3]):
                darkest = color
            if 19 <= y < 28:
                counts[color[:3]] = counts.get(color[:3], 0) + 1
    body = max(counts, key=counts.get) if counts else darkest[:3]
    body = (body[0], body[1], body[2], 255)
    light = tuple(
        min(255, round(channel * 1.3 + 18)) for channel in body[:3]
    ) + (255,)
    outline = darkest if darkest is not None else body
    return body, light, outline


def pixels_to_pixbuf(pixels):
    return GdkPixbuf.Pixbuf.new_from_bytes(
        GLib.Bytes.new(bytes(pixels)),
        GdkPixbuf.Colorspace.RGB,
        True,
        8,
        SPRITE,
        SPRITE,
        SPRITE * 4,
    )


def generate_sleep_frames(character):
    """Combine the cat's head and a flattened body into a curled-up nap."""
    sleep = find_animation(character, "sleep")
    path = asset(f"00_{character['id']}_{sleep['asset']}")
    if path is None:
        return []
    try:
        source = GdkPixbuf.Pixbuf.new_from_file(str(path))
    except GLib.Error as error:
        print(f"Warning: cannot load {path}: {error.message}")
        return []
    # Sleep poses are built on a SPRITE grid, so downscale hi-res frames first.
    source = source.scale_simple(SPRITE, SPRITE, GdkPixbuf.InterpType.BILINEAR)
    base = rgba_pixels(source)
    close_eyes(base)
    body, light, outline = body_palette(base)

    frames = []
    for index in range(sleep["frames"]):
        canvas = bytearray(SPRITE * SPRITE * 4)
        head_drop = (0, 1, 0, 1)[index % 4]
        body_rows = 10 if index % 4 == 2 else 9
        tail_flick = index % 4 == 3

        # Curled tail resting in front of the loaf.
        tail = ((6, 29), (5, 28), (4, 27), (4, 26), (4, 25), (5, 24), (6, 23), (7, 23))
        for step, (tx, ty) in enumerate(tail):
            if tail_flick and step >= 6:
                ty -= 1
            put_pixel(canvas, tx, ty, outline)
            if step >= 2:
                put_pixel(canvas, tx + 1, ty, body)

        # Flatten the body into a low loaf, anchored at the floor.
        for dy in range(body_rows):
            sy = 18 + dy * 12 // body_rows
            for dx in range(24):
                sx = 8 + dx * 19 // 24
                color = pixel_at(base, sx, sy)
                if color[3]:
                    put_pixel(canvas, 4 + dx, 20 + dy, color)

        # One front paw peeking out of the loaf.
        for x in range(9, 13):
            put_pixel(canvas, x, 28, outline if x in (9, 12) else light)

        # Head naps on top of the body, with a one-pixel breathing dip.
        for hy in range(12):
            for hx in range(17):
                color = pixel_at(base, 13 + hx, 8 + hy)
                if color[3]:
                    put_pixel(canvas, 13 + hx, 8 + head_drop + hy, color)
        frames.append(pixels_to_pixbuf(canvas))
    return frames


def load_sleep_sprite(name):
    path = asset(name)
    if path is None:
        return None
    try:
        return GdkPixbuf.Pixbuf.new_from_file(str(path))
    except GLib.Error as error:
        print(f"Warning: cannot load {path}: {error.message}")
        return None


def sleep_sprite_origin(sprite):
    return (
        (SIZE - sprite.get_width()) // 2,
        SIZE - sprite.get_height() - SLEEP_SPRITE_PAD,
    )


def generate_sleep_sprite_frames(name, count):
    """Breathe a full-size sleep sprite on a transparent 128x128 canvas."""
    sprite = load_sleep_sprite(name)
    if sprite is None:
        return []
    x, y = sleep_sprite_origin(sprite)
    frames = []
    for index in range(count):
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, SIZE, SIZE)
        cr = cairo.Context(surface)
        Gdk.cairo_set_source_pixbuf(
            cr, sprite, x, y + SLEEP_BOB[index % len(SLEEP_BOB)]
        )
        cr.paint()
        frames.append(Gdk.pixbuf_get_from_surface(surface, 0, 0, SIZE, SIZE))
    return frames


def load_bed_image():
    """Crop the bed's transparent margin and scale it to the window size."""
    path = asset("bed")
    if path is None:
        return None
    try:
        source = GdkPixbuf.Pixbuf.new_from_file(str(path))
    except GLib.Error as error:
        print(f"Warning: cannot load {path}: {error.message}")
        return None
    pixels = rgba_pixels(source)
    width, height = source.get_width(), source.get_height()
    left, top, right, bottom = width, height, -1, -1
    for y in range(height):
        for x in range(width):
            if pixels[(y * width + x) * 4 + 3]:
                left = min(left, x)
                right = max(right, x)
                top = min(top, y)
                bottom = max(bottom, y)
    if right < left:
        return None
    art = GdkPixbuf.Pixbuf.new_subpixbuf(
        source, left, top, right - left + 1, bottom - top + 1
    )
    return art.scale_simple(BED_W, BED_H, GdkPixbuf.InterpType.BILINEAR)


class Bed(Gtk.Window):
    """A dock-sized pet bed. The cat is drawn inside it while sleeping there."""

    def __init__(self, app):
        Gtk.Window.__init__(self, title="Cupcake Bed")
        transparent(self)
        self.app = app
        self.set_default_size(BED_W, BED_H)
        self.set_size_request(BED_W, BED_H)
        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.BUTTON1_MOTION_MASK
        )
        self.connect("draw", self.on_draw)
        self.connect("realize", self.on_realize)
        self.connect("button-press-event", self.on_press)
        self.connect("button-release-event", self.on_release)
        self.connect("motion-notify-event", self.on_motion)
        self.drag = None
        self.moved = False
        self.cat_frame = None
        self.cat_key = None
        self.sleep_sprite = None
        self.sprite_name = None
        self.image = load_bed_image()

    def on_realize(self, _widget):
        set_hand_cursor(self, "grab")

    def place(self):
        x, y = self.app.bed_xy()
        self.app.bed_x, self.app.bed_y = x, y
        self.move(x, y)

    def sleeping(self):
        return self.app.mode == "sleep" and self.app.on_bed

    def scaled_cat(self):
        if self.app.sleep_animation is None:
            return None
        frames = self.app.frames_for(self.app.sleep_animation)
        if not frames:
            return None
        frame = frames[self.app.frame_index % len(frames)]
        key = (id(frame), BED_CAT)
        if key != self.cat_key:
            self.cat_frame = frame.scale_simple(
                BED_CAT, BED_CAT, GdkPixbuf.InterpType.NEAREST
            )
            self.cat_key = key
        return self.cat_frame

    def sprite_sleep(self):
        sleep = self.app.sleep_animation
        if sleep is None:
            return None
        name = sleep.get("sprite")
        if name != self.sprite_name:
            self.sprite_name = name
            self.sleep_sprite = None
            sprite = load_sleep_sprite(name) if name else None
            if sprite is not None:
                height = round(
                    sprite.get_height() * BED_SPRITE_W / sprite.get_width()
                )
                self.sleep_sprite = sprite.scale_simple(
                    BED_SPRITE_W, height, GdkPixbuf.InterpType.BILINEAR
                )
        return self.sleep_sprite

    def on_draw(self, _widget, cr):
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        if self.image is not None:
            Gdk.cairo_set_source_pixbuf(cr, self.image, 0, 0)
            cr.paint()
        if self.sleeping():
            sprite = self.sprite_sleep()
            if sprite is not None:
                x = (BED_W - sprite.get_width()) // 2
                y = BED_SPRITE_Y + SLEEP_BOB[
                    self.app.frame_index % len(SLEEP_BOB)
                ]
                Gdk.cairo_set_source_pixbuf(cr, sprite, x, y)
                cr.paint()
            else:
                frame = self.scaled_cat()
                if frame is not None:
                    Gdk.cairo_set_source_pixbuf(cr, frame, BED_CAT_X, BED_CAT_Y)
                    cr.paint()
            lift = math.sin(GLib.get_monotonic_time() / 1_000_000 * 2) * 1.5
            self.app.draw_zzz(cr, ZZZ_BED, lift)
        return False

    def on_press(self, _widget, event):
        if event.button == 3:
            self.app.cancel_roam()
            if self.app.mode in ("walk", "play"):
                self.app.play_idle()
            self.app.build_menu().popup_at_pointer(event)
        elif event.button == 1:
            self.app.cancel_roam()
            win_x, win_y = self.app.bed_xy()
            self.drag = (event.x_root, event.y_root, win_x, win_y)
            self.moved = False
            set_hand_cursor(self, "grabbing")
        self.app.raise_cat()
        return True

    def on_motion(self, _widget, event):
        if self.drag is not None:
            x0, y0, win_x, win_y = self.drag
            dx = event.x_root - x0
            dy = event.y_root - y0
            if abs(dx) > 2 or abs(dy) > 2:
                self.moved = True
            area = self.app.workarea()
            x = int(min(max(win_x + dx, area.x), area.x + area.width - BED_W))
            y = int(min(max(win_y + dy, area.y), area.y + area.height - BED_H))
            self.move(x, y)
            self.app.bed_x = x
            self.app.bed_y = y
            self.queue_draw()
            self.app.raise_cat()
        return True

    def on_release(self, _widget, event):
        if event.button == 1 and self.drag is not None:
            moved = self.moved
            self.drag = None
            set_hand_cursor(self, "grab")
            if moved:
                self.app.save()
                self.app.schedule_roam(3)
            else:
                self.app.toggle_bed()
        return True


class Cupcake(Gtk.Window):
    def __init__(self, state=None):
        Gtk.Window.__init__(self, title="Cupcake")
        transparent(self)
        if ICON.is_file():
            self.set_icon_from_file(str(ICON))

        self.set_default_size(SIZE, SIZE)
        self.set_size_request(SIZE, SIZE)
        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.BUTTON1_MOTION_MASK
        )
        self.connect("draw", self.on_draw)
        self.connect("realize", self.on_realize)
        self.connect("button-press-event", self.on_press)
        self.connect("button-release-event", self.on_release)
        self.connect("motion-notify-event", self.on_motion)
        self.connect("destroy", self.on_destroy)

        self.frames = []
        self.frame_index = 0
        self.frame_end = None
        self.timer = None
        self.frame_cache = {}
        self.drag = None
        self.press = None
        self.moved = False
        self.pos = None
        self.character = CHARACTERS[0]
        self.rest_animation = self.character["anims"][0]
        self.sleep_animation = find_animation(self.character, "sleep")
        self.animation = self.rest_animation
        self.mode = "idle"  # idle | walk | play | sleep
        self.on_bed = False
        self.walk_timer = None
        self.walk_target = None
        self.walk_then = None
        self.roam_timer = None
        self.sleep_timer = None
        self.sleep_tick_timer = None
        self.roam_enabled = True
        self.bed_x = None
        self.bed_y = None
        self.bed_shown = True
        self.bed = None
        self.bed_version = 3
        self.click_times = []
        self.love_until = 0
        self.love_timer = None
        self.dragging = False
        self.drag_tilt = 0
        self.drag_strength = 0
        self.drag_dir = 1
        self.drag_timer = None
        self.drag_last = 0

        self.restore(state)
        if self.sleep_animation is None:
            self.bed_shown = False
        self.play_idle()
        self.show_all()
        self.place()

        self.bed = Bed(self)
        if self.bed_shown:
            self.bed.place()
            self.bed.show_all()
        else:
            self.bed.hide()
        self.raise_cat()
        GLib.idle_add(self.raise_cat)

        # GNOME never displays legacy XEmbed tray icons, so skip the wasted icon.
        if "GNOME" not in os.environ.get("XDG_CURRENT_DESKTOP", "").upper():
            self.setup_tray()
        self.schedule_roam()
        PETS.append(self)

    # MARK: - Animation

    def on_realize(self, _widget):
        set_hand_cursor(self, "grab")

    def frames_for(self, animation):
        generated = animation.get("generated")
        if generated == "sprite":
            key = (generated, self.character["id"])
            if key not in self.frame_cache:
                self.frame_cache[key] = generate_sleep_sprite_frames(
                    animation["sprite"], animation["frames"]
                )
            return self.frame_cache[key]
        if generated:
            key = (generated, self.character["id"])
            if key not in self.frame_cache:
                self.frame_cache[key] = [
                    frame.scale_simple(SIZE, SIZE, GdkPixbuf.InterpType.NEAREST)
                    for frame in generate_sleep_frames(self.character)
                ]
            return self.frame_cache[key]
        source = animation.get("asset", animation["name"])
        key = (source, animation["frames"])
        if key not in self.frame_cache:
            self.frame_cache[key] = load_frames(self.character, animation)
        return self.frame_cache[key]

    def flipped_frames(self, animation):
        source = animation.get("asset", animation["name"])
        key = (source, animation["frames"], "left")
        if key not in self.frame_cache:
            self.frame_cache[key] = [
                frame.flip(True) for frame in self.frames_for(animation)
            ]
        return self.frame_cache[key]

    def stop_timer(self):
        if self.timer is not None:
            GLib.source_remove(self.timer)
            self.timer = None
        self.frame_end = None

    def loop(self, frames, rate, tick_single=False):
        self.stop_timer()
        self.frames = frames
        self.frame_index = 0
        self.queue_draw()
        if len(frames) > 1:
            self.timer = GLib.timeout_add(max(16, int(rate * 1000)), self.next_frame)
        elif frames and tick_single:
            # One-frame sleep still needs redraws for the floating Zzz.
            self.timer = GLib.timeout_add(150, self.next_frame)

    def once(self, frames, rate, callback):
        self.stop_timer()
        self.frames = frames
        self.frame_index = 0
        self.queue_draw()
        if not frames:
            callback()
            return
        self.frame_end = callback
        if len(frames) > 1:
            self.timer = GLib.timeout_add(max(16, int(rate * 1000)), self.next_frame)
        else:
            self.timer = GLib.timeout_add(max(220, int(rate * 1000)), self.finish_once)

    def next_frame(self):
        if not self.frames:
            self.timer = None
            return False
        if len(self.frames) > 1:
            self.frame_index += 1
            if self.frame_index >= len(self.frames):
                if self.frame_end is not None:
                    callback = self.frame_end
                    self.frame_end = None
                    self.timer = None
                    callback()
                    return False
                self.frame_index = 0
        self.queue_draw()
        return True

    def finish_once(self):
        self.timer = None
        callback = self.frame_end
        self.frame_end = None
        if callback is not None:
            callback()
        return False

    def on_draw(self, _widget, cr):
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        if not self.frames or (self.mode == "sleep" and self.on_bed):
            return False
        now = GLib.get_monotonic_time() / 1_000_000
        loving = self.love_until > now and self.mode != "sleep"
        frame = self.frames[self.frame_index % len(self.frames)]
        if self.dragging:
            drag = find_animation(self.character, "drag")
            drag_frames = self.frames_for(drag) if drag is not None else []
            if drag_frames:
                frame = drag_frames[int(now / drag["rate"]) % len(drag_frames)]
        cr.save()
        if self.dragging:
            self.draw_drag_effect(cr, now)
            if abs(self.drag_tilt) > 0.1:
                cr.translate(SIZE / 2, SIZE * 0.75)
                cr.rotate(math.radians(self.drag_tilt))
                cr.translate(-SIZE / 2, -SIZE * 0.75)
        elif loving and self.mode != "play":
            sway = math.sin(now * 16) * 0.035
            cr.translate(SIZE / 2, SIZE)
            cr.rotate(sway)
            cr.translate(-SIZE / 2, -SIZE)
        Gdk.cairo_set_source_pixbuf(cr, frame, 0, 0)
        cr.paint()
        cr.restore()
        if self.mode == "sleep":
            self.draw_zzz(cr, ZZZ_BIG, math.sin(now * 2) * 1.5)
        if loving:
            self.draw_hearts(cr, now)
        return False

    def draw_zzz(self, cr, glyphs, lift=0):
        for offset, color in ((1, (0.08, 0.08, 0.12, 0.5)), (0, (1, 1, 1, 0.96))):
            cr.new_path()
            for x, y, size in glyphs:
                for row, bits in enumerate(PIXEL_Z):
                    for column, pixel in enumerate(bits):
                        if pixel:
                            cr.rectangle(
                                x + column * size + offset,
                                y + row * size + offset - lift,
                                size,
                                size,
                            )
            cr.set_source_rgba(*color)
            cr.fill()

    def draw_hearts(self, cr, now):
        elapsed = LOVE_TIME - max(0.0, self.love_until - now)
        for index in range(6):
            t = (elapsed * 0.75 + index * 0.21) % 1.5
            alpha = max(0.0, 1.0 - t / 1.35)
            if alpha <= 0:
                continue
            x = 64 + math.sin(elapsed * 2.6 + index * 1.7) * 24 + (index - 2.5) * 4
            y = 78 - t * 50
            cr.set_source_rgba(0.35, 0.08, 0.15, alpha * 0.5)
            for row, bits in enumerate(PIXEL_HEART):
                for column, pixel in enumerate(bits):
                    if pixel:
                        cr.rectangle(x + column * 2 + 1, y + row * 2 + 1, 2, 2)
            cr.fill()
            cr.set_source_rgba(1, 0.42, 0.58, alpha)
            for row, bits in enumerate(PIXEL_HEART):
                for column, pixel in enumerate(bits):
                    if pixel:
                        cr.rectangle(x + column * 2, y + row * 2, 2, 2)
            cr.fill()
            cr.set_source_rgba(1, 0.82, 0.88, alpha * 0.9)
            cr.rectangle(x + 2, y + 2, 2, 2)
            cr.fill()

    def draw_drag_effect(self, cr, now):
        strength = self.drag_strength
        if strength <= 0.05:
            return
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        for y, length in ((52, 12), (68, 24), (84, 16)):
            if self.drag_dir > 0:
                x0, x1 = 4, 4 + length * strength
            else:
                x0, x1 = 124, 124 - length * strength
            cr.set_line_width(4)
            cr.set_source_rgba(0, 0, 0, 0.22 * strength)
            cr.move_to(x0, y)
            cr.line_to(x1, y)
            cr.stroke()
            cr.set_line_width(1.4)
            cr.set_source_rgba(1, 1, 1, 0.42 * strength)
            cr.move_to(x0, y)
            cr.line_to(x1, y)
            cr.stroke()

    def play_idle(self):
        self.stop_walk()
        self.cancel_sleep()
        if not self.get_visible():
            self.show_all()
        self.mode = "idle"
        self.on_bed = False
        if self.bed is not None:
            self.bed.queue_draw()
        self.animation = self.rest_animation
        self.loop(
            self.frames_for(self.rest_animation),
            self.rest_animation["rate"],
        )

    def choose_character(self, _item, selected):
        self.cancel_roam()
        self.cancel_sleep()
        self.stop_walk()
        self.character = selected
        self.frame_cache.clear()
        self.rest_animation = selected["anims"][0]
        self.sleep_animation = find_animation(selected, "sleep")
        self.play_idle()
        self.place()
        self.save()
        self.schedule_roam()

    def add_pet(self, _item, selected):
        x, y = self.pos if self.pos is not None else self.get_position()
        Cupcake(
            {
                "character": selected["id"],
                "x": x + 48,
                "y": y + 48,
                "roam": self.roam_enabled,
            }
        )

    def choose_animation(self, _item, selected):
        if selected["name"] == "sleep":
            self.sleep_here()
            return
        self.cancel_roam()
        self.cancel_sleep()
        self.stop_walk()
        self.rest_animation = selected
        self.play_idle()
        self.save()
        self.schedule_roam()

    def random_character(self, *_):
        self.choose_character(None, random.choice(CHARACTERS))
        self.choose_animation(None, random.choice(self.character["anims"]))

    def random_animation(self, *_):
        self.choose_animation(None, random.choice(self.character["anims"]))

    # MARK: - Movement and sleep

    def workarea(self):
        display = self.get_display()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        return monitor.get_workarea()

    def default_bed_x(self):
        area = self.workarea()
        try:
            schemas = Gio.SettingsSchemaSource.get_default()
            schema = schemas.lookup("org.gnome.shell", True)
            settings = Gio.Settings.new_full(schema, None, None)
            count = len(settings.get_strv("favorite-apps"))
        except Exception:
            count = 10
        # Dash2Dock Lite defaults: 64 px icons, 72 px slots, plus one running app.
        width = 64 + 72 * (max(3, count) + 1)
        dock_right = area.x + (area.width + width) // 2
        x = dock_right - 24
        return min(max(x, area.x), area.x + area.width - BED_W)

    def default_bed_y(self):
        area = self.workarea()
        return area.y + area.height - BED_H - BED_GAP

    def bed_xy(self):
        area = self.workarea()
        x = self.bed_x if self.bed_x is not None else self.default_bed_x()
        y = self.bed_y if self.bed_y is not None else self.default_bed_y()
        x = int(min(max(x, area.x), area.x + area.width - BED_W))
        y = int(min(max(y, area.y), area.y + area.height - BED_H))
        return x, y

    def bed_target(self):
        area = self.workarea()
        bed_x, bed_y = self.bed_xy()
        x = bed_x + (BED_W - SIZE) // 2
        y = bed_y - 32
        x = min(max(x, area.x), area.x + area.width - SIZE)
        y = min(max(y, area.y), area.y + area.height - SIZE)
        return int(x), int(y)

    def near_bed(self):
        if not self.bed_shown:
            return False
        x, y = self.pos if self.pos is not None else self.get_position()
        target_x, target_y = self.bed_target()
        return abs(x - target_x) < 64 and abs(y - target_y) < 64

    def raise_cat(self):
        window = self.get_window()
        if self.bed is not None and window is not None:
            window.raise_()
        return False

    def go_to_bed(self):
        if self.bed is None or self.mode == "sleep" or self.sleep_animation is None:
            return
        if not self.bed_shown:
            self.set_bed_shown(True)
        self.walk_to(*self.bed_target(), then="sleep_bed")

    def toggle_bed(self):
        if self.mode == "sleep":
            self.wake_up()
            self.schedule_roam(2)
        else:
            self.go_to_bed()

    def set_bed_shown(self, shown):
        self.bed_shown = shown
        if self.bed is None:
            return
        if shown:
            self.bed.place()
            self.bed.show_all()
            self.bed.queue_draw()
            self.raise_cat()
        else:
            if self.mode == "sleep" and self.on_bed:
                self.wake_up()
            elif self.mode == "walk" and self.walk_then == "sleep_bed":
                self.play_idle()
            self.bed.hide()

    def toggle_bed_shown(self, item):
        self.set_bed_shown(item.get_active())
        self.save()

    def sleep_here(self):
        if self.sleep_animation is None:
            self.play_idle()
            return
        self.stop_walk()
        self.cancel_roam()
        self.cancel_sleep()
        self.show_all()
        self.mode = "sleep"
        self.on_bed = False
        if self.bed is not None:
            self.bed.queue_draw()
        self.animation = self.sleep_animation
        self.loop(
            self.frames_for(self.sleep_animation),
            self.sleep_animation["rate"],
        )
        self.start_sleep_tick()
        self.raise_cat()
        self.schedule_wake()
        self.save()

    def sleep_on_bed(self):
        if self.sleep_animation is None:
            self.play_idle()
            return
        self.stop_walk()
        self.cancel_roam()
        self.cancel_sleep()
        self.mode = "sleep"
        self.on_bed = True
        self.hide()
        self.animation = self.sleep_animation
        self.loop(
            self.frames_for(self.sleep_animation),
            self.sleep_animation["rate"],
        )
        self.start_sleep_tick()
        self.bed.queue_draw()
        self.schedule_wake()
        self.save()

    def start_sleep_tick(self):
        if self.sleep_tick_timer is None:
            self.sleep_tick_timer = GLib.timeout_add(SLEEP_TICK, self.sleep_tick)

    def sleep_tick(self):
        if self.mode != "sleep":
            self.sleep_tick_timer = None
            return False
        self.queue_draw()
        if self.on_bed and self.bed is not None:
            self.bed.queue_draw()
        return True

    def schedule_wake(self):
        if self.sleep_timer is not None:
            GLib.source_remove(self.sleep_timer)
            self.sleep_timer = None
        if self.mode == "sleep" and self.roam_enabled:
            self.sleep_timer = GLib.timeout_add_seconds(
                random.randint(*SLEEP_WAKE), self.wake_up
            )

    def wake_up(self):
        self.sleep_timer = None
        if self.mode == "sleep":
            was_on_bed = self.on_bed
            if was_on_bed:
                self.move(*self.bed_target())
                self.pos = self.bed_target()
            self.play_idle()
            self.place()
            self.queue_draw()
            self.raise_cat()
            self.schedule_roam(2)
        return False

    def cancel_sleep(self):
        if self.sleep_timer is not None:
            GLib.source_remove(self.sleep_timer)
            self.sleep_timer = None
        if self.sleep_tick_timer is not None:
            GLib.source_remove(self.sleep_tick_timer)
            self.sleep_tick_timer = None

    def walk_to(self, x, y, then=None):
        self.cancel_roam()
        self.cancel_sleep()
        self.stop_walk()
        area = self.workarea()
        x = int(min(max(x, area.x), area.x + area.width - SIZE))
        y = int(min(max(y, area.y), area.y + area.height - SIZE))
        self.show_all()
        self.mode = "walk"
        self.on_bed = False
        self.walk_target = (x, y)
        self.walk_then = then
        self.animation = self.rest_animation
        current = self.pos if self.pos is not None else self.get_position()
        walk_animation = (
            find_animation(self.character, "run")
            or find_animation(self.character, "jump")
            or self.rest_animation
        )
        frames = self.frames_for(walk_animation)
        moving_left = x < current[0]
        if x != current[0] and needs_flip(self.character, moving_left):
            frames = self.flipped_frames(walk_animation)
        self.loop(frames, max(0.1, walk_animation["rate"]))
        self.walk_timer = GLib.timeout_add(WALK_TICK, self.walk_step)

    def walk_step(self):
        if self.mode != "walk" or self.walk_target is None:
            self.walk_timer = None
            return False
        x, y = self.pos if self.pos is not None else self.get_position()
        target_x, target_y = self.walk_target
        dx, dy = target_x - x, target_y - y
        distance = math.hypot(dx, dy)
        step = WALK_SPEED * WALK_TICK / 1000
        if distance <= step:
            self.move(target_x, target_y)
            self.pos = (target_x, target_y)
            then = self.walk_then
            self.walk_timer = None
            self.walk_target = None
            self.walk_then = None
            if then == "sleep_bed":
                self.sleep_on_bed()
            elif then == "sleep_here":
                self.sleep_here()
            else:
                self.play_idle()
                self.schedule_roam()
            return False
        new_x = int(round(x + dx / distance * step))
        new_y = int(round(y + dy / distance * step))
        self.move(new_x, new_y)
        self.pos = (new_x, new_y)
        return True

    def stop_walk(self):
        if self.walk_timer is not None:
            GLib.source_remove(self.walk_timer)
            self.walk_timer = None
        self.walk_target = None
        self.walk_then = None

    def schedule_roam(self, delay=None):
        self.cancel_roam()
        if not self.roam_enabled:
            return
        if delay is None:
            delay = random.randint(10, 24)
        self.roam_timer = GLib.timeout_add_seconds(delay, self.roam_step)

    def cancel_roam(self):
        if self.roam_timer is not None:
            GLib.source_remove(self.roam_timer)
            self.roam_timer = None

    def roam_step(self):
        self.roam_timer = None
        if not self.roam_enabled or self.drag is not None:
            return False
        if self.mode == "sleep":
            return False
        if self.mode != "idle":
            self.schedule_roam()
            return False
        roll = random.random()
        can_sleep = self.sleep_animation is not None
        if roll < 0.42:
            area = self.workarea()
            self.walk_to(
                random.randint(area.x, area.x + area.width - SIZE),
                random.randint(area.y, area.y + area.height - SIZE),
            )
        elif can_sleep and roll < 0.62:
            area = self.workarea()
            self.walk_to(
                random.randint(area.x, area.x + area.width - SIZE),
                random.randint(area.y, area.y + area.height - SIZE),
                then="sleep_here",
            )
        elif can_sleep and roll < 0.84 and self.bed_shown:
            self.go_to_bed()
        else:
            self.schedule_roam()
        return False

    def click_reaction(self):
        self.cancel_roam()
        self.cancel_sleep()
        self.stop_walk()
        now = GLib.get_monotonic_time() / 1_000_000
        self.click_times = [
            stamp for stamp in self.click_times if now - stamp <= LOVE_WINDOW
        ]
        self.click_times.append(now)
        if len(self.click_times) >= LOVE_CLICKS:
            self.click_times = []
            self.love_until = now + LOVE_TIME
            if self.love_timer is None:
                self.love_timer = GLib.timeout_add(50, self.love_tick)
        reaction = (
            find_animation(self.character, "jump")
            or find_animation(self.character, "eating")
            or self.rest_animation
        )
        self.show_all()
        self.mode = "play"
        self.on_bed = False
        self.animation = self.rest_animation
        self.once(
            self.frames_for(reaction),
            reaction["rate"],
            self.after_play,
        )

    def love_tick(self):
        if GLib.get_monotonic_time() / 1_000_000 >= self.love_until:
            self.love_timer = None
            self.love_until = 0
            self.queue_draw()
            return False
        self.queue_draw()
        return True

    def after_play(self):
        self.play_idle()
        self.schedule_roam(5)

    def on_roam_toggled(self, item):
        self.roam_enabled = item.get_active()
        if self.roam_enabled:
            if self.mode == "sleep":
                self.start_sleep_tick()
                self.schedule_wake()
            self.schedule_roam(3)
        else:
            self.cancel_roam()
            if self.sleep_timer is not None:
                GLib.source_remove(self.sleep_timer)
                self.sleep_timer = None
            if self.mode == "walk":
                self.play_idle()
        self.save()

    # MARK: - Window

    def place(self):
        area = self.workarea()
        if self.pos is None:
            self.pos = (
                area.x + area.width - SIZE - 32,
                area.y + area.height - SIZE - 32,
            )
        # Keep the cat reachable if a monitor was unplugged.
        x = min(max(self.pos[0], area.x), area.x + area.width - SIZE)
        y = min(max(self.pos[1], area.y), area.y + area.height - SIZE)
        self.move(x, y)
        self.pos = (x, y)

    def on_press(self, _widget, event):
        self.cancel_roam()
        if event.button == 3:
            self.stop_walk()
            if self.mode in ("walk", "play"):
                self.play_idle()
            self.build_menu().popup_at_pointer(event)
        elif event.button == 1:
            self.stop_walk()
            if self.mode == "walk":
                self.play_idle()
            self.press = (event.x_root, event.y_root)
            win_x, win_y = self.pos if self.pos is not None else self.get_position()
            self.drag = (event.x_root, event.y_root, win_x, win_y)
            self.drag_last = event.x_root
            self.moved = False
            self.dragging = False
            set_hand_cursor(self, "grabbing")
        return True

    def on_motion(self, _widget, event):
        if self.drag is not None:
            x0, y0, win_x, win_y = self.drag
            moved_x = abs(event.x_root - self.press[0]) > 2
            moved_y = abs(event.y_root - self.press[1]) > 2
            if moved_x or moved_y:
                self.moved = True
                if not self.dragging:
                    self.dragging = True
                    if self.mode in ("sleep", "play", "walk"):
                        self.cancel_sleep()
                        self.play_idle()
                step_x = event.x_root - self.drag_last
                self.drag_last = event.x_root
                if step_x:
                    self.drag_dir = 1 if step_x > 0 else -1
                    self.drag_tilt = -max(-10.0, min(10.0, step_x * 1.2))
                    self.drag_strength = min(1.0, abs(step_x) / 6)
                if self.drag_timer is None:
                    self.drag_timer = GLib.timeout_add(50, self.drag_tick)
            area = self.workarea()
            x = int(win_x + event.x_root - x0)
            y = int(win_y + event.y_root - y0)
            x = min(max(x, area.x), area.x + area.width - SIZE)
            y = min(max(y, area.y), area.y + area.height - SIZE)
            self.move(x, y)
            self.pos = (x, y)
        return True

    def drag_tick(self):
        if not self.dragging:
            self.drag_timer = None
            return False
        self.drag_tilt *= 0.65
        self.drag_strength *= 0.7
        self.queue_draw()
        if abs(self.drag_tilt) < 0.1 and self.drag_strength < 0.05:
            self.drag_timer = None
            return False
        return True

    def stop_drag_effect(self):
        if self.drag_timer is not None:
            GLib.source_remove(self.drag_timer)
            self.drag_timer = None
        self.dragging = False
        self.drag_tilt = 0
        self.drag_strength = 0
        self.queue_draw()

    def on_release(self, _widget, event):
        if event.button == 1 and self.drag is not None:
            clicked = not self.moved
            self.drag = None
            self.stop_drag_effect()
            set_hand_cursor(self, "grab")
            if clicked:
                self.click_reaction()
            elif self.sleep_animation is not None and self.near_bed():
                self.sleep_on_bed()
            else:
                self.save()
                self.schedule_roam(6)
        return True

    def on_destroy(self, *_):
        if not QUITTING:
            self.save()
        self.cancel_roam()
        self.cancel_sleep()
        self.stop_walk()
        self.stop_timer()
        if self.love_timer is not None:
            GLib.source_remove(self.love_timer)
            self.love_timer = None
        if self.drag_timer is not None:
            GLib.source_remove(self.drag_timer)
            self.drag_timer = None
        if self.bed is not None:
            self.bed.destroy()
            self.bed = None
        tray = getattr(self, "tray", None)
        if tray is not None:
            tray.set_visible(False)
        if self in PETS:
            PETS.remove(self)
        if not PETS and not QUITTING:
            Gtk.main_quit()

    # MARK: - Menu and tray

    def build_menu(self):
        menu = Gtk.Menu()

        characters_item = Gtk.MenuItem(label="Characters")
        characters_menu = Gtk.Menu()
        group = None
        for item_character in CHARACTERS:
            item = Gtk.RadioMenuItem(label=item_character["name"])
            if group is None:
                group = item
            else:
                item.join_group(group)
            item.set_active(item_character is self.character)
            item.connect("activate", self.choose_character, item_character)
            characters_menu.append(item)
        characters_item.set_submenu(characters_menu)
        menu.append(characters_item)

        add_item = Gtk.MenuItem(label="Add Pet")
        add_menu = Gtk.Menu()
        for item_character in CHARACTERS:
            item = Gtk.MenuItem(label=item_character["name"])
            item.connect("activate", self.add_pet, item_character)
            add_menu.append(item)
        add_item.set_submenu(add_menu)
        menu.append(add_item)

        animations_item = Gtk.MenuItem(label="Animations")
        animations_menu = Gtk.Menu()
        group = None
        for item_animation in self.character["anims"]:
            item = Gtk.RadioMenuItem(label=item_animation["label"])
            if group is None:
                group = item
            else:
                item.join_group(group)
            if item_animation["name"] == "sleep":
                active = self.mode == "sleep"
            else:
                active = item_animation is self.rest_animation and self.mode != "sleep"
            item.set_active(active)
            item.connect("activate", self.choose_animation, item_animation)
            animations_menu.append(item)
        animations_item.set_submenu(animations_menu)
        menu.append(animations_item)

        menu.append(Gtk.SeparatorMenuItem())

        bed_item = Gtk.MenuItem(
            label="Wake Up" if self.mode == "sleep" else "Go to Bed"
        )
        bed_item.set_sensitive(self.sleep_animation is not None)
        bed_item.connect("activate", lambda *_: self.toggle_bed())
        menu.append(bed_item)

        bed_show = Gtk.CheckMenuItem(label="Show Bed")
        bed_show.set_active(self.bed_shown)
        bed_show.connect("toggled", self.toggle_bed_shown)
        menu.append(bed_show)

        roam_item = Gtk.CheckMenuItem(label="Roam Freely")
        roam_item.set_active(self.roam_enabled)
        roam_item.connect("toggled", self.on_roam_toggled)
        menu.append(roam_item)

        menu.append(Gtk.SeparatorMenuItem())

        random_character = Gtk.MenuItem(label="Random Character")
        random_character.connect("activate", self.random_character)
        menu.append(random_character)

        random_animation = Gtk.MenuItem(label="Random Animation")
        random_animation.connect("activate", self.random_animation)
        menu.append(random_animation)

        menu.append(Gtk.SeparatorMenuItem())

        info_text = f"{self.character['name']} · {self.animation['label']}"
        info = Gtk.MenuItem(label=info_text)
        info.set_sensitive(False)
        menu.append(info)

        menu.append(Gtk.SeparatorMenuItem())

        about = Gtk.MenuItem(label="About")
        about.connect("activate", self.show_about)
        menu.append(about)

        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", self.quit)
        menu.append(quit_item)

        menu.connect("selection-done", self.on_menu_done)
        menu.show_all()
        self.menu = menu  # keep a reference while it is open
        return menu

    def on_menu_done(self, *_):
        if self.mode != "sleep":
            self.schedule_roam(6)

    def setup_tray(self):
        self.tray = Gtk.StatusIcon()
        if ICON.is_file():
            self.tray.set_from_file(str(ICON))
        else:
            self.tray.set_from_icon_name("applications-utilities")
        self.tray.set_tooltip_text("Cupcake")
        self.tray.connect("popup-menu", self.on_tray_popup)
        self.tray.set_visible(True)

    def on_tray_popup(self, icon, button, activate_time):
        self.build_menu().popup(
            None, None, Gtk.StatusIcon.position_menu, icon, button, activate_time
        )

    def show_about(self, *_):
        Gtk.show_about_dialog(
            parent=self,
            program_name="Cupcake",
            version="1.3",
            comments="Adorable animated kitties for your desktop.",
            website="https://github.com/wizenheimer/cupcake",
            website_label="GitHub",
            license_type=Gtk.License.MIT_X11,
        )

    def quit(self, *_):
        global QUITTING
        save_all()
        QUITTING = True
        for pet in list(PETS):
            pet.destroy()
        Gtk.main_quit()

    # MARK: - State

    def state(self):
        x, y = self.pos if self.pos is not None else self.get_position()
        return {
            "character": self.character["id"],
            "animation": self.rest_animation["name"],
            "x": x,
            "y": y,
            "bed_x": self.bed_x,
            "bed_y": self.bed_y,
            "bed_shown": self.bed_shown,
            "bed_version": self.bed_version,
            "roam": self.roam_enabled,
        }

    def save(self):
        save_all()

    def restore(self, state=None):
        if not isinstance(state, dict):
            return
        self.character = next(
            (c for c in CHARACTERS if c["id"] == state.get("character")),
            self.character,
        )
        self.sleep_animation = find_animation(self.character, "sleep")
        self.rest_animation = next(
            (
                a
                for a in self.character["anims"]
                if a["name"] == state.get("animation")
                and a["name"] != "sleep"
            ),
            self.character["anims"][0],
        )
        self.animation = self.rest_animation
        if isinstance(state.get("x"), int) and isinstance(state.get("y"), int):
            self.pos = (state["x"], state["y"])
        if state.get("bed_version") == self.bed_version:
            if isinstance(state.get("bed_x"), int):
                self.bed_x = state["bed_x"]
            if isinstance(state.get("bed_y"), int):
                self.bed_y = state["bed_y"]
        if isinstance(state.get("bed_shown"), bool):
            self.bed_shown = state["bed_shown"]
        if isinstance(state.get("roam"), bool):
            self.roam_enabled = state["roam"]


def main():
    GLib.set_prgname("cupcake")
    states = load_states()
    for state in states:
        Cupcake(state)
    if not states:
        Cupcake()
    Gtk.main()


if __name__ == "__main__":
    main()
