// Compile: gcc gasmeter.c -o gasmeter -lwiringPi -lwiringPiDev -lrt


/* gasmeter.c
 *
 * Based on lcd.c from the wiringPi software - see original message and 
 * copyright below.
 *
 * Louis Marais (start 2016-07-06, initial version finalised on 2016-07-12)
 * 
 * Modified on 2016-07-22:
 * Memory leak - MJW investigated and found that it leaked in the
 * getIPaddr routine. I'm suppose to use freeifaddrs to free the 
 * memory used in the list that is created by the getifaddrs function.
 * MJW also pointed out several other things I could change to make
 * the code better. The funky thing is that this was in the example I
 * copied from, but I missed it.
 * 
 * Modified on 2016-08-01:
 * I discussed the application with Jason. He said it would be best if the
 * gasmeter reasing is logged to the file every time it changes, as well as
 * once an hour. This will be useful to study gas flow during fills, etc.
 * I added the millisecond portion to the time stamp in the meterlog file,
 * in case there are more than one pulse per second.
 * 
 * Modified on 2016-12-14:
 * The millisecond portion of the timestamp was extracted from a different
 * clock, so the timestamps in the files were wrong. I fixed that, see 
 * line ~ 292.
 * 
 * Modified 2018-11-30:
 * Data now stored in a new file each month with filename {yyyy-mm}.dat in the 
 * ~/data directory.
 * 
 * On a 20 x 4 LCD module display the following:
 *
 *    00000000011111111112
 *    12345678901234567890
 *   +--------------------+
 * 1 |YYYY-MM-DD  HH:MM:SS| Current date and time
 * 2 |  IP: 10.64.39.XXX  | IP address of Pi2
 * 3 |B366      NSW32346HP| Room number and serial number of gas meter
 * 4 |     00000.000 m3   | Meter reading in cubic metres
 *   +--------------------+
 *
 */

/*
 * lcd.c:
 *	Text-based LCD driver.
 *	This is designed to drive the parallel interface LCD drivers
 *	based in the Hitachi HD44780U controller and compatables.
 *
 *	This test program assumes the following:
 *
 *	8-bit displays:
 *		GPIO 0-7 is connected to display data pins 0-7.
 *		GPIO 11 is the RS pin.
 *		GPIO 10 is the Strobe/E pin.
 *
 *	For 4-bit interface:
 *		GPIO 4-7 is connected to display data pins 4-7.
 *		GPIO 11 is the RS pin.
 *		GPIO 10 is the Strobe/E pin.
 *
 * Copyright (c) 2012-2013 Gordon Henderson.
 ***********************************************************************
 * This file is part of wiringPi:
 *	https://projects.drogon.net/raspberry-pi/wiringpi/
 *
 *    wiringPi is free software: you can redistribute it and/or modify
 *    it under the terms of the GNU Lesser General Public License as published by
 *    the Free Software Foundation, either version 3 of the License, or
 *    (at your option) any later version.
 *
 *    wiringPi is distributed in the hope that it will be useful,
 *    but WITHOUT ANY WARRANTY; without even the implied warranty of
 *    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *    GNU Lesser General Public License for more details.
 *
 *    You should have received a copy of the GNU Lesser General Public License
 *    along with wiringPi.  If not, see <http://www.gnu.org/licenses/>.
 ***********************************************************************
 */

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>

#include <unistd.h>
#include <string.h>
#include <time.h>

#include <wiringPi.h>
#include <lcd.h>

// To get IP address (see http://stackoverflow.com/questions/2283494/get-ip-address-of-an-interface-on-linux)

#include <arpa/inet.h>
#include <sys/socket.h>
#include <netdb.h>
#include <ifaddrs.h>

// For kill signals
#include <signal.h>

#ifndef	TRUE
#  define	TRUE	(1==1)
#  define	FALSE	(1==2)
#endif

// Define cubic ^3 character

static unsigned char cubicChar [8] =
{
  0b01100, //  xx
  0b10010, // x  x
  0b00100, //   x
  0b10010, // x  x
  0b01100, //  xx
  0b00000, //
  0b00000, //
  0b00000, //
} ;


// Global lcd handle:
static int lcdHandle ;

