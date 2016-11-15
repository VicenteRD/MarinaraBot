import sys

import discord
from discord.ext import commands

import timer as Timer

import asyncio

ADMIN_ID = "87387330037448704"

TOKEN = ""
DESCRIPTION = '''A marinara timer bot that can be configured to your needs.'''
COMMAND_PREFIX = '!'
DEFAULT_TIMER = "(2xStudy:32,Break:8),Study:32,Long_Break:15"

RESPONSE_LIFESPAN = 15

TIMER_STEP = 1 # in seconds


class PomodoroBot(commands.Bot) :
	""" An extension of the Bot class, that contains the necessary attributes and methods to run a Marinara Timer. """
	
	# The timers currently running. There can be one per channel. (Indexed by the channel's ID)
	pomodoroTimer = {}
	# The messages that gets pinned, containing the current timer and its status (1 per channel, indexed by the channel's ID)
	statusMessage = {}

	# Whether the bot should send TTS messages on a change of periods.
	tts = False

	# Whether the bot is ticking, thus making all timers run.
	ticking = False

	def __init__(self, command_prefix, formatter=None, description=None, pm_help=False, **options):
		super().__init__(command_prefix, formatter, description, pm_help, **options)

	@asyncio.coroutine
	async def tick(self) :
		""" Ticks all timers. """

		await bot.wait_until_ready()

		while not bot.is_closed :

			if len(pomodoroTimer) == 0 :
				ticking = False
				return

			for channelId, timer in pomodoroTimer.items() :
				if timer.state == Timer.State.RUNNING :
					timer.currentTime += 1

					if timer.currentTime >= timer.pTimes[timer.currentPeriod] * 60 :
						toSay = "@here | '" + timer.pNames[timer.currentPeriod] + "' period over!"

						timer.currentTime = 0
						timer.currentPeriod += 1

						if timer.currentPeriod >= len(timer.pTimes) :
							if timer.onRepeat :
								if len(timer.pTimes) == 1:
									timer.currentPeriod = 0
								else:
									timer.currentPeriod = timer.currentPeriod % len(timer.pTimes)
							else :
								toSay += "\n...I have ran out of periods, and looping is off. Time to procrastinate?"
								
								print(toSay + "[channel: " + channelId + "]")
								await bot.send_message(channelId, toSay)
								
								timer.state = Timer.State.STOPPED
								await bot.unpin_message(bot.statusMessage[channelId])
								await bot.delete_message(bot.statusMessage[channelId])
								del bot.statusMessage[channelId]

								continue

						if timer.nextAction == Timer.Action.NONE :
							toSay += " '" + timer.pNames[timer.currentPeriod] + "' period now starting." #TODO also print, all prints to log
						
						print(toSay + "[channel: " + channelId + "]")
						await bot.send_message(channelId, toSay, tts = bot.tts)

				if timer.nextAction == Timer.Action.STOP :
					timer.nextAction = Timer.Action.NONE
					
					timer.currentPeriod = -1
					timer.currentTime = 0
					timer.state = Timer.State.STOPPED

					print("Timer on channel " + channelId + " has stopped.")
					await bot.send_message(channelId, "Timer has stopped.")

					await bot.unpin_message(bot.statusMessage[channelId])
					await bot.delete_message(bot.statusMessage[channelId])
					del bot.statusMessage[channelId]
					continue

				elif timer.nextAction == Timer.Action.PAUSE :
					timer.nextAction = Timer.Action.NONE
					timer.state = Timer.State.PAUSED

					print("Timer on channel " + channelId + " has paused.")
					await bot.send_message(channelId, "Timer has paused.")

				elif timer.nextAction == Timer.Action.RUN :
					
					if timer.state == Timer.State.STOPPED :
						timer.currentPeriod = 0

					statusAlert = ("Starting!" if timer.state == Timer.State.STOPPED else "Restarting!")
					print(statusAlert + "[channel: " + channelId + "]")
					await bot.send_message(channelId, statusAlert)

					if bot.statusMessage == None :
						bot.statusMessage[channelId] = await bot.send_message(channelId, "Generating status...")
						try :
							await bot.pin_message(bot.statusMessage[channelId])
						except discord.Forbidden:
							print("No permission to pin messages on channel " + channelId + ".")
							await bot.send_message(channelId, "I tried to pin a message and failed. Can I haz permission to pin messages? https://goo.gl/tYYD7s")

					timer.nextAction = Timer.Action.NONE
					timer.state = Timer.State.RUNNING
					
				await bot.edit_message(bot.statusMessage, bot.generateTimeStatus(True))

			if len(pomodoroTimer) == 0 :
				ticking = False
				return
			else :
				await asyncio.sleep(TIMER_STEP)

				
