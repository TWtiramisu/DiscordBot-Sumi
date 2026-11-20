import importlib
import random
from typing import Optional

import discord
from discord.ext import commands

from config import GLOBAL_COGS

# utils hot reload
import utils.rawtext
import utils.use
importlib.reload(utils.use)
importlib.reload(utils.rawtext)
from utils.rawtext import EditWhichRaw, RawtextsView, rawtext_insert, rawtext_select
from utils.use import InfosView


class Use(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.title = "功能選單"
        self.description = "一般日常實用指令"
        self.emoji = "🏷️"
        self.color = discord.Color.yellow()

        GLOBAL_COGS["use"] = self

    @commands.command(name="avatar", usage="<@用戶>", description="獲取用戶頭像")
    async def avatar(self, ctx: commands.Context, member: discord.Member):
        await ctx.reply(
            embed=discord.Embed(
                title=f"{member.display_name}的頭像",
                color=discord.Color.random(),
            ).set_image(url=member.display_avatar.url)
        )

    @commands.command(name="choose", usage="<選項(空格分開)>", description="機器人幫忙選擇")
    async def choose(self, ctx: commands.Context, *choose: str):
        if not choose:
            await ctx.reply("❌ 請提供至少一個選項！")
            return
        await ctx.reply(f"我覺得 `{random.choice(choose)}` 不錯")

    @commands.command(name="embed", usage="<標題> <內文>", description="生成嵌入消息")
    async def embed(self, ctx: commands.Context, title: str, *, description: str):
        await ctx.message.delete()
        await ctx.send(
            embed=discord.Embed(
                title=title,
                description=description,
                color=discord.Color.random(),
            )
        )

    @commands.command(name="info", usage="[member]", description="查看資訊")
    async def info(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        target_member = member or ctx.author
        await ctx.reply(view=InfosView(target_member))

    @commands.command(name="luck", description="今日運勢(僅供參考)")
    async def luck(self, ctx: commands.Context):
        fortune = random.choice(["大吉", "吉", "普通", "凶", "大凶"])
        await ctx.reply(f"{ctx.author.mention}的今日運勢:`{fortune}`")

    @commands.command(name="number", usage="<起始數字> <結束數字>", description="隨機取數")
    async def number(self, ctx: commands.Context, num_begin: int, num_end: int):
        low, high = min(num_begin, num_end), max(num_begin, num_end)
        await ctx.reply(f"我想選 `{random.randint(low, high)}`")

    @commands.command(name="ping", description="查看機器人延遲")
    async def ping(self, ctx: commands.Context):
        ping = round(self.bot.latency * 1000)
        await ctx.reply(
            embed=discord.Embed(
                title=f"**機器人延遲: {ping}ms**",
                color=discord.Color.green() if ping < 200 else discord.Color.red(),
            )
        )

    @commands.command(name="rawtext", description="MCBE rawtext 輔助編輯器")
    async def rawtext(self, ctx: commands.Context):
        result = await rawtext_select("userID", "userID", ctx.author.id)
        if result is None:
            await rawtext_insert("userID", (ctx.author.id,))

        view = RawtextsView(ctx.author).add_to_container(EditWhichRaw(ctx.author))
        await ctx.reply(view=view)

    @commands.command(name="say", description="讓機器人說出指定的話")
    async def say(self, ctx: commands.Context, *, content: str):
        await ctx.message.delete()
        await ctx.channel.send(content)


async def setup(bot: commands.Bot):
    await bot.add_cog(Use(bot))