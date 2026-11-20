import discord
from discord.ui import ActionRow, Button, Container, LayoutView, Modal, Select, Separator, TextDisplay, TextInput

import json
import aiosqlite
from typing import Any, List, Literal, Optional, Tuple
from config import DIV, RAWTEXT_SQL

ALLOWED_COLUMNS = {"userID", "raw1", "raw2", "raw3"}

def _validate_column(column_name: str) -> None:
    if column_name not in ALLOWED_COLUMNS:
        raise ValueError(f"Invalid column name: {column_name}")


async def rawtext_select(target_key: str, filter_key: str, filter_value: Any) -> Optional[Tuple]:
    _validate_column(target_key)
    _validate_column(filter_key)
    async with aiosqlite.connect(RAWTEXT_SQL) as db:
        query = f"SELECT {target_key} FROM rawtext WHERE {filter_key} = ?"
        async with db.execute(query, (filter_value,)) as cursor:
            result = await cursor.fetchone()
            return result


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
        # 確保該使用者存在於資料庫中，避免更新 0 筆資料
        if filter_key == "userID":
            check_sql = "SELECT userID FROM rawtext WHERE userID = ?"
            async with db.execute(check_sql, (filter_value,)) as cursor:
                if await cursor.fetchone() is None:
                    await db.execute("INSERT INTO rawtext (userID) VALUES (?)", (filter_value,))

        sql = f"UPDATE rawtext SET {target_key} = ? WHERE {filter_key} = ?"
        await db.execute(sql, (new_value, filter_value))
        await db.commit()


async def open_rawtext_column(author_id: int, column: str, output_mode: bool = False) -> str:
    """打開指定欄位並返回格式化好的 rawtext 字串。"""
    result = await rawtext_select(column, "userID", author_id)

    if not result or result[0] is None or str(result[0]).strip() in ("", "None"):
        return "沒有資料"

    raw_list = str(result[0]).split(DIV)
    if raw_list and raw_list[-1] == "":
        raw_list = raw_list[:-1]

    if not raw_list:
        return "沒有資料"

    if len(raw_list) > 40 and not output_mode:
        front_part = ",".join(raw_list[:20])
        back_part = ",".join(raw_list[-20:])
        rawtext_content = f'{{"rawtext":[{front_part},\n ... \n{back_part}]}}'
    else:
        full_content = ",".join(raw_list)
        rawtext_content = f'{{"rawtext":[{full_content}]}}'

    return rawtext_content


async def make_rawtext_list(author_id: int, edit_raw: str) -> List[List[str]]:
    """將 rawtext 內容處理成二維列表（防止 discord.ui.Select 選項超過 25 項上限）。"""
    the_raw = await rawtext_select(edit_raw, "userID", author_id)
    if not the_raw or the_raw[0] is None or str(the_raw[0]).strip() in ("", "None"):
        return []

    raw_list = str(the_raw[0]).split(DIV)
    if raw_list and raw_list[-1] == "":
        raw_list = raw_list[:-1]

    processed_list = []
    for index in range(0, len(raw_list), 25):
        processed_list.append(raw_list[index : index + 25])

    return processed_list


class RawtextsView(LayoutView):
    def __init__(self, author: discord.User | discord.Member, title: Optional[str] = None):
        super().__init__()
        self.author = author
        self.title = title
        self.container = self.MyContainer(self.title)
        self.add_item(self.container)

    def add_to_container(self, item) -> "RawtextsView":
        self.container.add_item_chained(item)
        return self

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author.id

    class MyContainer(Container):
        def __init__(self, title: Optional[str]):
            super().__init__()
            display_title = "## rawtext協助編寫指令" if title is None else f"## {title}"
            self.add_item(TextDisplay(display_title))
            self.add_item(Separator())

        def add_item_chained(self, item) -> "RawtextsView.MyContainer":
            self.add_item(item)
            return self

        # 保留舊方法名稱以防外部引用
        def addItem(self, item) -> "RawtextsView.MyContainer":
            return self.add_item_chained(item)


