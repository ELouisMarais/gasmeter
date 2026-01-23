#!/usr/bin/python3
# waveshare_d_ups.py

# A script to manage the UPS function of a Raspberry Pi based gas meter.
# Modified from INA219.py by Louis Marais for use with Cryogenics Gasmeter
# application. This application is run as a service on a Raspberry Pi connected
# to the Waveshare UPS hat (D).
#
# The measurement device on the UPS hat is an INA219, see its specs here:
# https://www.ti.com/lit/ds/symlink/ina219.pdf
#
# The demo software for the UPS hat is available as a 7-zip file on the 
# Waveshare wiki site for the hat: https://www.waveshare.com/wiki/UPS_HAT_(D).
# There is a README file for the software but no license file or any mention
# of a license. The README file notes that the software could be an example for
# someone but I believe this refers to the PyQt5 GUI application.
#
# Given this I believe the code is in the public domain and by mentioning the
# wiki site above I have adequately acknowledged the original source. The code
# below is provided under the MIT license.

#
# The MIT License (MIT)
#
# Copyright (c) 2026 E. Louis Marais
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#

# -----------------------------------------------------------------------------
#
# Authors: Louis Marais (and unknown author(s) of INA219.py)
# Version: 0.1
# Start date: 2026-01-13
# Last modifications: 2026-01-23
#
# Initial version. Based very heavily on INA219.py. See 
# https://www.waveshare.com/wiki/UPS_HAT_(D).
#
# -----------------------------------------------------------------------------
#
# Authors:
# Version: {Next}
# Start date:
# Last modifications:
#
# Modifications:
# ~~~~~~~~~~~~~~
#
# -----------------------------------------------------------------------------

import os
import sys
import time
import argparse
import configparser
import subprocess
import pwd
import signal

try:
	import smbus
except ImportError:
	sys.exit("Missing module 'smbus'.\nInstall using: sudo apt install "+
		"python3-smbus.")

script = os.path.basename(__file__)
VERSION = "0.1"
AUTHORS = "Louis Marais"

DEBUG = False

# -----------------------------------------------------------------------------
# Class definitions for UPS power measurement device (INA219)
# -----------------------------------------------------------------------------

# Config Register (R/W)
_REG_CONFIG                 = 0x00
# SHUNT VOLTAGE REGISTER (R)
_REG_SHUNTVOLTAGE           = 0x01

# BUS VOLTAGE REGISTER (R)
_REG_BUSVOLTAGE             = 0x02

# POWER REGISTER (R)
_REG_POWER                  = 0x03

# CURRENT REGISTER (R)
_REG_CURRENT                = 0x04

# CALIBRATION REGISTER (R/W)
_REG_CALIBRATION            = 0x05

# -----------------------------------------------------------------------------
class BusVoltageRange:
	"""Constants for ``bus_voltage_range``"""
	RANGE_16V               = 0x00      # set bus voltage range to 16V
	RANGE_32V               = 0x01      # set bus voltage range to 32V (default)

# -----------------------------------------------------------------------------
class Gain:
	"""Constants for ``gain``"""
	DIV_1_40MV              = 0x00      # shunt prog. gain set to  1, 40 mV range
	DIV_2_80MV              = 0x01      # shunt prog. gain set to /2, 80 mV range
	DIV_4_160MV             = 0x02      # shunt prog. gain set to /4, 160 mV range
	DIV_8_320MV             = 0x03      # shunt prog. gain set to /8, 320 mV range

