from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
import astrbot.api.message_components as Comp
from astrbot.core.utils.session_waiter import (
    session_waiter,
    SessionController,
)
import aiohttp
import gzip
import json
import re
from typing import List, Any

@register(
    "astrbot_plugin_check-dst-room",
    "EncodedWitcher",
    "提供饥荒服务器大厅查询的插件",
    "1.0.4")
class MyPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.session: aiohttp.ClientSession | None = None
        self.region_default = self.config.get("region","default")
        self.region = self.region_default
        self.region_list=["us-east-1","eu-central-1","ap-southeast-1","ap-east-1"]
        self.platform = "Steam"
         #get请求


    async def initialize(self):
        self.session = aiohttp.ClientSession()
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
    
    # 注册指令的装饰器。指令名为 helloworld。注册成功后，发送 `/helloworld` 就会触发这个指令，并回复 `你好, {user_name}!`
    @filter.command("helloworld")
    async def helloworld(self, event: AstrMessageEvent):
        """这是一个 hello world 指令""" # 这是 handler 的描述，将会被解析方便用户了解插件内容。建议填写。
        user_name = event.get_sender_name()
        message_str = event.message_str # 用户发的纯文本消息字符串
        message_chain = event.get_messages() # 用户所发的消息的消息链 # from astrbot.api.message_components import *
        logger.info(message_chain)
        yield event.plain_result(f"Hello, {user_name}, 你发了 {message_str}!") # 发送一条纯文本消息

    @filter.command("查房")
    async def check_room(self, event: AstrMessageEvent):
        """查询饥荒服务器大厅"""
        try:
            yield event.plain_result("请输入需要查询的房间关键字\n"+
                                     "可选参数:地区(用空格隔开)\n"+
                                     "如:查房 111 ap-east-1\n"+
                                     "地区列表:ap-east-1(默认),us-east-1,eu-central-1,ap-southeast-1")

            @session_waiter(timeout=30, record_history_chains=False)
            async def waiter(controller: SessionController, event: AstrMessageEvent):
                room_check=event.message_str.split(' ')
                message_result = event.make_result()
                chain=[]
                matched_rooms = []
                if len(room_check)==2 or len(room_check)==3:
                    check_mode=room_check[0]
                    room_keyword=room_check[1]
                    if check_mode == "查房" :
                        if len(room_check) == 3:
                            room_region = room_check[2]
                            self.region = room_region
                        else:
                            room_region = self.region_default
                        #room_region = room_check[2] if len(room_check) == 3 else self.region
                        if room_region in self.region_list:
                            url = f"https://lobby-v2-cdn.klei.com/{room_region}-Steam.json.gz"
                            try:
                                async with self.session.get(url) as response:
                                    if response.status == 200:
                                        try:
                                            compressed_data = await response.read()

                                            #decompressed_data = gzip.decompress(compressed_data)

                                            #servers_data = json.loads(decompressed_data)
                                            servers_data = json.loads(compressed_data)

                                            room_list = servers_data.get("GET", [])
                                            #room_list_len = len(room_list)
                                            for idx, room in enumerate(room_list, 1):
                                                if room_keyword.lower() in room["name"].lower():
                                                    matched_rooms.append({
                                                        "id": idx,
                                                        "name": room["name"],
                                                        "rowId": room["__rowId"],
                                                        "maxconnections": room["maxconnections"],
                                                        "connected": room["connected"],
                                                        "season": room["season"],
                                                        "mode": room["intent"]
                                                    })
                                            chain.append(Comp.Plain("输入详情+编号查看详情:\n"))
                                            chain.append(Comp.Plain("如:详情 1\n"))
                                            season_map = {
                                                "spring": "春天", "summer": "夏天", "autumn": "秋天", "winter": "冬天"
                                            }
                                            mode_map = {
                                                "endless": "无尽", "survival": "生存", "wilderness": "荒野", "lightsout": "永夜","relaxed": "休闲"
                                            }
                                            for room in matched_rooms:
                                                chain.append(Comp.Plain(f"{room['id']}. {room['name']}"
                                                                        f"({room['connected']}/{room['maxconnections']})"
                                                                        f"{season_map.get(room['season'], room['season'])}"
                                                                        f"({mode_map.get(room['mode'], room['mode'])})\n"))

                                        except (gzip.BadGzipFile, json.JSONDecodeError, KeyError) as e:
                                            # 捕获所有可能的数据处理错误
                                            self.region = self.region_default
                                            # 向用户报告一个更友好的错误信息
                                            chain = [Comp.Plain(
                                                f"处理服务器数据时出错，请稍后再试。错误: {type(e).__name__}")]
                                            message_result.chain = chain
                                            await event.send(message_result)
                                            controller.stop()
                                    else:
                                        self.region = self.region_default
                                        chain=[Comp.Plain(f"获取服务器列表失败，状态码: {response.status}")]
                                        message_result.chain = chain
                                        await event.send(message_result)
                                        controller.stop()
                            except aiohttp.ClientError as e:
                                # 捕获所有可能的网络连接错误
                                self.region = self.region_default
                                chain = [Comp.Plain(f"无法连接到服务器，请检查网络或稍后再试。错误: {type(e).__name__}")]
                                message_result.chain = chain
                                await event.send(message_result)
                                controller.stop()
                        else:
                            chain = [Comp.Plain("参数错误")]
                            message_result.chain = chain
                            await event.send(message_result)
                            controller.stop()
                    elif check_mode == "详情" :
                        room_id = room_check[1]
                        room_region = self.region
                        url=f"https://lobby-v2-{room_region}.klei.com/lobby/read" #post方法
                        #token="pds-g^KU_XjTVZdYQ^uvwqLfAY/Gim/7vJONmsxtxtrt4lnFJB0B1xVI09Ti8="
                        row_id = next((room['rowId'] for room in matched_rooms if room['id'] == room_id), None)
                        payload = {
                            "__token": "pds-g^KU_XjTVZdYQ^uvwqLfAY/Gim/7vJONmsxtxtrt4lnFJB0B1xVI09Ti8=",
                            "__gameID": "DST",
                            "query": {
                                "__rowId": f"{row_id}"
                            }
                        }
                        async with self.session.post(url, json=payload) as response:
                            # 确保请求成功
                            if response.status == 200:
                                try:
                                    room_data = await response.json()

                                    # 安全地检查 "GET" 列表是否为空
                                    if not room_data.get("GET"):
                                        chain.append(Comp.Plain("错误：服务器返回的数据中没有房间信息。"))
                                        message_result.chain = chain
                                        await event.send(message_result)
                                        controller.stop()

                                    room_info = room_data["GET"][0]

                                    # --- 提取和格式化信息 ---
                                    # 1. 基本信息
                                    room_name = room_info.get('name', '未知房间名')
                                    connected_players = room_info.get('connected', 0)
                                    max_players = room_info.get('maxconnections', 0)

                                    # 2. 游戏状态
                                    # 调用辅助函数解析天数
                                    day_info = parse_day_from_data(room_info.get('data', ''))
                                    season_map = {
                                        "spring": "春天", "summer": "夏天", "autumn": "秋天", "winter": "冬天"
                                    }
                                    season = room_info.get('season', '未知')

                                    # 3. 房间设置
                                    # 使用三元表达式将布尔值转换为更友好的文本
                                    has_password = "是" if room_info.get('password', False) else "否"

                                    # 4. 玩家列表
                                    # 调用辅助函数解析玩家列表
                                    players_list = parse_players_from_string(room_info.get('players', ''))
                                    players_str = ", ".join(players_list) if players_list else "无"

                                    # 5. 模组列表
                                    mods_enabled = room_info.get('mods', False)
                                    mods_info_list = room_info.get('mods_info', [])
                                    parsed_mods = parse_mods_info(mods_enabled, mods_info_list)

                                    #6. 直连代码
                                    ip = room_info.get("__addr","未知")
                                    port = room_info.get("__port","未知")
                                    direct_connect_code = f"c_connect(\"{ip}\",\"{port}\") 启用密码:{has_password}"


                                    # --- 构建更丰富的输出 ---
                                    chain.append(Comp.Plain(
                                        f"🚪 房间名: {room_name}\n"
                                        f"👥 人数: {connected_players} / {max_players}\n"
                                        f"☀️ 天数: {day_info} ({season_map.get(season, season)})\n"
                                        f"👤 在线玩家: {players_str}"
                                        f"🧩 模组列表: {parsed_mods}"
                                        f"🔑 直连代码: {direct_connect_code}"
                                    ))

                                except Exception as e:
                                    # 捕获可能的JSON解析错误或其他异常
                                    chain.append(Comp.Plain(f"处理房间数据时出错: {e}"))
                            else:
                                # 处理请求失败的情况
                                chain.append(Comp.Plain(f"查询失败，服务器状态码: {response.status}"))
                    else:
                        chain = [Comp.Plain("输入错误")]
                        message_result.chain = chain
                        await event.send(message_result)
                        controller.stop()
                else:
                    chain = [Comp.Plain("输入错误")]
                    message_result.chain=chain
                    await event.send(message_result)
                    controller.stop()

                message_result.chain = chain
                await event.send(message_result)
                controller.stop()

            try:
                await waiter(event)
            except TimeoutError as _:  # 当超时后，会话控制器会抛出 TimeoutError
                yield event.plain_result("查房超时")
            except Exception as e:
                yield event.plain_result("发生错误，请联系管理员: " + str(e))
            finally:
                event.stop_event()

        except Exception as e:
            logger.error("check-dst-room error: " + str(e))

    async def terminate(self):
        if self.session:
            await self.session.close()
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""

