import json
import math
from typing import Any, ClassVar, Dict, List, Literal, Optional, Tuple

import aiosqlite
import discord
from discord.ui import (
    ActionRow,
    Button,
    Container,
    LayoutView,
    Modal,
    Select,
    Separator,
    TextDisplay,
    TextInput,
)

from config import RAWTEXT_SQL

ALLOWED_COLUMNS = {"userID", "raw1", "raw2", "raw3"}
PAGE_SIZE = 25


def _validate_column(column_name: str) -> None:
    if column_name not in ALLOWED_COLUMNS:
        raise ValueError(f"Invalid column name: {column_name}")


def _to_compact_json(data: Any) -> str:
    """序列化為無多餘空格的緊湊 JSON 字串 (冒號、逗號無空格)。"""
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)


# ── 資料庫存取與格式轉換 ──────────────────────────────────────────────


async def rawtext_select(target_key: str, filter_key: str, filter_value: Any) -> Optional[Tuple]:
    _validate_column(target_key)
    _validate_column(filter_key)
    async with aiosqlite.connect(RAWTEXT_SQL) as db:
        query = f"SELECT {target_key} FROM rawtext WHERE {filter_key} = ?"
        async with db.execute(query, (filter_value,)) as cursor:
            return await cursor.fetchone()


async def rawtext_insert(target_key: str, value: tuple) -> None:
    _validate_column(target_key)
    async with aiosqlite.connect(RAWTEXT_SQL) as db:
        placeholders = ", ".join(["?"] * len(value))
        sql = f"INSERT INTO rawtext ({target_key}) VALUES ({placeholders})"
        await db.execute(sql, value)
        await db.commit()


async def rawtext_update(target_key: str, new_value: Any, filter_key: str, filter_value: Any) -> None:
    _validate_column(target_key)
    _validate_column(filter_key)
    async with aiosqlite.connect(RAWTEXT_SQL) as db:
        if filter_key == "userID":
            check_sql = "SELECT userID FROM rawtext WHERE userID = ?"
            async with db.execute(check_sql, (filter_value,)) as cursor:
                if await cursor.fetchone() is None:
                    await db.execute("INSERT INTO rawtext (userID) VALUES (?)", (filter_value,))

        sql = f"UPDATE rawtext SET {target_key} = ? WHERE {filter_key} = ?"
        await db.execute(sql, (new_value, filter_value))
        await db.commit()


async def get_rawtext_items(author_id: int, column: str) -> List[dict]:
    """從資料庫讀取該欄位的 rawtext 項目列表 (標準 JSON 陣列)。"""
    row = await rawtext_select(column, "userID", author_id)
    if not row or row[0] is None:
        return []

    raw_str = str(row[0]).strip()
    if not raw_str or raw_str == "None":
        return []

    try:
        parsed = json.loads(raw_str)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass

    return []


async def save_rawtext_items(author_id: int, column: str, items: List[dict]) -> str:
    """
    將 rawtext 項目列表序列化為緊湊 JSON 陣列並存入資料庫，
    直接返回格式化好的預覽字串，避免二次查詢。
    """
    if not items:
        new_val = None
    else:
        new_val = _to_compact_json(items)

    await rawtext_update(column, new_val, "userID", author_id)
    return format_rawtext_content(items)


def format_rawtext_content(items: List[dict], output_mode: bool = False) -> str:
    """將項目列表格式化為 Minecraft Rawtext 規範字串。"""
    if not items:
        return "沒有資料"

    item_strings = [_to_compact_json(item) for item in items]

    if len(item_strings) > 40 and not output_mode:
        front_part = ",".join(item_strings[:20])
        back_part = ",".join(item_strings[-20:])
        return f'{{"rawtext":[{front_part},\n ... \n{back_part}]}}'

    full_content = ",".join(item_strings)
    return f'{{"rawtext":[{full_content}]}}'


async def open_rawtext_column(author_id: int, column: str, output_mode: bool = False) -> str:
    """打開指定欄位並返回格式化好的 rawtext 字串。"""
    items = await get_rawtext_items(author_id, column)
    return format_rawtext_content(items, output_mode=output_mode)


