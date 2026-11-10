import discord
from discord.ext import commands

import os, json, inspect
from openai import AsyncOpenAI
from dotenv import load_dotenv



class GroqAICog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        load_dotenv()
        self.ai_client = AsyncOpenAI(
            api_key = os.getenv("GROQ_API_KEY"),
            base_url = "https://api.groq.com/openai/v1"
        )
        # default model
        self.model_name = "qwen/qwen3.8-27b"
        
        # database files
        self.memory_file = "db/chat_memory.json"
        self.longterm_memory_file = "db/longterm_memory.json"
        self.ensure_db_files()

        # chat memory
        self.chat_history = self.load_memory()
        
        # target channel
        self.target_channel_id = 1569521240538873946

    def ensure_db_files(self):
        """檢查 db/ 是否有 chat_memory.json 與 longterm_memory.json，若無則創建"""
        os.makedirs("db", exist_ok=True)
        for filepath, default_data in [
            (self.memory_file, {}),
            (self.longterm_memory_file, {})
        ]:
            if not os.path.exists(filepath):
                try:
                    with open(filepath, "w", encoding="utf-8") as f:
                        json.dump(default_data, f, ensure_ascii=False, indent=4)
                    print(f"[+] 已自動建立資料庫檔案: {filepath}")
                    
                except Exception as e:
                    print(f"[!] 建立 {filepath} 失敗: {e}")

    def load_memory(self) -> dict:
        """從 JSON 檔案載入對話歷史紀錄"""
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    # JSON 中的 Key 是字串，讀取時轉回 int (channel_id)
                    data = json.load(f)
                    return {int(k): v for k, v in data.items()}
                
            except Exception as e:
                print(f"[!] 載入記憶檔失敗: {e}")
                return {}
            
        return {}

    def load_longterm_memory(self) -> dict:
        """從 JSON 檔案載入長期記憶"""
        if os.path.exists(self.longterm_memory_file):
            try:
                with open(self.longterm_memory_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[!] 載入長期記憶檔失敗: {e}")
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
            print(f"[!] 儲存記憶檔失敗: {e}")

    def cog_unload(self):
        """當 Cog 被 !reload 或卸載時觸發，自動存檔"""
        self.save_memory()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # 忽略來自機器人本身的訊息
        if message.author.bot:
            return

        # 僅在特定頻道中觸發
        if message.channel.id != self.target_channel_id:
            return

        # 忽略指令訊息（例如以前綴開頭的訊息）
        prefix = self.bot.command_prefix
        if isinstance(prefix, str) and message.content.startswith(prefix):
            return
        
        elif isinstance(prefix, (list, tuple)) and message.content.startswith(tuple(prefix)):
            return

        # 若是註冊指令也忽略
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        prompt = message.content.strip()
        if not prompt:
            return

        async with message.channel.typing():
            try:
                channel_id = message.channel.id

                # 檢查該頻道是否已有對話紀錄
                if channel_id not in self.chat_history:
                    self.chat_history[channel_id] = []

                # 將使用者的最新發言寫入記憶（包含發言者名稱與 ID）
                user_content = f"[{message.author.display_name} | ID: {message.author.id}]: {prompt}"
                self.chat_history[channel_id].append({"role": "user", "content": user_content})

                # 限制對話歷史長度（保留最新 10 則）
                if len(self.chat_history[channel_id]) > 10:
                    self.chat_history[channel_id] = self.chat_history[channel_id][-10:]

                # 載入長期記憶
                longterm_memory = self.load_longterm_memory()
                longterm_str = json.dumps(longterm_memory, ensure_ascii=False, indent=2) if longterm_memory else "無"

                # 查詢當前發言者是否有長期記憶 profile
                user_profile = longterm_memory.get("user_profiles", {}).get(str(message.author.id))
                profile_desc = json.dumps(user_profile, ensure_ascii=False) if user_profile else "無（新朋友或暫無特定紀錄）"

                # 組裝完整訊息
                system_content = inspect.cleandoc(f"""
                    你是一名 Discord 伺服器的專屬助手「Sumi」。
                    你的性格特點：
                    1. 說話語氣親切、可愛，會帶一點幽默感。
                    2. 必須統一使用「繁體中文」回答，並減少 Emoji 的使用頻率。
                    3. 回答盡量簡明扼要，除非使用者特別要求詳細說明。
                    4. 偶爾會在句子末尾加上合適的顏文字。

                    [長期記憶資料庫]：
                    {longterm_str}

                    [當前對話者資訊]：
                    - 暱稱: {message.author.display_name}
                    - ID: {message.author.id}
                    - 匹配到的個人資料/備註: {profile_desc}

                    [注意事項]：
                    對話歷史中每則使用者發言格式為 `[暱稱 | ID: 使用者ID]: 內容`。
                    請善用發言者的 ID、暱稱與長期記憶進行個人化互動；若長期記憶中有對應身分（如特定稱呼或喜好，多個名稱請擇一稱呼），請以此為依據親切自然地稱呼與互動。
                """)

                messages = [
                    {
                        "role": "system",
                        "content": system_content
                    }
                ] + self.chat_history[channel_id]

                # 呼叫 API
                response = await self.ai_client.chat.completions.create(
                    model = self.model_name,
                    messages = messages,
                    temperature = 0.7,
                    max_tokens = 1024
                )
                
                reply = response.choices[0].message.content

                # 將 AI 的回答寫入對話歷史並即時存檔
                self.chat_history[channel_id].append({"role": "assistant", "content": reply})
                self.save_memory()

                # 發送訊息（優先使用 reply，若被刪除等情況則 fallback 為 channel.send）
                if len(reply) > 2000:
                    chunks = [reply[i:i+1900] for i in range(0, len(reply), 1900)]
                    for i, chunk in enumerate(chunks):
                        if i == 0:
                            try:
                                await message.reply(chunk)

                            except discord.HTTPException:
                                await message.channel.send(chunk)

                        else:
                            await message.channel.send(chunk)
                else:
                    try:
                        await message.reply(reply)

                    except discord.HTTPException:
                        await message.channel.send(reply)

            except Exception as e:
                await message.channel.send(f"[x] 呼叫 Groq API 時發生錯誤：```{str(e)}```")

    @commands.command(name="cclear")
    async def content_clear(self, ctx: commands.Context):
        channel_id = ctx.channel.id
        if channel_id in self.chat_history:
            del self.chat_history[channel_id]
            self.save_memory()
            await ctx.reply("[v] Sumi 已經忘記本頻道的上下文囉！")
        else:
            await ctx.reply("[x] 本頻道目前沒有任何對話記憶喔。")

async def setup(bot: commands.Bot):
    await bot.add_cog(GroqAICog(bot))