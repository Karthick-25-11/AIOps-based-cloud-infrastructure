PHASE 3 EKS

TEST FOR SILENT LEAK no net- reboot(restart old pods,not new one)-DB shows failed-expected)-need to delete that silent pod manually for succesful reboot
it dont detect high cpu pod,instead it restarts old pods-need to upgrade to raal AI ops

CMD:
kubectl run silent --image=alpine --restart=Never -- sh -c "while true; do yes > /dev/null; done"


DELETE POD CMD : kubectl delete pod silent 
DB= SUCCESS

Rsult:
✔ Old pod killed
✔ New pod created
✔ Restart SUCCESSFULLY executed

-------------------------------------------------------------------------

TEST FOR VIRAL SURGE (with net)- AUTO SCALE pods not EC2- DB success

kubectl run viral \
--image=alpine \
--restart=Never \
-- sh -c "
apk add --no-cache stress-ng wget > /dev/null 2>&1;

echo 'Stage 1';
stress-ng --cpu 1 --timeout 120s &
while true; do wget -q -O /dev/null https://speed.hetzner.de/100MB.bin; done
"

Result : Lambda → SSM → jump server → kubectl scale deployment 
(✔ More pods on SAME node
❌ No new EC2 instances)

Future : EKS + ASG integration ie If pods > threshold → scale EC2 ASG


-----------------------------------------------------------------------

PLATAEU
kubectl run plateau \
--image=alpine \
--restart=Never \
-- sh -c "while true; do yes > /dev/null; done"


Result: initially marked as SILENT LEAK, let it be, dont delete pod manually, after 5 mins, it will be plateau and RESTART pods done

-----------------------------------------------------------------------