class EditWhichRaw(ActionRow):
    def __init__(self, author: discord.User | discord.Member, disabled_raw: Optional[Literal["raw1", "raw2", "raw3"]] = None):
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

    @discord.ui.button(label="重置欄位", style=discord.ButtonStyle.red)
    async def reseted(self, interaction: discord.Interaction, button: Button) -> None:
        await rawtext_update(self.edit_raw, None, "userID", interaction.user.id)
        rawtext_content = await open_rawtext_column(interaction.user.id, self.edit_raw)

        view = (
            RawtextsView(interaction.user, f"欄位{self.edit_raw[-1]}．預覽模式")
            .add_to_container(EditWhichRaw(interaction.user, self.edit_raw))
            .add_to_container(TextDisplay(f"```{rawtext_content}```"))
            .add_to_container(Separator())
            .add_to_container(PreviewRawtextItems(interaction.user, self.edit_raw))
        )
        await interaction.response.edit_message(view=view)

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

    @discord.ui.button(label="輸出結果", style=discord.ButtonStyle.blurple)
    async def finished(self, interaction: discord.Interaction, button: Button) -> None:
        rawtext_content = await open_rawtext_column(interaction.user.id, self.edit_raw, output_mode=True)
        await interaction.response.send_message(rawtext_content, ephemeral=True)


class ExecuteButtons(ActionRow):
    def __init__(self, author: discord.User | discord.Member, raw: str):
        super().__init__()
        self.author = author
        self.edit_raw = raw

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author.id

    @discord.ui.button(label="返回", style=discord.ButtonStyle.gray)
    async def backed(self, interaction: discord.Interaction, button: Button) -> None:
        rawtext_content = await open_rawtext_column(interaction.user.id, self.edit_raw)

        view = (
            RawtextsView(interaction.user, f"欄位{self.edit_raw[-1]}．預覽模式")
            .add_to_container(EditWhichRaw(interaction.user, self.edit_raw))
            .add_to_container(TextDisplay(f"```{rawtext_content}```"))
            .add_to_container(Separator())
            .add_to_container(PreviewRawtextItems(interaction.user, self.edit_raw))
        )
        await interaction.response.edit_message(view=view)

    @discord.ui.button(label="新增", style=discord.ButtonStyle.blurple)
    async def added(self, interaction: discord.Interaction, button: Button) -> None:
        rawtext_content = await open_rawtext_column(interaction.user.id, self.edit_raw)

        view = (
            RawtextsView(interaction.user, f"欄位{self.edit_raw[-1]}．新增模式")
            .add_to_container(TextDisplay(f"```{rawtext_content}```"))
            .add_to_container(Separator())
            .add_to_container(TextsComponents(self.edit_raw, "add"))
        )
        await interaction.response.edit_message(view=view)

    @discord.ui.button(label="編輯", style=discord.ButtonStyle.blurple)
    async def edited(self, interaction: discord.Interaction, button: Button) -> None:
        rawtext_content = await open_rawtext_column(interaction.user.id, self.edit_raw)

        view = (
            RawtextsView(interaction.user, f"欄位{self.edit_raw[-1]}．編輯模式")
            .add_to_container(TextDisplay(f"```{rawtext_content}```"))
            .add_to_container(Separator())
            .add_to_container(ExecuteButtons(interaction.user, self.edit_raw))
        )
        processed_rawtext_list = await make_rawtext_list(interaction.user.id, self.edit_raw)
        for first_index, nested_list_content in enumerate(processed_rawtext_list):
            view.add_to_container(RawtextItemDropdown(self.edit_raw, nested_list_content, first_index, "edit"))

        await interaction.response.edit_message(view=view)

    @discord.ui.button(label="插入", style=discord.ButtonStyle.blurple)
    async def inserted(self, interaction: discord.Interaction, button: Button) -> None:
        rawtext_content = await open_rawtext_column(interaction.user.id, self.edit_raw)

        view = (
            RawtextsView(interaction.user, f"欄位{self.edit_raw[-1]}．插入模式")
            .add_to_container(TextDisplay(f"```{rawtext_content}```"))
            .add_to_container(Separator())
            .add_to_container(ExecuteButtons(interaction.user, self.edit_raw))
        )
        processed_rawtext_list = await make_rawtext_list(interaction.user.id, self.edit_raw)
        for first_index, nested_list_content in enumerate(processed_rawtext_list):
            view.add_to_container(RawtextItemDropdown(self.edit_raw, nested_list_content, first_index, "insert"))

        await interaction.response.edit_message(view=view)