# -----------------------------------------------------------------------------
class ADCResolution:
	"""Constants for ``bus_adc_resolution`` or ``shunt_adc_resolution``"""
	ADCRES_9BIT_1S          = 0x00      #  9bit,   1 sample,     84us
	ADCRES_10BIT_1S         = 0x01      # 10bit,   1 sample,    148us
	ADCRES_11BIT_1S         = 0x02      # 11 bit,  1 sample,    276us
	ADCRES_12BIT_1S         = 0x03      # 12 bit,  1 sample,    532us
	ADCRES_12BIT_2S         = 0x09      # 12 bit,  2 samples,  1.06ms
	ADCRES_12BIT_4S         = 0x0A      # 12 bit,  4 samples,  2.13ms
	ADCRES_12BIT_8S         = 0x0B      # 12bit,   8 samples,  4.26ms
	ADCRES_12BIT_16S        = 0x0C      # 12bit,  16 samples,  8.51ms
	ADCRES_12BIT_32S        = 0x0D      # 12bit,  32 samples, 17.02ms
	ADCRES_12BIT_64S        = 0x0E      # 12bit,  64 samples, 34.05ms
	ADCRES_12BIT_128S       = 0x0F      # 12bit, 128 samples, 68.10ms

# -----------------------------------------------------------------------------
class Mode:
	"""Constants for ``mode``"""
	POWERDOW                = 0x00      # power down
	SVOLT_TRIGGERED         = 0x01      # shunt voltage triggered
	BVOLT_TRIGGERED         = 0x02      # bus voltage triggered
	SANDBVOLT_TRIGGERED     = 0x03      # shunt and bus voltage triggered
	ADCOFF                  = 0x04      # ADC off
	SVOLT_CONTINUOUS        = 0x05      # shunt voltage continuous
	BVOLT_CONTINUOUS        = 0x06      # bus voltage continuous
	SANDBVOLT_CONTINUOUS    = 0x07      # shunt and bus voltage continuous

# -----------------------------------------------------------------------------
# Functional class
# -----------------------------------------------------------------------------
class INA219:
	def __init__(self, i2c_bus=1, addr=0x40):
		self.bus = smbus.SMBus(i2c_bus);
		self.addr = addr
		
		# Set chip to known config values to start
		self._cal_value = 0
		self._current_lsb = 0
		self._power_lsb = 0
		self.set_calibration_16V_5A()

# -----------------------------------------------------------------------------
	def read(self,address):
		data = self.bus.read_i2c_block_data(self.addr, address, 2)
		return ((data[0] * 256 ) + data[1])

# -----------------------------------------------------------------------------
	def write(self,address,data):
		temp = [0,0]
		temp[1] = data & 0xFF
		temp[0] =(data & 0xFF00) >> 8
		self.bus.write_i2c_block_data(self.addr,address,temp)

