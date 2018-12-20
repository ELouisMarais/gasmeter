/*
 * ConnectionHandler.cpp  Created on: 18 Jul 2014
 * Copyright (c) 2014 Derek Molloy (www.derekmolloy.ie)
 * Made available for the book "Exploring BeagleBone" 
 * See: www.exploringbeaglebone.com
 * Licensed under the EUPL V.1.1
 *
 * This Software is provided to You under the terms of the European 
 * Union Public License (the "EUPL") version 1.1 as published by the 
 * European Union. Any use of this Software, other than as authorized 
 * under this License is strictly prohibited (to the extent such use 
 * is covered by a right of the copyright holder of this Software).
 * 
 * This Software is provided under the License on an "AS IS" basis and 
 * without warranties of any kind concerning the Software, including 
 * without limitation merchantability, fitness for a particular purpose, 
 * absence of defects or errors, accuracy, and non-infringement of 
 * intellectual property rights other than copyright. This disclaimer 
 * of warranty is an essential part of the License and a condition for 
 * the grant of any rights to this Software.
 * 
 * For more details, see http://www.derekmolloy.ie/
 */

// Initial version on 2016-07-20
// Modified from a BeagleBone Black demo
// Louis Marais

/*
 * 2016-08-02
 * 
 * Need to add more messages
 * The only current message is 'getReading', which returns the current gas meter reading
 * 
 * Want to add:
 * 
 * getRoomNo - send room number associated with this meter
 * setRoomNo, {roomno} - change room number associated with the meter
 * getMeterSN - get the meter serial number
 * setMeterSN, {SN} - set the meter serial number
 * getReadings, {start time/date}, [{end time/date}] - send all meter readings
 *                                                     from start timestamp to
 *                                                     end timestamp (end 
 *                                                     timestamp is optional).
 *                                                     Timestamps must be in
 *                                                     UTC, client is responsible
 *                                                     for translations.
 * 
 */


#include "ConnectionHandler.h"
#include <stdio.h>
#include <stdlib.h>
#include <pthread.h>
#include <iostream>
#include <fstream>
#include <sstream>
#include "SocketServer.h"
using namespace std;

//#define LDR_PATH "/sys/bus/iio/devices/iio:device0/in_voltage"

const char* gasmeterreadingfn = "/home/pi/etc/meterreading";
const char* roomnofn = "/home/pi/etc/roomno";
const char* metersnfn = "/home/pi/etc/serialnumber";

namespace exploringBB {

ConnectionHandler::ConnectionHandler(SocketServer *parent, sockaddr_in *client, int clientSocketfd) {
  this->parent = parent;
  this->client = client;
  this->running = true;
  this->clientSocketfd = clientSocketfd;
  //cout << "Created a Connection Handler" << endl;
}

ConnectionHandler::~ConnectionHandler() {
  delete this->client;
  cout << "Destroyed a Connection Handler" << endl;
}

int ConnectionHandler::start(){
  cout << "Starting the Connection Handler thread" << endl;
  return (pthread_create(&(this->thread), NULL, threadHelper, this)==0);
}

void ConnectionHandler::wait(){
  (void) pthread_join(this->thread, NULL);
}

int ConnectionHandler::send(std::string message){
  const char *writeBuffer = message.data();
  int length = message.length();
  int n = write(this->clientSocketfd, writeBuffer, length);
  if (n < 0){
    perror("Connection Handler: error writing to server socket.");
    return 1;
  }
  return 0;
}

string ConnectionHandler::receive(int size=1024){
  char readBuffer[size];
  int n = read(this->clientSocketfd, readBuffer, sizeof(readBuffer));
  if (n < 0){
    perror("Connection Handler: error reading from server socket.");
  }
  return string(readBuffer);
}

float ConnectionHandler::getGasmeterReading(){
  // open file and get value, then return it to caller  
  //float cur_voltage = adc_value * (1.80f/4096.0f);
  //float diff_degreesC = (cur_voltage-0.75f)/0.01f;
  float meterReading;
  ifstream IN;
  IN.open(gasmeterreadingfn);
  if(!IN)
  {
    perror("Cannot open 'meterreading' file.");
    exit(1);
  }
  IN >> meterReading;
  IN.close();
  return (meterReading);
}

string ConnectionHandler::getRoomNo(){
  // open file and get value, then return it to caller  
  string roomno;
  ifstream IN;
  IN.open(roomnofn);
  if(!IN)
  {
    perror("Cannot open 'roomno' file.");
    exit(1);
  }
  IN >> roomno;
  IN.close();
  return (roomno);
}

int ConnectionHandler::setRoomNo(string roomno){
  // open file and get value, then return it to caller  
  //string roomno;
  ofstream OUT;
  OUT.open(roomnofn);
  if(!OUT)
  {
    perror("Cannot open 'roomno' file.");
    exit(1);
  }
  OUT << roomno;
  OUT.close();
  return 0;
}

string ConnectionHandler::getMeterSN(){
  // open file and get value, then return it to caller  
  string metersn;
  ifstream IN;
  IN.open(metersnfn);
  if(!IN)
  {
    perror("Cannot open 'serialnumber' file.");
    exit(1);
  }
  IN >> metersn;
  IN.close();
  return (metersn);
}

void ConnectionHandler::threadLoop(){
  cout << "*** Created a Gasmeter Connection Handler threaded Function" << endl;
  string rec = this->receive(1024);
  cout << "Received from the client [" << rec << "]" << endl;
  if (rec == "getReading"){
    stringstream ss;
    ss << this->getGasmeterReading();
    this->send(ss.str());
    cout << "Sent [" << ss.str() << "]" << endl;
  }
  else if(rec == "getRoomNo"){
    stringstream ss;
    ss << this->getRoomNo();
    this->send(ss.str());
    cout << "Sent [" << ss.str() << "]" << endl;
  }
  else if(rec.substr(0,10) == "setRoomNo,"){
    // Check for valid room number after comma
    string roomno = rec.substr(10,(rec.length()-10));
    setRoomNo(roomno);
    stringstream ss;
    ss << "Roomno: " << roomno;
    this->send(ss.str());
    cout << "Sent [" << ss.str() << "]" << endl;
  }
  else if(rec == "getMeterSN"){
    stringstream ss;
    ss << this->getMeterSN();
    this->send(ss.str());
    cout << "Sent [" << ss.str() << "]" << endl;
  }
  else if(rec == "setMeterSN,"){
    // Check for valid SN after comma
  }
  else if(rec == "getReadings,"){
    // Check for valid start timestamp, and optional end timestamp
  } else {
     this->send(string("Unknown Command"));
  }
  cout << "*** End of the Gasmeter Connection Handler Function" << endl;
  this->parent->notifyHandlerDeath(this);
}

} /* namespace exploringBB */
