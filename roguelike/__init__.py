from __future__ import annotations
import os
import enum
import time
import random
import logging
import dataclasses as dc
from math import ceil
from typing import Any, Callable, List, Optional, Tuple, Union

import pyglet
from pyglet.window import key

from .map import Map, Tileset
from .entity import ActionMove, Player

LOG_FORMAT = logging.Formatter("%(asctime)s [%(levelname)s]: %(message)s")#, "%Y-%m-%d %H:%M:%S")
LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.DEBUG)
TH = logging.StreamHandler()
TH.setLevel(logging.DEBUG)
TH.setFormatter(LOG_FORMAT)
LOGGER.addHandler(TH)

# add resource folder to resources, register it as font directory
DIR_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DIR_RES = os.path.join(DIR_ROOT, "res")
pyglet.font.add_directory(DIR_RES)
pyglet.resource.path = [DIR_RES]
pyglet.resource.reindex()

UPDATE_INTERVAL = 1/60


@enum.unique
class Directions(enum.Enum):
    LEFT = (-1, 0)
    LEFT_UP = (-1, 1)
    UP = (0, 1)
    RIGHT_UP = (1, 1)
    RIGHT = (1, 0)
    RIGHT_DOWN = (1, -1)
    DOWN = (0, -1)
    LEFT_DOWN = (-1, -1)


KEY_TO_DIR = {
    key.LEFT : Directions.LEFT,
    key.NUM_4: Directions.LEFT,
    key.NUM_7: Directions.LEFT_UP,
    key.UP   : Directions.UP,
    key.NUM_8: Directions.UP,
    key.NUM_9: Directions.RIGHT_UP,
    key.RIGHT: Directions.RIGHT,
    key.NUM_6: Directions.RIGHT,
    key.NUM_3: Directions.RIGHT_DOWN,
    key.DOWN : Directions.DOWN,
    key.NUM_2: Directions.DOWN,
    key.NUM_1: Directions.LEFT_DOWN,
}



class GameWindow(pyglet.window.Window): # pylint: disable=abstract-method
    """The main application class.
    Holds app state, handles input events, drawing, and update loop.
    """
    def __init__(self, *args: int, tileset: Tileset, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.grp_back = pyglet.graphics.OrderedGroup(0)
        self.grp_fore = pyglet.graphics.OrderedGroup(1)
        self.grp_ui = pyglet.graphics.OrderedGroup(2)
        self.view_target = self.width // 2, self.height // 2


        self.player = Player(pyglet.sprite.Sprite(tileset.get_image(6, 0)))
        self.gui = GUI(self)
        self.grid = Map((100, 100), self.player, self, tileset)

        self.key_handler = pyglet.window.key.KeyStateHandler()

        self.entities = self.grid.entities
        pyglet.clock.schedule_interval(self.update, UPDATE_INTERVAL)


    def update(self, delta: float) -> None:
        if not self.player.action:
            return

        action_successful = self.player.action(self, self.player)
        if not action_successful:
            return

        for entity in self.entities:
            if entity.action:
                entity.action(self, entity)


    def on_draw(self) -> None:
        self.clear()
        pyglet.gl.glLoadIdentity() # resets any applied translation matrices
        pyglet.gl.glPushMatrix() # stash the current matrix so next translation doesn't affect it
        pyglet.gl.glTranslatef(-self.view_target[0], -self.view_target[1], 0)
        self.grid.batch.draw()
        pyglet.gl.glPopMatrix() # retrieve to stashed matrix
        self.gui.batch.draw()


    def move_view(self, target: Tuple[int, int]) -> None:
        """Move the 'view' (center of the screen) to target tile."""
        abs_x, abs_y = target
        abs_x *= self.grid.tileset.tile_width
        abs_y *= self.grid.tileset.tile_height
        target_x = abs_x - (self.width // 2) + (self.grid.tileset.tile_width // 2)
        target_y = abs_y - (self.height // 2) + (self.grid.tileset.tile_height // 2)
        # view_target is a tuple of offsets from grid origin point
        self.view_target = target_x, target_y


    def on_resize(self, width: int, height: int) -> None:
        super().on_resize(width, height)
        LOGGER.debug("The window was resized to %dx%d", width, height)
        assert self.player.occupied_tile, "Player position not set!"
        self.move_view(self.player.occupied_tile)


    def on_key_press(self, symbol: int, modifiers: int) -> None:
        LOGGER.debug("Key pressed %d", symbol)
        move = KEY_TO_DIR.get(symbol)
        if move:
            move_x, move_y = move.value
            self.player.action = ActionMove(move_x, move_y)
            self.player.movement_repeat_key = symbol


    def on_key_release(self, symbol: int, modifiers: int) -> None:
        LOGGER.debug("Key released %d", symbol)
        if isinstance(self.player.action, ActionMove) and \
           self.player.movement_repeat_key == symbol:
            self.player.action = None


    def on_deactivate(self) -> None:
        pyglet.clock.unschedule(self.update)


    def on_activate(self) -> None:
        pyglet.clock.schedule_interval(self.update, UPDATE_INTERVAL)



class GUI:
    #TODO: main menu
    #TODO: in-game sidebar
    #TODO: in-game overlay menus
    def __init__(self, window: pyglet.window.Window) -> None:
        self.window = window
        self.batch = pyglet.graphics.Batch()
        self.label = pyglet.text.Label(
            text="Hello roguelike world",
            font_name="monogram",
            font_size=32,
            x=self.window.width//2 + 10, y=self.window.height-10,
            anchor_x="center", anchor_y="top",
            batch=self.batch, group=self.window.grp_ui
        )

        if __debug__:
            # emable fps and draw time measurements
            # this code will only fire when the module is ran without optimization flags
            self.fps_label = pyglet.text.Label(
                text="00.00",
                font_name="monogram",
                font_size=24,
                color=(250, 100, 100, 255),
                x=25, y=self.window.height-5,
                anchor_x="left", anchor_y="top",
                batch=self.batch, group=self.window.grp_ui
            )
            self.draw_time_label = pyglet.text.Label(
                text="00.00",
                font_name="monogram",
                font_size=24,
                color=(250, 100, 100, 255),
                x=25, y=self.fps_label.y-24-5,
                anchor_x="left", anchor_y="top",
                batch=self.batch, group=self.window.grp_ui
            )

            self.frame_times: List[float] = []
            def measure_draw_time(f: Callable) -> Callable:
                def inner(*args: Any, **kwargs: Any) -> Any:
                    t0 = time.time()
                    ret = f(*args, **kwargs)
                    self.frame_times.append(time.time() - t0)
                    return ret

                return inner


            def check_fps(_: float) -> None:
                self.fps_label.text = f"{float(pyglet.clock.get_fps()):0>4.2f} updates/s"
                if self.frame_times:
                    draw_time_ms = float(sum(self.frame_times) / len(self.frame_times)) * 1000
                    self.draw_time_label.text = f"{draw_time_ms:0>6.2f} ms/draw"
                    self.frame_times = []


            self.check_fps = check_fps
            pyglet.clock.schedule_interval(self.check_fps, .5)
            self.window.on_draw = measure_draw_time(self.window.on_draw)


    def resize(self) -> None:
        raise NotImplementedError()



def main() -> None:
    LOGGER.debug("Starting main()")
    tileset = Tileset("res/dejavu10x10_gs_tc.png", 8, 32, 2)
    window = GameWindow(960, 540, tileset=tileset, caption="roguelike", resizable=True)
    pyglet.app.run()