# -----------------------------------------------------------------------------
	def set_calibration_16V_5A(self):
		"""Configures to INA219 to be able to measure up to 16V and 5A of current. Counter
		   overflow occurs at 16A.
		   ..note :: These calculations assume a 0.01 shunt ohm resistor is present
		"""
		# By default we use a pretty huge range for the input voltage,
		# which probably isn't the most appropriate choice for system
		# that don't use a lot of power.  But all of the calculations
		# are shown below if you want to change the settings.  You will
		# also need to change any relevant register settings, such as
		# setting the VBUS_MAX to 16V instead of 32V, etc.
		
		# VBUS_MAX = 16V             (Assumes 16V, can also be set to 32V)
		# VSHUNT_MAX = 0.08          (Assumes Gain 2, 80mV, can also be 0.32, 0.16, 0.04)
		# RSHUNT = 0.01               (Resistor value in ohms)
		
		# 1. Determine max possible current
		# MaxPossible_I = VSHUNT_MAX / RSHUNT
		# MaxPossible_I = 8.0A
		
		# 2. Determine max expected current
		# MaxExpected_I = 5.0A
		
		# 3. Calculate possible range of LSBs (Min = 15-bit, Max = 12-bit)
		# MinimumLSB = MaxExpected_I/32767
		# MinimumLSB = 0.0001529              (61uA per bit)
		# MaximumLSB = MaxExpected_I/4096
		# MaximumLSB = 0,0012207              (488uA per bit)
		
		# 4. Choose an LSB between the min and max values
		#    (Preferrably a roundish number close to MinLSB)
		# CurrentLSB = 0.00016 (uA per bit)
		self._current_lsb = 0.1524  # Current LSB = 100uA per bit
		
		# 5. Compute the calibration register
		# Cal = trunc (0.04096 / (Current_LSB * RSHUNT))
		# Cal = 13434 (0x347a)
		
		self._cal_value = 26868
		
		# 6. Calculate the power LSB
		# PowerLSB = 20 * CurrentLSB
		# PowerLSB = 0.002 (2mW per bit)
		self._power_lsb = 0.003048  # Power LSB = 2mW per bit
		
		# 7. Compute the maximum current and shunt voltage values before overflow
		#
		# Max_Current = Current_LSB * 32767
		# Max_Current = 3.2767A before overflow
		#
		# If Max_Current > Max_Possible_I then
		#    Max_Current_Before_Overflow = MaxPossible_I
		# Else
		#    Max_Current_Before_Overflow = Max_Current
		# End If
		#
		# Max_ShuntVoltage = Max_Current_Before_Overflow * RSHUNT
		# Max_ShuntVoltage = 0.32V
		#
		# If Max_ShuntVoltage >= VSHUNT_MAX
		#    Max_ShuntVoltage_Before_Overflow = VSHUNT_MAX
		# Else
		#    Max_ShuntVoltage_Before_Overflow = Max_ShuntVoltage
		# End If
		
		# 8. Compute the Maximum Power
		# MaximumPower = Max_Current_Before_Overflow * VBUS_MAX
		# MaximumPower = 3.2 * 32V
		# MaximumPower = 102.4W
		
		# Set Calibration register to 'Cal' calculated above
		self.write(_REG_CALIBRATION,self._cal_value)
		
		# Set Config register to take into account the settings above
		self.bus_voltage_range = BusVoltageRange.RANGE_16V
		self.gain = Gain.DIV_2_80MV
		self.bus_adc_resolution = ADCResolution.ADCRES_12BIT_32S
		self.shunt_adc_resolution = ADCResolution.ADCRES_12BIT_32S
		self.mode = Mode.SANDBVOLT_CONTINUOUS
		self.config = (self.bus_voltage_range << 13 |
									self.gain << 11 |
									self.bus_adc_resolution << 7 |
									self.shunt_adc_resolution << 3 |
									self.mode)
		self.write(_REG_CONFIG,self.config)

# -----------------------------------------------------------------------------
	def getShuntVoltage_mV(self):
		self.write(_REG_CALIBRATION,self._cal_value)
		value = self.read(_REG_SHUNTVOLTAGE)
		if value > 32767:
			value -= 65535
		return value * 0.01

# -----------------------------------------------------------------------------
	def getBusVoltage_V(self):
		self.write(_REG_CALIBRATION,self._cal_value)
		self.read(_REG_BUSVOLTAGE)
		return (self.read(_REG_BUSVOLTAGE) >> 3) * 0.004

# -----------------------------------------------------------------------------
	def getCurrent_mA(self):
		value = self.read(_REG_CURRENT)
		if value > 32767:
			value -= 65535
		return value * self._current_lsb

# -----------------------------------------------------------------------------
	def getPower_W(self):
		self.write(_REG_CALIBRATION,self._cal_value)
		value = self.read(_REG_POWER)
		if value > 32767:
			value -= 65535
		return value * self._power_lsb

# -----------------------------------------------------------------------------
# Sub routines
# -----------------------------------------------------------------------------
def ts():
	now = time.gmtime()
	tsStr = time.strftime('%Y-%m-%d %H:%M:%S ')
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
def getMJD():
	mjd = int(time.time()/86400) + 40587
	return(mjd)

# -----------------------------------------------------------------------------
def makePath(hm,s):
	if not s.startswith('/'):
		s = hm + s
	if not s.endswith('/'):
		s = s + '/'
	return(s)

# -----------------------------------------------------------------------------
def makeFilePath(hm,s):
	if not s.startswith('/'):
		s = hm + s
	return(s)

# -----------------------------------------------------------------------------
def checkPath(p):
	if not os.path.isdir(p):
		errorExit(f'The path {p} does not exist')
	return

# -----------------------------------------------------------------------------
def signalHandler(signal,frame):
	global running
	running = False
	return

