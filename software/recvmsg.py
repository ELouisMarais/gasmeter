#!/usr/bin/python3
# recvmsg.py

# This reads broadcast messages on the netowrk and stores the parameters
# in complaint messages on the local machine.
#
# It does this by performing the following steps:
#  1. Receive a message broadcast on the network
#  2. Parse the message and if it conforms to the expected format check the 
#     message name against the names in the configuration file.
#  3. If it is a message with valid name the data in the message is stored
#     in the configured location.
#
# Message structure
# {name}\t{data}
#
# Configuration file: ~/etc/recvmsg.conf
#

# Louis Marais
# Version 1.0
# Start data: 2018-12-12
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
#
#
#

import os
import re
import configparser
import socket
import sys
import signal
import time
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
			debug('['+sect+']['+key+'] missing from '+configfile+'!')
		else:
			debug('['+sect+']['+key+'] = '+config[sect][key])
		return

# -----------------------------------------------------------------------------

def getFileModificationTime(filename):
	tmsmp = 0
	if os.path.isfile(filename):
		tmsmp = os.path.getmtime(filename)
	return tmsmp

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

def createFile(sectionname,tmsmp,datapath,dataext):
	filetype = 'MJD'
	if config.has_option(sectionname,'file type'):
		debug("config has option ["+sectionname+"][file type] = "+config[sectionname]["file type"])
		filetype = config[sectionname]['file type']
	if filetype == "YYYY-MM":
		fl = datetime.datetime.fromtimestamp(int(tmsmp)).strftime('%Y-%m')
	elif filetype == "YYYYMM":
		fl = datetime.datetime.fromtimestamp(int(tmsmp)).strftime('%Y%m')
	elif filetype == "YYYY":
		fl = datetime.datetime.fromtimestamp(int(tmsmp)).strftime('%Y')
	else:
		mjd = int(tmsmp/86400) + 40587
		fl = str(mjd)
	debug("filetype: "+filetype+" fl: "+fl)
	flnm = datapath+fl+'.'+dataext
	debug("data file name: "+flnm)
	return flnm

# -----------------------------------------------------------------------------

def processData(parameters,tmsmp,name,data):
	# extract name and data from msg, check against config and store
	debug("Processing message, time stamp "+str(tmsmp))
	debug("Processing message, name: "+name)
	debug("Processing message, data: "+data)
	debug("Processing message, parameters: "+str(parameters))
	i = 0
	while config[parameters[i]]['name'] != name:
		i += 1
		if i >= len(parameters):
			print("parameters[i]['name'] not found! We were looking for name ==",
				 name+"\nFix up the configurations! Note that local and remote",
				 "names must match.")
			return
	debug("Our section is "+str(i)+" with section name "+parameters[i])
	header = config[parameters[i]]['data']
	datapath = config[parameters[i]]['path']
	datapath = addSlashToPath(datapath)
	if not(re.match(r'^/',datapath)):
		datapath = HOME+datapath
	if not(os.path.isdir(datapath)):
		print("The datapath ("+datapath+") for name =",name,"does not exist.")
		return
	dataext = config[parameters[i]]['file extension']
	debug("header: "+header)
	debug("datapath: "+datapath)
	debug("data ext: "+dataext)
	flnm = createFile(parameters[i],float(tmsmp),datapath,dataext)
	debug("File name: "+flnm)
	if not(os.path.isfile(flnm)):
		f = open(flnm,'w')
		f.write('Timestamp\t'+header+'\n')
		f.close()
	tsStr = "%0.6f" % (float(tmsmp)/86400 + 40587)
	debug("tmsmp: "+str(tmsmp)+" tsStr: "+tsStr)
	f = open(flnm,'a')
	f.write(tsStr+'\t'+data+'\n')
	f.close()
	return

# -----------------------------------------------------------------------------

def writeAddr(flnm,addr):
	f = open(flnm,'w')
	f.write(addr)
	f.close()
	return

# -----------------------------------------------------------------------------
#   Main
# -----------------------------------------------------------------------------

parser = argparse.ArgumentParser("Network measurement value receiver")
parser.add_argument("-v","--version",action="store_true",help="Show version "+
										"and exit.")
parser.add_argument("-c","--config",nargs=1,help="Specify alternative "+
										"configuration file. The default is "+
										"~/etc/recvmsg.conf.")
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

configfile = HOME+"etc/recvmsg.conf"

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
checkConfigOptions(config,['main,targets','main,lockfile','main,lock path'])

targetlist = config['main']['targets']
lockpath = addSlashToPath(config['main']['lock path'])
if not(re.match(r'^/',lockpath)):
	lockpath = HOME+lockpath

# Make sure each of the targets has a section in the configuration file
msgnames = []
msgdata = []
msgpaths = []
msgfileexts = []
msgfiletypes = []
parameters = targetlist.split(',')

for name in parameters:
	msgnames.append(name+',name')
	msgdata.append(name+',data')
	msgpaths.append(name+',path')
	msgfileexts.append(name+',file extension')
	#msgfiletypes.append(name+',file type') # this optional option is not checked

checklist = msgnames + msgdata + msgpaths + msgfileexts + msgfiletypes

debug("names: "+str(msgnames))
debug("data: "+str(msgdata))
debug("paths: "+str(msgpaths))
debug("file ext: "+str(msgfileexts))
debug("checklist: "+str(checklist))

checkConfigOptions(config,checklist)

lockfile = lockpath + config['main']['lockfile']

if (not createProcessLock(lockfile)):
	errorExit ("Couldn't create a process lock. Process already running?")

signal.signal(signal.SIGINT, sigHandler)
signal.signal(signal.SIGTERM, sigHandler)

running = True

RCV_PORT = 12345
s = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
s.bind(('',RCV_PORT))
s.setblocking(0) # For non-blocking access
m = ''
addr = ''
data = ""
rcvtime = ""
while running:
	try:
		time.sleep(0.05)
		m,a = s.recvfrom(1024)
	except socket.error as err:
		pass
	else:
		addr = a[0]
		data = m.decode()
		debug("addr: "+addr)
		debug("data: "+m.decode())
		dataparts = data.split('\t')
		if(len(dataparts) == 3):
			tmsmp = dataparts[0]
			name = dataparts[1]
			measurements = dataparts[2]
			debug("time: "+tmsmp)
			debug("name: "+name)
			debug("meas: "+measurements)
			if(rcvtime != tmsmp):
				debug("Unique message received. Processing.")
				processData(parameters,tmsmp,name,measurements)
				rcvtime = tmsmp
				# Check address
				debug("Checking address")
				flnm = '/tmp/'+name+'.addr'
				if os.path.isfile(flnm):
					f = open(flnm,'r')
					chkaddr = f.readline().strip()
					f.close()
					debug("   addr: "+addr)
					debug("chkaddr: "+chkaddr)
					if addr != chkaddr:
						debug("Addresses do not match, overwriting wrong address")
						writeAddr(flnm,addr)
				else:
					debug("Creating address file")
					writeAddr(flnm,addr)
			else:
				debug("Message with duplicate timestamp received.")

removeProcessLock(lockfile)

print(script,"done.")
