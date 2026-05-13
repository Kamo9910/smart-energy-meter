# Smart Energy Meter 🇿🇦⚡

A real-time IoT energy monitoring system built with Raspberry Pi 5 and AWS cloud services. Designed specifically for South African households to monitor electricity consumption, detect load shedding, and control appliances remotely from anywhere in the world.

## The Problem
South Africa faces chronic load shedding and expensive electricity bills. This system gives households real-time visibility and control over their energy consumption.

## Features
- ⚡ Real-time voltage and current monitoring using ACS712 and ZMPT101B sensors
- 📊 Live power consumption dashboard accessible globally via AWS EC2
- 🔔 Automatic email alerts when load shedding is detected via AWS SES
- 💡 Remote appliance control via relay module from anywhere in the world
- 📈 Historical energy consumption graphs
- 💰 Projected monthly electricity bill calculation in Rands
- 🚨 Abnormal consumption anomaly detection via AWS Lambda
- 🌍 Load shedding stage monitoring via EskomSePush API

## Architecture# smart-energy-meter
Raspberry Pi 5 → API Gateway → Lambda → DynamoDB
→ SES (email alerts)
EC2 Dashboard → IoT Core → Raspberry Pi → Relay → Appliance## Hardware
- Raspberry Pi 5 4GB
- ACS712 20A Current Sensor
- ZMPT101B Voltage Sensor
- ADS1115 16-Bit ADC
- Relay Module
- Breadboard and jumper wires

## AWS Services Used
- AWS IoT Core
- AWS Lambda
- AWS API Gateway
- AWS DynamoDB
- AWS SES
- AWS EC2

## Project Versions
- **V1** — Live sensor readings, local web dashboard, DynamoDB storage
- **V2** — Load shedding alerts, SES email notifications, historical graphs
- **V3** — Serverless Lambda architecture, global EC2 dashboard, remote relay control via IoT Core

## Tech Stack
- Python 3
- Flask
- Raspberry Pi OS
- AWS SDK (boto3)
- AWS IoT SDK

## Author
Danny — Red Seal Millwright & AWS Certified Cloud Engineer
Johannesburg, South Africa
![Architecture Diagram](A.gif)
