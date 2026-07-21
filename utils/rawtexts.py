import discord
from discord.ui import LayoutView, Container, ActionRow, Separator, TextDisplay, Select, Button, Modal, TextInput

import aiosqlite
from typing import Literal
from config import DIV, RAWTEXT_SQL

async def rawtext_select(target_key:str, filter_key:str, filter_value):
    async with aiosqlite.connect(RAWTEXT_SQL) as db:
        query = f"SELECT {target_key} FROM rawtext WHERE {filter_key} = ?"
        async with db.execute(query, (filter_value,)) as cursor:
            result = await cursor.fetchone()
            return result
        
async def rawtext_insert(target_key:str, value:tuple):
    async with aiosqlite.connect(RAWTEXT_SQL) as db:
        sql = f"INSERT INTO rawtext ({target_key}) VALUES ({('?, '*len(value))[0:-2]})"
        await db.execute(sql, value)
        await db.commit()

async def rawtext_update(target_key:str, new_value, filter_key: str, filter_value):
    async with aiosqlite.connect(RAWTEXT_SQL) as db:
        sql = f"UPDATE rawtext SET {target_key} = ? WHERE {filter_key} = ?"
        await db.execute(sql, (new_value, filter_value))
        await db.commit()

#打開指定欄位
async def open_rawtextColumn(authorID, column, output_mode=False):
    result = await rawtext_select(column, "userID", authorID)
    
    if not result or result[0] is None or str(result[0]) == "None" or str(result[0]).strip() == "":
        return "沒有資料"

    raw_list = str(result[0]).split(DIV)
    if raw_list[-1] == "":
        raw_list = raw_list[:-1]

    if len(raw_list) > 40 and not output_mode:
        front_part = ",".join(raw_list[:20])
        back_part = ",".join(raw_list[-20:])
        rawtext_content = f'{{"rawtext":[{front_part},\n ... \n{back_part}]}}'

    else:
        full_content = ",".join(raw_list)
        rawtext_content = f'{{"rawtext":[{full_content}]}}'

    return rawtext_content

class rawtextsView(LayoutView):
    def __init__(self, author, title=None):
        super().__init__()
        self.author = author
        self.title = title
        self.container = self.myContainer(self.title)
        self.add_item(self.container)

    def add_to_container(self, item):
        self.container.addItem(item)
        return self # 讓外層 View 也能繼續被鏈式呼叫

    async def interaction_check(self, interaction: discord.Interaction):
        return interaction.user.id == self.author.id

    class myContainer(Container):
        def __init__(self, title):
            super().__init__()

            self.add_item(TextDisplay("## rawtext協助編寫指令" if title is None else f"## {title}"))
            self.add_item(Separator())

        def addItem(self, item):
            self.add_item(item)
            return self

#選擇要編輯哪個欄位
class editWhichRaw(ActionRow):
    def __init__(self, author, disabled_raw:Literal["raw1", "raw2", "raw3"]=None):
        super().__init__()
        self.author = author

        for i in range(1, 4):
            raw_name = f"raw{i}"
            btn = Button(
                label = f"欄位{i}",
                style = discord.ButtonStyle.green,
                custom_id = raw_name, #把 rawN 藏在 custom_id 裡面
                disabled = (disabled_raw == raw_name),
            )
            btn.callback = self.button_callback
            self.add_item(btn)

    async def interaction_check(self, interaction: discord.Interaction):
        return interaction.user.id == self.author.id
    
    async def button_callback(self, interaction: discord.Interaction):
        raw_key = interaction.data.get("custom_id")
        rawtext_content = await open_rawtextColumn(interaction.user.id, raw_key)
        
        view = (
            rawtextsView(interaction.user, f"欄位{raw_key[-1]}．預覽模式")
                .add_to_container(editWhichRaw(interaction.user, raw_key))
                .add_to_container(TextDisplay(f"```{rawtext_content}```"))
                .add_to_container(Separator())
                .add_to_container(previewRawtextItems(interaction.user, raw_key))
        )
        await interaction.response.edit_message(view=view)

