#!/bin/sh
# 점호·상태 확인용. 코드 종류를 shell 로 바꾸고 실행한다.
echo "SN       : $(hostname)"
echo "OS       : $(cat /home/pi/.OS_VERSION)"
echo "uptime   : $(uptime -p)"
echo "temp     : $(vcgencmd measure_temp)"
echo "disk     : $(df -h / | tail -1 | awk '{print $4" free"}')"
echo "wlan0    : $(ifconfig wlan0 | grep 'inet ' | awk '{print $2}')"
