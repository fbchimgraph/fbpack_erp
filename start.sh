#!/usr/bin/env bash
gunicorn fbpack.wsgi:application
