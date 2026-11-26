from typing import TYPE_CHECKING, Optional

import discord
from discord.ui import ActionRow, Button, Container, LayoutView, Separator, TextDisplay
import yt_dlp

if TYPE_CHECKING:
    from cmds.music import Music

YTDL_OPTIONS = {
    'format': 'ba/ba*/bestaudio/best', # 優先選擇純音訊軌
    'extract_flat': 'in_playlist', # 快速載入清單
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
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)


class MusicCardView(LayoutView):
    """顯示音樂狀態或加入佇列資訊的容器視圖。"""

    def __init__(self, header: str, body: str, color: discord.Color = discord.Color.blue()):
        super().__init__()
        self.add_item(self.CardContainer(header, body, color))

    class CardContainer(Container):
        def __init__(self, header: str, body: str, color: discord.Color):
            super().__init__(accent_color=color)
            self.add_item(TextDisplay(f"### {header}"))
            self.add_item(Separator())
            self.add_item(TextDisplay(body))


class QueueView(LayoutView):
    """顯示目前播放中歌曲與待播佇列的容器視圖，支援分頁。"""

    PER_PAGE = 10

    def __init__(
        self,
        current: Optional[dict],
        queue: list[dict],
        page: int = 1,
        color: discord.Color = discord.Color.blue(),
    ):
        super().__init__(timeout=300)
        self.add_item(self.QueueContainer(current, list(queue), page, color))

    class QueuePagination(ActionRow):
        def __init__(
            self,
            current: Optional[dict],
            queue: list[dict],
            page: int,
            total_pages: int,
            color: discord.Color,
        ):
            super().__init__()
            self.current = current
            self.queue = queue
            self.page = page
            self.total_pages = total_pages
            self.color = color

            prev_btn = Button(
                label="上一頁",
                emoji="◀️",
                style=discord.ButtonStyle.secondary,
                disabled=page <= 1,
            )
            prev_btn.callback = self.prev_page

            page_btn = Button(
                label=f"{page}/{total_pages}",
                style=discord.ButtonStyle.secondary,
                disabled=True,
            )

            next_btn = Button(
                label="下一頁",
                emoji="▶️",
                style=discord.ButtonStyle.secondary,
                disabled=page >= total_pages,
            )
            next_btn.callback = self.next_page

            self.add_item(prev_btn)
            self.add_item(page_btn)
            self.add_item(next_btn)

        async def prev_page(self, interaction: discord.Interaction):
            await interaction.response.edit_message(
                view=QueueView(
                    self.current,
                    self.queue,
                    page=self.page - 1,
                    color=self.color,
                )
            )

        async def next_page(self, interaction: discord.Interaction):
            await interaction.response.edit_message(
                view=QueueView(
                    self.current,
                    self.queue,
                    page=self.page + 1,
                    color=self.color,
                )
            )

    class QueueContainer(Container):
        def __init__(
            self,
            current: Optional[dict],
            queue: list[dict],
            page: int,
            color: discord.Color,
        ):
            super().__init__(accent_color=color)
            self.add_item(TextDisplay("## 當前播放清單"))
            self.add_item(Separator())

            if current:
                current_duration = current.get("duration", "未知時長")
                self.add_item(
                    TextDisplay(f"**正在播放**\n**[{current_duration}]** `{current['title']}`")
                )
                self.add_item(Separator())

            if queue:
                per_page = QueueView.PER_PAGE
                total_pages = max(1, (len(queue) + per_page - 1) // per_page)
                page = max(1, min(page, total_pages))
                start_idx = (page - 1) * per_page
                page_items = queue[start_idx : start_idx + per_page]

                lines = [
                    f"{i}. **[{song.get('duration', '未知時長')}]** `{song['title']}`"
                    for i, song in enumerate(page_items, start=start_idx + 1)
                ]
                self.add_item(TextDisplay("**稍後播放**\n" + "\n".join(lines)))

                if total_pages > 1:
                    self.add_item(
                        QueueView.QueuePagination(current, queue, page, total_pages, color)
                    )
            else:
                self.add_item(TextDisplay("**稍後播放**\n佇列中沒有其他歌曲。"))


class NowPlayingView(LayoutView):
    """顯示正在播放、下一首資訊與播放控制按鈕的容器視圖。"""

    def __init__(
        self,
        cog: "Music",
        guild_id: int,
        current_song: dict,
        next_song: Optional[dict],
        volume: float,
        is_paused: bool = False,
        color: discord.Color = discord.Color.blue(),
    ):
        super().__init__(timeout=None)
        self.container = self.NowPlayingContainer(
            cog, guild_id, current_song, next_song, volume, is_paused, color
        )
        self.add_item(self.container)

    def disable_components(self) -> None:
        """禁用當前播放卡片上的所有互動按鈕。"""
        for item in self.container.children:
            if isinstance(item, ActionRow):
                for child in item.children:
                    if isinstance(child, Button):
                        child.disabled = True

    class ControlsRow(ActionRow):
        def __init__(
            self,
            cog: "Music",
            guild_id: int,
            current_song: dict,
            is_paused: bool,
            color: discord.Color,
        ):
            super().__init__()
            self.cog = cog
            self.guild_id = guild_id
            self.current_song = current_song
            self.color = color

            toggle_btn = Button(
                label="繼續" if is_paused else "暫停",
                emoji="▶️" if is_paused else "⏸️",
                style=discord.ButtonStyle.primary if is_paused else discord.ButtonStyle.secondary,
            )
            toggle_btn.callback = self.toggle_pause

            next_btn = Button(
                label="下一首",
                emoji="⏭️",
                style=discord.ButtonStyle.secondary,
            )
            next_btn.callback = self.skip_song

            queue_btn = Button(
                label="播放清單",
                emoji="📜",
                style=discord.ButtonStyle.secondary,
            )
            queue_btn.callback = self.show_queue

            self.add_item(toggle_btn)
            self.add_item(next_btn)
            self.add_item(queue_btn)

        async def toggle_pause(self, interaction: discord.Interaction):
            voice_client = interaction.guild.voice_client if interaction.guild else None
            if not voice_client or (not voice_client.is_playing() and not voice_client.is_paused()):
                return await interaction.response.send_message(
                    "目前沒有正在播放的音樂。", ephemeral=True
                )

            if voice_client.is_paused():
                voice_client.resume()
                new_paused = False
            else:
                voice_client.pause()
                new_paused = True

            queue = self.cog.get_queue(self.guild_id)
            next_song = queue[0] if queue else None
            volume = self.cog.volumes.get(self.guild_id, 0.5)

            new_view = NowPlayingView(
                self.cog,
                self.guild_id,
                self.current_song,
                next_song,
                volume,
                is_paused=new_paused,
                color=self.color,
            )
            if interaction.message:
                self.cog.now_playing_messages[self.guild_id] = (interaction.message, new_view)

            await interaction.response.edit_message(view=new_view)

        async def skip_song(self, interaction: discord.Interaction):
            voice_client = interaction.guild.voice_client if interaction.guild else None
            if not voice_client or (not voice_client.is_playing() and not voice_client.is_paused()):
                return await interaction.response.send_message(
                    "目前沒有歌曲可以跳過。", ephemeral=True
                )

            await interaction.response.defer()
            voice_client.stop()

        async def show_queue(self, interaction: discord.Interaction):
            queue = self.cog.get_queue(self.guild_id)
            current = self.cog.current_songs.get(self.guild_id)
            if not current and not queue:
                return await interaction.response.send_message(
                    "目前沒有正在播放的歌曲，佇列也是空的。", ephemeral=True
                )

            await interaction.response.send_message(
                view=QueueView(current, queue, color=self.color),
                ephemeral=True,
            )

    class NowPlayingContainer(Container):
        def __init__(
            self,
            cog: "Music",
            guild_id: int,
            current_song: dict,
            next_song: Optional[dict],
            volume: float,
            is_paused: bool,
            color: discord.Color,
        ):
            super().__init__(accent_color=color)
            self.add_item(TextDisplay("### 正在播放"))
            self.add_item(Separator())

            duration_str = current_song.get("duration", "未知時長")
            self.add_item(
                TextDisplay(f"**[{duration_str}]** `{current_song['title']}`")
            )
            self.add_item(Separator())

            if next_song:
                next_duration = next_song.get("duration", "未知時長")
                self.add_item(
                    TextDisplay(f"**下一首**\n**[{next_duration}]** `{next_song['title']}`")
                )
            else:
                self.add_item(TextDisplay("**下一首**\n佇列中沒有其他歌曲。"))

            self.add_item(
                NowPlayingView.ControlsRow(cog, guild_id, current_song, is_paused, color)
            )