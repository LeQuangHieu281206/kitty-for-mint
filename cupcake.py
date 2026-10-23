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

SIZE = 128  # 32x32 sprites at 4x, nearest neighbour keeps them crisp
BED_W = 112
BED_H = 96
BED_GAP = 4  # px between the bed window and the screen edge
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
ZZZ_BED = ((76, 24, 1), (83, 16, 1), (91, 3, 2))
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

CLASSIC = [
    ("classical_cat", "Vanilla"),
    ("batman_cat", "Midnight"),
    ("black_cat", "Cocoa"),
    ("brown_cat", "Caramel"),
    ("demonic_cat", "Spicy"),
    ("egypt_cat", "Honey"),
    ("siamese_cat", "Cookies"),
    ("three_color_cat", "Rainbow"),
    ("tiger_cat", "Orange"),
    ("white_cat", "Sugar"),
    ("xmas_cat", "Mint"),
]

SPECIALS = [
    ("zombie_cat", "Zombie", [("eating", "Feast", 15, 0.12)]),
    ("flame_cat", "Inferno", [("jump", "Flame Leap", 13, 0.08)]),
    ("frost_cat", "Blizzard", [("jump", "Ice Leap", 13, 0.08)]),
    ("lightning_cat", "Thunder", [("jump", "Lightning Strike", 13, 0.08)]),
    ("shadow_cat", "Phantom", [("jump", "Shadow Dash", 13, 0.08)]),
    ("storm_cat", "Tempest", [("jump", "Wind Leap", 13, 0.08)]),
    ("couchbase_cat", "Couchbase", [("jump", "Gust", 13, 0.08)]),
]


def character(ident, name, animations):
    anims = [
        {"name": a[0], "label": a[1], "frames": a[2], "rate": a[3]}
        for a in animations
    ]
    # There are no sleep sprites in the original assets. Synthesise a lying
    # pose from the cat's own head/body and draw the Zzz in on_draw.
    source = next((a for a in anims if a["name"] == "idle"), anims[0])
    anims.append(
        {
            "name": "sleep",
            "label": "Sleep",
            "frames": 2,
            "rate": 0.75,
            "asset": source["name"],
            "generated": True,
        }
    )
    return {"id": ident, "name": name, "anims": anims}


CHARACTERS = [
    character(
        ident,
        name,
        [
            ("idle", "Chill", 14 if ident == "xmas_cat" else 7, 0.15),
            ("jump", "Wiggle", 13, 0.15),
        ],
    )
    for ident, name in CLASSIC
] + [character(ident, name, anims) for ident, name, anims in SPECIALS]


def find_animation(character, name):
    return next((a for a in character["anims"] if a["name"] == name), None)


def transparent(window):
    window.set_decorated(False)
    window.set_resizable(False)
    window.set_keep_above(True)
    window.set_skip_taskbar_hint(True)
    window.set_skip_pager_hint(True)
    window.set_accept_focus(False)
    window.set_app_paintable(True)
    window.set_type_hint(Gdk.WindowTypeHint.UTILITY)
    visual = window.get_screen().get_rgba_visual()
    if visual is not None:
        window.set_visual(visual)


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
    """Copy a pixbuf into a plain RGBA bytearray (32x32 assets only)."""
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


def generate_sleep_frames(character):
    """Combine the cat's head and a flattened body into a lying-down pose."""
    sleep = find_animation(character, "sleep")
    path = asset(f"00_{character['id']}_{sleep['asset']}")
    if path is None:
        return []
    try:
        source = GdkPixbuf.Pixbuf.new_from_file(str(path))
    except GLib.Error as error:
        print(f"Warning: cannot load {path}: {error.message}")
        return []
    base = rgba_pixels(source)
    close_eyes(base)

    frames = []
    for head_drop in (0, 1):
        canvas = bytearray(SPRITE * SPRITE * 4)
        # Flatten the body to a low loaf.
        for dy in range(13):
            sy = 10 + dy * 20 // 13
            for dx in range(28):
                sx = 2 + dx * 22 // 28
                source_index = (sy * SPRITE + sx) * 4
                target_index = ((17 + dy) * SPRITE + (1 + dx)) * 4
                canvas[target_index : target_index + 4] = base[
                    source_index : source_index + 4
                ]
        # Keep the head upright, with a one-pixel breathing dip.
        for y in range(22):
            for x in range(16):
                source_index = ((4 + y) * SPRITE + (14 + x)) * 4
                target_index = ((8 + head_drop + y) * SPRITE + (14 + x)) * 4
                canvas[target_index : target_index + 4] = base[
                    source_index : source_index + 4
                ]
        frames.append(
            GdkPixbuf.Pixbuf.new_from_bytes(
                GLib.Bytes.new(bytes(canvas)),
                GdkPixbuf.Colorspace.RGB,
                True,
                8,
                SPRITE,
                SPRITE,
                SPRITE * 4,
            )
        )
    return frames


def ellipse_path(cr, x, y, rx, ry):
    cr.save()
    cr.translate(x, y)
    cr.scale(rx, ry)
    cr.arc(0, 0, 1, 0, math.tau)
    cr.restore()


