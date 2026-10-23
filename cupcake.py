#!/usr/bin/env python3
"""Cupcake — animated pixel-art cats on your Linux desktop."""

import json
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
    return {
        "id": ident,
        "name": name,
        "anims": [
            {"name": a[0], "label": a[1], "frames": a[2], "rate": a[3]}
            for a in animations
        ],
    }


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


def asset(name):
    """Find a frame in the installed flat folder or the Xcode asset catalog."""
    for path in (ASSETS / f"{name}.png", ASSETS / f"{name}.imageset" / f"{name}.png"):
        if path.is_file():
            return path
    return None


def load_frames(character, animation):
    frames = []
    for index in range(animation["frames"]):
        path = asset(f"{index:02d}_{character['id']}_{animation['name']}")
        if path is None:
            print(f"Warning: missing frame {index} for {character['id']}/{animation['name']}")
            continue
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(path))
        except GLib.Error as error:
            print(f"Warning: cannot load {path}: {error.message}")
            continue
        frames.append(pixbuf.scale_simple(SIZE, SIZE, GdkPixbuf.InterpType.NEAREST))
    return frames


class Cupcake(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, title="Cupcake")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_accept_focus(False)
        self.set_app_paintable(True)
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        if ICON.is_file():
            self.set_icon_from_file(str(ICON))
        visual = self.get_screen().get_rgba_visual()
        if visual is not None:
            self.set_visual(visual)

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
        self.timer = None
        self.drag = None
        self.pos = None
        self.character = CHARACTERS[0]
        self.animation = self.character["anims"][0]

        self.restore()
        self.load_animation()
        self.show_all()
        self.place()
        # GNOME never displays legacy XEmbed tray icons, so skip the wasted icon.
        if "GNOME" not in os.environ.get("XDG_CURRENT_DESKTOP", "").upper():
            self.setup_tray()

    # MARK: - Animation

    def load_animation(self):
        if self.timer is not None:
            GLib.source_remove(self.timer)
            self.timer = None
        self.frames = load_frames(self.character, self.animation)
        self.frame_index = 0
        self.queue_draw()
        if len(self.frames) > 1:
            self.timer = GLib.timeout_add(
                max(16, int(self.animation["rate"] * 1000)), self.next_frame
            )

    def next_frame(self):
        self.frame_index = (self.frame_index + 1) % len(self.frames)
        self.queue_draw()
        return True

    def on_draw(self, _widget, cr):
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        if self.frames:
            Gdk.cairo_set_source_pixbuf(cr, self.frames[self.frame_index], 0, 0)
            cr.paint()
        return False

    def choose_character(self, _item, selected):
        self.character = selected
        self.animation = selected["anims"][0]
        self.load_animation()
        self.save()

    def choose_animation(self, _item, selected):
        self.animation = selected
        self.load_animation()
        self.save()

    def random_character(self, *_):
        self.character = random.choice(CHARACTERS)
        self.animation = random.choice(self.character["anims"])
        self.load_animation()
        self.save()

    def random_animation(self, *_):
        self.choose_animation(None, random.choice(self.character["anims"]))

    # MARK: - Window

    def place(self):
        display = self.get_display()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        area = monitor.get_workarea()
        if self.pos is None:
            self.pos = (
                area.x + area.width - SIZE - 32,
                area.y + area.height - SIZE - 32,
            )
        # Keep the cat reachable if a monitor was unplugged.
        x = min(max(self.pos[0], area.x), area.x + area.width - SIZE)
        y = min(max(self.pos[1], area.y), area.y + area.height - SIZE)
        self.move(x, y)

    def on_press(self, _widget, event):
        if event.button == 3:
            self.build_menu().popup_at_pointer(event)
        elif event.button == 1:
            self.drag = (event.x_root, event.y_root, *self.get_position())
        return True

    def on_motion(self, _widget, event):
        if self.drag is not None:
            x0, y0, win_x, win_y = self.drag
            self.move(
                int(win_x + event.x_root - x0),
                int(win_y + event.y_root - y0),
            )
        return True

    def on_release(self, _widget, event):
        if event.button == 1 and self.drag is not None:
            self.drag = None
            self.save()
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
            item.set_active(item_animation is self.animation)
            item.connect("activate", self.choose_animation, item_animation)
            animations_menu.append(item)
        animations_item.set_submenu(animations_menu)
        menu.append(animations_item)

        menu.append(Gtk.SeparatorMenuItem())

        random_character = Gtk.MenuItem(label="Random Character")
        random_character.connect("activate", self.random_character)
        menu.append(random_character)

        random_animation = Gtk.MenuItem(label="Random Animation")
        random_animation.connect("activate", self.random_animation)
        menu.append(random_animation)

        menu.append(Gtk.SeparatorMenuItem())

        info = Gtk.MenuItem(label=f"{self.character['name']} · {self.animation['label']}")
        info.set_sensitive(False)
        menu.append(info)

        menu.append(Gtk.SeparatorMenuItem())

        about = Gtk.MenuItem(label="About")
        about.connect("activate", self.show_about)
        menu.append(about)

        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", self.quit)
        menu.append(quit_item)

        menu.show_all()
        self.menu = menu  # keep a reference while it is open
        return menu

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
            version="1.0",
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
        if self.get_mapped():
            self.pos = self.get_position()
        x, y = self.pos if self.pos is not None else self.get_position()
        state = {
            "character": self.character["id"],
            "animation": self.animation["name"],
            "x": x,
            "y": y,
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
        self.animation = next(
            (a for a in self.character["anims"] if a["name"] == state.get("animation")),
            self.character["anims"][0],
        )
        if isinstance(state.get("x"), int) and isinstance(state.get("y"), int):
            self.pos = (state["x"], state["y"])


def main():
    GLib.set_prgname("cupcake")
    Cupcake()
    Gtk.main()


if __name__ == "__main__":
    main()
