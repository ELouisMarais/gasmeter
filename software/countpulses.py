#!/usr/bin/python3
# countpulses.py

# Count pulsed as they arrive on an GPIO pis. This replaces the C language
# program 'countpulses' that relies on the deprecated WiringPi library. Its
# author got fed up with people using his work and not appropriately 
# crediting it, which I can understand. Read more on his website:
# http://wiringpi.com/news/
#
# I also wanted to move away from using the C language, and Python seemed
# ideal.
#
# Based on count3pulses.py developed for the three gasmeters that represent
# the return gas meter for gas coming back to Cryogenics from laboratories.
#
# Comments from countpulses.c:
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #
# To count and store pulses coming from the gasmeter                        #
#                                                                           #
# Louis Marais, 2016-07-08                                                  #
# version 0.1 finished 2016-07-14                                           #
#                                                                           #
# version 0.2 started 2016-10-18                                            # 
#                                                                           #
# Modifications:                                                            #
#                                                                           #
# Found issue with float not having enough precision (volume variable)      #
# Made it a double, this fixed it.                                          #
#                                                                           #
# Last modified on 2016-10-18                                               # 
#                                                                           #
# Modified 2018-12-14:                                                      #
# 'meterreading' file must get "touched" at least every hour. This is       #
# required because the broadcast.py software looks for a change in the file #
# modification date.                                                        # 
#                                                                           #
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #
#
# -----------------------------------------------------------------------------
#
# Version 1.0
# Author(s): Louis Marais
# Start date: 2021-07-01
# Last modification: 2021-07-02
#
# -----------------------------------------------------------------------------
#
# Version (Next)
# Author(s): 
# Start date: 
# Last modification: 
#
# Modifications:
# --------------
#
# -----------------------------------------------------------------------------
#

import RPi.GPIO as GPIO
import datetime
import argparse
import configparser
import os
import sys
import signal
import time
import subprocess

GPIO.setmode(GPIO.BCM)

script = os.path.basename(__file__)
AUTHORS = "Louis Marais"
VERSION = "1.0"

DEBUG = False

versionStr = script+" version "+VERSION+" written by "+AUTHORS

# -----------------------------------------------------------------------------
# Sub routines
# -----------------------------------------------------------------------------

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
	print('ERROR: '+s)
	sys.exit(1)

# -----------------------------------------------------------------------------
def sigHandler(sig,frame):
	global running
	running = False
	return

# -----------------------------------------------------------------------------
# adapted from ottplib.py, so that this can be used with kickstart.pl
def createProcessLock(lockfile):
	if not(testProcessLock(lockfile)):
		return False
	flock = open(lockfile,'w')
	flock.write(os.path.basename(sys.argv[0])+' '+str(os.getpid()))
	flock.close()
	debug('Created process lock file: {}'.format(lockfile))
	return True

# -----------------------------------------------------------------------------
# adapted from ottplib.py, so that this can be used with kickstart.pl
def removeProcessLock(lockfile):
	if(os.path.isfile(lockfile)):
		os.unlink(lockfile)
	debug('Removed process lock file: {}'.format(lockfile))
	return

# -----------------------------------------------------------------------------
# adapted from ottplib.py, so that this can be used with kickstart.pl
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
	debug('Checking configuration file: {}'.format(configfile))
	for pair in sectkeys:
		sectkey = pair.split(",")
		sect = sectkey[0].strip()
		key = sectkey[1].strip()
		if not(checkConfigOption(config,sect,key)):
			errorExit('['+sect+']['+key+'] missing from '+configfile+'!')
		else:
			debug('[{}][{}] = {}'.format(sect,key,config[sect][key]))
	return

# -----------------------------------------------------------------------------
def checkPath(p):
	debug('Checking if path {} exists.'.format(p))
	if not os.path.isdir(p):
		debug('Trying to create apth: {}'.format(p))
		os.mkdir(p)
		if not os.path.isdir(p):
			errorExit('The path {} does not exist and could not be created.'.format(p))
	return

# -----------------------------------------------------------------------------
def getMeterReading(flnm):
	debug('Getting meter reading from file: '+flnm)
	reading = 0.00
	if os.path.isfile(flnm):
		with open(flnm,'r') as f:
			s = f.readline().strip()
			f.close()
			debug("reading: "+s)
			try:
				reading = float(s)
			except:
				errorExit('The file ('+flnm+') does not contain a valid value: '+s)
	else: # try to create file and put '0.00' in it
		try:
			f = open(flnm,'w')
			f.writelines('0.00')
			f.close()
		except:
			errorExit('Could not create file '+flnm)
	return(reading)


# -----------------------------------------------------------------------------
"""
def my_callback(channel):
	global newmeter1, newmeter2, newmeter3
	debug("Rising edge detected on "+str(channel))
	if channel == 5:
		newmeter1 += 0.01
	if channel == 6:
		newmeter2 += 0.01  # Damn! was 0.1, fixed 2020-09-22
	if channel == 16:
		newmeter3 += 0.01
	return
"""

def my_callback(channel):
	global newmeters
	debug("Rising edge detected on "+str(channel))
	for i in range (0,len(newmeters)):
		if channel == inputs[i]:
			newmeters[i] += volperpulse[i]
	return

# -----------------------------------------------------------------------------
def writeValues(v,flnm,fpath,fileformat):
	debug('Writing value ({:0.2f}) to file: {}'.format(v,flnm))
	with open (flnm,'w') as f:
		f.write("{:0.2f}".format(v))
		f.close()
	writeToDataFile(v,fpath,fileformat)
	return

