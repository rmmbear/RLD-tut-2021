from __future__ import annotations
import os
import enum
import time
import random
import logging
import dataclasses as dc
from math import ceil
from typing import Any, Callable, List, Optional, Tuple, Union

import numpy as np
import pyglet
from pyglet.window import key

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

IMG_FONT_SCALE = 2
IMG_FONT = pyglet.image.ImageGrid(pyglet.image.load("res/dejavu10x10_gs_tc.png"), 8, 32)
IMG_FONT_WIDTH = 10
IMG_FONT_HEIGHT = 10
UPDATE_INTERVAL = 1/60

IMG_WALL = IMG_FONT[6, 11]
IMG_FLOOR = IMG_FONT[7, 12]
IMG_PLAYER = IMG_FONT[6, 0]

#TODO: Delay creation of tile sprites
#TODO: use a sprite pool, assign sprites to tiles as needed
#FIXME: fix coordinate issue resulting from indexing discrepency between pyglet and numpy
#   numpy  [0,0] = top left
#   pyglet [0,0] = bottom left
#

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


def random_rgb() -> Tuple[int, int, int]:
    return (
        random.randrange(0,256),
        random.randrange(0,256),
        random.randrange(0,256),
    )


class Action:
    def __call__(self, window: GameWindow, entity: Entity) -> bool:
        raise NotImplementedError()



@dc.dataclass
class ActionMove(Action):
    dx: int
    dy: int

    def __call__(self, window: GameWindow, entity: Entity) -> bool:
        assert entity.occupied_tile
        target_col, target_row = entity.occupied_tile
        target_col += self.dx
        target_row += self.dy

        if window.grid.can_move_to(entity, target_col, target_row):
            window.grid.level_grid["entity"][entity.occupied_tile[::-1]] = 0
            window.grid.place_entity(entity, target_col, target_row)
            window.move_view(entity.occupied_tile)
            return True
        else:
            LOGGER.debug("Cannot move entity '%s' to (%d,%d)", entity.name, target_col, target_row)
            return False



class ActionEsc(Action):
    def __call__(self, window: GameWindow, entity: Entity) -> bool:
        window.close()
        return True
        # ~ # pop elements from ui stack and close them until the stack is empty
        # ~ if window.ui_stack:
            # ~ ui_element = window.ui_stack.pop()
            # ~ ui_element.close()
        # ~ else:
            # ~ # when ui stack is empty (player does not have menus open, interacts
            # ~ # with the game directly) display an instance of escape menu
            # ~ # (options for leaving to menu, quitting, settings menu)
            # ~ window.gui.something



class Entity:
    def __init__(self, name: str, sprite: pyglet.sprite.Sprite):
        self.name = name
        self.sprite = sprite
        self.occupied_tile: Union[Tuple[int, int], Tuple[()]] = ()
        self.action: Optional[Action] = None


    def update(self) -> None:

        return



class Player(Entity):
    def __init__(self) -> None:
        super().__init__("player", pyglet.sprite.Sprite(IMG_PLAYER))
        self.movement_repeat_key: Optional[int] = None



@dc.dataclass(init=True, eq=False)
class TileSprite:
    x: int
    y: int
    scale: Union[float, int] = 1
    # ~ image:
    sprite: Optional[pyglet.sprite.Sprite] = None
    color_norm: Tuple[int,int,int] = (255, 255, 255) # color of the sprite when it is visible
    color_dark: Tuple[int,int,int] = (128, 128, 128) # uncovered but not visible


    def __repr__(self) -> str:
        return f"<{self.__class__} [{self.x}, {self.y}]>"


    # https://github.com/python/mypy/issues/9779
    @property # type: ignore [no-redef]
    def sprite(self) -> pyglet.sprite.Sprite: # pylint: disable=function-redefined
        if not hasattr(self, "_sprite"):
            self._sprite = None
        return self._sprite


    @sprite.setter
    def sprite(self, sprite: pyglet.sprite.Sprite) -> None:
        """Ensure proper placement when setting the sprite"""
        if sprite:
            sprite.update(x=self.x, y=self.y)
            sprite.color = self.color_norm

        self._sprite = sprite


    def activate(self) -> None:
        raise NotImplementedError()
        # fetch a matching sprite for our image from the sprite pool
        # sprite pool will decide whether to return an existing sprite or make new one


    def deactivate(self) -> None:
        raise NotImplementedError()
        # remove the sprite from this object
        # return the sprite to sprite pool


    def set_image(self, img: pyglet.image.AbstractImage) -> None:
        raise NotImplementedError()
        # deactivate the existing sprite (if any)
        # set the new image
        # if the previous sprite was activated, activate this one as well


