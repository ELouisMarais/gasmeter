#!/usr/bin/python3
# gasmeter.py

# Show the gasmeter reading on an LCD display. This replaces the C language
# program 'gasmeter' that relies on the deprecated WiringPi library. Its
# author got fed up with people using his work and not appropriately 
# crediting it, which I can understand. Read more on his website:
# http://wiringpi.com/news/
#
# I also wanted to move away from using the C language, and Python seemed
# ideal.
#
# My LCD code is based on this work: (lcd_16x2.py, Python 2 on an original Pi):
# https://www.raspberrypi-spy.co.uk/2012/07/16x2-lcd-module-control-using-python/
# No license is mentioned on the page, so the best I can do is to quote the 
# source. The bits of code I used from the original have a comment to that 
# effect. I both extended and changed the code significanlty.
# 
# The gasmeter stuff is based in part on gasmeter.c, the original code used for
# this purpose (I was surprised how relatively new this is). Here are some of
# the original comments:
#
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #
#  gasmeter.c                                                                  #
#                                                                              # 
# Based on lcd.c from the wiringPi software - see original message and         #
# copyright below.                                                             #
#                                                                              # 
# Louis Marais (start 2016-07-06, initial version finalised on 2016-07-12)     #
#                                                                              # 
# Modified on 2016-07-22:                                                      #
# Memory leak - MJW investigated and found that it leaked in the               #
# getIPaddr routine. I'm suppose to use freeifaddrs to free the                #
# memory used in the list that is created by the getifaddrs function.          #
# MJW also pointed out several other things I could change to make             #
# the code better. The funky thing is that this was in the example I           #
# copied from, but I missed it.                                                #
#                                                                              # 
# Modified on 2016-08-01:                                                      #
# I discussed the application with Jason. He said it would be best if the      #
# gasmeter reasing is logged to the file every time it changes, as well as     #
# once an hour. This will be useful to study gas flow during fills, etc.       #
# I added the millisecond portion to the time stamp in the meterlog file,      #
# in case there are more than one pulse per second.                            #
#                                                                              # 
# Modified on 2016-12-14:                                                      #
# The millisecond portion of the timestamp was extracted from a different      #
# clock, so the timestamps in the files were wrong. I fixed that, see          #
# line ~ 292.                                                                  #
#                                                                              # 
# Modified 2018-11-30:                                                         #
# Data now stored in a new file each month with filename {yyyy-mm}.dat in the  # 
# ~/data directory.                                                            #
#                                                                              # 
# On a 20 x 4 LCD module display the following:                                #
#                                                                              # 
#    00000000011111111112                                                      #
#    12345678901234567890                                                      #
#   +--------------------+                                                     #
# 1 |YYYY-MM-DD  HH:MM:SS| Current date and time                               #
# 2 |  IP: 10.64.39.XXX  | IP address of Pi2                                   #
# 3 |B366      NSW32346HP| Room number and serial number of gas meter          #
# 4 |     00000.000 m3   | Meter reading in cubic metres                       #
#   +--------------------+                                                     #
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #
#
# Some of the routines used below have been scavanged from other projects, some
# of which are acknowledged. I should really collect these in a library at some
# stage.
#
# -----------------------------------------------------------------------------
#
# Version: 1.0
# Author: Louis Marais
# Start date: 2021-06-18
# Last modification: 2021-07-01
#
# -----------------------------------------------------------------------------
#
# Version: 2.0
# Author: Louis Marais
# Start date: 2026-01-28
# Last modification: 2026-01-28
#
# Modifications:
#
# 1. Fixed up (and modernised) formatting, etc. Removed commented out code.
# 2. Added UPS option - if a UPS is installed, the UPS messages are shown in
#    rotation with the IP and room / serial number messages.
#
#    Display alternates between these two states:
#
#      00000000011111111112                                                      
#      12345678901234567890                                                      
#     +--------------------+                                                     
#   1 |YYYY-MM-DD  HH:MM:SS| Current date and time
#   2 |  IP: 10.64.39.XXX  | IP address of Pi
#   3 |B366      NSW32346HP| Room number and serial number of gas meter
#   4 |     00000.000 m3   | Meter reading in cubic metres
#     +--------------------+                                                     
#     +--------------------+                                                     
#   1 |YYYY-MM-DD  HH:MM:SS| Current date and time                               
#   2 |POWER SOURCE: MAINS | Power source: Either MAINS or UPS
#   3 |BATTERY:  54% CHARGE| Battery state
#   4 |     00000.000 m3   | Meter reading in cubic metres
#     +--------------------+                                                     
#
# -----------------------------------------------------------------------------
#
# Version: Next
# Author: 
# Start date: 
# Last modification: 
#
# Modifications:
#
# -----------------------------------------------------------------------------