// filenames
static char* roomnofn="/home/pi/etc/roomno";
static char* serialnumberfn="/home/pi/etc/serialnumber";
static char* meterreadingfn="/home/pi/etc/meterreading";
//static char* meterlogfn="/home/pi/logs/meterlog";
static char* datapath = "/home/pi/data/";
static char* lockfn="/home/pi/logs/gasmeter.lock";

// Define a variable to indicate that linux is up and 
// that the application has not been killed.
static volatile int keepRunning = 1;

/*
 * Create handler for for kill events
 *********************************************************************************
 */

void intHandler(int dummy)
{
   keepRunning = 0; 
}

/*
 * Get IP address of eth0
 *********************************************************************************
 */

void getIPaddr(char* ipAddr)
{
  struct ifaddrs *ifaddr, *ifa;
  int family, s;
  char host[NI_MAXHOST];

  if (getifaddrs(&ifaddr) == -1) 
  {
    perror("getifaddrs");
    exit(EXIT_FAILURE);
  }

  for (ifa = ifaddr; ifa != NULL; ifa = ifa->ifa_next) 
  {
    if (ifa->ifa_addr == NULL)
      continue;  

    s=getnameinfo(ifa->ifa_addr,sizeof(struct sockaddr_in),host, NI_MAXHOST, NULL, 0, NI_NUMERICHOST);

    if((strcmp(ifa->ifa_name,"eth0")==0)&&(ifa->ifa_addr->sa_family==AF_INET))
    {
      if (s != 0)
      {
        printf("getnameinfo() failed: %s\n", gai_strerror(s));
        exit(EXIT_FAILURE);
      }
      sprintf(ipAddr,"%s", host); 
      //printf("%s", host); 
    }
  }
  freeifaddrs(ifaddr);
}

/*
 * Compare two strings
 *********************************************************************************
 */

// Now using built-in function strcmp
/*
int compareStr(const char* s1, const char* s2)
{
  if (strlen(s1) != strlen(s2)) return 1;
  int i; // compiler not C99 compliant!
  for(i = 0; i < strlen(s1); i++)
  {
    if (s1[i] != s2[i]) return 1;
  }
  return 0;
}
*/
/*
 * Check if the file is accessible
 *********************************************************************************
 */

int haveFileAccess(const char *filename)
{
  FILE *fp = fopen (filename, "r");
  if (fp!=NULL)
  {
    fclose (fp);
  } else
  {
    fprintf(stderr,"%s is not accessible!\n",filename);
  }  
  return (fp!=NULL);
}

/*
 * Get room number
 *********************************************************************************
 */

void getRoomNo(char* roomno)
{
  FILE *fp;
  fp = fopen(roomnofn,"rt");
  if (fp == NULL)
  {
    fprintf(stderr, "Cannot open 'roomno' file\n");
    exit(1);
  }
  fscanf(fp,"%s",roomno);
  fclose(fp);
}

/*
 * Get gas meter serial number
 *********************************************************************************
 */

void getGasMeterSN(char* sn)
{
  FILE *fp;
  fp = fopen(serialnumberfn,"rt");
  if (fp == NULL)
  {
    fprintf(stderr, "Cannot open 'serialnumber' file\n");
    exit(1);
  }
  fscanf(fp,"%s",sn);
  fclose(fp);
}

/*
 * Get gas meter reading
 *********************************************************************************
 */

float getGasMeterReading()
{
  char readingStr[32];
  FILE *fp;
  fp = fopen(meterreadingfn,"rt");
  if (fp == NULL)
  {
    fprintf(stderr, "Cannot open 'meterreading' file\n");
    exit(1);
  }
  fscanf(fp,"%s",readingStr);
  fclose(fp);
  return atof(readingStr);
}

/*
 * Write gas meter reading to file
 *********************************************************************************
 */