#該欄位編輯前預覽
class previewRawtextItems(ActionRow):
    def __init__(self, author, raw):
        super().__init__()
        self.author = author
        self.editraw = raw

    async def interaction_check(self, interaction: discord.Interaction):
        return interaction.user.id == self.author.id

    @discord.ui.button(label="返回", style=discord.ButtonStyle.gray)
    async def backed(self, interaction:discord.Interaction, button:Button):
        view = rawtextsView(interaction.user).add_to_container(editWhichRaw(interaction.user))
        await interaction.response.edit_message(view=view)

    @discord.ui.button(label="重製欄位", style=discord.ButtonStyle.red)
    async def reseted(self, interaction:discord.Interaction, button:Button):
        await rawtext_update(self.editraw, None, "userID", interaction.user.id)
        rawtext_content = await open_rawtextColumn(interaction.user.id, self.editraw)

        view = (
            rawtextsView(interaction.user, f"欄位{self.editraw[-1]}．預覽模式")
                .add_to_container(editWhichRaw(interaction.user, self.editraw))
                .add_to_container(TextDisplay(f"```{rawtext_content}```"))
                .add_to_container(Separator())
                .add_to_container(previewRawtextItems(interaction.user, self.editraw))
        )
        await interaction.response.edit_message(view=view)

    @discord.ui.button(label="確認選擇", style=discord.ButtonStyle.green)
    async def sured(self, interaction:discord.Interaction, button:Button):
        rawtext_content = await open_rawtextColumn(interaction.user.id, self.editraw)

        view = (
            rawtextsView(interaction.user, f"欄位{self.editraw[-1]}．執行模式")
                .add_to_container(TextDisplay(f"```{rawtext_content}```"))
                .add_to_container(Separator())
                .add_to_container(executeButtons(interaction.user, self.editraw))
        )
        await interaction.response.edit_message(view=view)

    @discord.ui.button(label="輸出結果", style=discord.ButtonStyle.blurple)
    async def finished(self, interaction:discord.Interaction, button:Button):
        rawtext_content = await open_rawtextColumn(interaction.user.id, self.editraw, True)

        await interaction.response.send_message(rawtext_content, ephemeral=True)

#新增/編輯/插入 按鈕
class executeButtons(ActionRow):
    def __init__(self, author, raw):
        super().__init__()
        self.author = author
        self.editraw = raw

    async def interaction_check(self, interaction: discord.Interaction):
        return interaction.user.id == self.author.id

    @discord.ui.button(label="返回", style=discord.ButtonStyle.gray)
    async def backed(self, interaction:discord.Interaction, button:Button):
        rawtext_content = await open_rawtextColumn(interaction.user.id, self.editraw)

        view = (
            rawtextsView(interaction.user, f"欄位{self.editraw[-1]}．預覽模式")
                .add_to_container(editWhichRaw(interaction.user, self.editraw))
                .add_to_container(TextDisplay(f"```{rawtext_content}```"))
                .add_to_container(Separator())
                .add_to_container(previewRawtextItems(interaction.user, self.editraw))
        )
        await interaction.response.edit_message(view=view)

    @discord.ui.button(label="新增", style=discord.ButtonStyle.blurple)
    async def added(self, interaction:discord.Interaction, button:Button):
        rawtext_content = await open_rawtextColumn(interaction.user.id, self.editraw)

        view = (
            rawtextsView(interaction.user, f"欄位{self.editraw[-1]}．新增模式")
                .add_to_container(TextDisplay(f"```{rawtext_content}```"))
                .add_to_container(Separator())
                .add_to_container(textsComponents(self.editraw, "add"))
        )
        await interaction.response.edit_message(view=view)

    @discord.ui.button(label="編輯", style=discord.ButtonStyle.blurple)
    async def edited(self, interaction:discord.Interaction, button:Button):
        rawtext_content = await open_rawtextColumn(interaction.user.id, self.editraw)

        view = (
            rawtextsView(interaction.user, f"欄位{self.editraw[-1]}．編輯模式")
                .add_to_container(TextDisplay(f"```{rawtext_content}```"))
                .add_to_container(Separator())
                .add_to_container(executeButtons(interaction.user, self.editraw))
        )
        processed_rawtextList = await make_rawtext_list(interaction.user.id, self.editraw)
        for first_index, nestedList_content in enumerate(processed_rawtextList):
            view.add_to_container(rawtext_itemDropdown(self.editraw, nestedList_content, first_index, "edit"))

        await interaction.response.edit_message(view=view)

    @discord.ui.button(label="插入", style=discord.ButtonStyle.blurple)
    async def inserted(self, interaction:discord.Interaction, button:Button):
        rawtext_content = await open_rawtextColumn(interaction.user.id, self.editraw)

        view = (
            rawtextsView(interaction.user, f"欄位{self.editraw[-1]}．插入模式")
                .add_to_container(TextDisplay(f"```{rawtext_content}```"))
                .add_to_container(Separator())
                .add_to_container(executeButtons(interaction.user, self.editraw))
        )
        processed_rawtextList = await make_rawtext_list(interaction.user.id, self.editraw)
        for first_index, nestedList_content in enumerate(processed_rawtextList):
            view.add_to_container(rawtext_itemDropdown(self.editraw, nestedList_content, first_index, "insert"))

        await interaction.response.edit_message(view=view)

