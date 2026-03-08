import discord
from discord.ext import commands, tasks
import sqlite3
import database
import datetime
from zoneinfo import ZoneInfo

class ActivityRSVP(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Estoy conectado y pude unirme", style=discord.ButtonStyle.success, custom_id="rsvp_yes")
    async def btn_yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("✅ ¡Genial! Has confirmado tu asistencia a la actividad.", ephemeral=True)

    @discord.ui.button(label="No estoy en el juego no pude unirme", style=discord.ButtonStyle.danger, custom_id="rsvp_no")
    async def btn_no(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("❌ Entendido. Se ha registrado tu ausencia.", ephemeral=True)

class Activities(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.add_view(ActivityRSVP()) # Persistent view registration
        self.activity_loop.start()

    def cog_unload(self):
        self.activity_loop.cancel()

    @commands.command(name="set_recordatorio_actividad")
    @commands.has_permissions(administrator=True)
    async def set_recordatorio_actividad(self, ctx):
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        # 1. Channel
        await ctx.send("📅 **Paso 1/6:** Menciona el canal donde se enviará el anuncio de la actividad (ej: `#anuncios`).")
        try:
            msg = await self.bot.wait_for('message', timeout=60.0, check=check)
            if not msg.channel_mentions:
                return await ctx.send("❌ No mencionaste ningún canal válido. Configuración cancelada.")
            channel_id = msg.channel_mentions[0].id
        except TimeoutError:
            return await ctx.send("⌛ Tiempo agotado.")

        # 2. Name
        await ctx.send("📅 **Paso 2/6:** ¿Cuál es el nombre de la actividad? (Ej: `Reparación en carretera`)")
        try:
            msg = await self.bot.wait_for('message', timeout=120.0, check=check)
            name = msg.content
        except TimeoutError:
            return await ctx.send("⌛ Tiempo agotado.")

        # 3. Description
        await ctx.send("📅 **Paso 3/6:** Escribe la descripción de la actividad (las instrucciones o detalles).")
        try:
            msg = await self.bot.wait_for('message', timeout=300.0, check=check)
            description = msg.content
        except TimeoutError:
            return await ctx.send("⌛ Tiempo agotado.")

        # 4. Time
        await ctx.send("📅 **Paso 4/6:** ¿A qué hora del servidor (Ouagadougou) se debe anunciar? Escríbelo en formato HH:MM (Ej: `04:00`, `16:30`).")
        try:
            msg = await self.bot.wait_for('message', timeout=120.0, check=check)
            action_time = msg.content.strip()
            if len(action_time) != 5 or ":" not in action_time:
                return await ctx.send("❌ Formato de hora inválido. Debes usar el formato HH:MM (ej: 04:00). Configuración cancelada.")
        except TimeoutError:
            return await ctx.send("⌛ Tiempo agotado.")

        # 5. Days
        await ctx.send("📅 **Paso 5/6:** ¿Qué días de la semana aplica? (Escribe `Todos` o los días separados por coma, ej: `Lunes,Miercoles,Viernes`).")
        try:
            msg = await self.bot.wait_for('message', timeout=120.0, check=check)
            days = msg.content.title()
        except TimeoutError:
            return await ctx.send("⌛ Tiempo agotado.")

        # 6. Banner
        await ctx.send("📅 **Paso 6/6:** Sube una imagen adjunta para el banner de la actividad (o pega una URL). Si no quieres imagen, escribe `Ninguno`.")
        try:
            msg = await self.bot.wait_for('message', timeout=120.0, check=check)
            if msg.attachments:
                banner_url = msg.attachments[0].url
            else:
                banner_url = msg.content.strip()
                if banner_url.lower() == "ninguno":
                    banner_url = ""
                elif not banner_url.startswith("http"):
                    await ctx.send("⚠️ No se detectó imagen ni URL válida. Se creará sin banner.")
                    banner_url = ""
        except TimeoutError:
            return await ctx.send("⌛ Tiempo agotado.")

        # Guardar en SQLite
        try:
            conn = database.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO activities (guild_id, channel_id, name, description, action_time, days, banner_url)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (ctx.guild.id, channel_id, name, description, action_time, days, banner_url))
            conn.commit()
            conn.close()
            await ctx.send(f"✅ ¡Éxito! La actividad **'{name}'** ha sido programada para anunciarse a las **{action_time}** (Huso horario de Ouagadougou).")
        except Exception as e:
            await ctx.send(f"❌ Error interno al guardar la actividad: {e}")

    @tasks.loop(minutes=1.0)
    async def activity_loop(self):
        await self.bot.wait_until_ready()
        
        # Obtener la hora actual exacta en Ouagadougou (GMT/UTC+0)
        try:
            tz = ZoneInfo("Africa/Ouagadougou")
        except:
            # Fallback a UTC genérico si falla la base de datos de zona horaria del OS
            tz = datetime.timezone.utc 
            
        now = datetime.datetime.now(tz)
        current_time_str = now.strftime("%H:%M")
        
        dias_semana_es = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]
        current_day_str = dias_semana_es[now.weekday()]

        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, guild_id, channel_id, name, description, days, banner_url FROM activities WHERE action_time = ?", (current_time_str,))
        activities = cursor.fetchall()
        conn.close()

        for act in activities:
            act_id, guild_id, channel_id, name, description, days, banner_url = act
            
            # Verificar si el día de hoy coincide (ignorando tildes y mayúsculas si es posible)
            if days.lower() != "todos":
                # Limpiamos acentos comunes por si el usuario los puso
                dia_seguro = current_day_str.lower()
                dias_bd = days.lower().replace("é", "e").replace("á", "a")
                if dia_seguro.replace("é", "e") not in dias_bd:
                    continue
                
            guild = self.bot.get_guild(guild_id)
            if not guild: continue
            channel = guild.get_channel(channel_id)
            if not channel: continue

            # Construcción del Embed fiel a la imagen solicitada
            embed = discord.Embed(title=f"🛠️ Actividad disponible: {name}", color=0x1a1a1a) # Dark background feel
            embed.add_field(name="📌 Empresa", value="Faccion / Organización", inline=False)
            embed.add_field(name="🕒 Horario (server)", value=f"{current_time_str}-Activo", inline=False)
            embed.add_field(name="⭐ Puntos diarios", value="Automático", inline=False)
            
            # Descripción inmersiva
            embed.description = f"```\n{description}\n```\n"
            
            # Timestamps / Datos en vivo
            fecha_hoy = now.strftime("%d/%m/%Y")
            embed.description += f"⏳ **Tiempo restante:** (Actividad en progreso)\n"
            embed.description += f"📅 **Ahora (server):** {current_time_str} {fecha_hoy}\n"
            
            if banner_url and banner_url.startswith("http"):
                embed.set_image(url=banner_url)
                
            embed.set_footer(text="Actividades GTAHub")

            try:
                await channel.send(embed=embed, view=ActivityRSVP())
            except Exception as e:
                print(f"Error enviando el recordatorio de actividad '{name}': {e}")

async def setup(bot):
    await bot.add_cog(Activities(bot))
