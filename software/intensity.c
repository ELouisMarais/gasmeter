// To build: gcc intensity.c -o intensity -lwiringPi

/*
 * To control the intensity of the LCD backlight
 *
 * Louis Marais, 2016-07-08
 *
 */

#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#include <wiringPi.h>

#include <signal.h>

#ifndef	TRUE
#  define	TRUE	(1==1)
#  define	FALSE	(1==2)
#endif

const int pwmPin = 1;
static char* intensityfn="/home/pi/etc/backlightlevel";
static char* lockfn="/home/pi/logs/intensity.lock";

// Define a variable to indicate that linux is up and 
// that the application has not been killed.
static volatile int keepRunning = 1;

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
 * Get the value of the backlight intensity from the file and do error checking
 *********************************************************************************
 */

int getBackLightLevel()
{
  char intensityStr[32];
  FILE *fp;
  fp = fopen(intensityfn,"rt");
  if (fp == NULL)
  {
    fprintf(stderr, "Cannot open 'backlightlevel' file\n");
    exit(1);
  }
  fscanf(fp,"%s",intensityStr);
  fclose(fp);
  int intensityInt;
  intensityInt = atoi(intensityStr);
  if (intensityInt < 0 || intensityInt > 1024) return 0;
  return intensityInt;
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
    fprintf(stderr, "Cannot open 'intensity.lock' file\n");
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
    fprintf(stderr, "Cannot delete 'intensity.lock' file\n");
  }
}

/*
 * Main routine
 *********************************************************************************
 */

int main (int argc, char *argv[])
{
  // Check if we have access to the required file
  if(!haveFileAccess(intensityfn)) return -1;

  // use intHandler to exit gracefully
  signal(SIGINT, intHandler);
  signal(SIGTERM, intHandler);

  wiringPiSetup();
  pinMode(pwmPin, PWM_OUTPUT);
  pwmWrite(pwmPin, 512);
  int backlight, oldbacklight;
  oldbacklight = 512;

  // Write executable and its pid to the lock file
  createLockFile(argv[0]);

  while (keepRunning) // Loop until SIGINT or SIGTERM
  {
    backlight = getBackLightLevel();
    if (backlight != oldbacklight)
    {
      pwmWrite(pwmPin, backlight);
      oldbacklight = backlight;
    }
    // We need to add a delay to ensure that this app does not eat up all the
    // CPU cycles! we will wait half a second between intensity update checks.
    delay (500);
  }
  // Dim the LCD backlight on exit
  pwmWrite(pwmPin,0);
  destroyLockFile();
  return 0;
}
