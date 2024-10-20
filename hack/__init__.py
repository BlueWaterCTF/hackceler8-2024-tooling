import functools
import itertools
import json
import math
import sys
import threading
import os
import time
from datetime import datetime
from typing import Any

from game.engine import gfx
from moderngl_window.context.base import KeyModifiers

from game.engine.gfx import BaseDrawParams, IterableParams


def inject_class(cls):
    assert len(cls.__bases__) == 1
    hacked_cls = cls.__bases__[0]
    for subclass in hacked_cls.__subclasses__():
        if subclass is not cls:
            assert len(subclass.__bases__) == 1
            subclass.__bases__ = (cls,)
    setattr(sys.modules[hacked_cls.__module__], hacked_cls.__name__, cls)
    cls.__name__ = hacked_cls.__name__
    return cls


gui_obj: 'HackedHackceler8' = None


# toolbox window
class Toolbox:
    SAVE_LOC = 'replays'

    def __init__(self):
        autosave_loc = os.path.join(Toolbox.SAVE_LOC, 'autosave')
        os.makedirs(autosave_loc, exist_ok=True)
        self.save_file = open(
            os.path.join(autosave_loc, f'{datetime.now().strftime("%d-%H-%M-%S-%f")}.jsonl'), 'wb')

        self.is_sim = False
        self.__game_snapshot = None
        self.__snapshot_index = 0
        self.__sub_msgs = []
        self.__unsub_msgs = []
        self.pending_replays = []
        self.replay_realtime = True
        self.window = None
        self.should_show_extra_info = False

        self.lock = threading.Lock()

        self.thread = threading.Thread(target=self.__start_window, daemon=True)
        self.thread.start()

    def has_pending_unsub(self):
        return len(self.__unsub_msgs) > 0

    def set_snapshot(self, snapshot):
        assert self.__game_snapshot is None and snapshot is not None
        self.__game_snapshot = snapshot

    def enqueue_msg(self, msg):
        if not self.is_sim:
            loc = self.save_file.tell()
            self.save_file.write(msg)
            self.save_file.write(b'\n')
            self.__sub_msgs.append((loc, msg))
            self.window.counter.set_tick(len(self.__sub_msgs))
            return True

        assert self.__game_snapshot is not None
        snapshot, self.__game_snapshot = self.__game_snapshot, None

        if self.__snapshot_index != len(self.__unsub_msgs):
            loc = self.__unsub_msgs[self.__snapshot_index][0]
            self.__unsub_msgs = self.__unsub_msgs[:self.__snapshot_index]

            self.save_file.truncate(loc)
            self.save_file.seek(loc, 0)
        else:
            loc = self.save_file.tell()

        self.save_file.write(msg)
        self.save_file.write(b'\n')

        self.__unsub_msgs.append((loc, snapshot, msg))
        self.__snapshot_index = len(self.__unsub_msgs)

        self.window.counter.set_tick(len(self.__sub_msgs), self.__snapshot_index, len(self.__unsub_msgs))

    def undo_one(self):
        if self.__snapshot_index <= 0:
            return
        self.__snapshot_index -= 1
        self.window.counter.set_tick(len(self.__sub_msgs), self.__snapshot_index, len(self.__unsub_msgs))
        return self.__unsub_msgs[self.__snapshot_index][1]

    def redo_one(self):
        if self.__snapshot_index + 1 >= len(self.__unsub_msgs):
            return
        self.__snapshot_index += 1
        self.window.counter.set_tick(len(self.__sub_msgs), self.__snapshot_index, len(self.__unsub_msgs))
        return self.__unsub_msgs[self.__snapshot_index][1]

    def save_messages(self):
        filename = self.window.save.input.text().strip()
        if filename:
            filename += f'.{datetime.now().strftime("%d-%H-%M-%S-%f")}.jsonl'
        else:
            filename = f'{datetime.now().strftime("%d-%H-%M-%S-%f")}.jsonl'

        with open(os.path.join(Toolbox.SAVE_LOC, filename), 'wb') as f:
            for _, msg in self.__sub_msgs:
                f.write(msg)
                f.write(b'\n')
            for _, _, msg in self.__unsub_msgs[:self.__snapshot_index]:
                f.write(msg)
                f.write(b'\n')

    def submit_unsubs(self):
        buf = self.__unsub_msgs[:self.__snapshot_index]

        ret = []
        for loc, _, msg in buf:
            ret.append(msg)
            self.__sub_msgs.append((loc, msg))

        self.__unsub_msgs = self.__unsub_msgs[self.__snapshot_index:]
        self.__snapshot_index = 0
        self.window.counter.set_tick(len(self.__sub_msgs), 0, len(self.__unsub_msgs))

        return ret

    def replay(self, realtime):
        if self.pending_replays:
            return
        if self.is_sim:
            return
        current = self.window.replay.list.currentItem()
        if current is None:
            return
        replays = []
        with open(os.path.join(Toolbox.SAVE_LOC, current.text() + '.jsonl'), 'rb') as f:
            for l in f:
                replays.append(json.loads(l))
        if self.__sub_msgs:
            _, last_msg = self.__sub_msgs[-1]
            last_msg = json.loads(last_msg)
            last_state = last_msg['state']
            while replays:
                top = replays.pop(0)
                if top['state'] == last_state:
                    break
        self.pending_replays = replays
        self.replay_realtime = realtime

    def stop_replay(self):
        self.pending_replays = []

    def __start_window(self):
        from hack.toolbox_gui import ToolboxWidget
        from PySide6 import QtWidgets

        app = QtWidgets.QApplication()
        self.window = ToolboxWidget()

        # connections
        self.window.save.save_button.clicked.connect(self.save_messages)

        self.window.play.stopReplay.connect(self.stop_replay)
        self.window.play.speed_txt.valueChanged.connect(self.speed_update)
        self.speed_update(self.window.play.speed_txt.value())
        self.window.replay.btns.btn1.clicked.connect(functools.partial(self.replay, realtime=True))
        self.window.replay.btns.btn2.clicked.connect(functools.partial(self.replay, realtime=False))
        self.window.replay.set_args(self.save_file.name.removeprefix(Toolbox.SAVE_LOC)[1:], Toolbox.SAVE_LOC)
        self.window.counter.sim_mode.toggled.connect(self.__set_sim)

        app.exec()

    @property
    def play_state(self):
        return self.window.play.state

    def set_play_state(self, state):
        self.window.play.set_state(state)

    def speed_update(self, speed):
        import game.engine.gfx

        game.engine.gfx.TICKRATE = 60 * speed

    def __set_sim(self, checked):
        with self.lock:
            if checked:
                self.is_sim = True
                self.window.counter.set_tick(len(self.__sub_msgs), 0, 0)
                return

            assert self.__snapshot_index == 0
            self.is_sim = False
            self.__unsub_msgs = []
            self.window.counter.set_tick(len(self.__sub_msgs))

    def toggle_sim(self):
        if self.is_sim:
            if self.__snapshot_index == 0:
                self.window.counter.sim_mode.setChecked(False)
        else:
            self.window.counter.sim_mode.setChecked(True)
    
