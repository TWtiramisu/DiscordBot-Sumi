import discord
from discord.ext import commands

import datetime
from config import GLOBAL_COGS



class mod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.title = "管理指令"
        self.description = "僅限管理員使用功能"
        self.emoji = "🔰"
        self.color = discord.Color.teal()

        GLOBAL_COGS["mod"] = self

    @commands.command(name="clear", usage="<數量>", description="清除指定數量的訊息")
    @commands.has_permissions(administrator=True)
    async def clear(self, ctx:commands.Context, num:int):
        await ctx.channel.purge(limit=num+1)

    @commands.command(name="vote", usage="<標題> <投票項目(空格分開,至多10個)>", description="發起投票")
    @commands.has_permissions(administrator=True)
    async def vote(self, ctx:commands.Context, title, *msg):
        emojiList = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
        msgList = msg
        pullList = []

        for n in range(len(msgList)):
            pullList.append(f"{emojiList[n]} {msgList[n]}")

        if len(pullList) <= 1 :
            await ctx.reply(":x: | 你需要更多選項以建立投票!")

        elif len(pullList) > 10:
            await ctx.reply(":x: | 投票選項不能超過 10 個!")

        elif 10 >= len(pullList) >= 2:
            await ctx.message.delete()
            vote_msg = await ctx.send(
                embed = discord.Embed(
                    title = f"{title}",
                    description = "\n".join(pullList),
                    color = discord.Color.random()
                ).set_footer(
                    text = f"投票發起者: {ctx.message.author}\n發起時間: {datetime.datetime.now()}"
                )
            )
            for i in range(len(pullList)):
                await vote_msg.add_reaction(emojiList[i])

async def setup(bot):
    await bot.add_cog(mod(bot))