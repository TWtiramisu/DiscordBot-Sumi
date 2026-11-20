import datetime
import discord
from discord.ext import commands

from config import GLOBAL_COGS


class Mod(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.title = "管理指令"
        self.description = "僅限管理員使用功能"
        self.emoji = "🔰"
        self.color = discord.Color.teal()

        GLOBAL_COGS["mod"] = self

    @commands.command(name="clear", usage="<數量>", description="清除指定數量的訊息")
    @commands.has_permissions(administrator=True)
    async def clear(self, ctx: commands.Context, num: int):
        await ctx.channel.purge(limit=num + 1)

    @commands.command(name="vote", usage="<標題> <投票項目(空格分開,至多10個)>", description="發起投票")
    @commands.has_permissions(administrator=True)
    async def vote(self, ctx: commands.Context, title: str, *msg: str):
        emoji_list = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

        if len(msg) <= 1:
            await ctx.reply("[x] 你需要至少 2 個選項以建立投票！")
            return

        if len(msg) > 10:
            await ctx.reply("[x] 投票選項不能超過 10 個！")
            return

        pull_list = [f"{emoji_list[i]} {item}" for i, item in enumerate(msg)]

        await ctx.message.delete()
        vote_msg = await ctx.send(
            embed=discord.Embed(
                title=f"{title}",
                description="\n".join(pull_list),
                color=discord.Color.random(),
            ).set_footer(
                text=f"投票發起者: {ctx.message.author}\n發起時間: {datetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S')}"
            )
        )
        for i in range(len(pull_list)):
            await vote_msg.add_reaction(emoji_list[i])


async def setup(bot: commands.Bot):
    await bot.add_cog(Mod(bot))