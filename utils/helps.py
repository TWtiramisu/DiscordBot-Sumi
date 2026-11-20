from typing import Literal, Optional, Tuple

import discord
from discord.app_commands import Choice
from discord.ui import ActionRow, Container, LayoutView, Separator, TextDisplay

from config import BOT_PREFIX, GLOBAL_COGS


def get_help_options(mode: Optional[Literal["choice"]] = None):
    options = []
    cogs_items = list(GLOBAL_COGS.items())

    if mode is None:
        for cog_category, cog_object in cogs_items:
            cmds = cog_object.get_commands()
            slash_cmds = cog_object.get_app_commands()
            if not cmds and not slash_cmds:
                continue

            options.append(
                discord.SelectOption(
                    label=getattr(cog_object, "title", cog_category),
                    description=getattr(cog_object, "description", "暫無分類說明"),
                    emoji=getattr(cog_object, "emoji", "🔳"),
                    value=cog_category,
                )
            )

    elif mode == "choice":
        for cog_category, cog_object in cogs_items:
            cmds = cog_object.get_commands()
            slash_cmds = cog_object.get_app_commands()
            if not cmds and not slash_cmds:
                continue

            options.append(
                Choice(
                    name=getattr(cog_object, "title", cog_category),
                    value=cog_category,
                )
            )

    return options


def get_category_descriptions(category: Optional[str] = None) -> Tuple[str, list[str], discord.Color]:
    description = []
    cogs_items = list(GLOBAL_COGS.items())

    if category is None:
        title = "📚 目錄"
        color = discord.Color.blue()

        for _, cog_object in cogs_items:
            cmds = cog_object.get_commands()
            slash_cmds = cog_object.get_app_commands()
            if not cmds and not slash_cmds:
                continue
            description.append(f"### {cog_object.title}\n- {cog_object.description}")

    else:
        target_cog = None

        for cog_category, cog_object in cogs_items:
            if category.lower() == cog_category.lower():
                title = f"{getattr(cog_object, 'emoji', ' ')} {getattr(cog_object, 'title', cog_category)}"
                color = getattr(cog_object, "color", discord.Color.light_gray())
                target_cog = cog_object
                break

        if target_cog is None:
            title = "Error!"
            color = discord.Color.red()
            description.append("沒有找到分類，請檢查拼字錯誤或使用選單!")
        else:
            cmds = target_cog.get_commands()
            slash_cmds = target_cog.get_app_commands()
            if cmds:
                description.append("### 前綴指令")
                for cmd in cmds:
                    usage = getattr(cmd, "usage", None)
                    name, desc = cmd.name, cmd.description
                    cmd_line = f"`{BOT_PREFIX}{name} {usage}` {desc}".replace(" None", "")
                    description.append(cmd_line)

            if slash_cmds:
                description.append("### 應用程式指令")
                for slash_cmd in slash_cmds:
                    name, desc = slash_cmd.name, slash_cmd.description
                    description.append(f"`/{name}` {desc}")

    return title, description, color


class ContentsView(LayoutView):
    def __init__(self, author: discord.User | discord.Member, category: Optional[str] = None):
        super().__init__()
        self.author = author
        self.add_item(self.MyContainer(author, category))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author.id

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
            title, description, color = get_category_descriptions(category)
            super().__init__(accent_color=color)
            options = get_help_options()

            sp = Separator()  # 分隔線組件

            self.add_item(TextDisplay(f"# {title}"))
            self.add_item(sp)
            self.add_item(TextDisplay("\n".join(description)))
            self.add_item(ContentsView.HelpSelect(author, options))