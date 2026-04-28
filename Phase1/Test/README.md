#SILENT LEAK
------------------------------------------------------------------------------
echo "Starting Stage 1: The Base (Target ~25%)"
stress --cpu 1 --timeout 180s &
sleep 180;

echo "Starting Stage 2: The Climb (Target ~55%)"
stress --cpu 1 --timeout 180s &
sleep 180;

echo "Starting Stage 3: The Peak (Target ~100%)"
stress --cpu 2 --timeout 180s &
echo "Staircase is locked. Go get a coffee. Let the automation do the rest."

--------------------------------------------------------------------------------