#!/bin/bash

echo "Camera setting"
arv-tool-0.4 control GevSCPSPacketSize=9000
arv-tool-0.4 control -n SENTECH-18B9810 TriggerDelay=50
echo "Network setting"
