"""Woman command handlers"""
import os
import random
from typing import List

from pyrogram import Client, filters
from pyrogram.enums import ChatType
from pyrogram.types import ChatMember, InputMediaPhoto, Message

from src.plugins.help import command_handler
from src.security.permissions import requires_setting

NO_IMAGES_FOUND = "Изображения не найдены."
GENERAL_ERROR = "❌ Произошла ошибка! Попробуйте позже."

# Relationship terms and actions
RELATIONSHIP_TERMS = [
    "жена", "девушка", "любовница", "питомец", "сестра", "мама", "тёща",
    "ебнёт камнем", "изобьёт", "наступит на яйца", "оторвёт яйца", "выебет",
    "покажет ножки", "продемонстрирует сиськи", "задушит", "убьет", "изнасилует",
    "тихонечко", "фемверсия", "трапик", "приготовит хачапури", "сохнет по",
    "изменит", "даст никелевую камушку", "послушает музыку", "ненавидит",
    "любит", "будет подразнивать", "помурлычит в дискордике", "подарит цветы",
    "накормит борщом", "заставит мыть посуду", "познакомит с мамой",
    "напишет стихи", "отведет в кино", "сделает массаж", "испечет пирожки",
    "погладит по голове", "споет колыбельную", "научит готовить", "будет ревновать",
    "постирает носки", "заставит носить платье", "накрасит губы", "сделает прическу",
    "научит танцевать", "возьмет на шопинг", "будет пилить"
]

ACCUSATIVE_VERBS = [
    "жена", "девушка", "любовница", "питомец", "сестра", "мама", "тёща",
    "ебнёт камнем", "разорвёт", "насадит на кол", "зарежет", "засталкерит",
    "женская версия", "выебет", "задушит", "убьет", "изнасилует", "изобьёт",
    "оторвёт яйца", "будет подразнивать", "трапик", "ненавидит", "послушает музыку",
    "любит", "изничтожит пенис", "закуколдит", "посадит в тюрьму", "убаюкает перед сном",
    "фемверсия", "возьмет замуж", "сделает феминистом", "заставит готовить",
    "отправит мыть посуду", "накрасит губы", "оденет в платье", "научит вышивать",
    "отведет к маме", "заставит смотреть мелодрамы", "будет пилить",
    "заставит ходить по магазинам", "научит гладить", "заставит убираться",
    "научит стирать", "сделает домохозяйкой", "превратит в подкаблучника",
    "украдет носки", "спрячет права", "заберет зарплату", "заставит спать на диване", "возьмет в ЗАГС",
]


def get_image_owner_mapping(image_path: str) -> str:
    """Extract the platform and username from the directory name and create appropriate link"""
    # Get the parent directory name which contains the platform and username
    dir_name = os.path.basename(os.path.dirname(image_path))

    # Split by underscore to separate platform and username
    if "_" not in dir_name:
        return "Unknown source"

    platform, username = dir_name.split("_", 1)

    # Create appropriate link based on platform
    if platform == "tg":
        return f"[{username}](https://t.me/{username})"
    elif platform == "vk":
        return f"[{username}](https://vk.com/{username})"
    else:
        return "Unknown source"


def get_random_images(folder_path: str, count: int) -> List[str]:
    """Get random images from the specified folder"""
    images = []
    for root, _, files in os.walk(folder_path):
        for file in files:
            if file.lower().endswith((".png", ".jpg", ".jpeg", ".gif")):
                images.append(os.path.join(root, file))

    return random.sample(images, min(count, len(images))) if images else []


async def get_chat_members(client: Client, chat_id: int) -> List[ChatMember]:
    """Get list of chat members excluding bots"""
    try:
        return [member async for member in client.get_chat_members(chat_id) if not member.user.is_bot]
    except Exception:
        return []


@command_handler(
    commands=["woman", "women"],
    description="Отправляет случайные изображения женщин с забавными подписями",
    group="NSFW"
)
@Client.on_message(filters.command(["woman", "women", "females"]), group=2)
@requires_setting('nsfw')
async def woman_command(client: Client, message: Message):
    """Send random woman images with funny captions"""
    try:
        folder_path = "assets/woman"
        image_count = 4

        # Get the total count of images in the dataset
        total_images = sum(len([f for f in files if f.lower().endswith((".png", ".jpg", ".jpeg", ".gif"))])
                           for _, _, files in os.walk(folder_path))

        notification = await message.reply_text("🔍 Запрашиваем альтушек...", quote=True)

        # Retrieve random images, exit early if none found
        image_paths = get_random_images(folder_path, image_count)
        if not image_paths:
            await message.reply_text(NO_IMAGES_FOUND, quote=True)
            return

        # Check if the message is from a private chat
        is_private = message.chat.type == ChatType.PRIVATE

        if not is_private:
            # Generate the main caption for the media
            combined_caption = f"Всего изображений в датасете: {total_images}\n\n"

            # Try to get chat members for funny captions
            all_members = await get_chat_members(client, message.chat.id)

            for i, image_path in enumerate(image_paths, 1):
                group_info = get_image_owner_mapping(image_path)
                # Add funny caption only if we have members
                if all_members:
                    random_member = random.choice(all_members)
                    random_term = random.choice(RELATIONSHIP_TERMS)
                    verb_suffix = "пользователя" if any(
                        verb in random_term for verb in ACCUSATIVE_VERBS) else "пользователю"
                    user_name = random_member.user.first_name or random_member.user.username or "Пользователь"
                    combined_caption += f"Пикча №{i} - {random_term} {verb_suffix} {user_name} | Источник: {group_info}\n"
                else:
                    combined_caption += f"Пикча №{i} | Источник: {group_info}\n"

        else:
            # Simpler caption for private chats
            combined_caption = f"Всего изображений в датасете: {total_images}\n\n"
            for i, image_path in enumerate(image_paths, 1):
                group_info = get_image_owner_mapping(image_path)
                combined_caption += f"Пикча №{i} | Источник: {group_info}\n"

        # Create a media group; only the first image gets the caption
        media_group = [InputMediaPhoto(media=image_paths[0], caption=combined_caption)]
        media_group.extend(InputMediaPhoto(media=image_path) for image_path in image_paths[1:])

        # Send the media group with the caption only on the first image
        await message.reply_media_group(media=media_group, quote=True)
        await notification.delete()
        return

    except Exception as e:
        await message.reply_text(GENERAL_ERROR, quote=True)
        return
