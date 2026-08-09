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
        print(f"bot {self.user.name} joined at {datetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S')}!")
        activity = discord.CustomActivity(name="正在烤蛋糕")
        await self.change_presence(status=discord.Status.idle, activity=activity)
bot = MyBot()

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