# -----------------------------------------------------------------------------
def TestProcessLock(lockFile):
	if (os.path.isfile(lockFile)):
		flock=open(lockFile,'r')
		info = flock.readline().split()
		flock.close()
		if (len(info)==2):
			if (os.path.exists('/proc/'+str(info[1]))):
				return False
	return True

# -----------------------------------------------------------------------------
def CreateProcessLock(lockFile):
	if (not TestProcessLock(lockFile)):
		return False;
	flock=open(lockFile,'w')
	flock.write(os.path.basename(sys.argv[0]) + ' ' + str(os.getpid()))
	flock.close()
	return True

# -----------------------------------------------------------------------------
def RemoveProcessLock(lockFile):
	if (os.path.isfile(lockFile)):
		os.unlink(lockFile)
	return

# -----------------------------------------------------------------------------
def checkConfig(cfg, req):
	cnt = []
	for section in cfg.sections():
		s = section.lower()
		for key in cfg[section]:
			cnt.append(s+','+key.lower())
	for s in req:
		if not s in cnt:
			errorExit('Required key ({}) not in configuration file.'.format(s))
	debug("checkConfig: All required section:key pairs found in configuration "+
			 "file.")
	return(cnt)

# -----------------------------------------------------------------------------
def getuser(d):
	cmd = ["id","-nu",f"{d}"]
	retval = subprocess.run(cmd,capture_output=True)
	u = retval.stdout.decode('ascii').strip()
	return(u)

# -----------------------------------------------------------------------------
def gethome(u):
	success = False
	try:
		hm = pwd.getpwnam(u).pw_dir
	except:
		errorExit(f"User {u} does not exist.")
	if not hm.endswith('/'):
		hm += '/'
	if os.path.isdir(hm):
		success = True
	return(success,hm)

# -----------------------------------------------------------------------------
def changeOwnerAttributes(flnm,user):
	# everyone can read, everyone can write
	os.chmod(flnm,0o664) # Sets file mode to: -rw-rw-r--
	# get user id and group id
	udets = pwd.getpwnam(user)
	uid = udets.pw_uid
	gid = udets.pw_gid
	# change owner if necessary
	current_owner = pwd.getpwuid(os.stat(flnm).st_uid).pw_name
	if not current_owner == user:
		os.chown(flnm, uid, gid)
		new_owner = pwd.getpwuid(os.stat(flnm).st_uid).pw_name
		debug(f"changeOwnerAttributes: {flnm} was owned by {current_owner} and "+
				  f"is now owned by {new_owner}")
	return

# -----------------------------------------------------------------------------
def savedata(pth,fext,dmsg,cuser,fuser):
	# Time       Battery     Supply    Current     Power    Charge
	# stamp         (V)        (V)       (A)        (W)       (%)
	#00:00:00     4.2120     4.2120   0.000914   0.006096   100.00
	mjd = getMJD()
	flnm = f"{pth}{mjd}{fext}"
	debug(f"savedata: Saving data to {flnm}")
	if not(os.path.isfile(flnm)):
		with open(flnm,'w') as f:
			f.write("# Time       Battery     Supply    Current     Power    Charge\n")
			f.write("# stamp         (V)        (V)       (A)        (W)       (%)\n")
			f.close()
	ts = time.strftime("%H:%M:%S",time.gmtime())
	with open(flnm,'a') as f:
		f.write(f"{ts}  {dmsg}\n")
		f.close()
	if cuser != fuser:
		changeOwnerAttributes(flnm,fuser)
	return

# -----------------------------------------------------------------------------
def savestatus(fl,dmsg,cuser,fuser):
	ts = time.strftime("%H:%M:%S",time.gmtime())
	#    Battery     Supply    Current     Power    Charge
	#       (V)        (V)       (A)        (W)       (%)
	#     4.2120     4.2120   0.000914   0.006096   100.00
	debug(f"savestatus: Saving status to {fl}")
	with open(fl,'w') as f:
		f.write("#    Battery     Supply    Current     Power    Charge\n")
		f.write("#       (V)        (V)       (A)        (W)       (%)\n")
		f.write(f"  {dmsg}\n")
		f.close()
	if cuser != fuser:
		changeOwnerAttributes(fl,fuser)
	return

