import time
import random
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union
import pyglet
import numpy as np

from.entity import Entity


#TODO: Delay creation of tile sprites
#TODO: use a sprite pool, assign sprites to tiles as needed
#FIXME: fix coordinate issue resulting from indexing discrepency between pyglet and numpy
#   numpy  [0,0] = top left
#   pyglet [0,0] = bottom left
#


LOGGER = logging.getLogger(__name__)

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


def random_rgb() -> Tuple[int, int, int]:
    return (
        random.randrange(0,256),
        random.randrange(0,256),
        random.randrange(0,256),
    )



class Tileset:
    def __init__(self, path: str, rows: int, cols: int, scale: int = 1) -> None:
        self.path = path
        self.rows = rows
        self.cols = cols

        self._image_grid = pyglet.image.ImageGrid(pyglet.image.load(path), rows, cols)
        self._num_to_img: Dict[int, pyglet.image.AbstractImage] = {}

        self.scale = scale
        self.tile_width = self._image_grid.item_height * scale
        self.tile_height = self._image_grid.item_height * scale


    def get_image(self, row: int, col: int) -> pyglet.image.AbstractImage:
        img = self._num_to_img.get(row * col)
        if img:
            return img

        img = self._image_grid[row, col]
        self._num_to_img[row * col] = img
        return img



class Map:
    def __init__(self, size: Tuple[int, int], player: Entity,
                 window: pyglet.window.Window, tileset: Tileset
                ) -> None:
        self.window = window
        self.tileset = tileset
        self.batch = pyglet.graphics.Batch()
        self.grp_tiles = pyglet.graphics.OrderedGroup(1, self.window.grp_fore)
        self.grp_entities = pyglet.graphics.OrderedGroup(2, self.window.grp_fore)

        self.level_grid = np.empty((size[1], size[0]), dtype=DT_TILE_NAV)
        self.create_grid()

        player.sprite.batch = self.batch
        player.sprite.group = self.grp_entities
        player.sprite.scale = self.tileset.scale
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
                pos_x = self.tileset.tile_width * col + 5
                pos_y = self.tileset.tile_height * row + 5
                sprite = pyglet.sprite.Sprite(
                    self.tileset.get_image(7, 12), x=pos_x, y=pos_y,
                    batch=self.batch, group=self.grp_tiles
                )
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
            sprite = pyglet.sprite.Sprite(
                self.tileset.get_image(6, 0), batch=self.batch, group=self.grp_entities)
            sprite.scale = self.tileset.scale
            sprite.color = random_rgb()
            #sprite = Sprite(0, 0, self.sprite_scale, sprite=_sprite, color_norm=_sprite.color)
            ent = Entity(f"npc{i}", sprite)
            self.place_entity(ent, rand_x, rand_y)
            self.entities.append(ent)


    def place_player(self) -> None:
        self.place_entity(self.player, 24, 13)


    def place_entity(self, entity: Entity, col: int, row: int) -> None:
        abs_x = col * self.tileset.tile_width
        abs_y = row * self.tileset.tile_height
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



@dataclass(init=True, eq=False)
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
