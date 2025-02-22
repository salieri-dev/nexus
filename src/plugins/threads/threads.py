import os
from pyrogram import Client, filters
from pyrogram.types import Message

from src.services.openrouter import OpenRouter
from structlog import get_logger

log = get_logger(__name__)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

@Client.on_message(filters.command(["bugurt"]), group=1)
async def create_bugurt(client: Client, message: Message):
    input_prompt = " ".join(message.command[1:])
    open_router = OpenRouter().client
    
    with open(os.path.join(CURRENT_DIR, "bugurt", "bugurt_system_prompt.txt"), "r") as file:
        system_prompt = file.read()
    
    completion = await open_router.chat.completions.create(
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": input_prompt
            }
        ],
        model="google/gemini-2.0-flash-thinking-exp:free", temperature=0.7, max_completion_tokens=65536, top_p=0.95, extra_body={"include_reasoning": True}
    )
    
    completion_response = completion.choices[0].message.content
    log.info(f"AI Response: {completion_response}")
    
    # Generate image from the JSON response
    from src.plugins.threads.service import generate_bugurt_image
    
    image_bytes = generate_bugurt_image(completion_response)
    if not image_bytes:
        await message.reply("Failed to generate bugurt image")
        return
        
    # Send the image
    from io import BytesIO
    
    # Convert bytes to BytesIO object
    photo = BytesIO(image_bytes)
    photo.name = "bugurt.png"
    await message.reply_photo(
        photo=photo,
        caption=input_prompt
    )

@Client.on_message(filters.command(["greentext"]), group=1)
async def create_greentext(client: Client, message: Message):
    input_prompt = " ".join(message.command[1:])
    open_router = OpenRouter().client
    
    with open(os.path.join(CURRENT_DIR, "greentext", "greentext_system_prompt.txt"), "r") as file:
        system_prompt = file.read()
    
    completion = await open_router.chat.completions.create(
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": input_prompt
            }
        ],
        model="google/gemini-2.0-flash-thinking-exp:free", temperature=0.7, max_completion_tokens=65536, top_p=0.95, extra_body={"include_reasoning": True}
    )
    
    completion_response = completion.choices[0].message.content
    log.info(f"AI Response: {completion_response}")
    
    # Generate image from the JSON response
    from src.plugins.threads.service import generate_greentext_image
    
    # Use the same image generator but with greentext template
    image_bytes = generate_greentext_image(completion_response)
    if not image_bytes:
        await message.reply("Failed to generate greentext image")
        return
        
    # Send the image
    from io import BytesIO
    
    # Convert bytes to BytesIO object
    photo = BytesIO(image_bytes)
    photo.name = "greentext.png"
    
    await message.reply_photo(
        photo=photo,
        caption=input_prompt
    )