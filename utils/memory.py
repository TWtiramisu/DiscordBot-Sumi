import discord
import os, asyncio
import numpy as np
import aiosqlite
from fastembed import TextEmbedding



class MemorySelectView(discord.ui.View):
    def __init__(self, memory_manager: MemoryManager, author_id: int, target_user: discord.User | discord.Member, memories: list[dict], timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.memory_manager = memory_manager
        self.author_id = author_id
        self.target_user = target_user
        self.memories = memories
        self.message: discord.Message | None = None

        # 最多支援 25 個選項（Discord 限制）
        display_memories = memories[:25]
        options = []
        for m in display_memories:
            fact_label = m["fact"][:95] + ("..." if len(m["fact"]) > 95 else "")
            date_str = m["created_at"][:10] if m.get("created_at") else ""
            desc = f"ID: {m['id']}" + (f" | 記於 {date_str}" if date_str else "")
            options.append(
                discord.SelectOption(
                    label = fact_label,
                    description = desc[:100],
                    value = str(m["id"])
                )
            )

        self.select_menu = discord.ui.Select(
            placeholder = "請選擇要刪除的記憶（可複選）",
            min_values = 1,
            max_values = len(options),
            options = options,
            row = 0
        )
        self.select_menu.callback = self.select_callback
        self.add_item(self.select_menu)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("[x] 這不是你的記憶選單，無法操作喔！", ephemeral=True)
            return False
        return True

    async def select_callback(self, interaction: discord.Interaction):
        selected_ids = [int(v) for v in self.select_menu.values]
        deleted_count = await self.memory_manager.delete_memories_by_ids(str(self.target_user.id), selected_ids)
        target_name = self.target_user.display_name
        self.stop()
        await interaction.response.edit_message(
            content=f"[v] 成功刪除 **{target_name}** 的 {deleted_count} 條指定記憶！",
            view=None
        )

    @discord.ui.button(label="清空全部記憶", style=discord.ButtonStyle.danger, emoji="💥", row=1)
    async def clear_all_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        count = await self.memory_manager.clear_user_memories(str(self.target_user.id))
        target_name = self.target_user.display_name
        self.stop()
        await interaction.response.edit_message(
            content=f"[v] 成功清空 **{target_name}** 的所有長期記憶（共 {count} 條）！",
            view=None
        )

    @discord.ui.button(label="取消", style=discord.ButtonStyle.secondary, row=1)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(content="[!] 已取消記憶管理操作。", view=None)

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(view=None)
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