void writeLog(float reading)
{
  char outstr[200], ts[32];
  time_t t;
  struct tm *tmutc;
  struct timespec tns;
  int ms;
  
  t = time(NULL);
  tmutc = gmtime(&t);
  //clock_gettime(CLOCK_MONOTONIC, &tns);
  clock_gettime(CLOCK_REALTIME, &tns);
  ms = tns.tv_nsec/1e6;
  strftime(outstr, sizeof(outstr), "%F %T", tmutc);
  snprintf(ts,32,"%s.%03d",outstr,ms);
  // Need to redo timestamp as outstr does not seem to round properly...
  
	// Create filename
	char buf[32]; 
	char flnm[255];// data file format and location: /home/pi/data/yyyy-mm.dat
	sprintf(buf,"%04d-%02d.dat",tmutc->tm_year+1900,tmutc->tm_mon + 1);
	strcpy(flnm,datapath);
	strcat(flnm,buf);
	
  FILE *fp;
  //fp = fopen(meterlogfn,"at");
  fp = fopen(flnm,"at");
  if (fp == NULL)
  {
    fprintf(stderr, "Cannot open 'meterlog' file\n");
    exit(1);
  }
  //fprintf(fp,"%04d-%02d-%02d %02d:%02d:%02d", t->tm_year+1900,t->tm_mon + 1,t->tm_mday,t->tm_hour,t->tm_min,t->tm_sec);
  //fprintf(fp,"\t%0.2f\n",reading);
  fprintf(fp,"%s\t%0.2f\n",ts,reading);
  fclose(fp);
}

/*
 * Create a process lock file
 *********************************************************************************
 */

void createLockFile(char* processname)
{
  FILE *fp;  
  fp = fopen(lockfn,"wt");
  if (fp == NULL)
  {
    fprintf(stderr, "Cannot open 'gasmeter.lock' file\n");
    exit(1);
  }
  int pid = getpid();
  fprintf (fp,"%s %d\n",processname,pid); 
  fclose(fp);
}

/*
 * Destroy the process lock file
 *********************************************************************************
 */

void destroyLockFile()
{
  if (remove(lockfn) != 0)
  {
    fprintf(stderr, "Cannot delete 'gasmeter.lock' file\n");
  }
}

/*
 * Main routine
 *********************************************************************************
 */

