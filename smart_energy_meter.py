import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
from datetime import datetime, timezone, timedelta
import boto3
import time
import math
import lgpio
import threading
import urllib.request
import json
from awscrt import mqtt
from awsiot import mqtt_connection_builder
from flask import Flask, render_template_string, redirect, url_for, jsonify

# GPIO Setup
h = lgpio.gpiochip_open(0)
RELAY_PIN = 17
LED_PIN = 27
lgpio.gpio_claim_output(h, RELAY_PIN)
lgpio.gpio_claim_output(h, LED_PIN)
lgpio.gpio_write(h, RELAY_PIN, 1)
lgpio.gpio_write(h, LED_PIN, 1)

ENDPOINT = "a132uk2z08cpnl-ats.iot.us-east-1.amazonaws.com"
CLIENT_ID = "EnergyMeterPi"
CERT = "/home/dkntshala/device-certificate.pem.crt"
KEY = "/home/dkntshala/private.pem.key"
CA = "/home/dkntshala/AmazonRootCA1.pem"
TOPIC = "energy/relay"

def on_message_received(topic, payload, **kwargs):
    message = json.loads(payload)
    command = message.get('command')
    global bulb_state
    if command == 'ON':
        bulb_state = True
        lgpio.gpio_write(h, RELAY_PIN, 0)
        lgpio.gpio_write(h, LED_PIN, 0)
        print("Relay ON — command received from cloud")
    elif command == 'OFF':
        bulb_state = False
        lgpio.gpio_write(h, RELAY_PIN, 1)
        lgpio.gpio_write(h, LED_PIN, 1)
        print("Relay OFF — command received from cloud")

def connect_iot():
    mqtt_connection = mqtt_connection_builder.mtls_from_path(
        endpoint=ENDPOINT,
        cert_filepath=CERT,
        pri_key_filepath=KEY,
        ca_filepath=CA,
        client_id=CLIENT_ID,
        clean_session=False,
        keep_alive_secs=30
    )
    connect_future = mqtt_connection.connect()
    connect_future.result()
    print("Connected to AWS IoT Core")
    subscribe_future, _ = mqtt_connection.subscribe(
        topic=TOPIC,
        qos=mqtt.QoS.AT_LEAST_ONCE,
        callback=on_message_received
    )
    subscribe_future.result()
    print(f"Subscribed to {TOPIC}")
    return mqtt_connection

# Sensor Setup
i2c = busio.I2C(board.SCL, board.SDA)
ads = ADS.ADS1115(i2c)
current_channel = AnalogIn(ads, 0)
voltage_channel = AnalogIn(ads, 1)
sensor_data = {'voltage': 0, 'current': 0, 'power': 0}
lambda_data = {'projected_cost': 0, 'anomaly': False, 'recommendations': []}

# DynamoDB Setup
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('EnergyMeter')

# Shared state
bulb_state = False
sensor_data = {'voltage': 0, 'current': 0, 'power': 0}

def get_rms_current(samples=1000):
    sum_squares = 0
    for _ in range(samples):
        voltage = current_channel.voltage
        current = (voltage - 2.60) / 0.066
        sum_squares += current ** 2
        time.sleep(0.001)
    return round(math.sqrt(sum_squares / samples), 4)

def get_rms_voltage(samples=500):
    sum_squares = 0
    for _ in range(samples):
        raw = voltage_channel.voltage
        scaled = (raw - 2.5) * 220 * 3.43
        sum_squares += scaled ** 2
        time.sleep(0.001)
    return round(math.sqrt(sum_squares / samples), 2)

def check_loadshedding():
    try:
        api_key = '231D79BC-321C4EC0-888BC396-7C3622A9'
        url = 'https://developer.sepush.co.za/business/2.0/status'
        req = urllib.request.Request(url)
        req.add_header('Token', api_key)
        response = urllib.request.urlopen(req)
        data = json.loads(response.read())
        
        stage = data['status']['eskom']['stage']
        updated = data['status']['eskom']['stage_updated']
        
        return int(stage), updated
    except Exception as e:
        print(f"Load shedding check error: {e}")
        return None, None

