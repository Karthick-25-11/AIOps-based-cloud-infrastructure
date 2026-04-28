test codes



---------------------------------------------------
ANOMALY 1- BLIP
test 1 - blip test
CMD:

stress --cpu 8 --timeout 600

or 80s

---------------------------------------------------

ANOMALY 3 better test commmand:
TEST FOR SILENT LEAK _ REBOOT

stress --cpu 1 --timeout 60

stress --cpu 2 --timeout 60

stress --cpu 4 --timeout 600

---------------------------------------------------

ANOMALY 3
gradual surge(no network) -- reboot yes

echo "Starting Stage 1: The Base (Target ~25%)"
stress --cpu 1 --timeout 180s &
sleep 180;

echo "Starting Stage 2: The Climb (Target ~55%)"
stress --cpu 1 --timeout 180s &
sleep 180;

echo "Starting Stage 3: The Peak (Target ~100%)"
stress --cpu 2 --timeout 180s &
echo "Staircase is locked. Go get a coffee. Let the automation do the rest."

-----------------------------------

ANOMALY 4 viral surge (network + gradual surge) - no reboot, auto scale it

# 1. Start the Network Flood in the background
while true; do wget -O /dev/null https://speed.hetzner.de/100MB.bin; done &
while true; do wget -O /dev/null https://speed.hetzner.de/100MB.bin; done &
FLOOD_PID=$!

echo "Stage 1: The Base + High Traffic (~25% CPU)"
stress --cpu 1 --timeout 180s

echo "Stage 2: The Climb + High Traffic (~55% CPU)"
stress --cpu 1 --timeout 180s

echo "Stage 3: The Peak + High Traffic (~100% CPU)"
stress --cpu 2 --timeout 180s

# 2. Clean up
kill $FLOOD_PID
killall wget
echo "Test Complete. Check DynamoDB for SCALE_OUT | VIRAL SURGE"