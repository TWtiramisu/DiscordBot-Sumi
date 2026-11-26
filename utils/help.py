from typing import Any, Literal, Optional, Tuple, overload

import discord
from discord.app_commands import Choice
from discord.ui import ActionRow, Container, LayoutView, Separator, TextDisplay

from config import BOT_PREFIX, GLOBAL_COGS

MAX_DISCORD_OPTIONS = 25


def _is_hidden_cmd(cmd: Any) -> bool:
    if getattr(cmd, "hidden", False):
        return True
    callback = getattr(cmd, "callback", None)
    return bool(getattr(callback, "__hidden__", False))


def _is_hidden_slash_cmd(slash_cmd: Any) -> bool:
    extras = getattr(slash_cmd, "extras", None)
    if isinstance(extras, dict) and extras.get("hidden") is True:
        return True
    callback = getattr(slash_cmd, "callback", None)
    return bool(getattr(callback, "__hidden__", False))


def _get_visible_commands(cog_object: Any) -> Tuple[list[Any], list[Any]]:
    cmds = [cmd for cmd in cog_object.get_commands() if not _is_hidden_cmd(cmd)]
    slash_cmds = [
        slash_cmd
        for slash_cmd in cog_object.get_app_commands()
        if not _is_hidden_slash_cmd(slash_cmd)
    ]
    return cmds, slash_cmds


def _get_active_cogs() -> list[Tuple[str, Any, list[Any], list[Any]]]:
    active_cogs = []
    for cog_category, cog_object in list(GLOBAL_COGS.items()):
        cmds, slash_cmds = _get_visible_commands(cog_object)
        if not cmds and not slash_cmds:
            continue
        active_cogs.append((cog_category, cog_object, cmds, slash_cmds))
    return active_cogs


@overload
def get_help_options(mode: None = None) -> list[discord.SelectOption]: ...


@overload
def get_help_options(mode: Literal["choice"]) -> list[Choice[str]]: ...


def get_help_options(
    mode: Optional[Literal["choice"]] = None,
) -> list[discord.SelectOption] | list[Choice[str]]:
    active_cogs = _get_active_cogs()[:MAX_DISCORD_OPTIONS]

    if mode == "choice":
        return [
            Choice(
                name=getattr(cog_object, "title", cog_category),
                value=cog_category,
            )
            for cog_category, cog_object, _, _ in active_cogs
        ]

    return [
        discord.SelectOption(
            label=getattr(cog_object, "title", cog_category),
            description=getattr(cog_object, "description", "暫無分類說明"),
            emoji=getattr(cog_object, "emoji", "🔳"),
            value=cog_category,
        )
        for cog_category, cog_object, _, _ in active_cogs
    ]


def get_category_descriptions(category: Optional[str] = None) -> Tuple[str, list[str], discord.Color]:
    descriptions: list[str] = []
    active_cogs = _get_active_cogs()

    if category is None:
        title = "📚 目錄"
        color = discord.Color.blue()

        for cog_category, cog_object, _, _ in active_cogs:
            cog_title = getattr(cog_object, "title", cog_category)
            cog_desc = getattr(cog_object, "description", "暫無分類說明")
            descriptions.append(f"### {cog_title}\n- {cog_desc}")

        if not descriptions:
            descriptions.append("目前沒有可用的指令分類。")

    else:
        target_entry = next(
            (entry for entry in active_cogs if entry[0].lower() == category.lower()),
            None,
        )

        if target_entry is None:
            title = "Error!"
            color = discord.Color.red()
            descriptions.append("沒有找到分類，請檢查拼字錯誤或使用選單!")
        else:
            cog_category, target_cog, cmds, slash_cmds = target_entry
            title = f"{getattr(target_cog, 'emoji', ' ')} {getattr(target_cog, 'title', cog_category)}"
            color = getattr(target_cog, "color", discord.Color.light_gray())

            if cmds:
                descriptions.append("### 前綴指令")
                for cmd in cmds:
                    usage = getattr(cmd, "usage", None)
                    usage_str = f" {usage}" if usage else ""
                    desc = cmd.description or "暫無說明"
                    descriptions.append(f"`{BOT_PREFIX}{cmd.name}{usage_str}` {desc}")

            if slash_cmds:
                descriptions.append("### 應用程式指令")
                for slash_cmd in slash_cmds:
                    desc = slash_cmd.description or "暫無說明"
                    descriptions.append(f"`/{slash_cmd.name}` {desc}")

    return title, descriptions, color


class ContentsView(LayoutView):
    def __init__(self, author: discord.User | discord.Member, category: Optional[str] = None):
        super().__init__()
        self.author = author
        self.add_item(self.MyContainer(author, category))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("只有指令發起者可以使用此選單！", ephemeral=True)
            return False
        return True

    class HelpSelect(ActionRow):
        def __init__(self, author: discord.User | discord.Member, options: list[discord.SelectOption]):
            super().__init__()
            self.author = author
            self.menu = discord.ui.Select(placeholder="點擊展開功能導覽", options=options)
            self.menu.callback = self.callback
            self.add_item(self.menu)

        async def callback(self, interaction: discord.Interaction):
            await interaction.response.edit_message(
                view=ContentsView(self.author, self.menu.values[0])
            )

    class MyContainer(Container):
        def __init__(self, author: discord.User | discord.Member, category: Optional[str]):
            title, descriptions, color = get_category_descriptions(category)
            super().__init__(accent_color=color)
            options = get_help_options()

            self.add_item(TextDisplay(f"# {title}"))
            self.add_item(Separator())
            self.add_item(TextDisplay("`<>` 必填參數、`[]` 選填參數（輸入指令時不需包含括號）"))
            self.add_item(Separator())
            self.add_item(TextDisplay("\n".join(descriptions)))
            if options:
                self.add_item(ContentsView.HelpSelect(author, options))