#文本組件(text/selector/score)
class textsComponents(ActionRow):
    def __init__(self, raw, mode:Literal["add", "replace", "insert"], rawtext_position=None):
        super().__init__()
        self.editraw = raw
        self.mode = mode
        self.rawtext_position = rawtext_position

        prefix = {"add": "新增", "replace": "替換", "insert": "插入"}
        for action in ["text(文字)", "selector(選擇器)", "score(記分板)"]:
            btn = Button(
                label = f"{prefix[mode]}{action}",
                style = discord.ButtonStyle.green,
                custom_id = f"{self.mode}-{action}"
            )
            btn.callback = self.button_callback
            self.add_item(btn)

        if mode == "replace":
            delect_btn = Button(
                label = "刪除文本",
                style = discord.ButtonStyle.danger,
                custom_id = "delete"
            )
            delect_btn.callback = self.delect_button_callback
            self.add_item(delect_btn)
    
    async def button_callback(self, interaction: discord.Interaction):
        custom_id = interaction.data.get("custom_id")
        mode, action = custom_id.split("-")
        
        if "text" in action:
            await interaction.response.send_modal(textTextInput(interaction.user, mode, self.editraw, self.rawtext_position))

        elif "selector" in action:
            await interaction.response.send_modal(selectorTextInput(interaction.user, mode, self.editraw, self.rawtext_position))

        elif "score" in action:
            await interaction.response.send_modal(scoreTextInput(interaction.user, mode, self.editraw, self.rawtext_position))

    async def delect_button_callback(self, interaction: discord.Interaction):
        processed_rawtextList = await make_rawtext_list(interaction.user.id, self.editraw)
        position = self.rawtext_position.split('-')
        index1, index2 = int(position[0]), int(position[1])
        del processed_rawtextList[index1][index2]
        
        await rawtext_update(self.editraw, DIV.join(item for sublist in processed_rawtextList for item in sublist)+DIV, 'userID', interaction.user.id)

        rawtext_content = await open_rawtextColumn(interaction.user.id, self.editraw)
        view = (
            rawtextsView(interaction.user, f"欄位{self.editraw[-1]}．執行模式")
                .add_to_container(TextDisplay(f"```{rawtext_content}```"))
                .add_to_container(Separator())
                .add_to_container(executeButtons(interaction.user, self.editraw))
        )
        await interaction.response.edit_message(view=view)

        raw = await rawtext_select(self.editraw, 'userID', interaction.user.id)

        if raw == "":
            await rawtext_update(self.editraw, None, 'userID', interaction.user.id)

    @discord.ui.button(label="返回", style=discord.ButtonStyle.gray)
    async def backed(self, interaction:discord.Interaction, button:Button):
        rawtext_content = await open_rawtextColumn(interaction.user.id, self.editraw)

        view = (
            rawtextsView(interaction.user, f"欄位{self.editraw[-1]}．執行模式")
                .add_to_container(TextDisplay(f"```{rawtext_content}```"))
                .add_to_container(Separator())
                .add_to_container(executeButtons(interaction.user, self.editraw))
        )
        await interaction.response.edit_message(view=view)

#將rawtext內容處理成二維列表(防discord.ui.Select溢出)
async def make_rawtext_list(authorID, editraw):
    theRaw = await rawtext_select(editraw, 'userID', authorID)

    rawList = str(theRaw[0]).split(DIV)[:-1] #將sql字串調出並拆成列表
    processed_rawtextList = []

    for index in range(0, len(rawList), 25): #使變數在0~列表長度中跑, 25個資料為一個range
        processed_rawtextList.append(rawList[index:index+25]) #設定子列表的內容(2維列表)

    return processed_rawtextList


