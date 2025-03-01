import os
import time
from dotenv import load_dotenv
import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = os.getenv("OWNER_ID")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

def owner_only(interaction: discord.Interaction) -> bool:
    if interaction.user.id != int(OWNER_ID):
        raise app_commands.CheckFailure("You are not authorized to use this command.")
    return True

active_matches = {}
user_locks = {}

def get_user_lock(user_id: int) -> asyncio.Lock:
    if user_id not in user_locks:
        user_locks[user_id] = asyncio.Lock()
    return user_locks[user_id]

hit_gifs = {
    "jab": "https://media1.tenor.com/m/7YiJgl16vigAAAAC/punch-cassius-clay.gif",
    "cross": "https://media1.tenor.com/m/KA2erOTiKcMAAAAC/punch-in-the-face-edgar-muñoz.gif",
    "hook": "https://media1.tenor.com/m/N__KdnoDH_MAAAAC/boxing-punch.gif",
    "uppercut": "https://media1.tenor.com/m/WZI35DJcOucAAAAC/mike-tyson-punch.giff",
    "defend": "https://media1.tenor.com/m/5ZY9yE_FFlUAAAAd/mike-tyson-james-tillis.gif"
}
miss_gifs = {
    "jab": "https://media1.tenor.com/m/YO-2u32heZYAAAAC/slipping-benjamin-whittaker.gif",
    "cross": "https://media1.tenor.com/m/a9-3ocvdwjAAAAAC/パンチ-エド.gif",
    "hook": "https://media1.tenor.com/m/Ag5myWTszjoAAAAd/swing-and.gif",
    "uppercut": "https://media1.tenor.com/m/ZszlyGrlmpQAAAAC/damn-punch.gif"
}
bot_hit_gifs = {
    "jab": "https://images.squarespace-cdn.com/content/v1/5d3d604f1c3c2e00014fe64d/1570224117948-MWORCUGRKYVOABVA98G7/JAB.gif",
    "cross": "https://media1.tenor.com/m/cfI7VFBogNQAAAAd/keyshawn-davis.gif",
    "hook": "https://media1.tenor.com/m/DOQxgMdB1AQAAAAd/punching-anthony-joshua.gif"
}
bot_miss_gifs = {
    "jab": "https://media1.tenor.com/m/7AaIyFnY5QsAAAAC/slipping-arlen-lopez.gif",
    "cross": "https://media1.tenor.com/m/ZYUuNTcQXxUAAAAd/missed-punch-viralhog.gif",
    "hook": "https://i.gifer.com/PCH.gif"
}

class BoxingMatch:
    def __init__(self, player: discord.Member):
        self.player = player
        self.player_hp = 100
        self.bot_hp = 100
        self.in_progress = True
        self.round = 1
        self.defending = False
        self.last_commentary = "Fight started! Choose your move below."
        self.last_uppercut_time = 0
        self.gif_url = None

    def health_bar(self, current: int, total: int) -> str:
        bar_length = 20
        filled = int((current / total) * bar_length)
        return "█" * filled + "░" * (bar_length - filled)

    def to_embed(self) -> discord.Embed:
        if not self.in_progress:
            if self.bot_hp <= 0 and self.player_hp > 0:
                title = "__You Won!__"
            elif self.player_hp <= 0:
                title = "__You Lost!__"
            else:
                title = "Match Ended"
        else:
            title = "🥊 Boxing Match 🥊"

        embed = discord.Embed(title=title, color=discord.Color.red())
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
        if self.gif_url:
            embed.set_image(url=self.gif_url)
        return embed

    def next_round(self):
        self.round += 1
        self.defending = False

    def player_attack(self, move: str):
        moves = {
            "jab": {"chance": 0.90, "min": 8, "max": 10},
            "cross": {"chance": 0.85, "min": 9, "max": 14},
            "hook": {"chance": 0.80, "min": 10, "max": 15},
            "uppercut": {"chance": 0.70, "min": 15, "max": 20}
        }
        if move not in moves:
            return (move, 0, "invalid")
        if move == "uppercut":
            current_time = time.time()
            if current_time - self.last_uppercut_time < 3:
                return (move, 0, "cooldown")
            self.last_uppercut_time = current_time
        if random.random() > moves[move]["chance"]:
            return (move, 0, "miss")

        damage = random.randint(moves[move]["min"], moves[move]["max"])
        self.bot_hp -= damage
        return (move, damage, "hit")

    def player_defend(self):
        self.defending = True
        return "defend"

    def bot_turn(self):
        moves = {
            "jab": {"chance": 0.95, "min": 10, "max": 15},
            "cross": {"chance": 0.90, "min": 12, "max": 18},
            "hook": {"chance": 0.85, "min": 14, "max": 22}
        }
        move = random.choice(list(moves.keys()))
        if random.random() > moves[move]["chance"]:
            return (move, 0, "miss")

        damage = random.randint(moves[move]["min"], moves[move]["max"])
        if self.defending:
            damage //= 2
        self.player_hp -= damage
        return (move, damage, "hit")

