import discord
from discord.ext import commands
import sqlite3
import database
import io
import datetime

class TicketPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Postulación", style=discord.ButtonStyle.danger, custom_id="ticket_postulacion")
    async def postulacion_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await handle_ticket_creation(interaction, "postulacion")

    @discord.ui.button(label="Reportar Miembro", style=discord.ButtonStyle.danger, custom_id="ticket_reporte")
    async def reporte_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await handle_ticket_creation(interaction, "reporte")

class TicketControl(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Reclamar", style=discord.ButtonStyle.primary, custom_id="ticket_reclamar")
    async def reclamar_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Announce staff and disable button
        button.disabled = True
        button.label = "Reclamado"
        await interaction.response.edit_message(view=self)
        await interaction.channel.send(f"🛡️ **Ticket Reclamado** por {interaction.user.mention}. ¡En breve te atenderá!")

    @discord.ui.button(label="Cerrar", style=discord.ButtonStyle.danger, custom_id="ticket_cerrar")
    async def cerrar_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Cerrando ticket en 5 segundos y generando transcript...", ephemeral=False)
        
        # Generate Transcript
        transcript = ""
        async for message in interaction.channel.history(limit=None, oldest_first=True):
            time_str = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
            transcript += f"[{time_str}] {message.author.name}: {message.content}\n"
            if message.attachments:
                for a in message.attachments:
                    transcript += f"  - [Adjunto]: {a.url}\n"
        
        transcript_file = discord.File(io.StringIO(transcript), filename=f"transcript_{interaction.channel.name}.txt")
        
        # In a real scenario, you'd send this to a log channel or the user themselves.
        # Sending to the user if possible:
        try:
            # We must fetch the user to DM them. For now, we will just send it to the interaction user (staff)
            await interaction.user.send(f"Transcript del ticket `{interaction.channel.name}`:", file=transcript_file)
        except:
            pass
            
        # Delete channel after short delay
        import asyncio
        await asyncio.sleep(5)
        await interaction.channel.delete()

async def handle_ticket_creation(interaction: discord.Interaction, ticket_type: str):
    guild = interaction.guild
    user = interaction.user
    
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT staff_roles, form_postulacion, form_reporte FROM ticket_settings WHERE guild_id = ?", (guild.id,))
    result = cursor.fetchone()
    conn.close()

    if not result:
        return await interaction.response.send_message("El sistema de tickets no está configurado.", ephemeral=True)

    staff_roles_str, form_postulacion, form_reporte = result
    
    # Parse staff roles, robust handling
    staff_roles = []
    if staff_roles_str:
        for r_id in staff_roles_str.split(','):
            try:
                role = guild.get_role(int(r_id.strip()))
                if role:
                    staff_roles.append(role)
            except ValueError:
                pass

    channel_name = f"ticket-{user.name.lower().replace(' ', '-')}"
    
    # Setup permissions
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        user: discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True)
    }
    
    for role in staff_roles:
        overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True)
        
    # Create channel
    try:
        category = interaction.channel.category  # Try to put it in the same category as the panel
        ticket_channel = await guild.create_text_channel(name=channel_name, overwrites=overwrites, category=category)
    except Exception as e:
        return await interaction.response.send_message(f"Error creando el ticket: {e}", ephemeral=True)

    await interaction.response.send_message(f"✅ Tu ticket ha sido creado en {ticket_channel.mention}", ephemeral=True)

    # Send Welcome Form
    form_text = form_postulacion if ticket_type == "postulacion" else form_reporte
    
    embed_form = discord.Embed(
        title=f"Ticket de {'Postulación' if ticket_type == 'postulacion' else 'Reporte'}",
        description=f"Hola {user.mention}, responde a las siguientes preguntas:\n\n{form_text}",
        color=discord.Color.red()
    )
    await ticket_channel.send(content=f"{user.mention}", embed=embed_form)
    
    # Send Staff Control Panel
    embed_ctrl = discord.Embed(
        title="Panel de Control Staff",
        description="Utiliza estos botones para gestionar el ticket.",
        color=discord.Color.dark_gray()
    )
    
    # Mentions string for staff pings
    staff_mentions = " ".join([r.mention for r in staff_roles]) if staff_roles else ""
    await ticket_channel.send(content=staff_mentions, embed=embed_ctrl, view=TicketControl())