def draw_bed_base(cr):
    # Shadow
    cr.set_source_rgba(0, 0, 0, 0.18)
    ellipse_path(cr, 56, 92, 40, 4)
    cr.fill()

    # Plush bolster
    cr.set_source_rgb(0.93, 0.85, 0.72)
    ellipse_path(cr, 56, 72, 44, 22)
    cr.fill()
    cr.set_source_rgb(0.98, 0.93, 0.84)
    ellipse_path(cr, 56, 68, 44, 20)
    cr.fill()

    # Cushion
    cr.set_source_rgb(0.74, 0.61, 0.46)
    ellipse_path(cr, 56, 70, 36, 15)
    cr.fill()
    cr.set_source_rgb(0.47, 0.31, 0.22)
    ellipse_path(cr, 56, 72, 33, 12)
    cr.fill()
    cr.set_source_rgb(0.55, 0.37, 0.27)
    ellipse_path(cr, 56, 70, 31, 10)
    cr.fill()

    cr.set_line_width(1.4)
    cr.set_source_rgba(1, 0.98, 0.92, 0.9)
    cr.save()
    cr.translate(56, 68)
    cr.scale(43, 19)
    cr.arc(0, 0, 1, math.pi * 1.08, math.pi * 1.92)
    cr.restore()
    cr.stroke()

    # Small pillow
    cr.set_source_rgb(0.89, 0.78, 0.61)
    cr.rectangle(15, 64, 27, 11)
    cr.fill()
    cr.set_source_rgb(1, 0.98, 0.92)
    cr.rectangle(15, 60, 27, 11)
    cr.fill()
    cr.set_source_rgba(0.72, 0.60, 0.45, 0.55)
    cr.rectangle(17, 70, 23, 1)
    cr.fill()

    # Stitches
    cr.set_source_rgba(0.68, 0.55, 0.39, 0.8)
    for x, y in (
        (17, 57),
        (27, 52),
        (44, 49),
        (62, 49),
        (79, 52),
        (91, 58),
        (99, 66),
        (101, 76),
        (97, 84),
    ):
        cr.rectangle(x, y, 2, 1)
    cr.fill()


def draw_bed_front(cr):
    # Front lip, drawn after the cat so it looks tucked into the bed.
    cr.save()
    cr.rectangle(8, 84, 96, 20)
    cr.clip()
    cr.set_source_rgb(0.97, 0.91, 0.81)
    ellipse_path(cr, 56, 68, 44, 20)
    cr.fill()
    cr.set_source_rgb(0.98, 0.94, 0.86)
    ellipse_path(cr, 56, 65, 42, 17)
    cr.fill()
    cr.restore()
    cr.set_source_rgba(0.72, 0.60, 0.45, 0.45)
    cr.set_line_width(1)
    cr.move_to(15, 86)
    cr.curve_to(28, 91, 84, 91, 98, 85)
    cr.stroke()
    cr.set_source_rgba(1, 0.97, 0.90, 0.9)
    cr.set_line_width(1.3)
    cr.move_to(14, 83)
    cr.curve_to(30, 88, 82, 88, 98, 82)
    cr.stroke()


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

    def on_realize(self, _widget):
        # Keep the transparent edges from stealing clicks from the dock.
        region = cairo.Region(cairo.RectangleInt(8, 20, BED_W - 16, BED_H - 24))
        self.get_window().input_shape_combine_region(region, 0, 0)

    def place(self):
        area = self.app.workarea()
        x = self.app.bed_x
        if x is None:
            x = self.app.default_bed_x()
        x = min(max(x, area.x), area.x + area.width - BED_W)
        self.app.bed_x = x
        self.move(x, area.y + area.height - BED_H - BED_GAP)

    def sleeping(self):
        return self.app.mode == "sleep" and self.app.on_bed

    def scaled_cat(self):
        frames = self.app.frames_for(self.app.sleep_animation)
        if not frames:
            return None
        frame = frames[self.app.frame_index % len(frames)]
        key = (id(frame), 64)
        if key != self.cat_key:
            self.cat_frame = frame.scale_simple(
                64, 64, GdkPixbuf.InterpType.NEAREST
            )
            self.cat_key = key
        return self.cat_frame

    def on_draw(self, _widget, cr):
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        draw_bed_base(cr)
        if self.sleeping():
            frame = self.scaled_cat()
            if frame is not None:
                Gdk.cairo_set_source_pixbuf(cr, frame, 24, 22)
                cr.paint()
        draw_bed_front(cr)
        if self.sleeping():
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
            self.drag = (event.x_root, self.app.bed_x)
            self.moved = False
        self.app.raise_cat()
        return True

    def on_motion(self, _widget, event):
        if self.drag is not None:
            x0, win_x = self.drag
            offset = event.x_root - x0
            if abs(offset) > 2:
                self.moved = True
            area = self.app.workarea()
            x = int(min(max(win_x + offset, area.x), area.x + area.width - BED_W))
            self.move(x, area.y + area.height - BED_H - BED_GAP)
            self.app.bed_x = x
            self.queue_draw()
            self.app.raise_cat()
        return True

    def on_release(self, _widget, event):
        if event.button == 1 and self.drag is not None:
            moved = self.moved
            self.drag = None
            if moved:
                self.app.save()
                self.app.schedule_roam(3)
            else:
                self.app.toggle_bed()
        return True


