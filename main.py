import os
from dotenv import load_dotenv
import discord
from discord.ext import commands
import random
import asyncio

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = 1325226119624130701

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

active_matches = {}
user_locks = {}

def get_user_lock(user_id: int) -> asyncio.Lock:
    if user_id not in user_locks:
        user_locks[user_id] = asyncio.Lock()
    return user_locks[user_id]

class BoxingMatch:
    def __init__(self, player: discord.Member):
        self.player = player
        self.player_hp = 100
        self.bot_hp = 100
        self.in_progress = True
        self.round = 1
        self.defending = False
        self.last_commentary = "Fight started! Choose your move below."
    
    def health_bar(self, current: int, total: int) -> str:
        bar_length = 20
        filled = int((current / total) * bar_length)
        return "█" * filled + "░" * (bar_length - filled)
    
    def to_embed(self) -> discord.Embed:
        embed = discord.Embed(title="🥊 Boxing Match 🥊", color=discord.Color.blue())
        embed.add_field(
            name=f"{self.player.display_name}",
            value=f"HP: {max(self.player_hp, 0)}/100\n{self.health_bar(self.player_hp, 100)}",
            inline=True
        )
        embed.add_field(
            name="Bot",
            value=f"HP: {max(self.bot_hp, 0)}/100\n{self.health_bar(self.bot_hp, 100)}",
            inline=True
        )
        embed.add_field(name="Round", value=str(self.round), inline=True)
        embed.description = self.last_commentary
        return embed
    
    def next_round(self):
        self.round += 1
        self.defending = False
    
    def player_attack(self, move: str):
        """
        Moves:
          - jab:      Very high accuracy, light damage (8–12)
          - cross:    High accuracy, moderate damage (10–16)
          - hook:     Moderate accuracy, higher damage (12–20)
          - uppercut: Lower accuracy, heavy damage (18–28)
        Returns a tuple: (move, damage, result) where result is "hit", "miss", or "invalid"
        """
        moves = {
            "jab": {"chance": 0.95, "min": 8, "max": 12},
            "cross": {"chance": 0.90, "min": 10, "max": 16},
            "hook": {"chance": 0.85, "min": 12, "max": 20},
            "uppercut": {"chance": 0.75, "min": 18, "max": 28}
        }
        if move not in moves:
            return (move, 0, "invalid")
        if random.random() > moves[move]["chance"]:
            return (move, 0, "miss")
        damage = random.randint(moves[move]["min"], moves[move]["max"])
        self.bot_hp -= damage
        return (move, damage, "hit")
    
    def player_defend(self):
        self.defending = True
        return "defend"
    
    def bot_turn(self):
        """
        Bot randomly attacks with: jab, cross, or hook.
        If the player defended, damage is halved.
        Returns a tuple: (move, damage, result)
        """
        moves = {
            "jab": {"chance": 0.95, "min": 8, "max": 12},
            "cross": {"chance": 0.90, "min": 10, "max": 16},
            "hook": {"chance": 0.85, "min": 12, "max": 20}
        }
        move = random.choice(list(moves.keys()))
        if random.random() > moves[move]["chance"]:
            return (move, 0, "miss")
        damage = random.randint(moves[move]["min"], moves[move]["max"])
        if self.defending:
            damage //= 2
        self.player_hp -= damage
        return (move, damage, "hit")

