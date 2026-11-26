import datetime
import importlib
import sys
from typing import Optional

from discord.ext import commands


class Main(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command()
    @commands.is_owner()
    async def guilds(self, ctx: commands.Context):
        server_names_string = "\n".join([guild.name for guild in self.bot.guilds])
        await ctx.reply(f"我已經被邀請進了以下的伺服器: \n```{server_names_string}```")

    # sync slash commands
    @commands.command()
    @commands.is_owner()
    async def sync(self, ctx: commands.Context, mode: str = "guild"):
        now = datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")

        try:
            if mode == "guild":  # 只同步當前 guild
                self.bot.tree.copy_global_to(guild=ctx.guild)
                synced = await self.bot.tree.sync(guild=ctx.guild)
            elif mode == "global":  # 全域同步
                synced = await self.bot.tree.sync()
            else:
                await ctx.reply(f"[x] 未知的模式 `{mode}`，請選擇 `guild` 或 `global`。")
                return

            synced_names = ", ".join([cmd.name for cmd in synced]) or "無指令"
            print(f"[{now} ◈ {mode} mode] Synced: {synced_names}")
            await ctx.reply(f"[v] 成功同步指令（{mode} 模式）：`{synced_names}`")

        except Exception as e:
            print(f"[!] Sync error: {e}")
            await ctx.reply(f"[x] 指令同步失敗：```{e}```")

    @commands.command()
    @commands.is_owner()
    async def clearsync(self, ctx: commands.Context):
        now = datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        try:
            self.bot.tree.clear_commands(guild=ctx.guild)
            await self.bot.tree.sync(guild=ctx.guild)
            print(f"[{now} ◈ guild_clear mode] Synced commands have been cleared.")
            await ctx.reply("[v] 已清除本伺服器同步的應用程式指令。")
        except Exception as e:
            print(f"[!] Clear sync error: {e}")
            await ctx.reply(f"[x] 清除失敗：```{e}```")

    # load cogs
    @commands.command()
    @commands.is_owner()
    async def reload(self, ctx: commands.Context, extension: str):
        target = extension if extension.startswith("cmds.") else f"cmds.{extension}"

        try:
            for name, mod in list(sys.modules.items()):
                if name.startswith("utils.") and mod is not None:
                    importlib.reload(mod)

            await self.bot.reload_extension(target)
            await ctx.reply(f"[v] 成功重新載入 Cog: `{target}`")
            print(f"[{datetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S')}] Reloaded: {target}")

        except commands.ExtensionNotFound:
            await ctx.reply(f"[x] 找不到該 Cog: `{target}`")
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
            await ctx.reply(f"[v] 成功載入 Cog：`{target}`")

        except Exception as e:
            await ctx.reply(f"[!] 載入 `{target}` 失敗：\n```py\n{e}\n```")
            print(f"[{datetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S')}] Exception: {target}")

    @commands.command()
    @commands.is_owner()
    async def unload(self, ctx: commands.Context, extension: str):
        target = extension if extension.startswith("cmds.") else f"cmds.{extension}"

        try:
            await self.bot.unload_extension(target)
            await ctx.reply(f"[v] 成功卸載 Cog：`{target}`")

        except Exception as e:
            await ctx.reply(f"[!] 卸載 `{target}` 失敗：\n```py\n{e}\n```")
            print(f"[{datetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S')}] Exception: {target}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Main(bot))