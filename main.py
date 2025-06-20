from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
import astrbot.api.message_components as Comp
from astrbot.core.utils.session_waiter import (
    session_waiter,
    SessionController,
)
import aiohttp
import json
import re
from typing import List, Any

@register(
    "astrbot_plugin_check-dst-room",
    "EncodedWitcher",
    "提供饥荒服务器大厅查询的插件",
    "1.1.7")
class MyPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.session: aiohttp.ClientSession | None = None
        self.region_default = self.config.get("region","default")
        self.region = self.region_default
        self.region_list=["us-east-1","eu-central-1","ap-southeast-1","ap-east-1"]
        self.platform = "Steam"
        self.matched_rooms = []

    async def initialize(self):
        self.session = aiohttp.ClientSession()
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""

    @filter.command("查房")
    async def check_room(self, event: AstrMessageEvent):
        """查询饥荒服务器大厅"""
        try:
            yield event.plain_result("请输入需要查询的房间关键字\n"+
                                     "可选参数:地区(用空格隔开)\n"+
                                     "如:查 111 ap-east-1\n"+
                                     "地区列表:ap-east-1(默认),us-east-1,eu-central-1,ap-southeast-1\n"
                                     "输入退出即可退出查询")

            @session_waiter(timeout=180, record_history_chains=False)
            async def waiter(controller: SessionController, event: AstrMessageEvent):
                room_check=event.message_str.split(' ')
                message_result = event.make_result()
                nodes = Comp.Nodes([])
                uin=event.get_self_id()

                if len(room_check)==2 or len(room_check)==3:
                    check_mode=room_check[0]
                    room_keyword=room_check[1]

                    if check_mode == "查" :
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
                                            self.matched_rooms = []
                                            for idx, room in enumerate(room_list, 1):
                                                if room_keyword.lower() in room["name"].lower():
                                                    self.matched_rooms.append({
                                                        "id": idx,
                                                        "name": room["name"],
                                                        "rowId": room["__rowId"],
                                                        "maxconnections": room["maxconnections"],
                                                        "connected": room["connected"],
                                                        "season": room["season"],
                                                        "mode": room["intent"]
                                                    })
                                            content=[Comp.Plain(f"输入详情+编号查看详情")]
                                            nodes.nodes.append(self.content_to_node(uin,content))
                                            content=[Comp.Plain(f"如:详情 1")]
                                            nodes.nodes.append(self.content_to_node(uin, content))
                                            season_map = {
                                                "spring": "春天", "summer": "夏天", "autumn": "秋天", "winter": "冬天"
                                            }
                                            mode_map = {
                                                "endless": "无尽", "survival": "生存", "wilderness": "荒野", "lightsout": "永夜","relaxed": "休闲"
                                            }
                                            for room in self.matched_rooms:
                                                content= [Comp.Plain(f"{room['id']}. {room['name']}"
                                                                     f"({room['connected']}/{room['maxconnections']})"
                                                                     f"{season_map.get(room['season'], room['season'])}"
                                                                     f"({mode_map.get(room['mode'], room['mode'])})")]
                                                nodes.nodes.append(self.content_to_node(uin, content))

                                        except (json.JSONDecodeError, KeyError) as e:
                                            self.region = self.region_default
                                            controller.stop()
                                    else:
                                        self.region = self.region_default
                                        content=[Comp.Plain(f"获取服务器列表失败，状态码: {response.status}")]
                                        message_result.chain = content
                                        controller.stop()
                            except aiohttp.ClientError as e:
                                # 捕获所有可能的网络连接错误
                                self.region = self.region_default
                                content = [Comp.Plain(f"无法连接到服务器，请检查网络或稍后再试。错误: {type(e).__name__}")]

                                message_result.chain = content
                                controller.stop()
                        else:
                            content = [Comp.Plain(f"参数错误")]

                            message_result.chain = content
                            controller.stop()

                    elif check_mode == "详情" :

                        try:
                            room_id = int(room_check[1])  # 将 room_id 转换为整数
                        except ValueError:
                            content = [Comp.Plain("房间编号请输入数字。")]
                            message_result.chain = content
                            controller.stop()

                        room_region = self.region
                        url=f"https://lobby-v2-{room_region}.klei.com/lobby/read" #post方法
                        #token="pds-g^KU_XjTVZdYQ^uvwqLfAY/Gim/7vJONmsxtxtrt4lnFJB0B1xVI09Ti8="
                        row_id = next((room['rowId'] for room in self.matched_rooms if room['id'] == room_id), None)
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
                                        content=[(Comp.Plain(f"错误：服务器返回的数据中没有房间信息。"))]
                                        message_result.chain = content
                                        controller.stop()

                                    room_info = room_data["GET"][0]

                                    # --- 提取和格式化信息 ---
                                    # 1. 基本信息
                                    room_name = room_info.get('name', '未知房间名')
                                    connected_players = room_info.get('connected', 0)
                                    max_players = room_info.get('maxconnections', 0)

                                    # 2. 游戏状态
                                    # 调用辅助函数解析天数
                                    day_info = self.parse_day_from_data(room_info.get('data', ''))
                                    season_map = {
                                        "spring": "春天", "summer": "夏天", "autumn": "秋天", "winter": "冬天"
                                    }
                                    season = season_map.get(room_info.get('season', '未知'),'未知')

                                    # 3. 房间设置
                                    # 使用三元表达式将布尔值转换为更友好的文本
                                    has_password = "是" if room_info.get('password', False) else "否"

                                    # 4. 玩家列表
                                    # 调用辅助函数解析玩家列表
                                    players_list = self.parse_players_from_string(room_info.get('players', ''))
                                    players_str = ", ".join(players_list) if players_list else "无"

                                    # 5. 模组列表
                                    mods_enabled = room_info.get('mods', False)
                                    mods_info_list = room_info.get('mods_info', [])
                                    parsed_mods = self.parse_mods_info(mods_enabled, mods_info_list)

                                    #6. 直连代码
                                    ip = room_info.get("__addr","未知")
                                    port = room_info.get("port","未知")
                                    direct_connect_code = f"c_connect(\"{ip}\",\"{port}\") 启用密码:{has_password}"


                                    # --- 构建输出 ---
                                    content=[Comp.Plain(f"房间名: {room_name}")]
                                    nodes.nodes.append(self.content_to_node(uin, content))
                                    content=[Comp.Plain(f"人数: {connected_players} / {max_players}")]
                                    nodes.nodes.append(self.content_to_node(uin, content))
                                    content=[Comp.Plain(f"天数: {day_info} ({season_map.get(season, season)})")]
                                    nodes.nodes.append(self.content_to_node(uin,content))
                                    content=[Comp.Plain(f"在线玩家: {players_str}")]
                                    nodes.nodes.append(self.content_to_node(uin,content))
                                    content=[Comp.Plain(f"模组列表: {parsed_mods}")]
                                    nodes.nodes.append(self.content_to_node(uin,content))
                                    content=[Comp.Plain(f"直连代码: {direct_connect_code}")]
                                    nodes.nodes.append(self.content_to_node(uin, content))


                                except Exception as e:
                                    # 捕获可能的JSON解析错误或其他异常
                                    content=[(Comp.Plain(f"处理房间数据时出错: {e}"))]

                                    message_result.chain = content
                                    controller.stop()
                            else:
                                # 处理请求失败的情况
                                content=[(Comp.Plain(f"查询失败，服务器状态码: {response.status},row_id={row_id}"))]

                                message_result.chain = content
                                controller.stop()


                elif len(room_check)== 1:
                    if room_check[0] == "退出":
                        content=[Comp.Plain("退出查房")]
                        message_result.chain=content
                        controller.stop()

                message_result.chain=[nodes]
                await event.send(message_result)
                controller.keep(timeout=180, reset_timeout=True)
                #controller.stop()

            try:
                await waiter(event)
            except TimeoutError as _:  # 当超时后，会话控制器会抛出 TimeoutError
                yield event.plain_result("查房超时已自动退出")
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

    def content_to_node(self, uin:str, content: [])-> Comp.Node:
        node = Comp.Node(
            uin=uin,
            name="",
            content=content
        )
        return node

    def parse_day_from_data(self, data_string: str) -> str:
        """从 'data' 字段的字符串中解析出游戏天数"""
        # 使用正则表达式匹配
        match = re.search(r"day=(\d+)", data_string)
        match1 = re.search(r"dayselapsedinseason=(\d+)", data_string)
        match2 = re.search(r"daysleftinseason=(\d+)", data_string)
        now_day = int(match.group(1)) if match else 0
        days_elapsed = int(match1.group(1)) if match1 else 0
        days_left = int(match2.group(1)) if match2 else 0
        season_days = days_elapsed + days_left
        if match:
            return f"{now_day}/{season_days}"
        return "未知天数"

    def parse_players_from_string(self, players_string: str) -> list[str]:
        """从 'players' 字段的字符串中解析出所有玩家的名字"""
        # 使用正则表达式匹配所有 "name=" 后面的带引号的字符串
        # re.findall 会返回所有匹配到的玩家名列表
        matches = re.findall(r'name="([^"]+)"', players_string)
        return matches


    def parse_mods_info(self, mods_enabled: bool, mods_info_list: List[Any]) -> List[str]:
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