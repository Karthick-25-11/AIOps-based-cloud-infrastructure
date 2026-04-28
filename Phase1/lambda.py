#22.04.2026

#works all 4 anomalies, here i tried to add memory layer(outcome)- to perform reboot/scaleout based on history, but that doesnt work, but all anomalies work fine

---------------------------

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
NET_THRESHOLD = 100000 # 100KB/s

def lambda_handler(event, context):
    # 1. DYNAMIC DISCOVERY
    asg_response = asg.describe_auto_scaling_groups(AutoScalingGroupNames=[ASG_NAME])
    asg_data = asg_response['AutoScalingGroups'][0]
    instances = asg_data['Instances']
    
    if not instances:
        return {"status": "ERROR", "reason": "No instances found"}
    
    target_id = instances[0]['InstanceId']

    # --- NEW LOGIC: WARM-UP GATE ---
    # Fetch instance launch time to prevent remediating brand new instances
    ec2_desc = ec2.describe_instances(InstanceIds=[target_id])
    launch_time = ec2_desc['Reservations'][0]['Instances'][0]['LaunchTime']
    now = datetime.now(launch_time.tzinfo) # Match timezone for subtraction
    age_seconds = (now - launch_time).total_seconds()

    if age_seconds < 600: # 10-minute warm-up gate
        return log_and_return(target_id, "STABLE", f"Warming up: {int(age_seconds)}s old")
    # -------------------------------

    # 2. FETCH GROUP METRICS
    dimensions = [{'Name': 'AutoScalingGroupName', 'Value': ASG_NAME}]
    common_params = {
        'Namespace': 'AWS/EC2', 'Dimensions': dimensions,
        'StartTime': datetime.utcnow() - timedelta(minutes=15),
        'EndTime': datetime.utcnow(), 'Period': 60, 'Statistics': ['Average']
    }

    cpu_stats = cw.get_metric_statistics(MetricName='CPUUtilization', **common_params)
    net_stats = cw.get_metric_statistics(MetricName='NetworkIn', **common_params)

    cpu_points = sorted(cpu_stats['Datapoints'], key=lambda x: x['Timestamp'])
    net_points = sorted(net_stats['Datapoints'], key=lambda x: x['Timestamp'])

    if not cpu_points:
        return log_and_return(target_id, "WAITING", "Gathering data...")

    p3 = cpu_points[-1]['Average']

    # --- NEW LOGIC: THE AUDITOR (CHECK PREVIOUS ACTION) ---
    response = audit_table.query(
        KeyConditionExpression=Key('InstanceID').eq(target_id),
        ScanIndexForward=False, # Get latest first
        Limit=50
    )
    history = response.get('Items', [])
    
    # Find the most recent actual remediation (Reboot or Scale)
    last_remediation = next((i for i in history if i['Action'] in ['AUTONOMOUS_REBOOT', 'SCALE_OUT']), None)

    if last_remediation and last_remediation.get('Outcome') == 'PENDING':
        time_diff = int(time.time()) - int(last_remediation['Timestamp'])
        
        if time_diff > 300: # Wait 5 mins before grading
            outcome = "SUCCESS" if p3 < THRESHOLD else "FAILED"
            audit_table.update_item(
                Key={'InstanceID': target_id, 'Timestamp': int(last_remediation['Timestamp'])},
                UpdateExpression="SET Outcome = :o",
                ExpressionAttributeValues={':o': outcome}
            )
            if outcome == "SUCCESS":
                return {"status": "STABLE", "reason": "Previous action succeeded"}
        else:
            # NEW LOGIC: Waiting Gate to prevent spamming while PENDING
            return {"status": "WAITING", "reason": f"Action in progress. {300-time_diff}s left in cooldown."}
    # -------------------------------------------------------

    # 3. DECISION ENGINE
    if len(cpu_points) >= 3:
        p1 = cpu_points[-3]['Average']
        p2 = cpu_points[-2]['Average']
        latest_net = net_points[-1]['Average'] if net_points else 0
        metrics_str = f"({p1:.1f}, {p2:.1f}, {p3:.1f})"

        # Rising Pattern Check (Sustained Growth)
        if p1 < p2 < p3 and p3 > THRESHOLD:
            if (p3 - p1) > 20:
                if latest_net > NET_THRESHOLD:
                    reason = f"VIRAL SURGE: {metrics_str} | Net: {latest_net/1024:.1f}KB/s"
                    return execute_scale_out(ASG_NAME, target_id, reason)
                else:
                    # --- NEW LOGIC: ESCALATION CHECK ---
                    if last_remediation and last_remediation.get('Outcome') == 'FAILED' and last_remediation['Action'] == 'AUTONOMOUS_REBOOT':
                        reason = f"SILENT LEAK (RETRY): Reboot failed, escalating to Scale Out | {metrics_str}"
                        return execute_scale_out(ASG_NAME, target_id, reason)
                    
                    reason = f"SILENT LEAK: {metrics_str} | Low Traffic"
                    return execute_reboot(target_id, reason)
            
            return log_and_return(target_id, "STABLE", f"Slow rise detected: {metrics_str}")

        # Plateau Check
        if p1 > THRESHOLD and p2 > THRESHOLD and p3 > THRESHOLD:
            return execute_reboot(target_id, f"PLATEAU: {metrics_str}")

        # BLIP CHECK
        if p2 > THRESHOLD and p3 < p2:
            reason = f"Anomaly detected but trend is stabilizing: {metrics_str}"
            return log_and_return(target_id, "STABLE", reason)

        return log_and_return(target_id, "STABLE", f"Group Healthy: {p3:.1f}% | {metrics_str}")

    return log_and_return(target_id, "WAITING", "Gathering data...")

def execute_reboot(instance_id, reason):
    ec2.reboot_instances(InstanceIds=[instance_id])
    return log_and_return(instance_id, "AUTONOMOUS_REBOOT", reason, outcome="PENDING")

def execute_scale_out(asg_name, instance_id, reason):
    response = asg.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
    current = response['AutoScalingGroups'][0]['DesiredCapacity']
    asg.set_desired_capacity(AutoScalingGroupName=asg_name, DesiredCapacity=current + 1)
    return log_and_return(instance_id, "SCALE_OUT", reason, outcome="PENDING")

def log_and_return(instance_id, action, reason, outcome=None):
    ist_time = datetime.utcnow() + timedelta(hours=5, minutes=30)
    
    item = {
        'InstanceID': instance_id,
        'Timestamp': int(time.time()),
        'Action': action,
        'Reason': reason,
        'HumanReadableTime': ist_time.strftime("%Y-%m-%d %H:%M:%S")
    }
    if outcome:
        item['Outcome'] = outcome
        
    audit_table.put_item(Item=item)
    return {"status": action, "time_ist": ist_time.strftime("%H:%M:%S")}