class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.add_view(TicketPanel()) # Persistent View
        self.bot.add_view(TicketControl()) # Persistent View

    @commands.command(name="set_ticket_system")
    @commands.has_permissions(administrator=True)
    async def set_ticket_system(self, ctx):
        # We use a separate command to avoid conflict with welcome's 'set' group in this simplified structure
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        # 1. Aesthetics
        await ctx.send("🎨 **Paso 1/4:** Sube la imagen del Banner principal del Panel de Tickets **adjuntándola** en tu mensaje. (O pega una URL).")
        try:
            msg = await self.bot.wait_for('message', timeout=120.0, check=check)
            if msg.attachments:
                banner_url = msg.attachments[0].url
            else:
                banner_url = msg.content.strip()
                if not banner_url.startswith("http") and banner_url.lower() != "ninguno":
                    await ctx.send("❌ No proporcionaste una imagen. Se creará sin banner.")
                    banner_url = ""
        except TimeoutError:
            return await ctx.send("⌛ Tiempo agotado.")

        await ctx.send("🎨 **Paso 2/4:** Escribe el Título que tendrá el Embed del sistema de tickets (Ej: Soporte).")
        try:
            msg = await self.bot.wait_for('message', timeout=120.0, check=check)
            panel_title = msg.content
        except TimeoutError:
            return await ctx.send("⌛ Tiempo agotado.")
            
        await ctx.send("🎨 **Paso 3/4:** Escribe la Descripción del Embed.")
        try:
            msg = await self.bot.wait_for('message', timeout=300.0, check=check)
            panel_desc = msg.content
        except TimeoutError:
            return await ctx.send("⌛ Tiempo agotado.")

        # 2. Staff Roles
        await ctx.send("🛡️ **Paso 4/6:** Menciona los roles (o envía sus IDs separados por espacios) que serán Staff (podrán ver/reclamar los tickets).")
        try:
            msg = await self.bot.wait_for('message', timeout=300.0, check=check)
            roles_found = []
            if msg.role_mentions:
                roles_found = [str(r.id) for r in msg.role_mentions]
            else:
                roles_found = [part for part in msg.content.split() if part.isdigit()]
            
            staff_roles_str = ",".join(roles_found)
        except TimeoutError:
            return await ctx.send("⌛ Tiempo agotado.")

        # 3. Forms
        await ctx.send("📝 **Paso 5/6:** ¿Qué preguntas quieres para el ticket de **Postulación**? Escríbelas todas en un solo mensaje.")
        try:
            msg = await self.bot.wait_for('message', timeout=600.0, check=check)
            form_postulacion = msg.content
        except TimeoutError:
            return await ctx.send("⌛ Tiempo agotado.")

        await ctx.send("📝 **Paso 6/6:** ¿Qué preguntas quieres para el ticket de **Reportar Miembro**? Escríbelas todas en un solo mensaje.")
        try:
            msg = await self.bot.wait_for('message', timeout=600.0, check=check)
            form_reporte = msg.content
        except TimeoutError:
            return await ctx.send("⌛ Tiempo agotado.")

        # Save to DB
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT guild_id FROM ticket_settings WHERE guild_id = ?", (ctx.guild.id,))
        if cursor.fetchone():
            cursor.execute('''
                UPDATE ticket_settings 
                SET banner_url=?, title=?, description=?, staff_roles=?, form_postulacion=?, form_reporte=?
                WHERE guild_id=?
            ''', (banner_url, panel_title, panel_desc, staff_roles_str, form_postulacion, form_reporte, ctx.guild.id))
        else:
            cursor.execute('''
                INSERT INTO ticket_settings (guild_id, banner_url, title, description, staff_roles, form_postulacion, form_reporte)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (ctx.guild.id, banner_url, panel_title, panel_desc, staff_roles_str, form_postulacion, form_reporte))
        conn.commit()
        conn.close()

        # Generar el panel
        embed = discord.Embed(title=panel_title, description=panel_desc, color=discord.Color.red())
        if banner_url.startswith("http"):
            embed.set_image(url=banner_url)
            
        await ctx.channel.send(embed=embed, view=TicketPanel())
        await ctx.send("✅ Panel de tickets creado y configuración persistida correctamente.")

async def setup(bot):
    await bot.add_cog(Tickets(bot))