DT_TILE_GRAPHIC = np.dtype([
        ("sprite", pyglet.sprite.Sprite),
        ("active", bool),   # whether this sprite has been initialized and can be displayed
    ]
)
DT_TILE_NAV = np.dtype([
        ("walkable", bool),          # True if this tile can be walked over
        ("transparent", bool),       # True if this tile doesn't block FOV
        ("sprite", DT_TILE_GRAPHIC), #
        ("entity", Entity),          # entity occupying the tile
    ]
)


class Map:
    def __init__(self, size: Tuple[int, int], player: Entity, window: pyglet.window.Window) -> None:
        self.window = window
        self.batch = pyglet.graphics.Batch()
        self.grp_tiles = pyglet.graphics.OrderedGroup(1, self.window.grp_fore)
        self.grp_entities = pyglet.graphics.OrderedGroup(2, self.window.grp_fore)

        self.sprite_scale = IMG_FONT_SCALE
        self.tile_width = IMG_FONT_WIDTH * IMG_FONT_SCALE
        self.tile_height = IMG_FONT_HEIGHT * IMG_FONT_SCALE

        self.level_grid = np.empty((size[1], size[0]), dtype=DT_TILE_NAV)
        self.create_grid()

        player.sprite.batch = self.batch
        player.sprite.group = self.grp_entities
        player.sprite.scale = self.sprite_scale
        self.player = player
        self.place_player()

        self.entities: List[Entity] = []
        self.create_entities()


    def create_grid(self) -> None:
        LOGGER.debug("Initializing grid")

        t0 = time.time()
        row_count, col_count = self.level_grid.shape
        for row in range(row_count):
            for col in range(col_count):
                pos_x = self.tile_width * col + 5
                pos_y = self.tile_width * row + 5
                sprite = pyglet.sprite.Sprite(
                    IMG_FLOOR, x=pos_x, y=pos_y, batch=self.batch, group=self.grp_tiles)
                tile = np.array(
                    (True, True, (sprite, False), 0),
                    dtype=DT_TILE_NAV
                )
                self.level_grid[row][col] = tile

        LOGGER.info("Init took %.4f", time.time() - t0)


    def create_entities(self) -> None:
        for i in range(10):
            rand_x = random.randrange(self.level_grid.shape[0]-1)
            rand_y = random.randrange(self.level_grid.shape[1]-1)
            sprite = pyglet.sprite.Sprite(IMG_PLAYER, batch=self.batch, group=self.grp_entities)
            sprite.scale = self.sprite_scale
            sprite.color = random_rgb()
            #sprite = Sprite(0, 0, self.sprite_scale, sprite=_sprite, color_norm=_sprite.color)
            ent = Entity(f"npc{i}", sprite)
            self.place_entity(ent, rand_x, rand_y)
            self.entities.append(ent)


    def place_player(self) -> None:
        self.place_entity(self.player, 24, 13)


    def place_entity(self, entity: Entity, col: int, row: int) -> None:
        abs_x = col * self.tile_width
        abs_y = row * self.tile_height
        LOGGER.debug("Adding entity on: grid(%s,%s) abs(%s,%s)",
                     col, row, abs_x, abs_y)

        if entity.sprite:
            entity.sprite.update(x=abs_x, y=abs_y)

        assert not self.level_grid["entity"][row][col]
        self.level_grid["entity"][row][col] = entity
        entity.occupied_tile = (col, row)


    def can_move_to(self, entity: Entity, col: int, row: int) -> bool:
        max_row, max_col = self.level_grid.shape
        if col >= max_col or row >= max_row or col < 0 or row < 0:
            LOGGER.debug("cannot move - out of bounds")
            return False

        if self.level_grid["entity"][row][col]:
            LOGGER.debug("cannot move - tile occupied")
            return False

        return True


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



class GameWindow(pyglet.window.Window): # pylint: disable=abstract-method
    """The main application class.
    Holds app state, handles input events, drawing, and update loop.
    """
    def __init__(self, *args: int, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.grp_back = pyglet.graphics.OrderedGroup(0)
        self.grp_fore = pyglet.graphics.OrderedGroup(1)
        self.grp_ui = pyglet.graphics.OrderedGroup(2)
        self.view_target = self.width // 2, self.height // 2

        self.player = Player()
        self.gui = GUI(self)
        self.grid = Map((100, 100), self.player, self)

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
        abs_x *= self.grid.tile_width
        abs_y *= self.grid.tile_height
        target_x = abs_x - (self.width // 2) + (self.grid.tile_width // 2)
        target_y = abs_y - (self.height // 2) + (self.grid.tile_height // 2)
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
            self.player.action = ActionMove(*move.value)
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



def main() -> None:
    LOGGER.debug("Starting main()")
    window = GameWindow(960, 540, caption="roguelike", resizable=True)
    pyglet.app.run()