def _render_post_submit_view(
    user: discord.User | discord.Member,
    edit_raw: str,
    mode: str,
    rawtext_content: str,
) -> "RawtextsView":
    """在 Modal 提交後建立對應模式的 View；若為 add 模式則停留在新增模式。"""
    if mode == "add":
        return (
            RawtextsView(user, f"欄位{edit_raw[-1]}．新增模式")
            .add_to_container(TextDisplay(f"```{rawtext_content}```"))
            .add_to_container(Separator())
            .add_to_container(TextsComponents(edit_raw, "add"))
        )

    return (
        RawtextsView(user, f"欄位{edit_raw[-1]}．執行模式")
        .add_to_container(TextDisplay(f"```{rawtext_content}```"))
        .add_to_container(Separator())
        .add_to_container(ExecuteButtons(user, edit_raw))
    )


# ── UI 視圖與組件 ───────────────────────────────────────────────────────


class RawtextsView(LayoutView):
    _active_views: ClassVar[Dict[int, "RawtextsView"]] = {}

    def __init__(
        self,
        author: discord.User | discord.Member,
        title: Optional[str] = None,
        timeout: float = 180.0,
    ):
        super().__init__(timeout=timeout)
        self.author = author
        self.title = title
        self.message: Optional[discord.Message] = None
        self._is_active: bool = True
        self.container = self.MyContainer(self.title)
        self.add_item(self.container)

    def add_to_container(self, item) -> "RawtextsView":
        self.container.add_item_chained(item)
        return self

    def set_message(self, message: Optional[discord.Message]) -> "RawtextsView":
        """設定所屬訊息並取消同一訊息舊 View 的逾時任務，防止 on_timeout 時間旅行。"""
        self.message = message
        if message and message.id:
            old_view = RawtextsView._active_views.get(message.id)
            if old_view is not None and old_view is not self:
                old_view._is_active = False
                old_view.timeout = None
            RawtextsView._active_views[message.id] = self
        return self

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author.id

    def disable_all_components(self) -> None:
        """遍歷並禁用本 View 及內部 Container 的所有可操作元件。"""
        def _disable(obj: Any) -> None:
            if hasattr(obj, "disabled"):
                obj.disabled = True
            if hasattr(obj, "children"):
                for child in obj.children:
                    _disable(child)

        for item in self.children:
            _disable(item)

    async def on_timeout(self) -> None:
        """逾時處理：雙重防衛確保只有當前活躍 View 才能編輯訊息。"""
        if not self._is_active:
            return
        if self.message and self.message.id:
            active = RawtextsView._active_views.get(self.message.id)
            if active is not self:
                return
        self.disable_all_components()
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass
            finally:
                if self.message and self.message.id in RawtextsView._active_views:
                    if RawtextsView._active_views[self.message.id] is self:
                        del RawtextsView._active_views[self.message.id]

    class MyContainer(Container):
        def __init__(self, title: Optional[str]):
            super().__init__()
            display_title = "## rawtext協助編寫指令" if title is None else f"## {title}"
            self.add_item(TextDisplay(display_title))
            self.add_item(Separator())

        def add_item_chained(self, item) -> "RawtextsView.MyContainer":
            self.add_item(item)
            return self

        def addItem(self, item) -> "RawtextsView.MyContainer":
            return self.add_item_chained(item)


