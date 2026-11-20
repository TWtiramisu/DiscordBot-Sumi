import discord
from discord.ui import Container, LayoutView, Section, Separator, TextDisplay, Thumbnail


class InfosView(LayoutView):
    def __init__(self, member: discord.Member):
        super().__init__()
        self.add_item(self.MyContainer(member))

    class MySection(Section):
        def __init__(self, member: discord.Member):
            super().__init__(
                TextDisplay(f"Display Name `{member.display_name}`"),
                TextDisplay(f"Name `{member.name}`"),
                TextDisplay(f"ID `{member.id}`"),
                accessory=Thumbnail(media=member.display_avatar.url),
            )

    class MyContainer(Container):
        def __init__(self, member: discord.Member):
            super().__init__(accent_color=member.color)

            sp = Separator()  # 分隔線組件

            created_str = f"<t:{int(member.created_at.timestamp())}:f>" if member.created_at else "未知"
            joined_str = f"<t:{int(member.joined_at.timestamp())}:f>" if member.joined_at else "未知"

            self.add_item(InfosView.MySection(member))
            self.add_item(sp)
            self.add_item(TextDisplay(f"帳號建立 {created_str}"))
            self.add_item(TextDisplay(f"加入此伺服器 {joined_str}"))
            self.add_item(sp)
            self.add_item(TextDisplay(f"伺服器 `{member.guild}`"))
            roles_str = "、".join([f"`{role.name}`" for role in member.roles if role.name != "@everyone"])
            self.add_item(TextDisplay(f"Roles {roles_str or '無'}"))