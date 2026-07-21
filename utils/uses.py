import discord
from discord.ui import LayoutView, Container, Separator, TextDisplay, Section, Thumbnail

from config import GLOBAL_COGS, BOT_PREFIX

class infosView(LayoutView):
    def __init__(self, member):
        super().__init__()
        self.add_item(self.myContainer(member))

    class mySection(Section):
        def __init__(self, member:discord.Member):
            super().__init__(
                TextDisplay(f"Display Name `{member.display_name}`"),
                TextDisplay(f"Name `{member.name}`"),
                TextDisplay(f"ID `{member.id}`"),
                accessory = Thumbnail(media=member.display_avatar.url)
            )

    class myContainer(Container):
        def __init__(self, member:discord.Member):
            super().__init__(accent_color=member.color)

            sp = Separator() #分隔線組件

            self.add_item(infosView.mySection(member))
            self.add_item(sp)
            self.add_item(TextDisplay(f"帳號建立 <t:{int(member.created_at.timestamp())}:f>"))
            self.add_item(TextDisplay(f"加入此伺服器 <t:{int(member.joined_at.timestamp())}:f>"))
            self.add_item(sp)
            self.add_item(TextDisplay(f"伺服器 `{member.guild}`"))
            self.add_item(TextDisplay(f"Roles `{'`、`'.join([role.name for role in member.roles if role.name != '@everyone'])}`"))