import RPi.GPIO as GPIO
import os
import datetime
import time
import sys
import subprocess
import re
import argparse
import configparser
import signal

script = os.path.basename(__file__)
VERSION = "2.0"
AUTHORS = "Louis Marais"

DEBUG = False

versionStr = f"{script} version {VERSION} written by {AUTHORS}"

# -----------------------------------------------------------------------------
# Setup stuff
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
 
# Define GPIO to LCD mapping
#       BCM   Physical
LCD_RS = 7  #    26
LCD_E  = 8  #    24
LCD_D4 = 23 #    16
LCD_D5 = 24 #    18
LCD_D6 = 25 #    22
LCD_D7 = 4  #     7 
 
# Define some device constants
LCD_WIDTH = 20
LCD_CHR = True
LCD_CMD = False
 
LCD_LINE_1 = 0x80
LCD_LINE_2 = 0xC0
LCD_LINE_3 = 0x94
LCD_LINE_4 = 0xD4
 
# Timing constants
E_PULSE = 0.0005
E_DELAY = 0.0005
#E_PULSE = 0.001 # Try increasing these times if LCD unresponsive
#E_DELAY = 0.001

cubicChar = (
	0b01100, #  xx
	0b10010, # x  x
	0b00100, #   x
	0b10010, # x  x
	0b01100, #  xx
	0b00000, #
	0b00000, #
	0b00000, #
)

# -----------------------------------------------------------------------------
# Sub routines
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# From raspberrypi-spy.co.uk
def lcd_init():
	# Initialise display
	lcd_byte(0x33,LCD_CMD) # 110011 Initialise
	lcd_byte(0x32,LCD_CMD) # 110010 Initialise
	lcd_byte(0x06,LCD_CMD) # 000110 Cursor move direction
	lcd_byte(0x0C,LCD_CMD) # 001100 Display On,Cursor Off, Blink Off
	lcd_byte(0x28,LCD_CMD) # 101000 Data length, number of lines, font size
	lcd_byte(0x01,LCD_CMD) # 000001 Clear display
	time.sleep(E_DELAY)
	return
 
# -----------------------------------------------------------------------------
# From raspberrypi-spy.co.uk
def lcd_byte(bits, mode):
	GPIO.output(LCD_RS, mode)
 
	GPIO.output(LCD_D4, False)
	GPIO.output(LCD_D5, False)
	GPIO.output(LCD_D6, False)
	GPIO.output(LCD_D7, False)
	if bits&0x10==0x10:
		GPIO.output(LCD_D4, True)
	if bits&0x20==0x20:
		GPIO.output(LCD_D5, True)
	if bits&0x40==0x40:
		GPIO.output(LCD_D6, True)
	if bits&0x80==0x80:
		GPIO.output(LCD_D7, True)
 
	lcd_toggle_enable()
 
	GPIO.output(LCD_D4, False)
	GPIO.output(LCD_D5, False)
	GPIO.output(LCD_D6, False)
	GPIO.output(LCD_D7, False)
	if bits&0x01==0x01:
		GPIO.output(LCD_D4, True)
	if bits&0x02==0x02:
		GPIO.output(LCD_D5, True)
	if bits&0x04==0x04:
		GPIO.output(LCD_D6, True)
	if bits&0x08==0x08:
		GPIO.output(LCD_D7, True)
 
	lcd_toggle_enable()
	return
 
# -----------------------------------------------------------------------------
# From raspberrypi-spy.co.uk
def lcd_toggle_enable():
	time.sleep(E_DELAY)
	GPIO.output(LCD_E, True)
	time.sleep(E_PULSE)
	GPIO.output(LCD_E, False)
	time.sleep(E_DELAY)
	return

# -----------------------------------------------------------------------------
# From raspberrypi-spy.co.uk
def lcd_string(message,line):
	message = message.ljust(LCD_WIDTH," ")
	
	lcd_byte(line, LCD_CMD)
	
	for i in range(LCD_WIDTH):
		lcd_byte(ord(message[i]),LCD_CHR)
	return
 
