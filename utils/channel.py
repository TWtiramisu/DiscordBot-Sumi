import json
import os
import aiosqlite
import discord


class ChannelDB:
    def __init__(self, db_path: str = "db/channel.db"):
        self.db_path = db_path

    async def init_db(self):
        """初始化資料庫與資料表"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS server_channels (
                    server_id INTEGER PRIMARY KEY,
                    channel_ids TEXT NOT NULL DEFAULT '[]'
                )
            """)
            await db.commit()

    async def get_channels(self, server_id: int) -> list[int]:
        """取得指定伺服器的對話頻道清單"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT channel_ids FROM server_channels WHERE server_id = ?",
                    (server_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row and row[0]:
                        return json.loads(row[0])
            return []
        except Exception as e:
            print(f"[!] 讀取對話頻道失敗: {e}")
            return []

    async def set_channels(self, server_id: int, channel_ids: list[int]):
        """寫入指定伺服器的對話頻道清單"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO server_channels (server_id, channel_ids) VALUES (?, ?)
                    ON CONFLICT(server_id) DO UPDATE SET channel_ids = excluded.channel_ids
                """, (server_id, json.dumps(channel_ids)))
                await db.commit()
        except Exception as e:
            print(f"[!] 儲存對話頻道失敗: {e}")

    async def add_channels(self, server_id: int, new_channel_ids: list[int]) -> tuple[list[int], list[int]]:
        """新增對話頻道，回傳 (更新後清單, 實際新增清單)"""
        current = await self.get_channels(server_id)
        current_set = set(current)
        added = []
        for cid in new_channel_ids:
            if cid not in current_set:
                current.append(cid)
                current_set.add(cid)
                added.append(cid)
        if added:
            await self.set_channels(server_id, current)
        return current, added

    async def remove_channels(self, server_id: int, remove_channel_ids: list[int]) -> tuple[list[int], int]:
        """移除對話頻道，回傳 (更新後清單, 實際刪除數量)"""
        current = await self.get_channels(server_id)
        remove_set = set(remove_channel_ids)
        updated = [cid for cid in current if cid not in remove_set]
        removed_count = len(current) - len(updated)
        if removed_count > 0:
            await self.set_channels(server_id, updated)
        return updated, removed_count

    async def get_all_servers(self) -> dict[int, list[int]]:
        """讀取所有伺服器的頻道清單"""
        result = {}
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute("SELECT server_id, channel_ids FROM server_channels") as cursor:
                    rows = await cursor.fetchall()
                    for row in rows:
                        try:
                            result[int(row[0])] = json.loads(row[1])
                        except Exception:
                            result[int(row[0])] = []
        except Exception as e:
            print(f"[!] 載入全部伺服器對話頻道失敗: {e}")
        return result


class AddChannelModal(discord.ui.Modal, title="新增對話頻道"):
    channel_input = discord.ui.TextInput(
        label="請輸入頻道 ID（空格分開）",
        style=discord.TextStyle.short,
        placeholder="例如: 123456789 987654321",
        required=True,
        max_length=500
    )

    def __init__(self, parent_view: "TalkChannelView"):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        raw_text = self.channel_input.value.strip()
        valid_ids: list[int] = []
        for part in raw_text.split():
            try:
                cid = int(part)
                if cid > 0 and cid not in valid_ids:
                    valid_ids.append(cid)
            except ValueError:
                continue

        if not valid_ids:
            await interaction.response.send_message("[x] 未輸入任何有效的頻道 ID。", ephemeral=True)
            return

        updated_channels, added_ids = await self.parent_view.cog.add_talk_channels(
            self.parent_view.guild.id,
            valid_ids
        )
        self.parent_view.channels = updated_channels
        self.parent_view.selected_ids.clear()
        self.parent_view.setup_components()

        if added_ids:
            notice = f"[v] 已成功新增 {len(added_ids)} 個對話頻道。"
        else:
            notice = "[!] 輸入的頻道皆已在清單中。"

        content = self.parent_view.get_content(notice=notice)
        await interaction.response.edit_message(content=content, view=self.parent_view)


class TalkChannelSelect(discord.ui.Select):
    def __init__(self, parent_view: "TalkChannelView", options: list[discord.SelectOption]):
        super().__init__(
            placeholder="請選擇欲刪除的頻道（可複選）",
            min_values=0,
            max_values=len(options),
            options=options,
            row=0
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        values = [int(v) for v in self.values]
        self.parent_view.selected_ids = set(values)
        self.parent_view.setup_components()
        content = self.parent_view.get_content()
        await interaction.response.edit_message(content=content, view=self.parent_view)


class TalkChannelView(discord.ui.View):
    def __init__(
        self,
        cog,
        guild: discord.Guild,
        author_id: int,
        channels: list[int],
        timeout: float = 120.0
    ):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.guild = guild
        self.author_id = author_id
        self.channels = channels
        self.selected_ids: set[int] = set()
        self.message: discord.Message | None = None

        self.setup_components()

    def setup_components(self):
        """根據當前狀態重新組裝元件"""
        self.clear_items()

        # 狀態一：有被選取的項目 -> 顯示選單、刪除所選按鈕、取消刪除按鈕
        if self.selected_ids:
            options = self._build_options()
            if options:
                self.add_item(TalkChannelSelect(self, options))

            btn_delete = discord.ui.Button(
                label=f"刪除所選 ({len(self.selected_ids)})",
                style=discord.ButtonStyle.danger,
                row=1
            )
            btn_delete.callback = self.on_click_delete
            self.add_item(btn_delete)

            btn_cancel = discord.ui.Button(
                label="取消刪除",
                style=discord.ButtonStyle.secondary,
                row=1
            )
            btn_cancel.callback = self.on_click_cancel
            self.add_item(btn_cancel)

        # 狀態二：未選取任何項目 -> 顯示選單（若有頻道）與新增頻道按鈕
        else:
            options = self._build_options()
            if options:
                self.add_item(TalkChannelSelect(self, options))

            btn_add = discord.ui.Button(
                label="新增頻道",
                style=discord.ButtonStyle.primary,
                row=1 if options else 0
            )
            btn_add.callback = self.on_click_add
            self.add_item(btn_add)

    def _build_options(self) -> list[discord.SelectOption]:
        """建立選單選項（最多支援 25 個）"""
        options: list[discord.SelectOption] = []
        for cid in self.channels[:25]:
            ch = self.guild.get_channel(cid)
            name = ch.name if ch else f"未知頻道 ({cid})"
            is_selected = (cid in self.selected_ids)
            options.append(
                discord.SelectOption(
                    label=name[:100],
                    description=f"ID: {cid}"[:100],
                    value=str(cid),
                    default=is_selected
                )
            )
        return options

    def get_content(self, notice: str = "") -> str:
        """產生提示文字"""
        lines = []
        if notice:
            lines.append(notice)
            lines.append("")

        if self.selected_ids:
            lines.append(f"已選取 {len(self.selected_ids)} 個頻道，請確認是否刪除或取消刪除：")
        elif self.channels:
            lines.append(f"目前伺服器已設定的指定對話頻道（共 {len(self.channels)} 個）：")
        else:
            lines.append("目前伺服器尚未設定任何指定對話頻道，請點擊下方按鈕新增。")

        return "\n".join(lines)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("[x] 只有指令發起者可以操作此選單。", ephemeral=True)
            return False
        return True

    async def on_click_add(self, interaction: discord.Interaction):
        modal = AddChannelModal(parent_view=self)
        await interaction.response.send_modal(modal)

    async def on_click_cancel(self, interaction: discord.Interaction):
        self.selected_ids.clear()
        self.setup_components()
        content = self.get_content()
        await interaction.response.edit_message(content=content, view=self)

    async def on_click_delete(self, interaction: discord.Interaction):
        to_remove = list(self.selected_ids)
        updated_channels, removed_count = await self.cog.remove_talk_channels(
            self.guild.id,
            to_remove
        )
        self.channels = updated_channels
        self.selected_ids.clear()
        self.setup_components()

        notice = f"[v] 已成功刪除 {removed_count} 個指定頻道。"
        content = self.get_content(notice=notice)
        await interaction.response.edit_message(content=content, view=self)

    async def on_timeout(self):
        if self.message:
            try:
                for item in self.children:
                    item.disabled = True
                await self.message.edit(view=self)
            except Exception:
                pass
