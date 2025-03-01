#!/bin/bash
# Simple script to start the sentiment analysis container

# Set the working directory to the project root
cd "$(dirname "$0")/.." || exit 1

# Start the cron container
docker compose up -d --no-deps cron