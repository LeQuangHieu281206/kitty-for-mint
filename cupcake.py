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
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk

SIZE = 128  # 32x32 sprites at 4x, nearest neighbour keeps them crisp
BED_W = 144
BED_H = 80
WALK_SPEED = 90  # pixels per second
WALK_TICK = 40  # milliseconds
SLEEP_WAKE = (30, 90)  # seconds
PIXEL_Z = ((1, 1, 1), (0, 0, 1), (0, 1, 0), (1, 0, 0), (1, 1, 1))

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
    # There are no sleep sprites in the original assets. Reuse idle frames
    # (or a single frame for special cats) and draw the Zzz in on_draw.
    source = next((a for a in anims if a["name"] == "idle"), anims[0])
    anims.append(
        {
            "name": "sleep",
            "label": "Sleep",
            "frames": source["frames"] if source["name"] == "idle" else 1,
            "rate": 0.55,
            "asset": source["name"],
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


class Bed(Gtk.Window):
    """Small transparent bed that sits above the bottom panel/dock."""

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
        self.connect("button-press-event", self.on_press)
        self.connect("button-release-event", self.on_release)
        self.connect("motion-notify-event", self.on_motion)
        self.drag = None
        self.moved = False

    def place(self):
        area = self.app.workarea()
        x = self.app.bed_x
        if x is None:
            x = area.x + (area.width - BED_W) // 2
        x = min(max(x, area.x), area.x + area.width - BED_W)
        self.app.bed_x = x
        self.move(x, area.y + area.height - BED_H - 4)

    def on_draw(self, _widget, cr):
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        # Shadow
        cr.set_source_rgba(0, 0, 0, 0.16)
        cr.save()
        cr.translate(BED_W / 2, 74)
        cr.scale(62, 5)
        cr.arc(0, 0, 1, 0, math.pi * 2)
        cr.restore()
        cr.fill()

        # Headboard, footboard and legs
        cr.set_source_rgb(0.36, 0.21, 0.11)
        cr.rectangle(4, 8, 14, 54)
        cr.rectangle(126, 26, 14, 36)
        cr.rectangle(18, 60, 8, 12)
        cr.rectangle(118, 60, 8, 12)
        cr.rectangle(2, 6, 18, 4)
        cr.rectangle(124, 24, 18, 4)
        cr.fill()

        # Wooden frame
        cr.set_source_rgb(0.53, 0.33, 0.18)
        cr.rectangle(10, 46, 124, 12)
        cr.fill()
        cr.set_source_rgb(0.68, 0.46, 0.27)
        cr.rectangle(10, 46, 124, 3)
        cr.fill()

        # Mattress
        cr.set_source_rgb(0.95, 0.90, 0.80)
        cr.rectangle(14, 30, 116, 18)
        cr.fill()
        cr.set_source_rgb(0.84, 0.77, 0.66)
        cr.rectangle(14, 46, 116, 2)
        cr.fill()

        # Pillow
        cr.set_source_rgb(0.99, 0.98, 0.94)
        cr.rectangle(20, 25, 32, 14)
        cr.fill()
        cr.set_source_rgb(0.86, 0.86, 0.84)
        cr.rectangle(35, 27, 2, 10)
        cr.fill()

        # Blanket
        cr.set_source_rgb(0.31, 0.51, 0.78)
        cr.rectangle(58, 30, 72, 18)
        cr.fill()
        cr.set_source_rgb(0.45, 0.65, 0.91)
        cr.rectangle(58, 35, 72, 2)
        cr.rectangle(58, 41, 72, 2)
        cr.fill()
        cr.set_source_rgb(0.23, 0.40, 0.64)
        cr.rectangle(58, 30, 2, 18)
        cr.fill()
        return False

    def on_press(self, _widget, event):
        if event.button == 3:
            self.app.cancel_roam()
            if self.app.mode in ("walk", "play"):
                self.app.play_idle()
            self.app.build_menu().popup_at_pointer(event)
        elif event.button == 1:
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
            x = int(
                min(max(win_x + offset, area.x), area.x + area.width - BED_W)
            )
            self.move(x, area.y + area.height - BED_H - 4)
            self.app.bed_x = x
            if self.app.mode == "sleep":
                self.app.place_on_bed()
            self.app.raise_cat()
        return True

    def on_release(self, _widget, event):
        if event.button == 1 and self.drag is not None:
            moved = self.moved
            self.drag = None
            if moved:
                self.app.save()
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
        self.roam_enabled = True
        self.bed_x = None
        self.bed = None

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
        if self.frames:
            cr.save()
            if self.mode == "sleep":
                bob = 1 if int(GLib.get_monotonic_time() / 1_000_000 * 1.4) % 2 else 0
                cr.translate(0, bob)
            frame = self.frames[self.frame_index % len(self.frames)]
            Gdk.cairo_set_source_pixbuf(cr, frame, 0, 0)
            cr.paint()
            cr.restore()
            if self.mode == "sleep":
                self.draw_zzz(cr)
        return False

    def draw_zzz(self, cr):
        rise = int((GLib.get_monotonic_time() / 1_000_000) % 2)
        glyphs = ((84, 30, 2), (94, 20, 2), (104, 3, 3))
        for offset, color in ((1, (0.08, 0.08, 0.12, 0.5)), (0, (1, 1, 1, 0.96))):
            cr.new_path()
            for x, y, size in glyphs:
                for row, bits in enumerate(PIXEL_Z):
                    for column, pixel in enumerate(bits):
                        if pixel:
                            cr.rectangle(
                                x + column * size + offset,
                                y + row * size + offset - rise,
                                size,
                                size,
                            )
            cr.set_source_rgba(*color)
            cr.fill()

    def play_idle(self):
        self.stop_walk()
        self.cancel_sleep()
        self.mode = "idle"
        self.on_bed = False
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
        self.save()
        self.schedule_roam()

    def choose_animation(self, _item, selected):
        if selected["name"] == "sleep":
            self.go_to_bed()
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

    def bed_xy(self):
        area = self.workarea()
        x = self.bed_x
        if x is None:
            x = area.x + (area.width - BED_W) // 2
        return int(x), area.y + area.height - BED_H - 4

    def place_on_bed(self):
        bed_x, bed_y = self.bed_xy()
        x = bed_x + (BED_W - SIZE) // 2
        y = bed_y - SIZE + 48
        self.move(x, y)
        self.pos = (x, y)

    def near_bed(self):
        bed_x, bed_y = self.bed_xy()
        x, y = self.pos if self.pos is not None else self.get_position()
        return (
            abs(x - (bed_x + (BED_W - SIZE) // 2)) < 56
            and abs(y - (bed_y - SIZE + 48)) < 56
        )

    def raise_cat(self):
        window = self.get_window()
        if self.bed is not None and window is not None:
            window.raise_()
        return False

    def go_to_bed(self):
        if self.bed is None or self.mode == "sleep":
            return
        bed_x, bed_y = self.bed_xy()
        self.walk_to(
            bed_x + (BED_W - SIZE) // 2,
            bed_y - SIZE + 48,
            then="sleep",
        )

    def toggle_bed(self):
        if self.mode == "sleep":
            self.cancel_sleep()
            self.play_idle()
            self.schedule_roam(2)
        else:
            self.go_to_bed()

    def sleep_now(self):
        self.stop_walk()
        self.cancel_roam()
        self.cancel_sleep()
        self.mode = "sleep"
        self.on_bed = True
        self.animation = self.sleep_animation
        self.place_on_bed()
        self.loop(
            self.frames_for(self.sleep_animation),
            self.sleep_animation["rate"],
            tick_single=True,
        )
        self.raise_cat()
        self.schedule_wake()

    def schedule_wake(self):
        self.cancel_sleep()
        if self.mode == "sleep" and self.roam_enabled:
            self.sleep_timer = GLib.timeout_add_seconds(
                random.randint(*SLEEP_WAKE), self.wake_up
            )

    def wake_up(self):
        self.sleep_timer = None
        if self.mode == "sleep":
            self.play_idle()
            self.schedule_roam(2)
        return False

    def cancel_sleep(self):
        if self.sleep_timer is not None:
            GLib.source_remove(self.sleep_timer)
            self.sleep_timer = None

    def walk_to(self, x, y, then=None):
        self.cancel_roam()
        self.stop_walk()
        area = self.workarea()
        x = int(min(max(x, area.x), area.x + area.width - SIZE))
        y = int(min(max(y, area.y), area.y + area.height - SIZE))
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
            if then == "sleep":
                self.sleep_now()
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
        if roll < 0.5:
            area = self.workarea()
            self.walk_to(
                random.randint(area.x, area.x + area.width - SIZE),
                random.randint(area.y, area.y + area.height - SIZE),
            )
        elif roll < 0.8:
            self.go_to_bed()
        else:
            self.schedule_roam()
        return False

    def click_reaction(self):
        self.cancel_roam()
        self.cancel_sleep()
        self.stop_walk()
        reaction = (
            find_animation(self.character, "jump")
            or find_animation(self.character, "eating")
            or self.rest_animation
        )
        self.mode = "play"
        self.on_bed = False
        self.animation = self.rest_animation
        self.once(
            self.frames_for(reaction),
            reaction["rate"],
            self.after_play,
        )

    def after_play(self):
        self.play_idle()
        self.schedule_roam(5)

    def on_roam_toggled(self, item):
        self.roam_enabled = item.get_active()
        if self.roam_enabled:
            if self.mode == "sleep":
                self.schedule_wake()
            self.schedule_roam(3)
        else:
            self.cancel_roam()
            self.cancel_sleep()
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
            self.moved = False
        return True

    def on_motion(self, _widget, event):
        if self.drag is not None:
            x0, y0, win_x, win_y = self.drag
            moved_x = abs(event.x_root - self.press[0]) > 2
            moved_y = abs(event.y_root - self.press[1]) > 2
            if moved_x or moved_y:
                self.moved = True
                if self.mode in ("sleep", "play", "walk"):
                    self.cancel_sleep()
                    self.play_idle()
            area = self.workarea()
            x = int(win_x + event.x_root - x0)
            y = int(win_y + event.y_root - y0)
            x = min(max(x, area.x), area.x + area.width - SIZE)
            y = min(max(y, area.y), area.y + area.height - SIZE)
            self.move(x, y)
            self.pos = (x, y)
        return True

    def on_release(self, _widget, event):
        if event.button == 1 and self.drag is not None:
            clicked = not self.moved
            self.drag = None
            if clicked:
                self.click_reaction()
            elif self.near_bed():
                self.sleep_now()
                self.save()
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
            version="1.1",
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
        if isinstance(state.get("bed_x"), int):
            self.bed_x = state["bed_x"]
        if isinstance(state.get("roam"), bool):
            self.roam_enabled = state["roam"]


def main():
    GLib.set_prgname("cupcake")
    Cupcake()
    Gtk.main()


if __name__ == "__main__":
    main()
