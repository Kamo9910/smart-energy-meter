from flask import Flask, render_template_string, redirect, url_for, jsonify, request
import boto3
import json

app = Flask(__name__)

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('EnergyMeter')

iot_client = boto3.client('iot-data', region_name='us-east-1')

def send_relay_command(command):
    iot_client.publish(
        topic='energy/relay',
        qos=1,
        payload=json.dumps({'command': command})
    )

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
        .chart-container { background: #0f3460; border-radius: 10px; padding: 20px; margin-bottom: 20px; }
        .stage { text-align: center; padding: 10px; border-radius: 10px; margin-bottom: 20px; }
        .stage-0 { background: #2d6a4f; }
        .stage-alert { background: #e94560; }
        .tips { background: #0f3460; border-radius: 10px; padding: 15px; margin-bottom: 20px; }
    </style>
</head>
<body>
    <h1>⚡ Smart Energy Meter</h1>

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
        <div class="card">
            <h2>R{{ projected_cost }}</h2>
            <p>Monthly Bill</p>
        </div>
    </div>
     
    <div style="text-align:center; margin-bottom:20px;">
        <form action="/relay/on" method="post" style="display:inline">
            <button style="padding:15px 30px; background:#2d6a4f; color:white; border:none; border-radius:10px; font-size:18px; cursor:pointer; margin:10px;">
                Turn ON 💡
            </button>
        </form>
        <form action="/relay/off" method="post" style="display:inline">
            <button style="padding:15px 30px; background:#e94560; color:white; border:none; border-radius:10px; font-size:18px; cursor:pointer; margin:10px;">
                Turn OFF 💡
            </button>
        </form>
    </div>
    <div class="tips">
        <p style="color:#a8dadc; margin-bottom:10px;">💡 Energy Saving Tips:</p>
        {% for tip in recommendations %}
        <p style="margin:5px 0;">• {{ tip }}</p>
        {% endfor %}
    </div>

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
        
        avg_power = sum(powers) / len(powers) if powers else 0
        projected_cost = round((avg_power / 1000) * 730 * 2.50, 2)
        
        recommendations = []
        if avg_power > 100:
            recommendations.append("High consumption detected — check for appliances left on")
        if avg_power > 50:
            recommendations.append("Consider switching to LED bulbs")
        recommendations.append("Switch off appliances at the wall during load shedding")
        recommendations.append("Run heavy appliances during off-peak hours")

        latest = items[-1] if items else {}

    except Exception as e:
        timestamps, powers, voltages = [], [], []
        projected_cost = 0
        recommendations = []
        latest = {}

    return render_template_string(HTML,
        voltage=latest.get('voltage', 0),
        current=latest.get('current', 0),
        power=latest.get('power', 0),
        projected_cost=projected_cost,
        recommendations=recommendations,
        timestamps=timestamps,
        powers=powers,
        voltages=voltages,
    )

iot_client = boto3.client('iot-data', region_name='us-east-1')

def send_relay_command(command):
    iot_client.publish(
        topic='energy/relay',
        qos=1,
        payload=json.dumps({'command': command})
    )

@app.route('/relay/on', methods=['POST'])
def relay_on():
    send_relay_command('ON')
    return redirect(url_for('index'))

@app.route('/relay/off', methods=['POST'])
def relay_off():
    send_relay_command('OFF')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)
