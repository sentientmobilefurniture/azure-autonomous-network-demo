#!/bin/bash
# Azure Web App startup command
cd /home/site/wwwroot
gunicorn app.main:app -w 2 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