class EditWhichRaw(ActionRow):
    def __init__(
        self,
        author: discord.User | discord.Member,
        disabled_raw: Optional[Literal["raw1", "raw2", "raw3"]] = None,
    ):
        super().__init__()
        self.author = author

        for i in range(1, 4):
            raw_name = f"raw{i}"
            btn = Button(
                label=f"欄位{i}",
                style=discord.ButtonStyle.green,
                custom_id=raw_name,
                disabled=(disabled_raw == raw_name),
            )
            btn.callback = self.button_callback
            self.add_item(btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author.id

    async def button_callback(self, interaction: discord.Interaction) -> None:
        raw_key = interaction.data.get("custom_id")
        rawtext_content = await open_rawtext_column(interaction.user.id, raw_key)

        view = (
            RawtextsView(interaction.user, f"欄位{raw_key[-1]}．預覽模式")
            .add_to_container(EditWhichRaw(interaction.user, raw_key))
            .add_to_container(TextDisplay(f"```{rawtext_content}```"))
            .add_to_container(Separator())
            .add_to_container(PreviewRawtextItems(interaction.user, raw_key))
        )
        await interaction.response.edit_message(view=view)
        view.set_message(interaction.message)


class PreviewRawtextItems(ActionRow):
    def __init__(self, author: discord.User | discord.Member, raw: str):
        super().__init__()
        self.author = author
        self.edit_raw = raw

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author.id

    @discord.ui.button(label="返回", style=discord.ButtonStyle.gray)
    async def backed(self, interaction: discord.Interaction, button: Button) -> None:
        view = RawtextsView(interaction.user).add_to_container(EditWhichRaw(interaction.user))
        await interaction.response.edit_message(view=view)
        view.set_message(interaction.message)

    @discord.ui.button(label="重置欄位", style=discord.ButtonStyle.red)
    async def reseted(self, interaction: discord.Interaction, button: Button) -> None:
        rawtext_content = await save_rawtext_items(interaction.user.id, self.edit_raw, [])

        view = (
            RawtextsView(interaction.user, f"欄位{self.edit_raw[-1]}．預覽模式")
            .add_to_container(EditWhichRaw(interaction.user, self.edit_raw))
            .add_to_container(TextDisplay(f"```{rawtext_content}```"))
            .add_to_container(Separator())
            .add_to_container(PreviewRawtextItems(interaction.user, self.edit_raw))
        )
        await interaction.response.edit_message(view=view)
        view.set_message(interaction.message)

    @discord.ui.button(label="確認選擇", style=discord.ButtonStyle.green)
    async def sured(self, interaction: discord.Interaction, button: Button) -> None:
        rawtext_content = await open_rawtext_column(interaction.user.id, self.edit_raw)

        view = (
            RawtextsView(interaction.user, f"欄位{self.edit_raw[-1]}．執行模式")
            .add_to_container(TextDisplay(f"```{rawtext_content}```"))
            .add_to_container(Separator())
            .add_to_container(ExecuteButtons(interaction.user, self.edit_raw))
        )
        await interaction.response.edit_message(view=view)
        view.set_message(interaction.message)

    @discord.ui.button(label="輸出結果", style=discord.ButtonStyle.blurple)
    async def finished(self, interaction: discord.Interaction, button: Button) -> None:
        rawtext_content = await open_rawtext_column(interaction.user.id, self.edit_raw, output_mode=True)
        await interaction.response.send_message(rawtext_content, ephemeral=True)


class ExecuteButtons(ActionRow):
    def __init__(
        self,
        author: discord.User | discord.Member,
        raw: str,
        current_mode: Optional[Literal["edit", "insert"]] = None,
    ):
        super().__init__()
        self.author = author
        self.edit_raw = raw
        self.current_mode = current_mode

        # 返回
        btn_back = Button(label="返回", style=discord.ButtonStyle.gray)
        btn_back.callback = self.backed_callback
        self.add_item(btn_back)

        # 新增
        btn_add = Button(label="新增", style=discord.ButtonStyle.blurple)
        btn_add.callback = self.added_callback
        self.add_item(btn_add)

        # 編輯（若當前已在編輯模式則禁用防呆）
        btn_edit = Button(
            label="編輯",
            style=discord.ButtonStyle.blurple,
            disabled=(current_mode == "edit"),
        )
        btn_edit.callback = self.edited_callback
        self.add_item(btn_edit)

        # 插入（若當前已在插入模式則禁用防呆）
        btn_insert = Button(
            label="插入",
            style=discord.ButtonStyle.blurple,
            disabled=(current_mode == "insert"),
        )
        btn_insert.callback = self.inserted_callback
        self.add_item(btn_insert)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author.id

    async def backed_callback(self, interaction: discord.Interaction) -> None:
        rawtext_content = await open_rawtext_column(interaction.user.id, self.edit_raw)

        view = (
            RawtextsView(interaction.user, f"欄位{self.edit_raw[-1]}．預覽模式")
            .add_to_container(EditWhichRaw(interaction.user, self.edit_raw))
            .add_to_container(TextDisplay(f"```{rawtext_content}```"))
            .add_to_container(Separator())
            .add_to_container(PreviewRawtextItems(interaction.user, self.edit_raw))
        )
        await interaction.response.edit_message(view=view)
        view.set_message(interaction.message)

    async def added_callback(self, interaction: discord.Interaction) -> None:
        rawtext_content = await open_rawtext_column(interaction.user.id, self.edit_raw)

        view = (
            RawtextsView(interaction.user, f"欄位{self.edit_raw[-1]}．新增模式")
            .add_to_container(TextDisplay(f"```{rawtext_content}```"))
            .add_to_container(Separator())
            .add_to_container(TextsComponents(self.edit_raw, "add"))
        )
        await interaction.response.edit_message(view=view)
        view.set_message(interaction.message)

    async def edited_callback(self, interaction: discord.Interaction) -> None:
        await self._render_selection_view(interaction, action="edit", page=0)

    async def inserted_callback(self, interaction: discord.Interaction) -> None:
        await self._render_selection_view(interaction, action="insert", page=0)

    async def _render_selection_view(
        self,
        interaction: discord.Interaction,
        action: Literal["edit", "insert"],
        page: int,
    ) -> None:
        items = await get_rawtext_items(interaction.user.id, self.edit_raw)
        rawtext_content = format_rawtext_content(items)
        mode_label = "編輯模式" if action == "edit" else "插入在前"

        # 在當前模式下，ExecuteButtons 將對應按鈕設為 disabled (防呆)
        view = (
            RawtextsView(interaction.user, f"欄位{self.edit_raw[-1]}．{mode_label}")
            .add_to_container(TextDisplay(f"```{rawtext_content}```"))
            .add_to_container(Separator())
            .add_to_container(ExecuteButtons(interaction.user, self.edit_raw, current_mode=action))
        )

        total_pages = max(1, math.ceil(len(items) / PAGE_SIZE))
        page = max(0, min(page, total_pages - 1))

        if items:
            view.add_to_container(RawtextItemDropdown(self.edit_raw, items, page, action))
            if total_pages > 1:
                view.add_to_container(RawtextPaginationRow(self.edit_raw, action, page, total_pages))

        await interaction.response.edit_message(view=view)
        view.set_message(interaction.message)


class RawtextItemDropdown(ActionRow):
    """單選單設計：只呈現當前頁面的 25 個項目"""

    def __init__(
        self,
        edit_raw: str,
        all_items: List[dict],
        page: int,
        action: Literal["edit", "insert"],
    ):
        super().__init__()
        self.edit_raw = edit_raw
        self.action = action
        self.page = page

        start_idx = page * PAGE_SIZE
        page_items = all_items[start_idx : start_idx + PAGE_SIZE]

        options = []
        for offset, item in enumerate(page_items):
            global_index = start_idx + offset
            json_text = _to_compact_json(item)
            label = json_text if len(json_text) <= 100 else json_text[:97] + "…"
            options.append(discord.SelectOption(label=label, value=str(global_index)))

        action_name = "編輯" if action == "edit" else "插入在前"
        select = Select(
            placeholder=f"請選擇要{action_name}的項目 (#{page+1}）",
            options=options,
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction) -> None:
        values = interaction.data.get("values", [])
        if not values:
            return

        target_index = int(values[0])
        items = await get_rawtext_items(interaction.user.id, self.edit_raw)

        if not (0 <= target_index < len(items)):
            return

        target_json = _to_compact_json(items[target_index])

        # 於插入在前模式下，預覽文本包含新文本位置，如: {新文本位置},{"text":"content"}
        if self.action == "insert":
            preview_text = f"{{新文本位置}},{target_json}"
            mode_name = "插入在前"
            component_mode = "insert"
        else:
            preview_text = target_json
            mode_name = "編輯模式"
            component_mode = "replace"

        view = (
            RawtextsView(interaction.user, f"欄位{self.edit_raw[-1]}．{mode_name}")
            .add_to_container(TextDisplay(f"```{preview_text}```"))
            .add_to_container(Separator())
            .add_to_container(TextsComponents(self.edit_raw, component_mode, target_index=target_index))
        )
        await interaction.response.edit_message(view=view)
        view.set_message(interaction.message)


class RawtextPaginationRow(ActionRow):
    """分頁控制列：上一頁 / 頁碼指示 / 下一頁"""

    def __init__(
        self,
        edit_raw: str,
        action: Literal["edit", "insert"],
        current_page: int,
        total_pages: int,
    ):
        super().__init__()
        self.edit_raw = edit_raw
        self.action = action
        self.current_page = current_page
        self.total_pages = total_pages

        btn_prev = Button(
            label="◀ 上一頁",
            style=discord.ButtonStyle.secondary,
            disabled=(current_page <= 0),
        )
        btn_prev.callback = self.prev_callback
        self.add_item(btn_prev)

        btn_info = Button(
            label=f"{current_page + 1} / {total_pages}",
            style=discord.ButtonStyle.gray,
            disabled=True,
        )
        self.add_item(btn_info)

        btn_next = Button(
            label="下一頁 ▶",
            style=discord.ButtonStyle.secondary,
            disabled=(current_page >= total_pages - 1),
        )
        btn_next.callback = self.next_callback
        self.add_item(btn_next)

    async def prev_callback(self, interaction: discord.Interaction) -> None:
        exec_buttons = ExecuteButtons(interaction.user, self.edit_raw, current_mode=self.action)
        await exec_buttons._render_selection_view(interaction, self.action, self.current_page - 1)

    async def next_callback(self, interaction: discord.Interaction) -> None:
        exec_buttons = ExecuteButtons(interaction.user, self.edit_raw, current_mode=self.action)
        await exec_buttons._render_selection_view(interaction, self.action, self.current_page + 1)


class TextsComponents(ActionRow):
    def __init__(
        self,
        raw: str,
        mode: Literal["add", "replace", "insert"],
        target_index: Optional[int] = None,
    ):
        super().__init__()
        self.edit_raw = raw
        self.mode = mode
        self.target_index = target_index

        prefix = {"add": "新增", "replace": "替換", "insert": "插入"}
        for action in ["text(文字)", "selector(選擇器)", "score(記分板)"]:
            btn = Button(
                label=f"{prefix[mode]}{action}",
                style=discord.ButtonStyle.green,
                custom_id=f"{self.mode}-{action}",
            )
            btn.callback = self.button_callback
            self.add_item(btn)

        if mode == "replace":
            delete_btn = Button(
                label="刪除文本",
                style=discord.ButtonStyle.danger,
                custom_id="delete",
            )
            delete_btn.callback = self.delete_button_callback
            self.add_item(delete_btn)

    async def button_callback(self, interaction: discord.Interaction) -> None:
        custom_id = interaction.data.get("custom_id")
        mode, action = custom_id.split("-")

        if "text" in action:
            await interaction.response.send_modal(
                TextTextInput(interaction.user, mode, self.edit_raw, self.target_index)
            )
        elif "selector" in action:
            await interaction.response.send_modal(
                SelectorTextInput(interaction.user, mode, self.edit_raw, self.target_index)
            )
        elif "score" in action:
            await interaction.response.send_modal(
                ScoreTextInput(interaction.user, mode, self.edit_raw, self.target_index)
            )

    async def delete_button_callback(self, interaction: discord.Interaction) -> None:
        items = await get_rawtext_items(interaction.user.id, self.edit_raw)
        if self.target_index is not None and 0 <= self.target_index < len(items):
            del items[self.target_index]

        rawtext_content = await save_rawtext_items(interaction.user.id, self.edit_raw, items)

        view = (
            RawtextsView(interaction.user, f"欄位{self.edit_raw[-1]}．執行模式")
            .add_to_container(TextDisplay(f"```{rawtext_content}```"))
            .add_to_container(Separator())
            .add_to_container(ExecuteButtons(interaction.user, self.edit_raw))
        )
        await interaction.response.edit_message(view=view)
        view.set_message(interaction.message)

    @discord.ui.button(label="返回", style=discord.ButtonStyle.gray)
    async def backed(self, interaction: discord.Interaction, button: Button) -> None:
        rawtext_content = await open_rawtext_column(interaction.user.id, self.edit_raw)

        view = (
            RawtextsView(interaction.user, f"欄位{self.edit_raw[-1]}．執行模式")
            .add_to_container(TextDisplay(f"```{rawtext_content}```"))
            .add_to_container(Separator())
            .add_to_container(ExecuteButtons(interaction.user, self.edit_raw))
        )
        await interaction.response.edit_message(view=view)
        view.set_message(interaction.message)


def _apply_rawtext_mutation(
    items: List[dict],
    mode: str,
    target_index: Optional[int],
    new_item: dict,
) -> List[dict]:
    """在記憶體中對項目列表執行新增/替換/插入操作。"""
    if mode == "add":
        items.append(new_item)
    elif target_index is not None:
        if mode == "replace" and 0 <= target_index < len(items):
            items[target_index] = new_item
        elif mode == "insert" and 0 <= target_index <= len(items):
            items.insert(target_index, new_item)
    return items


class TextTextInput(Modal):
    text = TextInput(label="請輸入文字", style=discord.TextStyle.short)

    def __init__(
        self,
        author: discord.User | discord.Member,
        mode: str,
        raw: str,
        target_index: Optional[int] = None,
        timeout: float = 300.0,
    ):
        self.author = author
        self.mode = mode
        self.edit_raw = raw
        self.target_index = target_index
        prefix = {"add": "新增", "replace": "替換", "insert": "插入"}.get(mode, "")
        super().__init__(title=f"{prefix}: text(文字)", timeout=timeout)

    async def on_timeout(self) -> None:
        pass

    async def on_submit(self, interaction: discord.Interaction) -> None:
        input_text = str(self.text)
        new_item = {"text": input_text}

        items = await get_rawtext_items(interaction.user.id, self.edit_raw)
        items = _apply_rawtext_mutation(items, self.mode, self.target_index, new_item)
        rawtext_content = await save_rawtext_items(interaction.user.id, self.edit_raw, items)

        view = _render_post_submit_view(interaction.user, self.edit_raw, self.mode, rawtext_content)
        await interaction.response.edit_message(view=view)
        view.set_message(interaction.message)


class SelectorTextInput(Modal):
    selector = TextInput(label="請輸入選擇對象(@a/@s等,可使用選擇器參數)", style=discord.TextStyle.short)

    def __init__(
        self,
        author: discord.User | discord.Member,
        mode: str,
        raw: str,
        target_index: Optional[int] = None,
        timeout: float = 300.0,
    ):
        self.author = author
        self.mode = mode
        self.edit_raw = raw
        self.target_index = target_index
        prefix = {"add": "新增", "replace": "替換", "insert": "插入"}.get(mode, "")
        super().__init__(title=f"{prefix}: selector(選擇器)", timeout=timeout)

    async def on_timeout(self) -> None:
        pass

    async def on_submit(self, interaction: discord.Interaction) -> None:
        input_selector = str(self.selector)
        new_item = {"selector": input_selector}

        items = await get_rawtext_items(interaction.user.id, self.edit_raw)
        items = _apply_rawtext_mutation(items, self.mode, self.target_index, new_item)
        rawtext_content = await save_rawtext_items(interaction.user.id, self.edit_raw, items)

        view = _render_post_submit_view(interaction.user, self.edit_raw, self.mode, rawtext_content)
        await interaction.response.edit_message(view=view)
        view.set_message(interaction.message)


class ScoreTextInput(Modal):
    score = TextInput(label="請填入記分板代稱", style=discord.TextStyle.short)
    name = TextInput(label="請填入選擇對象(@a/@s等,可使用選擇器參數或實體分數)", style=discord.TextStyle.short)

    def __init__(
        self,
        author: discord.User | discord.Member,
        mode: str,
        raw: str,
        target_index: Optional[int] = None,
        timeout: float = 300.0,
    ):
        self.author = author
        self.mode = mode
        self.edit_raw = raw
        self.target_index = target_index
        prefix = {"add": "新增", "replace": "替換", "insert": "插入"}.get(mode, "")
        super().__init__(title=f"{prefix}: score(記分板)", timeout=timeout)

    async def on_timeout(self) -> None:
        pass

    async def on_submit(self, interaction: discord.Interaction) -> None:
        input_score = str(self.score)
        input_name = str(self.name)
        new_item = {"score": {"objective": input_score, "name": input_name}}

        items = await get_rawtext_items(interaction.user.id, self.edit_raw)
        items = _apply_rawtext_mutation(items, self.mode, self.target_index, new_item)
        rawtext_content = await save_rawtext_items(interaction.user.id, self.edit_raw, items)

        view = _render_post_submit_view(interaction.user, self.edit_raw, self.mode, rawtext_content)
        await interaction.response.edit_message(view=view)
        view.set_message(interaction.message)