# -----------------------------------------------------------------------------
def savelcdmessage(fl,charge_perc,cur_A,cuser,fuser):
	 #       12345678901234567890  
	line1 = "POWER SOURCE: MAINS "
	if abs(cur_A) > 0.0002:   # Less than about 2 mA is meaningless
		if cur_A < 0:           # Current flowing from batteries 
			line1 = "POWER SOURCE: UPS   "
	line2 = f"BATTERY: {charge_perc:3d}% CHARGE"
	debug(f"savelcdmessage: line 1 >{line1} <")
	debug(f"savelcdmessage: line 2 >{line2} <")
	debug(f"savelcdmessage: Saving LCD message lines to {fl}")
	with open(fl,'w') as f:
		f.write(f"{line1}\n")
		f.write(f"{line2}\n")
		f.close()
	if cuser != fuser:
		changeOwnerAttributes(fl,fuser)
	return

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

parser = argparse.ArgumentParser(description="Manages Waveshare UPS (D) hat "+
																 "on a Raspberry Pi.")
parser.add_argument("-v","--version",action="store_true",help="Show version "+
										"and exit.")
parser.add_argument("-c","--config",nargs=1,help="Specify alternative "+
										"configuration file. The default is "+
										"~/etc/pi_ups.conf.")
parser.add_argument("-d","--debug",action="store_true",help="Turn debugging "+
										"on")

args = parser.parse_args()

if args.debug:
	DEBUG = True

versionStr = script+" version "+VERSION+" written by "+AUTHORS

if args.version:
	print(versionStr)
	sys.exit(0)

debug(versionStr)

HOME = os.path.expanduser('~')
if not(HOME.endswith('/')):
	HOME += '/'

debug("Current user's home: "+HOME)

configfile = HOME+"etc/pi_ups.conf"

if args.config:
	debug("Alternate config file specified: "+str(args.config[0]))
	configfile = str(args.config[0])
	if not configfile.startswith('/'):
		configfile = HOME+configfile

debug("Configuration file: "+configfile)

if not os.path.isfile(configfile):
	errorExit(configfile+' does not exist.')

conf = configparser.ConfigParser()
conf.read(configfile)

req = ['main,user','main,lock file','main,log interval','data,path','data,ext',
			 'status,path','status,file name','status,display file']

cfg = checkConfig(conf, req)

configured_user = conf['main']['user']
debug(f"Configured user: {configured_user}")

uid = os.getuid()
debug(f"Current user's id: {uid}")

current_user = getuser(uid)
debug(f"Current user: {current_user}")

if not configured_user == current_user:
	debug("Not running as configured user")
	r = gethome(configured_user)
	if r[0]:
		debug(f"Found the home directory for '{configured_user}': {r[1]}")
		HOME = r[1]
	else:
		debug(f"Could not find user '{configured_user}'. Home directory remains "+
				"as is.")
else:
	debug("Running as configured user")

lockfile = conf['main']['lock file']
if not lockfile.startswith('/'):
	lockfile = HOME+lockfile
if not CreateProcessLock(lockfile):
	errorExit(f'Unable to lock - {script} already running?')

try:
	logint = int(conf['main']['log interval'])
	if logint < 2 or logint > 3600:
		errorExit(f"The configured log interval ({logint} s) is invalid. The "+
						 "value must be between 2 and 3600 seconds.")
except:
	errorExit("Invalid value configured for '[main] log interval': "+
					 f"{conf['main']['log interval']}. The value must be an integer "+
					 "between 2 and 3600.")

debug(f"Data will be logged every {logint} seconds")

datapath = makePath(HOME,conf['data']['path'])
checkPath(datapath)
debug(f'Data will be saved to: {datapath}')

ext = conf['data']['ext']
if not ext.startswith('.'):
	ext = '.'+ext
debug(f"Data files will have a '{ext}' extension.")