class TextsComponents(ActionRow):
    def __init__(
        self,
        raw: str,
        mode: Literal["add", "replace", "insert"],
        rawtext_position: Optional[str] = None,
    ):
        super().__init__()
        self.edit_raw = raw
        self.mode = mode
        self.rawtext_position = rawtext_position

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
                TextTextInput(interaction.user, mode, self.edit_raw, self.rawtext_position)
            )
        elif "selector" in action:
            await interaction.response.send_modal(
                SelectorTextInput(interaction.user, mode, self.edit_raw, self.rawtext_position)
            )
        elif "score" in action:
            await interaction.response.send_modal(
                ScoreTextInput(interaction.user, mode, self.edit_raw, self.rawtext_position)
            )

    async def delete_button_callback(self, interaction: discord.Interaction) -> None:
        processed_rawtext_list = await make_rawtext_list(interaction.user.id, self.edit_raw)
        if self.rawtext_position and processed_rawtext_list:
            position = self.rawtext_position.split("-")
            index1, index2 = int(position[0]), int(position[1])
            if index1 < len(processed_rawtext_list) and index2 < len(processed_rawtext_list[index1]):
                del processed_rawtext_list[index1][index2]

        flattened = [item for sublist in processed_rawtext_list for item in sublist]
        new_value = f"{DIV.join(flattened)}{DIV}" if flattened else None

        await rawtext_update(self.edit_raw, new_value, "userID", interaction.user.id)

        rawtext_content = await open_rawtext_column(interaction.user.id, self.edit_raw)
        view = (
            RawtextsView(interaction.user, f"欄位{self.edit_raw[-1]}．執行模式")
            .add_to_container(TextDisplay(f"```{rawtext_content}```"))
            .add_to_container(Separator())
            .add_to_container(ExecuteButtons(interaction.user, self.edit_raw))
        )
        await interaction.response.edit_message(view=view)

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


class RawtextItemDropdown(ActionRow):
    def __init__(
        self,
        edit_raw: str,
        rawtext_list: list,
        page: int,
        action: Optional[Literal["edit", "insert"]] = None,
    ):
        super().__init__()
        self.edit_raw = edit_raw
        self.action = action

        options = [
            discord.SelectOption(label=content[:100], value=f"{page}-{index}")
            for index, content in enumerate(rawtext_list)
        ]

        action_name = "編輯" if action == "edit" else "插入"
        select = Select(
            placeholder=f"{action_name}文本-第{page + 1}頁",
            options=options,
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction) -> None:
        select_component = interaction.data.get("values")
        result = select_component[0] if select_component else None

        if not result:
            return

        processed_rawtext_list = await make_rawtext_list(interaction.user.id, self.edit_raw)
        position = result.split("-")
        index1, index2 = int(position[0]), int(position[1])

        preview_text = ""
        if index1 < len(processed_rawtext_list) and index2 < len(processed_rawtext_list[index1]):
            preview_text = processed_rawtext_list[index1][index2]

        mode_name = "編輯模式" if self.action == "edit" else "插入模式"
        component_mode = "replace" if self.action == "edit" else "insert"

        view = (
            RawtextsView(interaction.user, f"欄位{self.edit_raw[-1]}．{mode_name}")
            .add_to_container(TextDisplay(f"```{preview_text}```"))
            .add_to_container(Separator())
            .add_to_container(TextsComponents(self.edit_raw, component_mode, result))
        )
        await interaction.response.edit_message(view=view)


def _apply_rawtext_change(
    raw: Optional[str],
    processed_list: List[List[str]],
    mode: str,
    position_str: Optional[str],
    json_item_str: str,
) -> str:
    """輔助函式：根據 mode (add/replace/insert) 計算更新後的 rawtext 字串。"""
    if mode == "add":
        if raw is None or raw == "None":
            return f"{json_item_str}{DIV}"
        return f"{raw}{json_item_str}{DIV}"

    if position_str:
        pos = position_str.split("-")
        index1, index2 = int(pos[0]), int(pos[1])
        if index1 < len(processed_list) and index2 <= len(processed_list[index1]):
            if mode == "replace":
                processed_list[index1][index2] = json_item_str
            elif mode == "insert":
                processed_list[index1].insert(index2, json_item_str)

    flattened = [item for sublist in processed_list for item in sublist]
    return f"{DIV.join(flattened)}{DIV}" if flattened else ""