last_stage = 0

def send_loadshedding_alert(stage, updated):
    global last_stage
    if stage == last_stage:
        return
    
    ses = boto3.client('ses', region_name='us-east-1')
    
    if stage > 0:
        subject = f"⚠️ Load Shedding Alert — Stage {stage}"
        message = f"Load shedding is now Stage {stage}.\nLast updated: {updated}\n\nPrepare your generator!"
    else:
        subject = "✅ Power Restored — Stage 0"
        message = f"Load shedding has ended.\nLast updated: {updated}\n\nPower is back!"
    
    ses.send_email(
        Source='dkkamo4@gmail.com',
        Destination={'ToAddresses': ['dkkamo4@gmail.com']},
        Message={
            'Subject': {'Data': subject},
            'Body': {'Text': {'Data': message}}
        }
    )
    
    last_stage = stage
    print(f"Alert sent — Stage {stage}")

def loadshedding_loop():
    while True:
        stage, updated = check_loadshedding()
        if stage is not None:
            print(f"Load shedding stage: {stage}")
            send_loadshedding_alert(stage, updated)
        time.sleep(1800)

def sensor_loop():
    while True:
        try:
            current = get_rms_current()
            voltage = get_rms_voltage()
            power = round(voltage * current, 2)
            sensor_data['voltage'] = voltage
            sensor_data['current'] = current
            sensor_data['power'] = power

            api_url = 'https://aatsqiy4z0.execute-api.us-east-1.amazonaws.com/prod/data'
            data = json.dumps({
                'device_id': 'energy-meter-01',
                'voltage': str(voltage),
                'current': str(current),
                'power': str(power)
            }).encode('utf-8')

            req = urllib.request.Request(api_url, data=data, method='POST')
            req.add_header('Content-Type', 'application/json')
            response = urllib.request.urlopen(req)
            result = json.loads(response.read())

            print(f"Voltage: {voltage}V | Current: {current}A | Power: {power}W")
            print(f"Projected bill: R{result['projected_cost_rands']} | Anomaly: {result['anomaly_detected']}")
            print(f"Recommendations: {result['recommendations'][0]}")
            lambda_data['projected_cost'] = result['projected_cost_rands']
            lambda_data['anomaly'] = result['anomaly_detected']
            lambda_data['recommendations'] = result['recommendations']

        except Exception as e:
            print(f"Sensor error: {e} - retrying...")
        time.sleep(5)

# Flask App
app = Flask(__name__)

HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>Smart Energy Meter</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/3.9.1/chart.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Arial; background: #1a1a2e; color: white; padding: 20px; }
        h1 { color: #e94560; text-align: center; margin-bottom: 20px; }
        .cards { display: flex; justify-content: center; gap: 15px; flex-wrap: wrap; margin-bottom: 20px; }
        .card { background: #0f3460; padding: 20px; border-radius: 10px; text-align: center; min-width: 150px; }
        .card h2 { font-size: 28px; color: #e94560; }
        .card p { font-size: 14px; color: #a8dadc; }
        .btn { display: block; margin: 20px auto; padding: 15px 40px; font-size: 20px; border: none; border-radius: 10px; cursor: pointer; }
        .on { background: #e94560; color: white; }
        .off { background: #0f3460; color: white; }
        .chart-container { background: #0f3460; border-radius: 10px; padding: 20px; margin-bottom: 20px; }
        .stage { text-align: center; padding: 10px; border-radius: 10px; margin-bottom: 20px; }
        .stage-0 { background: #2d6a4f; }
        .stage-alert { background: #e94560; }
    </style>
</head>
<body>
    <h1>⚡ Smart Energy Meter</h1>
    
    <div class="stage {{ 'stage-0' if stage == 0 else 'stage-alert' }}">
        {% if stage == 0 %}
            ✅ No Load Shedding — Stage 0
        {% else %}
            ⚠️ Load Shedding Active — Stage {{ stage }}
        {% endif %}
    </div>
    {% if anomaly %}
    <div class="stage stage-alert">
        ⚠️ Abnormal Consumption Detected — Check your appliances!
    </div>
    {% endif %}

    <div class="stage stage-0" style="background:#0f3460">
        📊 Projected Monthly Bill: <strong>R{{ projected_cost }}</strong>
    </div>

    <div style="background:#0f3460; border-radius:10px; padding:15px; margin-bottom:20px;">
        <p style="color:#a8dadc; margin-bottom:10px;">💡 Energy Saving Tips:</p>
        {% for tip in recommendations %}
        <p style="margin:5px 0;">• {{ tip }}</p>
        {% endfor %}
    </div>
    <div class="cards">
        <div class="card">
            <h2>{{ voltage }}V</h2>
            <p>Voltage</p>
        </div>
        <div class="card">
            <h2>{{ current }}A</h2>
            <p>Current</p>
        </div>
        <div class="card">
            <h2>{{ power }}W</h2>
            <p>Power</p>
        </div>
    </div>

    <form action="/toggle" method="post">
        <button class="btn {{ 'on' if bulb_on else 'off' }}" type="submit">
            {{ 'Turn OFF 💡' if bulb_on else 'Turn ON 💡' }}
        </button>
    </form>

    <div class="chart-container">
        <canvas id="powerChart"></canvas>
    </div>

    <div class="chart-container">
        <canvas id="voltageChart"></canvas>
    </div>

    <script>
        const labels = {{ timestamps | safe }};
        const powerData = {{ powers | safe }};
        const voltageData = {{ voltages | safe }};

        new Chart(document.getElementById('powerChart'), {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Power (W)',
                    data: powerData,
                    borderColor: '#e94560',
                    backgroundColor: 'rgba(233,69,96,0.1)',
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                plugins: { legend: { labels: { color: 'white' } } },
                scales: {
                    x: { ticks: { color: 'white' }, grid: { color: '#333' } },
                    y: { ticks: { color: 'white' }, grid: { color: '#333' } }
                }
            }
        });

        new Chart(document.getElementById('voltageChart'), {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Voltage (V)',
                    data: voltageData,
                    borderColor: '#a8dadc',
                    backgroundColor: 'rgba(168,218,220,0.1)',
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                plugins: { legend: { labels: { color: 'white' } } },
                scales: {
                    x: { ticks: { color: 'white' }, grid: { color: '#333' } },
                    y: { ticks: { color: 'white' }, grid: { color: '#333' } }
                }
            }
        });

        setTimeout(() => location.reload(), 10000);
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    try:
        response = table.scan(Limit=20)
        items = sorted(response['Items'], key=lambda x: x['timestamp'])
        timestamps = [item['timestamp'][11:19] for item in items]
        powers = [float(item['power']) for item in items]
        voltages = [float(item['voltage']) for item in items]
    except:
        timestamps, powers, voltages = [], [], []

    return render_template_string(HTML,
        state='ON' if bulb_state else 'OFF',
        bulb_on=bulb_state,
        voltage=sensor_data['voltage'],
        current=sensor_data['current'],
        power=sensor_data['power'],
        stage=last_stage,
        timestamps=timestamps,
        powers=powers,
        voltages=voltages,
        anomaly=lambda_data['anomaly'],
        projected_cost=lambda_data['projected_cost'],
        recommendations=lambda_data['recommendations'],
    )

@app.route('/toggle', methods=['POST'])
def toggle():
    global bulb_state
    bulb_state = not bulb_state
    if bulb_state:
        lgpio.gpio_write(h, RELAY_PIN, 0)
        lgpio.gpio_write(h, LED_PIN, 0)
    else:
        lgpio.gpio_write(h, RELAY_PIN, 1)
        lgpio.gpio_write(h, LED_PIN, 1)
    return redirect(url_for('index'))

if __name__ == '__main__':
    mqtt_connection = connect_iot()
    sensor_thread = threading.Thread(target=sensor_loop, daemon=True)
    sensor_thread.start()
    loadshedding_thread = threading.Thread(target=loadshedding_loop, daemon=True)
    loadshedding_thread.start()
    app.run(host='0.0.0.0', port=5000)
