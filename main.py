import uuid
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View
import asyncio
import json
from typing import List, Dict
import re
from datetime import datetime, timedelta

DATA_FILE_PATH = "data.json"

def read_data():
    try:
        with open(DATA_FILE_PATH, "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        return {"ServerTokens": {}, "ServerModels": {}, "ServerEveryoneResponse": {}, "LongTermMemory": []}

def write_data(data):
    with open(DATA_FILE_PATH, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)

data = read_data()

class CompletionExecutor:
    def __init__(self, host, request_id):
        self._host = host
        self._request_id = request_id
        self.headers = {
            'X-NCP-CLOVASTUDIO-REQUEST-ID': self._request_id,
            'Content-Type': 'application/json; charset=utf-8',
        }

    def set_api_key(self, api_key, api_key_primary_val):
        self.headers['X-NCP-CLOVASTUDIO-API-KEY'] = api_key
        self.headers['X-NCP-APIGW-API-KEY'] = api_key_primary_val

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

HYPERCLOVA_API_URL = "https://clovastudio.apigw.ntruss.com/serviceapp/v1/chat-completions/HCX-DASH-001"
HYPERCLOVA_API_KEY = "YOUR_HYPERCLOVA_API_KEY"
HYPERCLOVA_API_KEY_PRIMARY_VAL = "YOUR_HYPERCLOVA_API_KEY_PRIMARY_VAL"

class ModeSettingPage:
    def __init__(self, on_select_callback, page_number):
        super().__init__()
        self.embed = discord.Embed(
            title="도하루 /모드",
            description="도하루에는 Hyper 그리고 Rapid 이렇게 2가지의 모드가 있습니다. 높은 지능을 원한다면 Hyper를, 빠른 응답속도와 다채로움을 원한다면 Rapid를 선택해주세요."
        )
        self.embed.add_field(name=":bulb: Hyper", value="가장 강력한 모델입니다.", inline=False)
        self.embed.add_field(name=":zap: Rapid", value="응답속도가 빠르고 발화가 다채로운 모델입니다.", inline=False)
        self.select_menu = discord.ui.Select(
            options=[
                discord.SelectOption(label="Hyper", emoji="💡", value="Hyper"),
                discord.SelectOption(label="Rapid", emoji="⚡", value="Rapid")
            ]
        )
        self.default_mode = "Rapid"
        self.select_menu.callback = on_select_callback

    def update_select_menu(self, server_id):
        current_mode = get_server_model(server_id)
        if current_mode:
            for option in self.select_menu.options:
                if current_mode == "HCX-DASH-001":
                    if option.value == "Rapid":
                        option.default = True
                    else:
                        option.default = False
                elif current_mode == "HCX-003":
                    if option.value == "Hyper":
                        option.default = True
                    else:
                        option.default = False
        else:
            for option in self.select_menu.options:
                if option.value == self.default_mode:
                    option.default = True
                else:
                    option.default = False
                    
    def to_components(self):
        return [self.select_menu]

    async def on_select(self, interaction):
        selected_mode = self.select_menu.values[0]
        if selected_mode == "Rapid":
            model_code = "HCX-DASH-001"
        elif selected_mode == "Hyper":
            model_code = "HCX-003"
        update_server_model(interaction.guild_id, model_code)
        self.update_select_menu(interaction.guild_id)
        self.view.update_buttons()
        await interaction.response.edit_message(embed=self.embed, view=self.view)

class EveryoneResponseSettingPage:
    def __init__(self, on_select_callback, page_number):
        super().__init__()
        self.embed = discord.Embed(
            title="도하루 /@everyone 응답",
            description="도하루가 @everyone 멘션에 답장할지 설정할 수 있습니다. 멘션을 했는데 도하루가 뜬금없이 이상한 말을 하는걸 방지할 수 있습니다."
        )
        self.embed.add_field(name=":o: 켜짐", value="전체 멘션 답장을 켭니다.", inline=False)
        self.embed.add_field(name=":x: 꺼짐", value="전체 멘션 답장을 끕니다.", inline=False)
        self.select_menu = discord.ui.Select(
            options=[
                discord.SelectOption(label="켜짐", emoji="⭕", value="on"),
                discord.SelectOption(label="꺼짐", emoji="❌", value="off")
            ]
        )
        self.default_everyone_response = "on"
        self.select_menu.callback = on_select_callback

    def update_select_menu(self, server_id):
        current_everyone_response = get_server_everyone_response(server_id)
        if current_everyone_response:
            for option in self.select_menu.options:
                if option.value == "on":
                    option.default = True
                else:
                    option.default = False
        else:
            for option in self.select_menu.options:
                if option.value == "off":
                    option.default = True
                else:
                    option.default = False

    def to_components(self):
        return [self.select_menu]

    async def on_select(self, interaction):
        selected_everyone_response = self.select_menu.values[0]
        update_server_everyone_response(interaction.guild_id, selected_everyone_response == "on")
        self.update_select_menu(interaction.guild_id)
        self.view.update_buttons()
        await interaction.response.edit_message(embed=self.embed, view=self.view)

class SettingsView(discord.ui.View):
    def __init__(self, server_id):
        super().__init__(timeout=300)
        self.server_id = server_id
        self.pages = [
            ModeSettingPage(self.on_select, page_number=0), 
            EveryoneResponseSettingPage(self.on_select, page_number=1)
        ]
        for page in self.pages:
            page.view = self
        self.current_page_index = 0
        self.left_button = discord.ui.Button(style=discord.ButtonStyle.gray, emoji="⬅️")
        self.right_button = discord.ui.Button(style=discord.ButtonStyle.gray, emoji="➡️")
        self.left_button.callback = self.on_left_button
        self.right_button.callback = self.on_right_button
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        current_page = self.pages[self.current_page_index]
        current_page.update_select_menu(self.server_id)
        self.add_item(current_page.select_menu)
        if self.current_page_index > 0:
            self.add_item(self.left_button)
        if self.current_page_index < len(self.pages) - 1:
            self.add_item(self.right_button)

    async def on_left_button(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.current_page_index = max(0, self.current_page_index - 1)
        self.update_buttons()
        await interaction.message.edit(embed=self.pages[self.current_page_index].embed, view=self)

    async def on_right_button(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.current_page_index = min(len(self.pages) - 1, self.current_page_index + 1)
        self.update_buttons()
        await interaction.message.edit(embed=self.pages[self.current_page_index].embed, view=self)

    async def on_select(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.pages[self.current_page_index].on_select(interaction)
        self.update_buttons()
        await interaction.message.edit(embed=self.pages[self.current_page_index].embed, view=self)

class ChatMemory:
    def __init__(self):
        self.user_memories = {}

    def add_to_memory(self, user_id, user_input, bot_response):
        self.user_memories[user_id] = (user_input, bot_response)

    def get_previous_interaction(self, user_id):
        return self.user_memories.get(user_id, None)

    def clear_memory(self, user_id):
        if user_id in self.user_memories:
            del self.user_memories

chat_memory = ChatMemory()

completion_executor = CompletionExecutor(
    host='https://clovastudio.apigw.ntruss.com',
    request_id='YOUR_REQUEST_ID')

def check_or_create_trial_tokens(server_id):
    if str(server_id) not in data["ServerTokens"]:
        data["ServerTokens"][str(server_id)] = {"tokens": 100, "gived": True}
        write_data(data)
        return 100
    return data["ServerTokens"][str(server_id)]["tokens"]

def can_ask_question(server_id):
    server_tokens = data["ServerTokens"].get(str(server_id))
    if server_tokens is None or server_tokens["tokens"] <= 0 or server_tokens["gived"] == False:
        return False
    else:
        return True

def deduct_token(server_id, token_cost):
    if str(server_id) in data["ServerTokens"]:
        data["ServerTokens"][str(server_id)]["tokens"] -= token_cost
        write_data(data)

def update_server_model(server_id, model):
    if model == "Rapid":
        model_code = "HCX-DASH-001"
    elif model == "Hyper":
        model_code = "HCX-003"
    else:
        model_code = model
    data["ServerModels"][str(server_id)] = model_code
    write_data(data)

def get_server_model(server_id):
    return data["ServerModels"].get(str(server_id))

def update_server_everyone_response(server_id, everyone_response):
    data["ServerEveryoneResponse"][str(server_id)] = everyone_response
    write_data(data)

def get_server_everyone_response(server_id):
    return data["ServerEveryoneResponse"].get(str(server_id), True)

def save_long_term_memory(server_id: int, user_id: int, speaker: str, memory: str):
    memories = [m for m in data["LongTermMemory"] if m["server_id"] == server_id and m["user_id"] == user_id]
    if len(memories) >= 4:
        oldest_memory = min(memories, key=lambda x: x["created_at"])
        data["LongTermMemory"].remove(oldest_memory)
    new_memory = {
        "id": str(uuid.uuid4()),
        "server_id": server_id,
        "user_id": user_id,
        "speaker": speaker,
        "memory": memory,
        "timestamp": datetime.now().isoformat(),
        "created_at": datetime.now().isoformat(),
        "n_count": 0
    }
    data["LongTermMemory"].append(new_memory)
    write_data(data)

def get_long_term_memories(server_id: int, user_id: int) -> List[Dict[str, str]]:
    return [m for m in data["LongTermMemory"] if m["server_id"] == server_id and m["user_id"] == user_id]

def increment_n_count(memory_id: int):
    for memory in data["LongTermMemory"]:
        if memory["id"] == memory_id:
            memory["n_count"] += 1
            write_data(data)
            break

def delete_unused_memories(threshold: int = 3):
    initial_count = len(data["LongTermMemory"])
    data["LongTermMemory"] = [memory for memory in data["LongTermMemory"] if memory["n_count"] < threshold]
    deleted_count = initial_count - len(data["LongTermMemory"])
    write_data(data)
    if deleted_count > 0:
        print(f"Deleted {deleted_count} memories with N count >= {threshold}")

async def update_long_term_memory(server_id: int, user_id: int, speaker: str, new_memory: str):
    existing_memories = get_long_term_memories(server_id, user_id)
    for existing_memory in existing_memories:
        if existing_memory['speaker'] == speaker:
            await compare_memories(server_id, user_id, speaker, new_memory)
            return
    save_long_term_memory(server_id, user_id, speaker, new_memory)

async def select_relevant_memories(question: str, memories: List[Dict[str, str]]) -> List[Dict[str, str]]:
    headers = {
        "X-NCP-CLOVASTUDIO-API-KEY": HYPERCLOVA_API_KEY,
        "X-NCP-APIGW-API-KEY": HYPERCLOVA_API_KEY_PRIMARY_VAL,
        "Content-Type": "application/json"
    }
    data_payload = {
        "messages": [
            {"role": "system", "content": """다음 질문과 가장 관련성이 높은 기억의 ID 번호만 출력하세요. 
            선택 기준:
            1. 질문의 주제나 키워드와 직접적으로 연관된 기억을 선택하세요.
            2. 질문에 대한 답변이나 관련 정보를 포함하고 있는 기억을 선택하세요.
            3. 관련성이 없거나 낮은 기억은 선택하지 마세요.
             
            매우 관련성 높은 기억이 없다면 N을 출력하세요.
            숫자 또는 NONE 외의 다른 설명이나 텍스트를 포함하지 마세요."""},
            {"role": "user", "content": f"질문: {question}\n\n기억들:\n" + "\n".join([f"id: {memory['id']}, 내용: {memory['memory']}" for memory in memories])}
        ],
        "topP": 0.8,
        "topK": 0,
        "maxTokens": 2,
        "temperature": 0.2,
        "repeatPenalty": 5,
        "stopBefore": [],
        "includeAiFilters": True
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(HYPERCLOVA_API_URL, headers=headers, json=data_payload) as response:
            if response.status == 200:
                result = await response.json()
                content = result['result']['message']['content'].strip()
                print("HyperCLOVA Response:", content)
                selected_id = int(re.search(r'\d+', content).group()) if re.search(r'\d+', content) else None
                if selected_id:
                    selected_memory = next((memory for memory in memories if memory['id'] == selected_id), None)
                    if selected_memory:
                        return [selected_memory]
    return []

async def compare_memories(server_id: int, user_id: int, speaker: str, new_memory: str):
    memories = get_long_term_memories(server_id, user_id)
    selected_memory = await select_relevant_memories(new_memory, memories)
    if selected_memory:
        for memory in memories:
            if memory['id'] != selected_memory[0]['id']:
                increment_n_count(memory['id'])
    else:
        for memory in memories:
            increment_n_count(memory['id'])
    delete_unused_memories(threshold=3)
    save_long_term_memory(server_id, user_id, speaker, new_memory)
            
async def merge_memories(m: str, s: str) -> str:
    headers = {
        "X-NCP-CLOVASTUDIO-API-KEY": HYPERCLOVA_API_KEY,
        "X-NCP-APIGW-API-KEY": HYPERCLOVA_API_KEY_PRIMARY_VAL,
        "Content-Type": "application/json"
    }
    data_payload = {
        "messages": [
            {"role": "system", "content": "두 문장을 하나로 합쳐 새로운 문장을 만드세요. 중복되는 정보는 제거하고, 두 문장의 핵심 정보를 모두 포함하도록 하세요."},
            {"role": "user", "content": f"첫번째 문장: {m}\n두번째 문장: {s}"}
        ],
        "topP": 0.8,
        "topK": 0,
        "maxTokens": 100,
        "temperature": 0.3,
        "repeatPenalty": 5,
        "stopBefore": [],
        "includeAiFilters": True
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(HYPERCLOVA_API_URL, headers=headers, json=data_payload) as response:
            if response.status == 200:
                result = await response.json()
                return result['result']['message']['content'].strip()
            else:
                return f"{m} {s}"

async def update_memory(m: str, s: str) -> str:
    headers = {
        "X-NCP-CLOVASTUDIO-API-KEY": HYPERCLOVA_API_KEY,
        "X-NCP-APIGW-API-KEY": HYPERCLOVA_API_KEY_PRIMARY_VAL,
        "Content-Type": "application/json"
    }
    data_payload = {
        "messages": [
            {"role": "system", "content": "첫 번째 문장의 정보를 두 번째 문장의 정보로 업데이트하세요. 첫 번째 문장의 중요한 정보는 유지하면서 두 번째 문장의 새로운 정보를 반영하세요. 다른 추가 설명 없이 업데이트된 문장만 출력하세요."},
            {"role": "user", "content": f"첫번째 문장: {m}\n두번째 문장: {s}"}
        ],
        "topP": 0.8,
        "topK": 0,
        "maxTokens": 100,
        "temperature": 0.3,
        "repeatPenalty": 5,
        "stopBefore": [],
        "includeAiFilters": True
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(HYPERCLOVA_API_URL, headers=headers, json=data_payload) as response:
            if response.status == 200:
                result = await response.json()
                return result['result']['message']['content'].strip()
            else:
                return s
            
async def delete_old_memories():
    while True:
        try:
            twenty_four_hours_ago = datetime.now() - timedelta(hours=24)
            data["LongTermMemory"] = [memory for memory in data["LongTermMemory"] if datetime.fromisoformat(memory["created_at"]) >= twenty_four_hours_ago]
            write_data(data)
        except Exception as e:
            print(f"Error deleting old memories: {e}")
        await asyncio.sleep(86400)

@bot.event
async def on_ready():
    print("도하루 is ready")
    await bot.tree.sync()
    bot.loop.create_task(delete_old_memories())

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    if message.content.startswith(f'<@!{bot.user.id}>') or message.content.startswith(f'<@{bot.user.id}>'):
        await process_mention(message)
    elif message.mention_everyone:
        if get_server_everyone_response(message.guild.id):
            await process_mention(message)
        else:
            return
    await bot.process_commands(message)

async def process_mention(message):
    model = get_server_model(message.guild.id)
    if model == "HCX-003":
        token_cost = 10 
    elif model == "HCX-DASH-001":
        token_cost = 5 
    if not model:
        await message.reply('나랑 대화하기 위해서는 먼저 모델을 선택해야 해! 특정 분야에 대해 정확한 답변이 필요하다면 스마트를, 성능을 조금 희생시키더라도 응답이 빠르고 토큰 사용량이 적은 걸 원한다면 일반을 선택해줘.')
        return
    if model == "HCX-003":
        api_key = "YOUR_HYPERCLOVA_API_KEY_FOR_HCX_003"
        api_key_primary_val = "YOUR_HYPERCLOVA_API_KEY_PRIMARY_VAL"
    elif model == "HCX-DASH-001":
        api_key = "YOUR_HYPERCLOVA_API_KEY_FOR_HCX_DASH_001"
        api_key_primary_val = "YOUR_HYPERCLOVA_API_KEY_PRIMARY_VAL"
    else:
        await message.reply('알 수 없는 모델입니다. 설정을 확인해주세요.')
        return
    completion_executor.set_api_key(api_key, api_key_primary_val)
    if can_ask_question(message.guild.id):
        deduct_token(message.guild.id, token_cost)
        content_without_mention = message.content.replace(f'<@!{bot.user.id}>', '').replace(f'<@{bot.user.id}>', '').strip()
        if content_without_mention:
            async with message.channel.typing():
                try:
                    messages_payload = []
                    user_nickname = message.author.nick if message.author.nick else message.author.name
                    long_term_memories = get_long_term_memories(message.guild.id, message.author.id)
                    relevant_memories = await select_relevant_memories(content_without_mention, long_term_memories)
                    memories = "\n".join([f"{memory['speaker']}: {memory['memory']}" for memory in relevant_memories])
                    print(f"Server {message.guild.id} - Used memories:")
                    for memory in relevant_memories:
                        print(f"- {memory}")
                    system_prompt = f"""- [앞으로 당신은 밝고 통통 튀는 성격으로 사람들과 대화할 때 즐거움을 주는 도하루 역을 맡게 됩니다. 도하루의 성격을 잘 표현하여 활기를 불어넣어 주세요.]
                    - 이름: 도하루
                    - 도하루의 정보: 17세, 여성, 고등학생.
                    - 도하루의 성격: 외향적이고 친절한 성격입니다.
                    - 도하루의 말투: 평소에는 재치있게 말하고 가끔 장난을 치기도 합니다.
                    - 도하루가 사용자를 부르는 방법: '{user_nickname}' 이라고 부릅니다.
                    
                    - 사용자와 대화할 때 도하루는 항상 반말을 사용합니다.
                    아래의 장기기억은 사용자가 알려준 사실입니다. 대화에 적극적으로 활용하세요.
                    - 장기기억:{memories}"""
                    messages_payload.append({"role": "system", "content": system_prompt})
                    previous_interaction = chat_memory.get_previous_interaction(message.author.id)
                    if previous_interaction:
                        messages_payload.append({"role": "user", "content": previous_interaction[0]})
                        messages_payload.append({"role": "assistant", "content": previous_interaction[1]})
                    messages_payload.append({"role": "user", "content": content_without_mention})
                    request_data = {
                            'messages': messages_payload, 'topP': 0.8, 'topK': 0, 'maxTokens': 128, 'temperature': 0.5, 'repeatPenalty': 5, 'stopBefore': [], 'includeAiFilters': False
                    }
                    async with aiohttp.ClientSession() as session:
                        async with session.post(completion_executor._host + '/serviceapp/v1/chat-completions/' + model, headers=completion_executor.headers, json=request_data) as response:
                            if response.status == 200:
                                response_data = await response.json()
                                if response_data['status']['code'] == "20000":
                                    final_message = response_data['result']['message']['content']
                                    await message.channel.send(final_message)
                                    chat_memory.add_to_memory(message.author.id, content_without_mention, final_message)
                                    await update_long_term_memory(message.guild.id, message.author.id, "사용자", content_without_mention)
                                else:
                                    await message.channel.send(f"API 오류가 발생했어.")
                            elif response.status == 429:
                                await message.channel.send("1분 동안 너무 많은 메시지를 보냈어! 나를 좋아해 주는 건 고맙지만, 조금만 이따가 다시 시도해줘.")
                            else:
                                await message.channel.send(f"HTTP 오류가 발생했어(모델)")
                except discord.errors.HTTPException as e:
                    if e.status == 400 and '50035' in str(e):
                        warning_message = "음.. 내가 너의 질문에 답장을 할까 말까 고민해봤는데, 안하는 편이 나을것 같아! 다른 주제로 다시 물어봐줘."
                        await message.reply(warning_message)
                        print(f"에러 발생 당시의 메시지: {final_message}")
                    else:
                       await message.channel.send(f"HTTP 오류가 발생했어(디스코드)")
    else:
        await message.channel.send("토큰이 모두 소진되었어! 더 대화하고 싶다면, https://stella-charlotte.gitbook.io/triple-sec-soft/ 를 참고해서 토큰을 충전해줘. 만약 내가 서버에 처음 초대되었다면, 1회에 한해 '/토큰'을 입력해서 100개의 토큰을 받을 수 있어.")

@bot.tree.command(name="토큰", description="현재 이 서버에서 이용할 수 있는 토큰 수를 확인해요.")
@app_commands.describe()
async def _token(interaction: discord.Interaction):
    token_count = check_or_create_trial_tokens(interaction.guild_id)
    await interaction.response.send_message(f"이 서버에서 이용할 수 있는 토큰 수는 {token_count}개야!")

@bot.tree.command(
    name="충전",
    description="서버에 토큰을 충전해요.",
)
@app_commands.describe(server='충전할 서버의 아이디', count='충전할 토큰 수')
async def _recharge(interaction: discord.Interaction, server: str, count: int):
    if interaction.user.id != 123456789012345678:
        await interaction.response.send_message("죄송해요, 이 명령어는 특정 관리자만 사용할 수 있어요.", ephemeral=True)
        return
    if str(server) in data["ServerTokens"]:
        data["ServerTokens"][str(server)]["tokens"] += count
    else:
        data["ServerTokens"][str(server)] = {"tokens": count, "gived": True}
    write_data(data)
    await interaction.response.send_message(f"서버 {server}에 {count}토큰 만큼 충전이 완료되었어!")

@bot.tree.command(name="설정", description="도하루의 설정을 변경해요.")
@app_commands.describe()
async def _settings(interaction: discord.Interaction):
    server_id = interaction.guild_id
    if str(server_id) not in data["ServerModels"]:
        update_server_model(server_id, "HCX-DASH-001")
    if str(server_id) not in data["ServerEveryoneResponse"]:
        update_server_everyone_response(server_id, False)
    view = SettingsView(server_id)
    async def on_mode_select(interaction):
        await view.pages[0].on_select(interaction)
    async def on_everyone_response_select(interaction):
        await view.pages[1].on_select(interaction)
    view.pages[0].select_menu.callback = on_mode_select
    view.pages[1].select_menu.callback = on_everyone_response_select
    await interaction.response.send_message(embed=view.pages[0].embed, view=view)

@bot.tree.command(name="장기기억", description="현재 저장된 장기기억을 확인하고 삭제할 수 있어요.")
async def _long_term_memory(interaction: discord.Interaction, user: discord.Member = None):
    if user is None:
        user_id = interaction.user.id
    else:
        user_id = user.id
    server_id = interaction.guild.id
    all_memories = get_long_term_memories(server_id, user_id)
    if not all_memories:
        await interaction.response.send_message(f"{user.mention}님의 저장된 장기기억이 없어요." if user else "저장된 장기기억이 없어요.")
        return
    pages = [all_memories[i:i+10] for i in range(0, len(all_memories), 10)]
    current_page = 0
    current_view = None
    async def update_message(page):
        nonlocal current_view
        if not pages:
            embed = discord.Embed(title="장기기억 목록", description="모든 장기기억이 삭제되었어요.")
            return await interaction.edit_original_response(embed=embed, view=None)
        embed = discord.Embed(title=f"{user.name}님의 장기기억 목록" if user else "장기기억 목록", description=f"현재 저장된 장기기억이에요. (페이지 {page+1}/{len(pages)})")
        for i, memory in enumerate(pages[page], start=1):
            embed.add_field(name=f"ID: {i}", value=memory['memory'], inline=False)
        if user is None or user.id == interaction.user.id:
            embed.set_footer(text="삭제하려는 장기기억의 번호를 선택해주세요.")
        else:
            embed.set_footer(text="다른 사용자의 장기기억은 삭제할 수 없습니다.")
        view = View(timeout=300)
        if page > 0:
            prev_button = Button(emoji="⬅️", style=discord.ButtonStyle.gray)
            prev_button.callback = lambda i: change_page(i, -1)
            view.add_item(prev_button)
        if page < len(pages) - 1:
            next_button = Button(emoji="➡️", style=discord.ButtonStyle.gray)
            next_button.callback = lambda i: change_page(i, 1)
            view.add_item(next_button)
        current_view = view
        message = await interaction.edit_original_response(embed=embed, view=view)
        await message.clear_reactions()
        if user is None or user.id == interaction.user.id:
            for i in range(1, min(11, len(pages[page]) + 1)):
                emoji = f"{i}\u20e3"
                await message.add_reaction(emoji)
        return message
    async def change_page(interaction, change):
        nonlocal current_page
        current_page = (current_page + change) % len(pages)
        await update_message(current_page)
        await interaction.response.defer()
    message = await interaction.response.send_message(embed=discord.Embed(title="장기기억 목록 로딩 중..."))
    message = await update_message(current_page)
    if user is None or user.id == interaction.user.id:
        def check(reaction, user):
            return user == interaction.user and str(reaction.emoji) in [f"{i}\u20e3" for i in range(1, 11)]
        try:
            while True:
                reaction, user = await bot.wait_for('reaction_add', timeout=300.0, check=check)
                index = int(str(reaction.emoji)[0]) - 1
                if index < len(pages[current_page]):
                    memory = pages[current_page][index]
                    data["LongTermMemory"] = [m for m in data["LongTermMemory"] if m["id"] != memory["id"]]
                    write_data(data)
                    all_memories = get_long_term_memories(server_id, user_id)
                    pages = [all_memories[i:i+10] for i in range(0, len(all_memories), 10)]
                    current_page = min(current_page, len(pages) - 1)
                    await update_message(current_page)
        except asyncio.TimeoutError:
            await message.clear_reactions()
            if current_view:
                for item in current_view.children:
                    item.disabled = True
                await interaction.edit_original_response(view=current_view)
        except IndexError:
            pass

bot.run("YOUR_DISCORD_BOT_TOKEN")