# -----------------------------------------------------------------------------
def mjd():
	MJD = int(time.time()/86400) + 40587
	debug("Today's MJD: {}".format(MJD))
	return(MJD)

# -----------------------------------------------------------------------------
def writeToDataFile(v,fpath,fileformat):
	debug('writing "{:.2f}" to path "{}" with file format "{}"'.format(v,fpath,fileformat))
	now = datetime.datetime.now()
	if fileformat == 'YYYY':
		flnm = fpath+now.strftime("%Y")+".dat"
	elif fileformat == 'YYYY-MM':
		flnm = fpath+now.strftime("%Y-%m")+".dat"
	else:
		flnm = fpath+str(mjd())+".dat"
	s = now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]+" {:0.3f}\n".format(v)
	debug("Writing {:0.2f} to {}: {}".format(v,flnm,s.strip()))
	with open(flnm,"a") as f:
		f.write(s)
		f.close()
	return

# -----------------------------------------------------------------------------
def getTotal():
	v = 0
	for m in meters:
		v += m
	return(v)

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

parser = argparse.ArgumentParser("Reads one or more gasmeters, logs the readings "+
																 "displays it on an LCD.")
parser.add_argument('-v','--version',action='version', version = versionStr)
parser.add_argument("-c","--config",nargs=1,help="Specify alternative "+
										"configuration file. The default is "+
										"~/etc/gasmeter.conf.")
parser.add_argument("-d","--debug",action="store_true",help="Turn debugging on")

args = parser.parse_args()

debug(versionStr)

if args.debug:
	DEBUG = True

HOME = os.path.expanduser('~')
if not HOME.endswith('/'):
	HOME +='/'

debug("Current user's home :"+HOME)

configfile = HOME+"etc/gasmeter.conf"

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
checkConfigOptions(config,['main,meter reading file','gasmeters,targets',
													 'gasmeters,meter reading path',
													 'gasmeters,lock file'], configfile)

targets = config['gasmeters']['targets'].split(',')

meterreadingpath = createAbsPath(config['gasmeters']['meter reading path'],HOME)

debug('The following targets were found: {}'.format(str(targets)))

for target in targets:
	checkConfigOptions(config,[target+',input',target+',volume per pulse',
														target+',data path',target+',file format'],
														configfile)

if len(targets) > 1:
	checkConfigOptions(config,['combined,data path','combined,file format'],
										configfile)

lockfile = createAbsFilename(config['gasmeters']['lock file'],HOME)

if not createProcessLock(lockfile):
	errorExit('Unable to lock - '+script+' already running?')

inputs = []
volperpulse = []
meterpaths = []
fileformats = []
meterfiles = []
meters = []

for target in targets:
	inputs.append(int(config[target.strip()]['input']))
	volperpulse.append(float(config[target.strip()]['volume per pulse']))
	debug('Setting pin {} as an input.'.format(inputs[-1]))
	GPIO.setup(inputs[-1], GPIO.IN)
	meterfiles.append(createAbsFilename(target.strip(),meterreadingpath))
	meters.append(getMeterReading(meterfiles[-1]))
	meterpaths.append(createAbsPath(config[target.strip()]['data path'],HOME))
	checkPath(meterpaths[-1])
	fileformats.append(config[target.strip()]['file format'])

if len(targets) > 1:
	totalfile = createAbsFilename(config['main']['meter reading file'],HOME)
	totalpath = createAbsPath(config['combined']['data path'],HOME)
	totalfileformat = config['combined']['file format']
	debug('Total of gasmeter(s) reading(s) file created: {}'.format(totalfile))
	debug ('total from multiple meters ({})'.format(str(meters)))
	total = 0
	for meter in meters:
		total += meter
	debug('Total gasmeter(s) reading: {:.2f}'.format(total))

newmeters = []
lastwritetimes = []

for i in range(0,len(meters)):
	newmeters.append(meters[i])
	lastwritetimes.append(time.time())

signal.signal(signal.SIGINT, sigHandler)
signal.signal(signal.SIGTERM, sigHandler)

for i in range(0,len(inputs)):
	GPIO.add_event_detect(inputs[i],GPIO.RISING, callback = my_callback,bouncetime = 100)
	debug('Added a GPIO event for input {}'.format(inputs[i]))

running = True

debug('Values in "newmeters": {}'.format(str(newmeters)))
debug('Last write times: {}'.format(str(lastwritetimes)))

while running:
	time.sleep(0.1) # otherwise it runs at 100% CPU!
	for i in range(0,len(meters)):
		if newmeters[i] != meters[i]:
			meters[i] = newmeters[i]
			writeValues(newmeters[i],meterfiles[i],meterpaths[i],fileformats[i])
			if len(meters) > 1: # For a single meter, do not double write!
				total = getTotal()
				writeValues(total,totalfile,totalpath,totalfileformat)
			lastwritetimes[i] = time.time()
		if (lastwritetimes[i] + 3600) < time.time():  # 3600
			writeValues(meters[i],meterfiles[i],meterpaths[i],fileformats[i])
			if len(meters) > 1: # For a single meter, do not double write!
				writeValues(total,totalfile,totalpath,totalfileformat)
			lastwritetimes[i] = time.time()

GPIO.cleanup()

removeProcessLock(lockfile)

debug('{} {} terminated.'.format(ts(),script))

