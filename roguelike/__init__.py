import os
import enum
import time
import random
import logging
import dataclasses as dc
from math import ceil
from typing import Any, List, Optional, Tuple, Union

import numpy
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

IMG_WALL = IMG_FONT[5, 10]
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
        random.randrange(0,256)
    )


class Entity:
    def __init__(self, name: str, sprite: pyglet.sprite.Sprite):
        self.name = name
        self.sprite = sprite
        self.occupied_tile: Optional[Tile] = None
        self.planned_move: Union[Tuple[Directions, int], Tuple] = ()
        #indices: 0 = Directions.DIRECTION, 1 = key symbol


    def update(self) -> Optional[Directions]:
        if self.planned_move and self.occupied_tile:
            direction = self.planned_move[0]
            moved = self.occupied_tile.move_entity(direction)
            if not moved:
                self.planned_move = ()
            else:
                return direction

        return None



@dc.dataclass(init=True, eq=False)
class Tile:
    grid_x: int
    grid_y: int
    abs_x: int
    abs_y: int
    map_grid: numpy.ndarray
    sprite: Optional[pyglet.sprite.Sprite] = None
    entity: Optional[Entity] = None


    def __repr__(self) -> str:
        return f"<Tile [{self.grid_x}, {self.grid_y}] at xy: ({self.abs_x},{self.abs_y})>"


    # https://github.com/python/mypy/issues/9779
    @property # type: ignore [no-redef]
    def sprite(self) -> pyglet.sprite.Sprite: # pylint: disable=function-redefined
        if not hasattr(self, "_sprite"):
            self._sprite = None
        return self._sprite


    @sprite.setter
    def sprite(self, sprite: pyglet.sprite.Sprite) -> None:
        """Ensure proper placement and anchoring."""
        if sprite:
            sprite.update(x=self.abs_x, y=self.abs_y)
            sprite.color = (
                int(self.grid_x / self.map_grid.shape[1] * 255),
                int(self.grid_y / self.map_grid.shape[0] * 255),
                255)
        self._sprite = sprite


    def add_entity(self, entity: Entity) -> None:
        LOGGER.debug("Adding entity on: grid(%s,%s) abs(%s,%s)",
                     self.grid_x, self.grid_y, self.abs_x, self.abs_y)

        if entity.sprite:
            entity.sprite.update(x=self.abs_x, y=self.abs_y)

        entity.occupied_tile = self
        self.entity = entity


    def move_entity(self, direction: Directions) -> bool:
        assert self.entity, "This tile has no entity on it!"
        assert self.entity.planned_move[0] == direction

        target_grid_x = self.grid_x + direction.value[0]
        target_grid_y = self.grid_y + direction.value[1]

        max_y, max_x = self.map_grid.shape
        if not 0 <= target_grid_x < max_x or not 0 <= target_grid_y < max_y:
            LOGGER.debug("%s at edge of grid", self.entity.name)
            return False

        target_tile = self.map_grid[target_grid_y, target_grid_x]
        if target_tile.can_move_here(self.entity):
            target_tile.add_entity(self.entity)
            self.entity.occupied_tile = target_tile
            self.entity = None
            return True

        LOGGER.debug("%s cannot move to %s", self.entity.name, self.__repr__())
        return False


    def can_move_here(self, entity: Entity) -> bool:
        if self.entity:
            return False

        return True