class Cupcake(Gtk.Window):
    def __init__(self):
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
        self.bed = None
        self.bed_version = 2
        self.click_times = []
        self.love_until = 0
        self.love_timer = None
        self.dragging = False
        self.drag_tilt = 0
        self.drag_strength = 0
        self.drag_dir = 1
        self.drag_timer = None
        self.drag_last = 0

        self.restore()
        self.play_idle()
        self.show_all()
        self.place()

        self.bed = Bed(self)
        self.bed.place()
        self.bed.show_all()
        self.raise_cat()
        GLib.idle_add(self.raise_cat)

        # GNOME never displays legacy XEmbed tray icons, so skip the wasted icon.
        if "GNOME" not in os.environ.get("XDG_CURRENT_DESKTOP", "").upper():
            self.setup_tray()
        self.schedule_roam()

    # MARK: - Animation

    def frames_for(self, animation):
        if animation.get("generated"):
            key = ("sleep", self.character["id"])
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

    def bed_xy(self):
        area = self.workarea()
        x = self.bed_x
        if x is None:
            x = self.default_bed_x()
        return int(x), area.y + area.height - BED_H - BED_GAP

    def bed_target(self):
        area = self.workarea()
        bed_x, bed_y = self.bed_xy()
        x = bed_x + (BED_W - SIZE) // 2
        y = bed_y - SIZE + 60
        x = min(max(x, area.x), area.x + area.width - SIZE)
        y = min(max(y, area.y), area.y + area.height - SIZE)
        return int(x), int(y)

    def near_bed(self):
        x, y = self.pos if self.pos is not None else self.get_position()
        target_x, target_y = self.bed_target()
        return abs(x - target_x) < 64 and abs(y - target_y) < 64

    def raise_cat(self):
        window = self.get_window()
        if self.bed is not None and window is not None:
            window.raise_()
        return False

    def go_to_bed(self):
        if self.bed is None or self.mode == "sleep":
            return
        self.walk_to(*self.bed_target(), then="sleep_bed")

    def toggle_bed(self):
        if self.mode == "sleep":
            self.wake_up()
            self.schedule_roam(2)
        else:
            self.go_to_bed()

    def sleep_here(self):
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
        self.stop_walk()
        self.cancel_roam()
        self.cancel_sleep()
        self.mode = "sleep"
        self.on_bed = True
        self.hide()
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
            find_animation(self.character, "jump") or self.rest_animation
        )
        frames = self.frames_for(walk_animation)
        if x < current[0]:
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
        if roll < 0.42:
            area = self.workarea()
            self.walk_to(
                random.randint(area.x, area.x + area.width - SIZE),
                random.randint(area.y, area.y + area.height - SIZE),
            )
        elif roll < 0.62:
            area = self.workarea()
            self.walk_to(
                random.randint(area.x, area.x + area.width - SIZE),
                random.randint(area.y, area.y + area.height - SIZE),
                then="sleep_here",
            )
        elif roll < 0.84:
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
            if clicked:
                self.click_reaction()
            elif self.near_bed():
                self.sleep_on_bed()
            else:
                self.save()
                self.schedule_roam(6)
        return True

    def on_destroy(self, *_):
        self.save()
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
        bed_item.connect("activate", lambda *_: self.toggle_bed())
        menu.append(bed_item)

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
            version="1.2",
            comments="Adorable animated kitties for your desktop.",
            website="https://github.com/wizenheimer/cupcake",
            website_label="GitHub",
            license_type=Gtk.License.MIT_X11,
        )

    def quit(self, *_):
        self.save()
        Gtk.main_quit()

    # MARK: - State

    def save(self):
        x, y = self.pos if self.pos is not None else self.get_position()
        state = {
            "character": self.character["id"],
            "animation": self.rest_animation["name"],
            "x": x,
            "y": y,
            "bed_x": self.bed_x,
            "bed_version": self.bed_version,
            "roam": self.roam_enabled,
        }
        try:
            CONFIG.parent.mkdir(parents=True, exist_ok=True)
            CONFIG.write_text(json.dumps(state))
        except OSError as error:
            print(f"Warning: cannot save state: {error}")

    def restore(self):
        try:
            state = json.loads(CONFIG.read_text())
        except (OSError, ValueError):
            return
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
        if state.get("bed_version") == self.bed_version and isinstance(
            state.get("bed_x"), int
        ):
            self.bed_x = state["bed_x"]
        if isinstance(state.get("roam"), bool):
            self.roam_enabled = state["roam"]


def main():
    GLib.set_prgname("cupcake")
    Cupcake()
    Gtk.main()


if __name__ == "__main__":
    main()