# ------------- Interactive Views -------------
class FightView(discord.ui.View):
    def __init__(self, match: BoxingMatch, lock: asyncio.Lock):
        super().__init__(timeout=None)
        self.match = match
        self.lock = lock
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.match.player.id:
            await interaction.response.send_message("This match isn’t yours!", ephemeral=True)
            return False
        return True
    
    async def update_message(self, interaction: discord.Interaction):
        embed = self.match.to_embed()
        # Swap to the post-match view if the match has ended.
        if not self.match.in_progress:
            view = PostMatchView(self.match, self.lock)
        else:
            view = self
        await interaction.response.edit_message(embed=embed, view=view)
    
    async def process_player_move(self, interaction: discord.Interaction, move: str):
        async with self.lock:
            if not self.match.in_progress:
                await interaction.response.send_message("The match has ended.", ephemeral=True)
                return
            commentary = ""
            if move in ["jab", "cross", "hook", "uppercut"]:
                move_name, dmg, result = self.match.player_attack(move)
                if result == "miss":
                    commentary = f"You attempted a **{move}** but missed!"
                elif result == "hit":
                    commentary = f"You landed a **{move}** for **{dmg}** damage!"
                else:
                    commentary = "Invalid move."
            elif move == "defend":
                self.match.player_defend()
                commentary = "You brace yourself and take a defensive stance."
            elif move == "forfeit":
                self.match.in_progress = False
                commentary = "You have forfeited the match. Better luck next time!"
                self.match.last_commentary = commentary
                await self.update_message(interaction)
                return
            if self.match.bot_hp <= 0:
                commentary += "\n\n🎉 You knocked out the bot! You win! 🎉"
                self.match.in_progress = False
                self.match.last_commentary = commentary
                self.match.next_round()
                await self.update_message(interaction)
                return
            # Bot’s turn.
            bot_move, bot_dmg, bot_result = self.match.bot_turn()
            if bot_result == "miss":
                commentary += f"\nThe bot tried a **{bot_move}** but missed!"
            elif bot_result == "hit":
                commentary += f"\nThe bot used **{bot_move}** and dealt **{bot_dmg}** damage to you!"
            if self.match.player_hp <= 0:
                commentary += "\n\n💥 You have been knocked out by the bot. You lose. 💥"
                self.match.in_progress = False
            self.match.last_commentary = commentary
            self.match.next_round()
        await self.update_message(interaction)
    
    @discord.ui.button(label="Jab", style=discord.ButtonStyle.primary, row=0)
    async def jab(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_player_move(interaction, "jab")
    
    @discord.ui.button(label="Cross", style=discord.ButtonStyle.primary, row=0)
    async def cross(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_player_move(interaction, "cross")
    
    @discord.ui.button(label="Hook", style=discord.ButtonStyle.primary, row=1)
    async def hook(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_player_move(interaction, "hook")
    
    @discord.ui.button(label="Uppercut", style=discord.ButtonStyle.primary, row=1)
    async def uppercut(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_player_move(interaction, "uppercut")
    
    @discord.ui.button(label="Defend", style=discord.ButtonStyle.secondary, row=2)
    async def defend(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_player_move(interaction, "defend")
    
    @discord.ui.button(label="Forfeit", style=discord.ButtonStyle.danger, row=2)
    async def forfeit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_player_move(interaction, "forfeit")

class PostMatchView(discord.ui.View):
    def __init__(self, match: BoxingMatch, lock: asyncio.Lock):
        super().__init__(timeout=None)
        self.match = match
        self.lock = lock
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.match.player.id:
            await interaction.response.send_message("This isn’t your match!", ephemeral=True)
            return False
        return True
    
    async def update_message(self, interaction: discord.Interaction, new_view: discord.ui.View):
        embed = self.match.to_embed()
        await interaction.response.edit_message(embed=embed, view=new_view)
    
    @discord.ui.button(label="Rematch", style=discord.ButtonStyle.success, row=0)
    async def rematch(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self.lock:
            new_match = BoxingMatch(self.match.player)
            active_matches[self.match.player.id] = new_match
            new_view = FightView(new_match, self.lock)
        await self.update_message(interaction, new_view)
    
    @discord.ui.button(label="Main Menu", style=discord.ButtonStyle.secondary, row=0)
    async def main_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Match over. Use /startfight to start a new match.", embed=self.match.to_embed(), view=None)

# ------------- Slash Commands -------------
@bot.tree.command(name="startfight", description="Begin a new boxing match against the bot!")
async def startfight(interaction: discord.Interaction):
    user = interaction.user
    lock = get_user_lock(user.id)
    async with lock:
        if user.id in active_matches and active_matches[user.id].in_progress:
            await interaction.response.send_message("You already have an active match! Use your current match buttons.", ephemeral=True)
            return
        match = BoxingMatch(interaction.user)
        active_matches[user.id] = match
        view = FightView(match, lock)
        embed = match.to_embed()
        await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="setactivity", description="Set the bot's activity status (Owner only)")
async def setactivity(interaction: discord.Interaction, status: str):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("You are not authorized to use this command.", ephemeral=True)
        return
    await bot.change_presence(activity=discord.Game(name=status))
    await interaction.response.send_message(f"Activity status updated to: {status}", ephemeral=True)

@bot.tree.command(name="listservers", description="List all servers the bot is in (Owner only)")
async def listservers(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("You are not authorized to use this command.", ephemeral=True)
        return
    guild_list = "\n".join([f"{guild.name} (ID: {guild.id})" for guild in bot.guilds])
    if not guild_list:
        guild_list = "The bot is not in any servers."
    embed = discord.Embed(title="Server List", description=guild_list, color=discord.Color.green())
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    try:
        await interaction.response.send_message(f"An error occurred: {error}", ephemeral=True)
    except Exception:
        pass

@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"Failed to sync commands: {e}")
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")

bot.run(BOT_TOKEN)
