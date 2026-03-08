import discord
from discord.ext import commands
import sqlite3
import database

class Warnings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def is_staff(self, ctx, staff_roles_str):
        if not staff_roles_str:
            return ctx.author.guild_permissions.administrator
        
        staff_roles_ids = [int(r_id.strip()) for r_id in staff_roles_str.split(',') if r_id.strip().isdigit()]
        author_role_ids = [r.id for r in ctx.author.roles]
        
        for r_id in staff_roles_ids:
            if r_id in author_role_ids:
                return True
        return ctx.author.guild_permissions.administrator

    @commands.command(name="set_warn_system")
    @commands.has_permissions(administrator=True)
    async def set_warn_system(self, ctx):
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        await ctx.send("🛡️ **Paso 1/2:** Menciona los roles (o envía sus IDs separados por espacios) que están autorizados para poner advertencias.")
        try:
            msg = await self.bot.wait_for('message', timeout=120.0, check=check)
            roles_found = []
            if msg.role_mentions:
                roles_found = [str(r.id) for r in msg.role_mentions]
            else:
                roles_found = [part for part in msg.content.split() if part.isdigit()]
            
            staff_roles_str = ",".join(roles_found)
        except TimeoutError:
            return await ctx.send("⌛ Tiempo agotado.")

        await ctx.send("📢 **Paso 2/2:** ¿En qué canal se deben publicar los anuncios de logs (Advertencias y Resets)? (Menciona con #)")
        try:
            msg = await self.bot.wait_for('message', timeout=120.0, check=check)
            if not msg.channel_mentions:
                return await ctx.send("❌ No mencionaste ningún canal válido. Configuración cancelada.")
            log_channel_id = msg.channel_mentions[0].id
        except TimeoutError:
            return await ctx.send("⌛ Tiempo agotado.")

        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT guild_id FROM warn_settings WHERE guild_id = ?", (ctx.guild.id,))
        if cursor.fetchone():
            cursor.execute('''
                UPDATE warn_settings 
                SET log_channel_id=?, staff_roles=?
                WHERE guild_id=?
            ''', (log_channel_id, staff_roles_str, ctx.guild.id))
        else:
            cursor.execute('''
                INSERT INTO warn_settings (guild_id, log_channel_id, staff_roles)
                VALUES (?, ?, ?)
            ''', (ctx.guild.id, log_channel_id, staff_roles_str))
        conn.commit()
        conn.close()

        await ctx.send("✅ Sistema de advertencias configurado correctamente.")

    @commands.command(name="warn")
    async def warn(self, ctx, member: discord.Member, points: float, *, reason: str):
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT log_channel_id, staff_roles FROM warn_settings WHERE guild_id = ?", (ctx.guild.id,))
        settings = cursor.fetchone()
        
        if not settings:
            conn.close()
            return await ctx.send("El sistema de advertencias no está configurado.")
            
        log_channel_id, staff_roles_str = settings
        
        if not self.is_staff(ctx, staff_roles_str):
            conn.close()
            return await ctx.send("❌ No tienes permisos para usar este comando.")

        # Inserción de la advertencia
        cursor.execute('''
            INSERT INTO warnings (guild_id, user_id, points, reason)
            VALUES (?, ?, ?, ?)
        ''', (ctx.guild.id, member.id, points, reason))
        
        # Calcular total de puntos
        cursor.execute('SELECT SUM(points) FROM warnings WHERE guild_id=? AND user_id=?', (ctx.guild.id, member.id))
        total_points = cursor.fetchone()[0] or 0.0
        conn.commit()
        conn.close()

        # Auto-delete the command message to keep it hidden
        try:
            await ctx.message.delete()
        except:
            pass
            
        # Enviar Log Embed
        log_channel = self.bot.get_channel(log_channel_id)
        embed = discord.Embed(title="⚠️ Nueva Advertencia", color=discord.Color.orange())
        embed.add_field(name="Usuario", value=member.mention, inline=False)
        embed.add_field(name="Puntos Agregados", value=f"{points}", inline=True)
        embed.add_field(name="Total Acumulado", value=f"{total_points}/5.0", inline=True)
        embed.add_field(name="Motivo", value=reason, inline=False)
        embed.set_footer(text=f"Sancionado por: {ctx.author.name} desde #{ctx.channel.name}")

        if log_channel:
            await log_channel.send(content=f"✅ Advertencia aplicada a {member.mention} ({total_points} puntos).", embed=embed)
        else:
            await ctx.send(f"✅ Advertencia aplicada a {member.mention} ({total_points} puntos), pero el canal de logs no fue encontrado.", delete_after=5)

        # Auto-Kick
        if total_points >= 5.0:
            try:
                await member.send(f"Has sido expulsado de {ctx.guild.name} por acumular {total_points}/5.0 puntos de advertencia.")
            except:
                pass # Puede tener DMs cerrados
                
            try:
                await member.kick(reason=f"Acumuló {total_points} puntos de advertencia.")
                kick_embed = discord.Embed(title="👢 Usuario Expulsado", description=f"{member.mention} fue expulsado automáticamente por alcanzar el límite de advertencias (5.0 pts).", color=discord.Color.red())
                if log_channel:
                    await log_channel.send(embed=kick_embed)
            except Exception as e:
                await ctx.send(f"❌ Error al expulsar a {member.name}. Posiblemente me falten permisos. Error: {e}")

    @commands.command(name="puntos")
    async def puntos(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT SUM(points) FROM warnings WHERE guild_id=? AND user_id=?', (ctx.guild.id, member.id))
        total_points = cursor.fetchone()[0] or 0.0
        
        cursor.execute('SELECT points, reason FROM warnings WHERE guild_id=? AND user_id=?', (ctx.guild.id, member.id))
        history = cursor.fetchall()
        conn.close()

        embed = discord.Embed(title=f"Puntos de {member.display_name}", color=discord.Color.blue())
        embed.description = f"**Total Acumulado:** {total_points}/5.0 pts"
        
        if history:
            historial_texto = ""
            for pts, rsn in history:
                historial_texto += f"• **+{pts}**: {rsn}\n"
            embed.add_field(name="Historial", value=historial_texto, inline=False)
            
        await ctx.send(embed=embed)

    @commands.command(name="reset_periodo")
    @commands.has_permissions(administrator=True)
    async def reset_periodo(self, ctx):
        conn = database.get_connection()
        cursor = conn.cursor()
        
        # Eliminar las advertencias
        cursor.execute('DELETE FROM warnings WHERE guild_id=?', (ctx.guild.id,))
        conn.commit()
        
        # Buscar log channel
        cursor.execute("SELECT log_channel_id FROM warn_settings WHERE guild_id = ?", (ctx.guild.id,))
        settings = cursor.fetchone()
        conn.close()

        embed = discord.Embed(title="🔄 Nuevo Periodo Iniciado", description="Se han puesto a 0 todos los puntos de advertencia del servidor.", color=discord.Color.green())
        embed.set_footer(text=f"Reset realizado por {ctx.author.name}")

        if settings:
            log_channel = self.bot.get_channel(settings[0])
            if log_channel:
                await log_channel.send(embed=embed)
                return await ctx.send("✅ Periodo reiniciado. Revisa los logs.")
                
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Warnings(bot))