class Map:
    def __init__(self, size: Tuple[int, int], window: pyglet.window.Window) -> None:
        self.window = window
        self.batch = pyglet.graphics.Batch()
        self.grp_tiles = pyglet.graphics.OrderedGroup(1, self.window.grp_foreground)
        self.grp_entities = pyglet.graphics.OrderedGroup(2, self.window.grp_foreground)

        self.sprite_scale = IMG_FONT_SCALE
        self.tile_width = IMG_FONT_WIDTH * IMG_FONT_SCALE
        self.tile_height = IMG_FONT_HEIGHT * IMG_FONT_SCALE

        self.level_grid_cols, self.level_grid_rows = size
        self.level_grid = numpy.empty((self.level_grid_rows, self.level_grid_cols), dtype=Tile)

        LOGGER.debug("Initializing grid")
        t0 = time.time()
        for row, row_arr in enumerate(self.level_grid):
            for col, _ in enumerate(row_arr):
                pos_x = self.tile_width * col + 5
                pos_y = self.tile_width * row + 5
                #XXX:creating sprite for every tile pre-emptively is a waste of resources
                sprite = pyglet.sprite.Sprite(IMG_WALL, batch=self.batch, group=self.grp_tiles)
                sprite.scale=self.sprite_scale
                row_arr[col] = Tile(abs_x=pos_x, abs_y=pos_y, grid_x=col, grid_y=row,
                                    map_grid=self.level_grid, sprite=sprite)

        LOGGER.info("Init took %.4f", time.time() - t0)

        player_sprite = pyglet.sprite.Sprite(
            IMG_PLAYER, batch=self.batch, group=self.grp_entities)
        player_sprite.scale = self.sprite_scale
        self.player = Entity("player", player_sprite)
        self.level_grid[13, 24].add_entity(self.player)
        self.move_view(self.player.occupied_tile)
        self.active_entities: List[Entity] = []

        for i in range(10):
            rand_x = random.randrange(49)
            rand_y = random.randrange(28)
            sprite = pyglet.sprite.Sprite(
                IMG_PLAYER, batch=self.batch, group=self.grp_entities)
            sprite.scale = self.sprite_scale
            sprite.color = random_rgb()
            ent = Entity(f"npc{i}", sprite)
            self.level_grid[rand_y][rand_x].add_entity(ent)
            self.active_entities.append(ent)

        pyglet.clock.schedule_interval(self.update, UPDATE_INTERVAL)


    def update(self, delta: float) -> None:
        if self.player.occupied_tile:
            moved = self.player.update()
            if moved and self.player.occupied_tile:
                self.move_view(self.player.occupied_tile)

        for entity in self.active_entities:
            entity.update()


    def on_key_press(self, symbol: int, modifiers: int) -> None:
        LOGGER.debug("Key pressed %d", symbol)
        move = KEY_TO_DIR.get(symbol)
        if move:
            self.player.planned_move = (move, symbol)


    def on_key_release(self, symbol: int, modifiers: int) -> None:
        LOGGER.debug("Key released %d", symbol)
        if self.player.planned_move and self.player.planned_move[1] == symbol:
            self.player.planned_move = ()


    def move_view(self, target: Tile) -> None:
        """Move the 'view' (center of the screen) to target tile."""
        target_x = target.abs_x - (self.window.width // 2) + (self.tile_width // 2)
        target_y = target.abs_y - (self.window.height // 2) + (self.tile_height // 2)
        # view_target is a tuple of offsets from grid origin point
        self.window.view_target = target_x, target_y



class GameController:
    ...



class GameWindow(pyglet.window.Window): # pylint: disable=abstract-method
    def __init__(self) -> None:
        super().__init__(960, 540, caption="roguelike", resizable=True)
        self.init_width = self.width
        self.init_height = self.height
        self.batch = pyglet.graphics.Batch()
        self.grp_background = pyglet.graphics.OrderedGroup(0)
        self.grp_foreground = pyglet.graphics.OrderedGroup(1)
        self.grp_interface = pyglet.graphics.OrderedGroup(2)
        self.view_target = self.width // 2, self.height // 2
        self.view_offset = (0,0)

        self.label = pyglet.text.Label(
            text="Hello roguelike world",
            font_name="monogram",
            font_size=32,
            x=self.width//2 + 10, y=self.height-10,
            anchor_x="center", anchor_y="top",
            batch=self.batch, group=self.grp_interface
        )

        self.fps_label = pyglet.text.Label(
            text="00.00",
            font_name="monogram",
            font_size=24,
            color=(250, 100, 100, 255),
            x=25, y=self.height-5,
            anchor_x="left", anchor_y="top",
            batch=self.batch, group=self.grp_interface
        )
        self.draw_time_label = pyglet.text.Label(
            text="00.00",
            font_name="monogram",
            font_size=24,
            color=(250, 100, 100, 255),
            x=25, y=self.fps_label.y-24-5,
            anchor_x="left", anchor_y="top",
            batch=self.batch, group=self.grp_interface
        )

        self.grid = Map((100, 100), self)
        self.push_handlers(self.grid)
        pyglet.clock.schedule_interval(self.check_fps, .5)
        self.frame_times: List[float] = []


    def check_fps(self, delta: int) -> None:
        self.fps_label.text = f"{float(pyglet.clock.get_fps()):0>4.2f} updates/s"
        self.draw_time_label.text = f"{float(sum(self.frame_times) / len(self.frame_times)) * 1000:0>6.2f} ms/draw"
        self.frame_times = []


    def on_draw(self) -> None:
        t0 = time.time()
        self.clear()
        pyglet.gl.glLoadIdentity() # resets any applied translation matrices
        pyglet.gl.glPushMatrix() # stash the current matrix so translation doesn't affect it
        pyglet.gl.glTranslatef(-self.view_target[0], -self.view_target[1], 0)
        self.grid.batch.draw()
        pyglet.gl.glPopMatrix() # retrieve to stashed matrix
        self.batch.draw()

        self.frame_times.append(time.time() - t0)


    def on_resize(self, width: int, height: int) -> None:
        super().on_resize(width, height)
        LOGGER.debug("The window was resized to %dx%d", width, height)
        self.grid.move_view(self.grid.player.occupied_tile)


    def on_deactivate(self) -> None:
        pyglet.clock.unschedule(self.grid.update)


    def on_activate(self) -> None:
        pyglet.clock.schedule_interval(self.grid.update, UPDATE_INTERVAL)



def main() -> None:
    LOGGER.debug("Starting main()")
    window = GameWindow()
    pyglet.app.run()
