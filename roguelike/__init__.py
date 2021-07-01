import os
import enum
import logging
from typing import Optional, Tuple

import pyglet
from pyglet.window import key

LOG_FORMAT = logging.Formatter("%(asctime)s [%(levelname)s]: %(message)s", "%Y-%m-%d %H:%M:%S")
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


class Player:
    def __init__(self, batch: pyglet.graphics.Batch, x: int = 0, y: int = 0,
                 sprite: Optional[pyglet.sprite.Sprite] = None) -> None:
        if not sprite:
            sprite = pyglet.sprite.Sprite(IMG_FONT[6, 0], batch=batch)

        self.sprite = sprite
        self.sprite.x = x
        self.sprite.y = y
        self.movement: Optional[Tuple[int, int, int]] = None
        #self.movement indices: 0 = x, 1 = y, 2 = key symbol


    def on_key_press(self, symbol: int, modifiers: int) -> None:
        movement = KEY_TO_DIR.get(symbol)
        if movement:
            self.movement = (*movement.value, symbol)


    def on_key_release(self, symbol: int, modifiers: int) -> None:
        if self.movement and self.movement[2] == symbol:
            self.movement = None


    def update(self, delta: float) -> None:
        if self.movement:
            self.sprite.x += self.movement[0]
            self.sprite.y += self.movement[1]



class GameWindow(pyglet.window.Window):
    def __init__(self):
        super().__init__(800, 600, resizable=True)
        self.main_batch = pyglet.graphics.Batch()
        self.label = pyglet.text.Label(
            text="Hello roguelike world",
            font_name="monogram",
            font_size=32,
            x=self.width//2, y=self.height-100,
            anchor_x="center", anchor_y="center",
            batch=self.main_batch
        )


    def on_draw(self) -> None:
        self.clear()
        self.main_batch.draw()


    def on_resize(self, width: int, height: int) -> None:
        super().on_resize(width, height)
        LOGGER.debug("The window was resized to %dx%d", width, height)



def main() -> None:
    """"""
    LOGGER.debug("Starting main()")
    window = GameWindow()
    player = Player(batch=window.main_batch, x=window.width//2, y=window.height//2)
    window.push_handlers(player)

    def update(delta: float) -> None:
        for obj in game_objects:
            obj.update(delta)


    game_objects = [player]
    pyglet.clock.schedule_interval(update, UPDATE_INTERVAL)
    pyglet.app.run()