# -----------------------------------------------------------------------------
# From raspberrypi-spy.co.uk
def lcd_char(ch,line,row):
	if row > LCD_WIDTH:
		return
	mempos = line + row - 1
	lcd_byte(mempos,LCD_CMD)
	lcd_byte(ord(ch[0]),LCD_CHR)
	return

# -----------------------------------------------------------------------------
def lcd_create_char(char_no,char_array):
	cg_ram_addr = 0x40 + char_no * 8
	for i in range(0,8):
		lcd_byte(cg_ram_addr+i,LCD_CMD)
		lcd_byte(char_array[i],LCD_CHR)
	return

# -----------------------------------------------------------------------------
# From raspberrypi-spy.co.uk
def setupLCD():
	GPIO.setwarnings(False)
	GPIO.setmode(GPIO.BCM)       # Use BCM GPIO numbers
	GPIO.setup(LCD_E, GPIO.OUT)  # E
	GPIO.setup(LCD_RS, GPIO.OUT) # RS
	GPIO.setup(LCD_D4, GPIO.OUT) # DB4
	GPIO.setup(LCD_D5, GPIO.OUT) # DB5
	GPIO.setup(LCD_D6, GPIO.OUT) # DB6
	GPIO.setup(LCD_D7, GPIO.OUT) # DB7
	return

# ---------------------------------------------------------------------------
def ts():
	now = datetime.datetime.now()
	s = now.strftime("%Y-%m-%d %H:%M:%S")
	return(s)

# ---------------------------------------------------------------------------
def debug(msg):
	if DEBUG:
		print(ts(),msg)
	return

# -----------------------------------------------------------------------------
def addSlashToPath(path):
	if not path.endswith('/'):
		path += '/'
	return path

# -----------------------------------------------------------------------------
def createAbsFilename(flnm,base):
	if not flnm.startswith('/'):
		flnm = base + flnm
	return(flnm)

# -----------------------------------------------------------------------------
def createAbsPath(path,base):
	path = addSlashToPath(path)
	if not path.startswith('/'):
		path = base + path
	return(path)

# -----------------------------------------------------------------------------
def errorExit(s):
	print(f'ERROR: {s}')
	sys.exit(1)

# -----------------------------------------------------------------------------
def sigHandler(sig,frame):
	global running
	running = False
	return

# -----------------------------------------------------------------------------
# adapted from ottplib.py, so that this can be used with kickstart.py
def createProcessLock(lockfile):
	if not(testProcessLock(lockfile)):
		return False
	flock = open(lockfile,'w')
	flock.write(os.path.basename(sys.argv[0])+' '+str(os.getpid()))
	flock.close()
	return True

# -----------------------------------------------------------------------------
# adapted from ottplib.py, so that this can be used with kickstart.py
def removeProcessLock(lockfile):
	if(os.path.isfile(lockfile)):
		os.unlink(lockfile)
	return

# -----------------------------------------------------------------------------
# adapted from ottplib.py, so that this can be used with kickstart.py
def testProcessLock(lockfile):
	if(os.path.isfile(lockfile)):
		flock = open(lockfile,'r')
		info = flock.readline().split()
		flock.close()
		if(len(info) == 2):
			if(os.path.exists('/proc/'+str(info[1]))):
				return False
	return True

# -----------------------------------------------------------------------------
def checkConfigOption(config,section,key):
	if config.has_option(section,key):
		return True
	else:
		return False

# -----------------------------------------------------------------------------
def checkConfigOptions(config,sectkeys,configfile):
	debug(f'checkConfigOptions: Checking configuration file: {configfile}')
	for pair in sectkeys:
		sectkey = pair.split(",")
		sect = sectkey[0].strip()
		key = sectkey[1].strip()
		if not(checkConfigOption(config,sect,key)):
			errorExit(f'checkConfigOptions: [{sect}][{key}] missing from {configfile}!')
		else:
			debug(f'checkConfigOptions: [{sect}][{key}] = {config[sect][key]}')
	return

# -----------------------------------------------------------------------------
def gettime():
	now = datetime.datetime.now()
	timeString = now.strftime("%Y-%m-%d  %H:%M:%S") # Note: formatting differs
	seconds = int(now.strftime("%S"))               # from that in the 'ts()'
	return(timeString,seconds)                      # function  

