import discord
from discord.ext import commands
from discord import app_commands

import datetime
from typing import Optional
from utils.helps import contentsView, get_helpOptions



class main(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

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

    @commands.command()
    @commands.is_owner()
    async def guilds(self, ctx:commands.Context):
        server_names_string = "\n".join([guild.name for guild in self.bot.guilds])
        await ctx.reply(f"我已經被邀請進了以下的伺服器: \n```{server_names_string}```")


    # sync slash commmands
    @commands.command()
    @commands.is_owner()
    async def sync(self, ctx:commands.Context, mode="guild"):
        now = datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        
        try:
            if mode == "guild": #只同步當前guild
                self.bot.tree.copy_global_to(guild=ctx.guild)
                synced = await self.bot.tree.sync(guild=ctx.guild)

            elif mode == "global": #全域同步
                synced = await self.bot.tree.sync()

            print(f"[{now} ◈ {mode} mode] Synced: {', '.join([content.name for content in synced])}")

        except Exception as e:
            print(e)

    @commands.command()
    @commands.is_owner()
    async def clearsync(self, ctx:commands.Context):
        now = datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")

        self.bot.tree.clear_commands(guild=ctx.guild)
        await self.bot.tree.sync(guild=ctx.guild)

        print(f"[{now} ◈ guild_clear mode] Synced commands have been cleared.")


    # load cogs
    @commands.command()
    @commands.is_owner()
    async def reload(self, ctx: commands.Context, extension: str):
        target = extension if extension.startswith("cmds.") else f"cmds.{extension}"
        
        try:
            await self.bot.reload_extension(target)
            await ctx.reply(f"[✔] 成功重新載入 Cog: `{target}`")
            print(f"[{datetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S')}] Reloaded: {target}")

        except commands.ExtensionNotFound:
            await ctx.reply(f"[X] 找不到該 Cog: `{target}`")
            print(f"[{datetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S')}] Cog not found: {target}")

        except Exception as e:
            await ctx.reply(f"[!] 載入 `{target}` 失敗：\n```py\n{e}\n```")
            print(f"[{datetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S')}] Exception: {target}")

    @commands.command()
    @commands.is_owner()
    async def load(self, ctx: commands.Context, extension: str):
        target = extension if extension.startswith("cmds.") else f"cmds.{extension}"

        try:
            await self.bot.load_extension(target)
            await ctx.reply(f"[✔] 成功載入 Cog：`{target}`")

        except Exception as e:
            await ctx.reply(f"[!] 載入 `{target}` 失敗：\n```py\n{e}\n```")
            print(f"[{datetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S')}] Exception: {target}")

    @commands.command()
    @commands.is_owner()
    async def unload(self, ctx: commands.Context, extension: str):
        target = extension if extension.startswith("cmds.") else f"cmds.{extension}"

        try:
            await self.bot.unload_extension(target)
            await ctx.reply(f"[✔] 成功卸載 Cog：`{target}`")

        except Exception as e:
            await ctx.reply(f"[!] 卸載 `{target}` 失敗：\n```py\n{e}\n```")
            print(f"[{datetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S')}] Exception: {target}")

async def setup(bot):
    await bot.add_cog(main(bot))