bot = PomodoroBot(command_prefix = COMMAND_PREFIX, description = DESCRIPTION, pm_help = True)

@bot.event
async def on_ready():
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('------')

@bot.command(pass_context = True)
async def setup(ctx, timerFormat = "default", repeat = True):
	""" Sets a marinara timer on the channel in which this message was sent.
		repeat	: Indicates whether the timer should start over when it's done with the list of periods or simply stop. (Default: True)
		tts 	: Indicates whether the timer should send a TTS message or a normal one whenever the period finishes or changes. (Default: False)"""

	if timerFormat == "help" :
		await bot.say("**Example:**\n\t" + COMMAND_PREFIX + "setup (2xStudy:32,Break:8),Study:32,Long_Break:15\n\t_This will give you a sequence of 32, 8, 32, 8, 32, 15_")
		return

	if timerFormat == "default" :
		timerFormat = DEFAULT_TIMER

	timerId = getChannelId(ctx)

	bot.pomodoroTimer[timerId] = Timer.PomodoroTimer()
	result, times = bot.pomodoroTimer[timerId].setup(timerFormat, repeat)
	
	if result == 0 and times != None:
		await bot.say("Correctly set up timer config: " + times, delete_after = RESPONSE_LIFESPAN)

	elif result == -1 : # len(pTimes) > 0
		print("Rejecting setup command, there is a period set already established")
		await bot.say("I'm already set and ready to go, please use the reset command if you want to change the timer configuration.")
		
	elif result == -2 : # state == RUNNING or PAUSED
		print("Someone tried to modify the timer while it was already running!")
		await bot.say("Please stop the timer completely before modifying it.")
		return

	elif result == -3 : # format error
		print("Could not set the periods correctly, command 'setup' failed")
		await bot.say("I did not understand what you wanted, please try again!") 

@bot.command(pass_context = True)
async def starttimer(ctx) :
	""" Starts the timer with the recorded setup. If none present, or if it's already running, it simply gives an error message."""
	
	timerId = getChannelId(ctx)

	if bot.pomodoroTimer[timerId] == None :
		print(getAuthorName(ctx) + " tried to start an inexistant timer [Channel: " + timerId + "]")
		await bot.say("No timer found for this channel.", delete_after = RESPONSE_LIFESPAN)

	else :
		if bot.pomodoroTimer[timerId].isSet() :
			print(getAuthorName(ctx) + " tried to start a timer without set periods [Channel: " + timerId + "]")
			await bot.say("Timer is not set up. Please use the command 'setup'. Use 'halp' or 'setup help' for further explanation", delete_after = RESPONSE_LIFESPAN)
			return
		
		else :
			if bot.pomodoroTimer[timerId].start() : # this is going to come back to haunt me in my best nightmares
				if not bot.ticking :
					ticking = True
					await bot.tick()
			else : 
				print(getAuthorName(ctx) + " tried to start a timer that was already running [Channel: " + timerId + "]")
				await bot.say("This channel's timer is already running", delete_after = RESPONSE_LIFESPAN)

@bot.command(pass_context = True)
async def pause(ctx) :
	""" Pauses the timer, if it's running. Keeps all settings and current period / time. """

	timerId = getChannelId(ctx)

	if bot.pomodoroTimer[timerId] == None :
		print(getAuthorName(ctx) + " tried to pause an inexistant timer [Channel: " + timerId + "]")
		await bot.say("No timer found for this channel.", delete_after = RESPONSE_LIFESPAN)

	else :
		if bot.pomodoroTimer[getChannelId(ctx)].pause() :
			alert = "Timer will be paused soon."
			print(alert)
			await bot.say(alert, delete_after = 1)

		else :
			await bot.say("Bruh, I cannot stop something that isn't moving.", delete_after = RESPONSE_LIFESPAN)