# -----------------------------------------------------------------------------
def centreString(s,d):
	if len(s) >= d:
		s = s[0:d]
	else:
		while len(s) < d:
			s = ' ' +s
			if len(s) < d:
				s += ' '
	return(s)

# -----------------------------------------------------------------------------
def showTime():
	global prevSec
	(tStr,sec) = gettime()
	if sec != prevSec:
		lcd_string(tStr,LCD_LINE_1)
		prevSec = sec
	return

# ---------------------------------------------------------------------------------------
def getIP():
	ipaddr = subprocess.check_output(["hostname","-I"])
	m = re.match(r'(\d+\.\d+\.\d+\.\d+)',ipaddr.decode())
	if m != None:
		ipaddr = m.group(1)
	else:
		ipaddr = "0.0.0.0"
	return(ipaddr)

# -----------------------------------------------------------------------------
def showIP(oldIP):
	ip = getIP()
	if ip != oldIP:
		debug(f"showIP: IP number changed. Old: {oldIP} new: {ip}")
	lcd_string(centreString(f"IP: {ip}",20),LCD_LINE_2)
	return (ip)

# -----------------------------------------------------------------------------
def showRoomAndSN(config):
	roomno = config['main']['room no']
	if len(roomno) > 10:
		roomno = roomno[0:10]
	sn = config['main']['serial number']
	if len(sn) > 10:
		sn = sn[0:10]
	lcd_string(f"{roomno:<10}{sn:>10}",LCD_LINE_3)
	return

# -----------------------------------------------------------------------------
def showUPSstatus(fl):
	if not os.path.isfile(fl):
		debug(f"showUPSstatus: {fl} does not exist, so nothing to do.")
		return
	with open(fl,'r') as f:
		lines = f.readlines()
		f.close()
	if not len(lines) == 2:
		debug(f"showUPSstatus: {fl} has {len(lines)} lines; 2 expected.")
		return
	lcd_string(lines[0],LCD_LINE_2)
	lcd_string(lines[1],LCD_LINE_3)
	return

# -----------------------------------------------------------------------------
def getVolume(flnm):
	with open (flnm,'r') as f:
		v = f.readline().strip()
		f.close()
	debug(f'getVolume: Value from {flnm}: {v}')
	return(v)

# -----------------------------------------------------------------------------
def showGasVolume(flnm,oldVolume):
	volume = getVolume(flnm)
	if volume != oldVolume:
		lcd_string(f"{float(volume):14.2f}x m\0  ",LCD_LINE_4)
	return (volume)

# -----------------------------------------------------------------------------
def getFileTime(flnm):
	ft = os.path.getmtime(flnm)
	return(ft)

# -----------------------------------------------------------------------------
def mjd():
	MJD = int(time.time()/86400) + 40587
	debug(f"mjd: Today's MJD: {MJD}")
	return(MJD)

# -----------------------------------------------------------------------------
def getUPSdisplayFilename(config):
	fl = ""
	if config.has_option('main','ups config file'):
		upsconfigfile = config['main']['ups config file']
		if not upsconfigfile.startswith('/'):
			upsconfigfile = HOME + upsconfigfile
		debug(f"getUPSdisplayFilename: UPS config file is {upsconfigfile}")
		upsconfig = configparser.ConfigParser()
		upsconfig.read(upsconfigfile)
		if upsconfig.has_option('status','path'):
			pth = upsconfig['status']['path']
			if not pth.startswith('/'):
				pth = HOME + pth
				if not pth.endswith('/'):
					pth += '/'
				if upsconfig.has_option('status','display file'):
					fl = pth + upsconfig['status']['display file']
					debug(f"getUPSdisplayFilename: File name is {fl}")
	else:
		debug("getUPSdisplayFilename: No entry for '[main] ups config file'")
	return(fl)

# -----------------------------------------------------------------------------
def getUPSoptions(config):
	ups_installed = False
	ups_present = config['main']['ups installed']
	if ups_present == '1' or ups_present.upper() == 'TRUE':
		ups_installed = True
	debug(f"getUPSoptions: Configured value for UPS installed: {ups_installed}")
	ups_fl = ""
	if ups_installed:
		ups_fl = getUPSdisplayFilename(config)
	debug(f"getUPSoptions: Configured UPS filename: {ups_fl}")
	if ups_fl == "":
		ups_installed = False
	update_interval = 10
	if config.has_option('main','rotate display'):
		try:
			s = config['main']['rotate display']
			update_interval = int(s)
		except:
			errorExit("getUPSoptions: Invalid value configured for update "+
						 f"interval: {s}. The value must be an integer between 5 and 60 "+
						 "(seconds).")
		debug(f"getUPSoptions: configured update interval: {update_interval} s")
		if update_interval < 5 or update_interval > 60:
			debug("getUPSoptions: Valid update intervals are between 5 and 60 "+
				 f"seconds. The configured value ({update_interval} s) falls outside "+
				 "these limits. The value will be set to the default (10 s).")
			update_interval = 10
	return(ups_installed,ups_fl,update_interval)

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

