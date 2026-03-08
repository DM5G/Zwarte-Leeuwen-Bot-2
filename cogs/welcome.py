import discord
from discord.ext import commands
import sqlite3
import database
import io
import aiohttp
from PIL import Image, ImageDraw, ImageFont, ImageOps

class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="set_welcome")
    @commands.has_permissions(administrator=True)
    async def set_welcome(self, ctx, system: str = None):
        """
        Comando interactivo para configurar el sistema de bienvenida.
        Uso: !set_welcome system
        """
        if system != "system":
            return await ctx.send("Sintaxis incorrecta. Usa: `!set_welcome system`")

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        # 1. Ask for channel
        await ctx.send("🔧 **Paso 1/3:** ¿En qué canal se enviarán las bienvenidas? (Menciona el canal con #)")
        try:
            msg = await self.bot.wait_for('message', timeout=60.0, check=check)
            if not msg.channel_mentions:
                return await ctx.send("❌ No mencionaste ningún canal válido. Configuración cancelada. (Asegúrate de poner el # y hacer clic en el canal de la lista).")
            channel_id = msg.channel_mentions[0].id
        except TimeoutError:
            return await ctx.send("⌛ Tiempo agotado para el Paso 1. Configuración cancelada.")

        # 2. Ask for banner URL / Attachment
        await ctx.send("🖼️ **Paso 2/3:** Sube la imagen de fondo (Banner) **adjuntándola** en tu próximo mensaje. (Si prefieres, también puedes pegar una URL válida que empiece por http).")
        try:
            msg = await self.bot.wait_for('message', timeout=120.0, check=check)
            if msg.attachments:
                banner_url = msg.attachments[0].url
            else:
                banner_url = msg.content.strip()
                if not banner_url.startswith("http"):
                    return await ctx.send("❌ No se adjuntó ninguna imagen ni es una URL válida. Configuración cancelada.")
        except TimeoutError:
            return await ctx.send("⌛ Tiempo agotado para el Paso 2. Configuración cancelada.")

        # 3. Ask for welcome message
        await ctx.send("📝 **Paso 3/3:** Escribe el mensaje de bienvenida. Puedes usar `@usuario` para mencionar al nuevo miembro.")
        try:
            msg = await self.bot.wait_for('message', timeout=300.0, check=check)
            welcome_message = msg.content
        except TimeoutError:
            return await ctx.send("⌛ Tiempo agotado para el Paso 3. Configuración cancelada.")

        # Save to database
        try:
            conn = database.get_connection()
            cursor = conn.cursor()
            
            # Check if settings exist for this guild
            cursor.execute("SELECT guild_id FROM welcome_settings WHERE guild_id = ?", (ctx.guild.id,))
            exists = cursor.fetchone()
            
            if exists:
                cursor.execute('''
                    UPDATE welcome_settings 
                    SET channel_id = ?, banner_url = ?, message = ?
                    WHERE guild_id = ?
                ''', (channel_id, banner_url, welcome_message, ctx.guild.id))
            else:
                cursor.execute('''
                    INSERT INTO welcome_settings (guild_id, channel_id, banner_url, message)
                    VALUES (?, ?, ?, ?)
                ''', (ctx.guild.id, channel_id, banner_url, welcome_message))
                
            conn.commit()
            conn.close()
            await ctx.send("✅ ¡Sistema de bienvenida configurado correctamente!")
            
        except sqlite3.Error as e:
            await ctx.send(f"❌ Ocurrió un error al guardar en la base de datos: {e}")


    async def create_welcome_card(self, avatar_url, banner_url, username):
        """Generates the welcome image using Pillow."""
        try:
            async with aiohttp.ClientSession() as session:
                # Load Banner
                async with session.get(banner_url) as resp:
                    if resp.status != 200:
                        return None
                    banner_data = await resp.read()
                    banner = Image.open(io.BytesIO(banner_data)).convert("RGBA")
                
                # Load Avatar
                async with session.get(avatar_url) as resp:
                    if resp.status != 200:
                        return None
                    avatar_data = await resp.read()
                    avatar = Image.open(io.BytesIO(avatar_data)).convert("RGBA")

            # Resize avatar and create circular mask
            avatar = avatar.resize((200, 200))
            mask = Image.new("L", avatar.size, 0)
            draw = ImageDraw.Draw(mask)
            draw.ellipse((0, 0) + avatar.size, fill=255)
            
            # Apply mask to avatar
            circular_avatar = ImageOps.fit(avatar, mask.size, centering=(0.5, 0.5))
            circular_avatar.putalpha(mask)

            # Paste avatar center horizontally, somewhat top vertically
            banner_w, banner_h = banner.size
            avatar_w, avatar_h = circular_avatar.size
            offset = ((banner_w - avatar_w) // 2, (banner_h - avatar_h) // 2 - 30)
            
            banner.paste(circular_avatar, offset, circular_avatar)

            # Draw username
            draw = ImageDraw.Draw(banner)
            try:
                # Try to load a generic font, or use default if not available
                font = ImageFont.truetype("arial.ttf", 45)
            except IOError:
                font = ImageFont.load_default()

            # Using textbbox to center text
            bbox = draw.textbbox((0, 0), username, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            text_x = (banner_w - text_w) / 2
            text_y = offset[1] + avatar_h + 20

            draw.text((text_x, text_y), username, font=font, fill=(255, 255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))

            output = io.BytesIO()
            # Convert to RGB to save as PNG properly without issues if banner didn't have alpha
            if banner.mode == 'RGBA':
                banner = banner.convert('RGB')
            banner.save(output, format="PNG")
            output.seek(0)
            return output
            
        except Exception as e:
            print(f"Error generating welcome card: {e}")
            return None

    @commands.Cog.listener()
    async def on_member_join(self, member):
        guild_id = member.guild.id
        
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT channel_id, banner_url, message FROM welcome_settings WHERE guild_id = ?", (guild_id,))
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            return  # System not configured for this guild

        channel_id, banner_url, message_template = result
        channel = self.bot.get_channel(channel_id)
        
        if not channel:
            return
            
        formatted_message = message_template.replace("@usuario", member.mention)

        avatar_url = member.avatar.url if member.avatar else member.default_avatar.url
        
        # Generar imagen
        image_stream = await self.create_welcome_card(str(avatar_url), banner_url, member.name)
        
        if image_stream:
            file = discord.File(fp=image_stream, filename="welcome.png")
            await channel.send(content=formatted_message, file=file)
        else:
            # Fallback if image generation fails
            await channel.send(content=formatted_message)

async def setup(bot):
    await bot.add_cog(Welcome(bot))