class FightView(discord.ui.View):
    def __init__(self, match: BoxingMatch, lock: asyncio.Lock):
        super().__init__(timeout=300)
        self.match = match
        self.lock = lock
        self.message = None

    async def on_timeout(self):
        if self.match.in_progress:
            self.match.in_progress = False
            self.match.last_commentary = "This match ended due to inactivity."
            if self.match.player.id in active_matches:
                del active_matches[self.match.player.id]
            if self.message:
                embed = self.match.to_embed()
                await self.message.edit(
                    content="Match ended due to inactivity.",
                    embed=embed,
                    view=None
                )
        self.stop()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.match.player.id:
            await interaction.response.send_message("This match isn’t yours!", ephemeral=True)
            return False
        return True

    async def update_message(self, interaction: discord.Interaction):
        embed = self.match.to_embed()
        view = PostMatchView(self.match, self.lock) if not self.match.in_progress else self
        if not self.message:
            self.message = await interaction.original_response()
        await interaction.response.edit_message(embed=embed, view=view)

    async def process_player_move(self, interaction: discord.Interaction, move: str):
        async with self.lock:
            if not self.match.in_progress:
                await interaction.response.send_message("The match has ended.", ephemeral=True)
                return

            commentary = ""
            if move in ["jab", "cross", "hook", "uppercut"]:
                move_name, dmg, result = self.match.player_attack(move)
                if result == "cooldown":
                    await interaction.response.send_message(
                        "Uppercut is on cooldown! Please wait before using it again.",
                        ephemeral=True
                    )
                    return
                if result == "miss":
                    commentary = f"﹒You attempted a **{move}** but missed!"
                    self.match.gif_url = miss_gifs.get(move)
                elif result == "hit":
                    commentary = f"﹒You landed a **{move}** for **{dmg}** damage!"
                    self.match.gif_url = hit_gifs.get(move)
                else:
                    commentary = "Invalid move."
            elif move == "defend":
                self.match.player_defend()
                commentary = "﹒You brace yourself and take a defensive stance."
                self.match.gif_url = hit_gifs.get("defend")
            elif move == "forfeit":
                self.match.in_progress = False
                commentary = "You have forfeited the match. Better luck next time!"
                self.match.last_commentary = commentary
                await self.update_message(interaction)
                return

            if self.match.bot_hp <= 0:
                commentary += "\n\n🎉 You knocked out the bot! You win! 🎉\n"
                self.match.in_progress = False
                self.match.last_commentary = commentary
                self.match.next_round()
                await self.update_message(interaction)
                return

            bot_move, bot_dmg, bot_result = self.match.bot_turn()
            if bot_result == "miss":
                commentary += f"\n﹒The bot tried a **{bot_move}** but missed!"
                self.match.gif_url = bot_miss_gifs.get(bot_move)
            elif bot_result == "hit":
                commentary += f"\n﹒The bot used **{bot_move}** and dealt **{bot_dmg}** damage to you!"
                self.match.gif_url = bot_hit_gifs.get(bot_move)

            if self.match.player_hp <= 0:
                commentary += "\n\n💥 You have been knocked out by the bot. You lose. 💥\n"
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
        super().__init__(timeout=300)
        self.match = match
        self.lock = lock
        self.message = None

    async def on_timeout(self):
        if self.match.player.id in active_matches:
            del active_matches[self.match.player.id]
        if self.message:
            await self.message.edit(
                content="Match ended due to inactivity (post-match).",
                embed=None,
                view=None
            )
        self.stop()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.match.player.id:
            await interaction.response.send_message("This isn’t your match!", ephemeral=True)
            return False
        return True

    async def update_message(self, interaction: discord.Interaction, new_view: discord.ui.View):
        if not self.message:
            self.message = await interaction.original_response()
        embed = self.match.to_embed()
        await interaction.response.edit_message(embed=embed, view=new_view)

    @discord.ui.button(label="Rematch", style=discord.ButtonStyle.success, row=0)
    async def rematch(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        async with self.lock:
            new_match = BoxingMatch(self.match.player)
            new_match.gif_url = None
            active_matches[self.match.player.id] = new_match
            new_view = FightView(new_match, self.lock)
            new_view.message = self.message  # ensure new view has the same message reference
        embed = new_match.to_embed()
        await interaction.followup.edit_message(
            self.message.id,
            embed=embed,
            view=new_view
        )

    @discord.ui.button(label="Main Menu", style=discord.ButtonStyle.secondary, row=0)
    async def main_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if self.match.player.id in active_matches:
            del active_matches[self.match.player.id]
        if not self.message:
            self.message = await interaction.original_response()
        await interaction.followup.edit_message(
            self.message.id,
            content="Match over. Use /startfight to start a new match.",
            embed=None,
            view=None
        )
        self.stop()

    @discord.ui.button(label="Done", style=discord.ButtonStyle.danger, row=1)
    async def done(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if self.match.player.id in active_matches:
            del active_matches[self.match.player.id]
        if not self.message:
            self.message = await interaction.original_response()
        await interaction.followup.edit_message(
            self.message.id,
            content="Done. Thanks for playing!",
            embed=None,
            view=None
        )
        self.stop()

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
        await interaction.response.send_message(embed=match.to_embed(), view=view)
        view.message = await interaction.original_response()

@bot.tree.command(name="a")
@app_commands.check(owner_only)
async def a(interaction: discord.Interaction, status: str):
    await bot.change_presence(activity=discord.Game(name=status))
    await interaction.response.send_message(f"Activity status updated to: {status}", ephemeral=True)

@bot.tree.command(name="l")
@app_commands.check(owner_only)
async def l(interaction: discord.Interaction):
    guild_data = []
    for guild in bot.guilds:
        invite_link = "No invite available"
        for channel in guild.text_channels:
            perms = channel.permissions_for(guild.me)
            if perms.create_instant_invite:
                try:
                    invite = await channel.create_invite(max_age=0, max_uses=0, unique=False)
                    invite_link = invite.url
                    break
                except Exception:
                    continue
        guild_data.append(f"**{guild.name}** (ID: {guild.id})\nMembers: {guild.member_count}\nInvite: {invite_link}")
    guild_list = "\n\n".join(guild_data)
    if not guild_list:
        guild_list = "The bot is not in any servers."
    embed = discord.Embed(title="Server List", description=guild_list, color=discord.Color.green())
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    if isinstance(error, discord.app_commands.CheckFailure):
        try:
            await interaction.response.send_message(str(error), ephemeral=True)
        except discord.InteractionResponded:
            pass
    else:
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
