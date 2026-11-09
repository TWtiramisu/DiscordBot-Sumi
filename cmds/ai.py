import discord
from discord.ext import commands

import os, json
from openai import AsyncOpenAI
from dotenv import load_dotenv

class GroqAICog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        load_dotenv()
        self.ai_client = AsyncOpenAI(
            api_key=os.getenv("GROQ_API_KEY"),
            base_url="https://api.groq.com/openai/v1"
        )
        self.model_name = "qwen/qwen3.8-27b"
        
        # 定義存檔路徑
        self.memory_file = "db/chat_memory.json"
        
        # 初始化時從 JSON 讀取歷史紀錄
        self.chat_history = self.load_memory()

    def load_memory(self) -> dict:
        """從 JSON 檔案載入對話歷史紀錄"""
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    # JSON 中的 Key 是字串，讀取時轉回 int (channel_id)
                    data = json.load(f)
                    return {int(k): v for k, v in data.items()}
            except Exception as e:
                print(f"⚠️ 載入記憶檔失敗: {e}")
                return {}
        return {}

    def save_memory(self):
        """將對話歷史紀錄寫入 JSON 檔案"""
        try:
            with open(self.memory_file, "w", encoding="utf-8") as f:
                # 把 int 的 channel_id 轉成 str 以符合 JSON 格式
                data = {str(k): v for k, v in self.chat_history.items()}
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"⚠️ 儲存記憶檔失敗: {e}")

    def cog_unload(self):
        """當 Cog 被 !reload 或卸載時觸發，自動存檔"""
        self.save_memory()

    @commands.command(name="ask")
    async def ask(self, ctx: commands.Context, *, prompt: str):
        async with ctx.typing():
            try:
                channel_id = ctx.channel.id

                # 檢查該頻道是否已有對話紀錄
                if channel_id not in self.chat_history:
                    self.chat_history[channel_id] = []

                # 將使用者的最新發言寫入記憶
                self.chat_history[channel_id].append({"role": "user", "content": prompt})

                # 限制對話歷史長度（保留最新 10 則）
                if len(self.chat_history[channel_id]) > 10:
                    self.chat_history[channel_id] = self.chat_history[channel_id][-10:]

                # 組裝完整訊息
                messages = [
                    {
                        "role": "system",
                        "content": """
                            你是一名 Discord 伺服器的專屬助手「Sumi」。
                            你的性格特點：
                            1. 說話語氣親切、可愛，偶爾會帶一點幽默感。
                            2. 必須統一使用「繁體中文」回答，並減少 Emoji 的使用頻率。
                            3. 回答盡量簡明扼要，除非使用者特別要求詳細說明。
                            4. 喜歡在句子末尾加上合適的顏文字。
                        """
                    }
                ] + self.chat_history[channel_id]

                # 呼叫 API
                response = await self.ai_client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=1024
                )
                
                reply = response.choices[0].message.content

                # 將 AI 的回答寫入對話歷史並即時存檔
                self.chat_history[channel_id].append({"role": "assistant", "content": reply})
                self.save_memory()  # 即時備份至 JSON 檔

                # 發送訊息
                if len(reply) > 2000:
                    for i in range(0, len(reply), 1900):
                        await ctx.send(reply[i:i+1900])
                else:
                    await ctx.send(reply)

            except Exception as e:
                await ctx.send(f"❌ 呼叫 Groq API 時發生錯誤：```{str(e)}```")

    @commands.command(name="ctxclear")
    async def clear(self, ctx: commands.Context):
        channel_id = ctx.channel.id
        if channel_id in self.chat_history:
            del self.chat_history[channel_id]
            self.save_memory()
            await ctx.send("[v] Sumi 已經忘記本頻道的上下文囉！")
        else:
            await ctx.send("[x] 本頻道目前沒有任何對話記憶喔。")

async def setup(bot: commands.Bot):
    await bot.add_cog(GroqAICog(bot))