// Compile: gcc countpulses.c -o countpulses -lwiringPi

/*
 * To count and store pulses coming from the gasmeter
 *
 * Louis Marais, 2016-07-08
 * version 0.1 finished 2016-07-14
 * 
 * version 0.2 started 2016-10-18
 * 
 * Modifications:
 * 
 * Found issue with float not having enough precision (volume variable)
 * Made it a double, this fixed it.
 * 
 * Last modified on 2016-10-18
 *
 * Modified 2018-12-14:
 * 'meterreading' file must get "touched" at least every hour. This is
 * required because the broadcast.py software looks for a change in the file 
 * modification date.
 * 
*/

#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#include <wiringPi.h>

#include <signal.h>

#include <time.h>
#include <unistd.h>
#include <utime.h>


#ifndef	TRUE
#  define	TRUE	(1==1)
#  define	FALSE	(1==2)
#endif

// I am getting spurious counts, maybe because this pin is
// right next to the PWM output pin ... So I'm moving away
// to the most remote pin possible (GPIO21, pin no 29).
//const int countPin = 0;
const int countPin = 29;
static char* meterreadingfn="/home/pi/etc/meterreading";
static char* lockfn="/home/pi/logs/countpulses.lock";

// Define a variable to indicate that linux is up and
// that the application has not been killed.
static volatile int keepRunning = 1;

/*
 * Define interrupt service routine
 *********************************************************************************
 * for some reason the first pulse is always counted twice... So I defined a
 * firstrun variable to solve this
 */

int firstRun = 0;

void gasmeterISR(void)
{
  // Ignore the first pulse.
  if(firstRun == 0)
  {
    firstRun = 1;
  }
  else
  {
    char volumeStr[32];
    FILE *fp;
    // get gas volume from file
    fp = fopen(meterreadingfn,"rt");
    if (fp == NULL)
    {
      fprintf(stderr, "Cannot open 'meterreading' file\n");
      exit(1);
    }
    fscanf(fp,"%s",volumeStr);
    fclose(fp);
    //float volume;
    double volume;
    volume = atof(volumeStr);
    // increment volume
    volume += 0.01;
    // write count to file
    // get gas volume from file
    fp = fopen(meterreadingfn,"wt");
    if (fp == NULL)
    {
      fprintf(stderr, "Cannot open 'meterreading' file\n");
      exit(1);
    }
    fprintf(fp,"%0.3f",volume);
    fclose(fp);
    // For testing
    //printf("volume now: %0.3f\n",volume);
  }
}

/*
 * Event handler for kill events
 *********************************************************************************
 */

void intHandler(int dummy)
{
   keepRunning = 0;
}

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
    printf("%s is not accessible!\n",filename);
  }
  return (fp!=NULL);
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
    fprintf(stderr, "Cannot open 'countpulses.lock' file\n");
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
    fprintf(stderr, "Cannot delete 'countpulses.lock' file\n");
  }
}


/*
 * 'touch' a file
 *********************************************************************************
 */
void touch(const char *filename)
{
  if(access(filename,F_OK) != -1){
    utime(filename,NULL);
  }
}

/*
 * Main routine
 *********************************************************************************
 */

int main (int argc, char *argv[])
{
  // Check if we have access to the required file
  if(!haveFileAccess(meterreadingfn)) return -1;

  // use intHandler to exit gracefully
  signal(SIGINT, intHandler);
  signal(SIGTERM, intHandler);

  wiringPiSetup();
  wiringPiISR(countPin,INT_EDGE_FALLING,&gasmeterISR);

  // Write executable and its pid to the lock file
  createLockFile(argv[0]);
  
  struct tm *t ;
  time_t tim ;
  int log_write = 0;
  FILE *fp;  
  
  while(keepRunning)
  {
    delay(500);
    // If it is on the hour "touch" the 'meterreading' file
    tim = time (NULL);
    t = localtime (&tim);  // Local time
    if(t->tm_min == 0 && t->tm_sec == 0 && log_write == 1)
    //if(t->tm_sec == 0 && log_write == 1)
    {
      touch(meterreadingfn);
      log_write = 0;
    }
    
    if(t->tm_min == 0 && t->tm_sec != 0 && log_write == 0) log_write = 1;
    //if(t->tm_sec != 0 && log_write == 0) log_write = 1;
    
  }
  destroyLockFile();
  return 0;
}
