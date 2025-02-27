import tkinter as tk
from tkinter import scrolledtext
import threading
import json
import os
import asyncio
import requests
import io
import re
from pydub import AudioSegment
import discord
from discord.ext import commands
from discord import FFmpegPCMAudio

###########################################
# DISCORD BOT + TTS LOGIC                 #
###########################################

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

DISCORD_TOKEN = None
ELEVEN_LABS_API_KEY = None
current_voice_id = None
REQUIRED_ROLE = None

def load_config_from_memory(discord_token: str, eleven_key: str, role: str):
    global DISCORD_TOKEN, ELEVEN_LABS_API_KEY, current_voice_id, REQUIRED_ROLE
    DISCORD_TOKEN = discord_token
    ELEVEN_LABS_API_KEY = eleven_key
    current_voice_id = None
    REQUIRED_ROLE = role.lower() if role else None

def get_tts_audio_stream(text, voice_id):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
    headers = {"xi-api-key": ELEVEN_LABS_API_KEY, "Content-Type": "application/json"}
    data = {"text": text, "model_id": "eleven_monolingual_v1", "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}}
    response = requests.post(url, json=data, headers=headers, stream=True)
    return io.BytesIO(response.content) if response.status_code == 200 else None

def has_required_role():
    async def predicate(ctx):
        if not REQUIRED_ROLE:
            return True
        role_names = [role.name.lower() for role in ctx.author.roles]
        if REQUIRED_ROLE in role_names:
            return True
        await ctx.send(f"You need the **{REQUIRED_ROLE.capitalize()}** role to use this command.")
        return False
    return commands.check(predicate)

def fetch_voices():
    url = "https://api.elevenlabs.io/v1/voices"
    headers = {"xi-api-key": ELEVEN_LABS_API_KEY}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        voices = response.json()["voices"]
        return {voice["name"].lower(): voice["voice_id"] for voice in voices}
    return {}

def create_new_bot():
    global bot
    intents = discord.Intents.default()
    intents.messages = True
    intents.message_content = True
    intents.voice_states = True
    bot = commands.Bot(command_prefix="!", intents=intents)

    @bot.event
    async def on_ready():
        print(f"{bot.user.name} is connected and ready!")

    @bot.command()
    @has_required_role()
    async def speak(ctx, *, message: str):
        global current_voice_id
        if ctx.author.voice is None:
            await ctx.send("You need to be in a voice channel for me to join.")
            return
        if not current_voice_id:
            await ctx.send("No voice selected—use !setvoice first!")
            return
        voices = fetch_voices()
        parts = re.findall(r"(\[.*?\])?(.*?)(?=\[|$)", message)
        if not parts:
            await ctx.send("Invalid input format.")
            return
        combined_audio = AudioSegment.silent(duration=0)
        active_voice_id = current_voice_id
        for voice_tag, segment_text in parts:
            if voice_tag:
                voice_name = voice_tag.strip("[]").strip().lower()
                if voice_name in voices:
                    active_voice_id = voices[voice_name]
                else:
                    await ctx.send(f"Voice **{voice_name}** not found. Using default voice.")
                    active_voice_id = current_voice_id
            if segment_text.strip():
                audio_stream = get_tts_audio_stream(segment_text.strip(), active_voice_id)
                if audio_stream:
                    segment_audio = AudioSegment.from_file(io.BytesIO(audio_stream.read()), format="mp3")
                    combined_audio += segment_audio
        combined_audio.export("final_tts_audio.mp3", format="mp3")
        voice_channel = ctx.author.voice.channel
        voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
        if voice_client is None:
            voice_client = await voice_channel.connect()
        source = FFmpegPCMAudio("final_tts_audio.mp3")
        voice_client.play(source, after=lambda e: print("Finished playing audio"))
        while voice_client.is_playing():
            await asyncio.sleep(1)

    @bot.command()
    @has_required_role()
    async def setvoice(ctx, *, voice_name: str):
        global current_voice_id
        voices = fetch_voices()
        voice_name_lower = voice_name.lower()
        if voice_name_lower in voices:
            current_voice_id = voices[voice_name_lower]
            await ctx.send(f"Default voice set to: **{voice_name.capitalize()}**")
        else:
            await ctx.send(f"Voice **{voice_name}** not found. Use `!voices` to see options.")

    @bot.command()
    @has_required_role()
    async def voices(ctx):
        voices = fetch_voices()
        if voices:
            voice_list = "\n".join([name.capitalize() for name in voices.keys()])
            await ctx.send(f"Available voices:\n```\n{voice_list}\n```")
        else:
            await ctx.send("Unable to fetch voices. Please try again later.")

    @bot.command()
    @has_required_role()
    async def help(ctx):
        help_text = """
Available commands:
!speak [voice] text - Speak text in a voice (e.g., !speak [Lily] Hello).
!setvoice voice_name - Set the default voice (e.g., !setvoice Lily).
!voices - List all available voices.
!help - Show this list.
        """
        await ctx.send(f"```\n{help_text.strip()}\n```")

#######################################
#         TKINTER GUI SECTION         #
#######################################

class TTSBotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("All-In-One Discord TTS Bot")
        self.config_path = os.path.join(os.path.dirname(__file__), 'config.json')
        loaded_token = loaded_eleven = loaded_role = ""
        try:
            with open(self.config_path, 'r') as f:
                cfg = json.load(f)
                loaded_token = cfg.get("discord_token", "")
                loaded_eleven = cfg.get("eleven_labs_api_key", "")
                loaded_role = cfg.get("required_role", "")
        except (FileNotFoundError, json.JSONDecodeError):
            pass

        self.discord_token_var = tk.StringVar(value=loaded_token)
        self.eleven_labs_var = tk.StringVar(value=loaded_eleven)
        self.required_role_var = tk.StringVar(value=loaded_role)

        tk.Label(root, text="Discord Token:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        tk.Entry(root, textvariable=self.discord_token_var, width=40).grid(row=0, column=1, padx=5, pady=5)
        tk.Label(root, text="Eleven Labs API Key:").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        tk.Entry(root, textvariable=self.eleven_labs_var, width=40).grid(row=1, column=1, padx=5, pady=5)
        tk.Label(root, text="Required Role:").grid(row=2, column=0, padx=5, pady=5, sticky="e")
        tk.Entry(root, textvariable=self.required_role_var, width=40).grid(row=2, column=1, padx=5, pady=5)
        self.start_button = tk.Button(root, text="Start Bot", command=self.start_bot)
        self.start_button.grid(row=3, column=0, padx=5, pady=5)
        self.stop_button = tk.Button(root, text="Stop Bot", command=self.stop_bot, state=tk.DISABLED)
        self.stop_button.grid(row=3, column=1, padx=5, pady=5)

        commands_text = "Commands:\n!speak [voice] text - Speak text in a voice (e.g., !speak [Lily] Hello)\n!setvoice voice_name - Set default voice (e.g., !setvoice Lily)\n!voices - List voices\n!help - Show commands in Discord"
        tk.Label(root, text=commands_text, justify=tk.LEFT).grid(row=4, column=0, columnspan=2, padx=5, pady=5)

        self.log_window = scrolledtext.ScrolledText(root, width=80, height=20, state=tk.DISABLED)
        self.log_window.grid(row=5, column=0, columnspan=2, padx=10, pady=5)

        self.bot_thread = None
        self.bot_loop = None
        self.is_bot_running = False

    def log_message(self, message: str):
        self.log_window.config(state=tk.NORMAL)
        self.log_window.insert(tk.END, message + "\n")
        self.log_window.config(state=tk.DISABLED)
        self.log_window.yview(tk.END)

    def start_bot(self):
        if self.is_bot_running:
            self.log_message("Bot is already running.")
            return
        self.log_message("Starting bot...")
        token = self.discord_token_var.get()
        eleven = self.eleven_labs_var.get()
        role = self.required_role_var.get()
        newcfg = {"discord_token": token, "eleven_labs_api_key": eleven, "required_role": role}
        try:
            with open(self.config_path, 'w') as f:
                json.dump(newcfg, f, indent=4)
        except Exception as e:
            self.log_message(f"Couldn't write config.json: {e}")
        load_config_from_memory(token, eleven, role)
        create_new_bot()
        self.bot_loop = asyncio.new_event_loop()
        self.bot_thread = threading.Thread(target=self.run_discord_bot, args=(self.bot_loop,), daemon=True)
        self.bot_thread.start()
        self.is_bot_running = True
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)

    def stop_bot(self):
        if not self.is_bot_running:
            self.log_message("Bot is not running.")
            return
        self.log_message("Stopping bot...")
        stop_thread = threading.Thread(target=self._stop_bot_logic, daemon=True)
        stop_thread.start()

    def _stop_bot_logic(self):
        async def close_bot():
            await bot.close()
        future = asyncio.run_coroutine_threadsafe(close_bot(), self.bot_loop)
        try:
            future.result()
        except Exception as e:
            self.log_message(f"Error while stopping bot: {e}")
        pending_tasks = asyncio.all_tasks(self.bot_loop)
        for task in pending_tasks:
            task.cancel()
            try:
                self.bot_loop.run_until_complete(task)
            except asyncio.CancelledError:
                pass
        self.bot_loop.call_soon_threadsafe(self.bot_loop.stop)
        self.bot_thread.join()
        self.bot_loop.close()
        self.bot_loop = None
        self.is_bot_running = False
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.log_message("Bot has stopped.")

    def run_discord_bot(self, loop):
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(bot.start(DISCORD_TOKEN))
        except Exception as e:
            self.log_message(f"Bot error: {e}")
        finally:
            loop.run_until_complete(bot.close())
            self.log_message("Bot has exited.")
            self.is_bot_running = False
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)

if __name__ == "__main__":
    root = tk.Tk()
    gui = TTSBotGUI(root)
    root.mainloop()