parser = argparse.ArgumentParser(description="Show the volume that has run "+
																 "through a gasmeter.")
parser.add_argument('-d','--debug',action="store_true",help="Turn debugging "+
										"on")
parser.add_argument('-v','--version',action='version', version = versionStr)
parser.add_argument('-c',nargs = 1,help = 'Specify alternative configuration '+
										'file (full path). Default is ~/etc/gasmeter.conf')

args = parser.parse_args()

if args.debug:
	DEBUG = True

debug(versionStr)

HOME = addSlashToPath(os.environ['HOME'])
debug(f"Current user's HOME: {HOME}")

configfile = f'{HOME}etc/gasmeter.conf'
if args.c:
	configfile = args.c[0]
debug(f'Configuration file: {configfile}')

if not os.path.isfile(configfile):
	errorExit(f'Configuration file does not exist: {configfile}')

config = configparser.ConfigParser()
config.read(configfile)

# Make sure required values are in the configuration file
checkConfigOptions(config,['main,room no','main,serial number',
													 'main,meter reading file','main,lock file'],
													 configfile)

debug(f"Configured room number: {config['main']['room no']}")
debug(f"Configured meter serial number: {config['main']['serial number']}")

readingflnm = createAbsFilename(config['main']['meter reading file'],HOME)
debug(f"Configured meter reading file: {readingflnm}")

lockfile = HOME + config['main']['lock file']
debug(f"Configured lock file: {lockfile}")

ups = False
ups_flnm = ""
ups_update = 10

if config.has_option('main','ups installed'):
	ups,ups_flnm,ups_update = getUPSoptions(config)

debug(f"UPS installed: {ups}")
if ups:
	debug(f"UPS messages file: {ups_flnm}")
	debug(f"UPS messages update rate: {ups_update} seconds")

if (not createProcessLock(lockfile)):
        errorExit ("Couldn't create a process lock. Process already running?")

setupLCD()
lcd_init()
lcd_create_char(0,cubicChar)

# Clear display
lcd_byte(0x01, LCD_CMD)

oldIP = "0.0.0.0"
oldIP = showIP(oldIP)
showRoomAndSN(config)
oldVolume = showGasVolume(readingflnm,'')
oldft = os.path.getmtime(readingflnm)

signal.signal(signal.SIGINT, sigHandler)
signal.signal(signal.SIGTERM, sigHandler)

prevSec = -1
running = True
count = 0
CHECK_TIME = 3600 # seconds
ups_time = time.time()
ups_cycle = False

while running:
	# Update the time regularly
	showTime()
	time.sleep(0.2)
	# Check the meter reading regularly
	ft = os.path.getmtime(readingflnm)
	if ft != oldft:
		debug(f'Volume has been updated! Old vol: {oldVolume}')
		oldVolume = showGasVolume(readingflnm,oldVolume)
		debug(f'Volume has been updated! New vol: {oldVolume}')
		oldft = ft
	
	# Note: The volume is saved to file at least once an hour. This is 
	# done by the countpulses software updating the file date of that
	# file at least once an hour.
	
	if ups:
		if time.time() > ups_time:
			if ups_cycle:
				debug("Showing UPS status")
				showUPSstatus(ups_flnm)
			else:
				debug("Showing IP address and room and serial numbers")
				oldIP = showIP(oldIP)
				showRoomAndSN(config)
			ups_cycle = not ups_cycle
			ups_time += ups_update
	else:
		# Check IP approximately every hour
		if count >= 5 * CHECK_TIME:
			ip = showIP(oldIP)
			debug(f'Checking IP! count: {count}, oldIP: {oldIP}, ip: {ip}')
			count = -1
		count += 1

# Clear display
lcd_byte(0x01, LCD_CMD)

GPIO.cleanup()

removeProcessLock(lockfile)

if DEBUG:
	print('\n')
debug(f'{script} done')
