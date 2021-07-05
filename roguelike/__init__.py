import os
import enum
import time
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
#TODO: investigate sprite scaling cost
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


class Entity:
    def __init__(self, name: str, sprite: pyglet.sprite.Sprite):
        self.name = name
        self.sprite = sprite
        self.occupied_cell: Optional[Tile] = None
        self.planned_move: Union[Tuple[Directions, int], Tuple] = ()
        #indices: 0 = Directions.DIRECTION, 1 = key symbol


    def update(self) -> Optional[Directions]:
        if self.planned_move and self.occupied_cell:
            direction = self.planned_move[0]
            moved = self.occupied_cell.move_entity(direction)
            if not moved:
                self.planned_move = ()
            else:
                return direction

        return None



@dc.dataclass(init=True, eq=False)
class Tile:
    grid_x: int
    grid_y: int
    map_grid: numpy.ndarray
    sprite: Optional[pyglet.sprite.Sprite] = None
    entity: Optional[Entity] = None
    screen_x: Optional[int] = None
    screen_y: Optional[int] = None


    def __repr__(self) -> str:
        return f"<Tile [{self.grid_x}, {self.grid_y}] at xy: ({self.screen_x},{self.screen_y})>"


    # https://github.com/python/mypy/issues/9779
    @property # type: ignore [no-redef]
    def sprite(self) -> pyglet.sprite.Sprite: # pylint: disable=function-redefined
        if not hasattr(self, "_sprite"):
            self._sprite = None
        return self._sprite


    @sprite.setter
    def sprite(self, sprite: pyglet.sprite.Sprite) -> None:
        """Ensure proper placement and anchoring."""
        if self.screen_x and self.screen_y:
            sprite.x = self.screen_x
            sprite.y = self.screen_y

        sprite.anchor_y = 0
        sprite.anchor_x = 0
        sprite.color = (
            int(self.grid_x / self.map_grid.shape[1] * 255),
            int(self.grid_y / self.map_grid.shape[0] * 255),
            200,

        )
        self._sprite = sprite


    def add_entity(self, entity: Entity) -> None:
        LOGGER.debug("Adding entity on: grid(%s,%s) abs(%s,%s)",
                     self.grid_x, self.grid_y, self.screen_x, self.screen_y)

        if entity.sprite and (self.screen_x and self.screen_y):
            entity.sprite.x = self.screen_x
            entity.sprite.y = self.screen_y

        entity.occupied_cell = self
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
            self.entity.occupied_cell = target_tile
            self.entity = None
            return True

        LOGGER.debug("%s cannot move to %s", self.entity.name, self.__repr__())
        return False


    def can_move_here(self, entity: Entity) -> bool:
        if self.entity:
            return False

        return True


    def move_tile(self, pos_x: int, pos_y: int, window: pyglet.window.Window,
                  scale: Optional[float] = None) -> None:
        self.screen_x = pos_x
        self.screen_y = pos_y

        if scale:
            if self.sprite:
                self.sprite.scale = scale
            if self.entity:
                self.entity.sprite.scale = scale

        if self.sprite:
            self.sprite.x = pos_x
            self.sprite.y = pos_y

        if self.entity:
            self.entity.sprite.x = pos_x
            self.entity.sprite.y = pos_y