def parse_day_from_data(data_string: str) -> str:
    """从 'data' 字段的字符串中解析出游戏天数"""
    # 使用正则表达式匹配
    match = re.search(r"day=(\d+)", data_string)
    match1 = re.search(r"dayselapsedinseason=(\d+)", data_string)
    match2 = re.search(r"daysleftinseason=(\d+)", data_string)
    now_day = match.group(1)
    season_days = match1.group(1)+match2.group(1)
    if match:
        return f"{now_day}/{season_days}"
    return "未知天数"

def parse_players_from_string(players_string: str) -> list[str]:
    """从 'players' 字段的字符串中解析出所有玩家的名字"""
    # 使用正则表达式匹配所有 "name=" 后面的带引号的字符串
    # re.findall 会返回所有匹配到的玩家名列表
    matches = re.findall(r'name="([^"]+)"', players_string)
    return matches


def parse_mods_info(mods_enabled: bool, mods_info_list: List[Any]) -> List[str]:
    """
    解析 mods_info 列表，只返回模组名称的列表。

    Args:
        mods_enabled: 服务器是否启用了模组。
        mods_info_list: 从服务器获取的扁平化模组信息列表。

    Returns:
        一个只包含每个模组名称的字符串列表。
    """
    if not mods_enabled or not mods_info_list:
        return []

    parsed_mods = []
    MOD_INFO_CHUNK_SIZE = 5  # 每个模组信息占5个元素

    try:
        for i in range(0, len(mods_info_list), MOD_INFO_CHUNK_SIZE):
            chunk = mods_info_list[i: i + MOD_INFO_CHUNK_SIZE]

            if len(chunk) == MOD_INFO_CHUNK_SIZE:
                # 【关键改动】我们现在只提取模组名称 (chunk[1])
                mod_name = chunk[1]
                parsed_mods.append(mod_name)  # 直接添加模组名称

    except (TypeError, IndexError) as e:
        print(f"Error parsing mods_info: {e}")
        return ["模组列表解析失败"]

    return parsed_mods