import discord
from discord.ui import LayoutView, Container, ActionRow, Separator, TextDisplay
from discord.app_commands import Choice

from config import GLOBAL_COGS, BOT_PREFIX

def get_helpOptions(mode=None):
    options = []
    
    if mode is None:
        for cog_category, cog_object in GLOBAL_COGS.items():
            cmds, slash_cmds = cog_object.get_commands(), cog_object.get_app_commands()
            if not cmds and not slash_cmds: continue

            options.append(
                discord.SelectOption(
                    label = getattr(cog_object, "title", cog_category),
                    description = getattr(cog_object, "description", "暫無分類說明"),
                    emoji = getattr(cog_object, "emoji", "🔳"),
                    value = cog_category
                )
            )

    elif mode == "choice":
        for cog_category, cog_object in GLOBAL_COGS.items():
            cmds, slash_cmds = cog_object.get_commands(), cog_object.get_app_commands()
            if not cmds and not slash_cmds: continue
            
            options.append(
                Choice(
                    name = getattr(cog_object, "title", cog_category),
                    value = cog_category
                )
            )

    return options

def get_categoryDescriptions(category=None):
    description = []

    if category is None:
        title = "目錄"
        color = discord.Color.blue()

        for cog_category, cog_object in GLOBAL_COGS.items():
            cmds, slash_cmds = cog_object.get_commands(), cog_object.get_app_commands()
            if not cmds and not slash_cmds: continue
            description.append(f"### {cog_object.title}\n- {cog_object.description}")

    else:
        target_cog = None

        for cog_category, cog_object in GLOBAL_COGS.items():
            if category.lower() == cog_category:
                title = getattr(cog_object, "title", cog_category)
                color = getattr(cog_object, "color", discord.Color.light_gray())
                target_cog = cog_object
                break

        if target_cog is None:
            title = "error"
            description.append("category not found")

        else:
            cmds, slash_cmds = target_cog.get_commands(), target_cog.get_app_commands()
            if cmds:
                description.append("### 前綴指令")
                for cmd in cmds:
                    usage = getattr(cmd, "usage", None)
                    name, desc = cmd.name, cmd.description
                    description.append(f"`{BOT_PREFIX}{name} {usage}` {desc}".replace(" None", ""))

            if slash_cmds:
                description.append("### 應用程式指令")
                for slash_cmd in slash_cmds:
                    name, desc = slash_cmd.name, slash_cmd.description
                    description.append(f"`/{name}` {desc}")

    return title, description, color

class contentsView(LayoutView):
    def __init__(self, author, category=None):
        super().__init__()
        self.author = author
        self.add_item(self.myContainer(author, category))

    async def interaction_check(self, interaction: discord.Interaction):
        return interaction.user.id == self.author.id

    class helpSelect(ActionRow):
        def __init__(self, author, options):
            super().__init__()
            self.author = author
            self.menu = discord.ui.Select(placeholder="點擊展開功能導覽", options=options)
            self.menu.callback = self.callback
            self.add_item(self.menu)

        async def callback(self, interaction:discord.Interaction):
            await interaction.response.edit_message(view=contentsView(self.author, self.menu.values[0]))

    class myContainer(Container):
        def __init__(self, author, category):
            title, description, color = get_categoryDescriptions(category)
            super().__init__(accent_color=color)
            options = get_helpOptions()

            sp = Separator() #分隔線組件

            self.add_item(TextDisplay(f"# {title}"))
            self.add_item(sp)
            self.add_item(TextDisplay("\n".join(description)))
            self.add_item(contentsView.helpSelect(author, options))