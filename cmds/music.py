import asyncio
import importlib
from typing import Optional

import discord
from discord.ext import commands

from config import GLOBAL_COGS

# utils hot reload
import utils.musics
importlib.reload(utils.musics)
from utils.musics import FFMPEG_OPTIONS, ytdl


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.title = "音樂功能"
        self.description = "播放音樂！支援YT與Bilibili"
        self.emoji = "🎵"
        self.color = discord.Color.blue()

        GLOBAL_COGS["music"] = self

        # 佇列與播放狀態管理 (以伺服器 guild.id 作為 Key)
        self.music_queues: dict[int, list[dict]] = {}
        self.current_songs: dict[int, Optional[dict]] = {}
        self.play_next_events: dict[int, asyncio.Event] = {}
        self.volumes: dict[int, float] = {}  # 預設 0.5 (50%)
        self.player_locks: dict[int, asyncio.Lock] = {}

    def _get_player_lock(self, guild_id: int) -> asyncio.Lock:
        if guild_id not in self.player_locks:
            self.player_locks[guild_id] = asyncio.Lock()
        return self.player_locks[guild_id]

    def get_queue(self, guild_id: int) -> list[dict]:
        if guild_id not in self.music_queues:
            self.music_queues[guild_id] = []
        return self.music_queues[guild_id]

    def format_duration(self, seconds: Optional[int | float]) -> str:
        if not seconds:
            return "未知時長"
        seconds = int(seconds)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    async def audio_player_task(self, ctx: commands.Context):
        guild_id = ctx.guild.id
        lock = self._get_player_lock(guild_id)

        # 避免同伺服器重複啟動多個播放任務
        if lock.locked():
            return

        async with lock:
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

                # 播放前解析真正的音訊 URL
                loop = asyncio.get_event_loop()
                try:
                    real_data = await loop.run_in_executor(
                        None, lambda: ytdl.extract_info(current_song["url"], download=False)
                    )

                    if "entries" in real_data and len(real_data["entries"]) > 0:
                        real_data = real_data["entries"][0]

                    real_url = real_data["url"]
                    updated_title = real_data.get("part") or real_data.get("title")
                    if updated_title:
                        current_song["title"] = updated_title

                except Exception:
                    await ctx.send(f"⚠️ 無法播放 **{current_song['title']}**，已自動跳過。")
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
                duration_str = current_song.get("duration", "未知時長")
                await ctx.send(
                    f"🎵 正在播放： `{current_song['title']}` [{duration_str}]  \n-# 當前音量：{int(volume * 100)}%"
                )

                # 等待當前歌曲結束
                await self.play_next_events[guild_id].wait()

    @commands.command(name="join", description="讓機器人加入語音頻道")
    async def join(self, ctx: commands.Context):
        if not ctx.author.voice:
            return await ctx.reply("❌ 你必須先加入一個語音頻道！")

        channel = ctx.author.voice.channel
        if ctx.voice_client:
            await ctx.voice_client.move_to(channel)
        else:
            await channel.connect()
        await ctx.reply(f"📥 已加入： **{channel.name}**")

    @commands.command(name="leave", description="離開語音頻道並清空佇列")
    async def leave(self, ctx: commands.Context):
        guild_id = ctx.guild.id

        if ctx.voice_client:
            if guild_id in self.music_queues:
                self.music_queues[guild_id] = []
            if guild_id in self.current_songs:
                self.current_songs[guild_id] = None

            await ctx.voice_client.disconnect()
            await ctx.reply("👋 已離開語音頻道並清空佇列。")
        else:
            await ctx.reply("❌ 我目前不在任何語音頻道中。")

    @commands.command(name="play", usage="<url: YouTube/Bilibili>", description="添加播放佇列")
    async def play(self, ctx: commands.Context, *, url: str):
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
            is_playlist = "entries" in data and len(data["entries"]) > 1

            if is_playlist:
                main_title = data.get("title", "播放清單 / 分P合集")

                for entry in data["entries"]:
                    if entry:
                        video_url = entry.get("url") or entry.get("webpage_url")
                        if not video_url and entry.get("id"):
                            video_url = f"https://www.youtube.com/watch?v={entry.get('id')}"

                        song_title = (
                            entry.get("title")
                            or entry.get("part")
                            or entry.get("page_title")
                        )

                        if not song_title or song_title == "None":
                            bvid = entry.get("id") or video_url.split("/")[-1]
                            song_title = f"{bvid}"

                        duration_sec = entry.get("duration")
                        duration_str = self.format_duration(duration_sec)

                        song_item = {
                            "url": video_url,
                            "title": song_title,
                            "duration": duration_str,
                        }
                        queue.append(song_item)
                        added_count += 1

                await ctx.reply(f"📚 已成功將播放清單/合集 **{main_title}** (共 {added_count} 首歌曲) 匯入佇列！")
            else:
                if "entries" in data and len(data["entries"]) > 0:
                    data = data["entries"][0]

                video_url = (
                    data.get("webpage_url")
                    or data.get("url")
                    or f"https://www.youtube.com/watch?v={data.get('id')}"
                )
                song_title = data.get("part") or data.get("title") or "未知歌曲"
                duration_sec = data.get("duration")
                duration_str = self.format_duration(duration_sec)

                song_item = {
                    "url": video_url,
                    "title": song_title,
                    "duration": duration_str,
                }
                queue.append(song_item)
                await ctx.reply(f"⏳ 已加入佇列： **{song_item['title']}** [{duration_str}] \n-# 目前順位: #{len(queue)}")

        # 啟動播放任務
        if not ctx.voice_client.is_playing() and not ctx.voice_client.is_paused() and not self.current_songs.get(guild_id):
            self.bot.loop.create_task(self.audio_player_task(ctx))

    @commands.command(name="queue", description="查看目前的歌曲佇列", aliases=["q"])
    async def queue(self, ctx: commands.Context):
        guild_id = ctx.guild.id
        queue = self.get_queue(guild_id)
        current = self.current_songs.get(guild_id)

        if not current and len(queue) == 0:
            return await ctx.reply("📭 目前沒有正在播放的歌曲，佇列也是空的。")

        embed = discord.Embed(title="🎵 當前播放清單", color=discord.Color.blue())

        if current:
            current_duration = current.get("duration", "未知時長")
            embed.add_field(name="▶️ 正在播放", value=f"`{current['title']}` [{current_duration}]", inline=False)

        if len(queue) > 0:
            queue_list = ""
            for i, song in enumerate(queue[:10], start=1):
                song_duration = song.get("duration", "未知時長")
                queue_list += f"{i}. `{song['title']}` [{song_duration}]\n"

            if len(queue) > 10:
                queue_list += f"_...以及另外 {len(queue) - 10} 首歌曲_"
            embed.add_field(name="⏳ 稍後播放", value=queue_list, inline=False)
        else:
            embed.add_field(name="⏳ 稍後播放", value="佇列中沒有其他歌曲囉！", inline=False)

        await ctx.reply(embed=embed)

    @commands.command(name="pause", description="暫停播放")
    async def pause(self, ctx: commands.Context):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.reply("⏸️ 音樂已暫停。 \n-# 輸入 `\\resume` 恢復播放")
        else:
            await ctx.reply("❌ 目前沒有正在播放的音樂。")

    @commands.command(name="resume", description="恢復播放")
    async def resume(self, ctx: commands.Context):
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.reply("▶️ 音樂繼續播放。\n-# 輸入 `\\pause` 暫停")
        else:
            await ctx.reply("❌ 音樂並未處於暫停狀態。")

    @commands.command(name="skip", description="跳過當前歌曲")
    async def skip(self, ctx: commands.Context):
        if ctx.voice_client and (ctx.voice_client.is_playing() or ctx.voice_client.is_paused()):
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

        target_song = queue[index - 1]
        del queue[0 : index - 1]

        ctx.voice_client.stop()
        await ctx.reply(f"⏩ 已直接跳至順位 **#{index}**： **{target_song['title']}**！")

    @commands.command(name="remove", usage="<佇列位置/區間(空格分開)>", description="移除佇列中特定位置或區間的歌曲")
    async def remove(self, ctx: commands.Context, start: int, end: Optional[int] = None):
        guild_id = ctx.guild.id
        queue = self.get_queue(guild_id)

        if not queue:
            return await ctx.reply("❌ 佇列為空，無法刪除！")

        if end is None:
            end = start

        start_idx, end_idx = min(start, end), max(start, end)

        if start_idx < 1 or end_idx > len(queue):
            return await ctx.reply(f"❌ 無效的範圍！請輸入 `1` 到 `{len(queue)}` 之間的號碼。")

        removed_items = queue[start_idx - 1 : end_idx]
        del queue[start_idx - 1 : end_idx]

        if len(removed_items) == 1:
            await ctx.reply(f"🗑️ 已從佇列中移除： **{removed_items[0]['title']}**")
        else:
            await ctx.reply(f"🗑️ 已從佇列中成功移除 `#{start_idx}` 到 `#{end_idx}` 共 `{len(removed_items)}首歌`！")

    @commands.command(name="volume", usage="<音量>", description="調整音量 (0-100)", aliases=["vol"])
    async def volume(self, ctx: commands.Context, vol: int):
        if not ctx.voice_client:
            return await ctx.reply("❌ 我不在語音頻道。")

        if vol < 0 or vol > 100:
            return await ctx.reply("❌ 音量範圍必須在 0 到 100 之間！")

        guild_id = ctx.guild.id
        transformed_volume = vol / 100
        self.volumes[guild_id] = transformed_volume

        if ctx.voice_client.source:
            ctx.voice_client.source.volume = transformed_volume

        await ctx.reply(f"🔊 音量已調整為： `{vol}%`")


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))