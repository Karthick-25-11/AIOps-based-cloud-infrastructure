#28.042026

#EKS intgration PHASE

#ALL ANOMALY WORKING FOR CLUSTER_still not checked memory layer and old pods are killed instead of high cpu pod,so need to achieve kill the culprit pod

import boto3
import time
from datetime import datetime, timedelta
from boto3.dynamodb.conditions import Key

# =========================
# AWS CLIENTS
# =========================
cw = boto3.client('cloudwatch')
dynamodb = boto3.resource('dynamodb')
ssm = boto3.client('ssm')
ec2 = boto3.client('ec2')

# =========================
# CONFIG
# =========================
TABLE_NAME = "AIOps_Remediation_History"
ASG_NAME = "eks-ng-7dc902cc-8ccee6de-ceba-8071-bbbf-09d0c6cab9ff"
DEPLOYMENT_NAME = "demo"

THRESHOLD = 40
NET_THRESHOLD = 100000

audit_table = dynamodb.Table(TABLE_NAME)

# =========================
# COMMON SSM COMMAND (FIXED ONCE)
# =========================
def get_kubectl_restart_command():
    return f"sudo -u ubuntu bash -c 'export KUBECONFIG=/home/ubuntu/.kube/config && kubectl rollout restart deployment {DEPLOYMENT_NAME}'"

def get_kubectl_scale_command():
    return f"sudo -u ubuntu bash -c 'export KUBECONFIG=/home/ubuntu/.kube/config && kubectl scale deployment {DEPLOYMENT_NAME} --replicas=3'"

# =========================
# GET INSTANCE (NO HARDCODE)
# =========================
def get_instance_id():
    response = ec2.describe_instances(
        Filters=[
            {'Name': 'tag:aws:autoscaling:groupName', 'Values': [ASG_NAME]},
            {'Name': 'instance-state-name', 'Values': ['running']}
        ]
    )

    instances = [
        i['InstanceId']
        for r in response['Reservations']
        for i in r['Instances']
    ]

    return instances[0] if instances else None


# =========================
# MAIN HANDLER
# =========================
def lambda_handler(event, context):

    instance_id = "i-092afa06d43888cb4"   # your jump server

    if not instance_id:
        return {"status": "ERROR", "reason": "No EC2 instance found"}

    # ================= METRICS =================
    params = {
        'Namespace': 'AWS/EC2',
        'Dimensions': [{'Name': 'AutoScalingGroupName', 'Value': ASG_NAME}],
        'StartTime': datetime.utcnow() - timedelta(minutes=15),
        'EndTime': datetime.utcnow(),
        'Period': 60,
        'Statistics': ['Average']
    }

    cpu = cw.get_metric_statistics(MetricName='CPUUtilization', **params)
    net = cw.get_metric_statistics(MetricName='NetworkIn', **params)

    cpu_points = sorted(cpu['Datapoints'], key=lambda x: x['Timestamp'])
    net_points = sorted(net['Datapoints'], key=lambda x: x['Timestamp'])

    if not cpu_points:
        return log_and_return("WAITING", "Gathering data...")

    p3 = cpu_points[-1]['Average']

    # ================= MEMORY =================
    history = audit_table.query(
        KeyConditionExpression=Key('InstanceID').eq(ASG_NAME),
        ScanIndexForward=False,
        Limit=50
    ).get('Items', [])

    pending = next((i for i in history if i.get('Outcome') == 'PENDING'), None)

    # ================= HANDLE PENDING =================
    if pending:
        time_diff = int(time.time()) - int(pending['Timestamp'])

        if time_diff < 300:
            return {"status": "WAITING"}

        outcome = "SUCCESS" if p3 < THRESHOLD else "FAILED"
        update_outcome(pending, outcome)

    # ================= HEALTH =================
    if p3 < THRESHOLD:
        return log_and_return("STABLE", f"Healthy: {p3:.1f}%")

    # ================= DECISION ENGINE =================
    if len(cpu_points) >= 3:
        p1 = cpu_points[-3]['Average']
        p2 = cpu_points[-2]['Average']
        latest_net = net_points[-1]['Average'] if net_points else 0

        metrics = f"({p1:.1f}, {p2:.1f}, {p3:.1f})"

        # 1️⃣ PLATEAU
        if p1 > THRESHOLD and p2 > THRESHOLD and p3 > THRESHOLD:
            return execute_reboot(f"PLATEAU: {metrics}", instance_id)

        # 2️⃣ SILENT LEAK / VIRAL
        if p1 < p2 < p3 and p3 > THRESHOLD:
            if (p3 - p1) > 20:
                if latest_net > NET_THRESHOLD:
                    return execute_scale(f"VIRAL: {metrics}", instance_id)
                else:
                    return execute_reboot(f"SILENT LEAK: {metrics}", instance_id)

            return log_and_return("STABLE", f"Slow rise: {metrics}")

        # 3️⃣ BLIP
        if p2 > THRESHOLD and p3 < p2:
            return log_and_return("STABLE", f"Blip: {metrics}")

    return log_and_return("WAITING", "Gathering data...")


# =========================
# ACTIONS (CONSISTENT)
# =========================
def execute_reboot(reason, instance_id):

    ssm.send_command(
        InstanceIds=[instance_id],
        DocumentName="AWS-RunShellScript",
        Parameters={
            "commands": [get_kubectl_restart_command()]
        }
    )

    return log_and_return("AUTONOMOUS_REBOOT", reason, "PENDING")


def execute_scale(reason, instance_id):

    ssm.send_command(
        InstanceIds=[instance_id],
        DocumentName="AWS-RunShellScript",
        Parameters={
            "commands": [get_kubectl_scale_command()]
        }
    )

    return log_and_return("SCALE_OUT", reason, "PENDING")


# =========================
# HELPERS
# =========================
def update_outcome(item, status):
    audit_table.update_item(
        Key={'InstanceID': ASG_NAME, 'Timestamp': int(item['Timestamp'])},
        UpdateExpression="SET Outcome = :o",
        ExpressionAttributeValues={':o': status}
    )


def log_and_return(action, reason, outcome=None):
    ist = datetime.utcnow() + timedelta(hours=5, minutes=30)

    item = {
        'InstanceID': ASG_NAME,
        'Timestamp': int(time.time()),
        'Action': action,
        'Reason': reason,
        'HumanReadableTime': ist.strftime("%Y-%m-%d %H:%M:%S")
    }

    if outcome:
        item['Outcome'] = outcome

    audit_table.put_item(Item=item)

    return {"status": action}