#!/bin/bash
gunicorn fbpack.wsgi:application --bind 0.0.0.0:$PORT
