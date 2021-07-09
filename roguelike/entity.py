from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Union, Optional, Tuple, TYPE_CHECKING

import pyglet
if TYPE_CHECKING:
    from . import GameWindow

LOGGER = logging.getLogger(__name__)


class Action:
    def __call__(self, window: GameWindow, entity: Entity) -> bool:
        raise NotImplementedError()



@dataclass
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



class Player(Entity):
    def __init__(self, sprite: pyglet.sprite.Sprite) -> None:
        super().__init__("player", sprite)
        self.movement_repeat_key: Optional[int] = None
