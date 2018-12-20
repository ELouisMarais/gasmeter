/* A program for a threaded Temperature Server
* Written by Derek Molloy for the book "Exploring BeagleBone: Tools and 
* Techniques for Building with Embedded Linux" by John Wiley & Sons, 2014
* ISBN 9781118935125. Please see the file README.md in the repository root 
* directory for copyright and GNU GPLv3 license information.            */

#include <iostream>
#include "network/SocketClient.h"
using namespace std;
using namespace exploringBB;

string getResponse(string cmd, SocketClient sc)
{
  string response;
  
  sc.connectToServer();
  string message = cmd;
  cout << "Sending [" << message << "]" << endl;
  sc.send(message);
  response = sc.receive(1024);
  cout << "Received [" << response << "]" << endl;
  sc.disconnectFromServer();
  
  return response;
}

int setValue(string cmd, string val, SocketClient sc)
{
  string response;
  
  sc.connectToServer();
  string message;
  message = cmd + "," + val;
  cout << "Sending [" << message << "]" << endl;
  sc.send(message);
  response = sc.receive(1024);
  cout << "Received [" << response << "]" << endl;
  sc.disconnectFromServer();
  
  return 0;
}

int main(int argc, char *argv[]){
  if(argc!=2){
    cout << "Incorrect usage: " << endl;
    cout << "   client server_name" << endl;
    return 2;
  }
  cout << "Starting Pi gasmeter Client Test" << endl;
  SocketClient sc(argv[1], 5555);
  
  string message;
  string rec;
  /*
  rec = getResponse("getReading", sc);
  rec = getResponse("getRoomNo", sc);
  rec = getResponse("getMeterSN", sc);
  */
  setValue("setRoomNo",">123<",sc);
    
  cout << "End of Pi gasmeter Client Test" << endl;
}