class Map:
    def __init__(self, size: Tuple[int, int], window: pyglet.window.Window) -> None:
        self.window = window
        self.sprite_scale = IMG_FONT_SCALE
        self.tile_width = IMG_FONT_WIDTH * IMG_FONT_SCALE
        self.tile_height = IMG_FONT_HEIGHT * IMG_FONT_SCALE

        self.level_grid_cols, self.level_grid_rows = size
        self.level_grid = numpy.empty((self.level_grid_rows, self.level_grid_cols), dtype=Tile)

        self.view_tiles_x, self.view_tiles_y = 0, 0
        self.view_grid = None

        LOGGER.debug("Initializing grid")
        t0 = time.time()
        for row, row_arr in enumerate(self.level_grid):
            for col, tile in enumerate(row_arr):
                #XXX:creating sprite for every tile pre-emptiviely is a waste of resources
                sprite = pyglet.sprite.Sprite(IMG_WALL, batch=None, group=window.grp_background)
                row_arr[col] = Tile(grid_x=col, grid_y=row, map_grid=self.level_grid, sprite=sprite)

        LOGGER.info("Init took %.4f", time.time() - t0)

        player_sprite = pyglet.sprite.Sprite(
            IMG_PLAYER, batch=window.main_batch, group=window.grp_foreground)
        self.player = Entity("player", player_sprite)
        self.level_grid[self.level_grid_rows // 2, self.level_grid_cols // 2].add_entity(self.player)

        self.active_entities: List[Entity] = []
        pyglet.clock.schedule_interval(self.update, UPDATE_INTERVAL)


    def update(self, delta: float) -> None:
        moved = self.player.update()
        if moved and self.player.occupied_cell:
            target_x = self.player.occupied_cell.grid_x
            target_y = self.player.occupied_cell.grid_y
            self.move_view_to(target_x, target_y, moved.value)
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


    def resize(self, window: pyglet.window.Window) -> None:
        t0 = time.time()
        tiles_horizontal = ceil(window.width / self.tile_width)
        if tiles_horizontal % 2 == 0:
            tiles_horizontal += 1
        tiles_vertical = ceil(window.height / self.tile_height)
        if tiles_vertical % 2 == 0:
            tiles_vertical += 1

        self.view_tiles_x = tiles_horizontal
        self.view_tiles_y = tiles_vertical
        LOGGER.debug("Visible grid resized to (%dx%d)", tiles_horizontal, tiles_vertical)
        target = self.player.occupied_cell
        self.move_view_to(target.grid_x, target.grid_y, (0, 0))
        LOGGER.info("Resizing took %.3f", time.time() - t0)


    def move_view_to(self, grid_x: int, grid_y: int, direction: Tuple[int, int]) -> None:
        center_tile = self.level_grid[grid_y, grid_x]
        left_offset = 0
        bottom_offset = 0

        #FIXME: there still are occasional glitches when resizing

        min_col = center_tile.grid_x - self.view_tiles_x // 2
        if min_col < 0:
            left_offset = min_col * -1
            min_col = 0

        min_row = center_tile.grid_y - self.view_tiles_y // 2
        if min_row < 0:
            bottom_offset = min_row * -1
            min_row = 0

        #left_offset = 0
        #bottom_offset = 0

        row_constraint, col_constraint = self.level_grid.shape
        max_col = min(col_constraint, center_tile.grid_x + ceil(self.view_tiles_x / 2))
        max_row = min(row_constraint, center_tile.grid_y + ceil(self.view_tiles_y / 2))
        new_view = self.level_grid[min_row:max_row+1, min_col:max_col+1]
        LOGGER.debug("new view: %d:%d, %d:%d", min_row, max_row, min_col, max_col)
        # ~ breakpoint()
        # ~ LOGGER.debug("New view: %s", new_view)

        #disable rendering of tiles moved out of view
        t0 = time.time()
        if not self.view_grid is None:
            col_tiles_to_disable = ()
            row_tiles_to_disable = ()
            if direction[0] or direction[1]:
                if direction[0]:
                    if direction[0] > 0:
                        col_tiles_to_disable = self.view_grid[:,0:direction[0]]
                    elif direction[0] < 0:
                        col_tiles_to_disable = self.view_grid[:,direction[0]-1:-1]

                if direction[1]:
                    if direction[1] > 0:
                        row_tiles_to_disable = self.view_grid[0:direction[1]]
                    elif direction[1] < 0:
                        row_tiles_to_disable = self.view_grid[direction[1]-1:-1]
            else:
                # the view could have been shrunk as a result of resizing, check all tiles
                #XXX: this is slow
                row_tiles_to_disable = self.view_grid


            for row_arr in row_tiles_to_disable:
                for tile in row_arr:
                    tile.sprite.batch = None
                    #XXX:re-adding sprite to batch is a costly operation
            for row_arr in col_tiles_to_disable:
                for tile in row_arr:
                    tile.sprite.batch = None
                    #XXX:re-adding sprite to batch is a costly operation

        LOGGER.info("Disabling old view took %.3f", time.time() - t0)
        t1 = time.time()
        # calculate the layout for current view
        starting_pos_x = int(self.window.width - (self.view_tiles_x * self.tile_width))
        starting_pos_y = int(self.window.height - (self.view_tiles_y * self.tile_height))
        LOGGER.debug("Starting layout position: (%d,%d)", starting_pos_x, starting_pos_y)
        t0 = time.time()
        for y, row in enumerate(new_view):
            for x, tile in enumerate(row):
                pos_x = starting_pos_x + (self.tile_width * (x + left_offset))
                pos_y = starting_pos_y + (self.tile_height * (y + bottom_offset))
                tile.move_tile(pos_x, pos_y, self.window, self.sprite_scale)
                tile.sprite.batch = self.window.main_batch

        LOGGER.info("Enabling new view took %.3f", time.time() - t1)
        self.view_grid = new_view



class GameController:
    ...



class GameWindow(pyglet.window.Window): # pylint: disable=abstract-method
    def __init__(self) -> None:
        super().__init__(960, 540, caption="roguelike", resizable=True)
        self.main_batch = pyglet.graphics.Batch()
        self.grp_background = pyglet.graphics.OrderedGroup(0)
        self.grp_foreground = pyglet.graphics.OrderedGroup(1)
        self.grp_interface = pyglet.graphics.OrderedGroup(2)

        self.label = pyglet.text.Label(
            text="Hello roguelike world",
            font_name="monogram",
            font_size=32,
            x=self.width//2, y=self.height-10,
            anchor_x="center", anchor_y="top",
            batch=self.main_batch, group=self.grp_interface
        )

        self.fps_label = pyglet.text.Label(
            text="00.00",
            font_name="monogram",
            font_size=24,
            color=(250, 100, 100, 255),
            x=15, y=self.height-5,
            anchor_x="left", anchor_y="top",
            batch=self.main_batch, group=self.grp_interface
        )

        self.grid = Map((80, 45), self)
        self.push_handlers(self.grid)
        pyglet.clock.schedule_interval(self.check_fps, 1)


    def check_fps(self, delta: int) -> None:
        self.fps_label.text = f"{float(pyglet.clock.get_fps()):2.3}"


    def on_draw(self) -> None:
        self.switch_to()
        self.clear()
        self.main_batch.draw()


    def on_resize(self, width: int, height: int) -> None:
        #optimal_height = (3 * self.width) // 4
        #if height != optimal_height:
        #    pyglet.clock.schedule_once(self.correct_aspect, .5)
            #FIXME: resizing stops when the mouse stops moving,
            # and not when the user releases the resizing handle
            # as long as the handle is held, the window cannot be
            # programmatically resized
            #return
            # on_resize will be called again as result of correct_apsect()

        pyglet.clock.unschedule(self.delayed_resize)
        pyglet.clock.schedule_once(self.delayed_resize, .2, width, height)


    def delayed_resize(self, _: Any, width: int, height: int) -> None:
        super().on_resize(width, height)
        LOGGER.debug("The window was resized to %dx%d", width, height)
        self.grid.resize(self)


    def on_deactivate(self) -> None:
        pyglet.clock.unschedule(self.grid.update)


    def on_activate(self) -> None:
        pyglet.clock.schedule_interval(self.grid.update, UPDATE_INTERVAL)



def main() -> None:
    LOGGER.debug("Starting main()")
    window = GameWindow()
    pyglet.app.run()