#編輯/插入要用的選擇文本選單
class rawtext_itemDropdown(ActionRow):
    def __init__(self, editraw, rawtextList:list, page, action=None):
        super().__init__()
        self.editraw = editraw
        self.action = action

        options = [
            discord.SelectOption(label=content, value=f'{page}-{index}') for index, content in enumerate(rawtextList)
        ]

        select = Select(
            placeholder = f"{'編輯' if action=='edit' else '插入'}文本-第{page+1}頁", 
            options = options
        )
        select.callback = self.select_callback
    
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        select_component = interaction.data.get("values")
        result = select_component[0] if select_component else None
        
        if not result:
            return

        processed_rawtextList = await make_rawtext_list(interaction.user.id, self.editraw)
        
        position = result.split('-')
        index1, index2 = int(position[0]), int(position[1])

        if self.action == 'edit':
            view = (
                rawtextsView(interaction.user, f"欄位{self.editraw[-1]}．編輯模式")
                    .add_to_container(TextDisplay(f"```{processed_rawtextList[index1][index2]}```"))
                    .add_to_container(Separator())
                    .add_to_container(textsComponents(self.editraw, "replace", result)) 
            )
            await interaction.response.edit_message(view=view)
        
        elif self.action == 'insert':
            view = (
                rawtextsView(interaction.user, f"欄位{self.editraw[-1]}．插入模式")
                    .add_to_container(TextDisplay(f"```{processed_rawtextList[index1][index2]}```"))
                    .add_to_container(Separator())
                    .add_to_container(textsComponents(self.editraw, "insert", result)) 
            )
            await interaction.response.edit_message(view=view)

class textTextInput(Modal):
    def __init__(self, author, mode: str, raw, rawtext_position=None):
        self.author = author
        self.mode = mode
        self.editraw = raw
        self.rawtext_position = rawtext_position
        prefix = {"add": "新增", "replace": "替換", "insert": "插入"}[mode]
        super().__init__(title=f"{prefix}: text(文字)", timeout=None)

    text = TextInput(label="請輸入文字", style=discord.TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction):
        input_text = str(self.text)
        db_result = await rawtext_select(self.editraw, 'userID', interaction.user.id)
        raw = db_result[0] if db_result else None

        if self.rawtext_position != None:
            processed_rawtextList = await make_rawtext_list(interaction.user.id, self.editraw)
            position = self.rawtext_position.split('-')
            index1, index2 = int(position[0]), int(position[1])
        
        if self.mode == 'add':
            if raw == None or raw == "None":
                new_rawtext = f'{{"text":"{input_text}"}}{DIV}'
            else:
                new_rawtext = f'{raw}{{"text":"{input_text}"}}{DIV}'

        elif self.mode == 'replace':
            processed_rawtextList[index1][index2] = f'{{"text":"{input_text}"}}'
            new_rawtext = DIV.join(item for sublist in processed_rawtextList for item in sublist)+DIV

        elif self.mode == 'insert':
            processed_rawtextList[index1].insert(index2, f'{{"text":"{input_text}"}}')
            new_rawtext = DIV.join(item for sublist in processed_rawtextList for item in sublist)+DIV

        await rawtext_update(self.editraw, new_rawtext, 'userID', interaction.user.id)

        rawtext_content = await open_rawtextColumn(interaction.user.id, self.editraw)
        view = (
            rawtextsView(interaction.user, f"欄位{self.editraw[-1]}．執行模式")
                .add_to_container(TextDisplay(f"```{rawtext_content}```"))
                .add_to_container(Separator())
                .add_to_container(executeButtons(interaction.user, self.editraw))
        )
        await interaction.response.edit_message(view=view)

