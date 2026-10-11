import discord


async def fetch_stored_file(client: discord.Client, storage_ref: str) -> discord.File:
    """storage_ref format: 'discord:CHANNEL_ID:MESSAGE_ID'"""
    kind, channel_id, message_id = storage_ref.split(":")
    if kind != "discord":
        raise ValueError(f"Unsupported storage type: {kind}")

    channel = client.get_channel(int(channel_id)) or await client.fetch_channel(int(channel_id))
    message = await channel.fetch_message(int(message_id))
    if not message.attachments:
        raise FileNotFoundError("Archive message has no attachment")
    return await message.attachments[0].to_file()

async def delete_stored_file(client: discord.Client, storage_ref: str) -> None:
    try:
        kind, channel_id, message_id = storage_ref.split(":")
        if kind != "discord":
            return
        channel = client.get_channel(int(channel_id)) or await client.fetch_channel(int(channel_id))
        message = await channel.fetch_message(int(message_id))
        await message.delete()
    except (ValueError, discord.HTTPException):
        pass