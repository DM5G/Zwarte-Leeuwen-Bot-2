import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import database

# Cargar variables de entorno (útil para desarrollo local, en Railway usar variables de entorno)
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

class GTAHubBot(commands.Bot):
    def __init__(self):
        # Configurar intents para poder leer mensajes y ver miembros (necesario para bienvenida)
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True 
        
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Inicializar la base de datos
        database.init_db()
        
        # Cargar los cogs (módulos) automáticamente
        cogs_dir = "cogs"
        if os.path.exists(cogs_dir):
            for filename in os.listdir(cogs_dir):
                if filename.endswith(".py") and not filename.startswith("__"):
                    await self.load_extension(f"{cogs_dir}.{filename[:-3]}")
                    print(f"Módulo cargado: {filename}")
        
        # Sincronizar slash commands si se utilizan
        await self.tree.sync()
        print("Slash commands sincronizados.")

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Falta un argumento requerido: `{error.param.name}`. Revisa la sintaxis del comando.")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("❌ Uno de los argumentos no es válido (por ejemplo, pusiste letras en vez de números).")
        elif isinstance(error, commands.CommandNotFound):
            pass  # Ignorar si el comando no existe
        else:
            await ctx.send(f"❌ Ocurrió un error al ejecutar el comando: {str(error)}")

    async def on_ready(self):
        print(f'Bot conectado exitosamente como {self.user} (ID: {self.user.id})')
        print('------')

bot = GTAHubBot()

if __name__ == '__main__':
    if not TOKEN:
        print("ADVERTENCIA: La variable de entorno DISCORD_TOKEN no está configurada.")
    else:
        bot.run(TOKEN)