class selectorTextInput(Modal):
    def __init__(self, author, mode, raw, rawtext_position=None):
        self.author = author
        self.mode = mode
        self.editraw = raw
        self.rawtext_position = rawtext_position
        prefix = {"add": "新增", "replace": "替換", "insert": "插入"}[mode]
        super().__init__(title=f"{prefix}: selector(選擇器)", timeout=None)

    selector = TextInput(label="請輸入選擇對象(@a/@s等,可使用選擇器參數)", style=discord.TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction):
        input_selector = str(self.selector)
        db_result = await rawtext_select(self.editraw, 'userID', interaction.user.id)
        raw = db_result[0] if db_result else None

        if self.rawtext_position != None:
            processed_rawtextList = await make_rawtext_list(interaction.user.id, self.editraw)
            position = self.rawtext_position.split('-')
            index1, index2 = int(position[0]), int(position[1])

        if self.mode == 'add':
            if raw == None or raw == "None":
                new_rawtext = f'{{"selector":"{input_selector}"}}{DIV}'
            else:
                new_rawtext = f'{raw}{{"selector":"{input_selector}"}}{DIV}'

        elif self.mode == 'replace':
            processed_rawtextList[index1][index2] = f'{{"selector":"{input_selector}"}}'
            new_rawtext = DIV.join(item for sublist in processed_rawtextList for item in sublist)+DIV

        elif self.mode == 'insert':
            processed_rawtextList[index1].insert(index2, f'{{"selector":"{input_selector}"}}')
            new_rawtext = DIV.join(item for sublist in processed_rawtextList for item in sublist)+DIV

        await rawtext_update(self.editraw, new_rawtext, 'userID', interaction.user.id)

        rawtext_content = await open_rawtextColumn(interaction.user.id, self.editraw)
        view = (
            rawtextsView(interaction.user, f"欄位{self.editraw[-1]}．執行模式")
                .add_to_container(TextDisplay(f"```{rawtext_content}```"))
                .add_to_container(Separator())
                .add_to_container(executeButtons(interaction.user, self.editraw))
        )
        await interaction.response.edit_message(view=view)

class scoreTextInput(Modal):
    def __init__(self, author, mode, raw, rawtext_position=None):
        self.author = author
        self.mode = mode
        self.editraw = raw
        self.rawtext_position = rawtext_position
        prefix = {"add": "新增", "replace": "替換", "insert": "插入"}[mode]
        super().__init__(title=f"{prefix}: score(記分板)", timeout=None)

    score = TextInput(label="請填入記分板代稱", style=discord.TextStyle.short)
    name = TextInput(label="請填入選擇對象(@a/@s等,可使用選擇器參數或實體分數)", style=discord.TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction):
        input_score = str(self.score)
        input_name = str(self.name)
        db_result = await rawtext_select(self.editraw, 'userID', interaction.user.id)
        raw = db_result[0] if db_result else None

        if self.rawtext_position != None:
            processed_rawtextList = await make_rawtext_list(interaction.user.id, self.editraw)
            position = self.rawtext_position.split('-')
            index1, index2 = int(position[0]), int(position[1])

        if self.mode == 'add':
            if raw == None or raw == "None":
                new_rawtext = f'{{"score":{{"objective":"{input_score}","name":"{input_name}"}}}}{DIV}'
            else:
                new_rawtext = f'{raw}{{"score":{{"objective":"{input_score}","name":"{input_name}"}}}}{DIV}'

        elif self.mode == 'replace':
            processed_rawtextList[index1][index2] = f'{{"score":{{"objective":"{input_score}","name":"{input_name}"}}}}'
            new_rawtext = DIV.join(item for sublist in processed_rawtextList for item in sublist)+DIV

        elif self.mode == 'insert':
            processed_rawtextList[index1].insert(index2, f'{{"score":{{"objective":"{input_score}","name":"{input_name}"}}}}')
            new_rawtext = DIV.join(item for sublist in processed_rawtextList for item in sublist)+DIV

        await rawtext_update(self.editraw, new_rawtext, 'userID', interaction.user.id)

        await rawtext_update(self.editraw, new_rawtext, 'userID', interaction.user.id)

        rawtext_content = await open_rawtextColumn(interaction.user.id, self.editraw)
        view = (
            rawtextsView(interaction.user, f"欄位{self.editraw[-1]}．執行模式")
                .add_to_container(TextDisplay(f"```{rawtext_content}```"))
                .add_to_container(Separator())
                .add_to_container(executeButtons(interaction.user, self.editraw))
        )
        await interaction.response.edit_message(view=view)