def get_clipboard_text():
    from PySide6 import QtGui
    return QtGui.QGuiApplication.clipboard().text()

def set_clipboard_text(t):
    from PySide6 import QtGui
    QtGui.QGuiApplication.clipboard().setText(t)


toolbox = Toolbox()

# game.engine.gfx
import game.engine.gfx

from pyrr import Matrix44


@inject_class
class HackedCamera(game.engine.gfx.Camera):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.scale = 1
        self.init_w = self.viewport_width
        self.init_h = self.viewport_height

    def set_scale(self, scale):
        if scale <= 1e-6:
            return
        self.scale = scale
        self.viewport_width = self.init_w * self.scale
        self.viewport_height = self.init_h * self.scale
        self.projection_matrix = Matrix44.orthogonal_projection(0, self.viewport_width, 0, self.viewport_height, -1, 1)


# game.engine.generics
import game.engine.generics
import game.components.wall
import game.engine.modifier


@inject_class
class HackedGenericComponents(game.engine.generics.GenericObject):
    def get_draw_info(self) -> game.engine.gfx.IterableParams:
        info = super().get_draw_info()
        # if not self.blocking:
        #     return info
        hitbox = [game.engine.gfx.ShapeDrawParams(
            x=self.get_leftmost_point(), xr=self.get_rightmost_point(),
            y=self.get_lowest_point(), yt=self.get_highest_point(),
            color=(255, 0, 255, 255), flags=game.engine.gfx.Flags.OUTLINE.value,
            border_width=1.5, above_sprite=True,
        )]
        if self.get_width() <= 5 or self.get_height() <= 5:
            hitbox.append(game.engine.gfx.ShapeDrawParams(
                x=self.get_leftmost_point() - 5, xr=self.get_rightmost_point() + 5,
                y=self.get_lowest_point() - 5, yt=self.get_highest_point() + 5,
                color=(200, 200, 200, 255), flags=game.engine.gfx.Flags.OUTLINE.value,
                border_width=1.5, above_sprite=True,
            ))

        if not isinstance(self, game.components.wall.Wall):
            name = self.__class__.__name__
            fro_x, fro_y = gui_obj.game_coord_to_window_viewport(self.get_leftmost_point(), self.get_highest_point())
            text_color = (0, 1, 0, 1)
            # Highlight some names
            NAME_COLORS = {
                'NPC': (254.0 / 255.0, 228.0 / 255.0, 64.0 / 255.0, 1),
                'Enemy': (1, 89.0 / 255.0, 94.0 / 255.0, 1),
            }
            if self.nametype in NAME_COLORS:
                text_color = NAME_COLORS[self.nametype]
            draw_list = imgui.get_background_draw_list()
            draw_list.add_text_with_font_size(
                fro_x, fro_y - 30, imgui.get_color_u32_rgba(*text_color),
                name, gui_obj.scale_imgui(15))
            if self.name:
                draw_list.add_text_with_font_size(
                    fro_x, fro_y - 15, imgui.get_color_u32_rgba(*text_color),
                    self.name, gui_obj.scale_imgui(15))

        if isinstance(self.modifier, game.engine.modifier.Modifier):
            if self.__class__.__name__ == "HealthIncreaser":
                color = (0, 255, 0, 255)
            else:
                color = (255, 0, 0, 255)
            hitbox.append(game.engine.gfx.circle_outline(self.x, self.y, self.modifier.min_distance, color, 1))

        connections = {
            'Item': (0, 1, 0, 1),
            'KeyGate': (0, 1, 1, 1),
            'Portal': (0, 0, 1, 1),
            'Warp': (17.0 / 255.0, 138.0 / 255.0, 178.0 / 255.0, 1),
            'BossGate': (1, 0, 1, 1),
            'Fountain': (0, 1, 0, 1),
        }

        if toolbox.should_show_extra_info:
            connections['Gem'] = (0.5, 0.5, 0.5, 1)

        if self.__class__.__name__ in connections:
            fro_x, fro_y = gui_obj.game_coord_to_window_viewport(self.x, self.y)
            to_x, to_y = gui_obj.game_coord_to_window_viewport(gui_obj.game.player.x, gui_obj.game.player.y)
            draw_list = imgui.get_background_draw_list()
            draw_list.add_line(fro_x, fro_y, to_x, to_y,
                               imgui.get_color_u32_rgba(*connections[self.__class__.__name__]), gui_obj.scale_imgui(1))

        if 'Npc' in self.__class__.__name__:
            fro_x, fro_y = gui_obj.game_coord_to_window_viewport(self.x, self.y)
            to_x, to_y = gui_obj.game_coord_to_window_viewport(gui_obj.game.player.x, gui_obj.game.player.y)
            draw_list = imgui.get_background_draw_list()
            draw_list.add_line(
                fro_x, fro_y, to_x, to_y,
                imgui.get_color_u32_rgba(255.0 / 255.0, 228.0 / 255.0, 64.0 / 255.0, 1), gui_obj.scale_imgui(1))

        return itertools.chain(info, hitbox)


