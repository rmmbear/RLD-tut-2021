import os
import enum
import logging
import dataclasses as dc
from typing import Optional, Tuple

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
UPDATE_INTERVAL = 1/120 # 120HZ

#TODO: constrain movement to grid
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
        self.planned_move: Optional[Tuple[Cell, int]] = ()
        #indices: 0 = Cell, 1 = key symbol


    def update(self):
        if self.planned_move:
            if self.planned_move[0].can_move_here(self):
                self.occupied_cell.remove_entity()
                self.planned_move[0].add_entity(self)
                self.occupied_cell = self.planned_move[0]
            else:
                self.planned_move = None



@dc.dataclass
class Cell:
    x: int
    y: int
    grid_x: int
    grid_y: int
    _grid: numpy.ndarray
    entity: Optional[Entity] = None
    sprite: Optional[pyglet.sprite.Sprite] = None



    @property
    def sprite(self):
        return self._sprite


    @sprite.setter
    def sprite(self, sprite: pyglet.sprite.Sprite):
        sprite.x = self.x
        sprite.y = self.y
        sprite.anchor_y = 0
        sprite.anchor_x = 0
        sprite.color = (128,128,128)
        self._sprite = sprite


    def add_entity(self, entity: Entity) -> None:
        entity.sprite.x = self.x
        entity.sprite.y = self.y
        entity.occupied_cell = self
        self.entity = entity


    def remove_entity(self) -> None:
        self.entity = None


    def can_move_here(self, entity: Entity) -> bool:
        if self.entity:
            return False

        return True


class Map:
    ...



class Grid:
    def __init__(self, grid_columns: int, grid_rows: int, window: pyglet.window.Window) -> None:
        csize = 20
        self._grid = numpy.empty((grid_columns, grid_rows), dtype=Cell)
        LOGGER.debug("Initializing grid")
        for i in range(grid_columns * grid_rows):
            row = i//grid_columns
            column = i - (row*grid_columns)
            x = csize * column
            y = csize * row
            sprite = pyglet.sprite.Sprite(
                IMG_FONT[6, 11], batch=window.main_batch, group=window.grp_background)
            self._grid[column][row] = Cell(
                x=x, y=y, grid_x=row, grid_y=column, sprite=sprite, _grid=self._grid)

        self._grid.reshape(grid_columns,grid_rows)
        LOGGER.debug("Grid initialized")

        player_sprite = pyglet.sprite.Sprite(
            IMG_FONT[6, 0], batch=window.main_batch, group=window.grp_foreground)
        self.player = Entity(player_sprite)
        self._grid[grid_columns//2][grid_rows//2].add_entity(self.player)
        pyglet.clock.schedule_interval(self.update, UPDATE_INTERVAL)

        self.active_entities = [self.player]


    def on_key_press(self, symbol: int, modifiers: int) -> None:
        move = KEY_TO_DIR.get(symbol)
        if move:
            x = self.player.occupied_cell.grid_x + move.value[0]
            y = self.player.occupied_cell.grid_y + move.value[1]
            cell = self._grid[y,x]
            self.player.planned_move = (cell, symbol)


    def on_key_release(self, symbol: int, modifiers: int) -> None:
        if self.player.planned_move and self.player.planned_move[1] == symbol:
            self.player.planned_move = None


    def update(self, delta: float) -> None:
        for entity in self.active_entities:
            entity.update()





class GameWindow(pyglet.window.Window):
    def __init__(self):
        super().__init__(800, 600, resizable=True)
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
        self.fps_label.text = f"{pyglet.clock.get_fps():2.3}"


    def on_draw(self) -> None:
        self.clear()
        self.main_batch.draw()


    def on_resize(self, width: int, height: int) -> None:
        super().on_resize(width, height)
        LOGGER.debug("The window was resized to %dx%d", width, height)


    def on_deactivate(self):
        pyglet.clock.unschedule(self.grid.update)


    def on_activate(self):
        pyglet.clock.schedule_interval(self.grid.update, UPDATE_INTERVAL)



def main() -> None:
    """"""
    LOGGER.debug("Starting main()")
    window = GameWindow()
    pyglet.app.run()