class TextTextInput(Modal):
    text = TextInput(label="請輸入文字", style=discord.TextStyle.short)

    def __init__(
        self,
        author: discord.User | discord.Member,
        mode: str,
        raw: str,
        rawtext_position: Optional[str] = None,
    ):
        self.author = author
        self.mode = mode
        self.edit_raw = raw
        self.rawtext_position = rawtext_position
        prefix = {"add": "新增", "replace": "替換", "insert": "插入"}.get(mode, "")
        super().__init__(title=f"{prefix}: text(文字)", timeout=None)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        input_text = str(self.text)
        json_item_str = json.dumps({"text":input_text}, ensure_ascii=False, separators=[",", ":"])

        db_result = await rawtext_select(self.edit_raw, "userID", interaction.user.id)
        raw = db_result[0] if db_result else None
        processed_rawtext_list = (
            await make_rawtext_list(interaction.user.id, self.edit_raw)
            if self.rawtext_position is not None
            else []
        )

        new_rawtext = _apply_rawtext_change(
            raw, processed_rawtext_list, self.mode, self.rawtext_position, json_item_str
        )
        await rawtext_update(self.edit_raw, new_rawtext, "userID", interaction.user.id)

        rawtext_content = await open_rawtext_column(interaction.user.id, self.edit_raw)
        view = (
            RawtextsView(interaction.user, f"欄位{self.edit_raw[-1]}．執行模式")
            .add_to_container(TextDisplay(f"```{rawtext_content}```"))
            .add_to_container(Separator())
            .add_to_container(ExecuteButtons(interaction.user, self.edit_raw))
        )
        await interaction.response.edit_message(view=view)


class SelectorTextInput(Modal):
    selector = TextInput(label="請輸入選擇對象(@a/@s等,可使用選擇器參數)", style=discord.TextStyle.short)

    def __init__(
        self,
        author: discord.User | discord.Member,
        mode: str,
        raw: str,
        rawtext_position: Optional[str] = None,
    ):
        self.author = author
        self.mode = mode
        self.edit_raw = raw
        self.rawtext_position = rawtext_position
        prefix = {"add": "新增", "replace": "替換", "insert": "插入"}.get(mode, "")
        super().__init__(title=f"{prefix}: selector(選擇器)", timeout=None)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        input_selector = str(self.selector)
        json_item_str = json.dumps({"selector":input_selector}, ensure_ascii=False, separators=[",", ":"])

        db_result = await rawtext_select(self.edit_raw, "userID", interaction.user.id)
        raw = db_result[0] if db_result else None
        processed_rawtext_list = (
            await make_rawtext_list(interaction.user.id, self.edit_raw)
            if self.rawtext_position is not None
            else []
        )

        new_rawtext = _apply_rawtext_change(
            raw, processed_rawtext_list, self.mode, self.rawtext_position, json_item_str
        )
        await rawtext_update(self.edit_raw, new_rawtext, "userID", interaction.user.id)

        rawtext_content = await open_rawtext_column(interaction.user.id, self.edit_raw)
        view = (
            RawtextsView(interaction.user, f"欄位{self.edit_raw[-1]}．執行模式")
            .add_to_container(TextDisplay(f"```{rawtext_content}```"))
            .add_to_container(Separator())
            .add_to_container(ExecuteButtons(interaction.user, self.edit_raw))
        )
        await interaction.response.edit_message(view=view)


class ScoreTextInput(Modal):
    score = TextInput(label="請填入記分板代稱", style=discord.TextStyle.short)
    name = TextInput(label="請填入選擇對象(@a/@s等,可使用選擇器參數或實體分數)", style=discord.TextStyle.short)

    def __init__(
        self,
        author: discord.User | discord.Member,
        mode: str,
        raw: str,
        rawtext_position: Optional[str] = None,
    ):
        self.author = author
        self.mode = mode
        self.edit_raw = raw
        self.rawtext_position = rawtext_position
        prefix = {"add": "新增", "replace": "替換", "insert": "插入"}.get(mode, "")
        super().__init__(title=f"{prefix}: score(記分板)", timeout=None)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        input_score = str(self.score)
        input_name = str(self.name)
        json_item_str = json.dumps({"score":{"objective":input_score,"name":input_name}}, ensure_ascii=False, separators=[",", ":"])

        db_result = await rawtext_select(self.edit_raw, "userID", interaction.user.id)
        raw = db_result[0] if db_result else None
        processed_rawtext_list = (
            await make_rawtext_list(interaction.user.id, self.edit_raw)
            if self.rawtext_position is not None
            else []
        )

        new_rawtext = _apply_rawtext_change(
            raw, processed_rawtext_list, self.mode, self.rawtext_position, json_item_str
        )
        await rawtext_update(self.edit_raw, new_rawtext, "userID", interaction.user.id)

        rawtext_content = await open_rawtext_column(interaction.user.id, self.edit_raw)
        view = (
            RawtextsView(interaction.user, f"欄位{self.edit_raw[-1]}．執行模式")
            .add_to_container(TextDisplay(f"```{rawtext_content}```"))
            .add_to_container(Separator())
            .add_to_container(ExecuteButtons(interaction.user, self.edit_raw))
        )
        await interaction.response.edit_message(view=view)