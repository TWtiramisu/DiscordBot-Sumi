import discord
from discord.ext import commands

import random
from config import GLOBAL_COGS
from utils.rawtexts import rawtextsView, editWhichRaw, rawtext_select, rawtext_insert 
from utils.uses import infosView



class use(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.title = "功能選單"
        self.description = "一般日常實用指令"
        self.emoji = "🏷️"
        self.color = discord.Color.yellow()

        GLOBAL_COGS["use"] = self

    @commands.command(name="avatar", usage="<@用戶>", description="獲取用戶頭像")
    async def avatar(self, ctx:commands.Context, member:discord.Member):
        await ctx.reply(
            embed = discord.Embed(
                title = f"{member.display_name}的頭像",
                color=discord.Color.random()
            ).set_image(
                url = member.avatar
            )
        )

    @commands.command(name="choose", usage="<選項(空格分開)>", description="機器人幫忙選擇")
    async def choose(self, ctx:commands.Context, *choose:str):
        await ctx.reply(f"我覺得 `{random.choice(choose)}` 不錯")
    
    @commands.command(name="embed", usage="<標題> <內文>", description="生成嵌入消息")
    async def embed(self, ctx:commands.Context, title, *, description):
        await ctx.message.delete()
        await ctx.send(
            embed = discord.Embed(
                title = title,
                description = description,
                color = discord.Color.random()
            )
        )

    @commands.command(name="info", usage="[member]", description="查看資訊")
    async def info(self, ctx:commands.Context, member:discord.Member=None):
        member = member or ctx.author

        await ctx.reply(view=infosView(member))

    @commands.command(name="luck", description="今日運勢(僅供參考)")
    async def luck(self, ctx:commands.Context):
        await ctx.reply(f"{ctx.author.mention}的今日運勢:`{random.choice(['大吉','吉','普通','凶','大凶'])}`")

    @commands.command(name="number", usage="<起始數字> <結束數字>", description="隨機取數")
    async def number(self, ctx:commands.Context, numBegin:int, numEnd:int):
        await ctx.reply(f"我想選 `{random.randint(numBegin, numEnd)}`")

    @commands.command(name="ping", description="查看機器人延遲")
    async def ping(self, ctx:commands.Context):
        ping = round(self.bot.latency * 1000)
        await ctx.reply(
            embed = discord.Embed(
                title = f"**機器人延遲: {round(self.bot.latency * 1000)}ms**",
                color = discord.Color.green() if ping < 200 else discord.Color.red()
            )
        )

    @commands.command(name="rawtext", description="MCBE rawtext 輔助編輯器")
    async def rawtext(self, ctx:commands.Context):
        #創建sql_rawtext資料
        result = await rawtext_select('userID', 'userID', ctx.author.id)
        if result is None: 
            await rawtext_insert('userID', (ctx.author.id, )) #sqlite要求參數必須是一組資料 -> 封裝成tuple

        view = rawtextsView(ctx.author).add_to_container(editWhichRaw(ctx.author))
        await ctx.reply(view=view)

    @commands.command(name="say", description="讓機器人說出指定的話")
    async def say(self, ctx:commands.Context, *, content):
        await ctx.message.delete()
        await ctx.channel.send(f"{content}\n-# By: {ctx.author.mention}")

async def setup(bot):
    await bot.add_cog(use(bot))