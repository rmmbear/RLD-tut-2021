import os
import enum
import logging
import dataclasses as dc
from typing import Optional, Tuple, Union

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

IMG_FONT = pyglet.image.ImageGrid(pyglet.image.load("res/dejavu10x10_gs_tc.png"), 8, 32)
IMG_FONT_WIDTH = 10
IMG_FONT_HEIGHT = 10
UPDATE_INTERVAL = 1/60

#TODO: make the grid/sprite size dynamic/adjustable
#TODO: make the grid scale automatically when resizing the window
#TODO: make sprite color adjustable


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


# MAP > GRID > VIEW
# map is the underlying map data
# grid is the section of the map data currently loaded
# view is the subset of the grid actually displayed


class Entity:
    def __init__(self, sprite: pyglet.sprite.Sprite):
        self.sprite = sprite
        self.occupied_cell: Optional[Cell] = None
        self.planned_move: Union[Tuple[Directions, int], Tuple] = ()
        #indices: 0 = Directions.DIRECTION, 1 = key symbol


    def update(self) -> None:
        if self.planned_move and self.occupied_cell:
            target_x = self.occupied_cell.grid_x + self.planned_move[0].value[0]
            target_y = self.occupied_cell.grid_y + self.planned_move[0].value[1]


            max_y, max_x = self.occupied_cell.grid.shape
            if not 0 <= target_x < max_x or not 0 <= target_y < max_y:
                LOGGER.debug("edge of grid")
                self.planned_move = ()
            else:
                target_cell = self.occupied_cell.grid[target_y, target_x]

                if target_cell.can_move_here(self):
                    self.occupied_cell.remove_entity()
                    target_cell.add_entity(self)
                    self.occupied_cell = target_cell
                else:
                    LOGGER.debug("cannot move here")
                    self.planned_move = ()



@dc.dataclass
class Cell:
    x: int
    y: int
    grid_x: int
    grid_y: int
    grid: numpy.ndarray
    entity: Optional[Entity] = None
    sprite: Optional[pyglet.sprite.Sprite] = None

    # https://github.com/python/mypy/issues/9779
    @property # type: ignore [no-redef]
    def sprite(self) -> pyglet.sprite.Sprite: # pylint: disable=function-redefined
        return self._sprite

    # https://github.com/python/mypy/issues/9779
    @sprite.setter # type: ignore [no-redef]
    def sprite(self, sprite: pyglet.sprite.Sprite) -> None: # pylint: disable=function-redefined
        """Ensure proper placement and anchoring."""
        sprite.x = self.x
        sprite.y = self.y
        sprite.anchor_y = 0
        sprite.anchor_x = 0
        sprite.color = (128,128,128)
        self._sprite = sprite


    def add_entity(self, entity: Entity) -> None:
        LOGGER.debug("Player on: grid(%d,%d) abs(%d,%d)",
                     self.grid_x, self.grid_y, self.x, self.y)
        entity.sprite.x = self.x
        entity.sprite.y = self.y
        entity.occupied_cell = self
        self.entity = entity


    def remove_entity(self) -> None:
        self.entity = None


    def move_cell(self, pos_x: int, pos_y: int, scale: Optional[float] = None) -> None:
        if scale:
            if self.sprite:
                self.sprite.scale = scale
            if self.entity:
                #breakpoint()
                self.entity.sprite.scale = scale

        self.x = pos_x
        self.y = pos_y
        if self.sprite:
            self.sprite.x = pos_x
            self.sprite.y = pos_y

        if self.entity:
            self.entity.sprite.x = pos_x
            self.entity.sprite.y = pos_y


    def can_move_here(self, entity: Entity) -> bool:
        if self.entity:
            return False

        return True


class Map:
    ...



