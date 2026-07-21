import discord
from discord.ext import commands

import yt_dlp
import asyncio
from config import GLOBAL_COGS

YTDL_OPTIONS = {
    'format': 'ba/ba*/bestaudio/best', # 優先選擇純音訊軌
    'extract_flat': 'in_playlist',     # 快速載入清單
    'nocheckcertificate': True,
    'ignoreerrors': True,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/115.0.0.0 Safari/537.36',
        'Referer': 'https://www.bilibili.com/'
    }
}

FFMPEG_OPTIONS = {
    'before_options': (
        '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 '
        '-probesize 10000000 -analyzeduration 10000000 '
        '-headers "Referer: https://www.bilibili.com/\r\n'
        'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/115.0.0.0 Safari/537.36\r\n"'
    ),
    # -ar 48000 (固定 48kHz, 解決加速問題), -ac 2 (雙聲道)
    'options': '-vn -ar 48000 -ac 2'
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

class MusicBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.title = "音樂功能"
        self.description = "播放音樂! 支援YT與Bilibili"
        self.emoji = "🎵"
        self.color = discord.Color.blue()

        GLOBAL_COGS["music"] = self
        
        # 佇列與播放狀態管理 (以伺服器 guild.id 作為 Key)
        self.music_queues = {}  # 存放各伺服器的歌曲列表: {guild_id: [{"title": str, "url": str}, ...]}
        self.current_songs = {} # 存放各伺服器當前播放的歌曲項目
        self.play_next_events = {} # 各伺服器的非同步事件，用於通知播放下一首
        self.volumes = {}       # 存放各伺服器的音量設定，預設 0.5 (50%)

    def get_queue(self, guild_id):
        if guild_id not in self.music_queues:
            self.music_queues[guild_id] = []
        return self.music_queues[guild_id]
    
    def format_duration(self, seconds):
        # 將秒數轉換為 MM:SS 或 HH:MM:SS
        if not seconds:
            return "未知時長"
        seconds = int(seconds)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    async def audio_player_task(self, ctx:commands.Context):
        # 負責循環檢查佇列並播放歌曲
        guild_id = ctx.guild.id
        self.play_next_events[guild_id] = asyncio.Event()

        while ctx.voice_client and ctx.voice_client.is_connected():
            queue = self.get_queue(guild_id)
            
            if len(queue) == 0:
                self.current_songs[guild_id] = None
                await ctx.send("📭 佇列中的歌曲已播放完畢。")
                break

            # 取出佇列第一首
            current_song = queue.pop(0)
            self.current_songs[guild_id] = current_song

            # 播放前才解析真正的音訊 URL
            loop = asyncio.get_event_loop()
            try:
                real_data = await loop.run_in_executor(None, lambda: ytdl.extract_info(current_song['url'], download=False))
                
                if 'entries' in real_data and len(real_data['entries']) > 0:
                    real_data = real_data['entries'][0]
                    
                real_url = real_data['url']
                
                # 【新增此段】若解析時拿到了更精確的標題（例如特定的分 P 標題），即時更新它
                updated_title = real_data.get('part') or real_data.get('title')
                if updated_title:
                    current_song['title'] = updated_title

            except Exception as e:
                await ctx.send(f"⚠️ 無法播放 **{current_song['title']}**，已自動跳過。")
                self.play_next_events[guild_id].set()
                await self.play_next_events[guild_id].wait()
                continue

            # 設定音量控制源
            raw_source = discord.FFmpegPCMAudio(real_url, **FFMPEG_OPTIONS)
            volume = self.volumes.get(guild_id, 0.5)
            source = discord.PCMVolumeTransformer(raw_source, volume=volume)

            self.play_next_events[guild_id].clear()
            
            def after_playing(error):
                if error:
                    print(f"播放出錯: {error}")
                ctx.bot.loop.call_soon_threadsafe(self.play_next_events[guild_id].set)

            ctx.voice_client.play(source, after=after_playing)
            duration_str = current_song.get('duration', '未知時長')
            await ctx.send(f"🎵 正在播放： `{current_song['title']}` [{duration_str}]  \n-# 當前音量：{int(volume * 100)}%")

            # 等待當前歌曲結束
            await self.play_next_events[guild_id].wait()

    @commands.command(name="join", description="讓機器人加入語音頻道")
    async def join(self, ctx:commands.Context):
        if not ctx.author.voice:
            return await ctx.reply("❌ 你必須先加入一個語音頻道！")
        
        channel = ctx.author.voice.channel
        if ctx.voice_client:
            await ctx.voice_client.move_to(channel)
        else:
            await channel.connect()
        await ctx.reply(f"📥 已加入： **{channel.name}**")

    @commands.command(name="leave", description="離開語音頻道並清空佇列")
    async def leave(self, ctx:commands.Context):
        guild_id = ctx.guild.id
        
        if ctx.voice_client:
            # 清空該伺服器的播放資料
            if guild_id in self.music_queues:
                self.music_queues[guild_id] = []
            if guild_id in self.current_songs:
                self.current_songs[guild_id] = None
                
            await ctx.voice_client.disconnect()
            await ctx.reply("👋 已離開語音頻道並清空佇列。")

        else:
            await ctx.reply("❌ 我目前不在任何語音頻道中。")

    @commands.command(name="play", usage="<url: YT/Bilibili>", description="添加播放佇列")
    async def play(self, ctx:commands.Context, *, url):
        guild_id = ctx.guild.id

        if not ctx.voice_client:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                return await ctx.reply("❌ 你必須先加入一個語音頻道！")

        async with ctx.typing():
            loop = asyncio.get_event_loop()
            
            try:
                data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
            except Exception as e:
                return await ctx.reply(f"❌ 無法讀取該連結或歌曲: {e}")

            if not data:
                return await ctx.reply("❌ 找不到任何音樂資訊。")

            queue = self.get_queue(guild_id)
            added_count = 0

            # 判斷是否為播放清單 (包含 YouTube Playlist、B站分P、B站合集)
            is_playlist = 'entries' in data and len(data['entries']) > 1

            if is_playlist:
                main_title = data.get('title', '播放清單 / 分P合集')
                
                for idx, entry in enumerate(data['entries'], start=1):
                    if entry:  # 排除可能被刪除或私人的影片
                        # 1. 提取 URL
                        video_url = entry.get('url') or entry.get('webpage_url')
                        if not video_url and entry.get('id'):
                            video_url = f"https://www.youtube.com/watch?v={entry.get('id')}"

                        # 2. 提取正確的歌曲名稱
                        # --- 針對 B站收藏夾 Flat 模式的標題優化 ---
                        song_title = (
                            entry.get('title') or 
                            entry.get('part') or 
                            entry.get('page_title')
                        )

                        # 如果 Flat 模式下完全拿不到標題 (B站收藏夾常見狀況)
                        if not song_title or song_title == 'None':
                            # 嘗試拿 BV號/網址當作臨時名稱，避免顯示未知標題
                            bvid = entry.get('id') or video_url.split('/')[-1]
                            song_title = f"{bvid}"

                        # 擷取時間長度
                        duration_sec = entry.get('duration')
                        duration_str = self.format_duration(duration_sec)

                        song_item = {
                            'url': video_url,
                            'title': song_title,
                            'duration': duration_str  # <--- 新增此欄位
                        }
                        queue.append(song_item)
                        added_count += 1
                
                await ctx.reply(f"📚 已成功將播放清單/合集 **{main_title}** (共 {added_count} 首歌曲) 匯入佇列！")

            # 單曲或關鍵字搜尋結果
            else:

                if 'entries' in data and len(data['entries']) > 0:
                    data = data['entries'][0]

                video_url = data.get('webpage_url') or data.get('url') or f"https://www.youtube.com/watch?v={data.get('id')}"
                
                # 單曲歌名與時間抓取
                # --- B站單曲/單集標題解析邏輯 ---
                # 某些 B站單集影片會將真正的標題放在 part 或 title 中
                song_title = (
                    data.get('part') or 
                    data.get('title') or 
                    "未知歌曲"
                )
                duration_sec = data.get('duration')
                duration_str = self.format_duration(duration_sec)

                song_item = {
                    'url': video_url,
                    'title': song_title,
                    'duration': duration_str
                }
                queue.append(song_item)
                await ctx.reply(f"⏳ 已加入佇列： **{song_item['title']}** [{duration_str}] \n-# 目前順位: #{len(queue)}")

        # 檢查是否需要啟動播放任務
        if not ctx.voice_client.is_playing() and not ctx.voice_client.is_paused() and not self.current_songs.get(guild_id):
            self.bot.loop.create_task(self.audio_player_task(ctx))

    @commands.command(name="queue", description="查看目前的歌曲佇列", aliases=["q"])
    async def queue(self, ctx:commands.Context):
        guild_id = ctx.guild.id
        queue = self.get_queue(guild_id)
        current = self.current_songs.get(guild_id)

        if not current and len(queue) == 0:
            return await ctx.reply("📭 目前沒有正在播放的歌曲，佇列也是空的。")

        embed = discord.Embed(title="🎵 當前播放清單", color=discord.Color.blue())
        
        if current:
            current_duration = current.get('duration', '未知時長')
            embed.add_field(name="▶️ 正在播放", value=f"`{current['title']}` [{current_duration}]", inline=False)
        
        if len(queue) > 0:
            queue_list = ""

            for i, song in enumerate(queue[:10], start=1):  # 最多顯示 10 首
                song_duration = song.get('duration', '未知時長')
                queue_list += f"{i}. `{song['title']}` [{song_duration}]\n"

            if len(queue) > 10:
                queue_list += f"_...以及另外 {len(queue) - 10} 首歌曲_"
            embed.add_field(name="⏳ 稍後播放", value=queue_list, inline=False)

        else:
            embed.add_field(name="⏳ 稍後播放", value="佇列中沒有其他歌曲囉！", inline=False)

        await ctx.reply(embed=embed)

    @commands.command(name="pause", description="暫停播放")
    async def pause(self, ctx:commands.Context):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.reply("⏸️ 音樂已暫停。 \n-# 輸入 `\\resume` 恢復播放")

        else:
            await ctx.reply("❌ 目前沒有正在播放的音樂。")

    @commands.command(name="resume", description="恢復播放")
    async def resume(self, ctx:commands.Context):
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.reply("▶️ 音樂繼續播放。\n-# 輸入 `\\pause` 暫停")

        else:
            await ctx.reply("❌ 音樂並未處於暫停狀態。")

    @commands.command(name="skip", description="跳過當前歌曲")
    async def skip(self, ctx:commands.Context):
        if ctx.voice_client and (ctx.voice_client.is_playing() or ctx.voice_client.is_paused()):
            # 停止當前播放，會自動觸發 after_playing 回呼函數，進而切換到下一首
            ctx.voice_client.stop()
            await ctx.reply("⏭️ 已跳過目前歌曲。")

        else:
            await ctx.reply("❌ 目前沒有歌曲可以跳過。")

    @commands.command(name="goto", usage="<佇列位置>", description="跳過到佇列指定位置")
    async def goto(self, ctx: commands.Context, index: int):
        if not ctx.voice_client or (not ctx.voice_client.is_playing() and not ctx.voice_client.is_paused()):
            return await ctx.reply("❌ 目前沒有音樂正在播放！")

        guild_id = ctx.guild.id
        queue = self.get_queue(guild_id)

        if not queue:
            return await ctx.reply("❌ 佇列中沒有其他歌曲可跳過！")

        if index < 1 or index > len(queue):
            return await ctx.reply(f"❌ 無效的位置！請輸入 `1` 到 `{len(queue)}` 之間的號碼。")

        # 切片丟棄目標歌曲之前的項目
        # 例如要跳到 #3，則丟棄 index 0 和 1（即前兩首），讓第 3 首成為 queue 的第一首 (index 0)
        target_song = queue[index - 1]
        del queue[0 : index - 1]

        # 停止當前播放的歌曲，這會自動觸發 audio_player_task 裡面的 after_playing
        # 任務會自動從已更新的 queue 中取出第一首（即目標歌曲）開始播放
        ctx.voice_client.stop()

        await ctx.reply(f"⏩ 已直接跳至順位 **#{index}**： **{target_song['title']}**！")

    @commands.command(name="remove", usage="<佇列位置/區間(空格分開)>", description="移除佇列中特定位置或區間的歌曲")
    async def remove(self, ctx: commands.Context, start: int, end: int = None):
        guild_id = ctx.guild.id
        queue = self.get_queue(guild_id)

        if not queue:
            return await ctx.reply("❌ 佇列為空，無法刪除！")

        # 若使用者只傳入一個數字 (如 !remove 2)，把 end 設定為 start (代表單一刪除)
        if end is None:
            end = start

        # 確保輸入數字的順序正確（若使用者反著打如 3 1，自動幫調整為 1 3）
        start_idx, end_idx = min(start, end), max(start, end)

        # 檢查範圍是否合法 (1-based index)
        if start_idx < 1 or end_idx > len(queue):
            return await ctx.reply(f"❌ 無效的範圍！請輸入 `1` 到 `{len(queue)}` 之間的號碼。")

        # 轉為 Python 的 0-based 陣列索引 (切片刪除)
        # 例如刪除 1~3，相當於刪除 index 0, 1, 2 (即 queue[0:3])
        removed_items = queue[start_idx - 1 : end_idx]
        del queue[start_idx - 1 : end_idx]

        if len(removed_items) == 1:
            await ctx.reply(f"🗑️ 已從佇列中移除： **{removed_items[0]['title']}**")

        else:
            await ctx.reply(f"🗑️ 已從佇列中成功移除 `#{start_idx}` 到 `#{end_idx}` 共 `{len(removed_items)}首歌`！")

    @commands.command(name="volume", usage="<音量>", description="調整音量 (0-100)", aliases=["vol"])
    async def volume(self, ctx:commands.Context, vol:int):
        if not ctx.voice_client:
            return await ctx.reply("❌ 我不在語音頻道。")

        if vol < 0 or vol > 100:
            return await ctx.reply("❌ 音量範圍必須在 0 到 100 之間！")

        guild_id = ctx.guild.id
        # 將 0-100 轉換為 0.0 - 1.0
        transformed_volume = vol / 100
        self.volumes[guild_id] = transformed_volume

        # 如果當前正在播放，即時更新音量
        if ctx.voice_client.source:
            ctx.voice_client.source.volume = transformed_volume

        await ctx.reply(f"🔊 音量已調整為： `{vol}%`")

async def setup(bot):
    await bot.add_cog(MusicBot(bot))