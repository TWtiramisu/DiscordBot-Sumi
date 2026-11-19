import discord
import os, asyncio
import numpy as np
import aiosqlite
from fastembed import TextEmbedding



class MemoryChunkSelect(discord.ui.Select):
    """記憶區塊下拉選單（每個選單最多 25 條記憶）"""
    def __init__(self, parent_view: "MemorySelectView", chunk_index: int, options: list[discord.SelectOption], placeholder: str, row: int):
        super().__init__(
            placeholder=placeholder,
            min_values=0,
            max_values=len(options),
            options=options,
            row=row
        )
        self.parent_view = parent_view
        self.chunk_index = chunk_index

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.handle_select(interaction, self.chunk_index, [int(v) for v in self.values])


class MemorySelectView(discord.ui.View):
    """整合型記憶選單：瀏覽與複選刪除"""
    def __init__(
        self,
        memory_manager: "MemoryManager",
        author_id: int,
        target_user: discord.User | discord.Member,
        memories: list[dict],
        timeout: float = 60.0
    ):
        super().__init__(timeout=timeout)
        self.memory_manager = memory_manager
        self.author_id = author_id
        self.target_user = target_user
        self.memories = memories
        self.message: discord.Message | None = None
        self.selected_per_menu: dict[int, set[int]] = {}
        self.select_menus: list[MemoryChunkSelect] = []

        # 按鈕實例（複選時動態加入）
        self.btn_delete: discord.ui.Button | None = None
        self.btn_cancel: discord.ui.Button | None = None

        # 每個選單最多 25 條，Discord 訊息最多 5 個 ActionRow，保留 1 行給按鈕，最多支援 4 個選單（100 條）
        chunk_size = 25
        max_chunks = 4
        display_memories = memories[:max_chunks * chunk_size]
        chunks = [display_memories[i:i + chunk_size] for i in range(0, len(display_memories), chunk_size)]
        self.button_row = min(len(chunks), 4)

        for i, chunk in enumerate(chunks):
            options = []
            start_num = i * chunk_size + 1
            end_num = start_num + len(chunk) - 1
            for m in chunk:
                fact_label = m["fact"][:95] + ("..." if len(m["fact"]) > 95 else "")
                date_str = m["created_at"][:10] if m.get("created_at") else ""
                desc = f"ID: {m['id']}" + (f" | 記於 {date_str}" if date_str else "")
                options.append(
                    discord.SelectOption(
                        label=fact_label,
                        description=desc[:100],
                        value=str(m["id"])
                    )
                )

            if len(chunks) == 1:
                placeholder = "點擊瀏覽或勾選欲刪除的記憶 (可複選)..."
            else:
                placeholder = f"記憶 {start_num}~{end_num} (點擊瀏覽/勾選欲刪除項目)..."

            select = MemoryChunkSelect(
                parent_view=self,
                chunk_index=i,
                options=options,
                placeholder=placeholder,
                row=i
            )
            self.select_menus.append(select)
            self.add_item(select)

    def get_total_selected(self) -> set[int]:
        if not self.selected_per_menu:
            return set()
        return set().union(*self.selected_per_menu.values())

    def get_content(self, total_selected: set[int]) -> str:
        target_name = "你" if self.target_user.id == self.author_id else f"**{self.target_user.display_name}**"
        total_count = len(self.memories)
        note = f"（共 {total_count} 條）"
        if total_count > 100:
            note = f"（共 {total_count} 條，選單展示最新 100 條）"

        if total_selected:
            return (
                f"**Sumi 關於 {target_name} 的長期記憶 {note}**：\n"
                f"已勾選 **{len(total_selected)}** 條記憶，請確認是否刪除或取消："
            )
        else:
            return (
                f"**Sumi 關於 {target_name} 的長期記憶 {note}**：\n"
                f"請透過下方選單瀏覽記憶；如需刪除，可直接於選單中複選勾選。"
            )

    def update_buttons(self, total_selected: set[int]):
        count = len(total_selected)
        if count > 0:
            if self.btn_delete is None:
                self.btn_delete = discord.ui.Button(
                    label=f"刪除所選記憶 ({count})",
                    style=discord.ButtonStyle.danger,
                    row=self.button_row
                )
                self.btn_delete.callback = self.delete_button_callback
                self.add_item(self.btn_delete)

                self.btn_cancel = discord.ui.Button(
                    label="取消",
                    style=discord.ButtonStyle.secondary,
                    row=self.button_row
                )
                self.btn_cancel.callback = self.cancel_button_callback
                self.add_item(self.btn_cancel)
            else:
                self.btn_delete.label = f"刪除所選記憶 ({count})"
        else:
            if self.btn_delete is not None:
                self.remove_item(self.btn_delete)
                self.btn_delete = None
            if self.btn_cancel is not None:
                self.remove_item(self.btn_cancel)
                self.btn_cancel = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("[x] 這不是你的記憶選單，無法操作喔！", ephemeral=True)
            return False
        return True

    async def handle_select(self, interaction: discord.Interaction, chunk_index: int, values: list[int]):
        self.selected_per_menu[chunk_index] = set(values)
        total_selected = self.get_total_selected()

        # 更新 option.default 狀態
        for select in self.select_menus:
            for opt in select.options:
                opt.default = (int(opt.value) in total_selected)

        self.update_buttons(total_selected)
        await interaction.response.edit_message(
            content=self.get_content(total_selected),
            view=self
        )

    async def delete_button_callback(self, interaction: discord.Interaction):
        total_selected = self.get_total_selected()
        if not total_selected:
            await interaction.response.send_message("[!] 目前沒有選取任何記憶喔！", ephemeral=True)
            return

        deleted_count = await self.memory_manager.delete_memories_by_ids(
            str(self.target_user.id),
            list(total_selected)
        )
        target_name = self.target_user.display_name
        self.stop()
        await interaction.response.edit_message(
            content=f"[v] 成功刪除 **{target_name}** 的 {deleted_count} 條指定記憶！",
            view=None
        )

    async def cancel_button_callback(self, interaction: discord.Interaction):
        self.selected_per_menu.clear()
        for select in self.select_menus:
            for opt in select.options:
                opt.default = False
        self.update_buttons(set())
        await interaction.response.edit_message(
            content=self.get_content(set()),
            view=self
        )

    async def on_timeout(self):
        if self.message:
            try:
                for item in self.children:
                    item.disabled = True
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass



class MemoryManager:
    def __init__(self, db_path: str = "db/memories.db", model_name: str = "BAAI/bge-small-zh-v1.5"):
        self.db_path = db_path
        self.model_name = model_name
        self._embedder: TextEmbedding | None = None
        self._lock = asyncio.Lock()

    def _get_embedder(self) -> TextEmbedding:
        """懶加載 FastEmbed 模型"""
        if self._embedder is None:
            self._embedder = TextEmbedding(model_name=self.model_name)
        return self._embedder

    def _embed_text_sync(self, text: str) -> np.ndarray:
        """同步計算文字向量（已歸一化，長度 512）"""
        embedder = self._get_embedder()
        vector = list(embedder.embed([text]))[0].astype(np.float32)
        return vector

    async def get_embedding(self, text: str) -> np.ndarray:
        """在線程池中異步計算向量，不阻塞 asyncio 事件循環"""
        return await asyncio.to_thread(self._embed_text_sync, text)

    async def init_db(self):
        """初始化 SQLite 記憶資料庫與索引"""
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    fact TEXT NOT NULL,
                    vector BLOB NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_memories_user_id ON user_memories(user_id);")
            await db.commit()

    async def search_memories(self, user_id: str, query: str, top_k: int = 3, threshold: float = 0.50) -> list[str]:
        """
        語意檢索該使用者的相關長期記憶
        :param user_id: Discord 使用者 ID
        :param query: 檢索的語句（通常為使用者的當前發言）
        :param top_k: 最多回傳幾則記憶
        :param threshold: 餘弦相似度門檻（高於此值才算相關）
        :return: 相關事實列表
        """
        try:
            query_vec = await self.get_embedding(query)
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    "SELECT id, fact, vector FROM user_memories WHERE user_id = ?",
                    (user_id,)
                )
                rows = await cursor.fetchall()
                if not rows:
                    return []

                scored_facts = []
                for row_id, fact, vector_blob in rows:
                    fact_vec = np.frombuffer(vector_blob, dtype=np.float32)
                    sim = float(np.dot(query_vec, fact_vec))
                    if sim >= threshold:
                        scored_facts.append((sim, fact))

                # 依相似度由高到低排序
                scored_facts.sort(key=lambda x: x[0], reverse=True)
                return [fact for _, fact in scored_facts[:top_k]]

        except Exception as e:
            print(f"[!] 檢索使用者記憶時發生錯誤: {e}")
            return []

    async def add_memory(self, user_id: str, fact: str, deduplication_threshold: float = 0.85) -> bool:
        """
        為使用者新增或更新一條精煉事實
        :param user_id: Discord 使用者 ID
        :param fact: 提煉出的純文字事實
        :param deduplication_threshold: 去重門檻，若現有記憶相似度高於此值則更新而非重複插入
        :return: 是否成功
        """
        fact = fact.strip()
        if not fact:
            return False

        try:
            fact_vec = await self.get_embedding(fact)
            vector_blob = fact_vec.astype(np.float32).tobytes()

            async with self._lock:
                async with aiosqlite.connect(self.db_path) as db:
                    cursor = await db.execute(
                        "SELECT id, fact, vector FROM user_memories WHERE user_id = ?",
                        (user_id,)
                    )
                    rows = await cursor.fetchall()

                    matched_id = None
                    highest_sim = -1.0

                    for row_id, _, v_blob in rows:
                        v = np.frombuffer(v_blob, dtype=np.float32)
                        sim = float(np.dot(fact_vec, v))
                        if sim > highest_sim:
                            highest_sim = sim
                            matched_id = row_id

                    # 若現有記憶中已存在高相似度的條目，更新現有記憶
                    if highest_sim >= deduplication_threshold and matched_id is not None:
                        await db.execute(
                            "UPDATE user_memories SET fact = ?, vector = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                            (fact, vector_blob, matched_id)
                        )
                        print(f"[+] 更新既有記憶 (ID: {matched_id}, 相似度: {highest_sim:.2f}): {fact}")
                    else:
                        await db.execute(
                            "INSERT INTO user_memories (user_id, fact, vector) VALUES (?, ?, ?)",
                            (user_id, fact, vector_blob)
                        )
                        print(f"[+] 新增長期記憶 [User {user_id}]: {fact}")

                    await db.commit()
            return True

        except Exception as e:
            print(f"[!] 儲存使用者記憶時發生錯誤: {e}")
            return False

    async def extract_and_save_facts(self, ai_client, model_name: str, user_id: str, user_name: str, user_message: str, bot_reply: str):
        """
        背景異步任務：分析對話內容並提煉事實，寫入記憶庫
        """
        # 過短的閒聊發言不觸發事實提煉
        if len(user_message.strip()) < 4:
            return

        extraction_system_prompt = (
            "你是一個負責為專屬 AI 助手提煉使用者個人長期記憶的分析模組。\n"
            "請分析以下對話，判斷發言者是否透露了任何關於其「個人喜好、習慣、身分特徵、重要經歷、寵物、生日、願望、特定計畫或約定」等值得長期記住的事實。\n\n"
            "規則：\n"
            "1. 僅提煉「發言者本人」的事實，不包含常識、一般客套話（如早安、哈哈、好的、今天天氣好）或純知識問答。\n"
            "2. 若有值得記住的事實，請提煉為 1~2 句精簡陳述句（必須以發言者的暱稱開頭，例如「提拉米蘇喜歡喝無糖青茶」、「提拉米蘇養了一隻叫麻糬的貓」）。\n"
            "3. 若對話中沒有任何值得長期記住的個人事實，請務必僅輸出「NONE」。\n"
            "4. 統一使用繁體中文，絕對不要輸出任何多餘的解釋、標號或前綴。"
        )

        user_content = (
            f"發言者暱稱: {user_name} (ID: {user_id})\n"
            f"發言者訊息: {user_message}\n"
            f"助手回覆: {bot_reply}"
        )

        try:
            response = await ai_client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": extraction_system_prompt},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.3,
                max_tokens=256
            )

            result = response.choices[0].message.content.strip()
            if not result or "NONE" in result.upper():
                return

            # 可能有多行事實
            for line in result.splitlines():
                line = line.strip().lstrip("-*123456789. ")
                if line and len(line) >= 4 and not line.upper().startswith("NONE"):
                    await self.add_memory(user_id, line)

        except Exception as e:
            print(f"[!] 背景提煉記憶失敗: {e}")

    async def get_user_memories(self, user_id: str) -> list[dict]:
        """查詢某使用者的所有已儲存記憶"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    "SELECT id, fact, created_at, updated_at FROM user_memories WHERE user_id = ? ORDER BY id DESC",
                    (user_id,)
                )
                rows = await cursor.fetchall()
                return [
                    {
                        "id": row[0],
                        "fact": row[1],
                        "created_at": row[2],
                        "updated_at": row[3]
                    }
                    for row in rows
                ]
        except Exception as e:
            print(f"[!] 讀取使用者記憶列表失敗: {e}")
            return []

    async def delete_memories_by_ids(self, user_id: str, memory_ids: list[int]) -> int:
        """刪除某使用者指定的記憶 ID 列表"""
        if not memory_ids:
            return 0
        
        try:
            placeholders = ",".join("?" for _ in memory_ids)
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    f"DELETE FROM user_memories WHERE user_id = ? AND id IN ({placeholders})",
                    (user_id, *memory_ids)
                )
                await db.commit()
                return cursor.rowcount
            
        except Exception as e:
            print(f"[!] 刪除指定記憶失敗: {e}")
            return 0

    async def clear_user_memories(self, user_id: str) -> int:
        """清空某使用者的所有記憶"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("DELETE FROM user_memories WHERE user_id = ?", (user_id,))
                await db.commit()
                return cursor.rowcount
        except Exception as e:
            print(f"[!] 清空使用者記憶失敗: {e}")
            return 0
