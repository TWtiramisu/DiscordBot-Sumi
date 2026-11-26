from typing import TypeVar

from discord import app_commands
from discord.ext import commands

T = TypeVar("T")


def hidden(target: T) -> T:
    """標記指令為隱藏，使其不顯示於 help 選單中。

    支援置於 `@commands.command(...)`、`@app_commands.command(...)`、
    `app_commands.Group` 上方，或直接置於指令函式上方。
    """
    if isinstance(target, commands.Command):
        target.hidden = True
        if isinstance(getattr(target, "__original_kwargs__", None), dict):
            target.__original_kwargs__["hidden"] = True
        if getattr(target, "callback", None) is not None:
            setattr(target.callback, "__hidden__", True)

    elif isinstance(target, (app_commands.Command, app_commands.Group)):
        if not isinstance(target.extras, dict):
            target.extras = {}
        target.extras["hidden"] = True

    else:
        setattr(target, "__hidden__", True)
        
    return target