class Grid:
    def __init__(self, grid_cols: int, grid_rows: int, window: pyglet.window.Window) -> None:
        self.grid_cols = grid_cols
        self.grid_rows = grid_rows
        self._grid = numpy.empty((grid_rows, grid_cols), dtype=Cell)

        LOGGER.debug("Initializing grid")
        for row in range(grid_rows):
            for col in range(grid_cols):
                sprite = pyglet.sprite.Sprite(
                    IMG_FONT[6, 11], batch=window.main_batch, group=window.grp_background)
                self._grid[row][col] = Cell(
                    x=0, y=0, grid_x=col, grid_y=row, sprite=sprite, grid=self._grid)

        LOGGER.debug("Grid initialized")

        player_sprite = pyglet.sprite.Sprite(
            IMG_FONT[6, 0], batch=window.main_batch, group=window.grp_foreground)
        player_sprite.scale = window.width / (self.grid_cols * IMG_FONT_WIDTH)
        self.player = Entity(player_sprite)
        self._grid[self.grid_rows//2][self.grid_cols//2].add_entity(self.player)
        pyglet.clock.schedule_interval(self.update, UPDATE_INTERVAL)

        self.active_entities = [self.player]


    def on_key_press(self, symbol: int, modifiers: int) -> None:
        LOGGER.debug("Key pressed %d", symbol)
        move = KEY_TO_DIR.get(symbol)
        if move:
            self.player.planned_move = (move, symbol)


    def on_key_release(self, symbol: int, modifiers: int) -> None:
        LOGGER.debug("Key released %d", symbol)
        if self.player.planned_move and self.player.planned_move[1] == symbol:
            self.player.planned_move = ()


    def update(self, delta: float) -> None:
        for entity in self.active_entities:
            entity.update()


    def resize(self, window: pyglet.window.Window) -> None:
        sprite_scale = window.width / (self.grid_cols * IMG_FONT_WIDTH)
        sprite_size = IMG_FONT_WIDTH * sprite_scale
        LOGGER.debug("Resizing grid")
        for row in range(self.grid_rows):
            for col in range(self.grid_cols):
                pos_x = sprite_size * col + 1
                pos_y = sprite_size * row + 1
                self._grid[row][col].move_cell(pos_x, pos_y, sprite_scale)

        LOGGER.debug("Done resizing")


class GameWindow(pyglet.window.Window): #pylint: disable=abstract-method
    def __init__(self) -> None:
        super().__init__(800, 600, caption="roguelike", resizable=True)
        self.main_batch = pyglet.graphics.Batch()
        self.grp_background = pyglet.graphics.OrderedGroup(0)
        self.grp_foreground = pyglet.graphics.OrderedGroup(1)
        self.grp_interface = pyglet.graphics.OrderedGroup(2)

        self.label = pyglet.text.Label(
            text="Hello roguelike world",
            font_name="monogram",
            font_size=32,
            x=self.width//2, y=self.height-100,
            anchor_x="center", anchor_y="center",
            batch=self.main_batch, group=self.grp_interface
        )

        self.fps_label = pyglet.text.Label(
            text="00.00",
            font_name="monogram",
            font_size=24,
            color=(250, 100, 100, 255),
            x=15, y=self.height-50,
            anchor_x="left", anchor_y="center",
            batch=self.main_batch, group=self.grp_interface
        )

        self.grid = Grid(40, 30, self)
        self.push_handlers(self.grid)
        pyglet.clock.schedule_interval(self.check_fps, 1)


    def check_fps(self, delta: int) -> None:
        self.fps_label.text = f"{float(pyglet.clock.get_fps()):2.3}"


    def on_draw(self) -> None:
        self.clear()
        self.main_batch.draw()


    def on_resize(self, width: int, height: int) -> None:
        optimal_height = (3 * self.width) // 4
        if height != optimal_height:
            pyglet.clock.schedule_once(self.correct_aspect, .4)
            #FIXME: resizing stops when the mouse stops moving,
            # and not when the user releases the resizing handle
            # as long as the handle is held, the window cannot be
            # programmatically resized
            return
            # on_resize will be called again as result of correct_apsect()

        super().on_resize(width, height)
        LOGGER.debug("The window was resized to %dx%d", width, height)
        self.grid.resize(self)


    def correct_aspect(self, _):
        optimal_height = (3 * self.width) // 4
        if self.height != optimal_height:
            LOGGER.debug("correcting height")
            self.set_size(self.width, optimal_height)


    def on_deactivate(self) -> None:
        pyglet.clock.unschedule(self.grid.update)


    def on_activate(self) -> None:
        pyglet.clock.schedule_interval(self.grid.update, UPDATE_INTERVAL)



def main() -> None:
    LOGGER.debug("Starting main()")
    window = GameWindow()
    pyglet.app.run()
