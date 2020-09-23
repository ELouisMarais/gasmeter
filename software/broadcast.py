#!/usr/bin/python3
# broadcast.py

# Broadcast a network message to own network
# to be picked up by a server that will process it according to its own desires
#
# Message structure is strictly according to the one stated here, and fields 
# are TAB delimited.
# Values for the fields are read from a config file.
#
# Field            Description
# ~~~~~~~~~~~~~  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Sender name    Free field, for example ENVLOGGER GASMETER_G200_1 RASPI_01 or 
#                whatever. The message reader application (recvmsg.py) acts on
#                the message depending on its sender name. The reader 
#                application has a config file that tells it what to do.
# Parameters     First parameter, ... , last parameter

# Louis Marais
# Version 1.0
# Start data: 2018-09-18
# Last modification: 2018-12-12

# Louis Marais
# Version 2.0
# Start: 2020-09-23
# Last modification: 2020-09-23
#
# Modifications:
# ~~~~~~~~~~~~~~
# 1. Added debugging capability
# 2. Added some command line switches
# 3. Added errorExit routine
# 4. fixed old bug in code where the file being checked was path/target
#    instead of path/[target][file]
#
#
#

import sys
import time
from socket import *
import re
import subprocess
import os
import configparser
import signal
import datetime
import argparse

script = os.path.basename(__file__)
VERSION = "2.0"
AUTHORS = "Louis Marais"

DEBUG = False

# -----------------------------------------------------------------------------

def ts():
	now = datetime.datetime.now()
	tsStr = now.strftime('%Y-%m-%d %H:%M:%S ')
	return(tsStr)

# -----------------------------------------------------------------------------

def debug(msg):
	if DEBUG:
		print(ts(),msg)
	return

# -----------------------------------------------------------------------------

def errorExit(s):
	print('ERROR: '+s)
	sys.exit(1)

# -----------------------------------------------------------------------------

def sigHandler(sig,frame):
	global running
	running = False
	return

# -----------------------------------------------------------------------------

# No longer used - I decided not to send the IP to the reader application.
# Keep for future use / historical interest.
# I also discovered that the IP address is sent with the broadcast message 
# anyway - rather logical because the receiver will need to know who bradcast
# the message... Am I an idiot or what?
def getIP():
	ipaddr = subprocess.check_output(["hostname","-I"])
	# For BBB 'hostname -I' returns: b'10.149.169.21 192.168.7.2 192.168.6.2 \n'
	# We want to get the first address. The other two are for the USB network devices
	m = re.match(r'(\d+\.\d+\.\d+\.\d+)',ipaddr.decode())
	if m != None:
		ipaddr = m.group(1)
	else:
		ipaddr = "0.0.0.0"
	return ipaddr

# -----------------------------------------------------------------------------

def addSlashToPath(path):
	path = re.sub(r'/$','',path) # strip off last '/' if any, then add it
	path = path+'/'              # so we can be sure the path is correct
	return path

# -----------------------------------------------------------------------------

def checkConfigOption(config,section,key):
	if config.has_option(section,key):
		return True
	else:
		return False

# -----------------------------------------------------------------------------

def checkConfigOptions(config,sectkeys):
	for pair in sectkeys:
		sectkey = pair.split(",")
		sect = sectkey[0]
		key = sectkey[1]
		if not(checkConfigOption(config,sect,key)):
			errorExit('['+sect+']['+key+'] missing from '+configfile+'!')
		else:
			debug('['+sect+']['+key+'] = '+config[sect][key])

# -----------------------------------------------------------------------------

def getFileModificationTime(filename):
	ts = 0
	if os.path.isfile(filename):
		ts = os.path.getmtime(filename)
	return ts

# -----------------------------------------------------------------------------
# adapted from ottplib.py, so that this can be used with kickstart.pl
def createProcessLock(lockfile):
	if not(testProcessLock(lockfile)):
		return False
	flock = open(lockfile,'w')
	flock.write(os.path.basename(sys.argv[0])+' '+str(os.getpid()))
	return True

# -----------------------------------------------------------------------------
# adapted from ottplib.py, so that this can be used with kickstart.pl
def removeProcessLock(lockfile):
	if(os.path.isfile(lockfile)):
		os.unlink(lockfile)