# game.components.projectile
import game.components.projectile


@inject_class
class HackedProjectile(game.components.projectile.Projectile):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__init_x = self.x
        self.__init_y = self.y

    def get_draw_info(self):
        info = super().get_draw_info()

        fro_x, fro_y = gui_obj.game_coord_to_window_viewport(self.__init_x, self.__init_y)
        to_x, to_y = gui_obj.game_coord_to_window_viewport(self.x + self.x_speed * 10, self.y + self.y_speed * 10)

        color = imgui.get_color_u32_rgba(1, 0, 0, 1)
        draw_list = imgui.get_background_draw_list()
        draw_list.add_line(fro_x, fro_y, to_x, to_y, color, gui_obj.scale_imgui(2))

        return info


# game.components.portal
import game.components.portal


@inject_class
class HackedPortal(game.components.portal.Portal):
    def get_draw_info(self):
        old_visible = self.visible
        self.visible = True
        info = super().get_draw_info()
        self.visible = old_visible

        fro_x, fro_y = gui_obj.game_coord_to_window_viewport(self.x, self.y)
        to_x, to_y = gui_obj.game_coord_to_window_viewport(self.dest.x, self.dest.y)

        draw_list = imgui.get_background_draw_list()

        color = imgui.get_color_u32_rgba(1, 1, 0, 1)
        draw_list.add_line(fro_x, fro_y, to_x, to_y, color, gui_obj.scale_imgui(1))

        if self.usage_limit is not None:
            if self.usage_count >= self.usage_limit:
                color = imgui.get_color_u32_rgba(1, 0, 0, 1)
            draw_list.add_text_with_font_size(
                fro_x, fro_y, color, f'{self.usage_count}/{self.usage_limit}', gui_obj.scale_imgui(20))

        return info