@bot.command()
async def stop() :
	""" Stops the timer, if it's running, resetting the current period and time, but keeping the setup. """

	timerId = getChannelId(ctx)

	if bot.pomodoroTimer[timerId] == None :
		print(getAuthorName(ctx) + " tried to stop an inexistant timer [Channel: " + timerId + "]")
		await bot.say("No timer found for this channel.", delete_after = RESPONSE_LIFESPAN)

	else :
		if bot.pomodoroTimer[getChannelId(ctx)].stop() :
			alert = "Timer will stop soon."
			print(alert)
			await bot.say(alert, delete_after = 1)

		else :
			stop = "Timer has stopped." 
			print(stop)
			await bot.say(stop)

			await bot.unpin_message(bot.statusMessage)
			await bot.delete_message(bot.statusMessage)

@bot.command(pass_context = True)
async def resume(ctx) :
	""" Resumes a paused timer. """

	timerId = getChannelId(ctx)

	if bot.pomodoroTimer[timerId] == None :
		print(getAuthorName(ctx) + " tried to resume an inexistant timer [Channel: " + timerId + "]")
		await bot.say("No timer found for this channel.", delete_after = RESPONSE_LIFESPAN)

	else :
		if not bot.pomodoroTimer[getChannelId(ctx)].resume() :
			if getAuthorId(ctx) == "244720666018840576" :
				await bot.say("No grumbles for you, " + getAuthorName(ctx, True) + "!", delete_after = RESPONSE_LIFESPAN)
			else :
				await bot.say("**grumble grumble.** The timer is stopped or already running, I can't resume that!", delete_after = RESPONSE_LIFESPAN)


@bot.command(pass_context = True)
async def goto(ctx, nPeriod : int) :
	""" Skips to the (n-1)th period. """

	timerId = getChannelId(ctx)

	if bot.pomodoroTimer[timerId] == None :
		print(getAuthorName(ctx) + " tried changing periods in an inexistant timer [Channel: " + timerId + "]")
		await bot.say("No timer found for this channel.", delete_after = RESPONSE_LIFESPAN)
		return

	else :
		label = bot.pomodoroTimer[getChannelId(ctx)].goto(nPeriod)

		if label != None :
			success = "Moved to period number " + str(nPeriod) + " (" + label + ")"
			print(success)
			await bot.say(success)
		else :
			print("Invalid period number entered when trying goto command")
			await bot.say("Invalid period number.")

@bot.command(pass_context = True)
async def reset(ctx) :
	""" Resets the timer setup. """

	timerId = getChannelId(ctx)

	if bot.pomodoroTimer[timerId] == None :
		print(getAuthorName(ctx) + " tried resetting an inexistant timer setup [Channel: " + timerId + "]")
		await bot.say("No timer found for this channel.", delete_after = RESPONSE_LIFESPAN)

	else:
		if bot.pomodoroTimer[timerId].isStopped() :
			del bot.pomodoroTimer[timerId]

			print(getAuthorName(ctx) + " tried reset a timer [Channel: " + timerId + "]")
			await bot.say("Succesfully reset session configuration.", delete_after = RESPONSE_LIFESPAN)		
		else :
			print(getAuthorName(ctx) + " tried resetting a timer that was running or paused [Channel: " + timerId + "]")
			await bot.say("Cannot do that while the timer is not stopped. Please stop it first", delete_after = RESPONSE_LIFESPAN)

@bot.command(pass_context = True)
async def time(ctx) :
	""" Gives the user the current period and time of the timer. """

	timerId = getChannelId(ctx)

	if bot.pomodoroTimer[timerId] == None :
		print(getAuthorName(ctx) + " tried to get the current time of an inexistant timer [Channel: " + timerId + "]")
		await bot.say("No timer found for this channel.", delete_after = RESPONSE_LIFESPAN)

	else :
		time = bot.pomodoroTimer[timerId].time()
	
		print(time)
		await bot.say(time, delete_after = RESPONSE_LIFESPAN * 2)