# -----------------------------------------------------------------------------
# adapted from ottplib.py, so that this can be used with kickstart.pl
def testProcessLock(lockfile):
	if(os.path.isfile(lockfile)):
		flock = open(lockfile,'r')
		info = flock.readline().split()
		if(len(info) == 2):
			if(os.path.exists('/proc/'+str(info[1]))):
				return False
	return True

# -----------------------------------------------------------------------------

def makeMessage(name,files):
	debug("Name: "+name)
	debug("Files: "+str(files))
	# timestamp
	msg = str(time.time())+"\t"
	# name
	msg += name+"\t"
	# measurements
	for i in range(len(files)):
		if not(os.path.isfile(files[i])):
			msg += "-999.9"
			debug("File does not exist: "+files[i])
		elif(os.stat(files[i]).st_size == 0):
			msg += "-999.9"
			debug("File size is zero: "+files[i])
		else:
			with open(files[i]) as f:
				val = f.readline()
			f.close()
			debug("Value read from file: "+val.strip())
			msg += val.strip()
		if i < (len(files) - 1):
			msg += ','
	debug("Message constructed: "+msg)
	return msg

# -----------------------------------------------------------------------------

def sendMessage(msg):
	BC_PORT = 12345
	s = socket(AF_INET,SOCK_DGRAM)
	s.bind(('',0))
	s.setsockopt(SOL_SOCKET,SO_BROADCAST,1)
	b = bytes(msg,'utf8')
	s.sendto(b,('<broadcast>',BC_PORT))
	debug("Broadcast message sent to port: "+str(BC_PORT))
	return

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

parser = argparse.ArgumentParser("Network measurement value broadcaster")
parser.add_argument("-v","--version",action="store_true",help="Show version "+
										"and exit.")
parser.add_argument("-c","--config",nargs=1,help="Specify alternative "+
										"configuration file. The default is "+
										"~/etc/broadcast.conf.")
parser.add_argument("-d","--debug",action="store_true",help="Turn debugging on")

args = parser.parse_args()

if args.debug:
	DEBUG = True

versionStr = script+" version "+VERSION+" written by "+AUTHORS

if args.version:
	print(versionStr)
	sys.exit(0)

debug(versionStr)

HOME = os.path.expanduser('~')
if not HOME.endswith('/'):
	HOME +='/'

debug("Current user's home: "+HOME)

configfile = HOME+"etc/broadcast.conf"

if args.config:
	debug("Alternate config file specified: "+str(args.config[0]))
	configfile = str(args.config[0])
	if not configfile.startswith('/'):
		configfile = HOME+configfile

debug("Configuration file: "+configfile)

if not os.path.isfile(configfile):
	errorExit(configfile+' does not exist.')

config = configparser.ConfigParser()
config.read(configfile)

# Make sure required values are in the configuration file
checkConfigOptions(config,['main,name','main,targets','main,path','main,lockfile'])

name = config['main']['name']
targetlist = config['main']['targets']
path = addSlashToPath(config['main']['path'])
if not(re.match(r'^/',path)):
	path = HOME+path

# Make sure each of the targets has a section in the configuration file
targetcheck = []
filenames = []
filemodtimes = []
parameters = targetlist.split(',')

for target in parameters:
	targetcheck.append(target+',file')

checkConfigOptions(config,targetcheck)

for target in parameters:
	filenames.append(path+config[target]["file"])
	modtime = getFileModificationTime(filenames[-1])
	filemodtimes.append(modtime)


lockfile = path + config['main']['lockfile']

if (not createProcessLock(lockfile)):
	errorExit ("Couldn't create a process lock. Process already running?")

signal.signal(signal.SIGINT, sigHandler)
signal.signal(signal.SIGTERM, sigHandler)

running = True
first = True

while(running):
	filemod = False
	while not(filemod) and running:
		if(first):
			first = False
			filemod = True
		for i in range(len(filenames)):
			modtime = getFileModificationTime(filenames[i])
			if modtime != filemodtimes[i]:
				filemod = True
				filemodtimes[i] = modtime
		if not(filemod):
			time.sleep(1)
	if running:
		msg = makeMessage(name,filenames)
		# Send message 3 times, 100 ms apart (UDP is used, so delivery is
		# not guarenteed)
		for i in range (0,3):
			sendMessage(msg)
			time.sleep(0.1)

removeProcessLock(lockfile)

print(script,"done.")
