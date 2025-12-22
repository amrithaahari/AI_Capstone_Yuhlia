import asyncio
from openai import AsyncOpenAI

async def check():
    client = AsyncOpenAI()

    completions = await client.chat.completions.list(limit=5)

    assert completions.data, (
        "No chat completions found. "
        "Enable logging in the OpenAI dashboard → Admin → Logs."
    )

    print("✅ Chat completion logs found.")

if __name__ == "__main__":
    asyncio.run(check())
