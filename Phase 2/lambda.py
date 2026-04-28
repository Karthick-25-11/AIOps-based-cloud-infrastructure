#PHASE 2   dt:23.04.2026 time 18.47

#moved to instance based DB query to ASG based query 
#all anomalies work fine
#achieved memory layer dont make same mistake twice (if last reboot failed -- now scale out)

import boto3
import time
from datetime import datetime, timedelta
from boto3.dynamodb.conditions import Key

# Clients
ec2 = boto3.client('ec2')
cw = boto3.client('cloudwatch')
asg = boto3.client('autoscaling')
dynamodb = boto3.resource('dynamodb')

# Configuration
audit_table = dynamodb.Table('AIOps_Remediation_History')
ASG_NAME = "My-Application-ASG" 
THRESHOLD = 40 
NET_THRESHOLD = 100000  # 100KB/s

def lambda_handler(event, context):

    # 1. DYNAMIC DISCOVERY
    asg_response = asg.describe_auto_scaling_groups(AutoScalingGroupNames=[ASG_NAME])
    asg_data = asg_response['AutoScalingGroups'][0]
    instances = asg_data['Instances']
    
    if not instances:
        return {"status": "ERROR", "reason": "No instances found"}

    target_id = instances[0]['InstanceId']

    # --- FETCH METRICS ---
    dimensions = [{'Name': 'AutoScalingGroupName', 'Value': ASG_NAME}]
    common_params = {
        'Namespace': 'AWS/EC2',
        'Dimensions': dimensions,
        'StartTime': datetime.utcnow() - timedelta(minutes=15),
        'EndTime': datetime.utcnow(),
        'Period': 60,
        'Statistics': ['Average']
    }

    cpu_stats = cw.get_metric_statistics(MetricName='CPUUtilization', **common_params)
    net_stats = cw.get_metric_statistics(MetricName='NetworkIn', **common_params)

    cpu_points = sorted(cpu_stats['Datapoints'], key=lambda x: x['Timestamp'])
    net_points = sorted(net_stats['Datapoints'], key=lambda x: x['Timestamp'])

    if not cpu_points:
        return log_and_return(ASG_NAME, "WAITING", "Gathering data...")

    p3 = cpu_points[-1]['Average']

    # --- AUDITOR ---
    response = audit_table.query(
        KeyConditionExpression=Key('InstanceID').eq(ASG_NAME),
        ScanIndexForward=False,
        Limit=50
    )
    history = response.get('Items', [])

    last_remediation = next(
        (i for i in history 
         if i['Action'] in ['AUTONOMOUS_REBOOT', 'SCALE_OUT'] 
         and i.get('Outcome') != 'PENDING'),
        None
    )

    pending_action = next(
        (i for i in history 
         if i['Action'] in ['AUTONOMOUS_REBOOT', 'SCALE_OUT'] 
         and i.get('Outcome') == 'PENDING'),
        None
    )

    # HANDLE PENDING FIRST (FIXED)
    if pending_action:
        time_diff = int(time.time()) - int(pending_action['Timestamp'])

        if pending_action['Action'] == 'SCALE_OUT':
            if p3 < THRESHOLD:
                audit_table.update_item(
                    Key={'InstanceID': ASG_NAME, 'Timestamp': int(pending_action['Timestamp'])},
                    UpdateExpression="SET Outcome = :o",
                    ExpressionAttributeValues={':o': "SUCCESS"}
                )
            elif time_diff < 300:
                return {"status": "WAITING", "reason": "Scaling in progress"}
            else:
                audit_table.update_item(
                    Key={'InstanceID': ASG_NAME, 'Timestamp': int(pending_action['Timestamp'])},
                    UpdateExpression="SET Outcome = :o",
                    ExpressionAttributeValues={':o': "FAILED"}
                )

        else:
            if time_diff > 300:
                outcome = "SUCCESS" if p3 < THRESHOLD else "FAILED"
                audit_table.update_item(
                    Key={'InstanceID': ASG_NAME, 'Timestamp': int(pending_action['Timestamp'])},
                    UpdateExpression="SET Outcome = :o",
                    ExpressionAttributeValues={':o': outcome}
                )
            else:
                return {"status": "WAITING", "reason": f"Action in progress ({300-time_diff}s left)"}

    # --- WARM-UP GATE (MOVED HERE) ---
    ec2_desc = ec2.describe_instances(InstanceIds=[target_id])
    launch_time = ec2_desc['Reservations'][0]['Instances'][0]['LaunchTime']
    now = datetime.now(launch_time.tzinfo)
    age_seconds = (now - launch_time).total_seconds()

    if age_seconds < 600:
        return log_and_return(ASG_NAME, "STABLE", f"Warming up: {int(age_seconds)}s old")

    # --- CURRENT STATE GUARD ---
    if p3 < THRESHOLD:
        return log_and_return(ASG_NAME, "STABLE", f"Recovered/Healthy: {p3:.1f}%")

    # --- GLOBAL ESCALATION ---
    if last_remediation and last_remediation.get('Outcome') == 'FAILED' and last_remediation['Action'] == 'AUTONOMOUS_REBOOT':
        return execute_scale_out(ASG_NAME, target_id, "GLOBAL ESCALATION: reboot failed")

    # --- DECISION ENGINE (UNCHANGED) ---
    if len(cpu_points) >= 3:
        p1 = cpu_points[-3]['Average']
        p2 = cpu_points[-2]['Average']
        latest_net = net_points[-1]['Average'] if net_points else 0
        metrics_str = f"({p1:.1f}, {p2:.1f}, {p3:.1f})"

        if p1 < p2 < p3 and p3 > THRESHOLD:
            if (p3 - p1) > 20:
                if latest_net > NET_THRESHOLD:
                    return execute_scale_out(ASG_NAME, target_id, f"VIRAL SURGE: {metrics_str}")
                else:
                    return execute_reboot(target_id, f"SILENT LEAK: {metrics_str}")
            return log_and_return(ASG_NAME, "STABLE", f"Slow rise: {metrics_str}")

        if p1 > THRESHOLD and p2 > THRESHOLD and p3 > THRESHOLD:
            return execute_reboot(target_id, f"PLATEAU: {metrics_str}")

        if p2 > THRESHOLD and p3 < p2:
            return log_and_return(ASG_NAME, "STABLE", f"Blip: {metrics_str}")

        return log_and_return(ASG_NAME, "STABLE", f"Healthy: {metrics_str}")

    return log_and_return(ASG_NAME, "WAITING", "Gathering data...")


# --- ACTIONS ---
def execute_reboot(instance_id, reason):
    ec2.reboot_instances(InstanceIds=[instance_id])
    return log_and_return(ASG_NAME, "AUTONOMOUS_REBOOT", reason, outcome="PENDING")

def execute_scale_out(asg_name, instance_id, reason):
    response = asg.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
    current = response['AutoScalingGroups'][0]['DesiredCapacity']
    asg.set_desired_capacity(AutoScalingGroupName=asg_name, DesiredCapacity=current + 1)
    return log_and_return(ASG_NAME, "SCALE_OUT", reason, outcome="PENDING")

def log_and_return(resource_id, action, reason, outcome=None):
    ist_time = datetime.utcnow() + timedelta(hours=5, minutes=30)

    item = {
        'InstanceID': resource_id,
        'Timestamp': int(time.time()),
        'Action': action,
        'Reason': reason,
        'HumanReadableTime': ist_time.strftime("%Y-%m-%d %H:%M:%S")
    }

    if outcome:
        item['Outcome'] = outcome

    audit_table.put_item(Item=item)

    return {"status": action, "time_ist": ist_time.strftime("%H:%M:%S")}