# game.components.warp
import game.components.warp


@inject_class
class HackedWarp(game.components.warp.Warp):
    def get_draw_info(self):
        info = super().get_draw_info()

        if gui_obj.game is not None:
            fro_x, fro_y = gui_obj.game_coord_to_window_viewport(self.x, self.y)
            target = self.map_name if gui_obj.game.current_map == "base" else "base"
            color = imgui.get_color_u32_rgba(1, 1, 0, 1)
            draw_list = imgui.get_background_draw_list()
            draw_list.add_text_with_font_size(fro_x, fro_y, color, target, gui_obj.scale_imgui(20))

        return info


# game.components.bullet
import game.components.boss.bullet


@inject_class
class HackedBullet(game.components.boss.bullet.Bullet):
    def get_draw_info(self):
        info = super().get_draw_info()
        hitbox = [
            game.engine.gfx.ShapeDrawParams(
                x=self.x - self.hitbox_w * 0.5, xr=self.x + self.hitbox_w * 0.5,
                y=self.y - self.hitbox_w * 0.5, yt=self.y + self.hitbox_w * 0.5,
                color=(255, 0, 0, 255), flags=game.engine.gfx.Flags.OUTLINE.value,
                border_width=1.5, above_sprite=True,
            )
        ]
        return itertools.chain(info, hitbox)


# game.engine.screen_fader
import game.engine.screen_fader


@inject_class
class HackedScreenFader(game.engine.screen_fader.ScreenFader):
    def draw(self):
        return


# game.venator
import game.venator
import imgui

# game.components.weapon
import game.components.weapon.weapon


@inject_class
class HackedWeapon(game.components.weapon.weapon.Weapon):
    def get_draw_info(self):
        info = super().get_draw_info()
        if self.cool_down_timer <= 0:
            return info
        hitbox = [game.engine.gfx.circle_filled(
            x=self.x, y=self.y, radius=self.cool_down_timer * 5 * gui_obj.scale,
            color=(0, 255, 100, 200),
        )]
        return itertools.chain(info, hitbox)


class FakeNet:
    def __init__(self, real_net):
        self.real_net = real_net

    def send_one(self, msg):
        if not toolbox.enqueue_msg(msg):
            return
        if self.real_net is not None:
            self.real_net.send_one(msg)


@inject_class
class HackedVenator(game.venator.Venator):
    def send_game_info(self):
        net_old = self.net
        try:
            self.net = FakeNet(net_old)
            super().send_game_info()
        finally:
            self.net = net_old


# game.components.enemy
import game.components.enemy.enemy