int main (int argc, char *argv[])
{
  // Check if we have access to the required files
  if(!haveFileAccess(roomnofn)) return -1;
  if(!haveFileAccess(serialnumberfn)) return -1;
  if(!haveFileAccess(meterreadingfn)) return -1;
  
  // use intHandler to exit gracefull 
  signal(SIGINT, intHandler);
  signal(SIGTERM, intHandler);
  
  int i ;
  int lcd ;
  int bits, rows, cols ;

  struct tm *t ;
  time_t tim ;

  char buf[32], oldbuf[32];

  // While developing, this showed me that the thing was doing something!
  //printf ("\nRaspberry Pi based gas meter\n~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n");

  // Hardcode sizes for LCD used with gasmeter application - always uses a 
  // 20 x 4 LCD module
  bits = 4;
  cols = 20;
  rows = 4;

  // I left all the size testing in place.  
  if (!((rows == 1) || (rows == 2) || (rows == 4)))
  {
    fprintf (stderr, "%s: rows must be 1, 2 or 4\n", argv [0]) ;
    return EXIT_FAILURE ;
  }

  if (!((cols == 16) || (cols == 20)))
  {
    fprintf (stderr, "%s: cols must be 16 or 20\n", argv [0]) ;
    return EXIT_FAILURE ;
  }

  wiringPiSetup () ;

  if (bits == 4)
    lcdHandle = lcdInit (rows, cols, 4, 11,10, 4,5,6,7,0,0,0,0) ;
  else
    lcdHandle = lcdInit (rows, cols, 8, 11,10, 0,1,2,3,4,5,6,7) ;

  if (lcdHandle < 0)
  {
    fprintf (stderr, "%s: lcdInit failed\n", argv [0]) ;
    return -1 ;
  }

  // Get IP address, try 10 times (eth0 may not be up by the time this gets done)
  char ip[32],newip[32],ipstr[32];
  int count = 0;
  while (ip[0] == '\0' && count < 10)
  {
    getIPaddr(ip);
    // For debugging during development
    //printf ("Try %d, IP: %s\n",count,ip);
    if (ip[0] == '\0') { delay (1000); }
    count++;
  }

  // Define cubic character (^3)
  lcdCharDef (lcdHandle, 2, cubicChar);

  char roomno[32],gasmetersn[32];
  // Get room number and meter serial number
  getRoomNo(roomno);
  getGasMeterSN(gasmetersn);
  int lenRN = strlen(roomno);
  int lenSN = strlen(gasmetersn);
  int lenSp = 20 - lenRN - lenSN;
  char spStr[32];
  if(lenSp > 0)
  {
    sprintf(spStr,"%*c",lenSp,' ');
  } 
  else 
  {
    spStr[0] = ' ';
  }
  // To do: create a single string for room + sn and 
  // truncate intelligently to get a 20 character result
  
  // Show room number and meter serial number on line 2
  lcdPosition (lcdHandle,0,2);
  lcdPuts (lcdHandle,roomno);
  lcdPuts (lcdHandle,spStr);
  lcdPuts (lcdHandle,gasmetersn);
  
  float reading;
  char readingStr[32], oldreadingStr[32];
  int log_write = 0;
  int ipchecked = 0;
  int firstrun = 0;

  // Write executable and its pid to the lock file
  createLockFile(argv[0]);
  
  while (keepRunning) // Loop until SIGINT or SIGTERM
  {
    // Show date and time on line 0
    tim = time (NULL);
    t = localtime (&tim);  // Local time
    lcdPosition (lcdHandle,0,0);
    sprintf (buf, "%04d-%02d-%02d  %02d:%02d:%02d", t->tm_year+1900,t->tm_mon + 1,t->tm_mday,t->tm_hour,t->tm_min,t->tm_sec);    
    // Only update if the time has changed
    if(oldbuf[19] != buf[19]) lcdPuts (lcdHandle,buf); // printf("%s\n",buf); }
    strcpy(oldbuf,buf);
       
    // Get meter reading from file, and if it has changed, update it.
    reading = getGasMeterReading();
    // Sometimes the reading gets returned as 0. When this happens, do nothing.
    if(reading != 0)
    {
    sprintf(readingStr,"%9.2fx m",reading);
      //if (compareStr(readingStr,oldreadingStr) != 0)
      if (strcmp(readingStr,oldreadingStr) != 0)
      {
        // Show gas meter reading on line 3
        lcdPosition (lcdHandle,5,3);
        lcdPuts (lcdHandle, readingStr);
        lcdPutchar (lcdHandle,2);
        strcpy(oldreadingStr,readingStr);
        // Write the new value to the log file
        writeLog(reading);
      }
    }
    // Check the IP address every 5 minutes - it can change!
    if((((t->tm_min % 5) == 0) && (ipchecked == 0)) || (firstrun == 0))
    {
      getIPaddr(ip);
      //if (compareStr(ip,newip) != 0)
      if (strcmp(ip,newip) != 0)
      {
        // Clear the line first, if the new 'ipstr' is shorter than the current one
        // then there will be characters left over, which can cause confusion.
        lcdPosition (lcdHandle,0,1);
        lcdPuts (lcdHandle,"                    ");
        sprintf(ipstr,"IP: %s",ip);
        if(ip[0] == '\0') {sprintf(ipstr,"IP: 0.0.0.0");}
        int iplen = strlen(ipstr);
        // Show IP address centred on line 1
        lcdPosition (lcdHandle,(cols - iplen)/2,1);
        lcdPuts (lcdHandle,ipstr);      
        strcpy(newip,ip);
        ipchecked = 1;
      }
    }
    if(((t->tm_min % 5) != 0) && (ipchecked == 1)) ipchecked = 0;

    // Save gas meter reading to log file every hour
    if(t->tm_min == 0 && t->tm_sec == 0 && log_write == 1)
    //if(t->tm_sec == 0 && log_write == 1)
    {
      writeLog(reading);
      log_write = 0;
    }
    
    if(t->tm_min == 0 && t->tm_sec != 0 && log_write == 0) log_write = 1;
    //if(t->tm_sec != 0 && log_write == 0) log_write = 1;
    
    // Wait so that CPU utilisation is not so high (currently > 50%)
    // OK, much better now: 2.6% ~ 3% CPU utilisation!
    delay(250); // milliseconds
    firstrun = 1;
  }
  lcdClear (lcdHandle);
  destroyLockFile(); 
  t = NULL;
  free(t);
  return 0 ;
}
