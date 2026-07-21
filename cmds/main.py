import discord
from discord.ext import commands
from discord import app_commands

from typing import Optional
from utils.helps import contentsView, get_helpOptions

class main(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="t", description="ttt")
    async def t(self, ctx:commands.Context):
        try:
            await ctx.reply()

        except Exception as e: print(e)

    @commands.command()
    async def help(self, ctx:commands.Context, category=None):
        await ctx.reply(view=contentsView(ctx.author, category))

    #異步函數跟註冊器綁一起的不要動 -> 用autocomplete動態註冊Choice選單
    async def helpOptions_autocomplete(self, interaction:discord.Interaction, current:str):
        return get_helpOptions("choice")
    @app_commands.command(name="help", description="查看功能導覽")
    @app_commands.describe(category="分類")
    @app_commands.autocomplete(category=helpOptions_autocomplete)
    async def slash_help(self, interaction:discord.Interaction, category:Optional[str]):
        await interaction.response.send_message(view=contentsView(interaction.user, category))


async def setup(bot):
    await bot.add_cog(main(bot))