@inject_class
class HackedEnemy(game.components.enemy.enemy.Enemy):
    def get_draw_info(self):
        info = super().get_draw_info()

        if self.dead:
            return info

        self.game = gui_obj.game
        hitbox = []

        if self.can_melee or self.can_shoot:
            x = abs(self.x - gui_obj.game.player.x)
            y = abs(self.y - gui_obj.game.player.y)
            if x * x + y * y < 800 * 800:
                alpha = self.shoot_timer * 255 // 120
                if self._sees_player():
                    color = (255, 0, 0, alpha)
                elif (self.x - gui_obj.game.player.x > 0) == self.sprite.flipped:
                    color = (255, 255, 0, alpha)
                else:
                    color = (0, 255, 0, alpha)
                hitbox.append(game.engine.gfx.circle_filled(
                    self.x, self.y, 400, color
                ))

        if self.can_melee:
            if self._sees_player():
                color = (255, 0, 0, 255)
            else:
                color = (255, 255, 0, 255)
            hitbox.append(game.engine.gfx.ShapeDrawParams(
                x=self.x - self.melee_range, xr=self.x + self.melee_range,
                y=self.y - self.melee_range, yt=self.y + self.melee_range,
                color=color, flags=game.engine.gfx.Flags.OUTLINE.value,
                border_width=1.5, above_sprite=True,
            ))
        return itertools.chain(info, hitbox)


# game.venator_gui
import game.venator_gui
import game.components.items

from game.engine.keys import Keys

from hack.backup import GameBackup


