from configs.config import Config
from nonebot import on_message, on_command
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, Message, GroupMessageEvent
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from utils.http_utils import AsyncHttpx
from utils.utils import get_message_text
from services.log import logger
import random
import time

__zx_plugin_name__ = "ChatGPT"
__plugin_usage__ = """
usage：
    问答：问题
    设置历史记录长度：上下文长度+数字(建议不超过20)
    清空历史记录：重置世界树
""".strip()
__plugin_des__ = "ChatGPT"
__plugin_type__ = ("一些工具",)
__plugin_version__ = 0.1
__plugin_author__ = "gaoy"
__plugin_settings__ = {"level": 5, "default_status": True, "limit_superuser": False, }

Config.add_plugin_config("ChatGPT", "API_KEY", None, name="ChatGPT", help_="从Azure OpenAI Service 获取", default_value=None, )
Config.add_plugin_config("ChatGPT", "PROXY", None, name="ChatGPT", help_="如有代理需要，在此处填写你的代理地址", default_value=None, )

ai = on_message(priority=997)
possibility_set = on_command("设定ChatGPT回复概率", priority=5, block=True)
reset = on_command("重置ChatGPT", priority=5, block=True)
system_prompt_set = on_command("预设ChatGPT", priority=5, block=True)

url = 'https://mare.openai.azure.com/openai/deployments/ChatGPT/completions?api-version=2022-12-01'
AI_NAME = 'ChatGPT'
DEFAULT_POSSIBILITY = 0.2

chatgpt_last_time = time.time()
conversations = {}
possibilities = {}
context_length = 5

api_key = Config.get_config("ChatGPT", "API_KEY")
proxy = Config.get_config("ChatGPT", "PROXY")
system_prompt  = ''

@reset.handle()
async def _(event: MessageEvent):
    global conversations, system_prompt
    chat_id = str(event.group_id) if isinstance(event, GroupMessageEvent) else str(event.user_id)
    system_prompt = ''
    try:
        conversations.pop(chat_id)
    except:
        pass
    await reset.send("ChatGPT上下文重置完毕")

@system_prompt_set.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    global conversations, system_prompt
    msg = arg.extract_plain_text().strip()
    if not msg:
        return
    
    chat_id = str(event.group_id) if isinstance(event, GroupMessageEvent) else str(event.user_id)
    system_prompt = msg
    try:
        conversations.pop(chat_id)
    except:
        pass
    await system_prompt_set.finish("预设ChatGPT完成！")

@possibility_set.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    global possibilities
    msg = arg.extract_plain_text().strip()
    if not msg:
        return
    
    possibility = float(msg)
    chat_id = str(event.group_id) if isinstance(event, GroupMessageEvent) else str(event.user_id)
    possibilities[chat_id] = possibility
    
    await system_prompt_set.finish(f"设定ChatGPT回复概率为：{possibility}")

@ai.handle()
async def _(bot: Bot, event: MessageEvent):
    global conversations, context_length, chatgpt_last_time

    msg = get_message_text(event.json())
    if not msg:
        return

    chat_id = str(event.group_id) if isinstance(event, GroupMessageEvent) else str(event.user_id)
    conversation = conversations.get(chat_id, [])
    if not conversation:
        conversation = [[], context_length]
        conversations[chat_id] = conversation

    possibility = possibilities.get(chat_id, DEFAULT_POSSIBILITY)
    conversation[0].append({"sender": event.user_id, "text": msg})
    if random.random() > possibility:
        logger.info(f"ChatGPT received message but will not call API")
        return
        
    if not await SUPERUSER(bot, event):
        if (latency := time.time() - chatgpt_last_time) < 0:
            logger.info(f"ChatGPT received message but will not call API. latency: {latency}")
            return
    else:
        logger.info(f"ChatGPT received message and skip all the limitation")

    try:
        response = await ask(conversation[0])
        chatgpt_last_time = time.time()
    except Exception as e:
        return await ai.finish(str(e))
    conversation[0].append({"sender": AI_NAME, "text": response})

    # Limit the conversation to no larger than 10 turn-around
    conversation[0] = conversation[0] if len(conversation[0]) < conversation[1] * 2 else conversation[0][2:]
    conversations[chat_id] = conversation

    await ai.finish(response)

def create_prompt(messages):
    global system_prompt
    system_message_template = "<|im_start|>system\n{}\n<|im_end|>"
    system_message = system_message_template.format(system_prompt)
    prompt = system_message
    message_template = "\n<|im_start|>{}\n{}\n<|im_end|>"
    for message in messages:
        prompt += message_template.format(message['sender'], message['text'])
    prompt += f"\n<|im_start|>{AI_NAME}\n"
    return prompt

async def ask(conversation):
    logger.info(f"ChatGPT sending conversation {conversation}")
    if not (key := Config.get_config("ChatGPT", "API_KEY")):
        raise Exception("未配置API_KEY,请在config.yaml文件中进行配置")
    
    proxies = {"https://": proxies} if (proxies := Config.get_config("ChatGPT", "PROXY")) else None
    prompt = create_prompt(conversation)
    header = {"api-key": key, "Content-Type": "application/json"}
    data = {
            "prompt": prompt,
            "max_tokens": 500,
            "temperature": 0.6,
            "frequency_penalty": 0,
            "presence_penalty": 0,
            "top_p": 0.95,
            "stop": ["<|im_end|>"]
            }
    
    response = await AsyncHttpx.post(url, json=data, headers=header, proxy=proxies)
    if 'choices' in (response := response.json()):
        return response['choices'][0]['text'].strip('\n')
    else:
        return response

