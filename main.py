import discord
from discord.ext import commands

import os, asyncio, datetime
from config import Info, BOT_PREFIX

#建立一個繼承Bot的類別
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        intents.members = True
        super().__init__(
            command_prefix = BOT_PREFIX, 
            owner_id = Info.ownerID,
            intents = intents, 
            help_command = None,
            allowed_mentions = discord.AllowedMentions(replied_user=False) #禁用reply時的黃色提示
        )

    async def setup_hook(self): #啟動時自動載入所有 Cog
        for filename in os.listdir("./cmds"):
            if filename.endswith(".py"):
                await self.load_extension(f"cmds.{filename[:-3]}")
        print(f"Cog have been loaded.")

    async def on_ready(self):
        print(f"bot {self.user.name} joined at {datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")}!")
        activity = discord.CustomActivity(name="正在烤蛋糕")
        await self.change_presence(status=discord.Status.idle, activity=activity)
bot = MyBot()

@bot.command()
@commands.is_owner()
async def guilds(ctx:commands.Context):
    server_names_string = "\n".join([guild.name for guild in bot.guilds])
    await ctx.reply(f"我已經被邀請進了以下的伺服器: \n```{server_names_string}```")

#sync slash commmands
@bot.command()
@commands.is_owner()
async def sync(ctx:commands.Context, mode="guild"):
    now = datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    
    try:
        if mode == "guild": #只同步當前guild
            bot.tree.copy_global_to(guild=ctx.guild)
            synced = await bot.tree.sync(guild=ctx.guild)

        elif mode == "global": #全域同步
            synced = await bot.tree.sync()

        print(f"[{now} ◈ {mode} mode] Synced: {", ".join([content.name for content in synced])}")

    except Exception as e:
        print(e)

@bot.command()
@commands.is_owner()
async def clearsync(ctx:commands.Context):
    now = datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")

    bot.tree.clear_commands(guild=ctx.guild)
    await bot.tree.sync(guild=ctx.guild)

    print(f"[{now} ◈ guild_clear mode] Synced commands have been cleared.")

async def main():
    try:
        await bot.start(os.getenv("TOKEN"))
    except asyncio.CancelledError:
        print("[-] 機器人連線被取消。")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[!] 偵錯被使用者或系統中斷，正在安全關閉...")