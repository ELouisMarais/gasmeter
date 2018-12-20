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

import sys
import time
from socket import *
import re
import subprocess
import os
import configparser
import signal

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
			print('['+sect+']['+key+'] missing from',configfile+'!')
			quit()
		# For debugging - keep, may be useful later
		#else:
		#	print('['+sect+']['+key+'] exists.')

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
	# timestamp
	msg = str(time.time())+"\t"
	# name
	msg += name+"\t"
	# measurements
	for i in range(len(files)):
		if not(os.path.isfile(files[i])):
			msg += "-999.9"
		elif(os.stat(files[i]).st_size == 0):
			msg += "-999.9"
		else:
			with open(files[i]) as f:
				val = f.readline()
			f.close()
			msg += val.strip()
		if i < (len(files) - 1):
			msg += ','
	return msg

# -----------------------------------------------------------------------------

def sendMessage(msg):
	BC_PORT = 12345
	s = socket(AF_INET,SOCK_DGRAM)
	s.bind(('',0))
	s.setsockopt(SOL_SOCKET,SO_BROADCAST,1)
	b = bytes(msg,'utf8')
	s.sendto(b,('<broadcast>',BC_PORT))
	return

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

HOME = addSlashToPath(os.environ['HOME'])

configfile = HOME + 'etc/broadcast.conf'

if not(os.path.isfile(configfile)):
	print(configfile,"does not exist.");
	quit()

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
	filenames.append(path+target)
	modtime = getFileModificationTime(filenames[-1])
	filemodtimes.append(modtime)

checkConfigOptions(config,targetcheck)

lockfile = path + config['main']['lockfile']

if (not createProcessLock(lockfile)):
	print ("Couldn't create a process lock.")
	quit()

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
quit()
