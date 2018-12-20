/* A program for a threaded Temperature Server
* Written by Derek Molloy for the book "Exploring BeagleBone: Tools and 
* Techniques for Building with Embedded Linux" by John Wiley & Sons, 2014
* ISBN 9781118935125. Please see the file README.md in the repository root 
* directory for copyright and GNU GPLv3 license information.            */

/* I modified it to make it work as a server for the Pi gas meter readings
 * Louis Marais 2016-07-14
 */

#include <stdlib.h>
#include <iostream>
#include <fstream>
#include "network/SocketServer.h"
using namespace std;
using namespace exploringBB;

static char* lockfn="/home/pi/logs/gasmeterserver.lock";

/*
 * Create a process lock file
 *********************************************************************************
 */

void createLockFile(char* processname)
{
  ofstream OUT;
  OUT.open(lockfn);
  if(!OUT)
  {
    perror("Cannot open 'gasmeterserver.lock' file");
    exit(1);
  }
  
  OUT << processname << " " << getpid() << endl;
  OUT.close(); 
}

/*
 * Destroy the process lock file
 *********************************************************************************
 */

void destroyLockFile()
{
  if (remove(lockfn) != 0)
  {
    fprintf(stderr, "Cannot delete 'gasmeterserver.lock' file\n");
  }
}

/*
 * Main routine
 *********************************************************************************
 */

int main(int argc, char *argv[])
{
  // Create the lock file
  createLockFile(argv[0]);
  // Start the server and listen for requests   
  cout << "Starting Pi gasmeter Server" << endl;
  SocketServer server(5555);
  //SocketServer server(9990);
  cout << "Listening for a connection..." << endl;
  server.threadedListen();
  cout << "Pi gasmeter Server exiting..." << endl;
  // Remove lock file
  destroyLockFile(); 
}