@inject_class
class HackedHackceler8(game.venator_gui.Hackceler8):
    vsync = False
    title = game.venator_gui.Hackceler8.title + ' [\U0001f4a6 Blue Water]'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        global gui_obj
        gui_obj = self

        toolbox.window.unfocus_func = self.wnd._window.activate
        self.loading_screen_timer = 1
        self.__is_camera_following = True
        self.__key_pressing = set()
        self.__mouse_pos = (0, 0)
        self.__last_ticked = None

        self.imgui_io.get_clipboard_text_fn = get_clipboard_text
        self.imgui_io.set_clipboard_text_fn = set_clipboard_text

    def __pre_tick(self, *args, **kwargs):
        with toolbox.lock:
            if toolbox.is_sim:
                toolbox.set_snapshot(GameBackup.generate_snapshot(self.game))
            super().tick(*args, **kwargs)

    def __game_waiting_server(self):
        return self.game.waiting_for_server_txt or self.game.module_reloading

    def scale_imgui(self, size):
        return size * self.scale / self.camera.scale

    def draw(self):
        if self.game is not None and self.__game_waiting_server():
            draw_list = imgui.get_overlay_draw_list()
            if toolbox.has_pending_unsub():
                draw_list.add_text_with_font_size(
                    0, 0, imgui.get_color_u32_rgba(1, 0, 0, 1),
                    'Press B to sync with server', 50 * self.scale)
            else:
                draw_list.add_text_with_font_size(
                    0, 0, imgui.get_color_u32_rgba(1, 1, 0, 1),
                    'Waiting sync with the server', 50 * self.scale)
        # Draw top left extra info if enabled
        if self.game is not None and self.game.current_map is not None and toolbox.should_show_extra_info:
            draw_list = imgui.get_overlay_draw_list()
            if self._white_text():
                text_color = (1, 1, 1, 1)
            else:
                text_color = (0, 0, 0, 1)
            text_font_size = 20
            npcs = [o.name for o in self.game.objects if o.nametype == "NPC"]
            starting_y = 30
            y_offset = text_font_size + 5
            rows_to_display = []
            if len(npcs) > 0:
                rows_to_display.append('NPC({0}): {1}'.format(len(npcs), npcs))
            items = [o.display_name for o in self.game.objects if o.nametype == "Item"]
            if len(items) > 0:
                rows_to_display.append('Items({0}): {1}'.format(len(items), items))
            weapons = [o.get("type") for o in self.game.tiled_map.weapons]
            if len(weapons) > 0:
                rows_to_display.append('Weapons({0}): {1}, has: {2}, equipped: {3}'.format(
                    len(weapons),
                    weapons,
                    [w.display_name for w in self.game.player.weapons],
                    [w.display_name for w in filter(lambda x: x.equipped, self.game.player.weapons)]))
            if hasattr(self.game, 'gem_collection'):
                gems = [o.name for o in self.game.objects if o.nametype == "gem"]
                text = 'Gems({0}): '.format(len(gems))
                text_parts = []
                if hasattr(self.game.gem_collection, 'count_all_gems'):
                    text_parts.append('count_all_gems: {0}'.format(self.game.gem_collection.count_all_gems()))
                if hasattr(self.game.gem_collection, 'gems'):
                    text_parts.append('len(gems) - 1(root): {0}'.format(len(self.game.gem_collection.gems) - 1))
                text += ', '.join(text_parts)
                rows_to_display.append(text)

            for row in rows_to_display:
                draw_list.add_text_with_font_size(
                    30, starting_y, imgui.get_color_u32_rgba(*text_color),
                    row, text_font_size)
                starting_y += y_offset

        super().draw()

    def tick(self, *args, **kwargs):
        if self.game is None:
            if self.loading_screen_timer > 0:
                self.loading_screen_timer -= 1
                return
            self.setup_game()
            if hasattr(self.argv, 'extra_items') and self.argv.extra_items:
                for d in self.argv.extra_items:
                    if not any([i["display_name"] == d for i in self.game.items]):
                        it = game.components.items.Item(None, game.components.items.display_to_name(d), d)
                        it.collected_time = 1
                        self.game.items.append(it)

        if not self.game.ready:
            return

        if self.boss_bg is None:
            if self.game.current_map.endswith("_boss"):
                self.boss_bg = game.venator_gui.BossBG()
        else:
            if not self.game.current_map.endswith("_boss"):
                self.boss_bg = None
        self._center_camera_to_player()

        if toolbox.is_sim:
            if self.wnd.keys.Z in self.__key_pressing:
                while True:
                    top = toolbox.undo_one()
                    if top is None:
                        return
                    self.game = GameBackup.inflate_snapshot(top)
                    assert not self.__game_waiting_server()
                    if self.game.screen_fader is None:
                        return

            if self.wnd.keys.X in self.__key_pressing:
                while True:
                    top = toolbox.redo_one()
                    if top is None:
                        return
                    self.game = GameBackup.inflate_snapshot(top)
                    if self.game.screen_fader is None:
                        return

        if self.__game_waiting_server():
            self.game.recv_from_server()
            return

        if not self.game.map_loaded:
            self.game.map_loaded = True
            self.game.setup()

        toolbox.window.show_async()

        if toolbox.pending_replays:
            toolbox.set_play_state('replay')

            if toolbox.replay_realtime:
                lag = 1

                now = time.time()
                if self.__last_ticked is not None:
                    lag = math.ceil((now - self.__last_ticked) * game.engine.gfx.TICKRATE)
                self.__last_ticked = now

                for _ in range(lag):
                    top = toolbox.pending_replays.pop(0)
                    self.game.raw_pressed_keys = set((Keys.from_serialized(k) for k in top['keys']))
                    self.__pre_tick(*args, **kwargs)
                    if not toolbox.pending_replays or self.__game_waiting_server():
                        break
            else:
                self.__last_ticked = None
                while toolbox.pending_replays:
                    top = toolbox.pending_replays.pop(0)
                    self.game.raw_pressed_keys = set((Keys.from_serialized(k) for k in top['keys']))
                    self.__pre_tick(*args, **kwargs)
                    if self.__game_waiting_server():
                        return

            return

        if self.game.player is not None and (self.game.player.stamina <= 0 or (
                self.wnd.keys.A not in self.__key_pressing and self.wnd.keys.D not in self.__key_pressing)):
            self.game.raw_pressed_keys.discard(Keys.LSHIFT)
        else:
            if self.wnd.keys.LEFT_SHIFT in self.__key_pressing:
                self.game.raw_pressed_keys.add(Keys.LSHIFT)

        if self.game.screen_fader is not None:
            self.game.raw_pressed_keys.clear()
            while self.game.screen_fader is not None:
                if self.__game_waiting_server():
                    return
                self.__pre_tick(*args, **kwargs)

        match toolbox.play_state:
            case 'replay':
                self.game.raw_pressed_keys = set()
                toolbox.set_play_state('pause')
                return
            case 'play':
                pass
            case 'pause':
                if len(self.game.tracked_keys & self.game.raw_pressed_keys) == 0:
                    return
                toolbox.set_play_state('step')
            case 'step':
                if len(self.game.tracked_keys & self.game.raw_pressed_keys) == 0:
                    toolbox.set_play_state('pause')
                    return

        self.__pre_tick(*args, **kwargs)

    def key_event(self, key: Any, action: Any, modifiers: KeyModifiers):
        self.imgui_io.key_ctrl = modifiers.ctrl
        super().key_event(key, action, modifiers)

    def on_key_press(self, symbol: int, modifiers: KeyModifiers):
        match symbol:
            case _:
                self.__key_pressing.add(symbol)
                if Keys.from_ui(symbol) in self.game.tracked_keys and not toolbox.pending_replays:
                    super().on_key_press(symbol, modifiers)

    def on_key_release(self, symbol: int, modifiers: KeyModifiers):
        match symbol:
            case self.wnd.keys.B:
                if toolbox.is_sim:
                    unsubs = toolbox.submit_unsubs()
                    if self.net is not None:
                        for u in unsubs:
                            self.net.send_one(u)
            case self.wnd.keys.K:
                toolbox.toggle_sim()
            case self.wnd.keys.COMMA:
                toolbox.window.play.speed.step(-1)
            case self.wnd.keys.PERIOD:
                toolbox.window.play.speed.step(1)
            case self.wnd.keys.C:
                if not self.__is_camera_following:
                    self.__is_camera_following = True
                elif self.camera.scale != 1:
                    x = self.camera.position.x + self.camera.viewport_width / 2
                    y = self.camera.position.y + self.camera.viewport_height / 2
                    self.camera.set_scale(1)
                    self.camera.position.x = x - self.camera.viewport_width / 2
                    self.camera.position.y = y - self.camera.viewport_height / 2
                    self.camera.update()
            case self.wnd.keys.H:
                toolbox.should_show_extra_info = not toolbox.should_show_extra_info
            case _:
                self.__key_pressing.discard(symbol)
                if Keys.from_ui(symbol) in self.game.tracked_keys and not toolbox.pending_replays:
                    super().on_key_release(symbol, modifiers)

    def window_to_game_coord(self, x, y):
        actual_x = self.camera.position.x + x / self.wnd.width * self.camera.viewport_width
        actual_y = self.camera.position.y + (1 - y / self.wnd.height) * self.camera.viewport_height
        return actual_x, actual_y

    def game_coord_to_window_viewport(self, actual_x, actual_y):
        w, h = self.wnd.viewport_size
        x = (actual_x - self.camera.position.x) / self.camera.viewport_width * w
        y = (1 - (actual_y - self.camera.position.y) / self.camera.viewport_height) * h
        return x, y

    def mouse_position_event(self, x, y, dx, dy):
        self.__mouse_pos = (x, y)

    def mouse_scroll_event(self, x_offset, y_offset):
        diff = y_offset / 6
        if self.wnd.keys.LEFT_CTRL in self.__key_pressing:
            diff *= 2
        self.camera.set_scale(self.camera.scale + diff)

        if self.__is_camera_following:
            self._center_camera_to_player()
        else:
            x, y = self.__mouse_pos
            self.camera.position.x -= x / self.wnd.width * self.camera.init_w * diff
            self.camera.position.y -= (1 - y / self.wnd.height) * self.camera.init_h * diff
            self.camera.update()

    def mouse_drag_event(self, x, y, dx, dy):
        if self.wnd.mouse_states.right:
            self.__is_camera_following = False
            scale = self.camera.scale / self.wnd.width * self.camera.init_w
            if self.wnd.keys.LEFT_CTRL in self.__key_pressing:
                scale *= 2
            self.camera.position.x -= dx * scale
            self.camera.position.y += dy * scale
            self.camera.update()

    def _center_camera_to_player(self):
        if self.game.player is not None and self.__is_camera_following:
            self.camera.position.x = self.game.player.x - self.camera.viewport_width / 2
            self.camera.position.y = self.game.player.y - self.camera.viewport_height / 2
            self.camera.update()


import atexit
atexit.register(lambda: os._exit(0))