statuspath = makePath(HOME,conf['status']['path'])
checkPath(statuspath)

statusfile = statuspath + conf['status']['file name']
debug(f'UPS status will be saved to {statusfile}')

displayfile = statuspath + conf['status']['display file']
debug(f'UPS status for LCD display will be saved to {displayfile}')

ina219 = INA219(i2c_bus=1,addr=0x43)
low = 0

signal.signal(signal.SIGINT,signalHandler)
signal.signal(signal.SIGTERM,signalHandler)
signal.signal(signal.SIGHUP,signalHandler) # not usually run with a controlling TTY, but handle it anyway

running = True
nexttime = time.time()
checkbattery = time.time()

while running:
	if time.time() > nexttime:
		bus_voltage = ina219.getBusVoltage_V()              # voltage on V- (load side)
		shunt_voltage = ina219.getShuntVoltage_mV() / 1000  # voltage between V+ and V- across the shunt
		psu_voltage = bus_voltage + shunt_voltage           # INA219 measure bus voltage on the load side.
		                                                    # So PSU voltage = bus_voltage + shunt_voltage.
		current = -ina219.getCurrent_mA()/1000              # INA219 reports current in mA
		power = ina219.getPower_W()                         # power in W
		p = (bus_voltage - 3)/1.2*100
		if(p > 100):
			p = 100
		if(p < 0):
			p = 0
		
		# Recalculate charge percentage. I noticed that the charge percentage gets stuck below 100% when the 
		# battery is fully charged, but V_BATT is not 4.2 V. I believe this is due to the INA219 accuracy.
		# So I decided that if the charge percentage is > 95%, and the current is less than 2 mA the battery
		# is fully charged. An additional check is for battery voltage to be above 4.1 V.
		
		if p > 95 and p < 100:
			if abs(current) < 0.002:
				if psu_voltage > 4.1:
					debug(f"Modifying the charge percentage from {p}% to 100%")
					p = 100
		
		#            Battery (V)        Supply (V)        Current (A)    Power (W)   Charge percentage (%)
		msg = f"{psu_voltage:10.4f} {bus_voltage:10.4f} {current:10.6f} {power:10.6f} {p:8.2f}"
		
		debug("    Battery     Supply    Current     Power    Charge")
		debug("       (V)        (V)       (A)        (W)       (%)")
		debug(f" {msg}")
		
		savedata(datapath,ext,msg,current_user,configured_user)
		savestatus(statusfile,msg,current_user,configured_user)
		savelcdmessage(displayfile,p,current,current_user,configured_user)
		if time.time() > nexttime + logint: # If application starts before time on
			nexttime = time.time()            # Pi is synchronised, fix it.
			debug("Large step in time of day observed!")
		nexttime += logint
		
	
	if time.time() > checkbattery:
		checkbattery = time.time() + 2  # Precautionary: Time may not be synced when app starts!
		if(bus_voltage < 3.15) and (current < 0.050): # Minimum charge current: 50 mA
			low += 1
			if(low >= 30): # shut down when battery low for more than a minute
				debug("System shutdown now")
				address = os.popen("i2cdetect -y -r 1 0x2d 0x2d | egrep '2d' | awk '{print $2}'").read()
				if(address!='2d\n'):
					debug("0x2d i2c address not detected, something wrong.")
				else:
					debug("If charged, the system can be powered on again")
					# write 0x55 to 0x01 register of 0x2d Address device
					# This tells the MCU to start up the Pi when power is applied
					os.popen("i2cset -y 1 0x2d 0x01 0x55")
				os.system("sudo poweroff")
			else:
				debug(f"Voltage low, please charge in time,otherwise it will shut down in {60-2*low:2d} s")
		else:
			low = 0
		if time.time() > checkbattery + 2: # If application starts before time on
			checkbattery = time.time()       # Pi is synchronised, fix it.
			debug("Large step in time of day observed!")
		# Check the battery every 2 seconds
		checkbattery +=  2
	
	time.sleep(0.1)

RemoveProcessLock(lockfile)

debug(f"{ts()} {script} terminated.")