@bot.command(pass_context = True)
async def status(ctx) :
	""" Tells the user whether the timer is stopped, running or paused. """

	timerId = getChannelId(ctx)

	if bot.pomodoroTimer[timerId] == None :
		print(getAuthorName(ctx) + " tried to check the status of an inexistant timer [Channel: " + timerId + "]")
		await bot.say("No timer found for this channel.", delete_after = RESPONSE_LIFESPAN)

	else :
		status = bot.pomodoroTimer[timerId].status()

		print(status)
		await bot.say(status, delete_after = RESPONSE_LIFESPAN * 2)

@bot.command(pass_context = True)
async def tts(toggle : str) :
	""" Sets the tts option on or off. """

	toggle = toggle.lower()

	if toggle == "on" or toggle == "true" or toggle == "yes" or toggle == "y" :
		bot.tts = True
		print("TTS now on.")
		await bot.say("Text-to-speech now on.", tts = True, delete_after = RESPONSE_LIFESPAN)
	else :
		bot.tts = False 
		print("TTS now off.")
		await bot.say("Text-to-speech now off.", delete_after = RESPONSE_LIFESPAN)

@bot.command(pass_context = True)
async def halp(ctx) :
	""" Tells the user how to use the bot. """

	helpStr ="""
**!setup _<format> [loop tts]_**
\tSets the marinara timer up.
\t\tformat    : The periods format. Each period is a set of <name>:<time>, where time is in minutes, and periods are separated by commas. 
\t\trepeat    : Indicates whether the timer should start over when it's done with the list of periods or simply stop. ('True' or 'False', defaults to True)
\t\ttts           : Indicates whether the timer should say period changes out loud. ('True' or 'False', defaults to False)
**!starttimer**
\tStarts the timer (must be set up previously).
**!pause**
\tPauses the timer, keeping the current period and time intact.
**!stop**
\tStops the timer, resetting it to the first period and the time to 0
**!resume**
\tRestarts a paused timer.
**!goto _<period-index>_**
\tSkips to the indicated period (Resets the time to 0 within the period).
**!tts _<on|off>_**
\tTurns text-to-speech on or off.
**!time**
\tIf the timer is running, it will show how much time of the current period has passed.
**!status**
\tShows whether the timer is stopped, running or paused.
**!halp**
\tShows this message."""

	await bot.send_message(ctx.message.author, content = helpStr)

@bot.command(pass_context = True)
async def shutdown(ctx) :
	""" Exits the program. """

	if getAuthorId(ctx) == ADMIN_ID :
		print("Shutting down...")
		await bot.say("Hope I did well, bye!")
		
		for channelId, pinnedMessage in bot.statusMessage.items() :
			await bot.send_message(channelId, "I'm sorry, I have to go. See you later!")

			await bot.unpin_message(pinnedMessage)
			await bot.delete_message(pinnedMessage)
		await bot.logout()
	else :
		print(getAuthorName(ctx) + "attempted to stop the bot and failed (No permission to shut down).")

# Helper functions

def getChannelId(context : commands.Context) :
	return context.message.channel.id

def getAuthorId(context : commands.Context) :
	return context.message.author.id

def getAuthorName(context : commands.Context, nick = False) :
	return (context.message.author.nick if nick and context.message.author.nick != None else context.message.author.name)

def authorHasRole(context : commands.Context, roleId : str) :
	for role in context.message.author.roles :
		if role.id == roleId :
			return True
	return False


if __name__ == '__main__':

	if len(sys.argv) < 2 :
		print("Not enough arguments received!\nUsage: " + sys.argv[0] + " <token> [prefix] [admin_id]")
		exit(0)

	elif len(sys.argv) == 2 :
		TOKEN = sys.argv[1]

	elif len(sys.argv) == 3 and (len(sys.argv[2]) == 1 and not (sys.argv[2][0] > 'A' and sys.argv[2][0] < 'z')) :
		print("Command prefix set to " + sys.argv[2] +"\n")
		COMMAND_PREFIX = sys.argv[2]

	elif len(sys.argv) == 4 :
		print("Admin set to ID: " + sys.argv[3])
		ADMIN_ID = sys.argv[3]

	bot.command_prefix = COMMAND_PREFIX

	#TODO : logging

	bot.run(TOKEN)
