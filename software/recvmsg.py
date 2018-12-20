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

import os
import re
import configparser
import socket
import sys
import signal
import time
import datetime

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
			print('['+sect+']['+key+'] missing from',configfile+'!')
			quit()
		# For debugging - keep, may be useful later
		#else:
		#	print('['+sect+']['+key+'] exists.')
		return

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

def createFile(sectionname,ts,datapath,dataext):
	filetype = 'MJD'
	if config.has_option(sectionname,'file type'):
		# For debugging
		#print("config has option ["+sectionname+"][file type]")
		filetype = config[sectionname]['file type']
	if filetype == "YYYY-MM":
		fl = datetime.datetime.fromtimestamp(int(ts)).strftime('%Y-%m')
	elif filetype == "YYYYMM":
		fl = datetime.datetime.fromtimestamp(int(ts)).strftime('%Y%m')
	elif filetype == "YYYY":
		fl = datetime.datetime.fromtimestamp(int(ts)).strftime('%Y')
	else:
		mjd = int(ts/86400) + 40587
		fl = str(mjd)
	# For debugging
	#print("filetype:",filetype,"fl:",fl)
	flnm = datapath+fl+'.'+dataext
	# For debugging
	#print("data file name:",flnm)
	return flnm

# -----------------------------------------------------------------------------

def processData(parameters,ts,name,data):
	# extract name and data from msg, check against config and store
	# For debugging
	#print("\n\nprocessing message...")
	#print("timestamp:",ts)
	#print("name:",name)
	#print("data:",data)
	#print (parameters)
	i = 0
	while config[parameters[i]]['name'] != name:
		i += 1
		if i >= len(parameters):
			print("parameters[i]['name'] not found! We were looking for name ==",
				 name+"\nFix up the configurations! Note that local and remote",
				 "names must match.")
			return
	# For debugging
	#print("Our section is",i,"with section name",parameters[i])
	header = config[parameters[i]]['data']
	datapath = config[parameters[i]]['path']
	datapath = addSlashToPath(datapath)
	if not(re.match(r'^/',datapath)):
		datapath = HOME+datapath
	if not(os.path.isdir(datapath)):
		print("The datapath ("+datapath+") for name =",name,"does not exist.")
		return
	dataext = config[parameters[i]]['file extension']
	# For debugging
	#print("header:",header)
	#print("datapath:",datapath)
	#print("data ext:",dataext)
	flnm = createFile(parameters[i],float(ts),datapath,dataext)
	if not(os.path.isfile(flnm)):
		f = open(flnm,'w')
		f.write('Timestamp\t'+header+'\n')
		f.close()
	tsStr = "%0.6f" % (float(ts)/86400 + 40587)
	# For debugging
	#print("ts:",ts,"tsStr:",tsStr)
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

HOME = addSlashToPath(os.environ['HOME'])

configfile = HOME + 'etc/recvmsg.conf'

if not(os.path.isfile(configfile)):
	print(configfile,"does not exist.");
	quit()

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

# For debugging
#print("names:",msgnames)
#print("data:",msgdata)
#print("paths:",msgpaths)
#print("file ext:",msgfileexts)
#print("checklist:",checklist)

checkConfigOptions(config,checklist)

lockfile = lockpath + config['main']['lockfile']

if (not createProcessLock(lockfile)):
	print ("Couldn't create a process lock.")
	quit()

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
		# For debugging
		#print("addr:",addr)
		#print("data:",m.decode())
		dataparts = data.split('\t')
		if(len(dataparts) == 3):
			ts = dataparts[0]
			name = dataparts[1]
			measurements = dataparts[2]
			# For debugging
			#print("time:",ts)
			#print("name:",name)
			#rint("meas:",measurements)
			if(rcvtime != ts):
				# For debugging
				#print("\nUnique message received. Processing.\n")
				processData(parameters,ts,name,measurements)
				rcvtime = ts
				# Check address
				# For debugging
				#print("Checking address")
				flnm = '/tmp/'+name+'.addr'
				if os.path.isfile(flnm):
					f = open(flnm,'r')
					chkaddr = f.readline().strip()
					f.close()
					# For debugging
					#print("   addr:",addr)
					#print("chkaddr:",chkaddr)
					if addr != chkaddr:
						# For debugging
						#print("Addresses do not match, overwriting wrong address")
						writeAddr(flnm,addr)
				else:
					# For debugging
					#print("Creating address file")
					writeAddr(flnm,addr)
	
removeProcessLock(lockfile)
